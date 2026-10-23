import json,subprocess,tempfile,unittest
from pathlib import Path
R=Path(__file__).resolve().parents[1]
AWK=R/'overlay/usr/share/qmodem/modem_fields.awk'
class ModemFields(unittest.TestCase):
    def parse(self,mode,text):
        p=subprocess.run(['awk','-v','mode='+mode,'-f',str(AWK)],input=text,capture_output=True,text=True,check=True)
        return p.stdout.strip()
    def test_cnum(self):
        cases=[
            ('+CNUM: "My Number","13800138000",129','13800138000'),
            ('AT+CNUM\r\n+CNUM: "","+8613800138000",145\r\nOK','+8613800138000'),
            ('+CNUM: "Work, mobile","13800138000",129','13800138000'),
            ('+CNUM: "My ""Number""","8613800138000",145','+8613800138000'),
            ('+CNUM: ,"13800138000",129','13800138000'),
            ('+CNUM: "My Number",13800138000,129','13800138000'),
            ('^PDCPDATAINFO: 0,12345\n+CNUM: "My Number","13800138000",129','13800138000'),
            ('+CNUM: "My Number","",129',''),
            ('+CNUM: "13800138000","",129',''),
            ('+CNUM: "My Number","unknown",129',''),
            ('+CNUM: "My Number","13800138000',''),
            ('+CNUM: "My Number","1234567890123456",129',''),
            ('+CNUM: "My Number","12",129',''),
            ('+CNUM: "My Number","+123456789012345",145','+123456789012345'),
            ('^CNUM: "Other","13800138000",129',''),
            ('ERROR\n+CME ERROR: 10',''),
            ('+CNUM: "None","",129\n+CNUM: "Valid","13800138000",129','13800138000'),
        ]
        for raw,want in cases:
            with self.subTest(raw=raw):self.assertEqual(self.parse('cnum',raw),want)
    def test_lte_sinr(self):
        for raw,want in [(0,'-20'),(100,'0'),(155,'11'),(250,'30'),(251,'30'),(252,''),(255,''),(65535,''),(-1,'')]:
            with self.subTest(raw=raw):self.assertEqual(self.parse('lte_sinr',f'^HCSQ: "LTE",54,24,{raw},45'),want)
        self.assertEqual(self.parse('lte_sinr','^HCSQ: "NR",54,155,45'),'')
        self.assertEqual(self.parse('lte_sinr','^PDCPDATAINFO: 9,1\n^HCSQ: "LTE",54,24,155,45\r\nOK'),'11')
    def test_luci_routes(self):
        code=r'''
local routes={}
function entry(path,target,title) local item={target=target,title=title};routes[table.concat(path,"/")]=item;return item end
function template(x) return x end
function cbi(x) return x end
function call(x) return x end
function alias(...) return ... end
function firstchild() return {} end
function _(x) return x end
luci={i18n={translate=function(x)return x end}}
nixio={fs={access=function()return false end}}
io.popen=function()return {read=function()return "5700" end,close=function()end}end
dofile(arg[1]);luci.controller.modem.index()
dofile(arg[2]);luci.controller.qmodem_sms.index()
for _,v in ipairs({"smsc","smscs","smslist","smsdel","smssend"})do assert(not routes["admin/modem/"..v]) end
for _,v in ipairs({"modem_sms","send_sms","get_sms","delete_sms","sms_storage"})do local route=routes["admin/modem/qmodem/"..v];assert(route.target=="sms_management_removed" and not route.title) end
assert(routes["admin/modem/qmodem/sms_forward"])
assert(routes["admin/modem/qmodem/sms_forward_extedit"])
assert(routes["admin/modem/webui"])
'''
        self.lua(code,[R/'overlay/usr/lib/lua/luci/controller/modem.lua',R/'overlay/usr/lib/lua/luci/controller/qmodem_sms.lua'])
    def lua(self,code,argv):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'test.lua';p.write_text(code)
            result=subprocess.run(['lua5.1',str(p),*map(str,argv)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
    def test_boot_switch_request_gate(self):
        original=(R/'overlay/usr/lib/lua/luci/model/cbi/mwrt.lua').read_text()
        prefix=original[:original.index('-- 上一次切换失败')]
        cases=[(False,True,0,False),(True,False,0,False),(True,True,1,False),(True,True,0,True)]
        for authorized,board,rc,reboot in cases:
            with self.subTest(authorized=authorized,board=board,rc=rc):
                code='''local calls={};local forbidden=false
package.preload['nixio.fs']=function()return {access=function()return true end}end
package.preload['luci.sys']=function()return {call=function(c)table.insert(calls,c);return RC end}end
package.preload['luci.http']=function()return {formvalue=function()return "official" end,status=function(s)forbidden=s==403 end}end
package.preload['luci.dispatcher']=function()return {test_post_security=function()return AUTH end}end
io.open=function()return {read=function()return MODEL end,close=function()end}end
local function actual()
'''.replace('RC',str(rc)).replace('AUTH',str(authorized).lower()).replace('MODEL','"NRadio-C2000MAX-Ultra"' if board else '"other"')+prefix+'''\nend
actual()
'''
                code+='assert(forbidden=='+str(not authorized or not board).lower()+')\n'
                code+='local reboot=false;for _,c in ipairs(calls)do if c=="reboot"then reboot=true end end;assert(reboot=='+str(reboot).lower()+')\n'
                if not authorized or not board:code+='assert(#calls==0)\n'
                self.lua(code,[])
if __name__=='__main__':unittest.main(verbosity=2)
