module("luci.controller.ultraports", package.seeall)

function index()
    entry({"admin", "network", "ultra_ports"}, template("ultra_ports"), _("网口切换"), 65)
    for _, name in ipairs({"status", "apply", "confirm", "rollback", "probe", "ignore"}) do
        local e = entry({"admin", "network", "ultra_ports", name}, call("action_" .. name))
        e.leaf = true
    end
end

local function invoke(action, write)
    local http = require "luci.http"
    local dsp = require "luci.dispatcher"
    if write and not dsp.test_post_security() then return end
    local json = require "luci.jsonc"
    local nx = require "nixio"
    require "nixio.util"
    local payload = {}
    if write then
        for _, name in ipairs({"id", "mode", "proto", "username", "password", "ipaddr", "netmask", "gateway", "dns"}) do
            local v = http.formvalue(name)
            if v ~= nil then
                if type(v) ~= "string" or #v > 1024 then
                    http.status(400, "Bad Request")
                    http.prepare_content("application/json")
                    http.write_json({ok=false, error="请求参数过长或不正确"})
                    return
                end
                payload[name] = v
            end
        end
    end
    -- Nixio returns an already-unlinked temporary file descriptor. Credentials
    -- stay in tmpfs/stdin and never appear in shell arguments or named files.
    local fd = nx.mkstemp("/tmp/ultra-ports-request.XXXXXX")
    if not fd then
        http.status(503, "Service Unavailable")
        return
    end
    local encoded = json.stringify(payload)
    local n = fd:writeall(encoded)
    local output
    if n == #encoded then
        fd:seek(0, "set")
        local r, w = nx.pipe()
        local pid = nx.fork()
        if pid == 0 then
            -- ucodebridge can start Lua with fd 0 closed. mkstemp then owns
            -- fd 0: duplicate it first so closing the source keeps stdin alive.
            if fd:fileno() < 3 then
                local copy = nx.dup(fd)
                if not copy then os.exit(126) end
                fd:close()
                fd = copy
            end
            nx.dup(fd, nx.stdin)
            nx.dup(w, nx.stdout)
            r:close(); w:close(); fd:close()
            local null = nx.open("/dev/null", "w")
            if null then nx.dup(null, nx.stderr); null:close() end
            nx.exec("/usr/libexec/ultra-ports", action)
            os.exit(127)
        elseif pid then
            w:close(); fd:close(); fd=nil
            output = r:readall()
            r:close()
            nx.waitpid(pid)
        else
            r:close(); w:close()
        end
    end
    if fd then fd:close() end
    local result = output and json.parse(output)
    http.prepare_content("application/json")
    http.header("Cache-Control", "no-store")
    http.write_json(type(result) == "table" and result or {ok=false, error="网口服务暂不可用"})
end

function action_status() invoke("status", false) end
function action_apply() invoke("apply", true) end
function action_confirm() invoke("confirm", true) end
function action_rollback() invoke("rollback", true) end
function action_probe() invoke("probe", false) end
function action_ignore() invoke("ignore", true) end
