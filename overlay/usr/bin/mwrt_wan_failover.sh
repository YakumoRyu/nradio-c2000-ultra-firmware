#!/bin/sh
# Mwrt WAN Failover - 优化日志输出

CONFIG_FILE="Mwrt-Assurance"
CONFIG_SECTION="wan_failover"
LOG_FILE="/tmp/mwrt_failover.log"

mkdir -p /tmp
[ ! -f "$LOG_FILE" ] && touch "$LOG_FILE"

########################################
# 日志等级控制（DEBUG/INFO/WARN/ERROR）
LOG_LEVEL="INFO"   # 默认只记录 INFO 及以上
MAX_LOG_SIZE=10240 # KB，日志轮替阈值

should_log() {
    local level="$1"
    case "$LOG_LEVEL" in
        DEBUG) return 0 ;;  # 全部记录
        INFO)  [ "$level" != "DEBUG" ] && return 0 || return 1 ;;
        WARN)  [ "$level" = "WARN" ] || [ "$level" = "ERROR" ] && return 0 || return 1 ;;
        ERROR) [ "$level" = "ERROR" ] && return 0 || return 1 ;;
        *) return 1 ;;
    esac
}

rotate_log() {
    if [ -f "$LOG_FILE" ] && [ "$(du -k "$LOG_FILE" | cut -f1)" -ge "$MAX_LOG_SIZE" ]; then
        mv "$LOG_FILE" "$LOG_FILE.old"
        touch "$LOG_FILE"
    fi
}

log_msg() {
    local level="$1"; shift
    local msg="$*"
    should_log "$level" || return 0
    rotate_log
    local ts; ts=$(date '+%F %T')
    echo "$ts [$level] $msg" >> "$LOG_FILE"
}

# 状态变化才记录
last_state=""
set_state() {
    local new_state="$1"
    if [ "$last_state" != "$new_state" ]; then
        log_msg "INFO" "WAN 状态变化: $new_state"
        last_state="$new_state"
    fi
}

########################################
# LED 指示
#   有互联网 -> hc:blue:status 亮, hc:red:error 灭
#   无互联网 -> hc:red:error 亮, hc:blue:status 灭
#
# 直接写 sysfs 的 brightness。这两个灯 max_brightness 都是 1, 所以只有 0/1,
# 没有亮度中间档。
#
# hc:red:error 出厂 trigger 是 default-on —— 内核触发器还挂着的时候我们写
# brightness 只是临时生效, 触发器下次激活就覆盖回去, 所以先把 trigger 置成
# none 把控制权拿过来。hc:blue:status 出厂已经是 none, 一并置一次不影响。
#
# 每处都先判断节点可写再写: 这个脚本在别的板子上也跑, 那些板子没有这两个
# LED 节点, 找不到就安静跳过 —— 不报错、不刷日志、不影响故障切换本身。
# 同机上的 hc:red:int / hc:blue:cmode4 / hc:blue:cmode5 不碰。
LED_OK="/sys/class/leds/hc:blue:status"
LED_ERR="/sys/class/leds/hc:red:error"

led_write() {
    local led="$1"; local val="$2"
    [ -w "$led/brightness" ] && echo "$val" > "$led/brightness" 2>/dev/null
    return 0
}

led_init() {
    local led
    for led in "$LED_OK" "$LED_ERR"; do
        [ -w "$led/trigger" ] && echo none > "$led/trigger" 2>/dev/null
    done
    return 0
}

# 只在状态翻转时写, 免得每个检测周期都去动一次 sysfs
last_led=""
set_leds() {
    local online="$1"

    # /tmp/ledflag.conf 是本机既有的"灯光总开关"标记:
    #   /usr/bin/led.sh 选 1(全开) 写 "1"、选 2(全关) 写 "2"、
    #   选 3(恢复真实状态) 删掉它;
    #   /etc/init.d/modeminit 在有 /usr/bin/ledflagc.conf 时也会写 "0" 并全灭。
    # 标记在就别抢灯 —— 用户明确要求"全开/全关"的时候, 我们插一脚会让
    # hc:blue:status 自己跳回来, 看起来像坏了。等他选 3 再接回去。
    if [ -f /tmp/ledflag.conf ]; then
        # 清掉记忆: 标记一撤销, 下一轮立刻按真实状态重刷一次
        last_led=""
        return 0
    fi

    [ "$last_led" = "$online" ] && return 0
    if [ "$online" = "1" ]; then
        led_write "$LED_ERR" 0
        led_write "$LED_OK"  1
        log_msg "INFO" "LED: 蓝灯亮 (有互联网)"
    else
        led_write "$LED_OK"  0
        led_write "$LED_ERR" 1
        log_msg "INFO" "LED: 红灯亮 (无互联网)"
    fi
    last_led="$online"
}

