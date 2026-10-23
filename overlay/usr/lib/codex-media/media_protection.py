"""Give routing priority when media services cause sustained memory or I/O pressure."""
import json,os,subprocess,time,http.client,socket
from pathlib import Path
DOCKER='/usr/bin/docker'
STATUS='/tmp/codex-media-protection.json'
PERSIST='/overlay/media-stack/resource-protection-state.json'
persist_error_reported=False
ALLOWED=('autofilm','emby','mediawarp','openlist')
RESUME_AVAILABLE_MB={'openlist':192,'emby':256,'mediawarp':192,'autofilm':224}
RESUME_ORDER=('openlist','emby','mediawarp','autofilm')
STABLE_SECONDS=120
STAGE_SECONDS=120

class PressureGate:
 def __init__(self):self.since={}
 def observe(self,s,now):
  if s['available_mb']<64:return 'critical_memory'
  swapping=s['swap_in_mb_per_second'] is not None and s['swap_in_mb_per_second']>=2
  missing_counter_with_low_headroom=s['swap_in_mb_per_second'] is None and s['available_mb']<192
  conditions={'low_memory':(s['available_mb']<128,15),'swap_io_stall':(s['iowait_percent']>=30 and (swapping or missing_counter_with_low_headroom),15),'cpu_saturation':(s['cpu_busy_percent']>=90 and s['media_cpu_percent']>=8,20)}
  for key,(bad,seconds) in conditions.items():
   if bad:
    if key not in self.since:self.since[key]=now
    if now-self.since[key]>=seconds:return key
   else:self.since.pop(key,None)
  return None

class DockerHTTP(http.client.HTTPConnection):
 def __init__(self):super().__init__('localhost',timeout=1)
 def connect(self):
  self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.sock.settimeout(self.timeout);self.sock.connect('/var/run/docker.sock')

def process_inspect(proc_root='/proc',cgroup_root='/sys/fs/cgroup'):
 names={'embyserver':'emby','mediawarp':'mediawarp','openlist':'openlist','autofilm':'autofilm'}
 candidates={n:[] for n in ALLOWED}
 for root in Path(proc_root).iterdir():
  if not root.name.isdigit():continue
  try:
   exe=os.path.basename((root/'cmdline').read_bytes().split(b'\0',1)[0].decode()).lower()
   name=names.get(exe)
   if not name:continue
   rows=(root/'cgroup').read_text().splitlines()
   for row in rows:
    if not row.startswith('0::/docker/'):continue
    ident=row[len('0::/docker/'):]
    if len(ident)==64 and all(c in '0123456789abcdef' for c in ident) and (Path(cgroup_root)/'docker'/ident/'cgroup.procs').exists():
     candidates[name].append({'id':ident,'pid':int(root.name),'running':True})
  except (OSError,UnicodeError):continue
 return {n:(rows[0]|{'source':'process'} if len(rows)==1 else {'id':'','pid':0,'running':False,'source':'unknown'}) for n,rows in candidates.items()}

def inspect():
 # A blocked container inspect must not freeze all memory/CPU protection.
 result={};fallback=None
 for name in ALLOWED:
  conn=DockerHTTP()
  try:
   conn.request('GET','/containers/'+name+'/json');response=conn.getresponse()
   if response.status!=200:raise OSError('Docker inspect unavailable')
   row=json.loads(response.read())
   result[name]={'id':row['Id'],'running':row['State']['Running'],'pid':row['State']['Pid'],'source':'docker'}
  except (OSError,ValueError,KeyError,http.client.HTTPException):
   if fallback is None:fallback=process_inspect()
   result[name]=fallback[name]
  finally:conn.close()
 return result

def cpu_paths(containers):
 paths=[]
 for data in containers.values():
  pid=data['pid']
  if not pid:continue
  try:
   for row in open('/proc/'+str(pid)+'/cgroup'):
    _,controllers,rel=row.strip().split(':',2)
    if not controllers:
     p='/sys/fs/cgroup'+rel+'/cpu.stat'
     if os.path.exists(p):paths.append(p)
    elif 'cpuacct' in controllers.split(','):
     for mount in ('cpuacct','cpu,cpuacct','cpu'):
      p='/sys/fs/cgroup/'+mount+rel+'/cpuacct.usage'
      if os.path.exists(p):paths.append(p);break
  except OSError:pass
 return paths

