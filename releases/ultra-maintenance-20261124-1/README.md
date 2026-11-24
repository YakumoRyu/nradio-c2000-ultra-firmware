# 蜂窝切站修复升级包

旧版在模组的实际锁定值与缓存不一致时会停止刷新服务小区。本次修复会继续读取小区并区分手工锁定与自动试切。试切要求保住操作前已有的 IPv4 和 IPv6 连通性。回滚前核对当前锁定值，较晚写入的锁由操作者继续管理。

适用于已安装信号优先选择功能的 C2000 Ultra ImmortalWrt 25.12。安装包更新 `/usr/libexec/cell-preference`，定时任务在下次运行时使用新版本。

```sh
tar -xzf ultra-maintenance-20261124-1.tar.gz
cd ultra-maintenance-20261124-1
python3 install.py apply
```

状态可用 `/usr/libexec/cell-preference --check` 查询。关键状态变化保留在 `/overlay/cell-preference/events.jsonl` 与轮替文件中。手工锁存在时继续显示服务小区，自动试切由原启用命令明确恢复。

回退时在同一目录运行 `python3 install.py rollback`。安装及回退均沿用当前蜂窝设置，事务执行期间稍后再试。

需要整镜像时下载 [完整 r17 固件](../ultra-25.12-20261124-r17/README.md)。
