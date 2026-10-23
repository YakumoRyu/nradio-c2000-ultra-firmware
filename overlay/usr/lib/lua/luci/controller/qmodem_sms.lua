module("luci.controller.qmodem_sms", package.seeall)

-- QModem owns receiving/forwarding. The Balong WebUI owns SMS management.
-- Keep forwarding settings; the duplicate UI and storage/list/write routes stop here.
function index()
    for _, route in ipairs({"modem_sms", "send_sms", "get_sms", "delete_sms", "sms_storage"}) do
        entry({"admin", "modem", "qmodem", route}, call("sms_management_removed"), nil).leaf = true
    end
    entry({"admin", "modem", "qmodem", "sms_forward"}, cbi("qmodem_sms/sms_forward"), luci.i18n.translate("SMS Forward"), 12).leaf = true
    entry({"admin", "modem", "qmodem", "sms_forward_extedit"}, cbi("qmodem_sms/sms_forward_extedit")).leaf = true
end

function sms_management_removed()
    local http = require "luci.http"
    http.status(410, "Gone")
    http.prepare_content("application/json")
    http.write_json({error="短信管理请使用巴龙 WebUI。"})
end
