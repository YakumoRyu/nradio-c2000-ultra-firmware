#!/usr/bin/python3
"""Recover OpenList cloud drivers after a boot-time network initialization failure."""
import json,os,subprocess,sys,time,urllib.error,urllib.request,threading

AUTH_SOURCE='/overlay/media-stack/state/root/autofilm-v2/config/config.yaml'
STATUS='/tmp/codex-media-health.json'
DOCKER='/usr/bin/docker'
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
token=None

def request(path,body=None,authenticated=False):
 headers={'Content-Type':'application/json'}
 if authenticated:headers['Authorization']=token or ''
 req=urllib.request.Request('http://127.0.0.1:5244'+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
 with opener.open(req,timeout=7) as response:return json.load(response)

def login():
 global token
 code='x=YAML.load_file(ARGV[0]); a=x.fetch("alist").first; STDOUT.write(a.fetch("username")); STDOUT.write("\\0"); STDOUT.write(a.fetch("password"))'
 raw=subprocess.check_output(['/usr/bin/ruby','-ryaml','-e',code,AUTH_SOURCE],timeout=8,stderr=subprocess.DEVNULL)
 username,password=raw.split(b'\0',1)
 result=request('/api/auth/login',{'username':username.decode(),'password':password.decode()})
 if result.get('code')!=200:raise RuntimeError('local_auth_failed')
 token=result['data']['token']

def inspect_storages():
 if not token:login()
 result=request('/api/admin/storage/list?page=1&per_page=100',authenticated=True)
 if result.get('code') in (401,403):login();result=request('/api/admin/storage/list?page=1&per_page=100',authenticated=True)
 if result.get('code')!=200:raise RuntimeError('storage_status_unavailable')
 rows=(result.get('data') or {}).get('content') or []
 return [{'id':s['id'],'mount':s['mount_path'],'status':s.get('status') or '', 'disabled':bool(s.get('disabled'))} for s in rows if s.get('driver')=='139Yun']

def need_recovery(rows):
 bad=[r for r in rows if not r['disabled'] and r['status']!='work']
 # Only startup/uninitialized or transport failures. Authentication/data errors need manual diagnosis.
 markers=('timeout','timed out','connection','network','no such host','protocol scheme','cloudhost is empty','dial tcp','unexpected eof')
 return [r for r in bad if not r['status'] or any(x in r['status'].lower() for x in markers)]

def network_ready():
 # 139Yun initializes cloudHost through qryRoutePolicy on this host.
 # The obsolete aas landing page returns HTTP 999 even when the current API works.
 for host in ('user-njs.yun.139.com',):
  try:
   req=urllib.request.Request('https://'+host+'/',method='HEAD')
   with opener.open(req,timeout=6) as response:
    if response.status>=500:return False
  except urllib.error.HTTPError as e:
   if e.code>=500:return False
  except (urllib.error.URLError,TimeoutError,OSError):return False
 return True

def write_status(state,rows=None,**extra):
 data={'epoch':time.time(),'state':state,**extra}
 if rows is not None:data['storages']=[{**r,'status':r['status'] if r['status'] in ('','work') else 'driver_error'} for r in rows]
 temp=STATUS+'.tmp'
 with open(temp,'w') as f:json.dump(data,f)
 os.replace(temp,STATUS)


def recovery_history(old,boot_id,now):
 if not isinstance(old,dict):return -10000,[]
 if old.get('boot_id')==boot_id:
  recent=[x for x in old.get('restart_uptimes',[]) if isinstance(x,(int,float)) and 0<=now-x<3600]
  last=old.get('last_restart_uptime',-10000)
  if not isinstance(last,(int,float)) or last>now:last=now
  return last,recent
 # Preserve a legacy guard's known count conservatively during an online update.
 count=old.get('restarts_last_hour',0)
 if old.get('boot_id') is None and isinstance(count,int) and count>0:
  return now,[now]*min(3,count)
 return -10000,[]

def recovery_headroom():
 try:
  state=json.load(open('/tmp/codex-media-protection.json'))
  if not 0<=time.time()-state['epoch']<45:return False
  m=state['measurements'];peak=m.get('max_core_busy_percent')
  return not state['stopped_by_guard'] and m['available_mb']>=128 and m['cpu_busy_percent']<85 and m['iowait_percent']<20 and peak is not None and peak<95 and not m.get('network_softirq_hotspot',False)
 except (OSError,ValueError,KeyError,TypeError):return False

def main(once=False):
 global token
 bad_checks=0;previous=None
 boot_id=open('/proc/sys/kernel/random/boot_id').read().strip()
 try:old=json.load(open(STATUS))
 except (OSError,ValueError,TypeError):old={}
 last_restart,recent=recovery_history(old,boot_id,time.monotonic())
 while True:
  now=time.monotonic();recent=[n for n in recent if now-n<3600]
  try:
   rows=inspect_storages();bad=need_recovery(rows)
   healthy=bool(rows) and all(r['disabled'] or r['status']=='work' for r in rows)
   if healthy:
    state='healthy';bad_checks=0;delay=300
   elif bad:
    bad_checks+=1;state='waiting_for_network';delay=30
    if not once and bad_checks>=2 and now-last_restart>=600 and len(recent)<3 and recovery_headroom() and network_ready():
     subprocess.run([DOCKER,'restart','--time','10','openlist'],check=True,timeout=30,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
     token=None;last_restart=now;recent.append(now);bad_checks=0;state='reinitialized_openlist';delay=30
   else:
    state='driver_requires_attention';bad_checks=0;delay=300
   write_status(state,rows,restarts_last_hour=len(recent),boot_id=boot_id,last_restart_uptime=last_restart,restart_uptimes=recent)
  except (Exception,) as e:
   state='waiting_for_openlist';delay=30;write_status(state,error_type=type(e).__name__,restarts_last_hour=len(recent),boot_id=boot_id,last_restart_uptime=last_restart,restart_uptimes=recent)
  if state!=previous:
   print('media-health: '+state,flush=True);previous=state
  if once:return
  time.sleep(delay)

if __name__=='__main__':
 if '--once' not in sys.argv:
  from media_protection import run
  threading.Thread(target=run,daemon=True,name='routing-resource-protection').start()
 main('--once' in sys.argv)