def memory_high_paths(containers):
 # Docker keeps the container ID across restarts; refresh IDs with CPU paths.
 data=containers.get('emby',{})
 ident=data.get('id','')
 if len(ident)!=64 or any(c not in '0123456789abcdef' for c in ident):return []
 return ['/sys/fs/cgroup/docker/'+ident+'/memory.high']

def apply_memory_high(paths):
 for path in paths:
  try:
   # DLL mappings and SQLite pages are part of memory.current too. A low high
   # watermark repeatedly evicts them on TF storage despite ample host memory.
   value=str(320*1048576)
   with open(path) as f:current=f.read().strip()
   if current!=value:
    with open(path,'w') as f:f.write(value+'\n')
  except FileNotFoundError:pass

def read_cpu_ns(path):
 with open(path) as stream:
  if path.endswith('/cpu.stat'):
   counters=dict(row.split() for row in stream if len(row.split())==2)
   return int(counters['usage_usec'])*1000
  return int(stream.read())

def read_swapin(proc_root='/proc', block_root='/sys/class/block'):
 # Some vendor kernels omit VM_EVENT_COUNTERS. Block stats count 512-byte sectors,
 # independent of page size; only active swap partitions are safe fallbacks.
 try:
  with open(proc_root+'/vmstat') as f:
   for row in f:
    fields=row.split()
    if len(fields)==2 and fields[0]=='pswpin':
     return int(fields[1])*os.sysconf('SC_PAGE_SIZE'),'vmstat:pswpin'
 except (OSError,ValueError):pass
 try:
  with open(proc_root+'/swaps') as f:rows=[r.split() for r in f.readlines()[1:] if r.strip()]
  if not rows:return 0,'no_active_swap'
  devices=[];total=0
  for fields in rows:
   if len(fields)<5 or fields[1]!='partition' or not fields[0].startswith('/dev/'):
    return None,'unavailable'
   device=os.path.realpath(fields[0]);name=os.path.basename(device)
   with open(block_root+'/'+name+'/stat') as f:stats=f.read().split()
   total+=int(stats[2])*512;devices.append(device)
  return total,'block:'+','.join(sorted(devices))
 except (OSError,ValueError,IndexError):return None,'unavailable'

def snapshot(paths):
 cpu_rows={r.split()[0]:list(map(int,r.split()[1:9])) for r in open('/proc/stat') if r.startswith('cpu')}
 cpu=cpu_rows.pop('cpu')
 mem={r.split(':')[0]:int(r.split()[1]) for r in open('/proc/meminfo') if ':' in r}
 swapin,swap_source=read_swapin()
 media=0
 for p in paths:
  try:media+=read_cpu_ns(p)
  except OSError:pass
 return {'cpu':cpu,'cpu_by_core':cpu_rows,'available_mb':round(mem['MemAvailable']/1024,2),'swap_in_bytes':swapin,'swap_counter_source':swap_source,'media_ns':media,'now':time.monotonic()}

