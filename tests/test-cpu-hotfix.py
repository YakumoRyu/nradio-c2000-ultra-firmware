"""Exercise the production CPU installer against an isolated filesystem."""
import importlib.util,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
R=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('cpu_hotfix',R/'scripts/ultra-cpu-hotfix.py')
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)

class CPUInstaller(unittest.TestCase):
    def fixture(self,base):
        root=base/'root';payload=base/'payload'
        (root/'usr').mkdir(parents=True);(payload/'usr').mkdir(parents=True)
        (root/'usr/existing').write_bytes(b'old');(root/'usr/existing').chmod(0o755)
        (payload/'usr/existing').write_bytes(b'new');(payload/'usr/created').write_bytes(b'created')
        manifest={'files':{'usr/existing':{'before':[h.sha(b'old')],'after':h.sha(b'new'),'mode':0o755},'usr/created':{'before':[None],'after':h.sha(b'created'),'mode':0o644}}}
        return root,payload,manifest
    def test_apply_noop_rollback_and_modes(self):
        with tempfile.TemporaryDirectory() as d:
            root,p,m=self.fixture(Path(d));self.assertTrue(h.apply(root,p,m)['changed'])
            self.assertFalse(h.apply(root,p,m)['changed'])
            self.assertEqual((root/'usr/existing').stat().st_mode&0o777,0o755)
            h.rollback(root);self.assertEqual((root/'usr/existing').read_bytes(),b'old');self.assertFalse((root/'usr/created').exists())
    def test_unknown_file_prevents_all_writes(self):
        with tempfile.TemporaryDirectory() as d:
            root,p,m=self.fixture(Path(d));(root/'usr/created').write_bytes(b'custom')
            with self.assertRaises(ValueError):h.apply(root,p,m)
            self.assertEqual((root/'usr/existing').read_bytes(),b'old');self.assertFalse((root/h.BACKUP).exists())
    def test_payload_digest_checked(self):
        with tempfile.TemporaryDirectory() as d:
            root,p,m=self.fixture(Path(d));(p/'usr/created').write_bytes(b'broken')
            with self.assertRaises(AssertionError):h.apply(root,p,m)
            self.assertEqual((root/'usr/existing').read_bytes(),b'old')
    def test_partial_failure_restores_changed_files(self):
        with tempfile.TemporaryDirectory() as d:
            root,p,m=self.fixture(Path(d));original=h.write;failed=False
            def write(path,data,mode):
                nonlocal failed
                if path==root/'usr/created' and not failed:failed=True;raise OSError('simulated disk failure')
                return original(path,data,mode)
            with patch.object(h,'write',side_effect=write):
                with self.assertRaises(OSError):h.apply(root,p,m)
            self.assertEqual((root/'usr/existing').read_bytes(),b'old');self.assertFalse((root/'usr/created').exists())
            self.assertFalse((root/h.BACKUP/'record.json').exists())
    def test_rollback_preserves_subsequent_edits(self):
        with tempfile.TemporaryDirectory() as d:
            root,p,m=self.fixture(Path(d));h.apply(root,p,m);(root/'usr/existing').write_bytes(b'manual')
            with self.assertRaises(ValueError):h.rollback(root)
            self.assertEqual((root/'usr/created').read_bytes(),b'created')
    def test_already_fixed_without_record_writes_no_backup(self):
        with tempfile.TemporaryDirectory() as d:
            root,p,m=self.fixture(Path(d))
            for rel in m['files']:(root/rel).write_bytes((p/rel).read_bytes())
            self.assertFalse(h.apply(root,p,m)['changed']);self.assertFalse((root/h.BACKUP).exists())

if __name__=='__main__':unittest.main(verbosity=2)
