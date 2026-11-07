#!/usr/bin/env bash
# Start all three stubs; Ctrl-C stops them all.
set -euo pipefail
cd "$(dirname "$0")"
trap 'kill 0' EXIT
python3 classifier.py &
python3 management.py &
python3 runtime.py &
wait