def interval(a,b):
 d=[max(0,x-y) for x,y in zip(b['cpu'],a['cpu'])];total=max(1,sum(d));dt=max(.1,b['now']-a['now'])
 swap_rate=None
 if a.get('swap_counter_source')==b.get('swap_counter_source') and a['swap_in_bytes'] is not None and b['swap_in_bytes'] is not None and b['swap_in_bytes']>=a['swap_in_bytes']:
  swap_rate=round((b['swap_in_bytes']-a['swap_in_bytes'])/1048576/dt,3)
 per_core={};softirq_per_core={}
 for name,after in b.get('cpu_by_core',{}).items():
  before=a.get('cpu_by_core',{}).get(name)
  if before is None or any(x<y for x,y in zip(after,before)):continue
  delta=[x-y for x,y in zip(after,before)];ticks=sum(delta)
  if ticks<=0:continue
  per_core[name]=round(100*(ticks-delta[3]-delta[4])/ticks,2)
  softirq_per_core[name]=round(100*delta[6]/ticks,2)
 return {'available_mb':b['available_mb'],'cpu_busy_percent':round(100*(sum(d)-d[3]-d[4])/total,2),'iowait_percent':round(100*d[4]/total,2),'swap_in_mb_per_second':swap_rate,'swap_counter_source':b.get('swap_counter_source'),'media_cpu_percent':round(max(0,b['media_ns']-a['media_ns'])/1e9/dt/max(1,os.cpu_count())*100,2),'cpu_busy_per_core':per_core,'softirq_per_core':softirq_per_core,'max_core_busy_percent':max(per_core.values()) if per_core else None}

class CorePressure:
 def __init__(self):self.since={}
 def observe(self,measured,now):
  busy=measured.get('cpu_busy_per_core',{});soft=measured.get('softirq_per_core',{})
  for name in list(self.since):
   if busy.get(name,0)<95:self.since.pop(name,None)
  for name,percent in busy.items():
   if percent>=95:self.since.setdefault(name,now)
  durations={name:round(now-since,1) for name,since in self.since.items()}
  return {'single_core_saturation_seconds':max(durations.values(),default=0),'network_softirq_hotspot':any(seconds>=20 and soft.get(name,0)>=80 for name,seconds in durations.items())}

def safe_to_resume(measured,name='emby'):
 peak=measured.get('max_core_busy_percent')
 swap=measured.get('swap_in_mb_per_second')
 return measured['available_mb']>=RESUME_AVAILABLE_MB[name] and measured['cpu_busy_percent']<80 and measured['iowait_percent']<10 and peak is not None and peak<95 and not measured.get('network_softirq_hotspot',False) and (swap is None or swap<2)

class RecoveryPlan:
 def __init__(self,old,boot_id,now):
  self.attempts=[]
  owned=[n for n in old.get('stopped_by_guard',[]) if n in ALLOWED]
  phases=old.get('service_phases',{})
  self.phases={n:phases.get(n,'stopping') for n in owned}
  self.phases={n:(phase if phase in ('stopping','stopped','starting') else 'stopping') for n,phase in self.phases.items()}
  last=old.get('last_action') or {}
  if last.get('action')=='restart_media_stage':
   for n in last.get('containers',[]):
    if n in owned:self.phases[n]='starting'
  if old.get('boot_id')==boot_id:
   self.attempts=[v for v in old.get('recovery_attempts',[]) if isinstance(v,dict) and v.get('name') in ALLOWED and isinstance(v.get('uptime'),(int,float)) and 0<=now-v['uptime']<3600]
   # Preserve the hourly cooldown of the preceding guard version.
   if not self.attempts:
    recent=[v for v in old.get('recovery_uptimes',[]) if isinstance(v,(int,float)) and 0<=now-v<3600]
    if recent:self.attempts=[{'name':n,'uptime':max(recent)} for n in ALLOWED]
  self.healthy_since=None;self.candidate=None
 def next(self,stopped,measured,now,last_stop):
  self.attempts=[v for v in self.attempts if 0<=now-v['uptime']<3600]
  name=next((n for n in RESUME_ORDER if n in stopped),None)
  if name!=self.candidate:self.healthy_since=None;self.candidate=name
  if name is None:return None
  if not safe_to_resume(measured,name):self.healthy_since=None;return None
  if self.healthy_since is None:self.healthy_since=now
  if now-self.healthy_since<STABLE_SECONDS or now-last_stop<600:return None
  if any(v['name']==name for v in self.attempts):return None
  if self.attempts and now-max(v['uptime'] for v in self.attempts)<STAGE_SECONDS:return None
  return name
 def requested(self,name,now):
  self.attempts.append({'name':name,'uptime':now});self.healthy_since=None;self.phases[name]='starting'
 def stopping(self,names):
  for name in names:self.phases[name]='stopping'
 def reconcile(self,owned,containers):
  pending=[]
  for name in owned:
   phase=self.phases.setdefault(name,'stopping')
   if phase=='starting' and containers[name]['running']:
    self.phases.pop(name,None);continue
   if phase=='stopping' and not containers[name]['running'] and containers[name].get('source','docker')=='docker':self.phases[name]='stopped'
   pending.append(name)
  return pending

