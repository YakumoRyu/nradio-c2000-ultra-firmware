# Ultra累计维护升级包 — 2026-10-17

适用于本项目r4、r5、r6的NRadio-C2000MAX-Ultra25.12 TF系统，内核为Linux6.12.103。包含无线DMA恢复、CPU/首页和运营商图标修复，保留现有配置。

## 更新内容

- RX描述符为零地址、无效token、空数据指针、负偏移或DMA地址错配时，通过厂商SER异步队列请求恢复，同类恢复请求最多每30秒一次。
- 读取DMA所有权后增加`dma_rmb()`，保留原有NAPI无进展退出修复。
- 先校验描述符再分配拷贝缓冲；内存不足返回`ENOMEM`，不触发DMA恢复。
- 累计包含r6的CPU、首页和运营商图标修复。9个目标文件先校验原始值，再备份与安装。

## 安装

上传`ultra-maintenance-20261017-1-upgrade.tar.gz`到路由器`/tmp`，执行：

```sh
tar -xzf /tmp/ultra-maintenance-20261017-1-upgrade.tar.gz -C /tmp
sh /tmp/ultra-maintenance-20261017-1/install.sh
reboot
```

无线驱动在重启后生效。备份位于`/overlay/ultra-hotfix-backups/maintenance-20261017-r1/`，重复安装保持目标文件不变。

## 回退

```sh
python3 /tmp/ultra-maintenance-20261017-1/ultra-maintenance-hotfix.py rollback
reboot
```

回退恢复本包实际修改的文件。重启保留维护更新；恢复出厂后保留通用修复请使用[完整r7固件](../ultra-25.12-20261017-r7/README.md)。

## 验证

候选驱动的14项异常描述符/所有权测试、原有7项NAPI测试通过，模块架构、内核ABI和导出接口一致。实机重启已加载同一模块，双频、5G双栈、真实网络请求通过，用户确认网页和后台正常、Wi-Fi未再掉线。累计包另做r4/r5/r6安装、重复安装、回退和错误输入检查。详见`VERIFICATION.json`。

本次故障窗口记录了DMA地址错配和硬件越界日志，补丁补齐该异常路径的恢复与读顺序。是否还存在其他无线故障触发条件，由后续运行记录继续确认。
