local m, section, m2, s2
m = Map("mwrt", translate("模组提示信息与其他设定"))
section = m:section(TypedSection, "ndis", translate("WEBUI与转发/网络检查设置"))
section.anonymous = true
section.addremove = false
section:tab("general", translate("常规设置"))

simsel = section:taboption("general", ListValue, "simsel", translate("卡槽选择"))
local _mc_sim = luci.sys.exec("cat /tmp/modconf.conf 2>/dev/null") or ""
-- 卡槽切换是纯硬件 mux(GPIO cpe-sel0),只有 C2000 MAX/Ultra 有这根引脚。
-- H5000M / 87N 等机型无卡槽 mux -> 只有机身卡槽,且绝不写 cpe-sel0。
-- 判据用引脚节点存在性(物理真实状态),比匹配 board_name 字符串可靠。
local has_slot_mux = false
do
	local _f = io.open("/sys/class/gpio/cpe-sel0/value", "r")
	if _f then has_slot_mux = true; _f:close() end
end
if not has_slot_mux then
	-- 非 C2000 机型(H5000M/87N 等):无卡槽 mux,只显示机身卡槽,不做任何 GPIO 操作
	simsel:value("0", translate("机身卡槽"))
	simsel.default = "0"
elseif _mc_sim:find("5700") then
	-- MT5700 授权模组:保留机身卡槽(内置卡切换由 mt5700m.sh + ^SCICHG 处理)
	simsel:value("0", translate("机身卡槽"))
else
	-- FM350/RM520:内置卡是授权模组专属,非授权模组切内置会封卡 -> 只暴露外置卡
	simsel:value("1", translate("外置卡槽1(正面)"))
	simsel:value("2", translate("外置卡槽2(背面)"))
	simsel.default = "1"
end
simsel.rmempty = true
simsel.write = function(self, section, value)
	local old = self.map:get(section, self.option)
	self.map:set(section, self.option, value)
	-- 只有 C2000(有卡槽 mux)且非5700模组:选卡后动 GPIO cpe-sel0 切外置卡槽。
	-- 无 mux 机型一律不写 cpe-sel0(引脚不存在)。
	if old ~= value and has_slot_mux and not _mc_sim:find("5700") then
		luci.sys.call("/usr/share/modem/fm350sim.sh '" .. value .. "' >/dev/null 2>&1 &")
	end
end

local cmd = io.popen("cat /tmp/modconf.conf")
local content = cmd:read("*all") or ""
cmd:close()
if (content and string.find(content, "5700")) or (content and string.find(content, "MT5700M-CN")) then
    -- MT5700-SIN卡状态查询
    sim_card_stat = section:taboption("general", DummyValue, "sim_card_stat", translate("SIM状态"))
    local sim_status_output =luci.sys.exec("cat /tmp/simcardstat")
    local sim_status_output = luci.sys.exec("sendat 1 'AT^SIMSQ?' | awk '/^\\^SIMSQ:/ {split($0, a, \",\"); print a[2]}'")
    if sim_status_output == "" then
        local sim_status_description = "未获取到值,请刷新。"
    else
        sim_status_output = sim_status_output:match("%S+")
    end
        local sim_status_description = "未获取到值,请刷新。"
        if sim_status_output == "0" then
            sim_status_description = "状态码:0 -SIM卡未插入"
        elseif sim_status_output == "1" then
            sim_status_description = "状态码:1 -SIM卡已插入"
        elseif sim_status_output == "2" then
            sim_status_description = "状态码:2 -SIM卡被锁"
        elseif sim_status_output == "3" then
            sim_status_description = "状态码:3-SIMLOCK 锁定(暂不支持上报)"
        elseif sim_status_output == "10" then
            sim_status_description = "状态码:10-卡文件正在初始化 SIM Initializing"
        elseif sim_status_output == "11" then
            sim_status_description = "状态码:11-SIN卡已经正常 （可接入网络）"
        elseif sim_status_output == "12" then
            sim_status_description = "状态码:12 -SIM卡正常工作"
        elseif sim_status_output == "98" then
            sim_status_description = "状态码:98 -卡物理失效 （PUK锁死或者卡物理失效）"
        elseif sim_status_output == "99" then
            sim_status_description = "状态码:99 -卡移除 SIM removed"
        elseif sim_status_output == "Note2" then
            sim_status_description = "状态码:Note2 -不支持虚拟SIM卡"
        elseif sim_status_output == "100" then
            sim_status_description = "状态码:100 -卡错误（初始化过程中，卡失败）"
        elseif sim_status_output == "" then
            sim_status_description = "未获取到值或未插入,请刷新。"
        else
            sim_status_description = "状态码:"..sim_status_output.."  请参考AT手册"
        end
        sim_card_stat.value = sim_status_description
    end
    -- MT5700SIN卡状态查询

