#!/usr/bin/env python3
import importlib.machinery
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import tempfile
import contextlib
import io
import json
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
        active=baseline
        def at(port,cmd):
            nonlocal active
            calls.append(cmd)
            if cmd=='AT^NRFREQLOCK?':
                return '^NRFREQLOCK: 1\n1,1\n78,632000,1\nOK' if active==baseline else '^NRFREQLOCK: 2\n1,1\n78,635000,1,397\nOK'
            if cmd=='AT^MONSC':return '^MONSC: NR,460,01,635000,1,100000001,64,100001,-80,-10,20\nOK'
            if cmd in (baseline,selected):active=cmd
            return 'OK'
        with tempfile.TemporaryDirectory() as d,patch.object(m,'HISTORY',Path(d)),patch.object(m,'at',at),patch.object(m.time,'sleep',lambda _:None):
            phase,actual=m.select_cell(self.current,self.good,self.cfg,baseline,probe=lambda:True)
            self.assertEqual(phase,'original_setting_restored');self.assertEqual(actual,baseline)
            self.assertFalse((Path(d)/'pending.json').exists())
        self.assertIn(selected,calls);self.assertIn(baseline,calls)
        self.assertFalse(any('CFUN' in cmd or 'NDISDUP' in cmd for cmd in calls))
    def test_success_requires_actual_serving_cell_change(self):
        selected=False
        def at(port,cmd):
            nonlocal selected
            if cmd=='AT^NRFREQLOCK?':return '^NRFREQLOCK: 2\n1,1\n78,635000,1,397\nOK' if selected else '^NRFREQLOCK: 0\nOK'
            if cmd=='AT^MONSC':return '^MONSC: NR,460,01,635000,1,100000002,18D,100001,-70,-10,21\nOK'
            if cmd.startswith('AT^NRFREQLOCK=2,'):selected=True
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

    def test_fallback_frequency_does_not_get_promoted_over_preference(self):
        self.cfg['preferred_arfcn']=632000
        state,target=self.decide([self.good])
        self.assertEqual(state['phase'],'preferred_frequency_unavailable')
        self.assertIsNone(target)

    def test_mobile_frequency_accepts_exact_mobile_lock(self):
        c=m.checked_config({'preferred_arfcn':'635000','preferred_mobility':'1'})
        self.assertEqual(m.preferred_lock(c),'AT^NRFREQLOCK=1,1,1,"78","635000","1"')
        with self.assertRaises(ValueError):m.checked_config({'preferred_mobility':'2'})

    def test_mobile_policy_can_improve_on_fallback_frequency(self):
        self.cfg.update(preferred_mobility=1,preferred_arfcn=632000)
        state={}
        for t in (10000,10060,10120):state,target=self.decide([self.good],state,t)
        self.assertEqual(target,self.good)

    def test_only_measured_known_preference_can_cross_frequency(self):
        self.cfg.update(preferred_mobility=1,preferred_arfcn=632000,preferred_scs=0)
        # PCI can be reused between frequencies. SCS comes from the preference.
        raw='^MONNC: NR,632000,64,-70,-10,22\n^MONNC: NR,630000,64,-60,-8,31\n'
        candidates=m.neighbors(raw,self.current,self.cfg)
        self.assertEqual(len(candidates),1)
        self.assertEqual((candidates[0]['pci'],candidates[0]['scs']),(100,0))
        for t in (10000,10060,10120):
            state,target=self.decide(candidates+[self.good],{} if t==10000 else state,t)
        self.assertEqual(target,candidates[0])
        state,target=self.decide([candidates[0]|{'sinr':-2}],state,10180)
        self.assertIsNone(target)
        self.assertNotIn('better_neighbor',state)

    @contextlib.contextmanager
    def runtime(self,root,query):
        with patch.multiple(m,HISTORY=root/'history',STATE=root/'state.json',
                            SCAN=root/'scan.json',RUNTIME_LOCK=root/'runtime.lock',at=query,
                            config=lambda:{'enabled':'1','preferred_arfcn':'635000'}):
            yield

    def test_home_return_uses_frequency_and_pci_and_rechecks_quality(self):
        self.cfg.update(preferred_mobility=1,preferred_arfcn=632000,preferred_pci=100)
        home=self.good|{'arfcn':632000,'pci':100,'rsrp':-79}
        other=home|{'pci':564,'rsrp':-78}
        state={}
        for t in (10000,10060,10120):
            state,target=self.decide([self.good,home,other],state,t)
        self.assertEqual(target,home)
        self.assertFalse(m.acceptable(home|{'sinr':-3},self.current,self.cfg))
        self.assertFalse(m.home_cell(self.current,self.cfg))
        state,target=m.decide(home,[home|{'pci':555,'rsrp':-61}],{},self.cfg,10180)
        self.assertIsNone(target)
        self.assertEqual(state['phase'],'preferred_frequency_active')

    def test_mobile_loss_unlocks_and_continues_observing_then_relocks_home(self):
        cfg={'enabled':'1','preferred_mobility':'1','preferred_arfcn':'635000','preferred_pci':'100'}
        pref='AT^NRFREQLOCK=1,1,1,"78","635000","1"'
        target='AT^NRFREQLOCK=2,1,1,"78","635000","1","100"'
        responses={pref:'^NRFREQLOCK: 1\n1,1\n78,635000,1\nOK',m.UNLOCKED:'^NRFREQLOCK: 0\nOK',
                   target:'^NRFREQLOCK: 2\n1,1\n78,635000,1,100\nOK'}
        active=pref
        signal='^MONSC: LTE\nOK'
        calls=[]
        def at(port,cmd):
            nonlocal active
            if cmd==m.LOCK_QUERY:return responses[active]
            if cmd=='AT^MONSC':return signal
            if cmd=='AT^MONNC':return 'OK'
            self.assertIn(cmd,responses)
            calls.append(cmd);active=cmd
            return 'OK'
        with tempfile.TemporaryDirectory() as d,self.runtime(Path(d),at),patch.object(m,'config',return_value=cfg),patch.object(sys,'argv',['cell-preference']),patch.object(m,'ipv6_default_present',return_value=True),patch.object(m,'internet_ok',return_value=True),patch.object(m.time,'sleep'):
            def tick(t):
                with patch.object(m.time,'time',return_value=t):m.main()
                return m.load(m.STATE)
            tick(10000);tick(10060)
            self.assertEqual(calls,[])
            self.assertEqual(tick(10120)['phase'],'fallback_after_service_loss')
            signal='^MONSC: NR,460,01,632000,1,100000001,64,100001,-80,-10,20\nOK'
            self.assertEqual(tick(10180)['lock_owner'],'fallback')
            self.assertEqual(calls,[m.UNLOCKED])
            signal=signal.replace('632000','635000')
            for t in (12100,12160,12220):state=tick(t)
            self.assertEqual(state['phase'],'selected')
            self.assertEqual(calls,[m.UNLOCKED,target])
            self.assertEqual(tick(12280)['lock_owner'],'selection')
            # Network handed over, but the modem still reports our old PCI lock.
            # After persistent absence release just the PCI, leaving mobility on.
            signal=signal.replace('635000','632000')
            for t in (12340,12400,12460):state=tick(t)
            self.assertEqual(state['phase'],'released_absent_home')
            self.assertEqual(calls,[m.UNLOCKED,target,pref])

    def test_external_lock_updates_serving_status_without_any_setter(self):
        replies={'AT^NRFREQLOCK?':'^NRFREQLOCK: 2\n0,1\n78,635000,1,397\nOK',
                 'AT^MONSC':'^MONSC: NR,460,01,635000,1,100000002,18D,100001,-70,-10,21\nOK'}
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with self.runtime(root,lambda port,cmd:replies[cmd]),patch.object(sys,'argv',['cell-preference']):
                m.atomic(m.STATE,{'expected_lock':'AT^NRFREQLOCK=0','phase':'manual_lock_changed',
                                  'current':self.current|{'arfcn':632000},'count':3})
                m.main()
                state=m.load(m.STATE)
                self.assertEqual(state['phase'],'external_lock_active')
                self.assertEqual(state['current']['arfcn'],635000)
                self.assertEqual(state['count'],0)
                log=m.HISTORY/'events.jsonl'
                row=json.loads(log.read_text())
                self.assertEqual(row['cell']['pci'],397)
                self.assertNotIn('nci',row['cell'])
                before=log.read_bytes()
                m.main()
                self.assertEqual(log.read_bytes(),before)

    def test_status_preserves_pending_transaction_and_does_not_create_files(self):
        replies={'AT^NRFREQLOCK?':'^NRFREQLOCK: 2\n0,1\n78,635000,1,397\nOK',
                 'AT^MONSC':'^MONSC: NR,460,01,635000,1,100000002,18D,100001,-70,-10,21\nOK'}
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            output=io.StringIO()
            with self.runtime(root,lambda port,cmd:replies[cmd]),patch.object(sys,'argv',['cell-preference','--check']),contextlib.redirect_stdout(output):
                journal=m.HISTORY/'pending.json'
                m.atomic(journal,{'baseline':'AT^NRFREQLOCK=0','requested':'AT^NRFREQLOCK=2,0,1,"78","635000","1","397"'})
                before=journal.read_bytes()
                m.main()
                self.assertEqual(json.loads(output.getvalue())['phase'],'transaction_pending')
                self.assertEqual(journal.read_bytes(),before)
                self.assertFalse(m.STATE.exists())
                self.assertFalse(m.RUNTIME_LOCK.exists())

    def test_trial_cannot_commit_after_required_ipv6_default_route_disappears(self):
        active=False
        def at(port,cmd):
            nonlocal active
            if cmd=='AT^NRFREQLOCK?':return '^NRFREQLOCK: 2\n1,1\n78,635000,1,397\nOK' if active else '^NRFREQLOCK: 0\nOK'
            if cmd=='AT^MONSC':return '^MONSC: NR,460,01,635000,1,100000002,18D,100001,-70,-10,21\nOK'
            active=cmd!='AT^NRFREQLOCK=0'
            return 'OK'
        def run(args,timeout):
            self.assertEqual(args[:5],['ip','-6','route','show','default'])
            return 'default via fe80::1 dev eth2' if not active else ''
        with tempfile.TemporaryDirectory() as d,patch.multiple(m,HISTORY=Path(d),at=at,run=run),patch.object(m.subprocess,'run',return_value=type('Probe',(),{'returncode':0})()),patch.object(m.time,'sleep'):
            phase, actual=m.select_cell(self.current,self.good,self.cfg,'AT^NRFREQLOCK=0')
            self.assertEqual((phase,actual),('original_setting_restored','AT^NRFREQLOCK=0'))
            self.assertFalse(active)
            self.assertFalse((Path(d)/'last-selection.json').exists())

    def test_trial_rollback_leaves_later_manual_lock_in_place(self):
        replies=iter(['^NRFREQLOCK: 0\nOK','^NRFREQLOCK: 2\n1,1\n78,635000,1,397\nOK',
                      '^NRFREQLOCK: 1\n0,1\n78,632000,1\nOK'])
        def at(port,cmd):
            if cmd=='AT^NRFREQLOCK?':return next(replies)
            if cmd=='AT^MONSC':return '^MONSC: NR,460,01,635000,1,100000001,64,100001,-80,-10,20\nOK'
            self.assertEqual(cmd,'AT^NRFREQLOCK=2,1,1,"78","635000","1","397"')
            return 'OK'
        with tempfile.TemporaryDirectory() as d,patch.multiple(m,HISTORY=Path(d),at=at),patch.object(m.time,'sleep'):
            phase,actual=m.select_cell(self.current,self.good,self.cfg,'AT^NRFREQLOCK=0',probe=lambda:True)
            self.assertEqual((phase,actual),('external_lock_preserved','AT^NRFREQLOCK=1,0,1,"78","632000","1"'))
            self.assertFalse((Path(d)/'pending.json').exists())

    def test_only_policy_selection_can_restore_after_nr_loss(self):
        baseline='AT^NRFREQLOCK=1,0,1,"78","635000","1"'
        selected='AT^NRFREQLOCK=2,0,1,"78","635000","1","397"'
        active=selected
        def at(port,cmd):
            nonlocal active
            if cmd=='AT^NRFREQLOCK?':return '^NRFREQLOCK: 2\n0,1\n78,635000,1,397\nOK' if active==selected else '^NRFREQLOCK: 1\n0,1\n78,635000,1\nOK'
            if cmd=='AT^MONSC':return '^MONSC: LTE\nOK'
            self.assertEqual(cmd,baseline)
            active=baseline
            return 'OK'
        with tempfile.TemporaryDirectory() as d:
            with self.runtime(Path(d),at),patch.object(sys,'argv',['cell-preference']):
                for now in (10000,10060,10120):
                    with patch.object(m.time,'time',return_value=now):m.main()
                self.assertEqual(active,selected)
                m.atomic(m.HISTORY/'last-selection.json',{'baseline':baseline,'requested':selected,'confirmed':self.good})
                with patch.object(m.time,'time',return_value=10180):m.main()
                self.assertEqual(active,baseline)
                self.assertTrue(m.load(m.HISTORY/'last-selection.json')['retired'])
                self.assertEqual(m.load(m.STATE)['phase'],'previous_setting_restored_after_service_loss')

if __name__=='__main__':unittest.main()
