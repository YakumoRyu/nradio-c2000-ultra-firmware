#!/bin/sh
# Regenerate the modem WEBUI SPA backend config so its websocket host tracks the
# current br-lan LAN IP. Both SPA bundles fetch "/config.json" SAME-ORIGIN from the
# main uhttpd (docroot /www), then open a websocket to at.host:at.port. When the file
# is missing the SPA falls back to a hardcoded 192.168.88.1, which breaks after any LAN
# IP change. Writing the live LAN IP to /www/config.json keeps the WEBUI self-adapting.
#
# Historically this wrote /www/web/config.json (the :8888 uhttpd docroot), but the SPA
# is served same-origin under / by the MAIN server. The 5700 SPA fetches EXACTLY
# "/5700/config.json" (verified in umi*.js), so the authoritative file is
# /www/5700/config.json -- writing only /www/config.json left the SPA reading the
# bundle's stale 192.168.88.1 and connecting ws:// to the wrong host. We write every
# location a bundle might read so the serving layout can't defeat it.
ip="$(uci -q get network.lan.ipaddr)"
[ -n "$ip" ] || ip="192.168.1.1"
cfg="{\"status\":\"true\",\"at\":{\"host\":\"$ip\",\"port\":8766}}"

# The path the 5700 SPA actually fetches: /5700/config.json.
[ -d /www/5700 ] && printf '%s\n' "$cfg" > /www/5700/config.json

# Root path (some bundles / fallbacks fetch /config.json).
printf '%s\n' "$cfg" > /www/config.json

# Legacy :8888 docroot copy (FM350 web bundle), harmless if that server is unused.
mkdir -p /www/web
printf '%s\n' "$cfg" > /www/web/config.json

# Public endpoint metadata must remain readable under restrictive service umasks.
for file in /www/5700/config.json /www/config.json /www/web/config.json; do
    [ ! -f "$file" ] || chmod 644 "$file"
done
