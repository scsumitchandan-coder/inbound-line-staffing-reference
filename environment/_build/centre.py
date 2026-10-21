"""Build one contact centre (history records + case + truth) from a seed. Verifier side.

usage: python centre.py <seed> <outdir> [--no-truth]
"""
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
GENSIM = os.environ.get('GENSIM', os.path.join(HERE, 'gensim'))
STANDARDS = [(0.80, 20), (0.80, 30), (0.90, 30), (0.85, 20)]


EU = ['Europe/Amsterdam', 'Europe/London', 'Europe/Helsinki']
US = ['America/New_York', 'America/Chicago']
# plan-week Mondays: EU clocks went back on 25 Oct 2026, US clocks on 1 Nov 2026
CROSS = {'EU': ['2026-11-02', '2026-11-16', '2026-11-30'], 'US': ['2026-11-09', '2026-11-23', '2026-12-07']}
NOCROSS = {'EU': ['2026-09-21', '2026-10-05', '2026-10-19'], 'US': ['2026-09-28', '2026-10-12', '2026-10-26']}
ROLES = ['rising', 'step', 'clock', 'falling-step', 'bill', 'holiday']


def draw(seed, role=None):
    r = np.random.default_rng(seed)
    p = {'seed': int(seed)}
    role = role or ROLES[r.integers(len(ROLES))]
    p['role'] = role
    region = 'US' if r.random() < 0.4 else 'EU'
    p['tz'] = (US if region == 'US' else EU)[r.integers(2 if region == 'US' else 3)]
    cross = role == 'clock' or (role != 'steady' and r.random() < 0.5)
    pool = CROSS[region] if cross else NOCROSS[region]
    p['target_monday'] = pool[r.integers(len(pool))]
    p['open_h'] = int(r.choice([7, 8, 9]))
    p['n'] = int(r.choice([22, 24, 24, 26]))
    p['target_dow'] = int(r.integers(5))
    p['weeks'] = 8
    p['base'] = float(r.uniform(2200, 5500))
    dow = [r.uniform(1.08, 1.25), r.uniform(0.96, 1.04), r.uniform(0.94, 1.02), r.uniform(0.95, 1.03), r.uniform(0.80, 0.93)]
    p['dow'] = [float(x) for x in dow]
    n = p['n']
    x = np.arange(n) + 0.5
    m1, m2 = r.uniform(3.0, 7.0), r.uniform(10.0, 15.0)
    w1, w2 = r.uniform(2.0, 4.0), r.uniform(2.5, 5.0)
    a2 = r.uniform(0.5, 1.0)
    base_prof = 0.35 + np.exp(-0.5 * ((x - m1) / w1) ** 2) + a2 * np.exp(-0.5 * ((x - m2) / w2) ** 2)
    base_prof *= np.clip(1 - 0.5 * np.maximum(0, x - (n - 4)) / 4, 0.4, 1)
    profs = []
    for d in range(5):
        pr = base_prof * r.normal(1, 0.04, n)
        if d == 0:
            pr = pr * np.linspace(1.15, 0.9, n)
        profs.append((pr / pr.sum()).tolist())
    p['profiles'] = profs
    p['day_sd'] = 0.03
    p['trend'] = {'rising': r.uniform(0.022, 0.035), 'falling-step': -r.uniform(0.018, 0.03)}.get(role, 0.0)
    p['trend'] = float(p['trend'])
    p['aht'] = float(r.uniform(240, 400))
    p['sig'] = float(r.uniform(0.5, 0.7))
    p['qf'] = float(r.uniform(0.72, 0.86))
    p['step'] = float(r.uniform(1.12, 1.22)) if role in ('step', 'falling-step') else 1.0
    p['step_week'] = int(r.integers(3, 7))
    p['pshape'] = float(r.uniform(0.7, 1.1))
    p['pscale'] = float(r.uniform(70, 170))
    p1 = r.uniform(0.55, 0.8)
    p['pred'] = [float(p1 * 0.8 ** k) for k in range(4)]
    p['rmed'] = float(r.uniform(150, 400))
    p['rsig'] = float(r.uniform(0.6, 0.9))
    p['alt'] = 0.0
    p['hidden'] = float(r.uniform(0.03, 0.12))   # withheld numbers
    p['roster'] = [float(v) for v in r.uniform(0.80, 0.95, p['weeks'])]
    tgt, awt = STANDARDS[r.integers(len(STANDARDS))]
    p['target'], p['awt'], p['short'] = tgt, awt, 5
    # billing: calls follow the monthly bill date for a few days (calendar days 1..6 after it)
    p['bill_amp'] = float(r.uniform(0.30, 0.50))
    p['bill_tau'] = float(r.uniform(1.2, 2.2))
    plan = dt.date.fromisoformat(p['target_monday']) + dt.timedelta(days=p['target_dow'])
    if role == 'bill':
        # the plan date falls 1-2 days after a bill, and that offset fell on a weekday of the records at least once
        while True:
            k = int(r.integers(1, 3))
            bdate = plan - dt.timedelta(days=k)
            seen = [d for d in history_days(p) if bill_offset(d, bdate.day) == k]
            if bdate.day <= 28 and seen:
                break
            p['target_dow'] = int(r.integers(5)); plan = dt.date.fromisoformat(p['target_monday']) + dt.timedelta(days=p['target_dow'])
        p['bill_day'] = bdate.day
    else:
        while True:
            bd = int(r.integers(1, 29))
            if bill_offset(plan, bd) >= 8:
                break
        p['bill_day'] = bd
    # closures: one weekday in the history; for the 'holiday' line also the open day before the plan date
    hist = history_days(p)
    cand = [d for d in hist[5:-5]]
    if role == 'bill':   # never close the records' only day at the plan date's offset
        k_plan = bill_offset(plan, p['bill_day'])
        cand = [d for d in cand if bill_offset(d, p['bill_day']) != k_plan]
    closed = [cand[int(r.integers(len(cand)))]]
    if role == 'holiday':
        prev = plan - dt.timedelta(days=1)
        while prev.weekday() >= 5:
            prev -= dt.timedelta(days=1)
        closed.append(prev)
    p['closed'] = sorted({d.isoformat() for d in closed})
    p['catch_c'] = float(r.uniform(0.55, 0.80))      # share of a closed day's callers who call on the next open day
    p['catch_tau'] = float(r.uniform(3.0, 7.0))      # half hours: how early in that day they call
    return p


