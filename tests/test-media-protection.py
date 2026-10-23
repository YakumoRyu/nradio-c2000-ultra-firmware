"""Guard recovery under real forwarding load, partial Docker calls and pressure."""
import importlib.util,io,json,subprocess,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
S=Path(__file__).resolve().parents[1]/'overlay/usr/lib/codex-media/media_protection.py'
spec=importlib.util.spec_from_file_location('media_guard',S)
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
def measured(available=280,cpu=68):
 return {'available_mb':available,'cpu_busy_percent':cpu,'iowait_percent':0,'swap_in_mb_per_second':0,'media_cpu_percent':0,'cpu_busy_per_core':{'cpu0':cpu},'softirq_per_core':{'cpu0':35},'max_core_busy_percent':cpu}

class PlanTests(unittest.TestCase):
 def test_docker_timeout_falls_back_to_live_cgroups(self):
  class Broken:
   def request(self,*args):raise TimeoutError()
   def close(self):pass
  rows={n:{'id':'a'*64,'running':n=='emby','pid':42 if n=='emby' else 0} for n in g.ALLOWED}
  with patch.object(g,'DockerHTTP',Broken),patch.object(g,'process_inspect',return_value=rows):self.assertEqual(g.inspect(),rows)
 def test_process_fallback_requires_a_valid_docker_cgroup(self):
  with tempfile.TemporaryDirectory() as d:
   base=Path(d);proc=base/'proc';cg=base/'cg';proc.mkdir()
   for pid,rel in [('42','/docker/'+'a'*64),('43','/services/other')]:
    p=proc/pid;p.mkdir();(p/'cmdline').write_bytes(b'/system/EmbyServer\0');(p/'cgroup').write_text('0::'+rel+'\n')
   p=cg/'docker'/('a'*64);p.mkdir(parents=True);(p/'cgroup.procs').write_text('42\n')
   self.assertEqual(g.process_inspect(proc,cg)['emby']['pid'],42)
   (proc/'42/cgroup').write_text('0::/docker/../../services/other\n')
   self.assertFalse(g.process_inspect(proc,cg)['emby']['running'])
 def test_forwarding_load_allows_one_recovery_stage(self):
  p=g.RecoveryPlan({},'boot',1000)
  self.assertIsNone(p.next(['emby','openlist'],measured(),1000,100))
  self.assertEqual(p.next(['emby','openlist'],measured(),1120,100),'openlist')
  p.requested('openlist',1120)
  self.assertIsNone(p.next(['emby'],measured(),1125,100))
  self.assertEqual(p.next(['emby'],measured(),1245,100),'emby')
 def test_pressure_resets_stability_and_cooldown(self):
  p=g.RecoveryPlan({},'boot',1000)
  p.next(['emby'],measured(),1000,900)
  self.assertIsNone(p.next(['emby'],measured(),1120,900))
  self.assertIsNone(p.next(['emby'],measured(100),1200,900))
  self.assertIsNone(p.next(['emby'],measured(),1500,900))
  self.assertEqual(p.next(['emby'],measured(),1620,900),'emby')
 def test_per_service_hourly_budget_survives_restart(self):
  old={'boot_id':'boot','recovery_attempts':[{'name':'emby','uptime':1000}]}
  p=g.RecoveryPlan(old,'boot',1500)
  p.next(['emby'],measured(),1500,100)
  self.assertIsNone(p.next(['emby'],measured(),1620,100))
  self.assertEqual(p.next(['emby'],measured(),4600,100),'emby')
 def test_missing_peak_and_hotspot_block_resume(self):
  s=measured();s['max_core_busy_percent']=None
  self.assertFalse(g.safe_to_resume(s))
  s=measured();s['network_softirq_hotspot']=True
  self.assertFalse(g.safe_to_resume(s))
  self.assertFalse(g.safe_to_resume(measured(280,90)))
 def test_low_memory_and_cpu_stop_protection_remain(self):
  p=g.PressureGate();s=measured(120)
  self.assertIsNone(p.observe(s,100));self.assertEqual(p.observe(s,115),'low_memory')
  p=g.PressureGate();s=measured(280,96);s['media_cpu_percent']=12
  self.assertIsNone(p.observe(s,0));self.assertEqual(p.observe(s,20),'cpu_saturation')
  self.assertEqual(g.PressureGate().observe(measured(60),0),'critical_memory')

