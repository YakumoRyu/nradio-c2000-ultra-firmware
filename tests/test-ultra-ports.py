"""Protocol, transaction and real-UCI tests. Optional UCI_RUNNER is JSON argv."""
import copy
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[1]
FILES=REPO/'packages/ultra-port-manager/files'
def load(name,rel):
    loader=importlib.machinery.SourceFileLoader(name,str(FILES/rel))
    spec=importlib.util.spec_from_loader(name,loader);m=importlib.util.module_from_spec(spec);loader.exec_module(m);return m
m=load('ports','usr/libexec/ultra-ports')
p=load('probe','usr/libexec/ultra-port-probe')
NETWORK="""package network
config device 'bridge'
 option name 'br-lan'
 option type 'bridge'
 list ports 'eth1'
 list ports 'hnat'
 list ports 'eth0'
config interface 'lan'
 option device 'br-lan'
 option proto 'static'
 option ipaddr '192.168.66.1'
 option netmask '255.255.255.0'
config interface '2_1'
 option device 'eth2'
 option proto 'dhcp'
 option metric '11'
config interface '2_1v6'
 option device '@2_1'
 option proto 'dhcpv6'
 option metric '11'
"""
FIREWALL="""package firewall
config zone 'lan_zone'
 option name 'lan'
 list network 'lan'
config zone 'wan_zone'
 option name 'wan'
 option masq '1'
 list network '2_1'
 list network '2_1v6'
config rule 'keep_pcdn'
 option name 'Fixture preserved rule'
 option target 'ACCEPT'
"""
def baseline():return {'network':m.parse_export(NETWORK),'firewall':m.parse_export(FIREWALL)}


class Plans(unittest.TestCase):
    def test_old_idle_wan_never_used(self):
        cmd,mode=m.commands({'mode':'wan','proto':'dhcp'},baseline())
        self.assertEqual(mode,'wan');self.assertIn('set network.ultra_wan=interface',cmd)
        self.assertTrue(any('ultra_wan.device=eth0' in x for x in cmd))
        self.assertFalse(any('network.wan.' in x or 'network.2_1.' in x or 'eth2' in x for x in cmd))
    def test_lan_noop(self):self.assertEqual(m.commands({'mode':'lan'},baseline()),([], 'lan'))
    def test_rejects_vlan_and_unmanaged_port(self):
        c=baseline();c['network'].append({'id':'vlan','type':'bridge-vlan','options':{'device':'br-lan'}})
        with self.assertRaises(ValueError):m.commands({'mode':'wan'},c)
        c=baseline();c['network'][0]['options']['ports'].remove('eth0')
        with self.assertRaises(ValueError):m.commands({'mode':'wan'},c)
    def test_never_takes_over_existing_wan_or_second_port(self):
        c=baseline();c['network'].append({'id':'other','type':'interface','options':{'device':'eth0'}})
        with self.assertRaises(ValueError):m.commands({'mode':'wan'},c)
        c=baseline();c['network'][0]['options']['ports'].remove('eth1')
        with self.assertRaises(ValueError):m.commands({'mode':'wan'},c)
    def test_address_and_secret_validation(self):
        for f in ({'mode':'wan','proto':'static','ipaddr':'192.168.66.2','netmask':'255.255.255.0','gateway':'192.168.66.254'},
                  {'mode':'wan','proto':'static','ipaddr':'192.168.8.2','netmask':'255.255.255.0','gateway':'192.168.9.1'},
                  {'mode':'wan','proto':'pppoe','username':'u','password':'bad\nvalue'},
                  {'mode':'wan','proto':'dhcp','dns':[]}):
            with self.assertRaises(ValueError):m.commands(f,baseline())
    def test_protocol_selection_and_ipv6_scope(self):
        c,_=m.commands({'mode':'wan','proto':'pppoe','username':'fixture user','password':"quote'$(false)"},baseline())
        self.assertIn('set network.ultra_wan6.delegate=0',c)
        self.assertIn('set network.ultra_wan6.defaultroute=0',c)
        self.assertIn('set network.ultra_wan.metric=50',c)


class Discovery(unittest.TestCase):
    def setUp(self):self.mac=bytes.fromhex('020000000001');self.xid=12345;self.unique=b'fixture!'
    def test_dhcp_offer_match_and_wrong_transaction(self):
        sent,_=p.discover(self.mac,self.xid,self.unique)
        offer=bytearray(sent);offer[:6]=self.mac;offer[6:12]=bytes.fromhex('020000000002')
        offer[34:38]=struct.pack('!HH',67,68);b=42;offer[b]=2
        offer[b+240:b+256]=bytes([53,1,2,3,4,192,168,8,1,255,0,0,0,0,0,0])
        self.assertEqual(p.parse(bytes(offer),self.mac,self.xid,self.unique),{'kind':'dhcp','gateway':'192.168.8.1'})
        self.assertIsNone(p.parse(bytes(offer),self.mac,self.xid+1,self.unique))
        self.assertIsNone(p.parse(bytes(offer[:260]),self.mac,self.xid,self.unique))
    def test_pppoe_service_identity_and_malformed_tags(self):
        _,raw=p.discover(self.mac,self.xid,self.unique);f=bytearray(raw)
        f[:6]=self.mac;f[6:12]=bytes.fromhex('020000000002');f[15]=7
        self.assertEqual(p.parse(bytes(f),self.mac,self.xid,self.unique)['kind'],'pppoe')
        self.assertIsNone(p.parse(bytes(f),self.mac,self.xid,b'wrong!!!'))
        self.assertIsNone(p.parse(bytes(f[:20]),self.mac,self.xid,self.unique))


