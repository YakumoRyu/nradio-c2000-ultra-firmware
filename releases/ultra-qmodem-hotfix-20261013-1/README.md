# 独立升级包：QModem拨号监测修复

适用：本项目NRadio-C2000MAX-Ultra的25.12 TF系统，QModem监测脚本仍使用已维护的结构。这个IPK修复AT查询成功后异常计数未清零的问题；四次分散异常不再累计触发重拨，连续四次异常仍保留恢复拨号。

下载`ultra-qmodem-hotfix_20261013-r1_aarch64_cortex-a53.ipk`，约3.8KB。它是独立补丁包，保留现有配置，不包含内核或完整系统，不应上传到系统刷机入口。

## 安装

在现有Ultra TF系统中使用LuCI“软件包”的上传安装功能，或把IPK上传到`/tmp`后执行：

```sh
opkg install /tmp/ultra-qmodem-hotfix_20261013-r1_aarch64_cortex-a53.ipk
/usr/libexec/ultra-qmodem-hotfix status
```

安装器检查板型、系统基线和待修改代码，备份后原子替换。随后只重新加载procd的拨号监测实例；不调用hang/redial，也不重启AT串口服务或整机。源文件不匹配时拒绝修改。依赖为当前固件已有的qmodem和python3，无需更换内核模块。

成功安装后，`status`应显示`applied: true`。请结合平台在线情况、实际网页及上传观察确认业务正常。

## 回退

```sh
/usr/libexec/ultra-qmodem-hotfix rollback --activate
/usr/libexec/ultra-qmodem-hotfix status
```

原脚本保存在`/overlay/ultra-hotfix-backups/20261013-1/modem_dial.sh.before`。如果后来另行修改过脚本，工具会拒绝覆盖，应先人工核对。回退后的状态应为`applied: false`。确认回退完成后，可选择`opkg remove ultra-qmodem-hotfix`移除工具；仅删除工具不会自动撤销脚本改动。

## 验证和持久性

8项离线回归、源码补丁应用和IPK内容检查通过。升级包已在运行中的Ultra安装，配置、短信读/投递状态及AT owner保持，跨安装的3分钟观察中PCDN持续上传，LAN/WAN无新增错误或丢包。

普通重启后补丁保留；恢复出厂会清理可写区的IPK和热补丁。希望恢复出厂后仍保留修复，应安装[完整r3固件](https://github.com/YakumoRyu/nradio-c2000-ultra-firmware/releases/tag/ultra-25.12-20261013-r3)，其中修复已编入ROM。

本修复针对已复现的异常计数逻辑，不承诺提升带宽或恢复PCDN日收益。短时业务验收也不等于全天收益验收。没有在本轮产生新的短信进行转发端到端测试。
