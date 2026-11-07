#!/usr/bin/python3
"""Install the wireless health observer and bounded AP recovery service."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

CODE = ['usr/libexec/ultra-wifi-health', 'etc/init.d/ultra-wifi-health',
        'etc/uci-defaults/99-ultra-wifi-health']
LINKS = ['etc/rc.d/S95ultra-wifi-health', 'etc/rc.d/K10ultra-wifi-health']
BACKUP = 'overlay/ultra-hotfix-backups/wifi-health-package-20261107-r1'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write(p, data, mode=0o755):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + '.wifi-health.tmp')
    tmp.write_bytes(data)
    tmp.chmod(mode)
    os.replace(tmp, p)


def verify(payload):
    manifest = json.loads((payload / 'manifest.json').read_text())
    assert set(manifest['files']) == set(CODE), 'Unexpected payload'
    for rel, sha in manifest['files'].items():
        assert digest((payload / rel).read_bytes()) == sha, 'Invalid payload: ' + rel
    return manifest


def restore(root, info):
    backup = root / BACKUP
    for rel, data in info['files'].items():
        p = root / rel
        if data['existed']:
            write(p, (backup / rel).read_bytes(), data['mode'])
        elif p.exists():
            p.unlink()
    for rel, target in info['links'].items():
        p = root / rel
        if p.is_symlink():
            p.unlink()
        if target:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.symlink_to(target)


def apply(root, payload):
    root, payload = Path(root), Path(payload)
    manifest = verify(payload)
    if all((root / rel).is_file() and digest((root / rel).read_bytes()) == sha
           for rel, sha in manifest['files'].items()) and all((root / p).is_symlink() for p in LINKS):
        return {'changed': False, 'configuration_preserved': True}
    backup = root / BACKUP
    info_path = backup / 'manifest.json'
    assert not info_path.exists(), 'Existing transaction requires inspection'
    info = {'files': {}, 'links': {}}
    for rel in CODE:
        p = root / rel
        assert not p.is_symlink(), 'Unexpected code symlink'
        row = {'existed': p.exists(), 'mode': p.stat().st_mode & 0o777 if p.exists() else 0o755,
               'after': manifest['files'][rel]}
        if p.exists():
            row['before'] = digest(p.read_bytes())
            dest = backup / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dest)
        info['files'][rel] = row
    for rel in LINKS:
        p = root / rel
        assert not p.exists() or p.is_symlink(), 'Unexpected service entry'
        info['links'][rel] = os.readlink(p) if p.is_symlink() else None
    backup.mkdir(parents=True, exist_ok=True)
    backup.chmod(0o700)
    write(info_path, json.dumps(info, indent=2).encode(), 0o600)
    try:
        for rel in CODE:
            write(root / rel, (payload / rel).read_bytes())
        for rel in LINKS:
            p = root / rel
            if p.is_symlink():
                p.unlink()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.symlink_to('../init.d/ultra-wifi-health')
    except Exception:
        restore(root, info)
        raise
    return {'changed': True, 'configuration_preserved': True,
            'backup': '/' + BACKUP, 'reboot_required': False}


def rollback(root):
    root = Path(root)
    info = json.loads((root / BACKUP / 'manifest.json').read_text())
    for rel, row in info['files'].items():
        assert (root / rel).is_file() and digest((root / rel).read_bytes()) == row['after'], 'Installed file changed'
    restore(root, info)
    return {'rolled_back': True, 'configuration_preserved': True}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['apply', 'rollback'])
    p.add_argument('--root', default='/')
    args = p.parse_args()
    root = Path(args.root)
    live = root.resolve() == Path('/')
    if args.action == 'apply':
        if live:
            board = subprocess.check_output(['ubus', 'call', 'system', 'board'], text=True)
            assert 'NRadio-C2000MAX-Ultra' in board, 'This package targets C2000 Ultra'
        result = apply(root, Path(__file__).parent / 'payload')
        if live:
            subprocess.run(['/etc/init.d/ultra-wifi-health', 'enable'], check=True)
            subprocess.run(['/etc/init.d/ultra-wifi-health', 'restart'], check=True)
    else:
        # Verify ownership before stopping or restoring any service.
        info = json.loads((root / BACKUP / 'manifest.json').read_text())
        assert all(digest((root / rel).read_bytes()) == row['after'] for rel, row in info['files'].items())
        if live:
            subprocess.run(['/etc/init.d/ultra-wifi-health', 'stop'], check=True)
        result = rollback(root)
        if live and (root / LINKS[0]).is_symlink():
            subprocess.run(['/etc/init.d/ultra-wifi-health', 'start'], check=True)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