current_mod = section:taboption("general", Value, "current_mod", translate("当前模组"))
current_mod.rmempty = true
current_mod.default = ""

local s = m:section(SimpleSection)
s.title = "USB 设备信息 /lsusb"
s.description = "<div style='background:#1a1a1a;color:#fffb00;padding:12px;border-radius:6px;font-family:monospace;font-size:12px;white-space:pre;'>" ..
    luci.sys.exec("lsusb 2>/dev/null") .. "</div>"

local s = m:section(SimpleSection)
s.title = "PCI 设备信息 /lspci"
s.description = "<div style='background:#1a1a1a;color:#fffb00;padding:12px;border-radius:6px;font-family:monospace;font-size:12px;white-space:pre;'>" ..
    luci.sys.exec("lspci 2>/dev/null") .. "</div>"


function current_mod.cfgvalue(self, section)
    local keywords = {
        "mediatek", "fm350", "quectel", "fibocom", "huawei", "zte", "sierra", "cinterion", "longsung",
        "meig", "me909", "simcom", "foxconn", "alcatel", "ublox", "telit",
        "td tech", "td-tech", "tdtech", "td500", "td510"
    }
    local lsusb = luci.sys.exec("lsusb"):lower()
    for line in lsusb:gmatch("[^\r\n]+") do
        for _, key in ipairs(keywords) do
            if line:find(key) then
                local model = line:match("([%w%-]+)%s*$")
                return model or line
            end
        end
    end
    return "未检测到USB模组"
end

-----------------------------------------------------------------
section:tab("350WEBUI", translate("蜂窝模组WEBUI选项"), translate("适用于RM520/FM350模组WEBUI服务设置。"))
local websocket_status_350 = section:taboption("350WEBUI", DummyValue, "_websocket_status", translate("WEBUI 服务状态"))
websocket_status_350.rawhtml = true --允许原始HTML渲染
local handle_350 = io.popen("ps w | grep fm350webserver.py | grep -v grep")
local result_350 = handle_350:read("*a")
handle_350:close()

webuishow_350 = section:taboption("350WEBUI", Button, "webuishow_350", translate("打开webui界面"))
webuishow_350.inputtitle = translate("打开webui界面")
webuishow_350.inputstyle = "apply"
webuishow_350.write = function()
    luci.http.redirect(luci.dispatcher.build_url("admin/modem/webui"))
end

webuishow2_350 = section:taboption("350WEBUI", Button, "webuishow2_350", translate("网页样式显示"))
webuishow2_350.inputtitle = translate("打开webui链接")
webuishow2_350.inputstyle = "apply"
webuishow2_350.write = function()
    -- Build the target from the host the browser is already using, so it follows
    -- any br-lan IP change instead of a hardcoded address.
    local host = (luci.http.getenv("HTTP_HOST") or "192.168.1.1"):gsub(":%d+$", "")
    luci.http.redirect("http://" .. host .. ":8889/#/network-info")
end

if result_350 ~= "" then
    websocket_status_350.value = [[<span style="color: green; font-weight: bold;">✔ webui服务运行中</span>]]
