# NRadio C2000 Ultra 固件维护

面向 **NRadio-C2000MAX-Ultra / C2000Ultra** 的 ImmortalWrt 自编适配项目，维护板级适配、联发科闭源 Wi-Fi 驱动补丁、QModem、巴龙 WebUI 与运行资源保护。

| 项目 | 当前版本 |
| --- | --- |
| 系统 | ImmortalWrt 25.12-SNAPSHOT |
| 内核 | Linux 6.12.103 |
| 无线 | 联发科闭源驱动 8.3.1.2 |
| WebUI | 上游 v3.0.2，QModem 适配包 3.0.2-r2 |
| 固件版本 | ultra-25.12-20261009-r2 |
| 升级格式 | sysupgrade，布局兼容号 2.0，根分区内预留 512 MiB |

本项目是社区自编适配版。只适用于上述 Ultra 板型，不能仅凭名称相近用于 C2000 Max。

## 下载与验证状态

固件与配套离线软件仓库放在 [Releases](https://github.com/YakumoRyu/nradio-c2000-ultra-firmware/releases)，源码、补丁和版本记录由 Git 管理。

当前主固件约 **205.93 MiB**，可选软件仓库约 **144.03 MiB**。保留 Docker、Mihomo、Cloudflared、Python 和原有管理组件，因此体积与精简版不同。

**r2 已完成编译与静态/用户态验收，整镜像尚未刷写或实机启动。** 其中 WebUI 3.0.2 适配包已在运行中的 Ultra 路由器安装，并完成页面、AT 查询和共享短信库验收。发布为预发布版本，不能把单独 WebUI 的验收等同于整固件验收。

- [安装与兼容说明](docs/INSTALL.md)
- [版本验证记录](releases/ultra-25.12-20261009-r2/VERIFICATION.json)
- [更新日志](CHANGELOG.md)
- [源码与构建说明](docs/BUILD.md)
- [维护流程](docs/MAINTENANCE.md)

## 已集成的改动

- Wi-Fi NAPI 无进展空转、QoS 事件边界及逐设备接收错误计数修复。
- Ultra 板型、TF 启动与升级布局适配，保留原登录页面。
- QModem 统一负责模块发现、拨号和 AT 串口，WebUI 经 ubus 调用，避免多个服务争抢串口。
- Web 短信管理和转发共用持久数据库；查看不修改已读位、不领取转发任务，删除使用独立数据库编号。
- PushPlus 通用转发脚本和自定义转发入口，出厂不包含 Token 或个人转发目标。
- UPnP/IPv6 辅助逻辑、设备速率统计、代理恢复及媒体资源保护。
- 1 GiB zram、zstd 6 级通用默认值；路由功能优先于可选媒体服务。

## 个人数据与恢复出厂

公开镜像不包含个人密码、SSH 身份、订阅、私人域名、PushPlus/Cloudflare 凭据、短信库或媒体数据。设备无线校准由本机 Factory 分区生成。

恢复出厂会清理可写区中的个人配置和应用数据；编入只读固件的通用程序与补丁仍保留。使用者需要重新配置网络、密码和服务。私人备份必须自行保管，不应提交到本仓库或 Issue。

## 项目结构

```text
configs/           编译配置
patches/           基线和 QModem 补丁
source-additions/  Ultra DTS、驱动及内核补丁
overlay/           通用只读系统脚本与管理资源
packages/          WebUI 软件包和兼容软件包源码
webui/             React/TypeScript 前端源码
tests/             共享短信兼容检查
releases/          版本说明与公开验收记录
sources.lock.json  上游来源和固定提交
```

大型二进制输入单独记录在 `binary-assets.lock.json`。本仓库提供当前维护源码和配置；完整固件构建还需对应的二进制输入，详见构建说明。不得声称仅克隆仓库即可逐字节复现发布镜像。

## 反馈与迭代

通过 [Issues](https://github.com/YakumoRyu/nradio-c2000-ultra-firmware/issues) 提交设备型号、固件版本、触发步骤和脱敏日志。更新按“复现 → 最小修复 → 回归 → 隐私审计 → 预发布 → 实机验收”的流程进行。当前未设置自动升级生产路由器，也未启用定时无人值守发布。

## 上游与许可

感谢 [ImmortalWrt](https://github.com/immortalwrt/immortalwrt)、[chasey-dev/immortalwrt-mt798x-rebase](https://github.com/chasey-dev/immortalwrt-mt798x-rebase)、[QModem](https://github.com/FUjr/QModem)、[MT5700 WebUI](https://github.com/inotdream/mt5700webui-openwrt-server)、[iStore](https://github.com/linkease/istore) 及其他组件作者。

各上游组件继续适用其原有许可；本仓库不对第三方代码或厂商驱动重新授予统一许可。来源与版权说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 和 `LICENSES/`。