def restore_guard_state(old,boot_id,now):
 if not isinstance(old,dict):return [],0,[],None
 stopped=[n for n in old.get('stopped_by_guard',[]) if n in ALLOWED]
 last_stop=now if stopped else 0;recoveries=[]
 if old.get('boot_id')==boot_id:
  value=old.get('last_stop_uptime')
  if isinstance(value,(int,float)) and 0<=value<=now:last_stop=value
  recoveries=[v for v in old.get('recovery_uptimes',[]) if isinstance(v,(int,float)) and 0<=now-v<3600]
 return stopped,last_stop,recoveries,old.get('last_action')

def recover_lost_stop_intent(old,containers):
 # r9 could clear ownership while a timed-out stop request was still pending.
 # Reclaim only its recorded targets, with an authoritative Docker exit.
 if not isinstance(old,dict):return {}
 action=old.get('last_action') or {}
 if action.get('action')!='stop_media' or action.get('result')!='requested':return old
 owned=[n for n in old.get('stopped_by_guard',[]) if n in ALLOWED]
 phases=dict(old.get('service_phases') or {})
 for name in action.get('containers',[]):
  row=containers.get(name,{})
  if name in ALLOWED and name not in owned and row.get('source')=='docker' and row.get('running') is False:
   owned.append(name);phases[name]='stopped'
 return old|{'stopped_by_guard':owned,'service_phases':phases}


def write(data):
 with open(STATUS+'.tmp','w') as f:
  json.dump(data,f);f.flush();os.fsync(f.fileno())
 os.replace(STATUS+'.tmp',STATUS)

def load_state():
 for path in (STATUS,PERSIST):
  try:
   with open(path) as f:data=json.load(f)
   if isinstance(data,dict):return data
  except (OSError,ValueError,TypeError):pass
 return {}

def persist_state(data):
 # Only ownership/actions change on TF storage; five-second measurements stay in tmpfs.
 keys=('boot_id','stopped_by_guard','last_stop_uptime','recovery_uptimes','recovery_attempts','last_action','service_phases')
 state={k:data.get(k,{}) if k=='service_phases' else data[k] for k in keys}
 try:
  with open(PERSIST) as f:
   if json.load(f)==state:return
 except (OSError,ValueError,TypeError):pass
 with open(PERSIST+'.tmp','w') as f:
  os.chmod(PERSIST+'.tmp',0o600);json.dump(state,f);f.flush();os.fsync(f.fileno())
 os.replace(PERSIST+'.tmp',PERSIST)

def checkpoint(boot_id,stopped,last_stop,recoveries,last_action,measured,plan):
 global persist_error_reported
 data={'epoch':time.time(),'boot_id':boot_id,'last_stop_uptime':last_stop,'recovery_uptimes':recoveries,'recovery_attempts':plan.attempts,'next_recovery':plan.candidate,'state':'media_suspended_for_routing' if stopped else 'protecting','measurements':measured,'stopped_by_guard':stopped,'last_action':last_action,'automatic_recoveries_last_hour':len(recoveries),'thresholds':{'critical_available_mb':64,'sustained_available_mb':128,'memory_duration_seconds':15,'sustained_iowait_percent':30,'swap_in_mb_per_second':2,'cpu_busy_percent':90,'cpu_duration_seconds':20,'resume_available_mb':RESUME_AVAILABLE_MB,'resume_cpu_busy_percent':80,'resume_stable_seconds':STABLE_SECONDS,'recovery_stage_seconds':STAGE_SECONDS}}
 data['service_phases']={n:plan.phases.get(n,'stopping') for n in stopped}
 write(data)
 try:persist_state(data);persist_error_reported=False
 except OSError:
  if not persist_error_reported:print('media-protection: persistent state unavailable; tmpfs protection remains active',flush=True)
  persist_error_reported=True

