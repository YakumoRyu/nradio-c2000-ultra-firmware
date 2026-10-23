local fs   = require "nixio.fs"
local sys  = require "luci.sys"
local http = require "luci.http"

local mwrtfile = "/etc/config/mwrtinfo.file"
local is_pure = not fs.access(mwrtfile)

-- "系统切换"(SD↔官方系统 boot 切换)是 C2000 系列专属的双系统设计:靠 SPI NOR 里
-- U-Boot 的 boot_from_sd 标识切换,只有 C2000 MAX/Ultra 才有这套布局。其余机型
-- (E87N 等)没有内置官方系统,不该出现这个功能。判据用机型串是否含 C2000。
local is_c2000 = false
do
    local function _rd(p)
        local f = io.open(p, "r"); if not f then return "" end
        local s = f:read("*a") or ""; f:close(); return s
    end
    local id = (_rd("/tmp/sysinfo/model") .. " " .. _rd("/tmp/sysinfo/board_name")):upper()
    if id:find("C2000", 1, true) then is_c2000 = true end
end

-- ============================================================================
-- 启动系统切换
--
-- 本机跑在 SD 卡上,U-Boot 和它的环境变量都在 SPI NOR 里。开机时 U-Boot 读
-- NOR 上 u-boot-env 分区的 boot_from_sd 标识决定去哪儿启动:
--     1 = 优先从 SD 卡启动(当前 Mwrt 系统)
--     0 = 从内置 flash 启动(官方系统)
-- 改完重启即生效,SD 卡不用拔 —— 想回来把标识改回 1 就行。
--
-- 实际读写交给 /usr/bin/mwrt-bootswitch,它会先确认能读到一份 CRC 正确的
-- env 才允许写。env 分区里还住着 bootcmd 等引导参数,盲写会让机器起不来。
-- ============================================================================

local BOOTSW = "/usr/bin/mwrt-bootswitch"
local has_bootsw = fs.access(BOOTSW)

