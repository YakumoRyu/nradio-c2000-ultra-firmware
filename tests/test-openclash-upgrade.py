import gzip,hashlib,importlib.util,json,shutil,tarfile,tempfile,unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location('ocupdate',Path(__file__).resolve().parents[1]/'scripts/ultra-openclash-upgrade.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class UpgradeTest(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.base=self.root/'payload';self.base.mkdir()
  m.Path=lambda p: self.root/str(p).lstrip('/') if str(p).startswith('/') else Path(p)
  m.BACKUP=self.root/'backup';self.version='0.47.156';self.fail=False;self.calls=[]
  for rel,data in [('etc/config/openclash',b'personal'),('etc/openclash/core/clash_meta',b'oldcore'),('usr/service',b'oldcode')]:
   p=self.root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
  (self.root/'tmp').mkdir()
  for name,data in [('new.ipk',b'newpackage'),('old.ipk',b'oldpackage'),('core.gz',gzip.compress(b'newcore'))]:(self.base/name).write_bytes(data)
  self.manifest={'package':'new.ipk','core_archive':'core.gz','core_sha256':hashlib.sha256(b'newcore').hexdigest(),'assets':{p.name:m.digest(p) for p in self.base.iterdir()},'runtime_files':{'usr/service':hashlib.sha256(b'newcode').hexdigest()},'current_versions':['0.48.002-rultra1'],'rollback_packages':{'0.47.156':'old.ipk'}}
  (self.base/'manifest.json').write_text(json.dumps(self.manifest))
  m.package_version=lambda:self.version;m.ready=lambda v:None
  self.original_check_output=m.subprocess.check_output
  def output(args,**kw):
   if args[:2]==['opkg','files']:return 'Package contains files:\n/usr/service\n'
   if args[0]=='uci':return '1\n'
   if args[0].endswith('clash_meta'):return 'Mihomo Meta v1.19.32 fixture\n'
   raise AssertionError(args)
  m.subprocess.check_output=output
  def run(args,timeout=120):
   self.calls.append(args);self.assertNotIn('--force-confold',args)
   if args[0]=='cp':
    src=self.root/args[2].lstrip('/');dst=Path(args[3]);shutil.copytree(src,dst,symlinks=True)
   elif args[0]=='opkg' and '--noaction' not in args:
    new=args[-1].endswith('new.ipk');self.version='0.48.002-rultra1' if new else '0.47.156';(self.root/'usr/service').write_bytes(b'newcode' if new else b'oldcode')
    if new and self.fail:raise RuntimeError('injected install failure after files changed')
   elif args[0]=='tar':
    with tarfile.open(args[2]) as t:t.extractall(self.root,filter='data')
   return ''
  m.run=run
 def tearDown(self):m.subprocess.check_output=self.original_check_output;self.temp.cleanup()
 def test_install_repeat_and_rollback_preserve_config(self):
  self.assertTrue(m.apply(self.base)['changed']);self.assertFalse(m.apply(self.base)['changed']);self.assertTrue(m.rollback()['rolled_back'])
  self.assertEqual((self.root/'etc/config/openclash').read_bytes(),b'personal');self.assertEqual((self.root/'etc/openclash/core/clash_meta').read_bytes(),b'oldcore');self.assertFalse((self.root/'tmp/openclash').exists())
 def test_failed_native_install_restores_core_and_package(self):
  self.fail=True
  with self.assertRaises(RuntimeError):m.apply(self.base)
  self.assertEqual(self.version,'0.47.156');self.assertEqual((self.root/'usr/service').read_bytes(),b'oldcode');self.assertEqual((self.root/'etc/openclash/core/clash_meta').read_bytes(),b'oldcore')
 def test_corrupt_asset_rejected_without_stopping_service(self):
  (self.base/'core.gz').write_bytes(b'corrupt')
  with self.assertRaises(AssertionError):m.apply(self.base)
  self.assertFalse(self.calls);self.assertFalse(m.BACKUP.exists())
 def test_unsupported_baseline_is_untouched(self):
  self.version='custom'
  with self.assertRaises(AssertionError):m.apply(self.base)
  self.assertFalse(self.calls);self.assertFalse(m.BACKUP.exists())
 def test_existing_upgrade_snapshot_blocks_before_service_stop(self):
  (self.root/'tmp/openclash.bak').write_text('another transaction')
  with self.assertRaises(AssertionError):m.apply(self.base)
  self.assertFalse(self.calls)

if __name__=='__main__':unittest.main()
