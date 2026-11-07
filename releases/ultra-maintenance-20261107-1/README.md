# 无线停播恢复升级包

新增Wi-Fi状态观察与受限恢复。厂商驱动连续报告至少20秒无Beacon，或AP连续3次不可用时，经二次确认后仅重新启动受影响的无线频段。检测间隔30秒，启动宽限180秒，恢复间隔至少15分钟，每小时最多2次。正常空闲、无客户端、DFS等待及用户手动关闭均跳过。

结构化故障与15分钟资源样本保存在TF卡，日志最多两份256KiB；运行状态保存在内存盘。仅保存无线/内核事件类别和资源值。

包名：`ultra-maintenance-20261107-1.tar.gz`。更新3个通用文件，启用独立无线观察服务，无需整机重启。

```sh
tar -xzf ultra-maintenance-20261107-1.tar.gz
cd ultra-maintenance-20261107-1
python3 install.py apply
```

查看：`cat /tmp/ultra-wifi-health.json`；故障记录：`cat /overlay/ultra-wifi-health/events.jsonl`。回退在原解压目录运行`python3 install.py rollback`。

原无线、蜂窝、PCDN、代理、短信和媒体配置保持。15项恢复策略与5项安装回退测试通过。2026-11-07早晨停播的重启前日志已丢失；此次修复厂商驱动Beacon超时后只记录、未恢复的处理缺口，并加入持久故障记录。

完整ROM集成版见[完整r16](../ultra-25.12-20261107-r16/README.md)。
