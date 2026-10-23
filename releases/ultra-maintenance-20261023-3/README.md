# Ultra延迟停机恢复修复升级包

版本：`ultra-maintenance-20261023-3`。适用于Ultra25.12、Linux6.12.103的r4/r5/r6/r7/r8/r9基线。17文件累计升级包保留个人配置，r9仅更新媒体保护程序。

本次修复保护程序发出停止请求后，把Docker短暂的`Running=true`误当成恢复成功、提前移除恢复目标的问题。服务现在记录“等待停止、已停止、正在启动”三个阶段；收到停止请求的容器保留在队列中，只有已经发出启动请求并确认运行后才移出队列。Docker查询失败时，未找到进程只表示状态未知，不作为停止完成的依据。

停止阶段、恢复进度和触发时的资源数据持久保存；重复采样不会向同一待停服务反复发送停止命令。升级时自动恢复旧版未完成停止记录中丢失的目标，只处理Docker确认已退出的已记录服务。后台追赶分析、路由资源保护、320MiB回收水位和384MiB Emby硬限制继续保留。

## 安装

```sh
tar -xzf ultra-maintenance-20261023-3-upgrade.tar.gz
cd ultra-maintenance-20261023-3
sh install.sh
```

安装器检查板型、内核与原始文件摘要，在`/overlay/ultra-hotfix-backups/maintenance-20261023-r3`保存修改前文件。r9只需重新加载媒体保护服务；若累计无线驱动发生更新，结果中的`reboot_required`为true。

回退：

```sh
python3 ultra-maintenance-hotfix.py rollback
```

## 验证

21项媒体保护测试通过。新增的延迟退出案例在r9代码上复现失败，在修正版上通过；包括Docker停止超时后延迟退出、跨进程重启保留阶段、启动超时后确认成功，以及Docker不可用时不误判退出。

实机通过保护程序恢复队列启动Emby，3个媒体库和内外网视频206分段读取通过。15分钟、61组样本中，CPU为24.97%–57.16%，后台响应中位4毫秒、Emby13毫秒；最终候选另完成120秒在线核对，未重启路由器。

AutoFilm后台导入服务仍在恢复队列中，等待可用内存达到224MiB并持续稳定。Emby、MediaWarp和OpenList运行正常。安装回退与运行记录见同Release的`VERIFICATION.json`。

完整固件见[Ultra25.12 r10](../ultra-25.12-20261023-r10/README.md)。
