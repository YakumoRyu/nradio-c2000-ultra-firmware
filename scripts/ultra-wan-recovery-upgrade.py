#!/usr/bin/python3
"""Update WAN recovery coverage without changing proxy choices or radio settings."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile

REL='usr/libexec/openclash-wan-recover'
BACKUP='overlay/ultra-hotfix-backups/wan-recovery-20261102-r1'

def digest(data):return hashlib.sha256(data).hexdigest()
def write(path,data,mode=0o755):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.wan-recovery-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(data);os.fchmod(f.fileno(),mode);f.flush();os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)

def apply(root,payload):
    info=json.loads((payload/'manifest.json').read_text())
    assert info['path']==REL
    new=(payload/REL).read_bytes();assert digest(new)==info['after'],'payload differs'
    target=root/REL;old=target.read_bytes()
    if digest(old)==info['after']:return {'changed':False,'configuration_preserved':True}
    assert digest(old)==info['before'],'installed helper differs from supported baseline'
    compile(new,REL,'exec')
    backup=root/BACKUP
    backup.mkdir(parents=True,exist_ok=True,mode=0o700);os.chmod(backup,0o700)
    assert not (backup/'record.json').exists(),'backup already contains a previous transaction'
    write(backup/'previous',old,0o600)
    write(backup/'record.json',json.dumps(info|{'mode':target.stat().st_mode&0o777}).encode(),0o600)
    write(target,new,target.stat().st_mode&0o777)
    return {'changed':True,'backup':'/'+BACKUP,'configuration_preserved':True,'reboot_required':False}

def rollback(root):
    backup=root/BACKUP;info=json.loads((backup/'record.json').read_text())
    target=root/REL
    assert digest(target.read_bytes())==info['after'],'installed helper changed after upgrade'
    old=(backup/'previous').read_bytes();assert digest(old)==info['before'],'backup differs'
    write(target,old,info['mode']);(backup/'record.json').unlink()
    return {'rolled_back':True,'configuration_preserved':True}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['apply','rollback']);p.add_argument('--root',default='/')
    p.add_argument('--payload',type=Path,default=Path(__file__).parent/'payload')
    args=p.parse_args();root=Path(args.root).resolve()
    assert (root/'tmp/sysinfo/board_name').read_text().strip()=='NRadio-C2000MAX-Ultra'
    assert '25.12' in (root/'etc/openwrt_release').read_text()
    lock=root/'var/run/wan-recovery-upgrade.lock';lock.parent.mkdir(parents=True,exist_ok=True)
    with lock.open('a') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
        print(json.dumps(apply(root,args.payload) if args.action=='apply' else rollback(root)))

if __name__=='__main__':main()
