"""Exercise the real monitor with stubbed hardware and the offline installer."""
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
MONITOR = REPO / 'overlay/usr/share/qmodem/modem_dial.sh'
HELPER = REPO / 'packages/ultra-qmodem-hotfix/files/ultra-qmodem-hotfix'
OLD = b'            *)\n                if [ "$ipv4" != "$ipv4_cache" ] || [ "$ipv6" != "$ipv6_cache" ]; then'
NEW = b'            *)\n                unexpected_response_count=0\n                if [ "$ipv4" != "$ipv4_cache" ] || [ "$ipv6" != "$ipv6_cache" ]; then'


def replay(text, sequence):
    start = text.index('at_dial_monitor()\n{')
    end = text.index('\n}\n', start) + 3
    function = text[start:end]
    cases = '\n'.join(str(i) + ') connection_status=' + str(value) + ';;' for i, value in enumerate(sequence, 1))
    script = '''
unexpected_response_count=0
_step=0
_dial_count=0
pdp_type=ipv4
ipv4=10.0.0.2
ipv6=
check_cfun() { return 0; }
at_auto_dial() { return 1; }
at_dial() { _dial_count=$((_dial_count+1)); }
sleep() { :; }
m_debug() { :; }
handle_ip_change() { :; }
check_logfile_line() { :; }
ubus() { echo FORBIDDEN; exit 77; }
uci() { echo FORBIDDEN; exit 77; }
rdisc6() { echo FORBIDDEN; exit 77; }
ndisc6() { echo FORBIDDEN; exit 77; }
check_ip() {
  _step=$((_step+1))
  case "$_step" in
''' + cases + '''
  *) printf '%s\\n' "$_dial_count"; exit 0;;
  esac
}
''' + function + '\nat_dial_monitor\n'
    result = subprocess.run(['/bin/sh'], input=script, text=True, capture_output=True, timeout=5, check=True)
    return int(result.stdout.strip())


class MonitorTests(unittest.TestCase):
    def test_nonconsecutive_errors_do_not_redial(self):
        fixed = MONITOR.read_text()
        sequence = [-1, 3, -1, 3, -1, 3, -1, 3]
        self.assertEqual(replay(fixed, sequence), 1)
        self.assertEqual(replay(fixed.replace(NEW.decode(), OLD.decode(), 1), sequence), 2)

    def test_four_consecutive_errors_still_recover(self):
        self.assertEqual(replay(MONITOR.read_text(), [-1, -1, -1, -1, 3]), 2)

    def test_each_valid_pdp_state_clears_history(self):
        for valid in (1, 2, 3):
            with self.subTest(valid=valid):
                self.assertEqual(replay(MONITOR.read_text(), [-1, -1, -1, valid, -1, -1, -1, valid]), 1)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.target = self.root / 'usr/share/qmodem/modem_dial.sh'
        self.target.parent.mkdir(parents=True)
        self.original = MONITOR.read_bytes().replace(NEW, OLD, 1)
        self.target.write_bytes(self.original)
        self.target.chmod(0o755)
        (self.root / 'tmp/sysinfo').mkdir(parents=True)
        (self.root / 'tmp/sysinfo/board_name').write_text('NRadio-C2000MAX-Ultra\n')
        (self.root / 'etc').mkdir()
        (self.root / 'etc/openwrt_release').write_text("DISTRIB_RELEASE='25.12-SNAPSHOT'\n")

    def run_helper(self, action, *args, success=True):
        result = subprocess.run([sys.executable, str(HELPER), action, '--root', str(self.root), *args], capture_output=True, text=True, timeout=5)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        self.assertNotEqual(result.returncode, 0)
        return result

    def test_idempotent_apply_and_verified_rollback(self):
        self.assertTrue(self.run_helper('apply')['changed'])
        self.assertEqual(self.target.read_bytes().count(NEW), 1)
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o755)
        backup = self.root / 'overlay/ultra-hotfix-backups/20261013-1/modem_dial.sh.before'
        self.assertEqual(backup.read_bytes(), self.original)
        self.assertTrue(self.run_helper('apply')['already_applied'])
        self.assertEqual(backup.read_bytes(), self.original)
        self.assertTrue(self.run_helper('status')['applied'])
        self.assertTrue(self.run_helper('rollback')['rolled_back'])
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertFalse(self.run_helper('status')['applied'])

    def test_modified_target_is_not_overwritten_on_rollback(self):
        self.run_helper('apply')
        modified = self.target.read_bytes() + b'\n# separate local change\n'
        self.target.write_bytes(modified)
        self.run_helper('rollback', success=False)
        self.assertEqual(self.target.read_bytes(), modified)

    def test_wrong_board_is_rejected(self):
        (self.root / 'tmp/sysinfo/board_name').write_text('NRadio-C2000-Max\n')
        self.run_helper('apply', success=False)
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_unknown_monitor_is_rejected(self):
        self.target.write_bytes(b'#!/bin/sh\necho unknown\n')
        self.run_helper('apply', success=False)
        self.assertEqual(self.target.read_bytes(), b'#!/bin/sh\necho unknown\n')

    def test_offline_activation_cannot_touch_live_services(self):
        self.run_helper('apply', '--activate', success=False)
        self.assertEqual(self.target.read_bytes(), self.original)


if __name__ == '__main__':
    unittest.main(verbosity=2)
