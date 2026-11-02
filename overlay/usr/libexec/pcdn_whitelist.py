#!/usr/bin/python3
"""Maintain the optional PCDN forwarding whitelist without changing NAT."""
import argparse
import ipaddress
import json
from pathlib import Path
import re
import subprocess

from pcdn_settings import macs, valid_name

CHAIN = 'ultra_pcdn_allow'
JUMP = 'PCDN device whitelist'
SETS = {
    'ultra_pcdn_clients': 'ifname . ether_addr',
    'ultra_pcdn_return_v4': 'ifname . ipv4_addr',
    'ultra_pcdn_return_v6': 'ifname . ipv6_addr',
    'ultra_pcdn_uplinks': 'ifname',
}
COMMENTS = (
    'PCDN whitelist outbound',
    'PCDN whitelist IPv6 inbound',
    'PCDN whitelist IPv4 return',
    'PCDN whitelist IPv4 mapped inbound',
)
HOOK_BEGIN = '# BEGIN ultra-pcdn-whitelist'
HOOK_END = '# END ultra-pcdn-whitelist'
HOOK = (HOOK_BEGIN + '\n'
        '[ ! -x /usr/libexec/pcdn-ipv6-access ] || '
        '/usr/libexec/pcdn-ipv6-access >/dev/null 2>&1\n' + HOOK_END + '\n')


def command(args):
    p = subprocess.run(args, capture_output=True, text=True, timeout=8)
    if p.returncode:
        raise RuntimeError('PCDN whitelist command failed: ' + args[0])
    return json.loads(p.stdout)


def interfaces(settings):
    rows = settings.get('interface', [])
    if isinstance(rows, str):
        rows = [rows]
    return {valid_name(x) for x in rows}


def learned_ipv4(settings, addresses, neighbors):
    """Use current neighbor identity and LAN subnets, never a saved old IP."""
    devices = interfaces(settings)
    allowed = macs(settings)
    pools = {}
    own = set()
    for row in addresses:
        if row['ifname'] not in devices:
            continue
        for addr in row.get('addr_info', []):
            if addr.get('family') != 'inet':
                continue
            local = ipaddress.IPv4Interface(addr['local'] + '/' + str(addr['prefixlen']))
            pools.setdefault(row['ifname'], []).append(local.network)
            own.add(local.ip)
    result = set()
    for row in neighbors:
        dev = row.get('dev')
        states = row.get('state', [])
        if isinstance(states, str):
            states = [states]
        if dev not in devices or row.get('lladdr', '').lower() not in allowed:
            continue
        if any(x in ('FAILED', 'INCOMPLETE') for x in states):
            continue
        ip = ipaddress.IPv4Address(row['dst'])
        if ip in own:
            continue
        if any(ip in p and ip not in (p.network_address, p.broadcast_address)
               for p in pools.get(dev, [])):
            result.add((dev, str(ip)))
    return sorted(result)


def current_objects(table):
    items = table.get('nftables', [])
    chains = {x['chain']['name'] for x in items if 'chain' in x}
    sets = {x['set']['name'] for x in items if 'set' in x}
    rules = [x['rule'] for x in items if 'rule' in x]
    return chains, sets, rules


