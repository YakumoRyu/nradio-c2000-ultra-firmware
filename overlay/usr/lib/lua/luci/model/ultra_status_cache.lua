-- Coalesce slow read-only status work across LuCI workers without waiting.
local M = {}

function M.get(key, fresh_seconds, max_age, producer, empty)
    assert(type(key) == 'string' and key:match('^[%w_%-]+$'))
    local fs, nx, json = require 'nixio.fs', require 'nixio', require 'luci.jsonc'
    fs.mkdirr('/tmp/run/mwrt')
    local path = '/tmp/run/mwrt/status_' .. key .. '.json'
    local function now() return tonumber((fs.readfile('/proc/uptime') or ''):match('^[%d.]+')) or 0 end
    local function cached()
        local row = json.parse(fs.readfile(path) or '')
        if type(row) ~= 'table' or type(row.time) ~= 'number' or type(row.value) ~= 'table' then return nil end
        local age = now() - row.time
        if age < 0 or age > max_age then return nil end
        return row.value, age
    end
    local value, age = cached()
    if value and age <= fresh_seconds then return value end
    local lock = nx.open(path .. '.lock', 'w', '600')
    if not lock or not lock:lock('tlock') then
        if lock then lock:close() end
        return value or empty
    end
    value, age = cached()
    if value and age <= fresh_seconds then lock:close(); return value end
    local ok, result = pcall(producer)
    if ok and type(result) == 'table' then
        local text = json.stringify({time = now(), value = result})
        if text and fs.writefile(path .. '.new', text) then fs.rename(path .. '.new', path) end
    end
    lock:close()
    if ok and type(result) == 'table' then return result end
    return value or empty
end

return M
