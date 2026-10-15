-- Validate parsed QModem fields before caching or returning them to the UI.
local M = {}

function M.value(key, value)
    if value == nil then return nil end
    local s = tostring(value):gsub("^%s+", ""):gsub("%s+$", "")
    if s == "" or s == "--" or s == "ERROR" or s:find("CME ERROR", 1, true)
        or s:find("CMS ERROR", 1, true) or s:find("[\r\n]")
        or s:match("^%^[%w_]+:") then return nil end
    local k = tostring(key or ""):lower()
    if k == "imei" and (#s ~= 15 or not s:match("^%d+$")) then return nil end
    if k == "imsi" and (#s < 14 or #s > 15 or not s:match("^%d+$")) then return nil end
    return value
end

function M.list(items)
    local out = {}
    for _, entry in ipairs(items or {}) do
        if type(entry) == "table" and M.value(entry.key, entry.value) ~= nil then
            out[#out + 1] = entry
        end
    end
    return out
end

return M