else
    websocket_status_350.value = [[<span style="color: red; font-weight: bold;">✖ webui服务停止</span>]]
end

apply_notifications_websocket_350 = section:taboption("350WEBUI", Button, "apply_notifications_websocket_350", translate("重新启动webui"))
apply_notifications_websocket_350.inputtitle = translate("重启webui服务")
apply_notifications_websocket_350.inputstyle = "apply"
apply_notifications_websocket_350.write = function(self, section)
    local jsonc_350 = require("luci.jsonc")
    local nixio_350 = require("nixio")
    -- Refresh the WEBUI SPA config so it points at the current br-lan IP.
    os.execute("/usr/bin/gen_webui_config.sh")
    os.execute("ps w | grep fm350webserver.py | grep -v grep | awk '{print $1}' | xargs kill -9")
    local handle = io.popen("lsusb")
    local lsusb_output = handle:read("*all")
    handle:close()

    if (lsusb_output and (string.find(lsusb_output, "520") or string.find(lsusb_output, "350") or string.find(lsusb_output, "0e8d:7127") or string.find(lsusb_output, "0e8d 7127"))) then
        -- Pin the detected AT serial port so the server does not exit when its own
        -- tom_modem probe is starved by a contended semaphore.
        os.execute("python3 /usr/bin/detect_at_port.py /usr/bin/config.json")
        os.execute("python3 /usr/bin/fm350webserver.py &")
        luci.http.write("<script>alert('已重新开启WEBUI！')</script>")
    else
        luci.http.write("<script>alert('未检测到FM350/RM520模组，不支持此WEBUI！')</script>")
    end

    return true
end

-----------------------------------------------------------------
section:tab("WEBUI", translate("巴龙WEBUI选项与转发"), translate("适用于MT5700M-CN模组WEBUI服务设置,更改WebSocket IP和端口后webui界面需要修改相应参数。"))
local websocket_status = section:taboption("WEBUI", DummyValue, "_websocket_status", translate("WEBUI 服务状态"))
websocket_status.rawhtml = true --允许原始HTML渲染
local handle = io.popen("ps w | grep websocket_server.py | grep -v grep")
local result = handle:read("*a")
handle:close()

webuishow = section:taboption("WEBUI", Button, "webuishow", translate("打开webui界面"))
webuishow.inputtitle = translate("打开webui界面")
webuishow.inputstyle = "apply"
webuishow.write = function()
    luci.http.redirect(luci.dispatcher.build_url("admin/modem/webui"))
end

webuishow2 = section:taboption("WEBUI", Button, "webuishow2", translate("网页样式显示"))
webuishow2.inputtitle = translate("打开webui链接")
webuishow2.inputstyle = "apply"
webuishow2.write = function()
    -- Build the target from the host the browser is already using, so it follows
    -- any br-lan IP change instead of a dead hardcoded path.
    local host = (luci.http.getenv("HTTP_HOST") or "192.168.1.1"):gsub(":%d+$", "")
    luci.http.redirect("http://" .. host .. ":8889/#/network-info")
end

if result ~= "" then
    websocket_status.value = [[<span style="color: green; font-weight: bold;">✔ webui服务运行中</span>]]
else
    websocket_status.value = [[<span style="color: red; font-weight: bold;">✖ webui服务停止</span>]]
end
-- 选择连接WEBUI的方式
connection_type = section:taboption("WEBUI", ListValue, "connection_type", translate("连接方式"))
connection_type:value("SERIAL", translate("串口（通常是内部模组）"))
--connection_type:value("NETWORK", translate("网络（通常是AK68天线）"))
connection_type.default = "SERIAL"
connection_type.rmempty = false  -- 强制必须选择
-- 网络配置（仅当选择网络时必填）
host = section:taboption("WEBUI", Value, "host", translate("模组IP"))
host:depends("connection_type", "NETWORK")
host.rmempty = true  -- 允许为空但后端会填充默认值
host.default = "192.168.8.1"

