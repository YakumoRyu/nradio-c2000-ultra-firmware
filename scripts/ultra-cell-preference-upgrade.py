#!/usr/bin/python3
"""Install signal-priority reselection while retaining radio and personal settings."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

VERSION='20261102-r1'
BACKUP='overlay/ultra-hotfix-backups/cell-preference-'+VERSION
CODE=('usr/libexec/cell-preference','etc/uci-defaults/98-cell-preference')
CONFIG='etc/config/cell_preference'
CRON='etc/crontabs/root'
ENTRY='* * * * * [ "$(uci -q get cell_preference.main.enabled)" = 1 ] && /usr/libexec/cell-preference >/dev/null 2>&1'

def digest(data):return hashlib.sha256(data).hexdigest()

def write(path,data,mode):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.cell-pref-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(data);stream.flush();os.fchmod(stream.fileno(),mode);os.fsync(stream.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)

def apply(root,payload):
    manifest=json.loads((payload/'manifest.json').read_text())
    assert set(manifest['files'])==set(CODE)|{CONFIG}
    for rel,sha in manifest['files'].items():assert digest((payload/rel).read_bytes())==sha,'payload verification failed'
    backup=root/BACKUP;record=backup/'record.json'
    if record.exists():
        assert all((root/rel).is_file() and digest((root/rel).read_bytes())==manifest['files'][rel] for rel in CODE),'installed code changed'
        return {'changed':False,'backup':'/'+BACKUP}
    assert all(not (root/rel).exists() for rel in CODE),'existing cell-preference code requires review'
    original={rel:((root/rel).read_bytes() if (root/rel).exists() else None) for rel in (CONFIG,CRON)}
    backup.mkdir(parents=True,exist_ok=True,mode=0o700);os.chmod(backup,0o700)
    for rel,data in original.items():
        if data is not None:write(backup/rel,data,0o600)
    write(record,json.dumps({'version':VERSION,'created_config':original[CONFIG] is None,'files':manifest['files']}).encode(),0o600)
    try:
        for rel in CODE:write(root/rel,(payload/rel).read_bytes(),0o755)
        if original[CONFIG] is None:write(root/CONFIG,(payload/CONFIG).read_bytes(),0o600)
        cron=original[CRON] or b''
        if b'/usr/libexec/cell-preference' not in cron:write(root/CRON,cron.rstrip(b'\n')+b'\n'+ENTRY.encode()+b'\n',0o600)
    except Exception:
        for rel in CODE:
            if (root/rel).exists():(root/rel).unlink()
        for rel,data in original.items():
            if data is not None:write(root/rel,data,0o600)
            elif (root/rel).exists():(root/rel).unlink()
        record.unlink();raise
    return {'changed':True,'backup':'/'+BACKUP,'radio_reset':False,'configuration_preserved':True}

def rollback(root):
    backup=root/BACKUP;record=backup/'record.json';info=json.loads(record.read_text())
    for rel in CODE:assert digest((root/rel).read_bytes())==info['files'][rel],'installed code changed'
    for rel in CODE:(root/rel).unlink()
    cron=root/CRON
    if cron.exists():write(cron,b'\n'.join(x for x in cron.read_bytes().splitlines() if x!=ENTRY.encode())+b'\n',0o600)
    # Retain the user's preference configuration for a later reinstall.
    record.unlink()
    return {'rolled_back':True,'radio_reset':False}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['apply','rollback']);parser.add_argument('--root',default='/');parser.add_argument('--payload',type=Path,default=Path(__file__).parent/'payload');args=parser.parse_args()
    root=Path(args.root).resolve()
    assert (root/'tmp/sysinfo/board_name').read_text().strip()=='NRadio-C2000MAX-Ultra'
    assert '25.12' in (root/'etc/openwrt_release').read_text()
    lock=root/'var/run/cell-preference-upgrade.lock';lock.parent.mkdir(parents=True,exist_ok=True)
    with lock.open('a') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
        print(json.dumps(apply(root,args.payload) if args.action=='apply' else rollback(root)))

if __name__=='__main__':main()
