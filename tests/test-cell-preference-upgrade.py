import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

repo=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('upgrade',repo/'scripts/ultra-cell-preference-upgrade.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'root';self.payload=Path(self.temp.name)/'payload';self.root.mkdir();self.payload.mkdir()
        manifest={'files':{}}
        for rel in (*m.CODE,m.CONFIG):
            data=(repo/'overlay'/rel).read_bytes();target=self.payload/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data);manifest['files'][rel]=hashlib.sha256(data).hexdigest()
        (self.payload/'manifest.json').write_text(json.dumps(manifest))
        (self.root/m.CRON).parent.mkdir(parents=True);(self.root/m.CRON).write_text('* * * * * existing-service\n')
    def test_install_preserves_other_jobs_and_disabled_default(self):
        result=m.apply(self.root,self.payload);self.assertTrue(result['changed']);self.assertIn('existing-service',(self.root/m.CRON).read_text());self.assertIn("enabled '0'",(self.root/m.CONFIG).read_text())
    def test_repeat_preserves_personal_configuration(self):
        m.apply(self.root,self.payload);config=self.root/m.CONFIG;config.write_text("config preference 'main'\n option enabled '1'\n option gain_db '8'\n")
        self.assertFalse(m.apply(self.root,self.payload)['changed']);self.assertIn("gain_db '8'",config.read_text());self.assertEqual((self.root/m.CRON).read_text().count(m.ENTRY),1)
    def test_rollback_preserves_new_unrelated_cron_job(self):
        m.apply(self.root,self.payload)
        cron=self.root/m.CRON;cron.write_text(cron.read_text()+'* * * * * another-service\n')
        m.rollback(self.root);self.assertIn('another-service',cron.read_text());self.assertIn('existing-service',cron.read_text());self.assertNotIn(m.ENTRY,cron.read_text());self.assertTrue((self.root/m.CONFIG).exists())
    def test_reinstall_after_rollback(self):
        m.apply(self.root,self.payload);m.rollback(self.root);self.assertTrue(m.apply(self.root,self.payload)['changed'])
    def test_corrupt_payload_rejected_before_writes(self):
        (self.payload/m.CODE[0]).write_text('corrupt')
        with self.assertRaises(AssertionError):m.apply(self.root,self.payload)
        self.assertFalse((self.root/m.CODE[0]).exists());self.assertNotIn(m.ENTRY,(self.root/m.CRON).read_text())

if __name__=='__main__':unittest.main()
