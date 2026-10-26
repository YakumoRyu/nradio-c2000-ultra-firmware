import hashlib, importlib.util, json, tempfile, unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location('upgrade',Path(__file__).resolve().parents[1]/'scripts/ultra-webui-upgrade.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class UpgradeTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        m.Path=lambda p: self.root/str(p).lstrip('/') if str(p).startswith('/') else Path(p)
        m.BACKUP=self.root/'backup';self.version='3.0.2-r2';self.fail=False;self.restarts=0
        self.base=self.root/'payload';self.base.mkdir()
        self.target=self.root/'usr/bin/at-webserver';self.target.parent.mkdir(parents=True);self.target.write_bytes(b'old')
        config=self.root/'etc/config/at-webserver';config.parent.mkdir(parents=True);config.write_text('personal-settings')
        for name,data in [('new.ipk',b'new package'),('old.ipk',b'old package')]: (self.base/name).write_bytes(data)
        self.manifest={'package':'new.ipk','rollback':'old.ipk','package_sha256':m.digest(self.base/'new.ipk'),'rollback_sha256':m.digest(self.base/'old.ipk'),'files':{'usr/bin/at-webserver':hashlib.sha256(b'new').hexdigest()},'before':{'usr/bin/at-webserver':hashlib.sha256(b'old').hexdigest()}}
        (self.base/'manifest.json').write_text(json.dumps(self.manifest))
        m.installed=lambda:'Version: '+self.version+'\n'
        def run(args):
            if args[0]=='opkg':
                self.assertNotIn('--force-confold',args,'OpenWrt opkg does not support the dpkg confold option')
                new=args[-1].endswith('new.ipk');self.version='3.0.2-r3' if new else '3.0.2-r2';self.target.write_bytes(b'new' if new else b'old')
                if new and self.fail:raise RuntimeError('injected opkg failure after writing files')
            return ''
        m.run=run
        def restart():self.restarts+=1
        m.restart=restart
    def tearDown(self):self.temp.cleanup()
    def test_install_noop_and_rollback_preserve_config(self):
        self.assertTrue(m.apply(self.base)['changed']);self.assertFalse(m.apply(self.base)['changed'])
        self.assertTrue(m.rollback()['rolled_back']);self.assertEqual(self.target.read_bytes(),b'old')
        self.assertEqual((self.root/'etc/config/at-webserver').read_text(),'personal-settings')
    def test_partial_package_failure_restores_old_version(self):
        self.fail=True
        with self.assertRaises(RuntimeError):m.apply(self.base)
        self.assertEqual(self.version,'3.0.2-r2');self.assertEqual(self.target.read_bytes(),b'old')
    def test_modified_baseline_is_untouched(self):
        self.target.write_bytes(b'custom')
        with self.assertRaises(AssertionError):m.apply(self.base)
        self.assertEqual(self.target.read_bytes(),b'custom');self.assertFalse(m.BACKUP.exists())
    def test_corrupt_package_is_rejected_before_backup(self):
        (self.base/'new.ipk').write_bytes(b'corrupt')
        with self.assertRaises(AssertionError):m.apply(self.base)
        self.assertFalse(m.BACKUP.exists());self.assertEqual(self.target.read_bytes(),b'old')

if __name__=='__main__':unittest.main()