########################################
get_config_value() {
    local option="$1"; local default="$2"
    local value
    value=$(uci get ${CONFIG_FILE}.${CONFIG_SECTION}.${option} 2>/dev/null)
    if [ -n "$value" ]; then
        echo "$value"
    else
        echo "$default"
    fi
}

get_iface_name_by_dev() {
    local dev="$1"
    uci show network 2>/dev/null | grep "device='$dev'" | awk -F. '{print $2}' | awk -F= '{print $1}' | head -n 1
}

get_gateway() {
    local ifname="$1"
    local gw

    gw=$(ip route show dev "$ifname" | awk '/^default / {print $3; exit}')
    [ -n "$gw" ] && echo "$gw" && return 0

    local netname
    netname=$(get_iface_name_by_dev "$ifname")
    if [ -n "$netname" ]; then
        gw=$(uci get network."$netname".gateway 2>/dev/null)
        [ -n "$gw" ] && echo "$gw" && return 0
    fi

    if [ -f "/tmp/dhcp.leases" ]; then
        gw=$(grep "$ifname" /tmp/dhcp.leases | awk '{print $3}' | head -n 1)
        [ -n "$gw" ] && echo "$gw" && return 0
    fi

    gw=$(ip route | grep "$ifname" | awk '/default/ {print $3; exit}')
    [ -n "$gw" ] && echo "$gw" && return 0

    gw=$(ip addr show dev "$ifname" | awk '/inet / {print $2}' | cut -d/ -f1 | cut -d. -f1-3).1
    [ -n "$gw" ] && echo "$gw" && return 0

    return 1
}

check_primary_via_temp_route() {
    local ifname="$1"
    local target="$2"

    local gw
    gw=$(get_gateway "$ifname") || return 1

    if ! ip addr show dev "$ifname" | grep -q "inet "; then
        return 1
    fi

    ip route add "$target" via "$gw" dev "$ifname" 2>/dev/null
    local result=1
    if ping -I "$ifname" -c 2 -W 2 "$target" >/dev/null 2>&1; then
        result=0
    fi
    ip route del "$target" via "$gw" dev "$ifname" 2>/dev/null

    return $result
}

# 当前默认路由实际走哪个口。
# 点灯看的是实况, 而不是脚本自己记的 CURRENT_IF —— 后者只在本脚本切换时更新,
# 别处(ifup/DHCP/手动改路由)动过它并不知道。取不到就是没默认路由, 等于没网。
active_if() {
    ip route 2>/dev/null | awk '/^default/ {print $5; exit}'
}

# 只 ping, 不做 ifup —— 专门给点灯用。
# check_online() 在没有 inet 地址时会顺手 ifup 再探, 那个副作用是故障切换需要
# 的; 点灯只是反映现状, 不该为了点灯去动接口。
probe_online() {
    local ifname="$1"
    [ -n "$ifname" ] || return 1
    ping -I "$ifname" -c 1 -W 2 "$PING_TARGET" >/dev/null 2>&1
}

