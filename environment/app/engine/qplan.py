"""Python front end for the qplan queue engine (see ENGINE.md).

    from qplan import Line, simulate, staff

    line = Line(arrivals=[...], handle_mean=300, handle_sigma=0.6, queued_factor=0.85,
                patience_shape=0.9, patience_scale=140, redial=[0.6, 0.5, 0.4],
                redial_median=240, redial_sigma=0.8, answer_within=20, ignore_hangups_within=5)
    table = simulate(line, agents=[...], days=400, seed=1)    # pandas DataFrame, one row per half hour
    plan = staff(line, target=0.80, days=400, seed=1)          # list of agents per half hour
"""
import dataclasses
import io
import os
import subprocess
import tempfile
from typing import List, Optional

import pandas as pd

BIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'qplan.exe' if os.name == 'nt' else 'qplan')


@dataclasses.dataclass
class Line:
    arrivals: List[float]                 # expected first attempts in each half hour
    handle_mean: float                    # mean handle time (s) of a call answered without waiting
    handle_sigma: float                   # sigma of log handle time
    queued_factor: float = 1.0            # handle-time factor for a call that waited before being answered
    patience_shape: float = 1.0           # Weibull shape of how long a caller will wait
    patience_scale: Optional[float] = None  # Weibull scale (s); None: callers never hang up
    redial: List[float] = dataclasses.field(default_factory=lambda: [0.0])  # P(ring again) after 1st, 2nd, ... hang-up
    redial_median: float = 240.0          # median delay (s) from hanging up to ringing again (lognormal)
    redial_sigma: float = 0.8
    answer_within: float = 20.0           # service threshold (s)
    ignore_hangups_within: float = 5.0    # hang-ups this quick are not counted as offered


def _write(line, fh):
    n = len(line.arrivals)
    fh.write('%d\n%s\n' % (n, ' '.join('%.6f' % float(a) for a in line.arrivals)))
    scale = -1.0 if line.patience_scale is None else float(line.patience_scale)
    red = list(line.redial) or [0.0]
    fh.write('%.6f %.6f %.6f %.6f %.6f %d %s\n' % (line.handle_mean, line.handle_sigma, line.queued_factor,
                                                   line.patience_shape, scale, len(red), ' '.join('%.6f' % p for p in red)))
    fh.write('%.6f %.6f %.6f %.6f\n' % (line.redial_median, line.redial_sigma, line.answer_within, line.ignore_hangups_within))


def _run(args, line):
    with tempfile.NamedTemporaryFile('w', suffix='.line', delete=False) as fh:
        _write(line, fh)
        path = fh.name
    try:
        out = subprocess.run([BIN, args[0], path] + [str(a) for a in args[1:]], capture_output=True, text=True, check=True)
    finally:
        os.unlink(path)
    return out.stdout


def simulate(line, agents, days=400, seed=1):
    """Average per half hour over `days` simulated days with the given agents logged in."""
    if len(agents) != len(line.arrivals):
        raise ValueError('one agent number per half hour')
    return pd.read_csv(io.StringIO(_run(['simulate', int(days), int(seed)] + [int(a) for a in agents], line)))


def staff(line, target=0.80, days=400, seed=1):
    """Fewest agents per half hour, working forward from the first, so every half hour reaches `target`."""
    return [int(v) for v in _run(['staff', int(days), int(seed), float(target)], line).split()]