def bill_offset(day, bill_day):
    """Calendar days since the most recent bill date on or before `day`."""
    d = day
    for k in range(0, 40):
        if d.day == bill_day:
            return k
        d -= dt.timedelta(days=1)
    return 99


def bill_mult(p, day):
    k = bill_offset(day, p['bill_day'])
    return 1.0 + (p['bill_amp'] * np.exp(-(k - 1) / p['bill_tau']) if 1 <= k <= 6 else 0.0)


def day_lam(p, day, closed_prev_volume=None):
    """Expected first attempts per half hour on an open day."""
    d = day.weekday()
    lam = p['base'] * p['dow'][d] * level(p, day) * bill_mult(p, day) * np.array(p['profiles'][d])
    if closed_prev_volume is not None:
        w = np.exp(-np.arange(p['n']) / p['catch_tau'])
        lam = lam + p['catch_c'] * closed_prev_volume * w / w.sum()
    return lam


def prev_open(p, day):
    """If the open day before `day` (skipping weekends) is closed, return that closed day."""
    prev = day - dt.timedelta(days=1)
    while prev.weekday() >= 5:
        prev -= dt.timedelta(days=1)
    return prev if prev.isoformat() in p['closed'] else None


def expected_volume(p, day):
    return float(p['base'] * p['dow'][day.weekday()] * level(p, day) * bill_mult(p, day))


