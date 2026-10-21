"""Grade /app/planner.py on inbound lines built for this submission.

Six lines are generated from a hash of the submitted planner, one of each kind the generator knows: volume rising
through the records, a handle-time step, a clock change inside the records, volume falling with a handle-time
step, a plan date in the days after a monthly bill, and a plan date that follows a closure.
For each line the verifier computes, as root and out of the planner's reach:
  - the true requirement: the fewest agents per half hour, working forward, that meet the line's contract on its
    generating model (gensim solve);
  - the plans of two sound methods run on the same records (sound.py).
The planner is then run on each line as the unprivileged user `verifier`. A half hour is accepted when the planner's
number lies within [min - 1, max + 1] of the true requirement and the sound plans. Every half hour of every line must
be accepted.

Measured margins (battery draw 20261015 on this tree, authoring/evidence/BATTERY.md): the reference and both band
methods stay within -3..+4 agents of the true requirement on all six lines; three further sound variants fall
inside the range on every line; nine rivals (one wrong reading each) fall outside on at least one line; a tenth
(every attempt counted as new) is reported, not claimed. The local harbor Oracle on this tree scored reward 1.
"""
import hashlib
import json
import os
import pwd
import shutil
import signal
import stat
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TESTS)
import centre  # noqa: E402

PLANNER = '/app/planner.py'
SALT = b'inbound-line-staffing/2026-10'
N_LINES = 6
PLAN_TIMEOUT = 1200          # seconds per line for the submitted planner
PLAN_CPUS = 2
TRUTH_REPS = 300
WIDEN = 1
MAX_PLANNER_BYTES = 2_000_000
MAX_OUTPUT_BYTES = 200_000
USER = 'verifier'
WORK = '/tmp/grade'
SECRET = '/tmp/grade-secret'
SOUND = ('reference', 'recent')   # the two methods of sound.py

RUNNER = r'''
import importlib.util, json, math, sys
spec = importlib.util.spec_from_file_location("planner", "/app/planner.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
out = [int(math.floor(float(v) + 0.5)) for v in mod.plan(sys.argv[1])]
sys.stdout.write("\nPLAN " + json.dumps(out) + "\n")
'''


def _read_planner():
    """The planner's bytes, read without following links; None if it is not a plain regular file."""
    try:
        st = os.lstat(PLANNER)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_size > MAX_PLANNER_BYTES:
        return None
    fd = os.open(PLANNER, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | os.O_NONBLOCK)
    try:
        if os.fstat(fd).st_ino != st.st_ino:
            return None
        data = b''
        while len(data) <= MAX_PLANNER_BYTES:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            data += chunk
    finally:
        os.close(fd)
    return data if len(data) <= MAX_PLANNER_BYTES else None


def _seeds(data):
    h = hashlib.sha256(SALT + data).digest()
    return [int.from_bytes(h[4 * i:4 * i + 4], 'big') % 9_000_000 + 1000 for i in range(N_LINES)]


