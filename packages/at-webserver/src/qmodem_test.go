package main

import (
	"context"
	"encoding/json"
	"errors"
	"sync"
	"testing"
	"time"
)

func testQModem() (*qmodemBackend, *[]string) {
	calls := []string{}
	q := newQModemBackend("/dev/mock", func(unsolicited) {})
	q.uci = func(context.Context) (string, error) {
		return "qmodem.test='modem-device'\nqmodem.test.at_port='/dev/mock'", nil
	}
	q.call = func(_ context.Context, object, method string, p map[string]any) (map[string]any, error) {
		calls = append(calls, object+"."+method)
		switch method {
		case "config_get":
			return map[string]any{"mode": "database_poll"}, nil
		case "sync":
			return map[string]any{"status": "success"}, nil
		case "list":
			return map[string]any{"messages": []any{map[string]any{"id": float64(7), "sender": "synthetic", "content": "合成短信", "timestamp": float64(1700000000), "type": "received", "is_read": true, "complete": true}}}, nil
		case "delete":
			if p["id"] != 7 {
				panic("wrong database ID")
			}
			return map[string]any{"status": "success", "deleted": float64(1)}, nil
		case "sendat":
			return map[string]any{"status": "success", "response": "AT\r\nOK\r\n"}, nil
		}
		return nil, errors.New("unexpected call")
	}
	return q, &calls
}
func TestSharedSMSDoesNotClaimOrReadSIM(t *testing.T) {
	q, calls := testQModem()
	r := q.sharedSMS(context.Background(), "AT+CMGL=4\r")
	if r == nil || !r.Success {
		t.Fatal(r)
	}
	var rows []map[string]any
	if json.Unmarshal([]byte(*r.Data), &rows) != nil || len(rows) != 1 || rows[0]["index"] != float64(1000007) || rows[0]["is_read"] != true {
		t.Fatal(rows)
	}
	if len(*calls) != 3 || (*calls)[0] != "qmodem.sms.config_get" || (*calls)[1] != "qmodem.sms.sync" || (*calls)[2] != "qmodem.sms.list" {
		t.Fatal(*calls)
	}
}
func TestMultiplePagesSyncOnce(t *testing.T) {
	q, calls := testQModem()
	var wg sync.WaitGroup
	for i := 0; i < 8; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			r := q.sharedSMS(context.Background(), "AT+CMGL=4")
			if r == nil || !r.Success {
				t.Error(r)
			}
		}()
	}
	wg.Wait()
	count := 0
	for _, m := range *calls {
		if m == "qmodem.sms.sync" {
			count++
		}
	}
	if count != 1 {
		t.Fatal(count)
	}
}
func TestVirtualDeleteAndRealSlots(t *testing.T) {
	q, calls := testQModem()
	for _, cmd := range []string{"AT+CMGD=7", "AT+CMGD=0,4", "AT+CMGS=27", "AT^HCSQ?"} {
		if q.sharedSMS(context.Background(), cmd) != nil {
			t.Fatal(cmd)
		}
	}
	if len(*calls) != 0 {
		t.Fatal(*calls)
	}
	if r := q.sharedSMS(context.Background(), "AT+CMGD=1000007"); r == nil || !r.Success {
		t.Fatal(r)
	}
}
func TestSMSFailureDoesNotReportEmptySuccess(t *testing.T) {
	for _, failed := range []string{"config_get", "sync", "list"} {
		q, _ := testQModem()
		original := q.call
		q.call = func(ctx context.Context, o, m string, p map[string]any) (map[string]any, error) {
			if m == failed {
				return nil, errors.New("private data must not be reflected")
			}
			return original(ctx, o, m, p)
		}
		r := q.sharedSMS(context.Background(), "AT+CMGL=4")
		if r == nil || r.Success || r.Data != nil || *r.Error == "private data must not be reflected" {
			t.Fatal(r)
		}
	}
}
func TestDirectModeDoesNotAllowVirtualDelete(t *testing.T) {
	q, _ := testQModem()
	q.call = func(context.Context, string, string, map[string]any) (map[string]any, error) {
		return map[string]any{"mode": "direct"}, nil
	}
	if q.sharedSMS(context.Background(), "AT+CMGL=4") != nil {
		t.Fatal("direct list intercepted")
	}
	if r := q.sharedSMS(context.Background(), "AT+CMGD=1000007"); r == nil || r.Success {
		t.Fatal(r)
	}
}
func TestURCDoesNotReadOrForwardSMS(t *testing.T) {
	q, calls := testQModem()
	client := NewATClient(ATConfig{}, NewLogger(LevelError))
	client.q = q
	ws := &captureBroadcaster{}
	d := NewDispatcher(client, NewNotifier(NotificationConfig{}, client.log), ws, client.log)
	d.handleNewSMS(context.Background(), `+CMTI: "ME",7`)
	if len(*calls) != 0 || ws.count != 1 {
		t.Fatal(*calls, ws.count)
	}
}

type captureBroadcaster struct{ count int }

func (c *captureBroadcaster) Broadcast(any) { c.count++ }
func TestOtherDeviceAndQueryNotURC(t *testing.T) {
	q, _ := testQModem()
	got := 0
	q.emit = func(unsolicited) { got++ }
	q.handleEvent(json.RawMessage(`{"port":"/dev/other","raw_line":"+CMTI: x","correlation":"idle"}`))
	q.handleEvent(json.RawMessage(`{"port":"/dev/mock","raw_line":"^HCSQ: query","correlation":"response"}`))
	q.handleEvent(json.RawMessage(`{"port":"/dev/mock","raw_line":"^HCSQ: urc","correlation":"idle"}`))
	if got != 1 {
		t.Fatal(got)
	}
}
func TestNormalCommandsThroughUBus(t *testing.T) {
	q, calls := testQModem()
	r, e := q.exchange(context.Background(), "AT", 2*time.Second, nil)
	if e != nil || !r.OK() || len(*calls) != 1 || (*calls)[0] != "at-daemon.sendat" {
		t.Fatal(r, e, *calls)
	}
}
func TestLongScanUsesLeaseAndEvents(t *testing.T) {
	q, _ := testQModem()
	calls := []string{}
	q.call = func(_ context.Context, _, m string, p map[string]any) (map[string]any, error) {
		calls = append(calls, m)
		if m == "lease_acquire" {
			return map[string]any{"status": "success", "token": "synthetic"}, nil
		}
		if m == "sendat" {
			q.handleEvent(json.RawMessage(`{"port":"/dev/mock","raw_line":"^CELLSCAN: synthetic","correlation":"idle"}`))
			q.handleEvent(json.RawMessage(`{"port":"/dev/mock","raw_line":"OK","correlation":"idle"}`))
		}
		return map[string]any{"status": "success"}, nil
	}
	stream := []string{}
	r, e := q.exchange(context.Background(), "AT^CELLSCAN=0", time.Second, func(s string) { stream = append(stream, s) })
	if e != nil || !r.OK() || len(stream) != 2 || len(calls) != 3 || calls[2] != "lease_release" {
		t.Fatal(r, e, stream, calls)
	}
}