def write_params(fn, lam, aht, p):
    with open(fn, 'w', newline='\n') as f:
        f.write('%d\n%s\n' % (len(lam), ' '.join('%.5f' % v for v in lam)))
        f.write('%.5f %.5f %.5f %.5f %.5f %d %s\n' % (aht, p['sig'], p['qf'], p['pshape'], p['pscale'], len(p['pred']),
                                                     ' '.join('%.5f' % v for v in p['pred'])))
        f.write('%.5f %.5f %g %g %g\n' % (p['rmed'], p['rsig'], p['awt'], p['target'], p['short']))


def history_days(p):
    tm = dt.date.fromisoformat(p['target_monday'])
    start = tm - dt.timedelta(weeks=p['weeks'])
    return [start + dt.timedelta(days=i) for i in range(7 * p['weeks']) if (start + dt.timedelta(days=i)).weekday() < 5]


def level(p, day):
    """Volume level from the trend: 1 at the history start."""
    start = dt.date.fromisoformat(p['target_monday']) - dt.timedelta(weeks=p['weeks'])
    return (1 + p['trend']) ** ((day - start).days / 7.0)


def rough_need(lam, aht):
    a = np.asarray(lam) * aht / 1800.0
    return np.maximum(1, np.round(a + 1.1 * np.sqrt(a) + 1)).astype(int)