def _kill_user():
    try:
        uid = pwd.getpwnam(USER).pw_uid
    except KeyError:
        return
    for pid in os.listdir('/proc'):
        if not pid.isdigit():
            continue
        try:
            if os.stat(f'/proc/{pid}').st_uid == uid:
                os.kill(int(pid), signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass


def _prepare(i, seed):
    """Build line i as root; records go to a world-readable folder, truth and sound plans to the root-only folder."""
    line = os.path.join(WORK, f'line{i}')
    os.makedirs(line, exist_ok=True)
    res = centre.build(seed, line, truth=True, reps=TRUTH_REPS, role=centre.ROLES[i % len(centre.ROLES)])
    for name in os.listdir(line):
        if name not in ('calls.csv', 'agents.csv', 'case.json'):
            os.remove(os.path.join(line, name))
    plans = {'truth': res['truth']}
    for name in SOUND:
        out = os.path.join(SECRET, f'line{i}-{name}.csv')
        r = subprocess.run([sys.executable, os.path.join(TESTS, 'sound.py'), line, out, name],
                           capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(f'sound method {name} failed on line {i}: {r.stderr[-1500:]}')
        with open(out) as fh:
            plans[name] = [int(row.split(',')[1]) for row in fh.read().split()[1:]]
    json.dump({'seed': seed, 'role': res['params']['role'], 'plans': plans},
              open(os.path.join(SECRET, f'line{i}.json'), 'w'))
    for root, dirs, files in os.walk(line):
        os.chmod(root, 0o755)
        for f in files:
            os.chmod(os.path.join(root, f), 0o644)
    return plans


def _run_planner(i):
    line = os.path.join(WORK, f'line{i}')
    home = os.path.join(WORK, f'home{i}')
    os.makedirs(home, exist_ok=True)
    pw = pwd.getpwnam(USER)
    os.chown(home, pw.pw_uid, pw.pw_gid)
    os.chmod(home, 0o700)
    runner = os.path.join(WORK, 'runner.py')
    env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': home, 'TMPDIR': home, 'PYTHONDONTWRITEBYTECODE': '1',
           'OMP_NUM_THREADS': str(PLAN_CPUS), 'OPENBLAS_NUM_THREADS': str(PLAN_CPUS), 'MKL_NUM_THREADS': str(PLAN_CPUS)}

    def demote():
        os.setgid(pw.pw_gid)
        os.setgroups([])
        os.setuid(pw.pw_uid)
        os.setsid()

    t0 = time.time()
    proc = subprocess.Popen([sys.executable, runner, line], cwd='/app', env=env, preexec_fn=demote,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        out, err = proc.communicate(timeout=PLAN_TIMEOUT)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        return None, f'no plan within {PLAN_TIMEOUT} s'
    out = out[-MAX_OUTPUT_BYTES:].decode('utf-8', 'replace')
    for row in out.splitlines()[::-1]:
        if row.startswith('PLAN '):
            try:
                plan = json.loads(row[5:])
            except ValueError:
                break
            return plan, f'ok in {time.time() - t0:.0f} s'
    return None, 'planner failed: ' + err[-1500:].decode('utf-8', 'replace')


@pytest.fixture(scope='session')
def graded():
    assert os.geteuid() == 0, 'the verifier must run as root (it drops to the user verifier to run the planner)'
    data = _read_planner()
    assert data is not None, '/app/planner.py must be a regular file'
    os.chmod(TESTS, 0o700)
    for d in (WORK, SECRET):
        shutil.rmtree(d, ignore_errors=True)
    os.makedirs(WORK, 0o755)
    os.makedirs(SECRET, 0o700)
    os.chmod(WORK, 0o755)
    with open(os.path.join(WORK, 'runner.py'), 'w') as fh:
        fh.write(RUNNER)
    os.chmod(os.path.join(WORK, 'runner.py'), 0o644)
    seeds = _seeds(data)
    with ThreadPoolExecutor(2) as ex:
        plans = list(ex.map(_prepare, range(N_LINES), seeds))
    _kill_user()
    runs = [_run_planner(i) for i in range(N_LINES)]
    _kill_user()
    report = []
    for i, (p, (got, status)) in enumerate(zip(plans, runs)):
        stack = list(zip(*p.values()))
        lo = [min(c) - WIDEN for c in stack]
        hi = [max(c) + WIDEN for c in stack]
        report.append({'line': i, 'seed': seeds[i], 'status': status, 'plan': got, 'lo': lo, 'hi': hi,
                       'truth': p['truth']})
        print(f'line {i} (seed {seeds[i]}): {status}')
        print('  low ', lo)
        print('  high', hi)
        print('  plan', got)
    return report


@pytest.mark.parametrize('i', range(N_LINES))
def test_line(graded, i):
    r = graded[i]
    assert r['plan'] is not None, r['status']
    assert isinstance(r['plan'], list) and len(r['plan']) == len(r['truth']), 'one whole number per half hour'
    bad = [k for k, (v, a, b) in enumerate(zip(r['plan'], r['lo'], r['hi'])) if not (a <= v <= b)]
    assert not bad, f'half hours outside the accepted range: {bad}'
