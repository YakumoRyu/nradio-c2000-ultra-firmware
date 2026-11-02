#!/usr/bin/python3
"""Install or roll back the signal-preference and PCDN forwarding fixes."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('action', choices=['apply', 'rollback'])
p.add_argument('--root', default='/')
args = p.parse_args()
base = Path(__file__).resolve().parent
installers = ['cell-install.py', 'pcdn-install.py']
if args.action == 'rollback':
    installers.reverse()
results = []
for script in installers:
    command = [sys.executable, str(base / script), args.action, '--root', args.root,
               '--payload', str(base / 'payload')]
    result = subprocess.run(command, capture_output=True, text=True, timeout=45)
    if result.returncode:
        raise RuntimeError(script + ': ' + result.stderr[-500:])
    results.append(json.loads(result.stdout))
print(json.dumps({'changed': any(x.get('changed', False) for x in results),
                  'action': args.action, 'results': results}))
