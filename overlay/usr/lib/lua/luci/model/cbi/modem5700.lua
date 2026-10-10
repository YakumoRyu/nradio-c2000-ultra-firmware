local m, section, m2, s2
m = Map("mwrt", translate("MT5700M-CN模组其他设定"))

-- ── 渲染期开销收敛(2026-09-24) ────────────────────────────────────────────
-- 这一页原来 TTFB 1.03s,其余页面是 76ms。多出来的 950ms 全在**模型顶层**:
-- CBI 模型每次 GET 都整体重新执行一遍,顶层每一句 io.popen/os.execute 都是
-- 一次串行 fork,浏览器只能干等。实测各项:
--     LQXH.sh (AT^MONNC 读邻区) 330ms
--     sendat 1 AT+CGSN          200ms
--     sed -n Np /tmp/LQXH.file  10 次 ≈ 100ms
--     lsusb                     4 次 × 40ms = 160ms
--     lspci                     50ms
-- 两条治法,都不改页面行为:
--   1) 同一份输出只取一次 —— lsusb memo 到本地变量;邻区那 10 行改成读一次
--      文件再按行取,不再每行 fork 一个 sed。
--   2) 关着的功能不预热 —— "显示邻区"(enable_imei2) 和 "ModifyI"(enable_imei)
--      默认都是 0,字段被 :depends 隐藏,但 Lua CBI 仍会在服务端求值,于是那两条
--      AT 命令每次都白跑 530ms。改成只有开关真的打开时才去问模组;开关一打开
--      并保存,页面重载时自然就取到了。
-- 注意 AT 串口是全局独占资源(ttyUSB1),这两条 AT 命令同时也是 tom_modem 争用的
-- 来源之一,少跑两条对整机都有好处。
local _lsusb_memo
local function lsusb_cached()
	if _lsusb_memo == nil then
		_lsusb_memo = luci.sys.exec("lsusb 2>/dev/null") or ""
	end
	return _lsusb_memo
end

local function has_5700()
	return lsusb_cached():find("5700", 1, true) ~= nil
end

-- 开关是否打开。取 Map 自己的 cursor(cbi.lua:307),不另开一个 —— uci cursor 在
-- 同一请求内是单例,另开一个读不到 parse 阶段刚写进去的值。
local function flag_on(name)
	return m.uci:get_first("mwrt", "ndis", name) == "1"
end

-- 这些取值一律**懒加载**,不在顶层直接跑。原因:DummyValue.cfgvalue 是渲染阶段
-- 才调用的,而 Map:parse(提交新的开关值)排在渲染之前。如果在顶层按开关判断,
-- 那么"勾上开关并保存"这一次 POST 里,顶层读到的还是旧值 0 → 不取数,渲染阶段
-- 开关却已经是 1 → 显示空白,要再刷一次才有内容。懒加载天然避开这个时序。
local _at_memo = {}
local function at_once(key, cmd)
	if _at_memo[key] == nil then
		_at_memo[key] = luci.sys.exec(cmd) or ""
	end
	return _at_memo[key]
end

-- /tmp/modconf.conf 原来被 `io.popen("cat ...")` 读了 3 遍。popen 每次是
-- sh -c + cat 两个进程,读一个普通文件不需要这样。改成 io.open 读一次并缓存。
local _modconf_memo
local function modconf()
	if _modconf_memo == nil then
		local fh = io.open("/tmp/modconf.conf", "r")
		if fh then
			_modconf_memo = fh:read("*a") or ""
			fh:close()
		else
			_modconf_memo = ""
		end
	end
	return _modconf_memo
end
section = m:section(TypedSection, "ndis", translate("巴龙模组WEBUI与转发/网络检查设置"))
section.anonymous = true
section.addremove = false
section:tab("general", translate("常规设置"))
-- 2026-09-25 「高级设置」整个页签停用(内容见下面那段长注释)。只注释内容、留着
-- 页签声明的话会渲染出一个空壳页签,所以声明一起注释掉。
--section:tab("advanced", translate("高级设置"))

-- 卡槽选择:三卡槽(外置SIM1/外置SIM2/内置卡)是 C2000 系列(MAX/Ultra)专属的硬件布局。
-- 其余机型(H5000M 等)物理上只有一个卡槽,对应 C2000 的"外置SIM2卡槽"(simsel=6 —— 早期
-- X86 5700 的注释里即把 6 标注为"转接板或机身卡槽")。所以非 C2000 只给这一个选项、标签
-- "机身卡槽",绝不暴露 C2000 的多卡槽,免得误切到本机不存在的卡槽。判据与 router3d-data /
-- 页脚一致:机型串(model + board_name)是否含 C2000。
local function _rd_sim(p)
	local f = io.open(p, "r"); if not f then return "" end
	local s = f:read("*a") or ""; f:close(); return s
end
local _sim_isc2000 = (_rd_sim("/tmp/sysinfo/model") .. " " .. _rd_sim("/tmp/sysinfo/board_name")):lower():find("c2000", 1, true) ~= nil

