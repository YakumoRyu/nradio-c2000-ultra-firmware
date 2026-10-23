# Ultra号码、短信与1150适配升级包 — 2026-10-23

适用于本项目r4/r5/r6/r7的NRadio-C2000MAX-Ultra25.12 TF系统，Linux6.12.103。15文件累计包保留个人配置、短信库和转发记录。

## 本次更新

- 修复CNUM把My Number标签当成SIM号码；支持空标签、带逗号标签、国际号码和多行响应。
- 短信管理统一到巴龙WebUI，移除两处重复入口及旧存储/读写接口；保留QModem后台、PushPlus和转发设置。
- 系统切换区域独立于旧ndis配置，显示“切换到官方系统并重启”；切换只接受有效POST/CSRF请求。
- 参考1150补读LTE SINR，修正其字段顺序并过滤无效值。
- 累计包含r7无线DMA恢复和之前的CPU、首页及运营商图标修复。

## 安装与回退

上传`ultra-maintenance-20261023-1-upgrade.tar.gz`到`/tmp`后执行：

```sh
tar -xzf /tmp/ultra-maintenance-20261023-1-upgrade.tar.gz -C /tmp
sh /tmp/ultra-maintenance-20261023-1/install.sh
```

安装后Ctrl+F5刷新页面。r7原驱动保持时无需重启；从较早基线更新驱动时，结果`reboot_required`为true，重启后生效。系统切换在“系统→系统切换/屏保”，点击确认后才更改启动目标并重启。

```sh
python3 /tmp/ultra-maintenance-20261023-1/ultra-maintenance-hotfix.py rollback
```

备份位于`/overlay/ultra-hotfix-backups/maintenance-20261023-r1/`。回退涉及驱动时同样需要重启。恢复出厂后保留ROM修复请使用[完整r8](../ultra-25.12-20261023-r8/README.md)。

## 验证

号码、LTE解析、路由与切换请求4组回归通过；安装器6项及r4/r5/r6/r7归档安装/重复安装/回退检查通过。实机与真实浏览器确认号码、短信会话、旧入口关闭和切换按钮显示，用户确认号码及入口正常。旧短信及投递记录保持，新增短信对应转发任务首次成功。

系统切换的实际官方启动、实机4G回落未执行。验证期间约16:47另记录一次原因未确认的重启，随后网络与服务检查通过。详情见`VERIFICATION.json`和[1150对比](../../docs/MWRT1150_COMPARISON.md)。
