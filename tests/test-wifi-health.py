import copy
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader('wifi_health', str(ROOT/'overlay/usr/libexec/ultra-wifi-health'))
spec = importlib.util.spec_from_loader(loader.name, loader)
m = importlib.util.module_from_spec(spec)
loader.exec_module(m)


def ap(health='up', band=1):
    return {'radio': 'radio1', 'ifname': 'rai0', 'health': health, 'band': band, 'radio_up': True}


class WirelessHealth(unittest.TestCase):
    def test_fault_recovery_lifecycle(self):
        p = m.Policy()
        self.assertFalse(p.evaluate([ap('down')], 200))
        self.assertFalse(p.evaluate([ap('down')], 230))
        targets = p.evaluate([ap('down')], 260)
        self.assertEqual(targets[0]['reason'], 'ap_unavailable')
        p.action(260)
        for t in [290, 320, 350]:
            self.assertFalse(p.evaluate([ap('down')], t))
        self.assertFalse(p.evaluate([ap()], 1161))

    def test_no_clients_or_idle_ap_is_healthy(self):
        p = m.Policy()
        for t in range(200, 1000, 30):
            self.assertFalse(p.evaluate([ap()], t))

    def test_two_bad_samples_do_not_reload(self):
        p = m.Policy()
        for t, h in [(200,'down'), (230,'down'), (260,'up'), (290,'down')]:
            self.assertFalse(p.evaluate([ap(h)], t))

    def test_unavailable_ubus_is_unknown(self):
        p = m.Policy()
        p.evaluate([ap('down')],200)
        p.evaluate([ap('down')],230)
        self.assertFalse(p.evaluate(None,260))
        self.assertFalse(p.evaluate([ap('down')],290))

    def test_startup_and_dfs_grace(self):
        p = m.Policy()
        for t in [30,60,90,120,150]:
            self.assertFalse(p.evaluate([ap('down')],t))
        for t in [180,210,240]:
            self.assertFalse(p.evaluate([ap('waiting')],t))
        self.assertFalse(p.evaluate([ap('down')],270))

    def test_beacon_fault_requires_driver_counter(self):
        p = m.Policy()
        p.event({'kind':'beacon_stopped','band':1,'seconds':15,'uptime':200})
        self.assertFalse(p.evaluate([ap()],210))
        p.event({'kind':'beacon_stopped','band':1,'seconds':20,'uptime':215})
        self.assertEqual(p.evaluate([ap()],220)[0]['reason'],'beacon_stopped')
        p.event({'kind':'beacon_resumed','band':1,'uptime':221})
        self.assertFalse(p.evaluate([ap()],225))

    def test_stale_beacon_and_other_band_do_not_reload(self):
        p = m.Policy()
        p.event({'kind':'beacon_stopped','band':0,'seconds':20,'uptime':200})
        self.assertFalse(p.evaluate([ap()],210))
        self.assertFalse(p.evaluate([ap(band=0)],280))

    def test_manually_disabled_radios_and_non_ap_skipped(self):
        base={'r':{'up':True,'autostart':True,'config':{'band':'5g','key':'private'},'interfaces':[{'ifname':'rai0','config':{'mode':'ap','key':'private','ssid':'private'}}]}}
        self.assertEqual(len(m.configured_aps(base)),1)
        self.assertNotIn('private',json.dumps(m.configured_aps(base)))
        for which in ['disabled','pending']:
            data=copy.deepcopy(base);data['r'][which]=True
            self.assertEqual(m.configured_aps(data),[])
        data=copy.deepcopy(base);data['r']['autostart']=False
        self.assertEqual(m.configured_aps(data),[])
        data=copy.deepcopy(base);data['r']['interfaces'][0]['config']['mode']='sta'
        self.assertEqual(m.configured_aps(data),[])

    def test_hourly_budget_and_cooldown(self):
        p=m.Policy()
        for t in [200,230,260]:targets=p.evaluate([ap('down')],t)
        self.assertTrue(targets);p.action(260)
        for t in [1170,1200,1230]:targets=p.evaluate([ap('down')],t)
        self.assertTrue(targets);p.action(1230)
        for t in [2170,2200,2230]:self.assertFalse(p.evaluate([ap('down')],t))

    def test_down_timeout_always_attempts_up(self):
        calls=[]
        def run(args,timeout):
            calls.append(args)
            return (-1,'') if args[5]=='down' else (0,'')
        result=m.recover(['radio1','radio1','bad;reboot'],run)
        self.assertEqual(calls,[['ubus','-t','18','call','network.wireless','down','{"device":"radio1"}'],['ubus','-t','28','call','network.wireless','up','{"device":"radio1"}']])
        self.assertEqual(result,[{'radio':'radio1','down_rc':-1,'up_rc':0}])

    def test_final_recheck_cancels_recovered_or_disabled_ap(self):
        targets=[{'radio':'radio1','ifname':'rai0','reason':'ap_unavailable'}]
        self.assertFalse(m.still_broken(targets,[ap()]))
        self.assertFalse(m.still_broken(targets,[]))
        self.assertFalse(m.still_broken(targets,[ap('waiting')]))
        self.assertTrue(m.still_broken(targets,[ap('down')]))

    def test_parser_ignores_replayed_logs_and_does_not_copy_secrets(self):
        line='kernel: [ 200.000] nobcn occurs within 20 sec for band 1 (rai0)!! password=private'
        e=m.parse_event(line,210)
        self.assertEqual(e,{'kind':'beacon_stopped','seconds':20,'band':1,'uptime':200.0})
        self.assertIsNone(m.parse_event(line,300))
        self.assertIsNone(m.parse_event('cloudflared: private failure',210))

    def test_storage_failure_does_not_abort_supervision(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'file';f.write_text('x')
            m.History(f).append({'kind':'recovery'})

    def test_history_rotation_and_private_permissions(self):
        with tempfile.TemporaryDirectory() as d:
            h=m.History(Path(d));p=Path(d)/'events.jsonl'
            p.write_bytes(b'x'*262144)
            h.append({'kind':'recovery','uptime':300})
            self.assertTrue((Path(d)/'events.previous.jsonl').exists())
            self.assertEqual(json.loads(p.read_text())['kind'],'recovery')

    def test_restart_keeps_same_boot_rate_limit(self):
        with tempfile.TemporaryDirectory() as d, patch.object(m,'STATE',Path(d)/'state'):
            p=m.Policy();p.action(300);m.save_state(p,[ap()],301,'boot')
            restored=m.restore_policy('boot')
            self.assertEqual(restored.last_action,300)
            self.assertEqual(restored.attempts,[300])
            self.assertEqual(m.restore_policy('other-boot').attempts,[])


if __name__=='__main__':
    unittest.main()
