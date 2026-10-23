# 源码与构建

`sources.lock.json` 固定本次基线、feeds 和外部项目提交。`configs/ultra.config` 是本次软件选择；`patches/base` 和 `source-additions` 包含 Ultra 板级与内核/驱动适配；`patches/qmodem` 包含模块生命周期修复。

## WebUI 开发

Go 后端依赖已 vendor，可独立执行：

```sh
cd packages/at-webserver/src
go test -race -mod=vendor ./...
```

前端使用 Node.js 22 或更新的兼容版本：

```sh
cd webui
npm ci
npm run typecheck
npm run build
cd ..
node tests/test-v302-frontend.cjs
```

前端发布产物放在 `packages/at-webserver/files/www/5700`。更新时先构建并同步产物，核对包版本、页面版本和源码提交。

## 整固件维护输入

1. 检出 `sources.lock.json` 中的基线提交，应用 `patches/base`。
2. 将 `source-additions` 合并到基线，将 `packages/at-webserver`、`packages/luci-app-at-webserver` 放到基线的 `package/custom`。
3. 按锁定提交准备feeds、QModem、iStore、v2dat；依次应用`patches/qmodem/0001`和`0002`，添加`packages/compat` feed。
4. 将`packages/ultra-qmodem-hotfix`放到基线的`package/custom`，与WebUI包一同编译。单独升级包可用`make package/custom/ultra-qmodem-hotfix/compile`构建。
5. 将`packages/ultra-port-manager`放入`package/custom`；将`overlay`放入`files`，使用`configs/ultra.config`，运行`make defconfig`。在打包根文件系统前，将`overlay/www/luci-static/resources/ultra-layout.css`追加到主题`www/luci-static/argon/css/cascade.css`，标记只保留一次。
6. 准备`binary-assets.lock.json`记录的输入，完成依赖检查后构建完整镜像。

本仓库没有把 Docker、Mihomo、Cloudflared、规则库等大型二进制加入 Git。部分历史管理资源的来源与构建链仍需继续整理；当前完整发布镜像来自已验证的本地工程。GitHub Actions执行源码与协议回归，完整固件由本地工程构建并完成镜像审计。

整固件打包后检查板型、FIT/DTB、内核模块 ABI、512 MiB 数据区布局、原登录模板、闭源驱动补丁、隐私和用户态执行，再完成真实设备验收。

拨号计数和升级包回归可独立运行`python3 tests/test-qmodem-hotfix.py`；测试使用模拟硬件操作和临时文件系统，不访问生产模块。

CPU维护更新的回归使用`python3 tests/test-usb-watchdog.py`、`lua5.1 tests/test-cpu-sample.lua`和`python3 tests/test-cpu-hotfix.py`。CPU安装器为`scripts/ultra-cpu-hotfix.py`，发布归档包含5个目标文件与校验清单，完整固件通过`overlay`集成相同文件。

累计维护包使用`scripts/ultra-maintenance-hotfix.py`，当前包含15个目标文件，并记录r4/r5/r6/r7四基线的原始校验值。安装器回归执行`ULTRA_HOTFIX_SCRIPT=scripts/ultra-maintenance-hotfix.py python3 tests/test-cpu-hotfix.py`；归档分别对四种基线验证安装、重复安装、回退、个人配置保持和错误输入拒绝。无线模块在重启后生效。

无线接收修复为`954-recover-invalid-rx-dma-descriptors.patch`，与952 NAPI补丁共同应用。对已应用补丁的厂商源码运行`python3 tests/test-wifi-dma.py /path/to/wlan_hwifi/bus/mtk_pci_dma.c`和`python3 tests/test-wifi-napi.py /path/to/wlan_hwifi/bus/mtk_pci_dma.c`，分别编译真实函数并执行14项DMA/恢复场景与7项NAPI场景。DMA测试启用AddressSanitizer和UndefinedBehaviorSanitizer。

网口、AT字段和显示升级工具的回归分别为`tests/test-ultra-ports.py`、`tests/test-modem-fields.py`、`tests/test-modem-fields.lua`及`tests/test-ui-hotfix.py`。Lua用5.1运行；网口事务测试可通过`UCI_RUNNER`指定实际目标UCI的JSON参数列表，其余协议测试独立执行。

号码/SMS维护补丁为`patches/qmodem/0003-huawei-subscriber-number-and-lte-sinr.patch`，应用在0001/0002之后，包含QModem及短信LuCI包修订。执行`python3 tests/test-modem-fields-sms.py`；重编qmodem和luci-app-qmodem-sms，确保可选仓库与ROM一致。
