package main

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

type scanModem struct {
	q                      *qmodemBackend
	commands               []string
	nr                     string
	data, radio, scanError bool
	busy                   bool
}

func scanRig(t *testing.T) *scanModem {
	t.Helper()
	q, _ := testQModem()
	q.scanJournal = filepath.Join(t.TempDir(), "scan.json")
	q.startScanGuard = func(string) error { return nil }
	q.scanWait = func(ctx context.Context, _ time.Duration) bool { return ctx.Err() == nil }
	m := &scanModem{q: q, nr: "^NRFREQLOCK: 2\n0,1\n78,620016,1,100\nOK", data: true, radio: true}
	q.call = func(_ context.Context, object, method string, p map[string]any) (map[string]any, error) {
		if method == "lease_acquire" {
			m.commands = append(m.commands, "LEASE")
			return map[string]any{"status": "success", "token": "fixture"}, nil
		}
		if method == "lease_release" {
			m.commands = append(m.commands, "RELEASE")
			return map[string]any{"status": "success"}, nil
		}
		if method == "lease_renew" {
			return map[string]any{"status": "success"}, nil
		}
		if method != "sendat" {
			return nil, errors.New("unexpected method")
		}
		cmd, _ := p["at_cmd"].(string)
		m.commands = append(m.commands, cmd)
		reply := "OK"
		switch cmd {
		case "AT+CFUN?":
			reply = "+CFUN: 1\nOK"
		case "AT+CLCC":
			reply = "OK"
		case "AT^NRFREQLOCK?":
			reply = m.nr
		case "AT^LTEFREQLOCK?":
			reply = "^LTEFREQLOCK: 3\n0,2\n1\n3\nOK"
		case "AT^SETAUTODIAL?":
			reply = "^SETAUTODIAL:0\nOK"
		case "AT^NDISSTATQRY?":
			if m.data {
				reply = "^NDISSTATQRY: 1,1,,,\"IPV4\",1,,,\"IPV6\"\nOK"
			}
		case "AT^RRCSTAT?":
			if m.busy {
				reply = "^RRCSTAT: 0,1\nOK"
			} else {
				reply = "^RRCSTAT: 0,0\nOK"
			}
		case "AT+CFUN=0":
			m.radio = false
			m.data = false
		case "AT+CFUN=1":
			m.radio = true
		case "AT^NRFREQLOCK=0":
			m.nr = "^NRFREQLOCK: 0\nOK"
		case "AT^NRFREQLOCK=2,0,1,\"78\",\"620016\",\"1\",\"100\"":
			m.nr = "^NRFREQLOCK: 2\n0,1\n78,620016,1,100\nOK"
		case "AT^NDISDUP=1,1":
			m.data = true
		case "AT^NDISDUP=1,0":
			m.data = false
		default:
			if strings.HasPrefix(cmd, "AT^CELLSCAN") {
				line := "^CELLSCAN: 3,\"00101\",3300240,100,4E,1,1,,,,1,-70,-20,50,,620016"
				final := "OK"
				if m.scanError || m.data || !m.radio || strings.Contains(m.nr, "^NRFREQLOCK: 2") {
					final = "+CME ERROR: 3"
				} else {
					payload, _ := json.Marshal(map[string]any{"port": "/dev/mock", "raw_line": line})
					q.handleEvent(payload)
				}
				payload, _ := json.Marshal(map[string]any{"port": "/dev/mock", "raw_line": final})
				q.handleEvent(payload)
				return map[string]any{"status": "success"}, nil
			}
		}
		return map[string]any{"status": "success", "response": reply}, nil
	}
	return m
}

func TestScanSnapshotParsers(t *testing.T) {
	command, hard, err := scanLockCommand("^NRFREQLOCK", "^NRFREQLOCK: 2\n1,2\n78,620016,1,100\n78,620112,1,101\nOK")
	if err != nil || !hard || command != `AT^NRFREQLOCK=2,1,2,"78,78","620016,620112","1,1","100,101"` {
		t.Fatal(command, hard, err)
	}
	for _, bad := range []string{"", "^NRFREQLOCK: 2\n0,2\n78,620016,1,100\nOK", "^NRFREQLOCK: 2\n0,1\n78,123;AT+CFUN=0,1,1\nOK"} {
		if _, _, e := scanLockCommand("^NRFREQLOCK", bad); e == nil {
			t.Fatal("accepted invalid snapshot", bad)
		}
	}
	if c, h, e := scanLockCommand("^LTEFREQLOCK", "^LTEFREQLOCK: 3\n0,2\n1\n3\nOK"); e != nil || h || c != `AT^LTEFREQLOCK=3,0,2,"1,3"` {
		t.Fatal(c, h, e)
	}
	c, e := activeNDIS("^NDISSTATQRY: 1,1,,,\"IPV4\",0,,,\"IPV6\"\n^NDISSTATQRY: 2,0,,,\"IPV4\",1,,,\"IPV6\"\nOK")
	if e != nil || len(c) != 2 {
		t.Fatal(c, e)
	}
	if !rrcIdle("^RRCSTAT: 0,0\nOK") || rrcIdle("^RRCSTAT: 0,1\nOK") {
		t.Fatal("RRC state parsing")
	}
}

