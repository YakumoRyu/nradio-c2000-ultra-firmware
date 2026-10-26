#!/usr/bin/python3
"""Install the WebUI cell-scan update and retain the previous package for rollback."""
import argparse, fcntl, hashlib, json, os, shutil, subprocess, tarfile, time
from pathlib import Path

BACKUP = Path('/overlay/ultra-hotfix-backups/webui-20261026-r1')

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def run(args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=90).stdout

def installed():
    return run(['opkg', 'status', 'at-webserver'])

def verify_files(files):
    return all(Path('/'+p).is_file() and digest(Path('/'+p)) == h for p,h in files.items())

def restart():
    run(['/etc/init.d/at-webserver', 'restart'])
    time.sleep(2)
    run(['pidof', 'at-webserver'])

def rollback():
    record=json.loads((BACKUP/'record.json').read_text())
    package=BACKUP/record['package']
    assert digest(package)==record['sha256'], '回退包校验失败'
    run(['opkg', '--force-confold', '--force-downgrade', '--force-reinstall', 'install', str(package)])
    restart()
    assert verify_files(record['files']), '回退文件校验失败'
    (BACKUP/'restored').write_text(str(time.time()))
    return {'rolled_back':True,'backup':str(BACKUP)}

def apply(base):
    manifest=json.loads((base/'manifest.json').read_text())
    for item in ('package','rollback'):
        assert Path(manifest[item]).name==manifest[item]
        assert digest(base/manifest[item])==manifest[item+'_sha256'], '安装包校验失败'
    if verify_files(manifest['files']) and 'Version: 3.0.2-r3\n' in installed():
        return {'changed':False,'version':'3.0.2-r3'}
    assert 'Version: 3.0.2-r2\n' in installed(), '当前WebUI版本不在此升级包支持范围'
    assert verify_files(manifest['before']), '当前WebUI文件与原版r2不同'
    assert not (BACKUP/'record.json').exists(), '本版备份已存在，请先核对安装记录'
    BACKUP.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(BACKUP,0o700)
    shutil.copyfile(base/manifest['rollback'],BACKUP/manifest['rollback'])
    with tarfile.open(BACKUP/'before.tar','w') as tar:
        for rel in ['etc/config/at-webserver','usr/bin/at-webserver','www/5700']:
            if Path('/'+rel).exists():tar.add(Path('/'+rel),arcname=rel)
    os.chmod(BACKUP/'before.tar',0o600)
    record={'package':manifest['rollback'],'sha256':manifest['rollback_sha256'],'files':manifest['before']}
    (BACKUP/'record.json').write_text(json.dumps(record))
    os.chmod(BACKUP/'record.json',0o600)
    try:
        run(['opkg','--force-confold','install',str(base/manifest['package'])])
        restart()
        assert verify_files(manifest['files']), '安装后文件校验失败'
        assert 'Version: 3.0.2-r3\n' in installed(), '软件包版本未更新'
    except Exception:
        rollback()
        raise
    return {'changed':True,'version':'3.0.2-r3','backup':str(BACKUP),'reboot_required':False}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['apply','rollback'])
    args=parser.parse_args()
    assert Path('/tmp/sysinfo/board_name').read_text().strip()=='NRadio-C2000MAX-Ultra','机型不匹配'
    assert '25.12' in Path('/etc/openwrt_release').read_text() and os.uname().release=='6.12.103','系统基线不匹配'
    with open('/var/run/ultra-webui-upgrade.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert not Path('/overlay/at-webserver/scan-session.json').exists(),'请等待扫频结束再升级'
        result=apply(Path(__file__).resolve().parent) if args.action=='apply' else rollback()
    print(json.dumps(result))

if __name__=='__main__':
    try:main()
    except Exception as e:raise SystemExit('WebUI update: '+str(e))
