module("luci.controller.mwrt-assurance", package.seeall)

function index()
    if not nixio.fs.access("/etc/config/Mwrt-Assurance") then
        return
    end

    -- 配置页面
    entry({"admin", "network", "mwrt_assurance"},
        cbi("zmode/mwrt_wan_failover"),
        _("网关存活"), 80).dependent = true

    -- 状态展示页面
    entry({"admin", "network", "mwrt_Failover_status"},
        template("zmode/mwrt_wan_failover_status"),
        _("存活状态"), 96)

    -- 后端接口：获取状态
    entry({"admin", "network", "mwrt_assurance_status"},
        call("get_status")).leaf = true

    -- 后端接口：手动切换接口
    entry({"admin", "network", "mwrt_assurance_switch"},
        call("switch_wan")).leaf = true

    -- 后端接口：获取日志
    entry({"admin", "network", "mwrt_assurance_logs"},
        call("get_logs")).leaf = true
end

-- 获取指定接口网关
function get_gateway(ifname)
    local cmd = string.format("ip route show dev %s | grep '^default ' | awk '{print $3}'", ifname)
    local pipe = io.popen(cmd)
    if pipe then
        local gw = pipe:read("*l") or ""
        pipe:close()
        return gw
    end
    return ""
end

-- 检查接口是否可访问目标
function check_online(ifname, target)
    local ping_cmd = string.format("ping -I %s -c 1 -W 1 %s >/dev/null 2>&1", ifname, target)
    return (os.execute(ping_cmd) == 0)
end

function check_online_temp(ifname, target)
    -- 开启接口，不影响路由
    os.execute(string.format("ip link set %s up", ifname))

    -- 获取接口 IP
    local pipe = io.popen(string.format("ip addr show dev %s | grep 'inet ' | awk '{print $2}'", ifname))
    local ip_cidr = pipe:read("*l") or ""
    pipe:close()

    if ip_cidr == "" then
        -- 接口没有 IP 就直接失败
        return false
    end

    local source_ip = ip_cidr:match("^(%d+%.%d+%.%d+%.%d+)")
    local ping_cmd = string.format("ping -c 1 -W 1 -I %s %s >/dev/null 2>&1", source_ip, target)

    return (os.execute(ping_cmd) == 0)
end


-- 获取当前状态信息（返回 JSON）
function get_status()
    local uci = require("luci.model.uci").cursor()
    local primary_if    = uci:get("Mwrt-Assurance", "wan_failover", "primary_if") or "eth1"
    local secondary_if  = uci:get("Mwrt-Assurance", "wan_failover", "secondary_if") or "eth2"
    local target        = uci:get("Mwrt-Assurance", "wan_failover", "ping_target") or "8.8.8.8"
    local force_primary = uci:get("Mwrt-Assurance", "wan_failover", "force_primary") or "0"

    local cache_key = "gateway_" .. primary_if .. "_" .. secondary_if
    local status_data = require("luci.model.ultra_status_cache").get(cache_key, 5, 30, function()
        local routes = {}
        local current_if, current_gw, metric = "", "", math.huge
        local file = io.open("/proc/net/route", "r")
        if file then
            for line in file:lines() do
                local dev,dst,gw,flags,m = line:match("^(%S+)%s+(%x+)%s+(%x+)%s+(%x+)%s+%d+%s+%d+%s+(%d+)")
                if dst == "00000000" and (tonumber(flags,16) or 0)%2 == 1 then
                    routes[dev] = true
                    if tonumber(m) < metric then
                        current_if, metric = dev, tonumber(m)
                        local n = tonumber(gw,16) or 0
                        current_gw = string.format("%d.%d.%d.%d",n%256,math.floor(n/256)%256,math.floor(n/65536)%256,math.floor(n/16777216)%256)
                    end
                end
            end
            file:close()
        end
        local checked = {}
        local function online(dev)
            if checked[dev] ~= nil then return checked[dev] end
            local carrier_file = dev:match("^[%w_%.:%-]+$") and io.open("/sys/class/net/" .. dev .. "/carrier", "r")
            local carrier
            if carrier_file then carrier = carrier_file:read("*l"); carrier_file:close() end
            if carrier == "0" or dev == "" then checked[dev] = false
            else checked[dev] = check_online(dev, target) end
            return checked[dev]
        end
        local on, off = "在线 / Online", "离线 / Offline"
        return {
            ["当前物理接口 / Current Interface"] = current_if,
            ["当前网关 / Gateway"] = current_gw,
            ["当前是否联网 / Current Status"] = online(current_if) and on or off,
            ["宽带接口状态 / Primary Status"] = online(primary_if) and on or off,
            ["蜂窝接口状态 / Secondary Status"] = online(secondary_if) and on or off,
            ["主接口有网切换 / Force Primary"] = force_primary == "1" and "已启用 / Enabled" or "已关闭 / Disabled"
        }
    end, {})

    luci.http.prepare_content("application/json")
    luci.http.write_json(status_data)
end



-- 获取 failover 日志
function get_logs()
    local fs = require("nixio.fs")
    local log = fs.readfile("/tmp/mwrt_failover.log") or "暂无日志 / No logs"
    luci.http.prepare_content("text/plain; charset=utf-8")
    luci.http.write(log)
end