port = section:taboption("WEBUI", Value, "port", translate("模组端口"))
port:depends("connection_type", "NETWORK")
port.rmempty = true
port.default = "20249"
port.datatype = "port"

timeout = section:taboption("WEBUI", Value, "timeout", translate("超时时间"))
timeout:depends("connection_type", "NETWORK")
timeout.rmempty = true
timeout.default = "10"
timeout.datatype = "uinteger"
-- 串口配置（用于SERIAL）
serial_port = section:taboption("WEBUI", ListValue, "serial_port", translate("串口端口"))
serial_port.rmempty = true
serial_port.default = "/dev/ttyUSB1"
serial_port:depends("connection_type", "SERIAL")  -- 仅在选择串口时可见
-- 获取系统所有的串口接口
local serial_ports = {}
local f = io.popen("ls /dev/ttyUSB*")
if f then
    for port in f:lines() do
        table.insert(serial_ports, port)
    end
    f:close()
end
for _, port in ipairs(serial_ports) do
    serial_port:value(port)
end

baudrate = section:taboption("WEBUI", Value, "baudrate", translate("波特率"))
baudrate:depends("connection_type", "SERIAL")
baudrate.rmempty = true
baudrate.default = "115200"
baudrate.datatype = "uinteger"

serial_timeout = section:taboption("WEBUI", Value, "serial_timeout", translate("串口超时"))
serial_timeout:depends("connection_type", "SERIAL")
serial_timeout.rmempty = true
serial_timeout.default = "10"
serial_timeout.datatype = "uinteger"
-- 微信Webhook URL
wechat_webhook = section:taboption("WEBUI", Value, "wechat_webhook", translate("PPS+平台转发Token"))
wechat_webhook.rmempty = true
-- 日志文件路径
log_file = section:taboption("WEBUI", Value, "log_file", translate("日志文件"))
log_file.default = "notifications.log"
log_file.rmempty = false
-- 通知类型设置
notification_sms = section:taboption("WEBUI", Flag, "notification_sms", translate("短信转发"))
notification_sms.default = true

notification_call = section:taboption("WEBUI", Flag, "notification_call", translate("来电转发"))
notification_call.default = true

notification_memory_full = section:taboption("WEBUI", Flag, "notification_memory_full", translate("内存满通知转发"))
notification_memory_full.default = true

notification_signal = section:taboption("WEBUI", Flag, "notification_signal", translate("信号变化通知转发"),translate("以上信息勾选后会推送到PPS+公众号，请按需选择，短信转发需要在常规设置里面勾选短信开关。"))
notification_signal.default = false
-- 选择协议类型：IPv4 或 IPv6
protocol_type = section:taboption("WEBUI", ListValue, "protocol_type", translate("选择WebSocket协议类型"))
protocol_type:value("IPV4", translate("IPv4"))
protocol_type:value("IPV6", translate("IPv6"))
protocol_type.rmempty = false

-- WebSocket 主机地址和端口设置
websocket_host = section:taboption("WEBUI", Value, "websocket_host", translate("WebSocket 主机"))
websocket_host.default = "0.0.0.0"
websocket_host.rmempty = false
websocket_host:depends("protocol_type", "IPV4")

websocket_host_ipv6 = section:taboption("WEBUI", Value, "websocket_host_ipv6", translate("WebSocket 主机 (IPv6)"))
websocket_host_ipv6.default = "::"
websocket_host_ipv6.rmempty = false
websocket_host_ipv6:depends("protocol_type", "IPV6")

websocket_port = section:taboption("WEBUI", Value, "websocket_port", translate("WebSocket 端口") ,translate("提示：修改端口和IP后请在webui界面修改对应参数,0.0.0.0代表当前设备IP,通常不需要修改。"))
websocket_port.default = "8766"
websocket_port.rmempty = false

