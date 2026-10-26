#!/usr/bin/python3
"""Update Ultra OpenClash and Mihomo with a disk-backed backup and checked rollback."""
import argparse,fcntl,gzip,hashlib,json,os,shutil,subprocess,tarfile,time,urllib.request
from pathlib import Path

BACKUP=Path('/overlay/ultra-hotfix-backups/openclash-20261026-r2')

def digest(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def run(args,timeout=120):
    BACKUP.mkdir(parents=True,exist_ok=True,mode=0o700)
    output=BACKUP/('command-'+str(time.time_ns())+'.log')
    with output.open('w') as f:p=subprocess.run(args,stdout=f,stderr=f,timeout=timeout)
    text=output.read_text()
    if p.returncode:raise RuntimeError('Command failed: '+args[0]+' '+str(p.returncode))
    return text

def package_version():
    text=subprocess.check_output(['opkg','status','luci-app-openclash'],text=True,timeout=10)
    return next(x.split(':',1)[1].strip() for x in text.splitlines() if x.startswith('Version:'))

def files_match(files):return all(Path('/'+rel).is_file() and digest(Path('/'+rel))==sha for rel,sha in files.items())

def ready(expected):
    port=subprocess.check_output(['uci','-q','get','openclash.config.cn_port'],text=True).strip()
    secret=subprocess.check_output(['uci','-q','get','openclash.config.dashboard_password'],text=True).strip()
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));deadline=time.monotonic()+90
    while time.monotonic()<deadline:
        try:
            req=urllib.request.Request('http://127.0.0.1:'+port+'/version',headers={'Authorization':'Bearer '+secret})
            with opener.open(req,timeout=4) as r:
                if json.load(r).get('version')==expected:return
        except (OSError,ValueError):pass
        time.sleep(2)
    raise RuntimeError('核心控制接口未就绪')

def replace_core(source):
    target=Path('/etc/openclash/core/clash_meta.new')
    shutil.copyfile(source,target);os.chmod(target,0o755);os.replace(target,target.with_name('clash_meta'))

def clean_staging_links(stage):
    for name in ('openclash','openclash_ui','pac'):
        p=Path('/tmp')/name
        if p.is_symlink() and p.resolve()==stage/name:p.unlink()
    p=Path('/tmp/openclash.bak')
    if p.is_file() and digest(p)==digest(BACKUP/'original-config'):p.unlink()

def rollback():
    record=json.loads((BACKUP/'record.json').read_text())
    package=BACKUP/record['package'];assert digest(package)==record['package_sha256']
    try:run(['/etc/init.d/openclash','stop'],90)
    except Exception:pass
    stage=BACKUP/'staging';tmp=stage/'opkg-tmp';tmp.mkdir(parents=True,exist_ok=True)
    if not Path('/tmp/openclash.bak').exists():shutil.copyfile(BACKUP/'original-config',Path('/tmp/openclash.bak'))
    for name in ('openclash','openclash_ui','pac'):
        p=Path('/tmp')/name
        if (stage/name).exists() and not p.exists():p.symlink_to(stage/name,target_is_directory=True)
    run(['opkg','--tmp-dir',str(tmp),'--force-downgrade','--force-reinstall','install',str(package)],180)
    run(['tar','-xf',str(BACKUP/'files.tar'),'-C','/'],90)
    replace_core(BACKUP/'clash_meta')
    if record['enabled']:
        run(['/etc/init.d/openclash','start'],180);ready(record['core_version'])
    assert digest(Path('/etc/openclash/core/clash_meta'))==record['core_sha256']
    assert package_version()==record['version']
    clean_staging_links(stage)
    return {'rolled_back':True,'version':record['version'],'backup':str(BACKUP)}

