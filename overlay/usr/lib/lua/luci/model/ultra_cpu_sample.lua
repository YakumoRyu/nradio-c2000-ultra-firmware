-- Share /proc/stat samples across LuCI requests without sleeping in a worker.
local M = {}

function M.measure(before, after)
    if not before or not after or after.uptime < before.uptime then return 0 end
    local total, idle = after.total - before.total, after.idle - before.idle
    if total <= 0 or idle < 0 or idle > total then return 0 end
    return math.max(0, math.min(100, (total - idle) * 100 / total))
end

function M.read(fs)
    local raw = fs.readfile('/proc/stat') or ''
    local values = {}
    for v in (raw:match('^cpu%s+([^\n]+)') or ''):gmatch('%d+') do values[#values+1] = tonumber(v) end
    if #values < 8 then return nil end
    local total = 0
    for i=1,8 do total = total + values[i] end
    return {total=total, idle=values[4]+values[5], uptime=tonumber((fs.readfile('/proc/uptime') or ''):match('^[%d.]+')) or 0}
end

function M.percent()
    local fs, nx = require 'nixio.fs', require 'nixio'
    local path = '/tmp/mwrt_cpu_sample'
    local function cached()
        local u,t,i,p=(fs.readfile(path) or ''):match('^([%d.]+) (%d+) (%d+) ([%d.]+)$')
        if u then return {uptime=tonumber(u),total=tonumber(t),idle=tonumber(i),percent=tonumber(p)} end
    end
    local before=cached()
    local fd=nx.open(path..'.lock','w','600')
    if not fd or not fd:lock('tlock') then
        if fd then fd:close() end
        return before and before.percent or 0
    end
    before=cached()
    local now=M.read(fs)
    if not now then fd:close();return before and before.percent or 0 end
    if before and now.uptime>=before.uptime and now.uptime-before.uptime<0.75 then
        fd:close();return before.percent
    end
    local value=M.measure(before,now)
    local data=string.format('%.2f %.0f %.0f %.3f',now.uptime,now.total,now.idle,value)
    if fs.writefile(path..'.new',data) then fs.rename(path..'.new',path) end
    fd:close()
    return value
end

return M
