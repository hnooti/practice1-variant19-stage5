#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
bash run.sh --config config/default.json --vfs vfs/sample_vfs.zip --script tests/full_demo.txt
