"""Replay AT/URC interleaving through the installed QModem transport wrapper."""
import json,os,subprocess,tempfile,unittest
from pathlib import Path
R=Path(__file__).resolve().parents[1]
WRAPPER=R/'overlay/usr/libexec/qmodem-at-ubus'

class InterleavedAT(unittest.TestCase):
    def replay(self,command,response):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            programs={
                'jq':'#!/bin/sh\nprintf "%s" "{}"\n',
                'ubus':'#!/bin/sh\nprintf "%s" "$TEST_RESPONSE"\n',
                'jsonfilter':'''#!/usr/bin/python3
import sys,json
r=json.load(sys.stdin)
print(r['status'] if sys.argv[-1]=='@.status' else r['response'])
'''}
            for name,text in programs.items():
                (p/name).write_text(text);(p/name).chmod(0o755)
            env=dict(os.environ,PATH=d+':'+os.environ['PATH'],TEST_RESPONSE=json.dumps({'status':'success','response':response}))
            return subprocess.check_output(['/bin/sh',str(WRAPPER),'/dev/fake',command],env=env,text=True,timeout=3)

    def test_model_second_line(self):
        v=self.replay('AT+CGMM','AT+CGMM\r\n^PDCPDATAINFO: 1,987654321,123456789\r\nMT5700M-CN\r\nOK\r\n')
        self.assertEqual(v.splitlines()[1],'MT5700M-CN')
    def test_imei_second_line(self):
        v=self.replay('AT+CGSN','AT+CGSN\r\n^PDCPDATAINFO: 1,123456789012345,0\r\n^CERSSI: 0,0,0\r\n000000000000000\r\nOK\r\n')
        self.assertEqual(v.splitlines()[1],'000000000000000')
    def test_solicited_signal_is_retained(self):
        v=self.replay('AT^HCSQ?','AT^HCSQ?\n^PDCPDATAINFO: 0,0,0\n^HCSQ: "NR",50,60,70\nOK')
        self.assertIn('^HCSQ:',v);self.assertNotIn('PDCPDATAINFO',v)
    def test_solicited_pdcp_is_retained(self):
        self.assertIn('^PDCPDATAINFO:',self.replay('AT^PDCPDATAINFO?','^PDCPDATAINFO: 1,2,3\nOK'))
    def test_sms_body_and_revision_retained(self):
        self.assertIn('Revision: 1.2.5.0',self.replay('ATI','ATI\n^HCSQ: "NR",1,2,3\nRevision: 1.2.5.0\nOK'))
        body='AT+CMGL=4\n+CMGL: 1,0,,25\n001122334455\nOK'
        self.assertEqual(self.replay('AT+CMGL=4',body).strip(),body)

if __name__=='__main__':unittest.main(verbosity=2)
