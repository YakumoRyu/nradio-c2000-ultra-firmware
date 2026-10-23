"""Reconstruct locally verified release assets on GitHub and verify the upload."""
import hashlib,json,os,re,subprocess,sys,tempfile,urllib.parse,urllib.request
from pathlib import Path

def digest(path):
 with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def api(path):
 result=subprocess.run(['gh','api',path],capture_output=True,check=True,timeout=45)
 return json.loads(result.stdout)

def main(manifest):
 repo=os.environ['GH_REPO'];root=Path.cwd().resolve()
 assert re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo)
 config=json.loads(manifest.read_text());assert config['schema']==1
 releases=api('repos/'+repo+'/releases?per_page=20');records=[]
 with tempfile.TemporaryDirectory(prefix='ultra-release-delta-') as temp:
  directory=Path(temp)
  for item in config['assets']:
   for key in ('base_asset','target_asset'):assert Path(item[key]).name==item[key]
   for key in ('base_sha256','target_sha256','delta_sha256'):assert re.fullmatch('[0-9a-f]{64}',item[key])
   delta=(root/item['delta']).resolve();assert delta.is_relative_to(root) and digest(delta)==item['delta_sha256']
   release=next(r for r in releases if r['tag_name']==item['target_tag']);assert release['draft'] or release['prerelease']
   existing=next((a for a in release['assets'] if a['name']==item['target_asset']),None)
   expected='sha256:'+item['target_sha256']
   if existing:
    assert existing['size']==item['target_bytes'] and existing.get('digest')==expected
    records.append({'name':item['target_asset'],'digest':expected,'bytes':existing['size'],'verified_existing':True});continue
   base=directory/item['base_asset'];target=directory/item['target_asset']
   subprocess.run(['gh','release','download',item['base_tag'],'--repo',repo,'--pattern',item['base_asset'],'--dir',str(directory)],check=True,timeout=240)
   assert digest(base)==item['base_sha256']
   subprocess.run(['bspatch',str(base),str(target),str(delta)],check=True,timeout=180)
   assert target.stat().st_size==item['target_bytes'] and digest(target)==item['target_sha256']
   upload=release['upload_url'].split('{',1)[0]
   assert urllib.parse.urlsplit(upload).hostname=='uploads.github.com'
   request=urllib.request.Request(upload+'?'+urllib.parse.urlencode({'name':target.name}),data=target.read_bytes(),headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json','Content-Type':'application/octet-stream'},method='POST')
   with urllib.request.urlopen(request,timeout=240) as response:asset=json.load(response)
   assert asset['state']=='uploaded' and asset['size']==item['target_bytes'] and asset.get('digest')==expected
   records.append({'name':target.name,'digest':expected,'bytes':asset['size'],'base_and_delta_verified':True,'local_target_digest_matched':True,'uploaded_digest_matched':True})
   print('Verified '+target.name+' '+expected,flush=True)
 result={'passed':True,'commit':os.environ.get('GITHUB_SHA'),'assets':records}
 Path('release-delta-verification.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result),flush=True)

if __name__=='__main__':main(Path(sys.argv[1]))