-- 执行按钮（更新和执行通知配置、WebSocket 配置）
apply_notifications_websocket = section:taboption("WEBUI", Button, "apply_notifications_websocket", translate("应用通知与WebSocket配置"))
apply_notifications_websocket.inputtitle = translate("应用并重启服务")
apply_notifications_websocket.inputstyle = "apply"
apply_notifications_websocket.write = function(self, section)
    local jsonc = require("luci.jsonc")
    local nixio = require("nixio")

    -- Refresh the WEBUI SPA config so it points at the current br-lan IP.
    os.execute("/usr/bin/gen_webui_config.sh")

    local config_file = "/usr/bin/config.json"

    -- 读取现有配置（如果文件存在）
    local content = nixio.fs.readfile(config_file)
    local data = content and jsonc.parse(content) or {}

    -- 确保各个字段存在
    data.AT_CONFIG = data.AT_CONFIG or {}
    data.AT_CONFIG.NETWORK = data.AT_CONFIG.NETWORK or {}
    data.AT_CONFIG.SERIAL = data.AT_CONFIG.SERIAL or {}
    data.NOTIFICATION_CONFIG = data.NOTIFICATION_CONFIG or {}
    data.NOTIFICATION_CONFIG.NOTIFICATION_TYPES = data.NOTIFICATION_CONFIG.NOTIFICATION_TYPES or {}
    data.WEBSOCKET_CONFIG = data.WEBSOCKET_CONFIG or {}
    data.WEBSOCKET_CONFIG.IPV4 = data.WEBSOCKET_CONFIG.IPV4 or {}
    data.WEBSOCKET_CONFIG.IPV6 = data.WEBSOCKET_CONFIG.IPV6 or {}

    -- **获取用户输入的值**
    local connection_type = self.map:get(section, "connection_type")
    if connection_type and connection_type ~= "" then
        data.AT_CONFIG.TYPE = connection_type
    end

    -- **更新网络模式配置**
    if connection_type == "NETWORK" then
        local host = self.map:get(section, "host")
        if host and host ~= "" then
            data.AT_CONFIG.NETWORK.HOST = host
        end
        
        local port = self.map:get(section, "port")
        if port and port ~= "" then
            data.AT_CONFIG.NETWORK.PORT = tonumber(port)
        end
        
        local timeout = self.map:get(section, "timeout")
        if timeout and timeout ~= "" then
            data.AT_CONFIG.NETWORK.TIMEOUT = tonumber(timeout)
        end
    end

    -- **更新串口模式配置**
    if connection_type == "SERIAL" then
        local serial_port = self.map:get(section, "serial_port")
        if serial_port and serial_port ~= "" then
            data.AT_CONFIG.SERIAL.PORT = serial_port
        end

        local baudrate = self.map:get(section, "baudrate")
        if baudrate and baudrate ~= "" then
            data.AT_CONFIG.SERIAL.BAUDRATE = tonumber(baudrate)
        end

        local serial_timeout = self.map:get(section, "serial_timeout")
        if serial_timeout and serial_timeout ~= "" then
            data.AT_CONFIG.SERIAL.TIMEOUT = tonumber(serial_timeout)
        end
    end

    -- **更新通知设置**
    local wechat_webhook = self.map:get(section, "wechat_webhook")
    if wechat_webhook and wechat_webhook ~= "" then
        data.NOTIFICATION_CONFIG.WECHAT_WEBHOOK = wechat_webhook
    end

    local log_file = self.map:get(section, "log_file")
    if log_file and log_file ~= "" then
        data.NOTIFICATION_CONFIG.LOG_FILE = log_file
    end

    -- 更新通知设置
    local notification_sms = self.map:get(section, "notification_sms")
    if notification_sms ~= nil then
        -- 转换为布尔值
        data.NOTIFICATION_CONFIG.NOTIFICATION_TYPES.SMS = notification_sms == "1" or notification_sms == true
    end

    local notification_call = self.map:get(section, "notification_call")
    if notification_call ~= nil then
        -- 转换为布尔值
        data.NOTIFICATION_CONFIG.NOTIFICATION_TYPES.CALL = notification_call == "1" or notification_call == true
    end

    local notification_memory_full = self.map:get(section, "notification_memory_full")
    if notification_memory_full ~= nil then
        -- 转换为布尔值
        data.NOTIFICATION_CONFIG.NOTIFICATION_TYPES.MEMORY_FULL = notification_memory_full == "1" or notification_memory_full == true
    end

    local notification_signal = self.map:get(section, "notification_signal")
    if notification_signal ~= nil then
        -- 转换为布尔值
        data.NOTIFICATION_CONFIG.NOTIFICATION_TYPES.SIGNAL = notification_signal == "1" or notification_signal == true
    end
    -- **更新 WebSocket 设置**
    local protocol_type = self.map:get(section, "protocol_type")
    if protocol_type and protocol_type ~= "" then
        local websocket_host = self.map:get(section, "websocket_host")
        local websocket_host_ipv6 = self.map:get(section, "websocket_host_ipv6")
        local websocket_port = self.map:get(section, "websocket_port")

        if protocol_type == "IPV4" and websocket_host and websocket_host ~= "" then
            data.WEBSOCKET_CONFIG.IPV4.HOST = websocket_host
        end
        
        if protocol_type == "IPV6" and websocket_host_ipv6 and websocket_host_ipv6 ~= "" then
            data.WEBSOCKET_CONFIG.IPV6.HOST = websocket_host_ipv6
        end
        
        if websocket_port and websocket_port ~= "" then
            data.WEBSOCKET_CONFIG.IPV4.PORT = tonumber(websocket_port)
            data.WEBSOCKET_CONFIG.IPV6.PORT = tonumber(websocket_port)
        end
    end

    -- **删除旧的 config.json 并重新创建**
    nixio.fs.remove(config_file)
    nixio.fs.writefile(config_file, jsonc.stringify(data, true))

    -- **重启 WebSocket 服务**
    os.execute("ps w | grep websocket_server.py | grep -v grep | awk '{print $1}' | xargs kill -9")
    local file88 = io.open("/tmp/modconf.conf", "r")
	if file88 then
		local content88 = file88:read("*all")
		file88:close()
		if content88 and string.find(content88, "RM520") then
            luci.http.write("<script>alert('RM520模组无法使用此WEBUI！')</script>")
		elseif content88 and string.find(content88, "RM500U") then
            luci.http.write("<script>alert('RM500模组无法使用此WEBUI！')</script>")
		elseif content88 and string.find(content88, "MT5700") then
            -- Pin the detected AT serial port (SERIAL mode only) so the server does not
            -- sit in an endless reconnect loop with no data when the port drifts.
            os.execute("python3 /usr/bin/detect_at_port.py /usr/bin/config5700.json")
            os.execute("python3 /usr/bin/websocket_server.py &")
			luci.http.write("<script>alert('已重新开启WEBUI！')</script>")
        else
            luci.http.write("<script>alert('ERR！未检测到支持的模组！无法开启。')</script>")
		end
	end
    return true