def render(settings, ipv4, ipv6, uplinks, table):
    """Return one atomic nft batch; no raw/notrack or router input changes."""
    chains, sets, rules = current_objects(table)
    jumps = [r for r in rules if r['chain'] == 'forward' and r.get('comment') == JUMP]
    active = settings.get('enabled') == '1' and settings.get('firewall_whitelist') == '1'
    lines = []
    if not active:
        for r in jumps:
            lines.append('delete rule inet fw4 forward handle ' + str(int(r['handle'])))
        if CHAIN in chains:
            lines += ['flush chain inet fw4 ' + CHAIN, 'delete chain inet fw4 ' + CHAIN]
        for name in SETS:
            if name in sets:
                lines.append('delete set inet fw4 ' + name)
        return '\n'.join(lines) + ('\n' if lines else '')

    devices = interfaces(settings)
    clients = sorted((dev, mac) for dev in devices for mac in macs(settings))
    # Validate every token before any nft transaction is submitted.
    v4 = sorted({(valid_name(dev), str(ipaddress.IPv4Address(ip))) for dev, ip in ipv4 if dev in devices})
    v6 = sorted({(valid_name(dev), str(ipaddress.IPv6Address(ip))) for ip, dev in ipv6.items()
                 if dev in devices and ipaddress.IPv6Address(ip).is_global})
    wan = sorted({valid_name(dev) for dev in uplinks} - devices)
    entries = {
        'ultra_pcdn_clients': [json.dumps(dev) + ' . ' + mac for dev, mac in clients],
        'ultra_pcdn_return_v4': [json.dumps(dev) + ' . ' + ip for dev, ip in v4],
        'ultra_pcdn_return_v6': [json.dumps(dev) + ' . ' + ip for dev, ip in v6],
        'ultra_pcdn_uplinks': [json.dumps(dev) for dev in wan],
    }
    for name, kind in SETS.items():
        if name not in sets:
            lines.append('add set inet fw4 ' + name + ' { type ' + kind + '; }')
        lines.append('flush set inet fw4 ' + name)
        if entries[name]:
            lines.append('add element inet fw4 ' + name + ' { ' + ', '.join(entries[name]) + ' }')
    own_rules = [r for r in rules if r['chain'] == CHAIN]
    if CHAIN not in chains:
        lines.append('add chain inet fw4 ' + CHAIN)
    if [r.get('comment') for r in own_rules] != list(COMMENTS):
        lines.append('flush chain inet fw4 ' + CHAIN)
        expressions = (
            'iifname . ether saddr @ultra_pcdn_clients',
            'iifname @ultra_pcdn_uplinks oifname . ip6 daddr @ultra_pcdn_return_v6',
            'iifname @ultra_pcdn_uplinks oifname . ip daddr @ultra_pcdn_return_v4 ct state { established, related }',
            'iifname @ultra_pcdn_uplinks oifname . ip daddr @ultra_pcdn_return_v4 ct status dnat',
        )
        for expr, comment in zip(expressions, COMMENTS):
            lines.append('add rule inet fw4 ' + CHAIN + ' ' + expr +
                         ' counter accept comment ' + json.dumps(comment))
    forwarding = [r for r in rules if r['chain'] == 'forward']
    if len(jumps) != 1 or not forwarding or forwarding[0].get('comment') != JUMP:
        for r in jumps:
            lines.append('delete rule inet fw4 forward handle ' + str(int(r['handle'])))
        lines.append('insert rule inet fw4 forward jump ' + CHAIN + ' comment ' + json.dumps(JUMP))
    return '\n'.join(lines) + '\n'


def refresh(settings, ipv6):
    table = command(['nft', '-j', 'list', 'table', 'inet', 'fw4'])
    active = settings.get('enabled') == '1' and settings.get('firewall_whitelist') == '1'
    ipv4 = []
    uplinks = []
    if active:
        ipv4 = learned_ipv4(settings, command(['ip', '-j', '-4', 'addr', 'show']),
                            command(['ip', '-j', '-4', 'neigh', 'show']))
        wan = command(['ubus', 'call', 'network.interface.' +
                       valid_name(settings.get('upstream', '2_1v6')), 'status'])
        if wan.get('up'):
            uplinks = [wan.get('l3_device') or wan.get('device')]
    batch = render(settings, ipv4, ipv6, uplinks, table)
    if batch:
        p = subprocess.run(['nft', '-f', '-'], input=batch, capture_output=True, text=True, timeout=8)
        if p.returncode:
            raise RuntimeError('PCDN whitelist transaction failed: ' + p.stderr[-400:])
    return {'enabled': active, 'ipv4': [ip for _, ip in ipv4], 'ipv6': sorted(ipv6),
            'filter_scope': 'device forwarding', 'NAT_and_connection_tracking': 'preserved'}


def install_hook(path):
    old = path.read_text() if path.exists() else '#!/bin/sh\nexit 0\n'
    if HOOK_BEGIN in old:
        assert old.count(HOOK_BEGIN) == 1 and HOOK in old, 'existing PCDN hook differs'
        return old
    first, separator, rest = old.partition('\n')
    return first + '\n' + HOOK + rest if first.startswith('#!') and separator else HOOK + old


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install-hook', action='store_true', required=True)
    args = parser.parse_args()
    path = Path('/etc/openclash/custom/openclash_custom_firewall_rules.sh')
    path.parent.mkdir(parents=True, exist_ok=True)
    text = install_hook(path)
    path.write_text(text)
    path.chmod(0o755)
