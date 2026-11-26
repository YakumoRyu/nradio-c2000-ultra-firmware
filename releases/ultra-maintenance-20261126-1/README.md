# 在线小区择优升级包

适用于已安装 r17 切站脚本的 Ultra。解压后运行 `python3 install.py apply`，回退运行 `python3 install.py rollback`。下次分钟任务加载新脚本。

在 cell_preference.main 中设置 preferred_arfcn、preferred_scs、preferred_pci，preferred_mobility=1 对应允许重选和切换的频点设置，enabled=1 启用。程序按实际服务小区和在线邻区测量择优。目标与其他小区分别按频点、SCS 和 PCI 识别。目标消失后可使用备用小区，重新测得目标且质量合格时，经过连续采样和冷却再尝试锁回。试切验证切换前已可用的 IPv4 和 IPv6，失败时读回并恢复原设置。整个流程不调用射频重启或离网扫描。
