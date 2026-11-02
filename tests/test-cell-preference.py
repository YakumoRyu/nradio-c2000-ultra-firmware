#!/usr/bin/env python3
import importlib.machinery
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import tempfile
import contextlib
import io
import sys

path=Path(__file__).resolve().parents[1]/'overlay/usr/libexec/cell-preference'
loader=importlib.machinery.SourceFileLoader('cell_preference',str(path))
spec=importlib.util.spec_from_loader(loader.name,loader)
m=importlib.util.module_from_spec(spec);loader.exec_module(m)

class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.cfg=m.checked_config({})
        self.current={'arfcn':635000,'scs':1,'pci':100,'rsrp':-80,'rsrq':-10,'sinr':20}
        self.good=self.current|{'pci':397,'rsrp':-70,'sinr':21}
    def decide(self,rows,state=None,now=10000):return m.decide(self.current,rows,state or {},self.cfg,now)
    def test_current_is_better(self):
        s,target=self.decide([self.good|{'rsrp':-90}]);self.assertIsNone(target);self.assertEqual(s['phase'],'current_best_observed')
    def test_preferred_frequency_is_explicit(self):
        self.cfg['preferred_arfcn']=635000
        state,target=self.decide([]);self.assertEqual(state['phase'],'preferred_frequency_active');self.assertIsNone(target)
    def test_preferred_frequency_unavailable_does_not_reset_radio(self):
        self.cfg['preferred_arfcn']=632000
        state,target=self.decide([]);self.assertEqual(state['phase'],'preferred_frequency_unavailable');self.assertIsNone(target)
    def test_three_consecutive_measurements(self):
        state={}
        for now in (10000,10060):state,target=self.decide([self.good],state,now);self.assertIsNone(target)
        state,target=self.decide([self.good],state,10120);self.assertEqual(target,self.good)
    def test_small_gain_does_not_switch(self):self.assertIsNone(self.decide([self.good|{'rsrp':-75}])[1])
    def test_fast_status_checks_are_not_independent_samples(self):
        state,_=self.decide([self.good]);state,_=self.decide([self.good],state,10001);state,target=self.decide([self.good],state,10002)
        self.assertEqual(state['count'],1);self.assertIsNone(target)
    def test_bad_sinr_does_not_switch(self):self.assertIsNone(self.decide([self.good|{'sinr':-1}])[1])
    def test_quality_regression_does_not_switch(self):self.assertIsNone(self.decide([self.good|{'sinr':10}])[1])
    def test_bad_rsrq_does_not_switch(self):self.assertIsNone(self.decide([self.good|{'rsrq':-20}])[1])
    def test_confirmation_resets_after_gap(self):
        state,_=self.decide([self.good]);state,_=self.decide([self.good],state,10200);self.assertEqual(state['count'],1)
    def test_confirmation_resets_after_cell_change(self):
        state,_=self.decide([self.good]);self.current['pci']=101;state,_=self.decide([self.good],state,10060);self.assertEqual(state['count'],1)
    def test_cooldown_blocks_retry(self):
        state={'last_attempt':9500,'candidate':m.key(self.good),'count':3,'observed':9999};self.assertEqual(self.decide([self.good],state)[0]['phase'],'cooldown')
    def test_clock_reversal_blocks_retry(self):self.assertEqual(self.decide([self.good],{'last_attempt':11000})[0]['phase'],'cooldown')
    def test_parser_uses_hex_pci(self):
        row=m.serving('^MONSC: NR,460,01,635000,1,100000001,64,100001,-71,-10,23\nOK');self.assertEqual(row['pci'],100)
    def test_filter_sentinel_and_other_frequency(self):
        raw='^MONNC: NR,635000,18D,-60,-9,24\n^MONNC: NR,635000,171,-157,-44,-24\n^MONNC: NR,632000,64,-50,-8,30\n'
        rows=m.neighbors(raw,self.current);self.assertEqual(len(rows),1);self.assertEqual(rows[0]['pci'],397)
    def test_lock_roundtrip_retains_mobility(self):self.assertEqual(m.lock_command('^NRFREQLOCK: 1\n1,1\n78,632000,1\nOK'),'AT^NRFREQLOCK=1,1,1,"78","632000","1"')
    def test_reject_incomplete_lock(self):
        with self.assertRaises(ValueError):m.lock_command('^NRFREQLOCK: 2\n0,2\n78,632000,1,100\nOK')
    def test_unlocked_mode_is_reported_as_automatic(self):self.assertEqual(m.lock_command('^NRFREQLOCK: 0\nOK'),'AT^NRFREQLOCK=0')
    def test_reject_injected_configuration(self):
        with self.assertRaises(ValueError):m.checked_config({'at_port':'/dev/ttyUSB1;reboot'})
    def test_failed_selection_restores_original_without_radio_reset(self):
        calls=[]
        baseline='AT^NRFREQLOCK=1,1,1,"78","632000","1"'
        selected='AT^NRFREQLOCK=2,1,1,"78","635000","1","397"'
        def at(port,cmd):
            calls.append(cmd)
            if cmd=='AT^NRFREQLOCK?':
                return '^NRFREQLOCK: 1\n1,1\n78,632000,1\nOK' if baseline in calls else '^NRFREQLOCK: 2\n1,1\n78,635000,1,397\nOK'
            if cmd=='AT^MONSC':return '^MONSC: NR,460,01,635000,1,100000001,64,100001,-80,-10,20\nOK'
            return 'OK'
        with tempfile.TemporaryDirectory() as d,patch.object(m,'HISTORY',Path(d)),patch.object(m,'at',at),patch.object(m.time,'sleep',lambda _:None):
            phase,actual=m.select_cell(self.current,self.good,self.cfg,baseline,probe=lambda:True)
            self.assertEqual(phase,'original_setting_restored');self.assertEqual(actual,baseline)
            self.assertFalse((Path(d)/'pending.json').exists())
        self.assertIn(selected,calls);self.assertIn(baseline,calls)
        self.assertFalse(any('CFUN' in cmd or 'NDISDUP' in cmd for cmd in calls))
    def test_success_requires_actual_serving_cell_change(self):
        def at(port,cmd):
            if cmd=='AT^NRFREQLOCK?':return '^NRFREQLOCK: 2\n1,1\n78,635000,1,397\nOK'
            if cmd=='AT^MONSC':return '^MONSC: NR,460,01,635000,1,100000002,18D,100001,-70,-10,21\nOK'
            return 'OK'
        with tempfile.TemporaryDirectory() as d,patch.object(m,'HISTORY',Path(d)),patch.object(m,'at',at),patch.object(m.time,'sleep',lambda _:None):
            phase,_=m.select_cell(self.current,self.good,self.cfg,'AT^NRFREQLOCK=0',probe=lambda:True)
            self.assertEqual(phase,'selected');self.assertTrue((Path(d)/'last-selection.json').exists());self.assertFalse((Path(d)/'pending.json').exists())
    def test_no_change_while_network_unavailable(self):
        with patch.object(m,'at',side_effect=AssertionError('AT write while network down')):
            phase,command=m.select_cell(self.current,self.good,self.cfg,'AT^NRFREQLOCK=0',probe=lambda:False)
        self.assertEqual(phase,'network_not_ready');self.assertEqual(command,'AT^NRFREQLOCK=0')
    def test_explicit_auto_entry_clears_old_frequency_and_checks_reply(self):
        calls=[];mode={'value':1}
        def at(port,cmd):
            calls.append(cmd)
            if cmd=='AT^NRFREQLOCK=0':mode['value']=0;return 'OK'
            if cmd=='AT^NRFREQLOCK?':return '^NRFREQLOCK: 0\nOK' if mode['value']==0 else '^NRFREQLOCK: 1\n1,1\n78,632000,1\nOK'
            if cmd=='AT^MONSC':return '^MONSC: NR,460,01,635000,1,100000001,64,100001,-70,-10,21\nOK'
            if cmd=='AT^MONNC':return '^MONNC: NR,635000,18D,-90,-12,10\nOK'
            raise AssertionError(cmd)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch.object(m,'HISTORY',root/'history'),patch.object(m,'STATE',root/'state.json'),patch.object(m,'SCAN',root/'scan.json'),patch.object(m,'RUNTIME_LOCK',root/'runtime.lock'),patch.object(m,'at',at),patch.object(m,'config',lambda:{'enabled':'0'}),patch.object(m,'run',lambda *args,**kw:''),patch.object(sys,'argv',['cell-preference','--enable-auto']),contextlib.redirect_stdout(io.StringIO()):
                m.main()
            self.assertEqual(m.load(root/'state.json')['expected_lock'],'AT^NRFREQLOCK=0')
            self.assertFalse((root/'history/pending.json').exists());self.assertEqual(calls.count('AT^NRFREQLOCK=0'),1)
            self.assertFalse(any('CFUN' in x or 'NDISDUP' in x for x in calls))
    def test_scan_transaction_blocks_checks_and_auto_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);scan=root/'scan.json';scan.write_text('{}')
            with patch.object(m,'SCAN',scan),patch.object(m,'RUNTIME_LOCK',root/'runtime.lock'),patch.object(m,'config',lambda:{'enabled':'1'}),patch.object(m,'at',side_effect=AssertionError('AT during scan')),patch.object(sys,'argv',['cell-preference','--enable-auto']):m.main()
    def test_auto_entry_preserves_configured_preferred_frequency(self):
        calls=[]
        def at(port,cmd):
            calls.append(cmd)
            if cmd=='AT^NRFREQLOCK?':return '^NRFREQLOCK: 1\n0,1\n78,635000,1\nOK'
            if cmd=='AT^MONSC':return '^MONSC: NR,460,01,635000,1,100000001,64,100001,-65,-10,32\nOK'
            if cmd=='AT^MONNC':return '^MONNC: NR,635000,18D,-90,-12,10\nOK'
            raise AssertionError('preferred setting was changed: '+cmd)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch.object(m,'HISTORY',root/'history'),patch.object(m,'STATE',root/'state.json'),patch.object(m,'SCAN',root/'scan.json'),patch.object(m,'RUNTIME_LOCK',root/'runtime.lock'),patch.object(m,'at',at),patch.object(m,'config',lambda:{'enabled':'0','preferred_arfcn':'635000'}),patch.object(m,'run',lambda *a,**k:''),patch.object(sys,'argv',['cell-preference','--enable-auto']),contextlib.redirect_stdout(io.StringIO()):m.main()
            self.assertEqual(m.load(root/'state.json')['phase'],'preferred_frequency_active')
            self.assertEqual(m.load(root/'state.json')['expected_lock'],'AT^NRFREQLOCK=1,0,1,"78","635000","1"')
        self.assertNotIn('AT^NRFREQLOCK=0',calls)

if __name__=='__main__':unittest.main()