end
---------
local has_modem1 = (os.execute("lsusb | grep -q '5700'") == 0)
    if has_modem1 then
        luci.sys.exec("/usr/bin/LQXH.sh > /tmp/LQXH.file || echo '-' > /tmp/LQXH.file")--如果没有值要搞个-进去存着，不然这二逼LUA会报错
        enable_imei2 = section:taboption("WEBUI", Flag, "enable_imei2", translate("显示邻区"))
        enable_imei2.default = false
        enable_imei2.rmempty = true
    end


local function createSignalBar(rsrp_value)
    local bars = 10  -- 最大条数表示信号
    local percentage = math.min(100, math.max(0, (rsrp_value + 140) * 2))  -- 转换公式，确保范围在0-100
    local filledBars = math.floor((percentage / 100) * bars)
    local barGraph = string.rep(">", filledBars) .. string.rep("-", bars - filledBars)
    return string.format("[%s] %d%% (%d dBm)", barGraph, percentage, rsrp_value)
end

local function render_signal(name, line_number)
    local raw_value = luci.sys.exec("sed -n '" .. line_number .. "p' /tmp/LQXH.file")
    local mode = raw_value:match("模式(%w+)")
    local earfcn = raw_value:match("频点:(%d+)")
    local pci = raw_value:match("小区:(%d+)")
    local rsrp_value = tonumber(raw_value:match("信号:(%-?%d+)")) or -140
    local signalDisplay = createSignalBar(rsrp_value)
    return string.format("%s | 模式 %s | 频点： %s | 小区PCI： %s |  信号： %s", name, mode or "N/A", earfcn or "N/A", pci or "N/A", signalDisplay)
