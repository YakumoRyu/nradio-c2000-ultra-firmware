package.path='overlay/usr/lib/lua/?.lua;'..package.path
local cpu=require 'luci.model.ultra_cpu_sample'
assert(cpu.measure(nil,{total=100,idle=20,uptime=1})==0)
assert(cpu.measure({total=100,idle=50,uptime=1},{total=200,idle=120,uptime=2})==30)
assert(cpu.measure({total=100,idle=50,uptime=2},{total=50,idle=20,uptime=1})==0)
assert(cpu.measure({total=100,idle=50,uptime=1},{total=100,idle=50,uptime=2})==0)
assert(cpu.measure({total=100,idle=50,uptime=1},{total=200,idle=200,uptime=2})==0)
local paths={['/proc/stat']='cpu 10 0 20 50 20 0 0 0 0 0\ncpu0 0 0 0 0 0 0 0 0', ['/proc/uptime']='123.45 0'}
local s=cpu.read({readfile=function(path)return paths[path]end})
assert(s.total==100 and s.idle==70 and s.uptime==123.45)
paths['/proc/stat']='invalid'
assert(cpu.read({readfile=function(path)return paths[path]end})==nil)
-- Exercise the shared state, close-on-all-paths and sub-second coalescing.
paths['/proc/stat']='cpu 10 0 20 50 20 0 0 0 0 0'
package.loaded['nixio.fs']={readfile=function(p)return paths[p]end,writefile=function(p,v)paths[p]=v;return #v end,rename=function(a,b)paths[b]=paths[a];paths[a]=nil;return true end}
local closed=0;local locked=true
package.loaded.nixio={open=function()return {lock=function()return locked end,close=function()closed=closed+1 end}end}
assert(cpu.percent()==0)
paths['/proc/stat']='cpu 20 0 40 100 40 0 0 0';paths['/proc/uptime']='125.45 0'
assert(cpu.percent()==30)
paths['/proc/uptime']='125.50 0';assert(cpu.percent()==30)
locked=false;assert(cpu.percent()==30);assert(closed==4)
print('11 CPU sample and shared-cache checks passed')
