#!/bin/bash
# Install the reference planner: it estimates the line's behaviour from its records (local clock, repeat attempts,
# withheld numbers, handle-time level and speed-up, volume trend, patience) and staffs each half hour against the
# contract's service level with the engine's simulator.
set -euo pipefail
cp /solution/planner.py /app/planner.py
python3 /app/planner.py /app/practice