def stop(names):
 assert names and all(n in ALLOWED for n in names)
 subprocess.run([DOCKER,'stop','--time','8',*names],timeout=30,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

def run():
 gate=PressureGate();core_pressure=CorePressure();hotspot_reported=False
 with open('/proc/sys/kernel/random/boot_id') as f:boot_id=f.read().strip()
 old=recover_lost_stop_intent(load_state(),inspect())
 stopped,last_stop,recoveries,last_action=restore_guard_state(old,boot_id,time.monotonic())
 plan=RecoveryPlan(old if isinstance(old,dict) else {},boot_id,time.monotonic())
 paths=[];high_paths=[];previous=None;last_path_check=0;last_error=None
 while True:
  try:
   now=time.monotonic()
   if now-last_path_check>=60 or not last_path_check:
    containers=inspect();paths=cpu_paths(containers);high_paths=memory_high_paths(containers);last_path_check=now
   apply_memory_high(high_paths)
   current=snapshot(paths)
   if previous is None:previous=current;time.sleep(5);continue
   measured=interval(previous,current);previous=current
   measured.update(core_pressure.observe(measured,now))
   hotspot=measured['network_softirq_hotspot']
   if hotspot and not hotspot_reported:print('media-protection: sustained single-core network softirq pressure; inspect network driver',flush=True)
   hotspot_reported=hotspot
   reason=gate.observe(measured,now)
   recoveries=[t for t in recoveries if now-t<3600]
   if reason:
    running=inspect()
    # Shed one service, then remeasure before touching the next service.
    order=('emby','autofilm') if reason=='critical_memory' else ('autofilm','emby')
    targets=[n for n in order if running[n]['running'] and n not in stopped][:1]
    if not targets and measured['available_mb']<96:targets=[n for n in ('mediawarp','openlist') if running[n]['running'] and n not in stopped][:1]
    if targets:
     # Save ownership before Docker can time out after actually stopping a container.
     stopped=list(dict.fromkeys(stopped+targets));last_stop=now;plan.healthy_since=None;gate=PressureGate();last_action={'epoch':time.time(),'action':'stop_media','reason':reason,'containers':targets,'result':'requested'}
     last_action['measurements']=measured;plan.stopping(targets)
     checkpoint(boot_id,stopped,last_stop,recoveries,last_action,measured,plan)
     stop(targets)
     last_action['result']='completed'
     print('media-protection: stopped '+','.join(targets)+' for '+reason,flush=True)
   elif stopped:
    # A stop request can outlive its CLI timeout while Docker still reports
    # Running=true. Only our own start intent can acknowledge recovery.
    running=inspect()
    stopped=plan.reconcile(stopped,running)
    ready=[n for n in stopped if plan.phases.get(n)=='stopped']
    name=plan.next(ready,measured,now,last_stop)
    if name:
     plan.requested(name,now);last_action={'epoch':time.time(),'action':'restart_media_stage','containers':[name],'result':'requested'}
     checkpoint(boot_id,stopped,last_stop,recoveries,last_action,measured,plan)
     subprocess.run([DOCKER,'start',name],check=True,timeout=30,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
     if not inspect()[name]['running']:raise RuntimeError('Container did not become running')
     stopped.remove(name);plan.phases.pop(name,None);recoveries.append(now);last_path_check=0;previous=None
     last_action['result']='completed';print('media-protection: recovered '+name+' after stable routing headroom',flush=True)
   checkpoint(boot_id,stopped,last_stop,recoveries,last_action,measured,plan)
   last_error=None
  except Exception as e:
   if type(e).__name__!=last_error:print('media-protection: check error '+type(e).__name__,flush=True);last_error=type(e).__name__
  time.sleep(5)
