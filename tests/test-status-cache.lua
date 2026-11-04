local script = arg[0]:gsub('tests/test%-status%-cache.lua$', '')
local files, objects, clock, locked, writes, closes = {}, {}, 100, false, 0, 0
local fs = {}
function fs.mkdirr() end
function fs.readfile(path) if path == '/proc/uptime' then return tostring(clock) .. ' 0' end return files[path] end
function fs.writefile(path, data) files[path] = data; writes = writes + 1; return true end
function fs.rename(a,b) files[b]=files[a];files[a]=nil;return true end
local nx = {}
function nx.open()
    local held = false
    return {
        lock = function() if locked then return false end locked=true;held=true;return true end,
        close = function() if held then locked=false end closes=closes+1 end
    }
end
local json = {}
function json.stringify(value) local key='json-'..tostring(#objects+1);objects[#objects+1]=value;objects[key]=value;return key end
function json.parse(text) return objects[text] end
package.loaded['nixio.fs']=fs;package.loaded['nixio']=nx;package.loaded['luci.jsonc']=json
local cache = dofile(script .. 'overlay/usr/lib/lua/luci/model/ultra_status_cache.lua')
local calls=0
local function produce() calls=calls+1;return {sequence=calls} end
assert(cache.get('test',3,30,produce,{}).sequence==1)
assert(cache.get('test',3,30,produce,{}).sequence==1 and calls==1)
clock=105
local second
local function nested()
    second=cache.get('test',3,30,produce,{})
    return produce()
end
assert(cache.get('test',3,30,nested,{}).sequence==2)
assert(second.sequence==1 and calls==2)
clock=110
local old=cache.get('test',3,30,function() error('simulated backend failure') end,{})
assert(old.sequence==2 and not locked)
clock=150;locked=true
assert(next(cache.get('test',3,30,produce,{}))==nil and calls==2)
locked=false;clock=90
assert(cache.get('test',3,30,produce,{}).sequence==3)
local valid=pcall(function() cache.get('../unsafe',3,30,produce,{}) end)
assert(not valid)
assert(writes==3)
print('Status cache: freshness, concurrent refresh, stale expiry, clock rollback, failure unlock and key validation passed')
