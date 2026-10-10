# 上游来源与许可

这是多组件固件维护仓库，各组件保留自己的版权、许可和上游署名。

| 组件 | 来源 | 维护方式 |
| --- | --- | --- |
| ImmortalWrt 与 MediaTek 适配基线 | chasey-dev/immortalwrt-mt798x-rebase | 固定提交、附加板级/升级补丁 |
| QModem | FUjr/QModem | 固定提交、生命周期补丁 |
| MT5700 WebUI | inotdream/mt5700webui-openwrt-server | v3.0.2、QModem 共享 AT/SMS 适配 |
| iStore | linkease/istore | 固定提交 |
| v2dat | urlesistiana/v2dat | 固定提交 |
| mii_mgr / switch 兼容包 | padavanonly/immortalwrt-mt798x-6.6 | 包目录保留 SOURCE-ORIGIN |
| Go vendor、前端 npm 依赖 | 各依赖项目 | 保留许可文件和依赖锁 |
| 厂商无线驱动/固件 | 基线中的 MediaTek 配方所指来源 | 沿用原许可，不视为本项目自有开源代码 |
| 历史管理页面和通用维护脚本 | 已脱敏的本地适配工程 | 保留原文件声明；来源待进一步补全的部分不重新声明统一许可 |

源码固定版本见 `sources.lock.json`。适用的上游许可副本见 `LICENSES/`、vendor 和各包目录。不要将本仓库解释为对所有第三方组件统一授予 MIT 或其他许可。
