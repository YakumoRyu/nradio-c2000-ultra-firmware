import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

repo = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo / 'overlay/usr/libexec'))
import pcdn_whitelist as m

spec = importlib.util.spec_from_file_location('pcdn_upgrade', repo / 'scripts/ultra-pcdn-whitelist-upgrade.py')
upgrade = importlib.util.module_from_spec(spec)
spec.loader.exec_module(upgrade)

SETTINGS = {'enabled': '1', 'firewall_whitelist': '1',
            'interface': ['br-lan'], 'client_mac': ['02:00:00:00:00:01']}


class WhitelistTests(unittest.TestCase):
    def batch(self, settings=None, table=None, ips=None):
        return m.render(settings or SETTINGS, [('br-lan', '192.0.2.10')],
                        ips or {'2001:4860:1234::10': 'br-lan'}, ['eth2'], table or {})

    def test_disabled_default_creates_no_accept_rules(self):
        self.assertEqual(self.batch(SETTINGS | {'firewall_whitelist': '0'}), '')

    def test_outbound_mac_and_interface_with_ipv4_ipv6(self):
        text = self.batch()
        self.assertIn('"br-lan" . 02:00:00:00:00:01', text)
        self.assertIn('iifname . ether saddr @ultra_pcdn_clients counter accept', text)
        self.assertNotIn('notrack', text)
        self.assertNotIn('input ', text)
        self.assertNotIn('prerouting', text)

    def test_ipv4_inbound_requires_return_or_dnat(self):
        text = self.batch()
        ipv4_rules = [line for line in text.splitlines() if 'add rule' in line and 'ip daddr' in line]
        self.assertEqual(len(ipv4_rules), 2)
        self.assertTrue(all('ct state' in line or 'ct status dnat' in line for line in ipv4_rules))
        self.assertTrue(all('iifname @ultra_pcdn_uplinks' in line for line in ipv4_rules))

    def test_ipv6_all_ports_only_to_learned_device(self):
        text = self.batch(ips={'2001:4860:1234::10': 'br-lan', 'fd00::1': 'br-lan', '2001:4860::2': 'other'})
        self.assertIn('"br-lan" . 2001:4860:1234::10', text)
        self.assertNotIn('fd00', text)
        self.assertNotIn('2001:4860::2', text)
        line = next(x for x in text.splitlines() if 'IPv6 inbound' in x)
        self.assertNotIn('dport', line)
        self.assertIn('oifname . ip6 daddr @ultra_pcdn_return_v6', line)

    def test_moves_jump_before_openclash_and_removes_duplicates(self):
        rules = [{'rule': {'chain': 'forward', 'comment': 'OpenClash QUIC REJECT', 'handle': 2}},
                 {'rule': {'chain': 'forward', 'comment': m.JUMP, 'handle': 3}},
                 {'rule': {'chain': 'forward', 'comment': m.JUMP, 'handle': 4}}]
        text = self.batch(table={'nftables': rules})
        self.assertIn('delete rule inet fw4 forward handle 3', text)
        self.assertIn('delete rule inet fw4 forward handle 4', text)
        self.assertEqual(text.count('insert rule inet fw4 forward'), 1)

    def test_refresh_retains_counters_and_single_top_jump(self):
        rows = [{'chain': {'name': m.CHAIN}}]
        rows += [{'set': {'name': name}} for name in m.SETS]
        rows += [{'rule': {'chain': 'forward', 'comment': m.JUMP, 'handle': 1}}]
        rows += [{'rule': {'chain': m.CHAIN, 'comment': c, 'handle': 10 + i}} for i, c in enumerate(m.COMMENTS)]
        text = self.batch(table={'nftables': rows})
        self.assertNotIn('flush chain', text)
        self.assertNotIn('insert rule', text)
        self.assertNotIn('delete rule', text)
        self.assertEqual(text.count('flush set'), 4)

    def test_disabling_removes_only_our_objects(self):
        rows = [{'chain': {'name': m.CHAIN}}, {'chain': {'name': 'forward'}}]
        rows += [{'set': {'name': name}} for name in m.SETS]
        rows += [{'rule': {'chain': 'forward', 'comment': m.JUMP, 'handle': 1}}]
        text = self.batch(SETTINGS | {'firewall_whitelist': '0'}, {'nftables': rows})
        self.assertIn('delete chain inet fw4 ' + m.CHAIN, text)
        self.assertNotIn('flush table', text)
        self.assertNotIn('delete chain inet fw4 forward', text)

    def test_invalid_mac_and_interface_rejected(self):
        for settings in (SETTINGS | {'client_mac': ['invalid']}, SETTINGS | {'interface': ['br-lan"; accept']}):
            with self.assertRaises(ValueError):
                self.batch(settings)

    def test_ipv4_uses_current_lan_neighbor_not_old_saved_address(self):
        addresses = [{'ifname': 'br-lan', 'addr_info': [
            {'family': 'inet', 'local': '192.0.2.1', 'prefixlen': 24}]}]
        neighbors = [{'dev': 'br-lan', 'dst': '192.0.2.10', 'lladdr': '02:00:00:00:00:01', 'state': ['REACHABLE']}]
        rows = m.learned_ipv4(SETTINGS | {'client_ipv4': '198.51.100.1'}, addresses, neighbors)
        self.assertEqual(rows, [('br-lan', '192.0.2.10')])
        for address, state, mac in [('192.0.2.10', 'FAILED', '02:00:00:00:00:01'),
                                     ('198.51.100.10', 'REACHABLE', '02:00:00:00:00:01'),
                                     ('192.0.2.1', 'REACHABLE', '02:00:00:00:00:01'),
                                     ('192.0.2.11', 'REACHABLE', '02:00:00:00:00:02')]:
            row = neighbors[0] | {'dst': address, 'state': [state], 'lladdr': mac}
            self.assertEqual(m.learned_ipv4(SETTINGS, addresses, [row]), [])


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.root = base / 'root'
        self.payload = base / 'payload'
        self.root.mkdir()
        self.payload.mkdir()
        manifest = {'files': {}}
        for rel in upgrade.CODE:
            data = (repo / 'overlay' / rel).read_bytes()
            path = self.payload / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            manifest['files'][rel] = upgrade.digest(data)
        (self.payload / 'pcdn-manifest.json').write_text(json.dumps(manifest))
        self.hook = self.root / upgrade.HOOK_PATH
        self.hook.parent.mkdir(parents=True)
        self.hook.write_text('#!/bin/sh\n# existing custom rules\nexit 0\n')
        old = self.root / 'usr/libexec/pcdn-ipv6-access'
        old.parent.mkdir(parents=True)
        old.write_text('previous helper\n')
        old.chmod(0o755)

    def test_apply_repeat_and_preserve_custom_hook(self):
        self.assertTrue(upgrade.apply(self.root, self.payload)['changed'])
        self.assertFalse(upgrade.apply(self.root, self.payload)['changed'])
        text = self.hook.read_text()
        self.assertEqual(text.count(m.HOOK_BEGIN), 1)
        self.assertIn('# existing custom rules', text)
        self.assertLess(text.index(m.HOOK_BEGIN), text.index('exit 0'))
        self.assertFalse((self.root / 'etc/config/pcdn').exists())

    def test_rollback_restores_code_preserves_later_hook_edits(self):
        upgrade.apply(self.root, self.payload)
        self.hook.write_text(self.hook.read_text() + '# later custom rule\n')
        upgrade.rollback(self.root)
        self.assertEqual((self.root / 'usr/libexec/pcdn-ipv6-access').read_text(), 'previous helper\n')
        self.assertFalse((self.root / upgrade.CODE[0]).exists())
        self.assertIn('# later custom rule', self.hook.read_text())
        self.assertNotIn(m.HOOK_BEGIN, self.hook.read_text())

    def test_corrupt_payload_rejected_before_mutation(self):
        (self.payload / upgrade.CODE[0]).write_text('invalid')
        with self.assertRaises(AssertionError):
            upgrade.apply(self.root, self.payload)
        self.assertNotIn(m.HOOK_BEGIN, self.hook.read_text())
        self.assertEqual((self.root / 'usr/libexec/pcdn-ipv6-access').read_text(), 'previous helper\n')


if __name__ == '__main__':
    unittest.main()
