"""Configuration reader shared by optional PCDN helpers; no personal defaults."""
import ipaddress,re,shlex,subprocess

def values(text):
 sections={};current=None
 for line in text.splitlines():
  args=shlex.split(line,comments=True)
  if not args:continue
  if args[0]=='config' and len(args)>=3:current=sections.setdefault(args[2],{})
  elif current is not None and len(args)>=3:
   if args[0]=='option':current[args[1]]=args[2]
   elif args[0]=='list':current.setdefault(args[1],[]).append(args[2])
 return sections

def config():
 p=subprocess.run(['uci','-q','export','pcdn'],capture_output=True,text=True,timeout=5)
 return values(p.stdout).get('main',{}) if p.returncode==0 else {}

def valid_name(value):
 if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,32}',value):raise ValueError('invalid_interface_name')
 return value

def enabled(settings):return settings.get('enabled')=='1'

def macs(settings):
 rows=settings.get('client_mac',[])
 if isinstance(rows,str):rows=[rows]
 if any(not re.fullmatch(r'[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5}',x) for x in rows):raise ValueError('invalid_client_mac')
 return {x.lower() for x in rows}

def isolated_values(settings,network):
 """Pure validation used before any network or filesystem change."""
 dev=valid_name(network.get('device') or network.get('ifname') or '')
 ipv4=ipaddress.IPv4Interface(network['ipaddr']+'/'+network.get('netmask','255.255.255.0'))
 fixed=ipaddress.IPv4Address(settings['client_ipv4'])
 if fixed not in ipv4.network or fixed in (ipv4.ip,ipv4.network.network_address,ipv4.network.broadcast_address):raise ValueError('client_address_outside_lan')
 start=int(settings.get('dhcp_start','100'));limit=int(settings.get('dhcp_limit','100'))
 first=ipv4.network.network_address+start;last=first+limit-1
 if limit<1 or first<=ipv4.network.network_address or last>=ipv4.network.broadcast_address:raise ValueError('invalid_dhcp_range')
 prefix_id=int(settings.get('ipv6_subnet_id','1'),16)
 if not 1<=prefix_id<=65535:raise ValueError('invalid_ipv6_subnet_id')
 rows=macs(settings)
 if len(rows)!=1:raise ValueError('one_isolated_client_mac_required')
 return {'device':dev,'gateway':str(ipv4.ip),'netmask':str(ipv4.netmask),'first':str(first),'last':str(last),'fixed':str(fixed),'mac':next(iter(rows)),'prefix_id':prefix_id}