def build(seed, out, truth=True, reps=400, role=None):
    p = draw(seed, role)
    os.makedirs(out, exist_ok=True)
    r = np.random.default_rng(seed + 7919)
    days = [d for d in history_days(p) if d.isoformat() not in p['closed']]
    n = p['n']
    stdin, roster_rows = [], []
    groups = {}          # simulation group -> (arrival vector, list of day indices); weekday groups and catch-up days
    start = history_days(p)[0]
    for k, day in enumerate(days):
        d = day.weekday()
        wk = (day - start).days // 7
        aht_scale = p['step'] if wk >= p['step_week'] else 1.0
        noise = float(np.exp(r.normal(0, p['day_sd'])))
        plain = p['base'] * p['dow'][d] * level(p, day) * np.array(p['profiles'][d])     # what the old roster expected
        need = rough_need(plain, p['aht'] * aht_scale)
        logged = np.maximum(1, np.round(need * p['roster'][wk] * r.normal(1, 0.03, n))).astype(int)
        logged -= r.binomial(logged, 0.03)
        logged = np.maximum(logged, 1)
        shut = prev_open(p, day)
        if shut is None:
            key = ('dow', d)
            groups.setdefault(key, (p['base'] * np.array(p['profiles'][d]), []))[1].append(k)
            scale = p['dow'][d] * level(p, day) * bill_mult(p, day) * noise
        else:
            key = ('catch', k)
            groups[key] = (day_lam(p, day, expected_volume(p, shut)) * noise, [k])
            scale = 1.0
        stdin.append((k, ' '.join(map(str, logged)) + ' %.6f %.6f' % (scale, aht_scale)))
        for i in range(n):
            mins = p['open_h'] * 60 + 30 * i
            roster_rows.append((day.isoformat(), '%02d:%02d' % (mins // 60, mins % 60), int(logged[i])))
    rows = []
    for g, (key, (lamv, idx)) in enumerate(sorted(groups.items(), key=lambda kv: str(kv[0]))):
        pf = os.path.join(out, f'_h{g}.txt')
        write_params(pf, lamv, p['aht'], p)
        txt = subprocess.run([GENSIM, 'log', pf, str(len(idx)), str(seed * 10 + g)],
                             input='\n'.join(s for k, s in stdin if k in idx) + '\n',
                             capture_output=True, text=True, check=True).stdout
        if not txt.rstrip().endswith('END'):
            raise RuntimeError('truncated simulator output')
        cur = None
        for line in txt.splitlines():
            if line.startswith('DAY'):
                cur = idx[int(line.split()[1])]
                continue
            if line == 'END':
                break
            f = line.split()
            rows.append((cur, float(f[0]), int(f[1]), int(f[2]), f[3], float(f[4]), float(f[5]) if f[3] == 'S' else np.nan))
        os.remove(pf)
    c = pd.DataFrame(rows, columns=['day', 't', 'chain', 'k', 'kind', 'a', 'b'])
    # callers: one customer per chain; repeats may come from the customer's second phone; some numbers withheld
    n_cust = 400000
    ck = c.day.values.astype(np.int64) * 1000003 + c.chain.values
    uniq, inv = np.unique(ck, return_inverse=True)
    cust = r.integers(n_cust, size=len(uniq))[inv]
    phone = ((c.k.values > 0) & (r.random(len(c)) < p['alt'])).astype(int)
    hkey = (cust.astype(np.int64) * 2 + phone)
    hid = (hkey * 2654435761 % 100000) < p['hidden'] * 100000
    salt = hashlib.sha256(f'centre-{seed}'.encode()).hexdigest()[:16]
    uk, uinv = np.unique(hkey, return_inverse=True)
    names = np.array([hashlib.sha1(f'{salt}-{v}'.encode()).hexdigest()[:12] for v in uk])
    caller = names[uinv]
    caller[hid] = ''
    # local -> UTC
    dates = np.array([days[k] for k in c.day.values])
    local = pd.to_datetime(pd.Series(dates).astype(str)) + pd.to_timedelta(p['open_h'] * 3600 + c.t.values, unit='s')
    utc = local.dt.tz_localize(p['tz']).dt.tz_convert('UTC')
    calls = pd.DataFrame({
        'offered_utc': utc.dt.strftime('%Y-%m-%dT%H:%M:%S.%f').str[:-3] + 'Z',
        'caller': caller,
        'outcome': np.where(c.kind.values == 'S', 'answered', 'abandoned'),
        'wait_s': np.round(c.a.values, 1),
        'handle_s': np.round(c.b.values, 1),
        '_t': utc.values,
    }).sort_values('_t').drop(columns='_t').reset_index(drop=True)
    calls.insert(0, 'call_id', np.arange(len(calls)) + 5000001)
    calls.to_csv(os.path.join(out, 'calls.csv'), index=False, lineterminator='\n', na_rep='')
    pd.DataFrame(roster_rows, columns=['date', 'interval_start', 'agents']).to_csv(
        os.path.join(out, 'agents.csv'), index=False, lineterminator='\n')
    tday = dt.date.fromisoformat(p['target_monday']) + dt.timedelta(days=p['target_dow'])
    case = {'time_zone': p['tz'], 'opens': '%02d:00' % p['open_h'], 'half_hours': n, 'plan_date': tday.isoformat(),
            'closed_dates': p['closed'],
            'standard': {'answered_within_s': p['awt'], 'share': p['target'], 'ignore_hangups_within_s': p['short']}}
    json.dump(case, open(os.path.join(out, 'case.json'), 'w'), indent=1)
    res = {'params': p, 'plan_date': tday.isoformat()}
    if truth:
        shut = prev_open(p, tday)
        lam_t = day_lam(p, tday, None if shut is None else expected_volume(p, shut))
        pf = os.path.join(out, '_truth.txt')
        write_params(pf, lam_t, p['aht'] * p['step'], p)
        res['truth'] = [int(v) for v in subprocess.run([GENSIM, 'solve', pf, str(reps), str(seed + 17)], capture_output=True,
                                                        text=True, check=True).stdout.split()]
        res['truth_params_file'] = open(pf).read()
        os.remove(pf)
    return res


if __name__ == '__main__':
    seed, out = int(sys.argv[1]), sys.argv[2]
    role = next((a.split('=', 1)[1] for a in sys.argv if a.startswith('--role=')), None)
    res = build(seed, out, truth='--no-truth' not in sys.argv, role=role)
    json.dump(res, open(os.path.join(out, '_truth.json'), 'w'), indent=1)
    print(json.dumps({k: v for k, v in res['params'].items() if k not in ('profiles',)}))
    print('truth', res.get('truth'))
