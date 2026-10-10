module("luci.controller.mwrtdisclaimer", package.seeall)

-- 免责说明弹窗的后端。
--
-- 只做两件事:接收"我已同意"并落盘标识文件,以及在标识不存在时告诉前端要弹窗。
-- 判断逻辑本身放在全局 footer.ut 里(服务端 gate),已同意的用户连 JS 都不会下发,
-- 所以这里的 status 接口只是给外部脚本留的查询口,正常流程用不到。
--
-- 标识文件放 /usr/bin/ 是跟着本固件既有约定走的
-- (faninitair.conf / fanspeed.conf / modemflag.conf 都在那儿),
-- 这个目录在 overlay 上,重启保留、刷机清空 —— 正好是"刷机后重新弹一次"的语义。

local FLAG = "/usr/bin/disclaimer.conf"

function index()
	-- 不挂菜单,纯接口
	entry({"admin", "mwrtdisclaimer", "accept"}, call("action_accept"))
	entry({"admin", "mwrtdisclaimer", "status"}, call("action_status"))
end

local function accepted()
	return nixio.fs.access(FLAG)
end

function action_status()
	luci.http.prepare_content("application/json")
	luci.http.write_json({ accepted = accepted() and true or false })
end

function action_accept()
	local fs = require "nixio.fs"
	local ok = false

	if accepted() then
		-- 重复提交(比如用户开了两个标签页)不算失败
		ok = true
	else
		local when = os.date("%Y-%m-%d %H:%M:%S")
		ok = fs.writefile(FLAG, "accepted " .. when .. "\n") and true or false
		-- writefile 在个别版本返回 nil 但其实写成功了,以文件是否存在为准
		if not ok then ok = accepted() end
	end

	luci.http.prepare_content("application/json")
	luci.http.write_json({ ok = ok })
end