@unittest.skipUnless(os.environ.get('UCI_RUNNER'),'real UCI runner not supplied')
class Transactions(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.cfg=self.root/'config';self.cfg.mkdir()
        (self.cfg/'.delta').mkdir()
        (self.cfg/'network').write_text(NETWORK);(self.cfg/'firewall').write_text(FIREWALL)
        runner=json.loads(os.environ['UCI_RUNNER']);realrun=m.run
        def run(args,data=None,timeout=15):
            if args[0]=='uci':
                tail=args[1:]
                if '-c' not in tail:tail=['-c',str(self.cfg),'-t',str(self.cfg/'.delta')]+tail
                args=runner+tail
            return realrun(args,data,timeout)
        self.patches=[patch.object(m,'CONFIG',self.cfg),patch.object(m,'STATE',self.root/'state'),patch.object(m,'RUNTIME',self.root/'runtime'),patch.object(m,'supported',return_value=True),patch.object(m,'run',side_effect=run),patch.object(m,'reconfigure'),patch.object(m.subprocess,'Popen')]
        # Do not mock Popen globally: subprocess.run also uses it. Only the guard
        # launcher is intercepted using the module-level helper patched below.
        self.patches.pop()
        for x in self.patches:x.start()
        self.spawn=patch.object(m,'start_guard',return_value=None);self.spawn.start()
    def tearDown(self):
        self.spawn.stop()
        for x in reversed(self.patches):x.stop()
        self.tmp.cleanup()
    def test_round_trip_confirmation_preserves_cellular_and_rules(self):
        old=m.config();result=m.apply({'mode':'wan','proto':'dhcp'});s=m.load_state()
        self.assertTrue(result['changed']);after=m.config()
        for name in ('2_1','2_1v6','lan'):
            self.assertEqual(m.section(old['network'],name),m.section(after['network'],name))
        self.assertEqual(m.section(old['firewall'],'keep_pcdn'),m.section(after['firewall'],'keep_pcdn'))
        self.assertEqual(m.topology(after)[4],'wan');s['phase']='awaiting_confirmation';m.save(m.STATE/'pending.json',s)
        m.finish({'id':s['id']});self.assertIsNone(m.load_state())
        m.apply({'mode':'lan'});s=m.load_state();s['phase']='awaiting_confirmation';m.save(m.STATE/'pending.json',s)
        m.finish({'id':s['id']});c=m.config()
        self.assertIn('eth0',m.topology(c)[2]);self.assertNotIn('device',m.section(c['network'],m.WAN)['options'])
    def test_anonymous_sections_used_by_production(self):
        (self.cfg/'network').write_text(NETWORK.replace("config device 'bridge'",'config device'))
        (self.cfg/'firewall').write_text(FIREWALL.replace("config zone 'wan_zone'",'config zone'))
        m.apply({'mode':'wan','proto':'dhcp'})
        self.assertEqual(m.topology(m.config())[4],'wan')
    def test_checked_rollback_and_new_edit_conflict(self):
        before={p:(self.cfg/p).read_bytes() for p in m.PACKAGES}
        m.apply({'mode':'wan','proto':'pppoe','username':'fixture','password':"test'$(false)"})
        self.assertTrue(m.restore(m.load_state()))
        self.assertEqual(before,{p:(self.cfg/p).read_bytes() for p in m.PACKAGES})
        m.apply({'mode':'wan','proto':'dhcp'});s=m.load_state()
        (self.cfg/'network').write_text((self.cfg/'network').read_text()+'\n# later manual edit\n')
        self.assertFalse(m.restore(s));self.assertEqual(m.load_state()['phase'],'rollback_conflict')
    def test_timeout_and_power_cycle_recovery(self):
        before=(self.cfg/'network').read_bytes();m.apply({'mode':'wan','proto':'dhcp'});s=m.load_state()
        s['deadline']=0;m.save(m.STATE/'pending.json',s);m.recover()
        self.assertEqual((self.cfg/'network').read_bytes(),before)
        m.apply({'mode':'wan','proto':'dhcp'});s=m.load_state();s['boot']='different-boot';m.save(m.STATE/'pending.json',s);m.recover()
        self.assertEqual((self.cfg/'network').read_bytes(),before)
    def test_commit_failure_has_no_live_mutation(self):
        before={p:(self.cfg/p).read_bytes() for p in m.PACKAGES}
        with patch.object(m,'run',side_effect=ValueError('fixture UCI failure')):
            with self.assertRaises(ValueError):m.apply({'mode':'wan','proto':'dhcp'})
        self.assertEqual(before,{p:(self.cfg/p).read_bytes() for p in m.PACKAGES});self.assertIsNone(m.load_state())

if __name__=='__main__':unittest.main(verbosity=2)
