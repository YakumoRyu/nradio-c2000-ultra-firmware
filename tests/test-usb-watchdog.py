"""Replay the real AT reaper against fake /proc entries; never signal live PIDs."""
import os,subprocess,tempfile,unittest
from pathlib import Path
R=Path(__file__).resolve().parents[1]
SOURCE=R/'overlay/usr/bin/mwrt-qmodem-usb3'

def replay(entries):
 with tempfile.TemporaryDirectory() as d:
  base=Path(d);proc=base/'proc';proc.mkdir();tools=base/'bin';tools.mkdir()
  for i,(comm,argv,age) in enumerate(entries,100):
   p=proc/str(i);p.mkdir();(p/'comm').write_text(comm+'\n');(p/'cmdline').write_bytes(b'\0'.join(x.encode() for x in argv)+b'\0');(p/'age').write_text(str(age))
  wrapper=tools/'tr';wrapper.write_text('#!/bin/sh\necho call >> "$TR_LOG"\nexec /usr/bin/tr "$@"\n');wrapper.chmod(0o755)
  text=SOURCE.read_text(encoding='utf-8');start=text.index('reap_stuck_at() {');end=text.index('\n}\n',start)+3
  function=text[start:end].replace('/proc/',str(proc)+'/')
  shell='''
AT_STUCK_AGE=40
proc_age() { cat "PROC/$1/age"; }
tty_belongs_to() { return 1; }
log() { :; }
kill() { printf 'KILL:%s\\n' "$2"; }
sleep() { :; }
rm() { :; }
'''.replace('PROC',str(proc))+function+'\nreap_stuck_at 2-1\n'
  env=dict(os.environ,PATH=str(tools)+':'+os.environ['PATH'],TR_LOG=str(base/'tr.log'))
  result=subprocess.run(['/bin/sh'],input=shell,text=True,capture_output=True,env=env,timeout=5,check=True)
  calls=len((base/'tr.log').read_text().splitlines()) if (base/'tr.log').exists() else 0
  return result.stdout,calls

class Reaper(unittest.TestCase):
 def test_unrelated_processes_start_no_decoder(self):
  out,calls=replay([('kworker/0:1',['kworker/0:1'],100),('clash',['/etc/openclash/clash'],100),('python3',['python3','anything'],100)]*100)
  self.assertEqual(out,'');self.assertEqual(calls,0)
 def test_old_tom_modem_reaped(self):
  out,calls=replay([('tom_modem.real',['/usr/bin/tom_modem.real','-d','/dev/ttyUSB99'],80)])
  self.assertEqual(out,'KILL:100\n');self.assertEqual(calls,2)
 def test_young_tom_modem_kept(self):
  self.assertEqual(replay([('tom_modem.real',['tom_modem.real'],10)])[0],'')
 def test_only_exact_flock_command_reaped(self):
  out,_=replay([('flock',['flock','-x','9'],80),('flock',['flock','-nx','8'],80)])
  self.assertEqual(out,'KILL:100\n')
 def test_argument_text_and_spoofed_comm_kept(self):
  out,_=replay([('grep',['grep','flock -x 9'],80),('flock',['grep','flock -x 9'],80)])
  self.assertEqual(out,'')
 def test_busybox_compatible_argv_still_checked(self):
  self.assertEqual(replay([('busybox',['flock','-x','9'],80)])[0],'KILL:100\n')

if __name__=='__main__':unittest.main(verbosity=2)