end

modify_imei2 = section:taboption("WEBUI", DummyValue, "modify_imei2", translate("邻信号1"))
modify_imei2.cfgvalue = function()
    return render_signal("节点", 1)
end
modify_imei2:depends("enable_imei2", "1")

modify_imei3 = section:taboption("WEBUI", DummyValue, "modify_imei3", translate("邻信号2"))
modify_imei3.cfgvalue = function()
    return render_signal("节点", 2)
end
modify_imei3:depends("enable_imei2", "1")

modify_imei4 = section:taboption("WEBUI", DummyValue, "modify_imei4", translate("邻信号3"))
modify_imei4.cfgvalue = function()
    return render_signal("节点", 3)
end
modify_imei4:depends("enable_imei2", "1")

modify_imei5 = section:taboption("WEBUI", DummyValue, "modify_imei5", translate("邻信号4"))
modify_imei5.cfgvalue = function()
    return render_signal("节点", 4)
end
modify_imei5:depends("enable_imei2", "1")

modify_imei6 = section:taboption("WEBUI", DummyValue, "modify_imei6", translate("邻信号5"))
modify_imei6.cfgvalue = function()
    return render_signal("节点", 5)
end
modify_imei6:depends("enable_imei2", "1")

modify_imei7 = section:taboption("WEBUI", DummyValue, "modify_imei7", translate("邻信号6"))
modify_imei7.cfgvalue = function()
    return render_signal("节点", 6)
end
modify_imei7:depends("enable_imei2", "1")

modify_imei8 = section:taboption("WEBUI", DummyValue, "modify_imei8", translate("邻信号7"))
modify_imei8.cfgvalue = function()
    return render_signal("节点", 7)
end
modify_imei8:depends("enable_imei2", "1")

modify_imei9 = section:taboption("WEBUI", DummyValue, "modify_imei9", translate("邻信号8"))
modify_imei9.cfgvalue = function()
    return render_signal("节点", 8)
end
modify_imei9:depends("enable_imei2", "1")

modify_imei10 = section:taboption("WEBUI", DummyValue, "modify_imei10", translate("邻信号9"))
modify_imei10.cfgvalue = function()
    return render_signal("节点", 9)
end
modify_imei10:depends("enable_imei2", "1")

modify_imei11 = section:taboption("WEBUI", DummyValue, "modify_imei11", translate("邻信号10"))
modify_imei11.cfgvalue = function()
    return render_signal("节点", 10)
end
modify_imei11:depends("enable_imei2", "1")
---------------------------------------------------------------------------------

local cmd2 = io.popen("cat /tmp/modconf.conf")
local content = cmd2:read("*all") or ""
cmd2:close()

if (content and string.find(content, "MT5700")) or (content and string.find(content, "5700")) then
    enable_imei = section:taboption("WEBUI", Flag, "enable_imei", translate("ModifyI"))
    enable_imei.default = false
    enable_imei.rmempty = true
    enable_imei:depends("simsel", "0")
    modify_imei = section:taboption("WEBUI", Value, "modify_imei", translate("ModifyI"), translate("Warning! Warning! Warning! This is an internal engineering testing program, which is limited to testing whether the module is properly mounted. It is strictly prohibited to use it for other purposes, and the user shall bear all consequences arising from using it for other purposes on their own!"))
    modify_imei.default = luci.sys.exec("sendat 1 AT+CGSN | sed -n '2p'")
    modify_imei:depends("enable_imei", "1")
    modify_imei.validate = function(self, value)
       if not value:match("^%d%d%d%d%d%d%d%d%d%d%d%d%d%d%d$") then
           return nil, translate("IMEI必须是15位数字")
      end
      return value
