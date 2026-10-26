//go:build linux

package main

import (
	"context"
	"os"
	"os/exec"
	"syscall"
	"time"
)

func detachScanGuard(cmd *exec.Cmd) { cmd.SysProcAttr = &syscall.SysProcAttr{Setsid: true} }

func lockScanJournal(ctx context.Context, path string) (func(), error) {
	f, err := os.OpenFile(path+".lock", os.O_CREATE|os.O_RDWR, 0600)
	if err != nil {
		return nil, err
	}
	for {
		err = syscall.Flock(int(f.Fd()), syscall.LOCK_EX|syscall.LOCK_NB)
		if err == nil {
			return func() { _ = syscall.Flock(int(f.Fd()), syscall.LOCK_UN); _ = f.Close() }, nil
		}
		if !sleepCtx(ctx, 100*time.Millisecond) {
			_ = f.Close()
			return nil, ctx.Err()
		}
	}
}
