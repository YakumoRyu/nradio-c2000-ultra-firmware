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
3. 按锁定提交准备 feeds、QModem、iStore、v2dat；应用 QModem 补丁，添加 `packages/compat` feed。
4. 将 `overlay` 放入基线 `files`，使用 `configs/ultra.config`，运行 `make defconfig`。
5. 补齐 `binary-assets.lock.json` 记录的输入后再构建。未补齐时不能把生成镜像称为完整复现版。

本仓库没有把 Docker、Mihomo、Cloudflared、规则库等大型二进制加入 Git。部分历史管理资源的来源与构建链仍需继续整理；当前完整发布镜像来自已验证的本地工程。GitHub Actions 目前执行源码/协议回归，不声称自动生成已通过实机验收的完整固件。

整固件打包后必须检查板型、FIT/DTB、内核模块 ABI、512 MiB 数据区布局、原登录模板、闭源驱动补丁、隐私和用户态执行，再完成真实设备验收。
