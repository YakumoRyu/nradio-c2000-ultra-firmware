import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

R=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('wan_upgrade',R/'scripts/ultra-wan-recovery-upgrade.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class UpgradeTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)/'root';self.payload=Path(temp.name)/'payload'
        old=b'print("previous helper")\n';new=(R/'overlay'/m.REL).read_bytes()
        for p,data in [(self.root/m.REL,old),(self.payload/m.REL,new)]:
            p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);p.chmod(0o755)
        (self.root/'etc/config').mkdir(parents=True)
        self.config=self.root/'etc/config/personal';self.config.write_text('synthetic private config\n')
        self.manifest={'path':m.REL,'before':m.digest(old),'after':m.digest(new)}
        (self.payload/'manifest.json').write_text(json.dumps(self.manifest))
    def test_apply_and_repeat_preserve_configuration(self):
        self.assertTrue(m.apply(self.root,self.payload)['changed'])
        self.assertFalse(m.apply(self.root,self.payload)['changed'])
        self.assertEqual(self.config.read_text(),'synthetic private config\n')
    def test_rollback_retains_unrelated_files_and_reinstall(self):
        m.apply(self.root,self.payload);self.config.write_text('later personal config\n')
        m.rollback(self.root)
        self.assertEqual((self.root/m.REL).read_text(),'print("previous helper")\n')
        self.assertEqual(self.config.read_text(),'later personal config\n')
        self.assertTrue(m.apply(self.root,self.payload)['changed'])
    def test_modified_payload_rejected(self):
        (self.payload/m.REL).write_text('invalid')
        with self.assertRaises(AssertionError):m.apply(self.root,self.payload)
        self.assertEqual((self.root/m.REL).read_text(),'print("previous helper")\n')
    def test_unknown_installed_helper_is_preserved(self):
        (self.root/m.REL).write_text('user edited helper\n')
        with self.assertRaises(AssertionError):m.apply(self.root,self.payload)
        self.assertEqual((self.root/m.REL).read_text(),'user edited helper\n')

if __name__=='__main__':unittest.main()
