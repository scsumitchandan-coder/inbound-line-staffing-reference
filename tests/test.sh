#!/usr/bin/env bash
# Verifier entrypoint: run /app/planner.py on four lines built for this submission and check every half hour.
set -uo pipefail
mkdir -p /logs/verifier
cd /tests
python3 -m pytest --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py -rA -s
rc=$?
if [ "$rc" -eq 0 ]; then echo -n 1 > /logs/verifier/reward.txt; else echo -n 0 > /logs/verifier/reward.txt; fi
exit 0
