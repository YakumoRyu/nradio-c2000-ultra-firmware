# Ultra累计维护升级包 — 2026-10-16

适用于已安装本项目r4或r5维护更新的NRadio-C2000MAX-Ultra25.12 TF系统。保留个人配置，包含CPU、首页状态和运营商图标修复。

## 更新内容

- 补齐中国移动、电信、广电图标，保留联通资源，修复首页运营商图片404。
- 图片使用版本化地址，仅在来源变化时更新；解码完成后显示，失败时隐藏图片并保留运营商文字。
- 累计包含r5的分钟自愈检查、共享非阻塞CPU采样、状态读取优化及旧PCDN接口JSON修复。
- 8个目标文件采用原始/目标校验值检查，支持r4和r5两种基线，原文件自动备份，安装失败恢复。

## 安装

将`ultra-maintenance-20261016-2-upgrade.tar.gz`上传到路由器`/tmp`，执行：

```sh
tar -xzf /tmp/ultra-maintenance-20261016-2-upgrade.tar.gz -C /tmp
sh /tmp/ultra-maintenance-20261016-2/install.sh
```

安装后刷新管理页。备份位于`/overlay/ultra-hotfix-backups/maintenance-20261016-r2/`；已修复的文件保持原样，重复安装直接返回。

## 回退

回退本包实际更新的文件：

```sh
python3 /tmp/ultra-maintenance-20261016-2/ultra-maintenance-hotfix.py rollback
```

正常重启保留更新；恢复出厂后的通用修复由[完整r6固件](../ultra-25.12-20261016-r6/README.md)提供。

## 验证

图标在线修复完成15项检查：桌面/手机、浅色/深色、4家运营商资源解码、模拟404后隐藏且不重复请求、刷新恢复和源码/实机一致性。累计归档另在r4、r5两种基线完成安装、重复安装与回退，详见`VERIFICATION.json`。

CPU修复沿用r5的实机验证。持续几分钟的网页/后台卡顿仍作为独立故障项跟踪。
