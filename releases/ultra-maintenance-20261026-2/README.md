# Ultra OpenClash与Mihomo升级包

将OpenClash更新至上游稳定版v0.48.002，Mihomo更新至v1.19.33，并修复新版订阅弹窗标签与当前LuCI自动标签控件的冲突。保留原配置、订阅、自定义覆写、节点选择和PCDN绕过。

## 安装与回退

本包适用于本项目Ultra25.12、Linux6.12.103，OpenClash为0.47.156或0.48.002的设备。它单独更新代理组件，早期固件的其他维护补丁仍按对应版本安装。

将附件`ultra-maintenance-20261026-2-upgrade.tar.gz`上传至路由器TF卡的可写目录，解压并执行：

```sh
tar -xzf ultra-maintenance-20261026-2-upgrade.tar.gz
python3 ultra-maintenance-20261026-2/install.py apply
```

安装器验证安装包和核心摘要，将原核心、配置及对应回退包备份至`/overlay/ultra-hotfix-backups/openclash-20261026-r2`。升级暂存使用TF存储。原来启用代理时会重启OpenClash，连接短暂重连；无需整机重启。已运行相同代码与核心时重复执行不改动文件。

回退：

```sh
python3 ultra-maintenance-20261026-2/install.py rollback
```

## 版本与验证

- OpenClash上游v0.48.002，固件适配包0.48.002-rultra1；上游包SHA-256已核对。
- Mihomo官方ARM64稳定版v1.19.33，解压前后均校验。
- 订阅弹窗使用独立`data-oc-tpl-tab`属性，避免LuCI初始化时出现classList错误。
- 实机代理访问Google返回204、GitHub返回200，IPv4/IPv6直连均返回200。
- 8929条规则的内容和顺序、9个代理组选择、原订阅及PCDN绕过集合保持一致。
- 118个运行代码文件与编译包一致，浏览器显示新版本且无脚本错误。
- 123秒13组监测核心进程稳定，CPU14.8%至20.4%，后台检查13次成功；安装、重复安装、失败回退及错误输入测试通过。

本包只包含通用代码和上游公开文件。已有个人配置由安装时在设备上备份。

[完整r12固件](../ultra-25.12-20261026-r12/README.md)单独发布。