end
end
-- 初始化5700按钮
initmodem = section:taboption("WEBUI", Button, "initmodem", translate("模组重置"))
initmodem.inputtitle = translate("初始化5700模组为标准USB模式(点击立即执行)")
initmodem.inputstyle = "apply"

-- shell脚本内容
local script = [[
#!/bin/sh
echo "开始初始化模组...
1
#ff0000" > /tmp/lucimsg.file
sendat 1 'AT^SETAUTODIAL=1,1'
sleep 1
sendat 1 'AT^SETAUTODIAL=0'
sleep 1
sendat 1 'AT^SETAUTODIAL=1,1'
sleep 1
sendat 1 'AT^TDPMCFG=0,0,0,0'
sleep 1
sendat 1 'AT+CGDCONT=1,"IPV4V6"'
sleep 1
sendat 1 'AT^LEDSWITCH=1'
sleep 1
sendat 1 'AT^SETE5STICK=0'
sleep 1
sendat 1 'AT^SETMODE=4'
echo "切换完成，重启设备..." > /tmp/lucimsg.file
sleep 2
reboot
]]

if not nixio.fs.access("/usr/bin/init_5700.sh") then
    local f = io.open("/usr/bin/init_5700.sh", "w")
    f:write(script)
    f:close()
    luci.sys.call("chmod +x /usr/bin/init_5700.sh")
end

initmodem.write = function()
    local has_modem = (os.execute("lsusb | grep -q '5700'") == 0)
    if has_modem then
        io.popen("/usr/bin/init_5700.sh &")
    else
        luci.http.write("<script>alert('没有检测到MT5700M-CN模组，无法执行。')</script>")
    end
end

-----------------------------------------------------
function get_network_latency(test_url)
    local stdout = io.popen('ping -c 4 ' .. test_url .. ' | tail -1| awk \'{print $4}\' | cut -d \'/\' -f 2')
    local latency = stdout:read("*a")
    stdout:close()
    return latency:gsub("^%s*(.-)%s*$", "%1") 
end


section:tab("Networkchek", translate("网络检查"),translate("温馨提示：用于检查当前模组网络连接是否正常。"))
enable_weburl = section:taboption("Networkchek", Flag, "enable_weburl", translate("健康检查开关"))
enable_weburl.default = true
enable_weburl.rmempty = true
weburl = section:taboption("Networkchek", Value, "weburl", translate("网络检查地址"))
weburl.default = "www.baidu.com"
weburl.template = "cbi/value"
weburl.write = function(self, section, value)
    weburl.map:set(section, self.option, value)
    local latency = get_network_latency(value)
    weburl.map:set(section, "display_latency", latency)
end

display_latency = section:taboption("Networkchek", DummyValue, "display_latency", translate("检测延迟 (ms)"),translate("提示：URL输入后回车可测延迟"))
display_latency.rawhtml = true
display_latency:depends("enable_weburl", "1")

weburl:depends("enable_weburl", "1")

----------------------------------


-----------------------------------
local apply = luci.http.formvalue("cbi.apply")
local sys = require "luci.sys"
local file = io.open("/tmp/modconf.conf", "r")
if apply then
    if file then
        local content = file:read("*all")
        file:close()
        if content and string.find(content, "RM520") then
            --io.popen("/usr/share/modem/rm520n.sh &")
        elseif content and string.find(content, "RM500U") then
            --io.popen("/usr/share/modem/500U.sh &")  
            --sys.call("/sbin/ifup wan")
            --sys.call("/sbin/ifup wan6")
        elseif content and string.find(content, "MT5700") then
			--io.popen("/usr/share/modem/mt5700m.sh &")     
        end
    end
end
return m,m2

