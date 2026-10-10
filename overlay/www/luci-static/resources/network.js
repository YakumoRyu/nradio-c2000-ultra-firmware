'use strict';'require uci';'require rpc';'require validation';'require baseclass';'require firewall';const proto_errors={CONNECT_FAILED:_('Connection attempt failed'),INVALID_ADDRESS:_('IP address is invalid'),INVALID_GATEWAY:_('Gateway address is invalid'),INVALID_LOCAL_ADDRESS:_('Local IP address is invalid'),MISSING_ADDRESS:_('IP address is missing'),MISSING_PEER_ADDRESS:_('Peer address is missing'),NO_DEVICE:_('Network device is not present'),NO_IFACE:_('Unable to determine device name'),NO_IFNAME:_('Unable to determine device name'),NO_WAN_ADDRESS:_('Unable to determine external IP address'),NO_WAN_LINK:_('Unable to determine upstream interface'),PEER_RESOLVE_FAIL:_('Unable to resolve peer host name'),PIN_FAILED:_('PIN code rejected')};const iface_patterns_ignore=[/^wmaster\d+/,/^wifi\d+/,/^hwsim\d+/,/^imq\d+/,/^ifb\d+/,/^mon\.wlan\d+/,/^sit\d+/,/^gre\d+/,/^gretap\d+/,/^ip6gre\d+/,/^ip6tnl\d+/,/^tunl\d+/,/^lo$/];const iface_patterns_wireless=[/^wlan\d+/,/^ra[xiyez]?\d+/,/^apcli[xiyez]?\d+/,/^wl\d+/,/^ath\d+/,/^\w+\.network\d+/];const iface_patterns_virtual=[];const callLuciNetworkDevices=rpc.declare({object:'luci-rpc',method:'getNetworkDevices',expect:{'':{}}});const callLuciWirelessDevices=rpc.declare({object:'luci-rpc',method:'getWirelessDevices',expect:{'':{}}});const callLuciBoardJSON=rpc.declare({object:'luci-rpc',method:'getBoardJSON'});const callLuciHostHints=rpc.declare({object:'luci-rpc',method:'getHostHints',expect:{'':{}}});const callIwinfoAssoclist=rpc.declare({object:'iwinfo',method:'assoclist',params:['device','mac'],expect:{results:[]}});const callIwinfoScan=rpc.declare({object:'iwinfo',method:'scan',params:['device'],nobatch:true,expect:{results:[]}});const callNetworkInterfaceDump=rpc.declare({object:'network.interface',method:'dump',expect:{'interface':[]}});const callNetworkProtoHandlers=rpc.declare({object:'network',method:'get_proto_handlers',expect:{'':{}}});let _init=null;let _state=null;const _protocols={};const _protospecs={};function getProtocolHandlers(){return callNetworkProtoHandlers().then(function(protos){delete protos.bonding;if(!protos.hasOwnProperty('none'))
Object.assign(protos,{none:{no_device:false}});if(!protos.hasOwnProperty('relay')&&L.hasSystemFeature('relayd'))
Object.assign(protos,{relay:{no_device:true}});Object.assign(_protospecs,protos);return Promise.all(Object.keys(protos).map(function(p){return Promise.resolve(L.require('protocol.%s'.format(p))).catch(function(err){if(L.isObject(err)&&err.name!='NetworkError')
L.error(err);});})).then(function(){return protos;});}).catch(function(){return{};});}
function getWifiStateBySid(sid){const s=uci.get('wireless',sid);if(s!=null&&s['.type']=='wifi-iface'){for(let radioname in _state.radios){for(let netstate of _state.radios[radioname].interfaces){if(typeof(netstate.section)!='string')
continue;const s2=uci.get('wireless',netstate.section);if(s2!=null&&s['.type']==s2['.type']&&s['.name']==s2['.name']){if(s2['.anonymous']==false&&netstate.section.charAt(0)=='@')
return null;return[radioname,_state.radios[radioname],netstate];}}}}
return null;}
function getWifiStateByIfname(ifname){for(let radioname in _state.radios){for(let netstate of _state.radios[radioname].interfaces){if(typeof(netstate.ifname)!='string')
continue;if(netstate.ifname==ifname)
return[radioname,_state.radios[radioname],netstate];}}
return null;}
function isWifiIfname(ifname){for(let ifp of iface_patterns_wireless)
if(ifp.test(ifname))
return true;return false;}
function getWifiSidByNetid(netid){const m=/^(\w+)\.network(\d+)$/.exec(netid);if(m){const sections=uci.sections('wireless','wifi-iface');let n=0;for(let s of sections){if(s.device!=m[1])
continue;if(++n==+m[2])
return s['.name'];}}
return null;}
function getWifiSidByIfname(ifname){const sid=getWifiSidByNetid(ifname);if(sid!=null)
return sid;const res=getWifiStateByIfname(ifname);if(res!=null&&L.isObject(res[2])&&typeof(res[2].section)=='string')
return res[2].section;return null;}
function getWifiNetidBySid(sid){const s=uci.get('wireless',sid);if(s!=null&&s['.type']=='wifi-iface'){const radioname=s.device;if(typeof(radioname)=='string'){const sections=uci.sections('wireless','wifi-iface');let n=0;for(let sec of sections){if(sec.device!=radioname)
continue;n++;if(sec['.name']!=s['.name'])
continue;return['%s.network%d'.format(s.device,n),s.device];}}}
return null;}
function getWifiNetidByNetname(name){const sections=uci.sections('wireless','wifi-iface');for(let s of sections){if(typeof(s.network)!='string')
continue;const nets=s.network.split(/\s+/);for(let n of nets){if(n!=name)
continue;return getWifiNetidBySid(s['.name']);}}
return null;}
function isVirtualIfname(ifname){for(let nfp of iface_patterns_virtual)
if(nfp.test(ifname))
return true;return false;}
function isIgnoredIfname(ifname){for(let nfpi of iface_patterns_ignore)
if(nfpi.test(ifname))
return true;return false;}
function appendValue(config,section,option,value){let values=uci.get(config,section,option);const isArray=Array.isArray(values);let rv=false;if(isArray==false)
values=L.toArray(values);if(values.indexOf(value)==-1){values.push(value);rv=true;}
uci.set(config,section,option,isArray?values:values.join(' '));return rv;}
function removeValue(config,section,option,value){let values=uci.get(config,section,option);const isArray=Array.isArray(values);let rv=false;if(isArray==false)
values=L.toArray(values);for(let i=values.length-1;i>=0;i--){if(values[i]==value){values.splice(i,1);rv=true;}}
if(values.length>0)
uci.set(config,section,option,isArray?values:values.join(' '));else
uci.unset(config,section,option);return rv;}
function prefixToMask(bits,v6){const w=v6?128:32;const m=[];if(bits>w)
return null;for(let i=0;i<w/16;i++){const b=Math.min(16,bits);m.push((0xffff<<(16-b))&0xffff);bits-=b;}
if(v6)
return String.prototype.format.apply('%x:%x:%x:%x:%x:%x:%x:%x',m).replace(/:0(?::0)+$/,'::');else
return'%d.%d.%d.%d'.format(m[0]>>>8,m[0]&0xff,m[1]>>>8,m[1]&0xff);}
function maskToPrefix(mask,v6){const m=v6?validation.parseIPv6(mask):validation.parseIPv4(mask);if(!m)
return null;let bits=0;for(let i=0,z=false;i<m.length;i++){z=z||!m[i];while(!z&&(m[i]&(v6?0x8000:0x80))){m[i]=(m[i]<<1)&(v6?0xffff:0xff);bits++;}
if(m[i])
return null;}
return bits;}
function initNetworkState(refresh){if(_state==null||refresh){const hasWifi=L.hasSystemFeature('wifi');if(refresh||!_init){_init=Promise.all([L.resolveDefault(callNetworkInterfaceDump(),[]),L.resolveDefault(callLuciBoardJSON(),{}),L.resolveDefault(callLuciNetworkDevices(),{}),L.resolveDefault(callLuciWirelessDevices(),{}),L.resolveDefault(callLuciHostHints(),{}),getProtocolHandlers(),L.resolveDefault(uci.load('network')),hasWifi?L.resolveDefault(uci.load('wireless')):L.resolveDefault(),L.resolveDefault(uci.load('luci'))]).then(function([netifd_ifaces,board_json,luci_devs,radios,hosts]){const s={isTunnel:{},isBridge:{},isSwitch:{},isWifi:{},ifaces:netifd_ifaces,radios:radios,hosts:hosts,netdevs:{},bridges:{},switches:{},hostapd:{}};for(let name in luci_devs){const dev=luci_devs[name];if(isVirtualIfname(name))
s.isTunnel[name]=true;if(!s.isTunnel[name]&&isIgnoredIfname(name))
continue;s.netdevs[name]=s.netdevs[name]||{idx:dev.ifindex,name:name,rawname:name,flags:dev.flags,link:dev.link,stats:dev.stats,macaddr:dev.mac,pse:dev?.pse,type:dev.type,devtype:dev.devtype,mtu:dev.mtu,qlen:dev.qlen,wireless:dev.wireless,parent:dev.parent,ipaddrs:[],ip6addrs:[]};if(Array.isArray(dev.ipaddrs))
for(let ip of dev.ipaddrs)
s.netdevs[name].ipaddrs.push(ip.address+'/'+ip.netmask);if(Array.isArray(dev.ip6addrs))
for(let ip6 of dev.ip6addrs)
s.netdevs[name].ip6addrs.push(ip6.address+'/'+ip6.netmask);}
for(let name in luci_devs){const dev=luci_devs[name];if(!dev.bridge)
continue;const b={name:name,id:dev.id,stp:dev.stp,ifnames:[]};for(let port of dev.ports){const subdev=s.netdevs[port];if(subdev==null)
continue;b.ifnames.push(subdev);subdev.bridge=b;}
s.bridges[name]=b;s.isBridge[name]=true;}
for(let name in luci_devs){const dev=luci_devs[name];if(!dev.parent||dev.devtype!='dsa')
continue;s.isSwitch[dev.parent]=true;s.isSwitch[name]=true;}
if(L.isObject(board_json.switch)){for(let switchname in board_json.switch){const layout=board_json.switch[switchname];const netdevs={};const nports={};const ports=[];let pnum=null;let role=null;if(L.isObject(layout)&&Array.isArray(layout.ports)){for(let port of layout.ports){if(typeof(port)=='object'&&typeof(port.num)=='number'&&(typeof(port.role)=='string'||typeof(port.device)=='string')){const spec={num:port.num,role:port.role||'cpu',index:(port.index!=null)?port.index:port.num};if(port.device!=null){spec.device=port.device;spec.tagged=spec.need_tag;netdevs[port.num]=port.device;}
ports.push(spec);if(port.role!=null)
nports[port.role]=(nports[port.role]||0)+1;}}
ports.sort(function(a,b){return L.naturalCompare(a.role,b.role)||L.naturalCompare(a.index,b.index);});for(let port of ports){if(port.role!=role){role=port.role;pnum=1;}
if(role=='cpu')
port.label='CPU (%s)'.format(port.device);else if(nports[role]>1)
port.label='%s %d'.format(role.toUpperCase(),pnum++);else
port.label=role.toUpperCase();delete port.role;delete port.index;}
s.switches[switchname]={ports:ports,netdevs:netdevs};}}}
if(L.isObject(board_json.dsl)&&L.isObject(board_json.dsl.modem)){s.hasDSLModem=board_json.dsl.modem;}
_init=null;const objects=[];if(L.isObject(s.radios))
for(let radio in s.radios)
if(L.isObject(s.radios[radio])&&Array.isArray(s.radios[radio].interfaces))
for(let ri of s.radios[radio].interfaces)
if(L.isObject(ri)&&ri.ifname)
objects.push('hostapd.%s'.format(ri.ifname));return(objects.length?L.resolveDefault(rpc.list.apply(rpc,objects),{}):Promise.resolve({})).then(function(res){for(let k in res){const m=k.match(/^hostapd\.(.+)$/);if(m)
s.hostapd[m[1]]=res[k];}
return(_state=s);});});}}
if(refresh)
return _init;return(_state!=null?Promise.resolve(_state):_init);}
function ifnameOf(obj){if(obj instanceof Protocol)
return obj.getIfname();else if(obj instanceof Device)
return obj.getName();else if(obj instanceof WifiDevice)
return obj.getName();else if(obj instanceof WifiNetwork)
return obj.getIfname();else if(typeof(obj)=='string')
return obj.replace(/:.+$/,'');return null;}
function networkSort(a,b){return L.naturalCompare(a.getName(),b.getName());}
function deviceSort(a,b){const typeWeight={wifi:2,alias:3};return L.naturalCompare(typeWeight[a.getType()]||1,typeWeight[b.getType()]||1)||L.naturalCompare(a.getName(),b.getName());}
function formatWifiEncryption(enc){if(!L.isObject(enc))
return null;if(!enc.enabled)
return'None';const ciphers=Array.isArray(enc.ciphers)?enc.ciphers.map(function(c){return c.toUpperCase()}):['NONE'];if(Array.isArray(enc.wep)){let has_open=false;let has_shared=false;for(let wencr of enc.wep)
if(wencr=='open')
has_open=true;else if(wencr=='shared')
has_shared=true;if(has_open&&has_shared)
return'WEP Open/Shared (%s)'.format(ciphers.join(', '));else if(has_open)
return'WEP Open System (%s)'.format(ciphers.join(', '));else if(has_shared)
return'WEP Shared Auth (%s)'.format(ciphers.join(', '));return'WEP';}
if(Array.isArray(enc.wpa)){const versions=[];const suites=Array.isArray(enc.authentication)?enc.authentication.map(function(a){return a.toUpperCase()}):['NONE'];for(let encr of enc.wpa)
switch(encr){case 1:versions.push('WPA');break;default:versions.push('WPA%d'.format(encr));break;}
if(versions.length>1)
return'mixed %s %s (%s)'.format(versions.join('/'),suites.join(', '),ciphers.join(', '));return'%s %s (%s)'.format(versions[0],suites.join(', '),ciphers.join(', '));}
return'Unknown';}
function enumerateNetworks(){const uciInterfaces=uci.sections('network','interface');const networks={};for(let intf of uciInterfaces)
networks[intf['.name']]=this.instantiateNetwork(intf['.name']);for(let ifstate of _state.ifaces)
if(networks[ifstate.interface]==null)
networks[ifstate.interface]=this.instantiateNetwork(ifstate.interface,ifstate.proto);const rv=[];for(let network in networks)
if(networks.hasOwnProperty(network))
rv.push(networks[network]);rv.sort(networkSort);return rv;}
let Hosts,Network,Protocol,Device,WifiDevice,WifiNetwork,WifiVlan;Network=baseclass.extend({prefixToMask:prefixToMask,maskToPrefix:maskToPrefix,formatWifiEncryption:formatWifiEncryption,flushCache(){initNetworkState(true);return _init;},getProtocol(protoname,netname){const v=_protocols[protoname];if(v!=null)
return new v(netname||'__dummy__');return null;},getProtocols(){const rv=[];for(let protoname in _protocols)
rv.push(new _protocols[protoname]('__dummy__'));return rv;},registerProtocol(protoname,methods){const spec=L.isObject(_protospecs)?_protospecs[protoname]:null;const proto=Protocol.extend(Object.assign({getI18n(){return protoname;},isFloating(){return false;},isVirtual(){return(L.isObject(spec)&&spec.no_device==true);},renderFormOptions(section){}},methods,{__init__(name){this.sid=name;},getProtocol(){return protoname;}}));_protocols[protoname]=proto;return proto;},registerPatternVirtual(pat){iface_patterns_virtual.push(pat);},registerErrorCode(code,message){if(typeof(code)=='string'&&typeof(message)=='string'&&!proto_errors.hasOwnProperty(code)){proto_errors[code]=message;return true;}
return false;},addNetwork(name,options){return this.getNetwork(name).then(L.bind(function(existingNetwork){if(name!=null&&/^[a-zA-Z0-9_]+$/.test(name)&&existingNetwork==null){const sid=uci.add('network','interface',name);if(sid!=null){if(L.isObject(options))
for(let key in options)
if(options.hasOwnProperty(key))
uci.set('network',sid,key,options[key]);return this.instantiateNetwork(sid);}}
else if(existingNetwork!=null&&existingNetwork.isEmpty()){if(L.isObject(options))
for(let key in options)
if(options.hasOwnProperty(key))
existingNetwork.set(key,options[key]);return existingNetwork;}},this));},getNetwork(name){return initNetworkState().then(L.bind(function(){const section=(name!=null)?uci.get('network',name):null;if(section!=null&&section['.type']=='interface'){return this.instantiateNetwork(name);}
else if(name!=null){for(let ifc of _state.ifaces)
if(ifc.interface==name)
return this.instantiateNetwork(name,ifc.proto);}
return null;},this));},getNetworks(){return initNetworkState().then(L.bind(enumerateNetworks,this));},deleteNetwork(name){const requireFirewall=Promise.resolve(L.require('firewall')).catch(function(){});const loadDHCP=L.resolveDefault(uci.load('dhcp'));const network=this.instantiateNetwork(name);return Promise.all([requireFirewall,loadDHCP,initNetworkState()]).then(function(res){const uciInterface=uci.get('network',name);const firewall=res[0];if(uciInterface!=null&&uciInterface['.type']=='interface'){return Promise.resolve(network?network.deleteConfiguration():null).then(function(){uci.remove('network',name);uci.sections('luci','ifstate',function(s){if(s.interface==name)
uci.remove('luci',s['.name']);});uci.sections('network',null,function(s){switch(s['.type']){case'alias':case'route':case'route6':if(s.interface==name)
uci.remove('network',s['.name']);break;case'rule':case'rule6':if(s.in==name||s.out==name)
uci.remove('network',s['.name']);break;}});uci.sections('wireless','wifi-iface',function(s){const networks=L.toArray(s.network).filter(function(network){return network!=name});if(networks.length>0)
uci.set('wireless',s['.name'],'network',networks.join(' '));else
uci.unset('wireless',s['.name'],'network');});uci.sections('dhcp','dhcp',function(s){if(s.interface==name)
uci.remove('dhcp',s['.name']);});if(firewall)
return firewall.deleteNetwork(name).then(function(){return true});return true;}).catch(function(){return false;});}
return false;});},renameNetwork(oldName,newName){return initNetworkState().then(function(){if(newName==null||!/^[a-zA-Z0-9_]+$/.test(newName)||uci.get('network',newName)!=null)
return false;const oldNetwork=uci.get('network',oldName);if(oldNetwork==null||oldNetwork['.type']!='interface')
return false;const sid=uci.add('network','interface',newName);for(let key in oldNetwork)
if(oldNetwork.hasOwnProperty(key)&&key.charAt(0)!='.')
uci.set('network',sid,key,oldNetwork[key]);uci.sections('luci','ifstate',function(s){if(s.interface==oldName)
uci.set('luci',s['.name'],'interface',newName);});uci.sections('network','alias',function(s){if(s.interface==oldName)
uci.set('network',s['.name'],'interface',newName);});uci.sections('network','route',function(s){if(s.interface==oldName)
uci.set('network',s['.name'],'interface',newName);});uci.sections('network','route6',function(s){if(s.interface==oldName)
uci.set('network',s['.name'],'interface',newName);});uci.sections('wireless','wifi-iface',function(s){const networks=L.toArray(s.network).map(function(network){return(network==oldName?newName:network)});if(networks.length>0)
uci.set('wireless',s['.name'],'network',networks.join(' '));});uci.remove('network',oldName);return true;});},getDevice(name){return initNetworkState().then(L.bind(function(){if(name==null)
return null;if(_state.netdevs.hasOwnProperty(name))
return this.instantiateDevice(name);const netid=getWifiNetidBySid(name);if(netid!=null)
return this.instantiateDevice(netid[0]);return null;},this));},getDevices(){return initNetworkState().then(L.bind(function(){const devices={};const uciInterfaces=uci.sections('network','interface');for(let uif of uciInterfaces){const ifnames=L.toArray(uif.ifname);for(let ifn of ifnames){if(ifn.charAt(0)=='@')
continue;if(isIgnoredIfname(ifn)||isVirtualIfname(ifn)||isWifiIfname(ifn))
continue;devices[ifn]=this.instantiateDevice(ifn);}}
for(let ifname in _state.netdevs){if(devices.hasOwnProperty(ifname))
continue;if(isIgnoredIfname(ifname)||isWifiIfname(ifname))
continue;if(_state.netdevs[ifname].wireless)
continue;devices[ifname]=this.instantiateDevice(ifname);}
const uciSwitchVLANs=uci.sections('network','switch_vlan');for(let sw of uciSwitchVLANs){if(typeof(sw.ports)!='string'||typeof(sw.device)!='string'||!_state.switches.hasOwnProperty(sw.device))
continue;const ports=sw.ports.split(/\s+/);for(let p of ports){let m=p.match(/^(\d+)([tu]?)$/);if(m==null)
continue;let netdev=_state.switches[sw.device].netdevs[m[1]];if(netdev==null)
continue;if(!devices.hasOwnProperty(netdev))
devices[netdev]=this.instantiateDevice(netdev);_state.isSwitch[netdev]=true;if(m[2]!='t')
continue;let vid=sw.vid||sw.vlan;vid=(vid!=null?+vid:null);if(vid==null||vid<0||vid>4095)
continue;const vlandev='%s.%d'.format(netdev,vid);if(!devices.hasOwnProperty(vlandev))
devices[vlandev]=this.instantiateDevice(vlandev);_state.isSwitch[vlandev]=true;}}
const uciBridgeVLANs=uci.sections('network','bridge-vlan');for(let bvl of uciBridgeVLANs){const basedev=bvl.device;const local=bvl.local;const alias=bvl.alias;const vid=+bvl.vlan;const ports=L.toArray(bvl.ports);if(local=='0')
continue;if(isNaN(vid)||vid<0||vid>4095)
continue;const vlandev='%s.%s'.format(basedev,alias||vid);_state.isBridge[basedev]=true;if(!_state.bridges.hasOwnProperty(basedev))
_state.bridges[basedev]={name:basedev,ifnames:[]};if(!devices.hasOwnProperty(vlandev))
devices[vlandev]=this.instantiateDevice(vlandev);ports.forEach(function(port_name){const m=port_name.match(/^([^:]+)(?::[ut*]+)?$/);const p=m?m[1]:null;if(!p)
return;if(_state.bridges[basedev].ifnames.filter(function(sd){return sd.name==p}).length)
return;_state.netdevs[p]=_state.netdevs[p]||{name:p,ipaddrs:[],ip6addrs:[],type:1,devtype:'ethernet',stats:{},flags:{}};_state.bridges[basedev].ifnames.push(_state.netdevs[p]);_state.netdevs[p].bridge=_state.bridges[basedev];});}
const uciWifiIfaces=uci.sections('wireless','wifi-iface');const networkCount={};for(let wf_if of uciWifiIfaces){if(typeof(wf_if.device)!='string')
continue;networkCount[wf_if.device]=(networkCount[wf_if.device]||0)+1;const netid='%s.network%d'.format(wf_if.device,networkCount[wf_if.device]);devices[netid]=this.instantiateDevice(netid);}
const uciDevices=uci.sections('network','device');for(let d of uciDevices){const type=d.type;const name=d.name;if(!type||!name||devices.hasOwnProperty(name))
continue;if(type=='bridge')
_state.isBridge[name]=true;devices[name]=this.instantiateDevice(name);}
const rv=[];for(let netdev in devices)
if(devices.hasOwnProperty(netdev))
rv.push(devices[netdev]);rv.sort(deviceSort);return rv;},this));},isIgnoredDevice(name){return isIgnoredIfname(name);},getWifiDevice(devname){return initNetworkState().then(L.bind(function(){const existingDevice=uci.get('wireless',devname);if(existingDevice==null||existingDevice['.type']!='wifi-device')
return null;return this.instantiateWifiDevice(devname,_state.radios[devname]||{});},this));},getWifiDevices(){return initNetworkState().then(L.bind(function(){const uciWifiDevices=uci.sections('wireless','wifi-device');const rv=[];for(let wfd of uciWifiDevices){const devname=wfd['.name'];rv.push(this.instantiateWifiDevice(devname,_state.radios[devname]||{}));}
return rv;},this));},getWifiNetwork(netname){return initNetworkState().then(L.bind(this.lookupWifiNetwork,this,netname));},getWifiNetworks(){return initNetworkState().then(L.bind(function(){const wifiIfaces=uci.sections('wireless','wifi-iface');const rv=[];for(let wf_if of wifiIfaces)
rv.push(this.lookupWifiNetwork(wf_if['.name']));rv.sort(function(a,b){return L.naturalCompare(a.getID(),b.getID());});return rv;},this));},addWifiNetwork(options){return initNetworkState().then(L.bind(function(){if(options==null||typeof(options)!='object'||typeof(options.device)!='string')
return null;const existingDevice=uci.get('wireless',options.device);if(existingDevice==null||existingDevice['.type']!='wifi-device')
return null;const sid=uci.add('wireless','wifi-iface');for(let key in options)
if(options.hasOwnProperty(key))
uci.set('wireless',sid,key,options[key]);const radioname=existingDevice['.name'];const netid=getWifiNetidBySid(sid)||[];return this.instantiateWifiNetwork(sid,radioname,_state.radios[radioname],netid[0],null);},this));},deleteWifiNetwork(netname){return initNetworkState().then(L.bind(function(){const sid=getWifiSidByIfname(netname);if(sid==null)
return false;uci.remove('wireless',sid);return true;},this));},getStatusByRoute(addr,mask){return initNetworkState().then(L.bind(function(){const rv=[];for(let sif of _state.ifaces){if(!Array.isArray(sif.route))
continue;for(let sifr of sif.route){if(typeof(sifr)!='object'||typeof(sifr.target)!='string'||typeof(sifr.mask)!='number')
continue;if(sifr.table)
continue;if(sifr.target!=addr||sifr.mask!=mask)
continue;rv.push(sif);}}
rv.sort(function(a,b){return L.naturalCompare(a.metric,b.metric)||L.naturalCompare(a.interface,b.interface);});return rv;},this));},getStatusByAddress(addr){return initNetworkState().then(L.bind(function(){for(let sif of _state.ifaces){if(Array.isArray(sif['ipv4-address']))
for(let a of sif['ipv4-address'])
if(typeof(a)=='object'&&a.address==addr)
return sif;if(Array.isArray(sif['ipv6-address']))
for(let a of sif['ipv6-address'])
if(typeof(a)=='object'&&a.address==addr)
return sif;if(Array.isArray(sif['ipv6-prefix-assignment']))
for(let a of sif['ipv6-prefix-assignment'])
if(typeof(a)=='object'&&typeof(a['local-address'])=='object'&&a['local-address'].address==addr)
return sif;}
return null;},this));},getWANNetworks(){return this.getStatusByRoute('0.0.0.0',0).then(L.bind(function(statuses){const rv=[],seen={};for(let s of statuses){if(!seen.hasOwnProperty(s.interface)){rv.push(this.instantiateNetwork(s.interface,s.proto));seen[s.interface]=true;}}
return rv;},this));},getWAN6Networks(){return this.getStatusByRoute('::',0).then(L.bind(function(statuses){const rv=[],seen={};for(let s of statuses){if(!seen.hasOwnProperty(s.interface)){rv.push(this.instantiateNetwork(s.interface,s.proto));seen[s.interface]=true;}}
return rv;},this));},getSwitchTopologies(){return initNetworkState().then(function(){return _state.switches;});},instantiateNetwork(name,proto){if(name==null)
return null;proto=(proto==null?(uci.get('network',name,'proto')||'none'):proto);const protoClass=_protocols[proto]||Protocol;return new protoClass(name);},instantiateDevice(name,network,extend){if(extend!=null)
return new(Device.extend(extend))(name,network);return new Device(name,network);},instantiateWifiDevice(radioname,radiostate){return new WifiDevice(radioname,radiostate);},instantiateWifiNetwork(sid,radioname,radiostate,netid,netstate,hostapd){return new WifiNetwork(sid,radioname,radiostate,netid,netstate,hostapd);},lookupWifiNetwork(netname){let sid,res,netid,radioname,radiostate,netstate;sid=getWifiSidByNetid(netname);if(sid!=null){res=getWifiStateBySid(sid);netid=netname;radioname=res?res[0]:null;radiostate=res?res[1]:null;netstate=res?res[2]:null;}
else{res=getWifiStateByIfname(netname);if(res!=null){radioname=res[0];radiostate=res[1];netstate=res[2];sid=netstate.section;netid=L.toArray(getWifiNetidBySid(sid))[0];}
else{res=getWifiStateBySid(netname);if(res!=null){radioname=res[0];radiostate=res[1];netstate=res[2];sid=netname;netid=L.toArray(getWifiNetidBySid(sid))[0];}
else{res=getWifiNetidBySid(netname);if(res!=null){netid=res[0];radioname=res[1];sid=netname;}}}}
return this.instantiateWifiNetwork(sid||netname,radioname,radiostate,netid,netstate,netstate?_state.hostapd[netstate.ifname]:null);},getIfnameOf(obj){return ifnameOf(obj);},getDSLModemType(){return initNetworkState().then(function(){return _state.hasDSLModem?_state.hasDSLModem.type:null;});},getHostHints(){return initNetworkState().then(function(){return new Hosts(_state.hosts);});}});Hosts=baseclass.extend({__init__(hosts){this.hosts=hosts;},getHostnameByMACAddr(mac){return this.hosts[mac]?(this.hosts[mac].name||null):null;},getIPAddrByMACAddr(mac){return this.hosts[mac]?(L.toArray(this.hosts[mac].ipaddrs||this.hosts[mac].ipv4)[0]||null):null;},getIP6AddrByMACAddr(mac){return this.hosts[mac]?(L.toArray(this.hosts[mac].ip6addrs||this.hosts[mac].ipv6)[0]||null):null;},getHostnameByIPAddr(ipaddr){for(let mac in this.hosts){if(this.hosts[mac].name==null)
continue;const addrs=L.toArray(this.hosts[mac].ipaddrs||this.hosts[mac].ipv4);for(let a of addrs)
if(a==ipaddr)
return this.hosts[mac].name;}
return null;},getMACAddrByIPAddr(ipaddr){for(let mac in this.hosts){const addrs=L.toArray(this.hosts[mac].ipaddrs||this.hosts[mac].ipv4);for(let a of addrs)
if(a==ipaddr)
return mac;}
return null;},getHostnameByIP6Addr(ip6addr){for(let mac in this.hosts){if(this.hosts[mac].name==null)
continue;const addrs=L.toArray(this.hosts[mac].ip6addrs||this.hosts[mac].ipv6);for(let a of addrs)
if(a==ip6addr)
return this.hosts[mac].name;}
return null;},getMACAddrByIP6Addr(ip6addr){for(let mac in this.hosts){const addrs=L.toArray(this.hosts[mac].ip6addrs||this.hosts[mac].ipv6);for(let a of addrs)
if(a==ip6addr)
return mac;}
return null;},getMACHints(preferIp6){const rv=[];for(let mac in this.hosts){const hint=this.hosts[mac].name||L.toArray(this.hosts[mac][preferIp6?'ip6addrs':'ipaddrs']||this.hosts[mac][preferIp6?'ipv6':'ipv4'])[0]||L.toArray(this.hosts[mac][preferIp6?'ipaddrs':'ip6addrs']||this.hosts[mac][preferIp6?'ipv4':'ipv6'])[0];rv.push([mac,hint]);}
return rv.sort(function(a,b){return L.naturalCompare(a[0],b[0]);});}});Protocol=baseclass.extend({__init__(name){this.sid=name;},_get(opt){const val=uci.get('network',this.sid,opt);if(Array.isArray(val))
return val.join(' ');return val||'';},_ubus(field){for(let sif of _state.ifaces){if(sif.interface!=this.sid)
continue;return(field!=null?sif[field]:sif);}},get(opt){return uci.get('network',this.sid,opt);},set(opt,val){return uci.set('network',this.sid,opt,val);},getIfname(){let ifname;if(this.isFloating())
ifname=this._ubus('l3_device');else
ifname=this._ubus('device')||this._ubus('l3_device');if(ifname!=null)
return ifname;const res=getWifiNetidByNetname(this.sid);return(res!=null?res[0]:null);},getProtocol(){return null;},getI18n(){switch(this.getProtocol()){case'none':return _('Unmanaged');case'static':return _('Static address');case'dhcp':return _('DHCP client');default:return _('Unknown');}},getType(){return this._get('type');},getName(){return this.sid;},getUptime(){return this._ubus('uptime')||0;},getExpiry(){const u=this._ubus('uptime');const d=this._ubus('data');const v6_prefixes=this._ubus('ipv6-prefix');const v6_addresses=this._ubus('ipv6-address');if(typeof(u)=='number'&&d!=null){if(typeof(d)=='object'&&typeof(d.leasetime)=='number'){const r=d.leasetime-(u%d.leasetime);return(r>0?r:0);}
if(Array.isArray(v6_prefixes)||Array.isArray(v6_addresses)){const prefixes=[...v6_prefixes,...v6_addresses];if(prefixes.length&&typeof(prefixes[0].valid)=='number'){const r=prefixes[0].valid;return(r>0?r:0);}}}
return-1;},getMetric(){return this._ubus('metric')||0;},getZoneName(){const d=this._ubus('data');if(L.isObject(d)&&typeof(d.zone)=='string')
return d.zone;return null;},getIPAddr(){const addrs=this._ubus('ipv4-address');return((Array.isArray(addrs)&&addrs.length)?addrs[0].address:null);},getIPAddrs(){const addrs=this._ubus('ipv4-address');const rv=[];if(Array.isArray(addrs))
for(let a of addrs)
rv.push('%s/%d'.format(a.address,a.mask));return rv;},getNetmask(){const addrs=this._ubus('ipv4-address');if(Array.isArray(addrs)&&addrs.length)
return prefixToMask(addrs[0].mask,false);},getGatewayAddr(){const routes=this._ubus('route');if(Array.isArray(routes))
for(let r of routes)
if(typeof(r)=='object'&&r.target=='0.0.0.0'&&r.mask==0)
return r.nexthop;return null;},getDNSAddrs(){const addrs=this._ubus('dns-server');const rv=[];if(Array.isArray(addrs))
for(let a of addrs)
if(!/:/.test(a))
rv.push(a);return rv;},getIP6Addr(){let addrs=this._ubus('ipv6-address');if(Array.isArray(addrs)&&L.isObject(addrs[0]))
return'%s/%d'.format(addrs[0].address,addrs[0].mask);addrs=this._ubus('ipv6-prefix-assignment');if(Array.isArray(addrs)&&L.isObject(addrs[0])&&L.isObject(addrs[0]['local-address']))
return'%s/%d'.format(addrs[0]['local-address'].address,addrs[0]['local-address'].mask);return null;},getIP6Addrs(){let addrs=this._ubus('ipv6-address');const rv=new Set();if(Array.isArray(addrs))
for(let a of addrs)
if(L.isObject(a))
rv.add('%s/%d'.format(a.address,a.mask));addrs=this._ubus('ipv6-prefix-assignment');if(Array.isArray(addrs))
for(let a of addrs)
if(L.isObject(a)&&L.isObject(a['local-address']))
rv.add('%s/%d'.format(a['local-address'].address,a['local-address'].mask));return Array.from(rv);},getGateway6Addr(){const routes=this._ubus('route');if(Array.isArray(routes))
for(let r of routes)
if(typeof(r)=='object'&&r.target=='::'&&r.mask==0)
return r.nexthop;return null;},getDNS6Addrs(){const addrs=this._ubus('dns-server');const rv=[];if(Array.isArray(addrs))
for(let a of addrs)
if(/:/.test(a))
rv.push(a);return rv;},getIP6Prefix(){const prefixes=this._ubus('ipv6-prefix');if(Array.isArray(prefixes)&&L.isObject(prefixes[0]))
return'%s/%d'.format(prefixes[0].address,prefixes[0].mask);return null;},getIP6Prefixes(){const prefixes=this._ubus('ipv6-prefix');const rv=[];if(Array.isArray(prefixes))
for(let p of prefixes)
if(L.isObject(p))
rv.push('%s/%d'.format(p.address,p.mask));return rv.length>0?rv:null;},getErrors(){const errors=this._ubus('errors');let rv=null;if(Array.isArray(errors)){for(let e of errors){if(!L.isObject(e)||typeof(e.code)!='string')
continue;rv=rv||[];rv.push(proto_errors[e.code]||_('Unknown error (%s)').format(e.code));}}
return rv;},isBridge(){return(!this.isVirtual()&&this.getType()=='bridge');},getPackageName(){return null;},isCreateable(ifname){return Promise.resolve(null);},isInstalled(){return true;},isVirtual(){return false;},isFloating(){return false;},isDynamic(){return(this._ubus('dynamic')==true);},isPending(){return(this._ubus('pending')==true);},isAlias(){const ifnames=L.toArray(uci.get('network',this.sid,'device'));let parent=null;for(let ifn of ifnames)
if(ifn.charAt(0)=='@')
parent=ifn.substr(1);else if(parent!=null)
parent=null;return parent;},isEmpty(){if(this.isFloating())
return false;let empty=true;const device=this._get('device');if(device!=null&&device.match(/\S+/))
empty=false;if(empty==true&&getWifiNetidBySid(this.sid)!=null)
empty=false;return empty;},isUp(){return(this._ubus('up')==true);},addDevice(device){device=ifnameOf(device);if(device==null||this.isFloating())
return false;const wif=getWifiSidByIfname(device);if(wif!=null)
return appendValue('wireless',wif,'network',this.sid);return appendValue('network',this.sid,'device',device);},deleteDevice(device){let rv=false;device=ifnameOf(device);if(device==null||this.isFloating())
return false;const wif=getWifiSidByIfname(device);if(wif!=null)
rv=removeValue('wireless',wif,'network',this.sid);if(removeValue('network',this.sid,'device',device))
rv=true;return rv;},getDevice(){if(this.isVirtual()){const ifname='%s-%s'.format(this.getProtocol(),this.sid);_state.isTunnel[this.getProtocol()+'-'+this.sid]=true;return Network.prototype.instantiateDevice(ifname,this);}
else if(this.isBridge()){const ifname='br-%s'.format(this.sid);_state.isBridge[ifname]=true;return new Device(ifname,this);}
else{const ifnames=L.toArray(uci.get('network',this.sid,'device'));for(let ifn of ifnames){const m=ifn.match(/^([^:/]+)/);return((m&&m[1])?Network.prototype.instantiateDevice(m[1],this):null);}
const ifname=getWifiNetidByNetname(this.sid);return(ifname!=null?Network.prototype.instantiateDevice(ifname[0],this):null);}},getL2Device(){const ifname=this._ubus('device');return(ifname!=null?Network.prototype.instantiateDevice(ifname,this):null);},getL3Device(){const ifname=this._ubus('l3_device');return(ifname!=null?Network.prototype.instantiateDevice(ifname,this):null);},getDevices(){const rv=[];if(!this.isBridge()&&!(this.isVirtual()&&!this.isFloating()))
return null;const device=uci.get('network',this.sid,'device');if(device&&device.charAt(0)!='@'){const m=device.match(/^([^:/]+)/);if(m!=null)
rv.push(Network.prototype.instantiateDevice(m[1],this));}
const uciWifiIfaces=uci.sections('wireless','wifi-iface');for(let wf_if of uciWifiIfaces){if(typeof(wf_if.device)!='string')
continue;const networks=L.toArray(wf_if.network);for(let n of networks){if(n!=this.sid)
continue;const netid=getWifiNetidBySid(wf_if['.name']);if(netid!=null)
rv.push(Network.prototype.instantiateDevice(netid[0],this));}}
rv.sort(deviceSort);return rv;},containsDevice(device){device=ifnameOf(device);if(device==null)
return false;else if(this.isVirtual()&&'%s-%s'.format(this.getProtocol(),this.sid)==device)
return true;else if(this.isBridge()&&'br-%s'.format(this.sid)==device)
return true;const name=uci.get('network',this.sid,'device');if(name){const m=name.match(/^([^:/]+)/);if(m!=null&&m[1]==device)
return true;}
const wif=getWifiSidByIfname(device);if(wif!=null){const networks=L.toArray(uci.get('wireless',wif,'network'));for(let n of networks)
if(n==this.sid)
return true;}
return false;},deleteConfiguration(){}});Device=baseclass.extend({__init__(device,network){const wif=getWifiSidByIfname(device);if(wif!=null){const res=getWifiStateBySid(wif)||[];const netid=getWifiNetidBySid(wif)||[];this.wif=new WifiNetwork(wif,res[0],res[1],netid[0],res[2],{ifname:device});this.device=this.wif.getIfname();}
this.device=this.device||device;this.dev=Object.assign({},_state.netdevs[this.device]);this.network=network;let conf;uci.sections('network','device',function(s){if(s.name==device)
conf=s;});this.config=Object.assign({},conf);},_devstate(){let rv=this.dev;for(let a of arguments)
if(L.isObject(rv))
rv=rv[a];else
return null;return rv;},getName(){return(this.wif!=null?this.wif.getIfname():this.device);},getMAC(){const mac=this._devstate('macaddr');return mac?mac.toUpperCase():null;},getMTU(){return this._devstate('mtu');},getIPAddrs(){const addrs=this._devstate('ipaddrs');return(Array.isArray(addrs)?addrs:[]);},getIP6Addrs(){const addrs=this._devstate('ip6addrs');return(Array.isArray(addrs)?addrs:[]);},getType(){if(this.device!=null&&this.device.charAt(0)=='@')
return'alias';else if(this.dev.devtype=='wlan'||this.wif!=null||isWifiIfname(this.device))
return'wifi';else if(this.dev.devtype=='bridge'||_state.isBridge[this.device])
return'bridge';else if(this.dev.devtype=='wireguard')
return'wireguard';else if(_state.isTunnel[this.device])
return'tunnel';else if(this.dev.devtype=='vlan'||this.device.indexOf('.')>-1)
return'vlan';else if(this.dev.devtype=='dsa'||_state.isSwitch[this.device])
return'switch';else if(this.config.type=='8021q'||this.config.type=='8021ad')
return'vlan';else if(this.config.type=='bridge')
return'bridge';else if(this.config.type=='vrf')
return'vrf';else
return'ethernet';},getShortName(){if(this.wif!=null)
return this.wif.getShortName();return this.device;},getI18n(){if(this.wif!=null){return'%s: %s "%s"'.format(_('Wireless Network'),this.wif.getActiveMode(),this.wif.getActiveSSID()||this.wif.getActiveBSSID()||this.wif.getID()||'?');}
return'%s: "%s"'.format(this.getTypeI18n(),this.getName());},getTypeI18n(){switch(this.getType()){case'alias':return _('Alias Interface');case'wifi':return _('Wireless Adapter');case'bridge':return _('Bridge');case'vrf':return _('Virtual Routing and Forwarding (VRF)');case'switch':return(_state.netdevs[this.device]&&_state.netdevs[this.device].devtype=='dsa')?_('Switch port'):_('Ethernet Switch');case'vlan':return(_state.isSwitch[this.device]?_('Switch VLAN'):_('Software VLAN'));case'wireguard':return _('WireGuard Interface');case'tunnel':return _('Tunnel Interface');default:return _('Ethernet Adapter');}},getPorts(){const br=_state.bridges[this.device];const rv=[];if(br==null||!Array.isArray(br.ifnames))
return null;for(let ifn of br.ifnames)
rv.push(Network.prototype.instantiateDevice(ifn.name));rv.sort(deviceSort);return rv;},getBridgeID(){const br=_state.bridges[this.device];return(br!=null?br.id:null);},getBridgeSTP(){const br=_state.bridges[this.device];return(br!=null?!!br.stp:false);},isUp(){let up=this._devstate('flags','up');if(up==null)
up=(this.getType()=='alias');return up;},isBridge(){return(this.getType()=='bridge');},isBridgePort(){return(this._devstate('bridge')!=null);},getTXBytes(){const stat=this._devstate('stats');return(stat!=null?stat.tx_bytes||0:0);},getRXBytes(){const stat=this._devstate('stats');return(stat!=null?stat.rx_bytes||0:0);},getTXPackets(){const stat=this._devstate('stats');return(stat!=null?stat.tx_packets||0:0);},getRXPackets(){const stat=this._devstate('stats');return(stat!=null?stat.rx_packets||0:0);},getCarrier(){const link=this._devstate('link');return(link!=null?link.carrier||false:false);},getSpeed(){const link=this._devstate('link');return(link!=null?link.speed||null:null);},getDuplex(){const link=this._devstate('link');const duplex=link?link.duplex:null;return(duplex!='unknown')?duplex:null;},getPSE(){const pse=this._devstate('pse');if(!pse)
return null;return{c33AdminState:pse['c33-admin-state']||null,c33PowerStatus:pse['c33-power-status']||null,c33PowerClass:pse['c33-power-class']||null,c33ActualPower:pse['c33-actual-power']||null,c33AvailablePowerLimit:pse['c33-available-power-limit']||null,podlAdminState:pse['podl-admin-state']||null,podlPowerStatus:pse['podl-power-status']||null,priority:pse['priority']||null,priorityMax:pse['priority-max']||null};},hasPSE(){return this._devstate('pse')!=null;},getNetwork(){return this.getNetworks()[0];},getNetworks(){if(this.networks==null){this.networks=[];const networks=enumerateNetworks.apply(L.network);for(let n of networks)
if(n.containsDevice(this.device)||n.getIfname()==this.device)
this.networks.push(n);this.networks.sort(networkSort);}
return this.networks;},getWifiNetwork(){return(this.wif!=null?this.wif:null);},getParent(){if(this.dev.parent)
return Network.prototype.instantiateDevice(this.dev.parent);if((this.config.type=='8021q'||this.config.type=='802ad')&&typeof(this.config.ifname)=='string')
return Network.prototype.instantiateDevice(this.config.ifname);return null;}});WifiDevice=baseclass.extend({__init__(name,radiostate){const uciWifiDevice=uci.get('wireless',name);if(uciWifiDevice!=null&&uciWifiDevice['.type']=='wifi-device'&&uciWifiDevice['.name']!=null){this.sid=uciWifiDevice['.name'];}
this.sid=this.sid||name;this._ubusdata={radio:name,dev:radiostate};},ubus(){let v=this._ubusdata;for(let a of arguments)
if(L.isObject(v))
v=v[a];else
return null;return v;},get(opt){return uci.get('wireless',this.sid,opt);},set(opt,value){return uci.set('wireless',this.sid,opt,value);},isDisabled(){return this.ubus('dev','disabled')||this.get('disabled')=='1';},getName(){return this.sid;},getHWModes(){const hwmodes=this.ubus('dev','iwinfo','hwmodes');return Array.isArray(hwmodes)?hwmodes:['b','g'];},getHTModes(){const htmodes=this.ubus('dev','iwinfo','htmodes');return(Array.isArray(htmodes)&&htmodes.length)?htmodes:null;},getI18n(){const hw=this.ubus('dev','iwinfo','hardware');let type=L.isObject(hw)?hw.name:null;const modes=this.ubus('dev','iwinfo','hwmodes_text');if(this.ubus('dev','iwinfo','type')=='wl')
type='Broadcom';return'%s %s Wireless Controller (%s)'.format(type||'Generic',modes?'802.11'+modes:'unknown',this.getName());},getScanList(){return callIwinfoScan(this.sid);},isUp(){if(L.isObject(_state.radios[this.sid]))
return(_state.radios[this.sid].up==true);return false;},getWifiNetwork(network){return Network.prototype.getWifiNetwork(network).then(L.bind(function(networkInstance){const uciWifiIface=(networkInstance.sid?uci.get('wireless',networkInstance.sid):null);if(uciWifiIface==null||uciWifiIface['.type']!='wifi-iface'||uciWifiIface.device!=this.sid)
return Promise.reject();return networkInstance;},this));},getWifiNetworks(){return Network.prototype.getWifiNetworks().then(L.bind(function(networks){const rv=[];for(let n of networks)
if(n.getWifiDeviceName()==this.getName())
rv.push(n);return rv;},this));},addWifiNetwork(options){if(!L.isObject(options))
options={};options.device=this.sid;return Network.prototype.addWifiNetwork(options);},deleteWifiNetwork(network){let sid=null;if(network instanceof WifiNetwork){sid=network.sid;}
else{const uciWifiIface=uci.get('wireless',network);if(uciWifiIface==null||uciWifiIface['.type']!='wifi-iface')
sid=getWifiSidByIfname(network);}
if(sid==null||uci.get('wireless',sid,'device')!=this.sid)
return Promise.resolve(false);uci.remove('wireless',sid);return Promise.resolve(true);}});WifiNetwork=baseclass.extend({__init__(sid,radioname,radiostate,netid,netstate,hostapd){this.sid=sid;this.netid=netid;this._ubusdata={hostapd:hostapd,radio:radioname,dev:radiostate,net:netstate};},ubus(){let v=this._ubusdata;for(let a of arguments)
if(L.isObject(v))
v=v[a];else
return null;return v;},get(opt){return uci.get('wireless',this.sid,opt);},set(opt,value){return uci.set('wireless',this.sid,opt,value);},isDisabled(){return this.ubus('dev','disabled')||this.get('disabled')=='1';},getMode(){return this.ubus('net','config','mode')||this.get('mode')||'ap';},getSSID(){if(this.getMode()=='mesh')
return null;return this.ubus('net','config','ssid')||this.get('ssid');},getMeshID(){if(this.getMode()!='mesh')
return null;return this.ubus('net','config','mesh_id')||this.get('mesh_id');},getBSSID(){return this.ubus('net','config','bssid')||this.get('bssid');},getNetworkNames(){return L.toArray(this.ubus('net','config','network')||this.get('network'));},getID(){return this.netid;},getName(){return this.sid;},getIfname(){let ifname=this.ubus('net','ifname')||this.ubus('net','iwinfo','ifname');if(ifname==null||ifname.match(/^(wifi|radio)\d/))
ifname=this.netid;return ifname;},getVlanIfnames(){const vlans=L.toArray(this.ubus('net','vlans'));const ifnames=[];for(let v of vlans)
ifnames.push(v['ifname']);return ifnames;},getWifiDeviceName(){return this.ubus('radio')||this.get('device');},getWifiDevice(){const radioname=this.getWifiDeviceName();if(radioname==null)
return Promise.reject();return Network.prototype.getWifiDevice(radioname);},isUp(){const device=this.getDevice();if(device==null)
return false;return device.isUp();},getActiveMode(){const mode=this.ubus('net','iwinfo','mode')||this.getMode();switch(mode){case'ap':return'Master';case'sta':return'Client';case'adhoc':return'Ad-Hoc';case'mesh':return'Mesh Point';case'monitor':return'Monitor';default:return mode;}},getActiveModeI18n(){const mode=this.getActiveMode();switch(mode){case'Master':return _('Access Point');case'Ad-Hoc':return _('Ad-Hoc');case'Client':return _('Client');case'Monitor':return _('Monitor');case'Master(VLAN)':return _('Master (VLAN)');case'WDS':return _('WDS');case'Mesh Point':return _('Mesh Point');case'P2P Client':return _('P2P Client');case'P2P Go':return _('P2P Go');case'Unknown':return _('Unknown');default:return mode;}},getActiveSSID(){return this.ubus('net','iwinfo','ssid')||this.ubus('net','config','ssid')||this.get('ssid');},getActiveBSSID(){return this.ubus('net','iwinfo','bssid')||this.ubus('net','config','bssid')||this.get('bssid');},getActiveEncryption(){return formatWifiEncryption(this.ubus('net','iwinfo','encryption'))||'-';},getAssocList(){const tasks=[];let station;for(let vlan of this.getVlans())
tasks.push(callIwinfoAssoclist(vlan.getIfname()).then(function(stations){for(station of stations)
station.vlan=vlan;return stations;}));tasks.push(callIwinfoAssoclist(this.getIfname()));return Promise.all(tasks).then(function(values){return Array.prototype.concat.apply([],values);});},getVlans(){const vlans=[];const vlans_ubus=this.ubus('net','vlans');if(vlans_ubus)
for(let vlan of vlans_ubus)
vlans.push(new WifiVlan(vlan));return vlans;},getFrequency(){const freq=this.ubus('net','iwinfo','frequency');if(freq!=null&&freq>0)
return'%.03f'.format(freq/1000);return null;},getBitRate(){const rate=this.ubus('net','iwinfo','bitrate');if(rate!=null&&rate>0)
return(rate/1000);return null;},getChannel(){return this.ubus('net','iwinfo','channel')||this.ubus('dev','config','channel')||this.get('channel');},getSignal(){return this.ubus('net','iwinfo','signal')||0;},getNoise(){return this.ubus('net','iwinfo','noise')||0;},getCountryCode(){return this.ubus('net','iwinfo','country')||this.ubus('dev','config','country')||'00';},getTXPower(){return this.ubus('net','iwinfo','txpower');},getTXPowerOffset(){return this.ubus('net','iwinfo','txpower_offset')||0;},getSignalLevel(signal,noise){if(this.getActiveBSSID()=='00:00:00:00:00:00')
return-1;signal=signal||this.getSignal();noise=noise||this.getNoise();if(signal<0&&noise<0){const snr=-1*(noise-signal);return Math.floor(snr/5);}
return 0;},getSignalPercent(){const qc=this.ubus('net','iwinfo','quality')||0;const qm=this.ubus('net','iwinfo','quality_max')||0;if(qc>0&&qm>0)
return Math.floor((100/qm)*qc);return 0;},getShortName(){return'%s "%s"'.format(this.getActiveModeI18n(),this.getActiveSSID()||this.getActiveBSSID()||this.getID());},getI18n(){return'%s: %s "%s" (%s)'.format(_('Wireless Network'),this.getActiveModeI18n(),this.getActiveSSID()||this.getActiveBSSID()||this.getID(),this.getIfname());},getNetwork(){return this.getNetworks()[0];},getNetworks(){const networkNames=this.getNetworkNames();const networks=[];for(let nn of networkNames){const uciInterface=uci.get('network',nn);if(uciInterface==null||uciInterface['.type']!='interface')
continue;networks.push(Network.prototype.instantiateNetwork(nn));}
networks.sort(networkSort);return networks;},getDevice(){return Network.prototype.instantiateDevice(this.getIfname());},isClientDisconnectSupported(){return L.isObject(this.ubus('hostapd','del_client'));},disconnectClient(mac,deauth,reason,ban_time){if(reason==null||reason==0)
reason=1;if(ban_time==0)
ban_time=null;return rpc.declare({object:'hostapd.%s'.format(this.getIfname()),method:'del_client',params:['addr','deauth','reason','ban_time']})(mac,deauth,reason,ban_time);}});WifiVlan=baseclass.extend({__init__(vlan){this.ifname=vlan.ifname;if(L.isObject(vlan.config)){this.vid=vlan.config.vid;this.name=vlan.config.name;if(Array.isArray(vlan.config.network)&&vlan.config.network.length)
this.network=vlan.config.network[0];}},getName(){return this.name;},getVlanId(){return this.vid;},getNetwork(){return this.network;},getIfname(){return this.ifname;},getI18n(){const name=this.name&&this.name!=this.vid?' ('+this.name+')':'';return'vlan %d%s'.format(this.vid,name);},});return Network;