#!/bin/bash
set -eu
umask 077
state=/etc/sms-pushplus
test -r "$state/token"
export SMS_SENDER="${SMS_SENDER:-未知}"
export SMS_TIME="${SMS_TIME:-$(date '+%Y-%m-%d %H:%M:%S')}"
export SMS_CONTENT="${SMS_CONTENT:-}"
test -n "$SMS_CONTENT"

test_mode=0
[ "${1:-}" != --test ] || test_mode=1
if [ "$test_mode" = 0 ]; then
    cutoff=$(cat "$state/enabled-since")
    if [[ "$SMS_TIME" < "$cutoff" ]]; then
        exit 0
    fi
fi
digest=$(printf '%s\0%s\0%s' "$SMS_SENDER" "$SMS_TIME" "$SMS_CONTENT" | sha256sum | cut -d ' ' -f1)
if [ "$test_mode" = 0 ] && [ -f "$state/sent.sha256" ] && grep -qx "$digest" "$state/sent.sha256"; then
    exit 0
fi

export PUSHPLUS_TOKEN
PUSHPLUS_TOKEN=$(cat "$state/token")
export PUSHPLUS_TITLE='路由器新短信'
[ "$test_mode" = 0 ] || PUSHPLUS_TITLE='路由器 PushPlus 接入测试'
response=$(mktemp /tmp/pushplus-response.XXXXXX)
trap 'rm -f "$response"' EXIT
if ! jq -nc '{token:env.PUSHPLUS_TOKEN,title:env.PUSHPLUS_TITLE,content:("发件人："+env.SMS_SENDER+"\n时间："+env.SMS_TIME+"\n\n"+env.SMS_CONTENT),template:"txt",channel:"wechat"}' |
    curl --silent --show-error --connect-timeout 8 --max-time 25 --retry 0 \
    -H 'Content-Type: application/json' --data-binary @- \
    -o "$response" https://www.pushplus.plus/send; then
    printf '{"status":"transport_error"}\n' > /tmp/pushplus-last-status.json
    exit 1
fi
unset PUSHPLUS_TOKEN
code=$(jq -r '.code // 0' "$response" 2>/dev/null || echo 0)
if [ "$code" != 200 ]; then
    jq -nc --arg code "$code" '{status:"api_rejected",code:$code}' > /tmp/pushplus-last-status.json
    cat /tmp/pushplus-last-status.json
    exit 1
fi
jq -c '{status:"accepted",code:.code,requestId:.data,delivery:"queued"}' "$response" > /tmp/pushplus-last-status.json
if [ "$test_mode" = 0 ]; then
    printf '%s\n' "$digest" >> "$state/sent.sha256"
fi
cat /tmp/pushplus-last-status.json
