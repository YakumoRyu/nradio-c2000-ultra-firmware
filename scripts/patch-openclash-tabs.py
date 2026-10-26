#!/usr/bin/python3
"""Keep OpenClash subscription tabs separate from LuCI's automatic tab widgets."""
import argparse,hashlib,json,os,tempfile
from pathlib import Path

FILES={
 'usr/lib/lua/luci/view/openclash/config_upload.htm':5,
 'www/luci-static/resources/openclash/js/config_upload.js':6,
}

def apply(root):
    changes=[]
    for rel,count in FILES.items():
        path=root/rel;data=path.read_bytes()
        if data.count(b'data-oc-tpl-tab')==count and b'data-tab' not in data:continue
        if data.count(b'data-tab')!=count or b'data-oc-tpl-tab' in data:raise ValueError('Unexpected OpenClash template: '+rel)
        changes.append((path,data.replace(b'data-tab',b'data-oc-tpl-tab')))
    for path,data in changes:
        fd,name=tempfile.mkstemp(prefix='.oc-tabs-',dir=path.parent)
        try:
            with os.fdopen(fd,'wb') as f:f.write(data);os.fchmod(f.fileno(),path.stat().st_mode&0o777);f.flush();os.fsync(f.fileno())
            os.replace(name,path)
        finally:
            if os.path.exists(name):os.unlink(name)
    return {'changed_files':len(changes),'namespace':'data-oc-tpl-tab'}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);a=p.parse_args()
    print(json.dumps(apply(a.root)))