simsel= section:taboption("general", ListValue, "simsel", translate("卡槽选择"))
if _sim_isc2000 then
	simsel:value("0", translate("外置SIM1卡槽"))
	simsel:value("6", translate("外置SIM2卡槽"))
	simsel:value("1", translate("内置卡"))
else
	simsel:value("6", translate("机身卡槽"))
	simsel.default = "6"
end
simsel.rmempty = true

local content = modconf()
if (content and string.find(content, "5700")) or (content and string.find(content, "MT5700M-CN")) then
    -- MT5700-SIM卡状态(实时轮询,无需刷新页面)
    --
    -- 原写法是页面渲染时同步跑一次 sendat,把结果当死字符串塞进 DummyValue。
    -- 但切卡脚本 mt5700m.sh 是后台跑的,要 30 秒才完事,那时页面早渲染完了,
    -- 所以"保存并应用"后看到的永远是切换前的旧状态。
    -- 现在只放一个占位容器,内容由下面的 JS 轮询 admin/modem/simstat 填充。
    sim_card_stat = section:taboption("general", DummyValue, "sim_card_stat", translate("SIM状态"))
    sim_card_stat.rawhtml = true

    local simstat_url = luci.dispatcher.build_url("admin", "modem", "simstat")
    -- 用 [==[ ]==] 而不是 [[ ]]:JS 结尾的 //]]> 里含 ]],会提前截断长字符串
    sim_card_stat.value = [==[<span id="mwrt_simstat">正在读取…</span>
<script type="text/javascript">//<![CDATA[
(function () {
    var URL  = ']==] .. simstat_url .. [==[';
    var SLOW = 5000, FAST = 1500;
    var timer = null, busyBefore = false;

    function paint(el, d) {
        var color = '#888', mark = '';
        if (d.busy) {
            color = '#e8a33d'; mark = '↻ ';
        } else if (d.code == '1' || d.code == '11' || d.code == '12') {
            color = '#4caf50'; mark = '✔ ';
        } else if (d.code !== '') {
            color = '#d9534f'; mark = '✘ ';
        }
        var html = '<span style="color:' + color + ';font-weight:bold">'
                 + mark + (d.text || '') + '</span>';
        if (d.slot)
            html += ' <span style="color:#888">[' + d.slot + ']</span>';
        if (d.iccid)
            html += '<br><span style="color:#888;font-size:90%">ICCID: '
                  + d.iccid + '</span>';
        el.innerHTML = html;
    }

    function schedule(ms) {
        if (timer) window.clearTimeout(timer);
        timer = window.setTimeout(poll, ms);
    }

    function poll() {
        var el = document.getElementById('mwrt_simstat');
        if (!el) { schedule(SLOW); return; }

        var x = new XMLHttpRequest();
        x.open('GET', URL + '?_=' + Date.now(), true);
        x.timeout = 20000;
        x.onreadystatechange = function () {
            if (x.readyState != 4) return;
            if (x.status == 200) {
                var d;
                try { d = JSON.parse(x.responseText); }
                catch (e) { schedule(SLOW); return; }
                paint(el, d);
                // 切换刚结束的那一拍再快查一次,确保拿到稳定后的终态
                var next = (d.busy || busyBefore) ? FAST : SLOW;
                busyBefore = !!d.busy;
                schedule(next);
            } else {
                schedule(SLOW);
            }
        };
        x.ontimeout = function () { schedule(SLOW); };
        x.onerror   = function () { schedule(SLOW); };
        x.send();
    }

    // 点"保存并应用"之后切卡脚本才起来,这里立刻转入快轮询去等它
    document.addEventListener('click', function (ev) {
        var t = ev.target;
        if (t && t.name &&
            (t.name.indexOf('cbi.apply') === 0 || t.name.indexOf('cbi.save') === 0)) {
            busyBefore = true;
            schedule(FAST);
        }
    }, true);

    if (document.readyState === 'loading')
        document.addEventListener('DOMContentLoaded', poll);
    else
        poll();
})();
//]]></script>]==]
    end
    -- MT5700SIN卡状态查询

-- 当前模组(2026-09-25 美化)。
-- 原来是个可编辑输入框,但它本质是只读信息:cfgvalue 恒定返回从 lsusb 解析出来的
-- 型号,uci 里从来没有这一项 —— 输入框里改了也会被下一次渲染盖回去(而且 parse
-- 阶段 formvalue 与 cfgvalue 相等会被判定"未改动"、压根不写 uci)。既然是只读的,
-- 就按只读信息渲染:DummyValue + rawhtml,给一枚带状态点的徽标,顺带把同一行
-- lsusb 里已有的厂商、VID:PID、以及挂在哪一代 USB 口上一并标出来 —— 这些都从
-- 已缓存的 lsusb 输出里就地解析,不多花任何一次 fork。
current_mod = section:taboption("general", DummyValue, "current_mod", translate("当前模组"))
current_mod.rawhtml = true

function current_mod.cfgvalue(self, section)
    local xml = require "luci.xml"
    local keywords = {
        "quectel", "fibocom", "huawei", "zte", "sierra", "cinterion", "longsung",
        "meig", "me909", "simcom", "foxconn", "alcatel", "ublox", "telit",
        "td tech", "td-tech", "tdtech", "td500", "td510"
    }
    local raw = lsusb_cached()

    -- 根集线器的 ID 标明该总线的代次:1d6b:0003 = USB 3.x,1d6b:0002 = USB 2.0。
    -- 拿来告诉你模组到底挂在高速口还是 2.0 口上(这台机器上它必须在 3.0 那条)。
    local busgen = {}
    for line in raw:gmatch("[^\r\n]+") do
        local bus, id = line:match("^Bus (%d+) Device %d+: ID (%x+:%x+)")
        if bus and id == "1d6b:0003" then
            busgen[bus] = "USB 3.x"
        elseif bus and id == "1d6b:0002" then
            busgen[bus] = "USB 2.0"
        end
    end

    for line in raw:gmatch("[^\r\n]+") do
        local low = line:lower()
        for _, key in ipairs(keywords) do
            if low:find(key, 1, true) then
                local bus, vidpid, desc =
                    line:match("^Bus (%d+) Device %d+: ID (%x+:%x+)%s*(.*)$")
                desc = desc or ""
                -- 型号取描述串的最后一段(与原来的取法一致)。厂商就是它前面那截 ——
                -- 用长度截取而不是再拼一个 pattern,免得型号里的 '-' 之类被当成元字符。
                local name = desc:match("([%w%-]+)%s*$") or line
                local vendor = ""
                if #desc >= #name then
                    vendor = (desc:sub(1, #desc - #name):gsub("%s+$", ""))
                end

                local meta = {}
                if #vendor > 0 then meta[#meta + 1] = vendor end
                if vidpid then meta[#meta + 1] = vidpid end
                if bus and busgen[bus] then
                    meta[#meta + 1] = busgen[bus] .. " / Bus " .. bus
                end

                local html = "<span class=\"mwrt-modbadge is-ok\">"
                          .. "<span class=\"mwrt-modbadge-dot\"></span>"
                          .. "<span class=\"mwrt-modbadge-name\">"
                          .. xml.pcdata(name) .. "</span></span>"
                if #meta > 0 then
                    html = html .. "<span class=\"mwrt-modbadge-meta\">"
                                .. xml.pcdata(table.concat(meta, " · "))
                                .. "</span>"
                end
                return html
            end
        end
    end

    return "<span class=\"mwrt-modbadge is-none\">"
        .. "<span class=\"mwrt-modbadge-dot\"></span>"
        .. "<span class=\"mwrt-modbadge-name\">" .. translate("未检测到USB模组")
        .. "</span></span>"
end

-- 命令输出面板(2026-09-25 美化)。
-- 原来是 inline style 写死的黑底亮黄 + white-space:pre,没有任何溢出处理 ——
-- lspci 最长一行 131 字符、lsusb 63 字符,浏览器一缩放(CSS 视口变窄)内容就直接
-- 跑到盒子外面去,看不见也拉不回来。改成 <pre class="mwrt-cmdout">:
--   · 用 <pre> 而不是 <div>:万一 aurora 那张表没加载上,<pre> 靠浏览器自带的
--     white-space:pre 也还能保持对齐,<div> 会塌成一坨;
--   · 长相(横向滚动、配色、滚动条)交给 mwrt-aurora-chrome.css §16,
--     和 luci-app-Airpifanctrl 的「屏幕保护」页共用同一套,不再各写一份 inline;
--   · 输出过 pcdata 转义 —— 描述串来自设备,理论上可以带 < > & 把版面打破。
local function cmd_panel(text)
    return "<pre class=\"mwrt-cmdout\">"
        .. require("luci.xml").pcdata(text or "")
        .. "</pre>"
end

local s = m:section(SimpleSection)
s.title = "USB 设备信息 /lsusb"
s.description = cmd_panel(lsusb_cached())

local s = m:section(SimpleSection)
s.title = "PCI 设备信息 /lspci"
s.description = cmd_panel(luci.sys.exec("lspci 2>/dev/null"))

-----------------------------------------------------------------
-----------------------------------------------------------------
section:tab("WEBUI", translate("WEBUI选项与转发"), translate("适用于MT5700M-CN模组WEBUI服务设置,更改WebSocket IP和端口后webui界面需要修改相应参数。"))
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
wechat_webhook = section:taboption("WEBUI", Value, "wechat_webhook", translate("PPS+平台转发Token"),translate("Token申请请微信搜索公众号“pushplus推送加”，然后根据教程开通即可获取。"))
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

    local config_file = "/usr/bin/config5700.json"

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
            luci.http.write("<script>alert('RM520模组无法使用次WEBUI！')</script>")
		elseif content88 and string.find(content88, "RM500U") then
            luci.http.write("<script>alert('RM500模组无法使用次WEBUI！')</script>")
		elseif content88 and string.find(content88, "MT5700") then
            --os.execute("rm -f /usr/bin/config.json")
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
----------------------------------------------
--[==[ 2026-09-25 以下四组功能整体停用(用不上,按要求注释掉,不删源码以便将来恢复):
        1) IPV6 操作          —— section:tab("ipv6", ...) 及 ipv6mode / ipv6btn
        2) 高级设置整个页签    —— 显示邻区(enable_imei2 + 邻信号1..10)、ModifyI
                                 (enable_imei / modify_imei)、模组重置(initmodem)、
                                 IP直通开关(initmodem2/initmodem3)、IP直通状态(ips_status)
        3) 网络检查            —— section:tab("Networkchek", ...)、健康检查开关、
                                 网络检查地址、检测延迟
        4) 管理AK68            —— manage_ak68 及其三个从属项(关闭/打开AK控制模式、
                                 AKCT状态),这些原本挂在「常规设置」页签下

      注释掉之后顺带省下的开销(这页原来慢就是这些东西堆出来的,见 §页首注释):
        · LQXH.sh 邻区扫描(330ms,占 ttyUSB1)—— 连惰性调用一起没了
        · AT+CGSN(200ms,占 ttyUSB1)
        · ubus call network.interface.5700wan status(IP直通状态要用)
        · ping -c 4(只在保存网络检查地址时跑,但字段没了也就不会触发)

      注意这一段刻意用了**带两个等号**的那一级长注释(开头那行),因为区间内有 11 处
      普通的双中括号闭合符号(几个 shell 脚本长字符串,以及 AKCT/IP直通状态那几个
      内联 span)。若改用不带等号的普通长注释,会在区间内第一个双中括号处就提前闭合,
      后面的代码漏出来必然语法错。同理,这段说明里不能把闭合符号原样写出来 ——
      写出来就当场把注释关掉了(第一版就是这么踩的)。
      要恢复某一组,把对应那几行单独搬出这段注释即可。

      保留未动的:常规设置(卡槽选择 / SIM状态 / 当前模组)、WEBUI选项与转发、
      Internal testing(ATA),以及页尾的 lsusb/lspci 面板。

local content2 = modconf()

if content2 ~= "" then
   if string.find(content2, "RM520") then
       section:tab("ipv6", translate("当前OP固件不适用于RM520N模组,请刷移远固件！"), translate("当前OP固件不适用于RM520N模组,请刷移远固件！"))
   else
      if string.find(content2, "MT5700") then
        section:tab("ipv6", translate("IPV6操作"), translate("温馨提示：请选择你需要的IPV6执行结果后点击按钮完成设置。"))
        local ipv6mode = section:taboption("ipv6", ListValue, "ipv6mode", translate("IPV6模式选择"))
        ipv6mode:value("full", translate("打开IPV6通信"))
        ipv6mode:value("half", translate("仅限CPE开IPV6"))
        ipv6mode:value("off", translate("关闭IPV6通信"))
        local ipv6btn = section:taboption("ipv6", Button, "ipv6btn", translate("执行选择模式"), translate("执行选择的模式，点击按钮即可生效，重启不会重新执行。"))
        function ipv6btn.write(self, section)
            local mode = ipv6mode:formvalue(section)
            if not mode then
                luci.http.write("<script>alert('无效的模式选择！')</script>")
                return
            end
          
            if mode == "full" then
                command = '/usr/bin/full_ipv6.run'
                message = {
                    done = translate("已完成打开IPV6动作，为了确保IPV6地址下发，建议使你的设备重新连接CPE以便于获取IPV6地址！"),
                    fail = translate("执行失败：")
                }
            elseif mode == "half" then
                command = '/usr/bin/half_ipv6.run'
                message = {
                    done = translate("已完成仅限CPE开IPV6，此模式你的设备不接入IPV6，但CPE本身可以通过IPV6通信！"),
                    fail = translate("执行失败：")
                }
            elseif mode == "off" then
                command = '/usr/bin/turn_off_ipv6.run'
                message = {
                    done = translate("已完成关闭所有IPV6通信，此模式CPE和你的设备都不通过IPV6通信！"),
                    fail = translate("执行失败：")
                }
                luci.http.write("<script>alert('关闭IPV6需要等待数秒，请点击后等待完成，请不要刷新页面和操作其他！')</script>")
            end
        
            if command then
                local handle = io.popen(command, "r")
                local result = handle:read("*a")
                handle:close()
        
                if result:find("Done") then
                    luci.http.write("<script>alert('" .. message.done .. "')</script>")
                else
                    luci.http.write("<script>alert('" .. message.fail .. result .. "')</script>")
                end
            end
        end
      end
       --section:tab("ipv6"):addoption("note", translate("当前模组暂不支持IPV6设置"))
   end
else
   --section:tab("ipv6", translate("未检测到模组信息或不支持"), translate("当前未检测到模组信息，请不要操作以下参数。"))
end
-------------------------------------------------------
local has_modem1 = has_5700()
    if has_modem1 then
        -- LQXH.sh 走 AT^MONNC 扫邻区,330ms,而且占用 ttyUSB1。原来无条件在顶层
        -- 跑,可"显示邻区"默认是关的,那 330ms 每次开页面都白付。改成由下面的
        -- lqxh_lines() 在真的要渲染邻区行时才跑一次。
        enable_imei2 = section:taboption("advanced", Flag, "enable_imei2", translate("显示邻区"))
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

-- 邻区数据:整份读一次、按行切好缓存。原来每一行都 fork 一个
-- `sed -n Np /tmp/LQXH.file`,10 行就是 10 次 fork(≈100ms);扫描本身
-- (LQXH.sh,330ms + 占 ttyUSB1)也挪到这里 —— 只有真要渲染邻区时才跑。
-- 首次调用才动手,所以"显示邻区"关着的时候这两笔都是 0。
--
-- 为什么门控必须放在这里、而且必须读开关:
--   Lua CBI 的 :depends 只产生**客户端**的显隐 JS,服务端照样会对隐藏字段调
--   cfgvalue(cbi.lua:1468 的 render 无条件走 Node.render,模板里再取值)。
--   所以"字段被隐藏"省不掉任何开销,只有显式判断开关才省得掉。
--   而判断点放在渲染期(cfgvalue 里)而不是模型顶层,是因为 parse 排在 render
--   之前(dispatcher.lua:343 先 parse、352 才 render):勾上开关并保存的那一次
--   POST,顶层读到的还是旧值 0,渲染时开关却已是 1 —— 放顶层会让第一次保存后
--   看到空白,得再刷一次。
local _lqxh_lines
local function lqxh_lines()
    if _lqxh_lines == nil then
        _lqxh_lines = {}
        if has_modem1 and flag_on("enable_imei2") then
            luci.sys.exec("/usr/bin/LQXH.sh > /tmp/LQXH.file || echo '-' > /tmp/LQXH.file")
            -- 直接读文件,省掉每行一个 sed 的 fork
            local fh = io.open("/tmp/LQXH.file", "r")
            if fh then
                local raw = fh:read("*a") or ""
                fh:close()
                for line in raw:gmatch("[^\r\n]+") do
                    _lqxh_lines[#_lqxh_lines + 1] = line
                end
            end
        end
    end
    return _lqxh_lines
end

local function render_signal(name, line_number)
    local raw_value = lqxh_lines()[line_number] or ""
    local mode = raw_value:match("模式(%w+)")
    local earfcn = raw_value:match("频点:(%d+)")
    local pci = raw_value:match("小区:(%d+)")
    local rsrp_value = tonumber(raw_value:match("信号:(%-?%d+)")) or -140
    local signalDisplay = createSignalBar(rsrp_value)
    return string.format("%s | 模式 %s | 频点： %s | 小区PCI： %s |  信号： %s", name, mode or "N/A", earfcn or "N/A", pci or "N/A", signalDisplay)
end

modify_imei2 = section:taboption("advanced", DummyValue, "modify_imei2", translate("邻信号1"))
modify_imei2.cfgvalue = function()
    return render_signal("节点", 1)
end
modify_imei2:depends("enable_imei2", "1")

modify_imei3 = section:taboption("advanced", DummyValue, "modify_imei3", translate("邻信号2"))
modify_imei3.cfgvalue = function()
    return render_signal("节点", 2)
end
modify_imei3:depends("enable_imei2", "1")

modify_imei4 = section:taboption("advanced", DummyValue, "modify_imei4", translate("邻信号3"))
modify_imei4.cfgvalue = function()
    return render_signal("节点", 3)
end
modify_imei4:depends("enable_imei2", "1")

modify_imei5 = section:taboption("advanced", DummyValue, "modify_imei5", translate("邻信号4"))
modify_imei5.cfgvalue = function()
    return render_signal("节点", 4)
end
modify_imei5:depends("enable_imei2", "1")

modify_imei6 = section:taboption("advanced", DummyValue, "modify_imei6", translate("邻信号5"))
modify_imei6.cfgvalue = function()
    return render_signal("节点", 5)
end
modify_imei6:depends("enable_imei2", "1")

modify_imei7 = section:taboption("advanced", DummyValue, "modify_imei7", translate("邻信号6"))
modify_imei7.cfgvalue = function()
    return render_signal("节点", 6)
end
modify_imei7:depends("enable_imei2", "1")

modify_imei8 = section:taboption("advanced", DummyValue, "modify_imei8", translate("邻信号7"))
modify_imei8.cfgvalue = function()
    return render_signal("节点", 7)
end
modify_imei8:depends("enable_imei2", "1")

modify_imei9 = section:taboption("advanced", DummyValue, "modify_imei9", translate("邻信号8"))
modify_imei9.cfgvalue = function()
    return render_signal("节点", 8)
end
modify_imei9:depends("enable_imei2", "1")

modify_imei10 = section:taboption("advanced", DummyValue, "modify_imei10", translate("邻信号9"))
modify_imei10.cfgvalue = function()
    return render_signal("节点", 9)
end
modify_imei10:depends("enable_imei2", "1")

modify_imei11 = section:taboption("advanced", DummyValue, "modify_imei11", translate("邻信号10"))
modify_imei11.cfgvalue = function()
    return render_signal("节点", 10)
end
modify_imei11:depends("enable_imei2", "1")
---------------------------------------------------------------------------------

local content = modconf()

if (content and string.find(content, "MT5700")) or (content and string.find(content, "5700")) then
    enable_imei = section:taboption("advanced", Flag, "enable_imei", translate("ModifyI"))
    enable_imei.default = false
    enable_imei.rmempty = true
    enable_imei:depends("simsel", "0")
    modify_imei = section:taboption("advanced", Value, "modify_imei", translate("ModifyI"), translate("Warning! Warning! Warning! This is an internal engineering testing program, which is limited to testing whether the module is properly mounted. It is strictly prohibited to use it for other purposes, and the user shall bear all consequences arising from using it for other purposes on their own!"))
    -- 原来这里是 modify_imei.default = luci.sys.exec("sendat 1 AT+CGSN ...") ——
    -- 顶层无条件跑,200ms + 占 ttyUSB1,而 "ModifyI" 默认关着,这 200ms 每次打开
    -- 本页都白付。
    --
    -- 模板取值是 `self:cfgvalue(section) or self.default`(cbi/value.htm),所以把
    -- 兜底值改成由 cfgvalue 在渲染期按开关现取,显示效果与原来完全一致。
    -- parse 也会调 cfgvalue(cbi.lua:1502),这里的语义仍然安全:uci 里已有值时原样
    -- 返回;没有值且开关开着时返回模组读回的 IMEI,表单提交同一个值则判定未改动、
    -- 不写 uci —— 与原先"default 只用于显示"的行为一致。
    modify_imei.default = ""
    local _imei_cfgvalue = modify_imei.cfgvalue
    modify_imei.cfgvalue = function(self, section)
        local v = _imei_cfgvalue(self, section)
        if v and #v > 0 then return v end
        if flag_on("enable_imei") then
            -- 顺手去掉 sendat 回来的尾部 CR/LF。原写法把 "864...\r\n" 整串塞进
            -- 输入框,而本字段自己的 validate 要求"恰好 15 位数字" —— 带着换行
            -- 存不进去。显示上看不出区别,少一个踩了才知道的坑。
            local v = at_once("cgsn", "sendat 1 AT+CGSN | sed -n '2p'")
            return (v:gsub("%s+$", ""))
        end
        return nil
    end
    modify_imei:depends("enable_imei", "1")
    modify_imei.validate = function(self, value)
       if not value:match("^%d%d%d%d%d%d%d%d%d%d%d%d%d%d%d$") then
           return nil, translate("IMEI必须是15位数字")
      end
      return value
end
end
-- 初始化5700按钮
initmodem = section:taboption("advanced", Button, "initmodem", translate("模组重置"))
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
-- IP直通操作
initmodem2 = section:taboption("advanced", Button, "initmodem2", translate("打开IP直通"))
initmodem2.inputtitle = translate("点击打开IP直通功能(点击立即执行)")
initmodem2.inputstyle = "apply"

-- shell脚本内容
local script = [[
#!/bin/sh
echo "执行开启IP直通操作,模组将重启...
1
#ff0000" > /tmp/lucimsg.file
sendat 1 'AT^TDCFG="infcfg","mode",3'
sleep 1
sendat 1 'AT+CFUN=1,1'
echo "切换完成，重启设备..." > /tmp/lucimsg.file
sleep 2
reboot
]]

if not nixio.fs.access("/tmp/init_57002.sh") then
    local f = io.open("/tmp/init_57002.sh", "w")
    f:write(script)
    f:close()
    luci.sys.call("chmod +x /tmp/init_57002.sh")
end

local function js_escape(str)
    if not str then return "" end
    str = str:gsub("\\", "\\\\")
    str = str:gsub("'", "\\'")
    str = str:gsub('"', '\\"')
    str = str:gsub("\r", "\\r"):gsub("\n", "\\n")
    return str
end

initmodem2.write = function()
    local has_modem = (os.execute("lsusb | grep -q '5700'") == 0)
    if not has_modem then
        luci.http.write("<script>alert('没有检测到MT5700M-CN模组，无法执行。')</script>")
        return
    end

    local handle = io.popen("sendat 1 'ATI'")
    local output = handle:read("*a") or ""
    handle:close()

    local revision_line = output:match("Revision[^\n]*")
    if revision_line then
        -- 提取B后数字
        local bnum = revision_line:match("B(%d+)")
        local version_num = tonumber(bnum)

        if version_num and version_num >= 21 then
            io.popen("/tmp/init_57002.sh &")
        else
            local safe_version = js_escape(revision_line)
            luci.http.write(
                string.format(
                    "<script>alert('检测到你的模组版本低于B021，请升级后再尝试此功能。\\n当前模组固件版本：%s')</script>",
                    safe_version
                )
            )
        end
    else
        luci.http.write("<script>alert('无法读取模组版本信息，请检查设备。')</script>")
    end
end


-- IP直通操作
initmodem3 = section:taboption("advanced", Button, "initmodem3", translate("关闭IP直通"))
initmodem3.inputtitle = translate("点击关闭IP直通功能(点击立即执行)")
initmodem3.inputstyle = "apply"

-- shell脚本内容
local script = [[
#!/bin/sh
echo "执行关闭IP直通操作,模组将重启...
1
#ff0000" > /tmp/lucimsg.file
sendat 1 'AT^TDCFG="infcfg","mode",1'
sleep 1
sendat 1 'AT+CFUN=1,1'
echo "切换完成，重启设备..." > /tmp/lucimsg.file
sleep 2
reboot
]]

if not nixio.fs.access("/tmp/init_57003.sh") then
    local f = io.open("/tmp/init_57003.sh", "w")
    f:write(script)
    f:close()
    luci.sys.call("chmod +x /tmp/init_57003.sh")
end

initmodem3.write = function()
    local has_modem = (os.execute("lsusb | grep -q '5700'") == 0)
    if not has_modem then
        luci.http.write("<script>alert('没有检测到MT5700M-CN模组，无法执行。')</script>")
        return
    end

    local handle = io.popen("sendat 1 'ATI'")
    local output = handle:read("*a") or ""
    handle:close()

    local revision_line = output:match("Revision[^\n]*")
    if revision_line then
        -- 提取B后数字
        local bnum = revision_line:match("B(%d+)")
        local version_num = tonumber(bnum)

        if version_num and version_num >= 21 then
            io.popen("/tmp/init_57003.sh &")
        else
            local safe_version = js_escape(revision_line)
            luci.http.write(
                string.format(
                    "<script>alert('检测到你的模组版本低于B021，请升级后再尝试此功能。\\n当前模组固件版本：%s')</script>",
                    safe_version
                )
            )
        end
    else
        luci.http.write("<script>alert('无法读取模组版本信息，请检查设备。')</script>")
    end
end


local util  = require "luci.util"
local jsonc = require "luci.jsonc"

local function get_iface_ip(ifname)
    -- 调用 ubus 获取接口信息
    local cmd = string.format("ubus call network.interface.%s status 2>/dev/null", ifname)
    local raw = util.exec(cmd)

    if raw and #raw > 0 then
        local data = jsonc.parse(raw)
        if data and data['ipv4-address'] and #data['ipv4-address'] > 0 then
            return data['ipv4-address'][1].address
        end
    end
    return nil
end

local eth1_ip = get_iface_ip("5700wan")  -- 如果 eth1 是作为 wan 接口
-- 如果你要直接用设备名，也可以用下面方式：
-- local eth1_ip = get_iface_ip("eth1")

local ips_status = section:taboption(
    "advanced",
    DummyValue,
    "_ips_status",
    translate("IP直通状态"),
    translate("打开IP直通WAN口会获取到运营商下发的IP地址,关闭IP直通会获取到模组的管理地址，该功能仅适用于5700模组转网口模式。")
)
ips_status.rawhtml = true

if eth1_ip == "192.168.8.1" then
    ips_status.value = [[<span style="color: green; font-weight: bold;">✔ IP透传未打开</span>]]
elseif eth1_ip and eth1_ip ~= "" then
    ips_status.value = [[<span style="color: green; font-weight: bold;">✔ IP透传已打开</span>]]
else
    ips_status.value = [[<span style="color: yellow; font-weight: bold;">？ 未知状态，请刷新重试</span>]]
end
-----------------------------------------
--------------------AKct

-- 管理 AK68 开关
manage_ak68 = section:taboption("general", Flag, "manage_ak68", translate("管理AK68"))
manage_ak68.default = false
manage_ak68.rmempty = true


-- AKCT close
initmodem4 = section:taboption("general", Button, "initmodem4", translate("关闭AK控制模式"))
initmodem4.inputtitle = translate("点击关闭AK控制模式")
initmodem4.inputstyle = "apply"
initmodem4:depends("manage_ak68", "1")

local script_close = [[
#!/bin/sh
echo "已切关闭AK68模式。
1
#2b9ce7ff" > /tmp/lucimsg.file
rm -f /usr/bin/AK68EN.file
/etc/init.d/modeminit restart
ifdown eth0
ifup eth0
]]

if not nixio.fs.access("/tmp/init_57004.sh") then
    local f = io.open("/tmp/init_57004.sh", "w")
    f:write(script_close)
    f:close()
    luci.sys.call("chmod +x /tmp/init_57004.sh")
end

initmodem4.write = function()
    local has_modem = (os.execute("lsusb | grep -q '5700'") == 0)
    if not has_modem then
        luci.http.write("<script>alert('没有检测到MT5700M-CN模组，无法执行。')</script>")
        return
    end

    os.execute("ps w | grep websocket_server-AK68.py | grep -v grep | awk '{print $1}' | xargs kill -9")
    os.execute("pgrep -f devck-AK68.sh | xargs kill -9")
    os.execute("pgrep -f netmodeled-AK68.sh | xargs kill -9")
    os.execute("rm -f /usr/bin/config5700.json")
    io.popen("/tmp/init_57004.sh &")
end


-- AKCT EN
initmodem5 = section:taboption("general", Button, "initmodem5", translate("打开AK控制模式"))
initmodem5.inputtitle = translate("点击打开AK控制模式")
initmodem5.inputstyle = "apply"
initmodem5:depends("manage_ak68", "1")

local script_open = [[
#!/bin/sh
echo "已切换至AK68模式，请及时将AK68接入到WAN口，如不是鲲鹏设备，需手动新建WAN口。
1
#2392fbff" > /tmp/lucimsg.file
echo "1" > /usr/bin/AK68EN.file
/etc/init.d/modeminit-AK68 restart
]]

if not nixio.fs.access("/tmp/init_57005.sh") then
    local f = io.open("/tmp/init_57005.sh", "w")
    f:write(script_open)
    f:close()
    luci.sys.call("chmod +x /tmp/init_57005.sh")
end

initmodem5.write = function()
    local has_modem = (os.execute("lsusb | grep -q '5700'") == 0)
    if not has_modem then
        luci.http.write("<script>alert('没有检测到MT5700M-CN模组，无法执行。')</script>")
        return
    end
    io.popen("/tmp/init_57005.sh &")
    os.execute("ps w | grep websocket_server.py | grep -v grep | awk '{print $1}' | xargs kill -9")
    os.execute("pgrep -f 5700netchek.sh | xargs kill -9")
    os.execute("pgrep -f netmodeled.sh | xargs kill -9")
end


-- AKCT 状态
local AKCT_status = section:taboption(
    "general",
    DummyValue,
    "_AKCT_status",
    translate("AKCT状态"),
    translate("AKCT打开代表当前设备网络来自于AK68，内置模组不工作，关闭则内置模组工作。")
)
AKCT_status.rawhtml = true
AKCT_status:depends("manage_ak68", "1")

local ls = lsusb_cached()
if ls:find("5700") then
    if nixio.fs.access("/usr/bin/AK68EN.file") then
        AKCT_status.value = [[<span style="color: green; font-weight: bold;">✔ AKCT已打开</span>]]
    else
        AKCT_status.value = [[<span style="color: red; font-weight: bold;">x AKCT未打开</span>]]
    end
else
    AKCT_status.value = [[<span style="color: yellow; font-weight: bold;">无内置5700模组，不可操作。</span>]]
end
]==]
-- ↑↑↑ 停用区间到此结束(IPV6操作 / 高级设置 / 网络检查 / 管理AK68)↑↑↑
-----------------------------------
section:tab("ATA", translate("Internal testing"),translate("提示：该功能需要将移动网络--WEB界面--短信中心--设置--短信开关打开并后才能使用;Warning! Warning! Warning! This is an internal engineering testing program, which is limited to testing whether the module is properly mounted. It is strictly prohibited to use it for other purposes, and the user shall bear all consequences arising from using it for other purposes on their own!"))
local number5 = section:taboption("ATA", Value, "number1", translate("号码"))
local take_btn = section:taboption("ATA", Button, "take", translate("Cell out"))
local takeof_btn = section:taboption("ATA", Button, "takeof", translate("Cell OFF"))

function take_btn.write(self, section)
    local number6 = number5:formvalue(section)
    if number6 == ""  then
        luci.http.write("<script>alert('输入框不能为空！');</script>")
    else
        local command = 'sendat 1 "' .. 'ATD' .. number6 .. ';"'
        local result = luci.sys.exec(command)
        if result and result:find("OK") then
            luci.http.write("<script>alert('complete！');</script>")
        else
            luci.http.write("<script>alert('Busy or EER！');</script>")
        end
        return nil
    end
    return nil
end

function takeof_btn.write()
    local result = luci.sys.exec('sendat 1 "ATH"')
    if result and result:find("OK") then
        luci.http.write("<script>alert('complete！');</script>")
    else
        luci.http.write("<script>alert('EER！');</script>")
    end
    return nil
end

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
			io.popen("/usr/share/modem/mt5700m.sh &")     
        end
    end
end
return m,m2

