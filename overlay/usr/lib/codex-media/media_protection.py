"""Give routing priority when media services cause sustained memory or I/O pressure."""
import json,os,subprocess,time
DOCKER='/usr/bin/docker'
STATUS='/tmp/codex-media-protection.json'
ALLOWED=('autofilm','emby','mediawarp','openlist')

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

def inspect():
 rows=json.loads(subprocess.check_output([DOCKER,'inspect',*ALLOWED],timeout=7,stderr=subprocess.DEVNULL))
 return {x['Name'].lstrip('/'):{'id':x['Id'],'running':x['State']['Running'],'pid':x['State']['Pid']} for x in rows}

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
   value=str(256*1048576)
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

def safe_to_resume(measured):
 peak=measured.get('max_core_busy_percent')
 return measured['available_mb']>=384 and measured['cpu_busy_percent']<50 and measured['iowait_percent']<10 and peak is not None and peak<85

def restore_guard_state(old,boot_id,now):
 if not isinstance(old,dict):return [],0,[],None
 stopped=[n for n in old.get('stopped_by_guard',[]) if n in ALLOWED]
 last_stop=now if stopped else 0;recoveries=[]
 if old.get('boot_id')==boot_id:
  value=old.get('last_stop_uptime')
  if isinstance(value,(int,float)) and 0<=value<=now:last_stop=value
  recoveries=[v for v in old.get('recovery_uptimes',[]) if isinstance(v,(int,float)) and 0<=now-v<3600]
 return stopped,last_stop,recoveries,old.get('last_action')


def write(data):
 with open(STATUS+'.tmp','w') as f:json.dump(data,f)
 os.replace(STATUS+'.tmp',STATUS)

def stop(names):
 assert names and all(n in ALLOWED for n in names)
 subprocess.run([DOCKER,'stop','--time','8',*names],timeout=30,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

def run():
 gate=PressureGate();core_pressure=CorePressure();healthy_since=None;hotspot_reported=False
 boot_id=open('/proc/sys/kernel/random/boot_id').read().strip()
 try:old=json.load(open(STATUS))
 except (OSError,ValueError,TypeError):old={}
 stopped,last_stop,recoveries,last_action=restore_guard_state(old,boot_id,time.monotonic())
 paths=[];high_paths=[];previous=None;last_path_check=0;last_error=None
 while True:
  try:
   now=time.monotonic()
   if now-last_path_check>=60 or not paths:
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
    targets=[n for n in ('autofilm','emby') if running[n]['running']]
    if not targets and measured['available_mb']<96:targets=[n for n in ('mediawarp','openlist') if running[n]['running']]
    if targets:
     stop(targets);stopped=list(dict.fromkeys(stopped+targets));last_stop=now;healthy_since=None;gate=PressureGate();last_action={'epoch':time.time(),'action':'stop_media','reason':reason,'containers':targets}
     print('media-protection: stopped '+','.join(targets)+' for '+reason,flush=True)
   elif stopped:
    sufficiently_free=safe_to_resume(measured)
    healthy_since=(healthy_since if healthy_since is not None else now) if sufficiently_free else None
    # At most one automatic restart per hour, only after 5 stable minutes and 10 minutes cooldown.
    if healthy_since is not None and now-healthy_since>=300 and now-last_stop>=600 and not recoveries:
     targets=[n for n in ('openlist','mediawarp','emby','autofilm') if n in stopped]
     for name in targets:
      subprocess.run([DOCKER,'start',name],check=True,timeout=15,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
     stopped=[];recoveries.append(now);healthy_since=None;last_action={'epoch':time.time(),'action':'restart_media_after_cooldown','containers':targets};print('media-protection: cautious recovery after stable routing headroom',flush=True)
   write({'epoch':time.time(),'boot_id':boot_id,'last_stop_uptime':last_stop,'recovery_uptimes':recoveries,'state':'media_suspended_for_routing' if stopped else 'protecting','measurements':measured,'stopped_by_guard':stopped,'last_action':last_action,'automatic_recoveries_last_hour':len(recoveries),'thresholds':{'critical_available_mb':64,'sustained_available_mb':128,'memory_duration_seconds':15,'sustained_iowait_percent':30,'swap_in_mb_per_second':2,'cpu_busy_percent':90,'cpu_duration_seconds':20}})
   last_error=None
  except Exception as e:
   if type(e).__name__!=last_error:print('media-protection: check error '+type(e).__name__,flush=True);last_error=type(e).__name__
  time.sleep(5)
