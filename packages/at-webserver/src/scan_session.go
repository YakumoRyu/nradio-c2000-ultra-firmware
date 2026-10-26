package main

import (
	"context"
	"encoding/csv"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

const scanJournalPath = "/overlay/at-webserver/scan-session.json"

type scanSession struct {
	Changed  bool   `json:"changed"`
	Port     string `json:"port"`
	Parent   int    `json:"parent"`
	Deadline int64  `json:"deadline"`
	NR       string `json:"nr"`
	LTE      string `json:"lte"`
	ClearNR  bool   `json:"clear_nr"`
	ClearLTE bool   `json:"clear_lte"`
	Autodial string `json:"autodial"`
	Active   []int  `json:"active"`
}

func scanLockCommand(prefix, text string) (string, bool, error) {
	var rows []string
	for _, line := range strings.Split(text, "\n") {
		line = strings.TrimSpace(line)
		if strings.HasPrefix(line, prefix+":") {
			rows = []string{strings.TrimSpace(strings.TrimPrefix(line, prefix+":"))}
			continue
		}
		if len(rows) > 0 && line != "" && line != "OK" && !strings.HasPrefix(line, "^") && !strings.HasPrefix(line, "+") {
			rows = append(rows, line)
		}
	}
	if len(rows) == 0 {
		return "", false, errors.New("无法读取原锁频设置")
	}
	mode, err := strconv.Atoi(rows[0])
	if err != nil || mode < 0 || mode > 3 {
		return "", false, errors.New("原锁频类型无效")
	}
	if mode == 0 {
		return "AT" + prefix + "=0", false, nil
	}
	if len(rows) < 3 {
		return "", false, errors.New("原锁频设置不完整")
	}
	header := strings.Split(rows[1], ",")
	if len(header) != 2 {
		return "", false, errors.New("原锁频列表无效")
	}
	mobility, e1 := strconv.Atoi(header[0])
	count, e2 := strconv.Atoi(header[1])
	if e1 != nil || e2 != nil || mobility < 0 || mobility > 1 || count < 1 || count > 20 || len(rows) != count+2 {
		return "", false, errors.New("原锁频数量无效")
	}
	columns := 1
	if mode == 1 {
		columns = 2
		if prefix == "^NRFREQLOCK" {
			columns = 3
		}
	}
	if mode == 2 {
		columns = 3
		if prefix == "^NRFREQLOCK" {
			columns = 4
		}
	}
	values := make([][]string, columns)
	for _, row := range rows[2:] {
		fields := strings.Split(row, ",")
		if len(fields) != columns {
			return "", false, errors.New("原锁频字段不完整")
		}
		for i, f := range fields {
			n, e := strconv.ParseUint(strings.TrimSpace(f), 10, 32)
			if e != nil {
				return "", false, errors.New("原锁频字段无效")
			}
			values[i] = append(values[i], strconv.FormatUint(n, 10))
		}
	}
	command := fmt.Sprintf("AT%s=%d,%d,%d", prefix, mode, mobility, count)
	for _, col := range values {
		command += ",\"" + strings.Join(col, ",") + "\""
	}
	return command, mode == 1 || mode == 2, nil
}

func activeNDIS(text string) ([]int, error) {
	active := map[int]bool{}
	for _, line := range strings.Split(text, "\n") {
		line = strings.TrimSpace(line)
		if !strings.HasPrefix(line, "^NDISSTATQRY:") {
			continue
		}
		fields, err := csv.NewReader(strings.NewReader(strings.TrimSpace(strings.TrimPrefix(line, "^NDISSTATQRY:")))).Read()
		if err != nil || len(fields) < 5 {
			return nil, errors.New("数据连接状态格式无效")
		}
		cid, e := strconv.Atoi(fields[0])
		if e != nil || cid < 1 || cid > 11 {
			return nil, errors.New("数据连接编号无效")
		}
		if fields[1] == "1" || len(fields) >= 9 && fields[5] == "1" {
			active[cid] = true
		}
	}
	var out []int
	for cid := 1; cid <= 11; cid++ {
		if active[cid] {
			out = append(out, cid)
		}
	}
	return out, nil
}

func autodialCommand(text string) (string, error) {
	for _, line := range strings.Split(text, "\n") {
		line = strings.TrimSpace(line)
		if !strings.HasPrefix(line, "^SETAUTODIAL:") {
			continue
		}
		f := strings.Split(strings.TrimSpace(strings.TrimPrefix(line, "^SETAUTODIAL:")), ",")
		if f[0] == "0" {
			return "AT^SETAUTODIAL=0", nil
		}
		if f[0] == "1" && len(f) == 2 && (f[1] == "1" || f[1] == "2") {
			return "AT^SETAUTODIAL=1," + f[1], nil
		}
	}
	return "", errors.New("无法读取自动拨号设置")
}

func rrcIdle(text string) bool {
	for _, line := range strings.Split(text, "\n") {
		if strings.HasPrefix(strings.TrimSpace(line), "^RRCSTAT:") {
			f := strings.Split(strings.TrimSpace(strings.TrimPrefix(strings.TrimSpace(line), "^RRCSTAT:")), ",")
			return len(f) >= 2 && (f[1] == "0" || f[1] == "2")
		}
	}
	return false
}

func (q *qmodemBackend) scanAT(ctx context.Context, command string) (ATResponse, error) {
	r, e := q.exchange(ctx, command, 8*time.Second, nil)
	if e != nil {
		return r, e
	}
	if !r.OK() {
		return r, fmt.Errorf("%s: %s", strings.Split(command, "=")[0], r.Text())
	}
	return r, nil
}

func writeScanJournal(path string, s scanSession) error {
	if err := os.MkdirAll(filepath.Dir(path), 0700); err != nil {
		return err
	}
	b, err := json.Marshal(s)
	if err != nil {
		return err
	}
	f, err := os.OpenFile(path+".new", os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0600)
	if err != nil {
		return err
	}
	_, err = f.Write(b)
	if err == nil {
		err = f.Sync()
	}
	closeErr := f.Close()
	if err != nil {
		return err
	}
	if closeErr != nil {
		return closeErr
	}
	return os.Rename(path+".new", path)
}

func (q *qmodemBackend) prepareScan(ctx context.Context, timeout time.Duration) (restore func() error, err error) {
	path := q.scanJournal
	if path == "" {
		path = scanJournalPath
	}
	if _, e := os.Stat(path); e == nil {
		return nil, errors.New("上次扫描正在恢复网络，请稍后重试")
	}
	query := func(command string) (string, error) { r, e := q.scanAT(ctx, command); return r.Text(), e }
	cfun, e := query("AT+CFUN?")
	if e != nil || !strings.Contains(cfun, "+CFUN: 1") {
		return nil, errors.New("扫描需要模组处于正常工作模式")
	}
	calls, e := query("AT+CLCC")
	if e != nil {
		return nil, e
	}
	if strings.Contains(calls, "+CLCC:") {
		return nil, errors.New("通话结束后再扫描")
	}
	port, _ := q.mapping()
	s := scanSession{Port: port, Parent: os.Getpid(), Deadline: time.Now().Add(timeout + 100*time.Second).Unix()}
	nr, e := query("AT^NRFREQLOCK?")
	if e != nil {
		return nil, e
	}
	s.NR, s.ClearNR, e = scanLockCommand("^NRFREQLOCK", nr)
	if e != nil {
		return nil, e
	}
	lte, e := query("AT^LTEFREQLOCK?")
	if e != nil {
		return nil, e
	}
	s.LTE, s.ClearLTE, e = scanLockCommand("^LTEFREQLOCK", lte)
	if e != nil {
		return nil, e
	}
	// Scan against the modem's complete supported bands, then restore both
	// original lists. This also avoids stale restrictions across a CFUN cycle.
	s.ClearNR = s.NR != "AT^NRFREQLOCK=0"
	s.ClearLTE = s.LTE != "AT^LTEFREQLOCK=0"
	auto, e := query("AT^SETAUTODIAL?")
	if e != nil {
		return nil, e
	}
	s.Autodial, e = autodialCommand(auto)
	if e != nil {
		return nil, e
	}
	data, e := query("AT^NDISSTATQRY?")
	if e != nil {
		return nil, e
	}
	s.Active, e = activeNDIS(data)
	if e != nil {
		return nil, e
	}
	if e = writeScanJournal(path, s); e != nil {
		return nil, e
	}
	cleanup := func() error {
		c, cancel := context.WithTimeout(context.Background(), 80*time.Second)
		defer cancel()
		return q.restoreScanJournal(c, path)
	}
	restore = cleanup
	defer func() {
		if err != nil {
			if e := cleanup(); e != nil {
				err = fmt.Errorf("%v；恢复网络：%v", err, e)
			}
		}
	}()
	if q.startScanGuard != nil {
		err = q.startScanGuard(path)
	} else {
		err = startScanGuard(path)
	}
	if err != nil {
		return nil, err
	}
	s.Changed = true
	if err = writeScanJournal(path, s); err != nil {
		return nil, err
	}
	if s.Autodial != "AT^SETAUTODIAL=0" {
		if _, err = q.scanAT(ctx, "AT^SETAUTODIAL=0"); err != nil {
			return nil, err
		}
	}
	if s.ClearNR || s.ClearLTE {
		if _, err = q.scanAT(ctx, "AT+CFUN=0"); err != nil {
			return nil, err
		}
		if s.ClearNR {
			if _, err = q.scanAT(ctx, "AT^NRFREQLOCK=0"); err != nil {
				return nil, err
			}
		}
		if s.ClearLTE {
			if _, err = q.scanAT(ctx, "AT^LTEFREQLOCK=0"); err != nil {
				return nil, err
			}
		}
		if _, err = q.scanAT(ctx, "AT+CFUN=1"); err != nil {
			return nil, err
		}
		// CFUN acknowledges before NR registration and IMS startup finish.
		// An immediate RRC=idle sample here is not a settled scan-ready radio.
		wait := q.scanWait
		if wait == nil {
			wait = sleepCtx
		}
		if !wait(ctx, 8*time.Second) {
			return nil, ctx.Err()
		}
	} else {
		for _, cid := range s.Active {
			if _, err = q.scanAT(ctx, fmt.Sprintf("AT^NDISDUP=%d,0", cid)); err != nil {
				return nil, err
			}
		}
	}
	// Registration and IMS activity can keep RRC connected after PDP teardown.
	for i := 0; i < 25; i++ {
		var state string
		state, err = query("AT^RRCSTAT?")
		if err == nil && rrcIdle(state) {
			return restore, nil
		}
		if !sleepCtx(ctx, 2*time.Second) {
			return nil, ctx.Err()
		}
	}
	return nil, errors.New("无线连接仍忙碌，已恢复原网络，请稍后扫描")
}

func startScanGuard(path string) error {
	exe, err := os.Executable()
	if err != nil {
		return err
	}
	cmd := exec.Command(exe, "-scan-recovery", path, "-scan-watchdog")
	detachScanGuard(cmd)
	cmd.Stdin = nil
	cmd.Stdout = nil
	cmd.Stderr = nil
	if err = cmd.Start(); err != nil {
		return err
	}
	go func() { _ = cmd.Wait() }()
	return nil
}

func (q *qmodemBackend) restoreScanJournal(ctx context.Context, path string) error {
	unlock, err := lockScanJournal(ctx, path)
	if err != nil {
		return err
	}
	defer unlock()
	raw, err := os.ReadFile(path)
	if os.IsNotExist(err) {
		return nil
	}
	if err != nil {
		return err
	}
	var s scanSession
	if json.Unmarshal(raw, &s) != nil || !strings.HasPrefix(s.Port, "/dev/") {
		return errors.New("扫描恢复记录无效")
	}
	if !s.Changed {
		return os.Remove(path)
	}
	if !strings.HasPrefix(s.NR, "AT^NRFREQLOCK=") || !strings.HasPrefix(s.LTE, "AT^LTEFREQLOCK=") || !strings.HasPrefix(s.Autodial, "AT^SETAUTODIAL=") {
		return errors.New("扫描恢复命令无效")
	}
	if s.ClearNR || s.ClearLTE {
		if _, err = q.scanAT(ctx, "AT+CFUN=0"); err != nil {
			return err
		}
		var lockErr error
		if s.ClearNR {
			_, lockErr = q.scanAT(ctx, s.NR)
		}
		if s.ClearLTE {
			_, e := q.scanAT(ctx, s.LTE)
			if lockErr == nil {
				lockErr = e
			}
		}
		_, radioErr := q.scanAT(ctx, "AT+CFUN=1")
		if lockErr != nil {
			return lockErr
		}
		if radioErr != nil {
			return radioErr
		}
	}
	if s.Autodial != "AT^SETAUTODIAL=0" {
		if _, err = q.scanAT(ctx, s.Autodial); err != nil {
			return err
		}
	}
	for _, cid := range s.Active {
		if cid < 1 || cid > 11 {
			return errors.New("恢复连接编号无效")
		}
		var last error
		for i := 0; i < 12; i++ {
			var r ATResponse
			r, last = q.scanAT(ctx, "AT^NDISSTATQRY?")
			if last == nil {
				active, e := activeNDIS(r.Text())
				if e == nil {
					for _, v := range active {
						if v == cid {
							last = nil
							goto restored
						}
					}
				}
			}
			if s.Autodial == "AT^SETAUTODIAL=0" {
				_, last = q.scanAT(ctx, fmt.Sprintf("AT^NDISDUP=%d,1", cid))
			}
			if !sleepCtx(ctx, 2*time.Second) {
				return ctx.Err()
			}
		}
		return fmt.Errorf("等待数据连接恢复超时: %v", last)
	restored:
	}
	return os.Remove(path)
}

func recoverScanFile(path string, watch bool) error {
	if path != scanJournalPath {
		return errors.New("扫描恢复路径无效")
	}
	for {
		raw, err := os.ReadFile(path)
		if os.IsNotExist(err) {
			return nil
		}
		if err != nil {
			return err
		}
		var s scanSession
		if json.Unmarshal(raw, &s) != nil {
			return errors.New("扫描恢复记录无效")
		}
		if watch {
			if _, e := os.Stat(fmt.Sprintf("/proc/%d", s.Parent)); e == nil && time.Now().Unix() < s.Deadline {
				time.Sleep(2 * time.Second)
				continue
			}
		}
		q := newQModemBackend(s.Port, func(unsolicited) {})
		ctx, cancel := context.WithTimeout(context.Background(), 90*time.Second)
		// A dead scan may still own its lease; the same owner can restore it.
		err = q.restoreScanJournal(ctx, path)
		cancel()
		return err
	}
}