def apply(base):
    manifest=json.loads((base/'manifest.json').read_text())
    for name,sha in manifest['assets'].items():
        assert Path(name).name==name and digest(base/name)==sha,'升级文件校验失败'
    version=package_version()
    if version in manifest['current_versions'] and files_match(manifest['runtime_files']) and digest(Path('/etc/openclash/core/clash_meta'))==manifest['core_sha256']:
        return {'changed':False,'openclash':'0.48.002','mihomo':'v1.19.33'}
    assert version in manifest['rollback_packages'],'当前OpenClash版本不在此升级包范围'
    assert not (BACKUP/'record.json').exists(),'本版备份已存在，请先核对安装记录'
    for name in ('openclash.bak','openclash','openclash_ui','pac'):
        p=Path('/tmp')/name
        assert not p.exists() and not p.is_symlink(),'已有OpenClash升级暂存文件，请等待当前操作结束'
    BACKUP.mkdir(parents=True,exist_ok=True,mode=0o700);os.chmod(BACKUP,0o700)
    stage=BACKUP/'staging';stage.mkdir(mode=0o700)
    package=manifest['rollback_packages'][version]
    shutil.copyfile(base/package,BACKUP/package)
    current_files=subprocess.check_output(['opkg','files','luci-app-openclash'],text=True).splitlines()[1:]
    with tarfile.open(BACKUP/'files.tar','w') as t:
        for rel in current_files+['/etc/openclash','/etc/config/openclash','/etc/config/uhttpd','/etc/config/firewall','/etc/config/dhcp','/etc/nginx/conf.d/openclash.conf']:
            p=Path(rel)
            if p.exists() or p.is_symlink():t.add(p,arcname=rel.lstrip('/'),recursive=rel=='/etc/openclash')
    os.chmod(BACKUP/'files.tar',0o600)
    shutil.copyfile(Path('/etc/openclash/core/clash_meta'),BACKUP/'clash_meta')
    shutil.copyfile(Path('/etc/config/openclash'),BACKUP/'original-config');os.chmod(BACKUP/'original-config',0o600)
    enabled=subprocess.check_output(['uci','-q','get','openclash.config.enable'],text=True).strip()=='1'
    core_version=subprocess.check_output(['/etc/openclash/core/clash_meta','-v'],text=True).split()[2]
    record={'version':version,'package':package,'package_sha256':manifest['assets'][package],'enabled':enabled,'core_version':core_version,'core_sha256':digest(BACKUP/'clash_meta')}
    (BACKUP/'record.json').write_text(json.dumps(record));os.chmod(BACKUP/'record.json',0o600)
    # Preserve upstream's migration process, keeping its large snapshot on TF storage.
    for src,name in [('/etc/openclash','openclash'),('/usr/share/openclash/ui','openclash_ui'),('/www/luci-static/resources/openclash/pac','pac')]:
        if Path(src).exists():run(['cp','-a',src,str(stage/name)],60)
    with gzip.open(base/manifest['core_archive'],'rb') as src,(stage/'clash_meta').open('wb') as dst:shutil.copyfileobj(src,dst,1024*1024)
    assert digest(stage/'clash_meta')==manifest['core_sha256'],'解压核心校验失败'
    opkg_tmp=stage/'opkg-tmp';opkg_tmp.mkdir()
    run(['opkg','--tmp-dir',str(opkg_tmp),'--noaction','install',str(base/manifest['package'])],30)
    try:
        shutil.copyfile(BACKUP/'original-config',Path('/tmp/openclash.bak'))
        for name in ('openclash','openclash_ui','pac'):
            if (stage/name).exists():Path('/tmp/'+name).symlink_to(stage/name,target_is_directory=True)
        run(['/etc/init.d/openclash','stop'],90)
        run(['opkg','--tmp-dir',str(opkg_tmp),'install',str(base/manifest['package'])],180)
        replace_core(stage/'clash_meta')
        if enabled:run(['/etc/init.d/openclash','restart'],180);ready('v1.19.33')
        assert files_match(manifest['runtime_files']),'升级后文件校验失败'
        assert digest(Path('/etc/openclash/core/clash_meta'))==manifest['core_sha256']
    except Exception:
        rollback();raise
    finally:clean_staging_links(stage)
    return {'changed':True,'openclash':package_version(),'mihomo':'v1.19.33','backup':str(BACKUP),'reboot_required':False}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['apply','rollback']);args=parser.parse_args()
    assert Path('/tmp/sysinfo/board_name').read_text().strip()=='NRadio-C2000MAX-Ultra'
    assert '25.12' in Path('/etc/openwrt_release').read_text() and os.uname().release=='6.12.103'
    with open('/var/run/ultra-openclash-upgrade.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        result=apply(Path(__file__).resolve().parent) if args.action=='apply' else rollback()
    print(json.dumps(result))

if __name__=='__main__':
    try:main()
    except Exception as e:raise SystemExit('Ultra OpenClash: '+str(e))
