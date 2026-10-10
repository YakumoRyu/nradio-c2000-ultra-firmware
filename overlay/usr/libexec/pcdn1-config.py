#!/usr/bin/python3
"""Refresh an optional isolated LAN's routed IPv6 pool and DHCP service."""
import fcntl,ipaddress,json,os,subprocess,sys
from pathlib import Path
from pcdn_settings import config,enabled,isolated_values,valid_name,values

def output(args):
 p=subprocess.run(args,capture_output=True,text=True,timeout=10)
 return p.stdout.strip() if p.returncode==0 else ''
def call(args):subprocess.run(args,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)

def main():
 settings=config()
 if not enabled(settings):return
 name=valid_name(settings.get('isolated_network','pcdn1'));upstream=valid_name(settings.get('upstream','2_1v6'))
 network=values(output(['uci','-q','export','network'])).get(name)
 if not network:return
 params=isolated_values(settings,network)
 with open('/tmp/pcdn1-config.lock','w') as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:return
  state=json.loads(output(['ubus','call','network.interface.'+upstream,'status']) or '{}');pool=None
  for item in state.get('ipv6-prefix',[]):
   n=ipaddress.IPv6Network(item['address']+'/'+str(item['mask']))
   if n.prefixlen==64 and n.network_address.is_global:
    pool=ipaddress.IPv6Network((int(n.network_address)+(params['prefix_id']<<48),80));break
  address=str(pool.network_address+1)+'/80' if pool else ''
  old=network.get('ip6addr','');changed=old!=address
  if changed:
   if address:call(['uci','set','network.'+name+'.ip6addr='+address])
   elif old:call(['uci','delete','network.'+name+'.ip6addr'])
   call(['uci','commit','network']);call(['ubus','call','network','reload'])
  port=int(settings.get('dns_port','5355'))
  if not 1024<=port<=65535:raise ValueError('invalid_dns_port')
  servers=settings.get('dns_server',['223.5.5.5','119.29.29.29'])
  if isinstance(servers,str):servers=[servers]
  servers=[str(ipaddress.ip_address(s)) for s in servers]
  dev=params['device']
  lines=[f'port={port}',f'interface={dev}','except-interface=lo','bind-dynamic','no-hosts','no-resolv',*[f'server={s}' for s in servers],'cache-size=256','domain-needed','bogus-priv','user=nobody','group=nogroup','dhcp-authoritative','dhcp-leasefile=/tmp/pcdn-port1.leases',f'dhcp-range=set:pcdn1,{params["first"]},{params["last"]},{params["netmask"]},12h',f'dhcp-host={params["mac"]},{params["fixed"]},pcdn-port1,12h',f'dhcp-option=tag:pcdn1,option:router,{params["gateway"]}',f'dhcp-option=tag:pcdn1,option:dns-server,{params["gateway"]}','log-dhcp']
  if pool:lines+=['enable-ra',f'ra-param={dev},20,180',f'dhcp-range={pool.network_address+0x100},{pool.network_address+0xffff},80,30m','dhcp-option=option6:dns-server,[::]']
  path=Path('/var/etc/pcdn-port1.conf');path.parent.mkdir(exist_ok=True);text='\n'.join(lines)+'\n';different=not path.exists() or path.read_text()!=text
  tmp=path.with_suffix('.tmp');tmp.write_text(text);os.chmod(tmp,0o600);os.replace(tmp,path)
  call(['/usr/sbin/dnsmasq','--test','--conf-file='+str(path)])
  lease=Path('/tmp/pcdn-port1.leases');lease.touch(exist_ok=True);os.chown(lease,65534,65534);os.chmod(lease,0o600)
  if '--event' in sys.argv and (changed or different):call(['/etc/init.d/pcdn-port1','restart'])
  print(json.dumps({'public_pool':str(pool) if pool else None,'address':address,'prefix_changed':changed}))
if __name__=='__main__':main()
