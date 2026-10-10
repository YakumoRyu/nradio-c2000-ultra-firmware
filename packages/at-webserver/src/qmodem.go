package main

import (
	"context"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"os/exec"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

const sharedSMSIndexBase = 1000000
const qmodemOwner = "at-webserver"

type ubusCall func(context.Context, string, string, map[string]any) (map[string]any, error)
type qmodemBackend struct {
	port      string
	modem     string
	call      ubusCall
	uci       func(context.Context) (string, error)
	emit      func(unsolicited)
	connected atomic.Bool
	mapMu     sync.Mutex
	checked   time.Time
	smsMu     sync.Mutex
	lastSync  time.Time
	scanMu    sync.Mutex
	scan      chan string
}

func newQModemBackend(port string, emit func(unsolicited)) *qmodemBackend {
	return &qmodemBackend{port: port, call: callUBus, emit: emit, uci: func(ctx context.Context) (string, error) {
		ctx, cancel := context.WithTimeout(ctx, 3*time.Second)
		defer cancel()
		out, err := exec.CommandContext(ctx, "uci", "-q", "show", "qmodem").Output()
		return string(out), err
	}}
}

func callUBus(ctx context.Context, object, method string, params map[string]any) (map[string]any, error) {
	ctx, cancel := context.WithTimeout(ctx, 25*time.Second)
	defer cancel()
	payload, err := json.Marshal(params)
	if err != nil {
		return nil, err
	}
	// Structured argv, no shell, no stderr/AT payload in errors or logs.
	out, err := exec.CommandContext(ctx, "ubus", "-t", "24", "call", object, method, string(payload)).Output()
	if err != nil {
		return nil, errors.New("QModem service unavailable")
	}
	var result map[string]any
	if json.Unmarshal(out, &result) != nil {
		return nil, errors.New("Invalid QModem response")
	}
	return result, nil
}

func (q *qmodemBackend) resolve(ctx context.Context) error {
	q.mapMu.Lock()
	defer q.mapMu.Unlock()
	if time.Since(q.checked) < 30*time.Second && q.modem != "" {
		return nil
	}
	raw, err := q.uci(ctx)
	if err != nil {
		return errors.New("QModem device mapping unavailable")
	}
	values := map[string]string{}
	for _, line := range strings.Split(raw, "\n") {
		key, value, ok := strings.Cut(line, "=")
		if ok {
			values[key] = unquoteUCI(value)
		}
	}
	type device struct{ id, port string }
	var devices []device
	for key, value := range values {
		if value != "modem-device" || strings.Count(key, ".") != 1 {
			continue
		}
		port := values[key+".override_at_port"]
		if port == "" {
			port = values[key+".sms_at_port"]
		}
		if port == "" {
			port = values[key+".at_port"]
		}
		if strings.HasPrefix(port, "/dev/") {
			devices = append(devices, device{strings.TrimPrefix(key, "qmodem."), port})
		}
	}
	var selected *device
	for i := range devices {
		if devices[i].port == q.port {
			selected = &devices[i]
		}
	}
	if selected == nil && len(devices) == 1 {
		selected = &devices[0]
	}
	if selected == nil {
		return errors.New("Select the QModem device before connecting")
	}
	q.port, q.modem = selected.port, selected.id
	q.checked = time.Now()
	return nil
}

func (q *qmodemBackend) mapping() (string, string) {
	q.mapMu.Lock()
	defer q.mapMu.Unlock()
	return q.port, q.modem
}

func (q *qmodemBackend) run(ctx context.Context) {
	var wg sync.WaitGroup
	wg.Add(1)
	go func() { defer wg.Done(); q.listen(ctx) }()
	defer wg.Wait()
	for ctx.Err() == nil {
		valid := false
		if q.resolve(ctx) == nil {
			port, _ := q.mapping()
			result, err := q.call(ctx, "at-daemon", "list", map[string]any{})
			if err == nil {
				if ports, ok := result["ports"].([]any); ok {
					for _, p := range ports {
						if v, ok := p.(map[string]any); ok && v["port"] == port && v["is_open"] == float64(1) {
							valid = true
						}
					}
				}
			}
		}
		q.connected.Store(valid)
		if !sleepCtx(ctx, 15*time.Second) {
			return
		}
	}
}

// One ubus event subscriber observes URCs, never reads the serial device.
func (q *qmodemBackend) listen(ctx context.Context) {
	for ctx.Err() == nil {
		cmd := exec.CommandContext(ctx, "ubus", "listen", "qmodem.at.line")
		out, err := cmd.StdoutPipe()
		if err == nil {
			err = cmd.Start()
		}
		if err == nil {
			dec := json.NewDecoder(io.LimitReader(out, 1<<40))
			for {
				var event map[string]json.RawMessage
				if dec.Decode(&event) != nil {
					break
				}
				if raw, ok := event["qmodem.at.line"]; ok {
					q.handleEvent(raw)
				}
			}
			_ = cmd.Process.Kill()
			_ = cmd.Wait()
		}
		q.connected.Store(false)
		if !sleepCtx(ctx, 2*time.Second) {
			return
		}
	}
}

func (q *qmodemBackend) handleEvent(raw json.RawMessage) {
	var e struct {
		Port        string `json:"port"`
		Line        string `json:"raw_line"`
		Correlation string `json:"correlation"`
	}
	if json.Unmarshal(raw, &e) != nil {
		return
	}
	port, _ := q.mapping()
	if e.Port != port {
		return
	}
	line := strings.TrimSpace(e.Line)
	if line == "" {
		return
	}
	q.scanMu.Lock()
	if q.scan != nil && (strings.HasPrefix(line, "^CELLSCAN:") || isTerminator(line)) {
		select {
		case q.scan <- line:
		default:
		}
		q.scanMu.Unlock()
		return
	}
	q.scanMu.Unlock()
	// Queries from dial/SMS workers must not masquerade as unsolicited results.
	if isExclusiveURC(line) || e.Correlation == "idle" && (strings.HasPrefix(line, "^PDCPDATAINFO:") || strings.HasPrefix(line, "^CERSSI:") || strings.HasPrefix(line, "^HCSQ:")) {
		q.emit(unsolicited{line: line, broadcast: true})
	}
}

func (q *qmodemBackend) exchange(ctx context.Context, command string, timeout time.Duration, stream func(string)) (ATResponse, error) {
	if err := q.resolve(ctx); err != nil {
		return ATResponse{}, err
	}
	if stream != nil {
		return q.scanCommand(ctx, command, timeout, stream)
	}
	if strings.HasPrefix(strings.ToUpper(command), "AT+CMGS=") {
		return q.submitSMS(ctx, command)
	}
	port, _ := q.mapping()
	seconds := int(timeout / time.Second)
	if seconds < 1 {
		seconds = 1
	}
	result, err := q.call(ctx, "at-daemon", "sendat", map[string]any{"at_port": port, "at_cmd": strings.TrimRight(command, "\r\n"), "timeout": seconds, "owner": qmodemOwner})
	if err != nil {
		return ATResponse{}, err
	}
	if result["status"] != "success" {
		return ATResponse{}, errors.New("QModem is busy or AT command timed out")
	}
	raw, ok := result["response"].(string)
	if !ok {
		return ATResponse{}, errNoResponse
	}
	q.connected.Store(true)
	return normalizedAT(raw, strings.TrimSpace(command)), nil
}

func normalizedAT(raw, echo string) ATResponse {
	var lines []string
	for _, line := range strings.Split(strings.ReplaceAll(raw, "\r", ""), "\n") {
		line = strings.TrimSpace(line)
		if line != "" && line != echo {
			lines = append(lines, line)
		}
	}
	return ATResponse{Lines: lines}
}

func (q *qmodemBackend) lease(ctx context.Context, ttl int) (func(), error) {
	port, _ := q.mapping()
	v, err := q.call(ctx, "at-daemon", "lease_acquire", map[string]any{"at_port": port, "owner": qmodemOwner, "ttl": ttl})
	if err != nil {
		return nil, err
	}
	token, ok := v["token"].(string)
	if v["status"] != "success" || !ok {
		return nil, errors.New("QModem AT port is busy")
	}
	return func() {
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		defer cancel()
		_, _ = q.call(ctx, "at-daemon", "lease_release", map[string]any{"at_port": port, "owner": qmodemOwner, "token": token})
	}, nil
}

func (q *qmodemBackend) submitSMS(ctx context.Context, command string) (ATResponse, error) {
	header, pdu, ok := strings.Cut(strings.TrimRight(command, "\r\n"), "\r")
	pdu = strings.TrimSuffix(pdu, "\x1a")
	if !ok || !regexp.MustCompile(`(?i)^AT\+CMGS=\d+$`).MatchString(header) || !isHex(pdu) || len(pdu)%2 != 0 {
		return ATResponse{}, errors.New("Invalid SMS PDU")
	}
	release, err := q.lease(ctx, 20)
	if err != nil {
		return ATResponse{}, err
	}
	defer release()
	port, _ := q.mapping()
	v, err := q.call(ctx, "at-daemon", "sendat", map[string]any{"at_port": port, "owner": qmodemOwner, "at_cmd": header, "end_flag": ">,ERROR,+CMS ERROR:,+CME ERROR:", "timeout": 2})
	if err != nil {
		return ATResponse{}, err
	}
	raw, _ := v["response"].(string)
	if v["status"] != "success" || !strings.Contains(raw, ">") {
		return ATResponse{}, errors.New("Modem did not accept SMS prompt")
	}
	v, err = q.call(ctx, "at-daemon", "sendat", map[string]any{"at_port": port, "owner": qmodemOwner, "raw_at_content": hex.EncodeToString([]byte(pdu + "\x1a")), "timeout": 2})
	if err != nil || v["status"] != "success" {
		return ATResponse{}, errors.New("SMS submission failed")
	}
	raw, _ = v["response"].(string)
	return normalizedAT(raw, ""), nil
}

func (q *qmodemBackend) scanCommand(ctx context.Context, command string, timeout time.Duration, stream func(string)) (ATResponse, error) {
	if timeout > 240*time.Second {
		return ATResponse{}, errors.New("QModem scan timeout must be at most 240 seconds")
	}
	release, err := q.lease(ctx, int(timeout/time.Second)+10)
	if err != nil {
		return ATResponse{}, err
	}
	defer release()
	lines := make(chan string, maxResponseLines)
	q.scanMu.Lock()
	q.scan = lines
	q.scanMu.Unlock()
	defer func() { q.scanMu.Lock(); q.scan = nil; q.scanMu.Unlock() }()
	port, _ := q.mapping()
	v, err := q.call(ctx, "at-daemon", "sendat", map[string]any{"at_port": port, "owner": qmodemOwner, "at_cmd": command, "sendonly": true})
	if err != nil || v["status"] != "success" {
		return ATResponse{}, errors.New("Could not start cell scan")
	}
	timer := time.NewTimer(timeout)
	defer timer.Stop()
	var result ATResponse
	for {
		select {
		case line := <-lines:
			if len(result.Lines) >= maxResponseLines {
				_ = q.interrupt("abcd")
				return ATResponse{}, errors.New("Cell scan response limit exceeded")
			}
			result.Lines = append(result.Lines, line)
			stream(line)
			if isTerminator(line) {
				return result, nil
			}
		case <-timer.C:
			_ = q.interrupt("abcd")
			return ATResponse{}, errors.New("Cell scan timed out")
		case <-ctx.Done():
			_ = q.interrupt("abcd")
			return ATResponse{}, ctx.Err()
		}
	}
}

func (q *qmodemBackend) interrupt(payload string) error {
	q.scanMu.Lock()
	active := q.scan != nil
	q.scanMu.Unlock()
	if !active {
		return errNoPendingCommand
	}
	if payload != "abcd" {
		return errors.New("Invalid scan interrupt")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	port, _ := q.mapping()
	v, err := q.call(ctx, "at-daemon", "sendat", map[string]any{"at_port": port, "owner": qmodemOwner, "raw_at_content": hex.EncodeToString([]byte("abcd\r")), "sendonly": true})
	if err != nil {
		return err
	}
	if v["status"] != "success" {
		return errors.New("Could not interrupt scan")
	}
	return nil
}

var smsListRe = regexp.MustCompile(`(?i)^AT\+CMGL\s*=\s*4$`)
var smsDeleteRe = regexp.MustCompile(`(?i)^AT\+CMGD\s*=\s*(\d+)$`)

func (q *qmodemBackend) sharedSMS(ctx context.Context, command string) *atCommandResponse {
	cmd := strings.TrimSpace(command)
	list := smsListRe.MatchString(cmd)
	del := smsDeleteRe.FindStringSubmatch(cmd)
	ident := 0
	if del != nil {
		ident, _ = strconv.Atoi(del[1])
	}
	if !list && ident <= sharedSMSIndexBase {
		return nil
	}
	q.smsMu.Lock()
	defer q.smsMu.Unlock()
	if err := q.resolve(ctx); err != nil {
		return errResponse("SMS device mapping unavailable")
	}
	_, modem := q.mapping()
	v, err := q.call(ctx, "qmodem.sms", "config_get", map[string]any{"modem_id": modem})
	if err != nil {
		return errResponse("SMS database unavailable")
	}
	if v["mode"] == "direct" {
		if list {
			return nil
		}
		return errResponse("Reload SMS page after changing SMS mode")
	}
	if v["mode"] != "database_poll" && v["mode"] != "database_urc" {
		return errResponse("SMS database mode unavailable")
	}
	if !list {
		v, err = q.call(ctx, "qmodem.sms", "delete", map[string]any{"modem_id": modem, "id": ident - sharedSMSIndexBase})
		if err != nil || v["status"] != "success" || v["deleted"] != float64(1) {
			return errResponse("SMS not found in shared store")
		}
		return ptr(okResponse("OK"))
	}
	if time.Since(q.lastSync) >= 10*time.Second {
		v, err = q.call(ctx, "qmodem.sms", "sync", map[string]any{"modem_id": modem})
		if err != nil || v["status"] != "success" {
			return errResponse("SMS synchronization failed")
		}
		q.lastSync = time.Now()
	}
	messages := []map[string]any{}
	for offset := 0; offset < 6500; offset += 500 {
		v, err = q.call(ctx, "qmodem.sms", "list", map[string]any{"modem_id": modem, "offset": offset, "limit": 500})
		if err != nil || v["status"] == "error" {
			return errResponse("SMS history unavailable")
		}
		rows, ok := v["messages"].([]any)
		if !ok {
			return errResponse("Invalid SMS database response")
		}
		for _, item := range rows {
			row, ok := item.(map[string]any)
			if !ok {
				return errResponse("Invalid SMS record")
			}
			id, ok := row["id"].(float64)
			if !ok || id <= 0 || id != float64(int(id)) {
				return errResponse("Invalid SMS identifier")
			}
			typ := "received"
			number, _ := row["sender"].(string)
			if row["type"] == "sent" {
				typ = "sent"
				number, _ = row["recipient"].(string)
			}
			content, _ := row["content"].(string)
			stamp, _ := row["timestamp"].(float64)
			messages = append(messages, map[string]any{"index": sharedSMSIndexBase + int(id), "number": number, "content": content, "time": strconv.FormatInt(int64(stamp), 10), "type": typ, "is_read": row["is_read"], "isComplete": row["complete"]})
		}
		if len(rows) < 500 {
			raw, err := json.Marshal(messages)
			if err != nil {
				return errResponse("Invalid SMS history")
			}
			return ptr(okResponse(string(raw)))
		}
	}
	return errResponse("SMS history exceeds Web page limit")
}
