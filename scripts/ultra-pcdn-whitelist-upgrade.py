#!/usr/bin/python3
"""Install the PCDN whitelist helper, preserving device and OpenClash settings."""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile

VERSION = '20261102-r1'
BACKUP = 'overlay/ultra-hotfix-backups/pcdn-whitelist-' + VERSION
CODE = ('usr/libexec/pcdn_whitelist.py', 'usr/libexec/pcdn-ipv6-access',
        'etc/uci-defaults/99-pcdn-whitelist')
HOOK_PATH = 'etc/openclash/custom/openclash_custom_firewall_rules.sh'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write(path, data, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.pcdn-whitelist-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            os.fchmod(f.fileno(), mode)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def helper(payload):
    # Configuration parsing is shared with the already installed PCDN helpers.
    import sys
    sys.path.insert(0, str(payload / 'usr/libexec'))
    spec = importlib.util.spec_from_file_location('whitelist_payload', payload / CODE[0])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def apply(root, payload):
    manifest = json.loads((payload / 'pcdn-manifest.json').read_text())
    assert set(manifest['files']) == set(CODE), 'unexpected payload path'
    for rel, sha in manifest['files'].items():
        assert digest((payload / rel).read_bytes()) == sha, 'payload verification failed'
    # Import dependencies from the target system; test roots provide the same module.
    import sys
    sys.path.insert(0, str(root / 'usr/libexec'))
    m = helper(payload)
    hook = root / HOOK_PATH
    new_hook = m.install_hook(hook).encode()
    backup = root / BACKUP
    record = backup / 'record.json'
    if record.exists():
        assert all((root / rel).is_file() and digest((root / rel).read_bytes()) == sha
                   for rel, sha in manifest['files'].items()), 'installed whitelist code changed'
        assert m.HOOK.encode() in hook.read_bytes(), 'OpenClash hook changed'
        return {'changed': False, 'backup': '/' + BACKUP}
    original = {}
    for rel in (*CODE, HOOK_PATH):
        p = root / rel
        original[rel] = {'exists': p.exists(), 'mode': (p.stat().st_mode & 0o777) if p.exists() else 0o755}
        if p.exists():
            original[rel]['sha256'] = digest(p.read_bytes())
    backup.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(backup, 0o700)
    for rel, info in original.items():
        if info['exists']:
            write(backup / rel, (root / rel).read_bytes(), 0o600)
    info = {'version': VERSION, 'files': manifest['files'], 'original': original,
            'hook_block': m.HOOK, 'hook_sha256': digest(new_hook)}
    write(record, json.dumps(info).encode(), 0o600)
    try:
        for rel in CODE:
            write(root / rel, (payload / rel).read_bytes(), 0o755)
        write(hook, new_hook, original[HOOK_PATH]['mode'])
    except Exception:
        for rel, old in original.items():
            if old['exists']:
                write(root / rel, (backup / rel).read_bytes(), old['mode'])
            elif (root / rel).exists():
                (root / rel).unlink()
        record.unlink()
        raise
    return {'changed': True, 'backup': '/' + BACKUP, 'configuration_preserved': True,
            'whitelist_activation': 'uci set pcdn.main.firewall_whitelist=1; uci commit pcdn; /usr/libexec/pcdn-ipv6-access'}


def rollback(root):
    backup = root / BACKUP
    record = backup / 'record.json'
    info = json.loads(record.read_text())
    for rel, sha in info['files'].items():
        assert digest((root / rel).read_bytes()) == sha, 'installed whitelist code changed'
    hook = root / HOOK_PATH
    data = hook.read_bytes()
    assert data.count(info['hook_block'].encode()) == 1, 'OpenClash hook changed'
    # Remove only our block, retaining later unrelated custom rules.
    write(hook, data.replace(info['hook_block'].encode(), b''), info['original'][HOOK_PATH]['mode'])
    for rel in CODE:
        old = info['original'][rel]
        if old['exists']:
            write(root / rel, (backup / rel).read_bytes(), old['mode'])
        else:
            (root / rel).unlink()
    record.unlink()
    return {'rolled_back': True, 'configuration_preserved': True,
            'runtime_cleanup': 'disable the whitelist and run the helper before rollback'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['apply', 'rollback'])
    p.add_argument('--root', default='/')
    p.add_argument('--payload', type=Path, default=Path(__file__).parent / 'payload')
    args = p.parse_args()
    root = Path(args.root).resolve()
    assert (root / 'tmp/sysinfo/board_name').read_text().strip() == 'NRadio-C2000MAX-Ultra'
    assert '25.12' in (root / 'etc/openwrt_release').read_text()
    lock = root / 'var/run/pcdn-whitelist-upgrade.lock'
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open('a') as guard:
        fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.action == 'rollback' and root == Path('/'):
            import sys
            sys.path.insert(0, '/usr/libexec')
            from pcdn_settings import config
            from pcdn_whitelist import refresh
            refresh(config() | {'firewall_whitelist': '0'}, {})
        print(json.dumps(apply(root, args.payload) if args.action == 'apply' else rollback(root)))


if __name__ == '__main__':
    main()
