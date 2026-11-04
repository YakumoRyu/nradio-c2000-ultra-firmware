import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

R=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('media',R/'overlay/usr/lib/codex-media/media_protection.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class RetryTests(unittest.TestCase):
    def plan(self,**extra):
        return m.RecoveryPlan({'boot_id':'boot','stopped_by_guard':['emby'],'service_phases':{'emby':'stopping'},**extra},'boot',1000)
    def test_pending_stop_retry_is_bounded_and_persisted(self):
        p=self.plan();self.assertTrue(p.can_stop('emby',1000));p.stop_requested('emby',1000)
        self.assertFalse(p.can_stop('emby',1119));self.assertTrue(p.can_stop('emby',1120))
        p.stop_requested('emby',1120);p.stop_requested('emby',1240)
        self.assertFalse(p.can_stop('emby',1500));self.assertTrue(p.can_stop('emby',5000))
    def test_reload_keeps_stop_cooldown(self):
        p=self.plan(stop_attempts=[{'name':'emby','uptime':950}])
        self.assertFalse(p.can_stop('emby',1000));self.assertTrue(p.can_stop('emby',1070))
    def test_other_service_has_independent_budget(self):
        p=self.plan(stop_attempts=[{'name':'emby','uptime':999}]);self.assertTrue(p.can_stop('autofilm',1000))
    def test_file_reclaim_io_without_swapin_triggers_protection(self):
        sample={'available_mb':160,'iowait_percent':60,'swap_in_mb_per_second':0,'cpu_busy_percent':30,'media_cpu_percent':1}
        gate=m.PressureGate();self.assertIsNone(gate.observe(sample,100));self.assertEqual(gate.observe(sample,116),'swap_io_stall')
    def test_io_with_ample_memory_does_not_stop_media(self):
        sample={'available_mb':300,'iowait_percent':60,'swap_in_mb_per_second':0,'cpu_busy_percent':30,'media_cpu_percent':1}
        gate=m.PressureGate();self.assertIsNone(gate.observe(sample,100));self.assertIsNone(gate.observe(sample,200))
    def test_healthy_sample_clears_sustained_io_timer(self):
        sample={'available_mb':160,'iowait_percent':60,'swap_in_mb_per_second':0,'cpu_busy_percent':30,'media_cpu_percent':1}
        gate=m.PressureGate();gate.observe(sample,100);gate.observe(sample|{'iowait_percent':0},110)
        self.assertIsNone(gate.observe(sample,119))
    def test_running_services_stuck_in_stopping_are_retried_in_real_loop(self):
        old={'boot_id':'boot','stopped_by_guard':list(m.ALLOWED),'service_phases':{n:'stopping' for n in m.ALLOWED},'last_stop_uptime':100}
        now=[1000];requests=[]
        rows={n:{'id':'a'*64,'pid':0,'running':True,'source':'docker'} for n in m.ALLOWED}
        sample={'available_mb':60,'cpu_busy_percent':20,'iowait_percent':60,'swap_in_mb_per_second':0,'media_cpu_percent':1,'cpu_busy_per_core':{'cpu0':20},'softirq_per_core':{'cpu0':0},'max_core_busy_percent':20}
        def sleep(seconds):
            now[0]+=seconds
            if now[0]>1450:raise KeyboardInterrupt()
        def stop(names):requests.extend((n,now[0]) for n in names)
        real_open=open
        def opened(path,*args,**kw):return io.StringIO('boot') if path=='/proc/sys/kernel/random/boot_id' else real_open(path,*args,**kw)
        with patch.object(m,'load_state',return_value=old),patch.object(m,'inspect',return_value=rows),patch.object(m,'snapshot',return_value={}),patch.object(m,'interval',return_value=sample),patch.object(m,'checkpoint'),patch.object(m,'stop',side_effect=stop),patch.object(m,'time',SimpleNamespace(monotonic=lambda:now[0],time=lambda:now[0]+100000,sleep=sleep)),patch('builtins.open',opened):
            with self.assertRaises(KeyboardInterrupt):m.run()
        emby=[t for n,t in requests if n=='emby']
        self.assertEqual(len(emby),3)
        self.assertTrue(all(b-a>=120 for a,b in zip(emby,emby[1:])))

if __name__=='__main__':unittest.main()
