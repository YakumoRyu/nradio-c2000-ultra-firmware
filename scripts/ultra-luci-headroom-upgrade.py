#!/usr/bin/python3
"""Install bounded LuCI status polling without changing personal settings."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

FILES=('usr/lib/lua/luci/controller/fancontrol.lua','usr/lib/lua/luci/controller/mwrt-assurance.lua',
       'usr/lib/lua/luci/model/ultra_status_cache.lua','usr/lib/lua/luci/view/zmode/modem_info.htm',
       'www/luci-static/resources/ultra-home-status.js','usr/lib/codex-media/media_protection.py')
BACKUP='overlay/ultra-hotfix-backups/luci-headroom-20261104-r1'
VM=()

def digest(data):return hashlib.sha256(data).hexdigest()
def write(path,data,mode):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.luci-headroom-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(data);os.fchmod(f.fileno(),mode);f.flush();os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)

def sysctl(args):
    p=subprocess.run(['sysctl',*args],capture_output=True,text=True,timeout=8,check=True)
    return p.stdout.strip()

def apply(root,payload):
    manifest=json.loads((payload/'manifest.json').read_text())
    assert set(manifest['files'])==set(FILES),'unexpected payload paths'
    for rel,row in manifest['files'].items():
        assert digest((payload/rel).read_bytes())==row['after'],'payload verification failed'
    target_hashes={rel:digest((root/rel).read_bytes()) if (root/rel).exists() else None for rel in FILES}
    if all(target_hashes[rel]==manifest['files'][rel]['after'] for rel in FILES):
        return {'changed':False,'configuration_preserved':True}
    assert all(target_hashes[rel]==manifest['files'][rel]['before'] for rel in FILES),'unsupported existing code'
    backup=root/BACKUP;record=backup/'record.json'
    assert not record.exists(),'existing transaction needs review'
    backup.mkdir(parents=True,exist_ok=True,mode=0o700);os.chmod(backup,0o700)
    original={}
    for rel in FILES:
        p=root/rel
        original[rel]={'exists':p.exists(),'mode':p.stat().st_mode&0o777 if p.exists() else 0o644}
        if p.exists():write(backup/rel,p.read_bytes(),0o600)
    values={key:sysctl(['-n',key]) for key in VM} if root==Path('/') else {}
    write(record,json.dumps({'files':manifest['files'],'original':original,'vm':values}).encode(),0o600)
    try:
        for rel in FILES:write(root/rel,(payload/rel).read_bytes(),original[rel]['mode'])
        if root==Path('/'):
            subprocess.run(['/etc/init.d/codex-media-health','restart'],check=True,timeout=20,
                           stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    except Exception:
        for rel,row in original.items():
            if row['exists']:write(root/rel,(backup/rel).read_bytes(),row['mode'])
            elif (root/rel).exists():(root/rel).unlink()
        if values:sysctl(['-w',*[k+'='+v for k,v in values.items()]])
        record.unlink();raise
    return {'changed':True,'backup':'/'+BACKUP,'configuration_preserved':True,'reboot_required':False}

def rollback(root):
    backup=root/BACKUP;record=backup/'record.json';info=json.loads(record.read_text())
    for rel,row in info['files'].items():assert digest((root/rel).read_bytes())==row['after'],'updated code changed'
    for rel,row in info['original'].items():
        if row['exists']:write(root/rel,(backup/rel).read_bytes(),row['mode'])
        else:(root/rel).unlink()
    if root==Path('/') and info['vm']:sysctl(['-w',*[k+'='+v for k,v in info['vm'].items()]])
    if root==Path('/'):
        subprocess.run(['/etc/init.d/codex-media-health','restart'],check=True,timeout=20,
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    record.unlink()
    return {'rolled_back':True,'configuration_preserved':True}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['apply','rollback']);p.add_argument('--root',default='/')
    p.add_argument('--payload',type=Path,default=Path(__file__).parent/'payload')
    args=p.parse_args();root=Path(args.root).resolve()
    assert (root/'tmp/sysinfo/board_name').read_text().strip()=='NRadio-C2000MAX-Ultra'
    assert '25.12' in (root/'etc/openwrt_release').read_text()
    lock=root/'var/run/luci-headroom-upgrade.lock';lock.parent.mkdir(parents=True,exist_ok=True)
    with lock.open('a') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
        print(json.dumps(apply(root,args.payload) if args.action=='apply' else rollback(root)))

if __name__=='__main__':main()
