import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

R=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('upgrade',R/'scripts/ultra-wifi-health-upgrade.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class Install(unittest.TestCase):
    def fixture(self,base):
        root=base/'root';payload=base/'payload';root.mkdir();payload.mkdir()
        files={}
        for rel in m.CODE:
            p=payload/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('new code\n');files[rel]=m.digest(p.read_bytes())
        (payload/'manifest.json').write_text(json.dumps({'files':files}))
        p=root/'etc/config/wireless';p.parent.mkdir(parents=True);p.write_text('personal wifi\n')
        return root,payload,p

    def test_apply_idempotence_and_rollback(self):
        with tempfile.TemporaryDirectory() as d:
            root,payload,config=self.fixture(Path(d))
            self.assertTrue(m.apply(root,payload)['changed'])
            self.assertFalse(m.apply(root,payload)['changed'])
            self.assertTrue(m.rollback(root)['rolled_back'])
            self.assertEqual(config.read_text(),'personal wifi\n')
            self.assertFalse((root/m.CODE[0]).exists())
            self.assertFalse((root/m.LINKS[0]).is_symlink())

    def test_existing_code_and_service_links_restored(self):
        with tempfile.TemporaryDirectory() as d:
            root,payload,config=self.fixture(Path(d))
            p=root/m.CODE[0];p.parent.mkdir(parents=True);p.write_text('old code\n');p.chmod(0o744)
            l=root/m.LINKS[0];l.parent.mkdir(parents=True);l.symlink_to('../init.d/older-wifi-health')
            m.apply(root,payload);m.rollback(root)
            self.assertEqual(p.read_text(),'old code\n')
            self.assertEqual(l.readlink(),Path('../init.d/older-wifi-health'))

    def test_tampered_payload_rejected_before_changes(self):
        with tempfile.TemporaryDirectory() as d:
            root,payload,config=self.fixture(Path(d));(payload/m.CODE[0]).write_text('tampered')
            with self.assertRaises(AssertionError):m.apply(root,payload)
            self.assertFalse((root/m.CODE[0]).exists())

    def test_modified_install_not_overwritten_by_rollback(self):
        with tempfile.TemporaryDirectory() as d:
            root,payload,config=self.fixture(Path(d));m.apply(root,payload)
            (root/m.CODE[0]).write_text('later change')
            with self.assertRaises(AssertionError):m.rollback(root)
            self.assertEqual((root/m.CODE[0]).read_text(),'later change')

    def test_partial_write_failure_restores_original_files(self):
        with tempfile.TemporaryDirectory() as d:
            root,payload,config=self.fixture(Path(d));original=m.write
            def fail(p,data,mode=0o755):
                if p==root/m.CODE[1]:raise OSError('injected failure')
                return original(p,data,mode)
            with patch.object(m,'write',fail):
                with self.assertRaises(OSError):m.apply(root,payload)
            self.assertFalse((root/m.CODE[0]).exists())
            self.assertEqual(config.read_text(),'personal wifi\n')


if __name__=='__main__':unittest.main()
