# 美国代理恢复检测升级包

修正WAN变化后的代理恢复检测范围。旧版只检查“节点选择”，当普通网页使用日本节点、“国外AI”使用美国节点时，会漏掉美国节点超时。新版同时检查两个组的实际Mieru出站，重复节点只检查一次；单独用于游戏的节点仍按原策略跳过。

恢复仅在WAN变化后的15分钟窗口内进行，等待链路稳定、连续3次实际请求失败且国内直连正常，并通过CPU、内存和冷却检查后，最多请求一次核心恢复。正常联网时不周期重启核心，不改变节点选择、规则、DNS、5G锁定或PCDN配置。

包名：`ultra-maintenance-20261102-2.tar.gz`。更新一个脚本，无需整机重启。

```sh
tar -xzf ultra-maintenance-20261102-2.tar.gz
cd ultra-maintenance-20261102-2
python3 install.py apply
```

查看状态：`cat /tmp/openclash-wan-recover.json`。检查当前直连和代理：`python3 /usr/libexec/openclash-wan-recover --probe-only`。回退：原解压目录执行`python3 install.py rollback`。

14项回归通过。线上未重启核心，配置摘要保持，实际HTTPS及持续运行结果见VERIFICATION.json。完整固件见[完整r14](../ultra-25.12-20261102-r14/README.md)。
