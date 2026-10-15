package.path = "overlay/usr/lib/lua/?.lua;" .. package.path
local fields = require "luci.model.ultra_modem_fields"
assert(fields.value("IMEI", "000000000000000") == "000000000000000")
assert(fields.value("IMEI", "123") == nil)
assert(fields.value("IMEI", "^PDCPDATAINFO: 1,000000000000000,0") == nil)
assert(fields.value("name", "^PDCPDATAINFO: 0,1,2") == nil)
assert(fields.value("name", "MT5700M-CN") == "MT5700M-CN")
assert(fields.value("name", "MT5700M-CN\r\n^CERSSI: 1,2,3") == nil)
local clean = fields.list({{key="name",value="MT5700M-CN"},{key="IMEI",value="^PDCPDATAINFO: 1,2,3"},{key="RSRP",value="-65 dBm"}})
assert(#clean == 2 and clean[2].key == "RSRP")
print("7 modem field validation cases passed")
