local script=arg[0]:gsub('tests/test%-gateway%-status.lua$','')
local calls={};local output
local routes='Iface Destination Gateway Flags RefCnt Use Metric Mask\neth2 00000000 0100000A 0003 0 0 11 00000000\n'
local data={['/proc/net/route']=routes,['/sys/class/net/eth1/carrier']='0',['/sys/class/net/eth2/carrier']='1'}
local realopen=io.open
io.open=function(path)
    if not data[path] then return nil end
    local text=data[path]
    return {read=function() return text end,close=function() end,lines=function()
        return text:gmatch('[^\n]+')
    end}
end
package.loaded['luci.model.uci']={cursor=function() return {get=function(_,_,_,key)
    return ({primary_if='eth1',secondary_if='eth2',ping_target='192.0.2.1',force_primary='0'})[key]
end} end}
package.loaded['luci.model.ultra_status_cache']={get=function(_,_,_,produce) return produce() end}
local env=setmetatable({module=function() end,package=package,luci={http={prepare_content=function() end,write_json=function(value) output=value end}}},{__index=_G})
local chunk=assert(loadfile(script..'overlay/usr/lib/lua/luci/controller/mwrt-assurance.lua'));setfenv(chunk,env);chunk()
env.check_online=function(dev,target) calls[#calls+1]=dev;return true end
env.get_status()
assert(#calls==1 and calls[1]=='eth2')
assert(output['当前物理接口 / Current Interface']=='eth2')
assert(output['当前网关 / Gateway']=='10.0.0.1')
assert(output['宽带接口状态 / Primary Status']=='离线 / Offline')
assert(output['蜂窝接口状态 / Secondary Status']=='在线 / Online')
io.open=realopen
print('Gateway status: one probe per physical interface, disconnected port skipped and route fields preserved')
