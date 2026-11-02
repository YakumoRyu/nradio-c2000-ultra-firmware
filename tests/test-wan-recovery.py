import importlib.machinery
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import urllib.parse

R=Path(__file__).resolve().parents[1]
loader=importlib.machinery.SourceFileLoader('wan_recovery',str(R/'overlay/usr/libexec/openclash-wan-recover'))
spec=importlib.util.spec_from_loader(loader.name,loader)
m=importlib.util.module_from_spec(spec);loader.exec_module(m)


class ProxyCoverageTests(unittest.TestCase):
    def setUp(self):
        self.proxies={m.MAIN_GROUP:{'now':'JP'},m.AI_GROUP:{'now':'US'},m.GAME_GROUP:{'now':'IPLC'},
                      'JP':{'type':'Mieru'},'US':{'type':'Mieru'},'IPLC':{'type':'Mieru'}}
        self.probed=[]
    def probe(self,failed=(),invalid=None):
        runtime=m.Runtime()
        def api(path):
            if path=='/proxies':return {'proxies':self.proxies}
            node=urllib.parse.unquote(path.split('/')[2]);self.probed.append(node)
            if node in failed:raise urllib.error.URLError('synthetic timeout')
            return {'delay':invalid if invalid is not None else 100}
        runtime.api=api
        return runtime.proxy()
    def test_ai_us_is_checked_when_main_japan_is_healthy(self):
        ok,data=self.probe(failed=('US',))
        self.assertFalse(ok);self.assertEqual(data['node'],'US');self.assertIn('JP',self.probed)
    def test_healthy_results_cover_both_selections(self):
        ok,data=self.probe();self.assertTrue(ok);self.assertEqual(data['nodes'],['JP','US'])
    def test_same_selected_node_is_not_probed_twice(self):
        self.proxies[m.AI_GROUP]['now']='JP'
        ok,data=self.probe();self.assertTrue(ok);self.assertEqual(self.probed,['JP'])
    def test_game_only_node_is_excluded(self):
        self.proxies[m.MAIN_GROUP]['now']='IPLC';self.proxies[m.AI_GROUP]['now']='IPLC'
        ok,data=self.probe();self.assertIsNone(ok);self.assertFalse(self.probed)
    def test_non_mieru_is_skipped(self):
        self.proxies['JP']['type']='Direct';self.proxies['US']['type']='Direct'
        ok,data=self.probe();self.assertIsNone(ok)
    def test_zero_and_boolean_delay_are_failures(self):
        for value in (0,False,True):
            ok,_=self.probe(invalid=value);self.assertFalse(ok)


class RecoveryGateTests(unittest.TestCase):
    def setUp(self):
        self.snap={'wan':[], 'event':'event', 'core':'123','ready':True,'enabled':True}
        self.state={'wan':[],'event':'event','core':'123','uptime':200,'pending_until':2000,'settle_until':250,
                    'last_probe':0,'failures':2,'proxy_probe':{'node':'US'},'attempted':False,'last_attempt':None}
        self.runtime=unittest.mock.Mock()
        self.runtime.direct.return_value=(True,{})
        self.runtime.proxy.return_value=(False,{'node':'US'})
        self.runtime.safe_resources.return_value=True
        self.runtime.snapshot.return_value=self.snap.copy()
    def test_third_failure_requests_one_restart(self):
        out=m.tick(self.state,self.snap,500,self.runtime)
        self.assertEqual(out['phase'],'restart_requested');self.runtime.restart.assert_called_once()
    def test_no_restart_without_recent_wan_event(self):
        out=m.tick(self.state|{'pending_until':400},self.snap,500,self.runtime)
        self.assertEqual(out['phase'],'idle');self.runtime.proxy.assert_not_called();self.runtime.restart.assert_not_called()
    def test_busy_resources_block_restart(self):
        self.runtime.safe_resources.return_value=False
        out=m.tick(self.state,self.snap,500,self.runtime)
        self.assertEqual(out['phase'],'resources_busy');self.runtime.restart.assert_not_called()
    def test_previous_attempt_is_not_repeated(self):
        out=m.tick(self.state|{'attempted':True},self.snap,500,self.runtime)
        self.assertEqual(out['phase'],'attempt_already_used');self.runtime.restart.assert_not_called()


if __name__=='__main__':unittest.main()