class LoopTests(unittest.TestCase):
 def run_loop(self,old=None,available=280,fail_stop=False,fail_start=False):
  with tempfile.TemporaryDirectory() as d:
   status=Path(d)/'state.json';now=[1000];end=1500;started=[]
   running={n:True for n in g.ALLOWED}
   if old:
    status.write_text(json.dumps(old))
    for n in old['stopped_by_guard']:running[n]=False
   def inspect():return {n:{'running':v,'pid':0,'id':'a'*64} for n,v in running.items()}
   def sleep(seconds):
    now[0]+=seconds
    if now[0]>=end:raise KeyboardInterrupt()
   def stop(names):
    nonlocal available
    for n in names:running[n]=False
    available=280
    if fail_stop:raise subprocess.TimeoutExpired(['docker','stop'],30)
   def start(argv,**kw):
    started.append(argv[-1]);running[argv[-1]]=True
    if fail_start:raise subprocess.TimeoutExpired(argv,30)
   real_open=open
   def opened(path,*a,**kw):return io.StringIO('boot') if path=='/proc/sys/kernel/random/boot_id' else real_open(path,*a,**kw)
   with patch.object(g,'STATUS',str(status)),patch.object(g,'PERSIST',str(Path(d)/'persistent.json')),patch.object(g,'time',SimpleNamespace(time=lambda:now[0]+100000,monotonic=lambda:now[0],sleep=sleep)),patch('builtins.open',opened),patch.object(g,'inspect',inspect),patch.object(g,'snapshot',lambda paths:{}),patch.object(g,'interval',lambda a,b:measured(available)),patch.object(g,'stop',stop),patch.object(g.subprocess,'run',start):
    with self.assertRaises(KeyboardInterrupt):g.run()
   return json.loads(status.read_text()),started,running
 def test_docker_stop_timeout_keeps_ownership(self):
  s,_,_=self.run_loop(available=60,fail_stop=True)
  self.assertEqual(s['stopped_by_guard'],['emby'])
  self.assertEqual(s['last_action']['result'],'requested')
 def test_start_timeout_after_success_reconciles_without_retry(self):
  old={'boot_id':'boot','stopped_by_guard':['emby'],'last_stop_uptime':100}
  s,started,running=self.run_loop(old,fail_start=True)
  self.assertEqual(started,['emby']);self.assertTrue(running['emby'])
  self.assertEqual(s['stopped_by_guard'],[])
  self.assertEqual(len(s['recovery_attempts']),1)
 def test_never_resumes_manually_stopped_containers(self):
  old={'boot_id':'boot','stopped_by_guard':['emby'],'last_stop_uptime':100}
  s,started,_=self.run_loop(old)
  self.assertEqual(started,['emby']);self.assertEqual(s['stopped_by_guard'],[])
 def test_persistent_ownership_survives_reboot_without_periodic_TF_writes(self):
  with tempfile.TemporaryDirectory() as d,patch.object(g,'STATUS',str(Path(d)/'tmp.json')),patch.object(g,'PERSIST',str(Path(d)/'persistent.json')):
   state={'boot_id':'old','stopped_by_guard':['emby'],'last_stop_uptime':100,'recovery_uptimes':[],'recovery_attempts':[],'last_action':{'action':'stop_media'}}
   g.persist_state(state);before=Path(g.PERSIST).stat().st_mtime_ns
   g.persist_state(state|{'measurements':{'available_mb':250}})
   self.assertEqual(Path(g.PERSIST).stat().st_mtime_ns,before)
   restored=g.load_state();stopped,last,_,_=g.restore_guard_state(restored,'new',20)
   self.assertEqual(stopped,['emby']);self.assertEqual(last,20)
 def test_full_TF_does_not_prevent_routing_protection_checkpoint(self):
  with tempfile.TemporaryDirectory() as d,patch.object(g,'STATUS',str(Path(d)/'tmp.json')),patch.object(g,'persist_state',side_effect=OSError('disk full')):
   p=g.RecoveryPlan({},'boot',1000)
   g.checkpoint('boot',['emby'],1000,[],{'action':'stop_media'},measured(60),p)
   self.assertEqual(json.loads(Path(g.STATUS).read_text())['stopped_by_guard'],['emby'])

class HealthTests(unittest.TestCase):
 def test_autofilm_suspension_does_not_block_cloud_driver_recovery(self):
  s=importlib.util.spec_from_file_location('media_health',S.with_name('media-health.py'));h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
  for stopped,expected in [(['autofilm'],True),(['openlist'],False)]:
   state={'epoch':1000,'measurements':measured(),'stopped_by_guard':stopped}
   with patch('builtins.open',return_value=io.StringIO(json.dumps(state))),patch.object(h.time,'time',return_value=1001):self.assertEqual(h.recovery_headroom(),expected)

if __name__=='__main__':unittest.main(verbosity=2)
