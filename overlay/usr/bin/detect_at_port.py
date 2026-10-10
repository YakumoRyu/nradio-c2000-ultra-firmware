#!/usr/bin/env python3
# Auto-detect the modem AT serial port and pin it into a WEBUI server config's
# SERIAL.PORT. fm350webserver.py otherwise relies on its built-in auto-probe, which
# runs tom_modem with a fixed 2s timeout per port; when the tom_modem semaphore is
# contended (e.g. a stale /tmp/shm/tom_modem_lock_dev_ttyUSB* lock from a killed
# probe) every probe times out and the server exits with "未检测到AT端口".
#
# This probes each /dev/ttyUSB* with pyserial DIRECTLY -- independent of tom_modem and
# its semaphore -- so detection cannot be defeated by that deadlock. Only SERIAL.PORT
# is rewritten; the server still talks to the modem via its configured MODE (tom_modem)
# so it keeps coexisting with QModem through the shared per-port lock.
#
# Usage: detect_at_port.py [config_path]   (default /usr/bin/config.json)
import sys, glob, json, time

CFG = sys.argv[1] if len(sys.argv) > 1 else "/usr/bin/config.json"

try:
    import serial
except Exception as e:
    print("detect_at_port: pyserial unavailable (%s), leaving config untouched" % e)
    sys.exit(0)


def responds_to_at(dev):
    """Return True if <dev> answers an AT command with OK."""
    try:
        s = serial.Serial(dev, 115200, timeout=1)
    except Exception:
        return False
    try:
        s.reset_input_buffer()
        s.write(b"AT\r")
        time.sleep(0.3)
        reply = s.read_all().decode(errors="ignore")
        return "OK" in reply
    except Exception:
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


def main():
    found = None
    for dev in sorted(glob.glob("/dev/ttyUSB*")):
        if responds_to_at(dev):
            found = dev
            break

    try:
        with open(CFG, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}

    # Two config schemas are in use:
    #   * fm350webserver.py / config.json  -> flat  data["SERIAL"]["PORT"]
    #   * websocket_server.py / config5700.json -> nested
    #       data["AT_CONFIG"]["SERIAL"]["PORT"], gated by AT_CONFIG["TYPE"].
    # Detect which one this file is and only touch the serial port. For the nested
    # 5700 schema, do nothing when TYPE == "NETWORK" (the modem is reached over IP,
    # not a local tty, so the serial port is irrelevant).
    at_cfg = data.get("AT_CONFIG")
    if isinstance(at_cfg, dict):
        conn_type = at_cfg.get("TYPE", "SERIAL")
        if conn_type == "NETWORK":
            print("detect_at_port: %s is NETWORK mode, serial port untouched" % CFG)
            return
        if not isinstance(at_cfg.get("SERIAL"), dict):
            at_cfg["SERIAL"] = {}
        serial_sec = at_cfg["SERIAL"]
        nested = True
    else:
        if not isinstance(data.get("SERIAL"), dict):
            data["SERIAL"] = {}
        serial_sec = data["SERIAL"]
        nested = False

    if found:
        serial_sec["PORT"] = found
        print("detect_at_port: AT port = %s (written to %s)" % (found, CFG))
    else:
        # Fall back to the server's own auto-probe if nothing answered.
        serial_sec["PORT"] = "auto"
        print("detect_at_port: no AT port responded; left PORT=auto")

    # MODE (tom_modem/direct) only exists in the flat fm350 schema; the nested 5700
    # schema uses BAUDRATE/TIMEOUT instead, so only default it for the flat form.
    if not nested:
        serial_sec.setdefault("MODE", "tom_modem")

    with open(CFG, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