func TestQModemScanRestoresOriginalCellAndData(t *testing.T) {
	for _, reject := range []bool{false, true} {
		t.Run(map[bool]string{false: "completed", true: "modem_error"}[reject], func(t *testing.T) {
			m := scanRig(t)
			m.scanError = reject
			var lines []string
			r, e := m.q.exchange(context.Background(), "AT^CELLSCAN=3", time.Second, func(s string) { lines = append(lines, s) })
			if e != nil || r.HasError() != reject {
				t.Fatal(r, e)
			}
			if !m.data || !m.radio || !strings.Contains(m.nr, "^NRFREQLOCK: 2") {
				t.Fatal("original state not restored", m.commands)
			}
			if _, e = os.Stat(m.q.scanJournal); !os.IsNotExist(e) {
				t.Fatal("journal retained", e)
			}
			if m.commands[0] != "LEASE" || m.commands[len(m.commands)-1] != "RELEASE" {
				t.Fatal(m.commands)
			}
			if !reject && len(lines) != 2 {
				t.Fatal(lines)
			}
		})
	}
}

func TestScanPreparationFailureDoesNotLoseRecovery(t *testing.T) {
	m := scanRig(t)
	m.q.startScanGuard = func(string) error { return errors.New("cannot start guard") }
	_, e := m.q.exchange(context.Background(), "AT^CELLSCAN=3", time.Second, func(string) {})
	if e == nil || !m.data || !m.radio {
		t.Fatal(e, m.commands)
	}
	for _, c := range m.commands {
		if c == "AT+CFUN=0" {
			t.Fatal("radio changed before guard ready")
		}
	}
}

func TestCancelDuringScanPreparationRestoresCell(t *testing.T) {
	m := scanRig(t)
	m.busy = true
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	_, e := m.q.exchange(ctx, "AT^CELLSCAN=3", time.Second, func(string) {})
	if e == nil || !m.data || !m.radio {
		t.Fatal(e, m.commands)
	}
	if _, e = os.Stat(m.q.scanJournal); !os.IsNotExist(e) {
		t.Fatal("recovery not completed", e)
	}
}

func TestPendingScanJournalRestoredWithoutScanning(t *testing.T) {
	m := scanRig(t)
	m.nr = "^NRFREQLOCK: 0\nOK"
	m.data = false
	s := scanSession{Changed: true, Port: "/dev/mock", ClearNR: true, NR: `AT^NRFREQLOCK=2,0,1,"78","620016","1","100"`, LTE: "AT^LTEFREQLOCK=0", Autodial: "AT^SETAUTODIAL=0", Active: []int{1}}
	if e := writeScanJournal(m.q.scanJournal, s); e != nil {
		t.Fatal(e)
	}
	if e := m.q.restoreScanJournal(context.Background(), m.q.scanJournal); e != nil || !m.data || !strings.Contains(m.nr, "^NRFREQLOCK: 2") {
		t.Fatal(e, m.commands)
	}
	for _, c := range m.commands {
		if strings.HasPrefix(c, "AT^CELLSCAN") {
			t.Fatal("recovery started another scan")
		}
	}
}

func TestScanQueriesDoNotStartAnOutage(t *testing.T) {
	if isCellScan("AT^CELLSCAN?") || isCellScan("AT^CELLSCAN=?") {
		t.Fatal("query classified as active scan")
	}
}

func TestScanDoesNotConsumeDelayedPreparationOK(t *testing.T) {
	q, _ := testQModem()
	q.scan = make(chan string, 4)
	q.handleEvent(json.RawMessage(`{"port":"/dev/mock","raw_line":"OK","correlation":"terminal","command_id":17}`))
	if len(q.scan) != 0 {
		t.Fatal("previous query completed a new scan")
	}
	q.handleEvent(json.RawMessage(`{"port":"/dev/mock","raw_line":"^CELLSCAN: fixture","correlation":"idle","command_id":0}`))
	q.handleEvent(json.RawMessage(`{"port":"/dev/mock","raw_line":"OK","correlation":"terminal","command_id":0}`))
	if len(q.scan) != 2 {
		t.Fatal("lost scan result or terminator")
	}
}
