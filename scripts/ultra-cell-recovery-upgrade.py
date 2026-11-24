#!/usr/bin/python3
"""Update the installed cell preference helper and retain its prior version."""
import argparse
import fcntl
import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path


HELPER = Path('usr/libexec/cell-preference')
BACKUP = Path('overlay/ultra-hotfix-backups/cell-recovery-20261124-r1')
LOCK = Path('tmp/cell-preference.lock')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write(path, data, mode):
    fd, name = tempfile.mkstemp(prefix='.cell-recovery-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def apply(root, payload):
    manifest = json.loads((payload / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('path') != HELPER.as_posix():
        raise ValueError('Unexpected payload path')
    new = (payload / HELPER).read_bytes()
    if digest(new) != manifest['after']:
        raise ValueError('Payload hash mismatch')
    target = root / HELPER
    if target.is_symlink():
        raise ValueError('Expected a regular cell preference helper')
    old = target.read_bytes()
    if digest(old) == manifest['after']:
        return {'changed': False}
    if digest(old) != manifest['before']:
        raise ValueError('Installed helper does not match the supported version')
    compile(new, str(HELPER), 'exec')
    backup = root / BACKUP
    backup.mkdir(mode=0o700, parents=True, exist_ok=True)
    record = backup / 'record.json'
    mode = stat.S_IMODE(target.stat().st_mode)
    metadata = manifest | {'mode': mode}
    if record.exists():
        if json.loads(record.read_text(encoding='utf-8')) != metadata or digest((backup / 'previous').read_bytes()) != manifest['before']:
            raise ValueError('Existing transaction does not match this install')
    else:
        write(backup / 'previous', old, 0o600)
        write(record, json.dumps(metadata).encode('utf-8'), 0o600)
    write(target, new, mode)
    return {'changed': True, 'backup': '/' + BACKUP.as_posix(), 'reboot_required': False}


def rollback(root):
    backup = root / BACKUP
    record = backup / 'record.json'
    manifest = json.loads(record.read_text(encoding='utf-8'))
    target = root / HELPER
    old = (backup / 'previous').read_bytes()
    if target.is_symlink() or digest(target.read_bytes()) != manifest['after'] or digest(old) != manifest['before']:
        raise ValueError('Installed helper or backup changed')
    write(target, old, manifest['mode'])
    return {'rolled_back': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['apply', 'rollback'])
    parser.add_argument('--root', default='/')
    parser.add_argument('--payload', type=Path, default=Path(__file__).parent / 'payload')
    args = parser.parse_args()
    root = Path(args.root).resolve()
    board = (root / 'tmp/sysinfo/board_name').read_text().strip()
    if board != 'NRadio-C2000MAX-Ultra' or '25.12' not in (root / 'etc/openwrt_release').read_text():
        raise ValueError('This package requires C2000 Ultra with ImmortalWrt 25.12')
    with (root / LOCK).open('a') as guard:
        fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (root / 'overlay/cell-preference/pending.json').exists():
            raise RuntimeError('Wait for the active cell preference transaction to finish')
        result = apply(root, args.payload) if args.action == 'apply' else rollback(root)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
