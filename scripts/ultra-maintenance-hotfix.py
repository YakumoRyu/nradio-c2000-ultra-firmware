#!/usr/bin/python3
"""Install cumulative Ultra maintenance fixes with checked rollback."""
import argparse,fcntl,hashlib,json,os,subprocess,tempfile
from pathlib import Path

VERSION='20261023-r2'
BACKUP='overlay/ultra-hotfix-backups/maintenance-'+VERSION


def sha(data):return hashlib.sha256(data).hexdigest()
def write(path,data,mode):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.ultra-maintenance-',dir=str(path.parent))
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(data);f.flush();os.fchmod(f.fileno(),mode);os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)

def apply(root,payload,manifest):
    plan=[]
    for rel,entry in manifest['files'].items():
        path=root/rel;source=payload/rel
        if not path.resolve().is_relative_to(root) or path.is_symlink():raise ValueError('目标路径异常: '+rel)
        data=source.read_bytes();assert sha(data)==entry['after']
        current=path.read_bytes() if path.exists() else None
        if current==data:continue
        if (sha(current) if current is not None else None) not in entry['before']:raise ValueError('需核对当前文件: '+rel)
        plan.append((rel,current,data,entry['mode']))
    directory=root/BACKUP;record=directory/'record.json'
    if record.exists():
        previous=json.loads(record.read_text())
        if plan:raise ValueError('已有本版安装记录，请先回退再重新安装')
        return {'ok':True,'changed':False,'files':len(previous['files'])}
    if not plan:return {'ok':True,'changed':False,'files':0}
    directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    entries={}
    for rel,current,data,mode in plan:
        if current is not None:write(directory/rel,current,0o600)
        entries[rel]={'before':sha(current) if current is not None else None,'after':sha(data),'mode':(root/rel).stat().st_mode&0o777 if current is not None else mode}
    write(record,json.dumps({'version':VERSION,'files':entries}).encode(),0o600)
    changed=[]
    try:
        for rel,current,data,mode in plan:
            write(root/rel,data,mode);changed.append((rel,current,entries[rel]['mode']))
    except Exception:
        for rel,current,mode in reversed(changed):
            if current is None:(root/rel).unlink()
            else:write(root/rel,current,mode)
        record.unlink();raise
    return {'ok':True,'changed':True,'files':len(plan),'changed_paths':[rel for rel,_,_,_ in plan],'backup':'/'+BACKUP,
            'reboot_required':any(rel.startswith('lib/modules/') for rel,_,_,_ in plan)}

def rollback(root):
    directory=root/BACKUP;record=directory/'record.json'
    data=json.loads(record.read_text())
    for rel,entry in data['files'].items():
        current=(root/rel).read_bytes() if (root/rel).exists() else None
        if (sha(current) if current is not None else None) not in (entry['before'],entry['after']):raise ValueError('文件已另行修改: '+rel)
        if entry['before'] is not None:assert sha((directory/rel).read_bytes())==entry['before']
    for rel,entry in data['files'].items():
        if entry['before'] is None:
            if (root/rel).exists():(root/rel).unlink()
        else:write(root/rel,(directory/rel).read_bytes(),entry['mode'])
    record.unlink()
    return {'ok':True,'rolled_back':True,'changed_paths':list(data['files']),
            'reboot_required':any(rel.startswith('lib/modules/') for rel in data['files'])}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('apply','rollback'));p.add_argument('--root',default='/');p.add_argument('--payload',type=Path,default=Path(__file__).parent/'payload')
    a=p.parse_args();root=Path(a.root).resolve()
    assert (root/'tmp/sysinfo/board_name').read_text().strip()=='NRadio-C2000MAX-Ultra'
    assert '25.12' in (root/'etc/openwrt_release').read_text()
    if root==Path('/') and os.uname().release!='6.12.103':raise ValueError('需要Linux6.12.103')
    lock=root/'var/run/ultra-maintenance-hotfix.lock';lock.parent.mkdir(parents=True,exist_ok=True)
    with lock.open('a') as f:
        fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        r=apply(root,a.payload,json.loads((a.payload/'manifest.json').read_text())) if a.action=='apply' else rollback(root)
    if root==Path('/'):
        # LuCI recompiles its menu cache on the next request; no service restarts.
        for item in Path('/tmp').glob('luci-indexcache*'):
            if item.is_file():item.unlink()
        if any(p.startswith('usr/lib/codex-media/') for p in r.get('changed_paths',[])):
            running=False
            for proc in Path('/proc').iterdir():
                if not proc.name.isdigit():continue
                try:
                    args=(proc/'cmdline').read_bytes().split(b'\0')
                    if b'/usr/lib/codex-media/media-health.py' in args:running=True;break
                except OSError:pass
            if running:
                subprocess.run(['/etc/init.d/codex-media-health','restart'],check=True,timeout=30)
                r['media_guard_restarted']=True
    r.setdefault('reboot_required',False)
    print(json.dumps(r))

if __name__=='__main__':
    try:main()
    except Exception as e:raise SystemExit('Ultra maintenance: '+str(e))