check_online() {
    local ifname="$1"; local ping_target="$PING_TARGET"

    if ! ip addr show dev "$ifname" | grep -q "inet "; then
        ifup "$ifname"
        sleep 2
    fi

    if ping -I "$ifname" -c 2 -W 2 "$ping_target" >/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

switch_to() {
    local ifname="$1"; local gw="$2"
    [ -z "$gw" ] && log_msg "ERROR" "切换失败 $ifname: 无网关" && return
    ip route del default >/dev/null 2>&1
    ip route replace default via "$gw" dev "$ifname"
    CURRENT_IF="$ifname"
    log_msg "INFO" "默认路由已切换到 $ifname ($gw)"
}

########################################
CURRENT_IF=$(ip route | awk '/^default/ {print $5; exit}')
fail_count=0
success_count=0

ENABLED=$(get_config_value "enabled" "1")
PRIMARY_IF=$(get_config_value "primary_if" "eth0")
SECONDARY_IF=$(get_config_value "secondary_if" "eth2")
PING_TARGET=$(get_config_value "ping_target" "8.8.8.8")
CHECK_INTERVAL=$(get_config_value "check_interval" "5")
FAIL_THRESHOLD=$(get_config_value "fail_threshold" "2")
SUCCESS_THRESHOLD=$(get_config_value "success_threshold" "3")
FORCE_PRIMARY=$(get_config_value "force_primary" "1")

log_msg "INFO" "脚本启动，当前接口=$CURRENT_IF"

# 先把这两个灯的内核触发器摘掉, 否则 hc:red:error 的 default-on 会跟我们抢
led_init

while true; do
    # 本轮的联网判断。留空 = 还不知道, 由轮末补一次探测。
    ONLINE=""
    ENABLED=$(uci get ${CONFIG_FILE}.${CONFIG_SECTION}.enabled 2>/dev/null || echo "1")
    PRIMARY_IF=$(uci get ${CONFIG_FILE}.${CONFIG_SECTION}.primary_if 2>/dev/null || echo "eth0")
    SECONDARY_IF=$(uci get ${CONFIG_FILE}.${CONFIG_SECTION}.secondary_if 2>/dev/null || echo "eth2")
    PING_TARGET=$(uci get ${CONFIG_FILE}.${CONFIG_SECTION}.ping_target 2>/dev/null || echo "8.8.8.8")
    CHECK_INTERVAL=$(uci get ${CONFIG_FILE}.${CONFIG_SECTION}.check_interval 2>/dev/null || echo "5")
    FAIL_THRESHOLD=$(uci get ${CONFIG_FILE}.${CONFIG_SECTION}.fail_threshold 2>/dev/null || echo "2")
    SUCCESS_THRESHOLD=$(uci get ${CONFIG_FILE}.${CONFIG_SECTION}.success_threshold 2>/dev/null || echo "3")
    FORCE_PRIMARY=$(uci get ${CONFIG_FILE}.${CONFIG_SECTION}.force_primary 2>/dev/null || echo "1")

    # 故障切换停用时不动路由, 但灯照样要反映真实联网状态 ——
    # "有没有互联网"和"要不要自动切换"是两件事。
    if [ "$ENABLED" != "1" ]; then
        if probe_online "$(active_if)"; then set_leds 1; else set_leds 0; fi
        sleep "$CHECK_INTERVAL"
        continue
    fi

    if [ "$CURRENT_IF" = "$PRIMARY_IF" ]; then
        if check_online "$PRIMARY_IF"; then
            fail_count=0
            success_count=$((success_count + 1))
            set_state "PRIMARY_OK"
            ONLINE=1
        else
            success_count=0
            fail_count=$((fail_count + 1))
            # 主口这一轮探测失败, 而默认路由还在主口上 —— 先按没网算。
            # 下面真切到备用口了再改回未知, 交给轮末重新探。
            ONLINE=0
            if [ "$fail_count" -ge "$FAIL_THRESHOLD" ]; then
                log_msg "WARN" "主WAN故障，准备切换到备用WAN: $SECONDARY_IF"

                if ! check_online "$SECONDARY_IF"; then
                    ifup "$SECONDARY_IF"
                    sleep 3
                fi

                gw_secondary=$(get_gateway "$SECONDARY_IF")
                if [ -n "$gw_secondary" ]; then
                    switch_to "$SECONDARY_IF" "$gw_secondary"
                    set_state "SECONDARY_ACTIVE"
                    # 刚切过来, 备用口通不通这一轮还没探过, 置回未知
                    ONLINE=""
                else
                    log_msg "ERROR" "备用WAN无网关，无法切换"
                fi
                fail_count=0
            fi
        fi
    else
        if [ "$FORCE_PRIMARY" = "1" ]; then
            if check_primary_via_temp_route "$PRIMARY_IF" "$PING_TARGET"; then
                log_msg "INFO" "检测到主WAN恢复，切换路由到主WAN"
                gw_primary=$(get_gateway "$PRIMARY_IF")
                if [ -n "$gw_primary" ]; then
                    switch_to "$PRIMARY_IF" "$gw_primary"
                    set_state "PRIMARY_OK"
                    # 刚才 check_primary_via_temp_route 已经证明主口能出网
                    ONLINE=1
                fi
            fi
        fi
    fi

    # 点灯。本轮已经探出结果的直接用; 没探过的才补一次 —— 比如正跑在备用口
    # 上、这一轮只探了主口的情况。这样不会为了点灯把 ping 量翻倍。
    if [ -z "$ONLINE" ]; then
        if probe_online "$(active_if)"; then ONLINE=1; else ONLINE=0; fi
    fi
    set_leds "$ONLINE"

    sleep "$CHECK_INTERVAL"
done
