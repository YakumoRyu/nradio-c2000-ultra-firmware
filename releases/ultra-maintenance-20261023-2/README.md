# Ultra媒体保护与Emby恢复升级包

版本：`ultra-maintenance-20261023-2`。在Ultra25.12、Linux6.12.103的r4/r5/r6/r7/r8基线上安装17个文件的累计维护补丁，保留个人配置。

本次修复：

- Docker接口超时后继续采集CPU、内存与容器组状态，避免保护状态停止更新。
- 保护停服前保存目标；分步恢复OpenList、Emby、MediaWarp和AutoFilm，逐个核对结果并保留恢复进度。
- 将Emby的`memory.high`设为320MiB，保留384MiB硬限制，减少TF卡上程序页被反复回收和重读。
- 按服务设置恢复余量，允许在正常网络转发负载下恢复；每个服务保留一小时重试间隔。
- 将保护目标持久保存，重启后继续恢复。资源采样仍写入内存，TF卡只在保护状态改变时写入。
- AutoFilm被暂停时，OpenList仍可根据自己的状态恢复云盘驱动。

同包包含此前的无线DMA、CPU采样、运营商图标、SIM号码、短信入口与系统切换修复。r8用户安装本包只需更新两个媒体保护文件，并重新加载正在运行的保护服务。

## 安装与回退

将升级包上传到路由器后执行：

```sh
tar -xzf ultra-maintenance-20261023-2-upgrade.tar.gz
cd ultra-maintenance-20261023-2
sh install.sh
```

安装器核对板型、系统、内核和文件摘要，并在`/overlay/ultra-hotfix-backups/maintenance-20261023-r2`保存修改前文件。结果中的`reboot_required`表示是否需要重启加载累计无线驱动补丁；仅更新媒体保护代码时不需要整机重启。

回退本次文件：

```sh
python3 ultra-maintenance-hotfix.py rollback
```

## 验证

13项媒体保护测试通过；实机媒体库、播放信息和云盘视频分段读取通过。3分钟监测中，后台与媒体端点全部返回200，保护状态持续更新。Emby后台追赶分析保留，用户确认手动重启后网页和后台正常。

完整镜像见[Ultra25.12 r9](../ultra-25.12-20261023-r9/README.md)。详细数值与安装回退验证见同Release的`VERIFICATION.json`。
