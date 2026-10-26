//go:build !linux

package main

import (
	"context"
	"errors"
	"os/exec"
)

func detachScanGuard(*exec.Cmd) {}

func lockScanJournal(context.Context, string) (func(), error) {
	return nil, errors.New("QModem扫描恢复需要Linux文件锁")
}
