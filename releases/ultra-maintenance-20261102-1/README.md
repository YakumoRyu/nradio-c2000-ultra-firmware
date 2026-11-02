# 信号优先重选与PCDN白名单升级包

为Ultra25.12增加保持联网的NR邻区选择。每分钟读取实时信号，连续3次强至少6dB且SINR/RSRQ合格才请求选择；30分钟冷却，失败恢复原锁频。忽略无效数据与快速重复查询，手动锁频修改后暂停自动控制。保持当前连接时不主动扫描、重拨或切飞行模式。

包名：`ultra-maintenance-20261102-1.tar.gz`。保留网络、代理、PCDN、短信和媒体配置，无需整机重启。

增加PCDN设备转发白名单，按已配置的MAC和LAN接口识别设备。出站IPv4/IPv6在OpenClash全局QUIC等过滤规则前放行，IPv6入站匹配当前公网前缀下学到的盒子地址；IPv4继续使用现有NAT和UPnP映射。地址集合每分钟更新，OpenClash重建规则后自动补回优先入口。保持其他设备的防火墙策略。

```sh
tar -xzf ultra-maintenance-20261102-1.tar.gz
cd ultra-maintenance-20261102-1
python3 install.py apply
python3 /usr/libexec/cell-preference --enable-auto
python3 /usr/libexec/cell-preference --check
```

已有PCDN设备配置时启用白名单：

```sh
uci set pcdn.main.firewall_whitelist=1
uci commit pcdn
/usr/libexec/pcdn-ipv6-access
nft list chain inet fw4 ultra_pcdn_allow
```

`pcdn.main.client_mac`和`pcdn.main.interface`分别指定盒子MAC及LAN接口。公共包不预填个人设备数据，白名单默认关闭。安装保留现有启用状态；回退前由安装器清除本功能的运行规则，恢复旧收集程序，保留其他自定义规则与设备配置。

查看运行状态：`cat /tmp/cell-preference.json`。暂停：`uci set cell_preference.main.enabled=0; uci commit cell_preference`。回退：在原解压目录执行`python3 install.py rollback`，保留偏好配置，删除本功能代码和定时入口。若手动改锁频后要重新交给策略，停用策略、删除`/tmp/cell-preference.json`后再启用。

可用`preferred_arfcn`和`preferred_scs`保存首选频点；默认`preferred_arfcn=0`表示不指定。进入自动模式时，有首选就保留其频点限制，没有首选才解除历史锁频。锁频设置和实际驻留分别回读确认。

策略使用模块报告的同频邻区；跨频扫频仍由WebUI手动启动。当前实机邻区均较弱，已验证保持连接与定时运行；指定首选频点的受控重选已实机确认，切换后RSRP/SINR改善、双栈HTTPS通过；被动更强邻区分支保留后续场景验收。完整固件见[完整r13](../ultra-25.12-20261102-r13/README.md)。
