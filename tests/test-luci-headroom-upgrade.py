import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

R=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('luci_upgrade',R/'scripts/ultra-luci-headroom-upgrade.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class InstallerTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        base=Path(temp.name);self.root=base/'root';self.payload=base/'payload';manifest={'files':{}}
        for index,rel in enumerate(m.FILES):
            data=(R/'overlay'/rel).read_bytes();p=self.payload/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
            old=('old code '+str(index)).encode() if index<2 else None
            manifest['files'][rel]={'before':m.digest(old) if old else None,'after':m.digest(data)}
            if old:
                p=self.root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(old);p.chmod(0o644)
        (self.payload/'manifest.json').write_text(json.dumps(manifest))
        config=self.root/'etc/config/private';config.parent.mkdir(parents=True);config.write_text('personal data\n');self.config=config
    def test_apply_noop_and_configuration(self):
        self.assertTrue(m.apply(self.root,self.payload)['changed']);self.assertFalse(m.apply(self.root,self.payload)['changed'])
        self.assertEqual(self.config.read_text(),'personal data\n')
    def test_rollback_then_reinstall_preserves_later_settings(self):
        m.apply(self.root,self.payload);self.config.write_text('later config\n');m.rollback(self.root)
        self.assertEqual((self.root/m.FILES[0]).read_text(),'old code 0');self.assertFalse((self.root/m.FILES[2]).exists())
        self.assertEqual(self.config.read_text(),'later config\n');self.assertTrue(m.apply(self.root,self.payload)['changed'])
    def test_tampered_payload_cannot_write(self):
        (self.payload/m.FILES[0]).write_text('tampered')
        with self.assertRaises(AssertionError):m.apply(self.root,self.payload)
        self.assertEqual((self.root/m.FILES[0]).read_text(),'old code 0')
    def test_unexpected_existing_file_is_preserved(self):
        p=self.root/m.FILES[2];p.parent.mkdir(parents=True,exist_ok=True);p.write_text('custom module')
        with self.assertRaises(AssertionError):m.apply(self.root,self.payload)
        self.assertEqual(p.read_text(),'custom module')
    def test_later_code_edit_prevents_rollback(self):
        m.apply(self.root,self.payload);(self.root/m.FILES[0]).write_text('later code')
        with self.assertRaises(AssertionError):m.rollback(self.root)
        self.assertEqual((self.root/m.FILES[0]).read_text(),'later code')
if __name__=='__main__':unittest.main()
