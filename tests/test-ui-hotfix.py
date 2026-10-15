import importlib.util,json,tempfile,unittest
from pathlib import Path
R=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('hotfix',R/'scripts/ultra-ui-hotfix.py')
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)

class UIInstaller(unittest.TestCase):
    def fixture(self,base):
        root=base/'root';payload=base/'payload';payload.mkdir();root.mkdir()
        css=root/h.CSS;css.parent.mkdir(parents=True);css.write_bytes(b'old css')
        add=payload/'www/luci-static/resources/ultra-layout.css';add.parent.mkdir(parents=True);add.write_bytes(h.MARK+b'\n.new{}')
        target=root/'usr/example';target.parent.mkdir(parents=True);target.write_bytes(b'old');target.chmod(0o755)
        (payload/'usr').mkdir();(payload/'usr/example').write_bytes(b'new');(payload/'usr/created').write_bytes(b'created')
        manifest={'files':{'usr/example':{'before':[h.sha(b'old')],'after':h.sha(b'new'),'mode':0o755},'usr/created':{'before':[None],'after':h.sha(b'created'),'mode':0o644}}}
        return root,payload,manifest
    def test_install_idempotence_rollback_and_modes(self):
        with tempfile.TemporaryDirectory() as d:
            root,payload,m=self.fixture(Path(d))
            self.assertTrue(h.apply(root,payload,m)['changed'])
            self.assertFalse(h.apply(root,payload,m)['changed'])
            self.assertEqual((root/'usr/example').stat().st_mode&0o777,0o755)
            self.assertIn(h.MARK,(root/h.CSS).read_bytes())
            h.rollback(root)
            self.assertEqual((root/'usr/example').read_bytes(),b'old');self.assertFalse((root/'usr/created').exists());self.assertEqual((root/h.CSS).read_bytes(),b'old css')
    def test_unknown_source_aborts_before_any_write(self):
        with tempfile.TemporaryDirectory() as d:
            root,payload,m=self.fixture(Path(d));(root/'usr/example').write_bytes(b'unknown')
            with self.assertRaises(ValueError):h.apply(root,payload,m)
            self.assertFalse((root/'usr/created').exists());self.assertEqual((root/h.CSS).read_bytes(),b'old css')
    def test_rollback_preserves_later_edits(self):
        with tempfile.TemporaryDirectory() as d:
            root,payload,m=self.fixture(Path(d));h.apply(root,payload,m);(root/'usr/example').write_bytes(b'manual')
            with self.assertRaises(ValueError):h.rollback(root)
            self.assertEqual((root/'usr/created').read_bytes(),b'created')

if __name__=='__main__':unittest.main(verbosity=2)