local bootsw_action = http.formvalue("bootsw")
if has_bootsw and (bootsw_action == "official" or bootsw_action == "sd") then
    if not is_c2000 or not require("luci.dispatcher").test_post_security() then
        http.status(403, "Forbidden")
        return
    end
    local target = (bootsw_action == "official") and "to-official" or "to-sd"
    local name   = (bootsw_action == "official") and "官方系统" or "SD 卡系统"

    -- 写成功才重启。失败就把原因留在页面上,机器保持原样。
    local rc = sys.call(BOOTSW .. " " .. target .. " >/tmp/bootswitch.log 2>&1")
    if rc == 0 then
        sys.call(string.format(
            [[echo '正在切换启动目标为%s，设备即将重启...
70
#ffd500ff' > /tmp/lucimsg.file]], name))
        sys.call("sync")
        sys.call("reboot")
    end
end

-- 上一次切换失败的原因(如果有),显示完一次就够了
local bootsw_err = nil
if bootsw_action and fs.access("/tmp/bootswitch.log") then
    local log = fs.readfile("/tmp/bootswitch.log") or ""
    log = log:gsub("^%s+", ""):gsub("%s+$", "")
    if #log > 0 then bootsw_err = log end
    fs.unlink("/tmp/bootswitch.log")
end

-- 读当前状态
local bs_ready, bs_value, bs_error = false, nil, nil
if has_bootsw then
    local st = sys.exec(BOOTSW .. " status 2>/dev/null") or ""
    bs_ready = st:match('"ready"%s*:%s*true') ~= nil
    bs_value = st:match('"value"%s*:%s*"([^"]*)"')
    bs_error = st:match('"error"%s*:%s*"(.-)"')
else
    bs_error = "未找到 " .. BOOTSW .. "，请确认固件已包含该脚本。"
end

local action = http.formvalue("swiface")
if action == "pure" then
    local nixio = require "nixio"
    local src = "/usr/share/luci/menu.d/"
    local dst = "/usr/share/luci/"
    local files = {
        "luci-app-upnp.json",
        "luci-app-quickstart.json",
        "luci-app-statistics.json",
        "luci-app-ksmbd.json"
    }

    for _, name in ipairs(files) do
        local f1 = src .. name
        local f2 = dst .. name
        if nixio.fs.access(f1) then
            os.execute("mv " .. f1 .. " " .. f2)
        end
    end
    sys.call("rm -f /etc/config/mwrtinfo.file")
    sys.call([[echo '正在切换系统为纯净版，重启完成后尽量保持清理浏览器缓存状态，正在重启设备...
70
#ffd500ff' > /tmp/lucimsg.file]])
    sys.call("reboot")
elseif action == "standard" then
    local nixio = require "nixio"
    local src = "/usr/share/luci/"
    local dst = "/usr/share/luci/menu.d/"
    local files = {
        "luci-app-upnp.json",
        "luci-app-quickstart.json",
        "luci-app-statistics.json",
        "luci-app-ksmbd.json"
    }

    for _, name in ipairs(files) do
        local f1 = src .. name
        local f2 = dst .. name
        if nixio.fs.access(f1) then
            os.execute("mv " .. f1 .. " " .. f2)
        end
    end

    sys.call("touch /etc/config/mwrtinfo.file")
    sys.call([[echo '正在切换系统为常规版，重启完成后尽量保持清理浏览器缓存状态，正在重启设备...
70
#ffd500ff' > /tmp/lucimsg.file]])
    sys.call("reboot")
end

local m = Map("mwrt", translate("Mwrt设定"))
local section = m:section(TypedSection, "ndis", translate("Mwrt固件设置"))
section.anonymous = true
section.addremove = false
section:tab("displayst", translate("屏幕保护/USB网卡开关"))
-- The boot selector does not depend on a legacy mwrt.ndis configuration section.

-- ---- 启动系统切换 UI ------------------------------------------------------
-- 脚本的报错信息会原样进 HTML,这里手工转义。
-- 用 string.char 拼实体,免得改文件的时候把实体本身再转义一遍。
local AMP, LT, GT = string.char(38), string.char(60), string.char(62)
local E_AMP = AMP .. "amp;"
local E_LT  = AMP .. "lt;"
local E_GT  = AMP .. "gt;"
local function esc(s)
    if not s then return "" end
    s = s:gsub(AMP, E_AMP)
    s = s:gsub(LT, E_LT)
    s = s:gsub(GT, E_GT)
    return s
end

local bs_html = {}
local function put(s) bs_html[#bs_html + 1] = s end

put([[<style>
.bsw{max-width:760px;font-size:13px;line-height:1.7}
.bsw-now{display:flex;align-items:center;gap:12px;padding:14px 16px;margin-bottom:14px;
border-radius:10px;background:linear-gradient(135deg,rgba(31,111,235,.08),rgba(20,184,166,.08));
border:1px solid rgba(31,111,235,.22)}
.bsw-dot{width:10px;height:10px;border-radius:50%;flex:0 0 auto;background:#14b885;
box-shadow:0 0 8px #14b885}
.bsw-now b{font-size:15px;color:#1f6feb}
.bsw-tip{padding:12px 14px;margin-bottom:14px;border-radius:8px;font-size:12.5px;
background:#fff8e1;border:1px solid #ffe08a;color:#7a5b00}
.bsw-err{padding:12px 14px;margin-bottom:14px;border-radius:8px;font-size:12.5px;
background:#fdecea;border:1px solid #f5c2c0;color:#a3231d;white-space:pre-wrap;word-break:break-all}
.bsw-steps{margin:10px 0 0;padding-left:20px;color:#5a6680;font-size:12.5px}
.bsw-steps li{margin:3px 0}
.bsw-act{margin-top:4px}
</style>
<div class="bsw">]])

if not bs_ready then
    -- 还没法读写 env,把原因和补救办法直说,不给一个按不动的按钮
    put('<div class="bsw-err"><b>当前固件暂时无法切换</b><br>')
    put(esc(bs_error or "未知原因"))
    put('</div>')
else
    local cur_is_sd = (bs_value == "1")
    local cur_name  = cur_is_sd and "SD 卡系统（Mwrt）" or "设备内置官方系统"

    put('<div class="bsw-now"><span class="bsw-dot"></span><div>当前启动目标：<b>')
    put(esc(cur_name))
    put('</b><br><span style="color:#5a6680;font-size:12px">boot_from_sd = ')
    put(esc(bs_value or "?"))
    put('&nbsp;&nbsp;（1 = SD 卡系统，0 = 官方系统）</span></div></div>')

    if bootsw_err then
        put('<div class="bsw-err"><b>上次切换未成功</b><br>')
        put(esc(bootsw_err))
        put('</div>')
    end

    if cur_is_sd then
        put([[<div class="bsw-tip"><b>切换到官方系统后</b>
<ul class="bsw-steps">
<li>设备重启后进入内置官方系统</li>
<li>TF 卡系统和数据保留</li>
<li>在官方系统里将启动顺序改为存储卡优先，即可切回 TF 卡系统</li>
</ul></div>]])
        put([[<div class="bsw-act">
<input type="button" class="cbi-button cbi-button-reset" value="切换到官方系统并重启"
    onclick="if(confirm('设备将重启并进入内置官方系统，TF 卡系统和数据保留。\n\n确认切换并立即重启？')){document.getElementById('bootsw').value='official';this.form.submit();}">
<input type="hidden" id="bootsw" name="bootsw" value="">
</div>]])
    else
        put([[<div class="bsw-tip">当前设置为从内置官方系统启动。
点下面的按钮改回从 SD 卡启动（即当前 Mwrt 系统）。</div>]])
        put([[<div class="bsw-act">
<input type="button" class="cbi-button cbi-button-apply" value="切回 SD 卡系统并重启"
    onclick="if(confirm('确认改为从 SD 卡启动并立即重启？')){document.getElementById('bootsw').value='sd';this.form.submit();}">
<input type="hidden" id="bootsw" name="bootsw" value="">
</div>]])
    end
end

put('</div>')

if is_c2000 then
    local boot_section = m:section(SimpleSection, translate("系统切换"))
    local btn = boot_section:option(DummyValue, "_bootsw_btn", "")
    btn.rawhtml = true
    btn.cfgvalue = function(self, section)
        return table.concat(bs_html)
    end
end

local rshowtime = section:taboption("displayst", Flag, "rshowtime", translate("屏幕保护"))
rshowtime.rmempty = false
rshowtime.default = 1

local showtime = section:taboption("displayst", ListValue, "showtime", translate("屏幕时间(秒)"))
showtime:depends("rshowtime", "1")
local times = {5,10,20,30,40,50,60,70,80,90,100,120,300,600}
for _,v in ipairs(times) do showtime:value(tostring(v), tostring(v)) end
showtime.rmempty = true
showtime.default = "10"

USBEN = section:taboption("displayst", Flag, "USBEN", translate("USB网口检测开关"),translate("开启USB开关后,USB接口接入外部网卡的时候会自动建立WAN口数据,如果使用的蜂窝模组是RNDIS可能会被误判。"))
USBEN.rmempty = false
USBEN.default=1

-- 命令输出面板(2026-09-25 美化)。
-- 原来是 inline style 写死的黑底亮黄 + white-space:pre,没有任何溢出处理 ——
-- banner 最长一行 119 字符(那个 ASCII art 的字符画),浏览器一缩放(CSS 视口变窄)
-- 内容就跑到盒子外面,看不见也拉不回来。改成 <pre class="mwrt-cmdout">,长相
-- (横向滚动、配色、滚动条)统一交给 mwrt-aurora-chrome.css §16,与模组页共用一套。
-- banner 是 ASCII art,必须保持 pre 不换行,否则字符画会散架 —— §16 里
-- .mwrt-cmdout 就是 pre + overflow-x:auto,正好对上。
-- 输出过 pcdata 转义:banner 现在没有 < > &,但它是可被改的文件,转义掉不吃亏。
local function cmd_panel(text)
    return "<pre class=\"mwrt-cmdout\">"
        .. require("luci.xml").pcdata(text or "")
        .. "</pre>"
end

local s = m:section(SimpleSection)
s.title = "USB 设备信息 /lsusb"
s.description = cmd_panel(luci.sys.exec("lsusb 2>/dev/null"))

local s = m:section(SimpleSection)
s.title = "Banner信息"
s.description = cmd_panel(luci.sys.exec("cat /etc/banner"))

return m
