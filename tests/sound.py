"""The two sound planning methods whose plans, with the true requirement, span the accepted range.

    python sound.py <line_dir> <out_csv> reference|recent

- reference: the reference planner's method (solution/planner.py), unchanged.
- recent: the same estimates, except that handle times come from the last two weeks of the records whatever
  happened before, and the volume trend is always carried to the plan date, however small.

Both are sound readings of the records; neither has a setting that selects a wrong method. Both staff with the
verifier's own simulator (gensim `solve`, the contract's measure), as the reference does with its embedded copy.
Measured margins are in test_outputs.py's docstring.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile

import numpy as np
import pandas as pd
from scipy.optimize import minimize

DAYS, SEED = 300, 11          # simulated days and seed of the staffing search
TREND_Z, STEP_Z = 2.5, 4.0    # significance of the volume trend and of the handle-time change point


def load(line_dir):
    case = json.load(open(os.path.join(line_dir, 'case.json')))
    c = pd.read_csv(os.path.join(line_dir, 'calls.csv'), dtype={'caller': str})
    c['caller'] = c.caller.fillna('')
    return case, c


def localise(case, c):
    lt = pd.to_datetime(c.offered_utc, utc=True).dt.tz_convert(case['time_zone']).dt.tz_localize(None)
    oh, om = map(int, case['opens'].split(':'))
    c = c.copy()
    c['date'] = lt.dt.normalize()
    c['sec'] = (lt - c.date).dt.total_seconds() - (oh * 3600 + om * 60)
    c['iv'] = (c.sec // 1800).astype(int)
    c['ab'] = c.outcome.eq('abandoned')
    c['hang'] = np.where(c.ab, c.sec + c.wait_s, np.nan)
    return c.sort_values(['date', 'sec']).reset_index(drop=True)


def linked_redials(c):
    idc = c[c.caller != ''].copy()
    g = idc.groupby(['caller', 'date'])
    idc['prev_ab'] = g.ab.shift(1)
    idc['prev_hang'] = g.hang.shift(1)
    idc['redial'] = idc.prev_ab.eq(True) & ((idc.sec - idc.prev_hang) < 3 * 3600)
    idc['chain'] = (~idc.redial).astype(int).groupby([idc.caller, idc.date]).cumsum()
    idc['k'] = idc.groupby(['caller', 'date', 'chain']).cumcount()
    idc['next_red'] = g.redial.shift(-1).astype('boolean').fillna(False).astype(bool)
    return idc


def bill_offset(day, bill_day):
    """Calendar days since the most recent bill date (day `bill_day` of a month) on or before `day`."""
    d = pd.Timestamp(day)
    for k in range(40):
        if d.day == bill_day:
            return k
        d -= pd.Timedelta(days=1)
    return 99


def bill_tail(m, beta, keep, day, use_trend):
    """Bill effect for a day whose offset after the bill date never fell on an open day in the records: an exponential
    decay fitted to the offsets that did. 1 when the offset was observed (already in the fit) or is beyond six days."""
    k = bill_offset(day, m['bill_day'])
    first_col = 6 if use_trend else 5
    if not 1 <= k <= 6 or keep[first_col + k - 1]:
        return 1.0
    ks = np.array([j for j in range(1, 7) if keep[first_col + j - 1]])
    if len(ks) == 0:
        return 1.0
    g = np.exp(beta[first_col + ks - 1]) - 1

    def sse(tau):
        e = np.exp(-(ks - 1) / tau)
        return float(((g - (g @ e) / (e @ e) * e) ** 2).sum())
    tau = float(min(np.linspace(0.5, 5, 46), key=sse))
    e = np.exp(-(ks - 1) / tau)
    return 1.0 + max(float(g @ e / (e @ e)), 0.0) * float(np.exp(-(k - 1) / tau))


def estimate(line_dir, handle_weeks):
    """The line's model at the plan date. handle_weeks(an0_week_means, counts, W) -> first week of handle data."""
    case, c = load(line_dir)
    n = int(case['half_hours'])
    st = case['standard']
    awt, share, short = float(st['answered_within_s']), float(st['share']), float(st['ignore_hangups_within_s'])
    c = localise(case, c)
    c = c[(c.sec >= 0) & (c.iv < n)].reset_index(drop=True)
    plan_date = pd.Timestamp(case['plan_date'])
    first = c.date.min()
    c['week'] = ((c.date - first).dt.days // 7).astype(int)
    W = int(c.week.max()) + 1

    # repeats linked through the calling number
    idc = linked_redials(c)
    c['linked'] = False
    c.loc[idc.index[idc.redial.values], 'linked'] = True
    abn = idc[idc.ab & (idc.hang < (n * 1800 - 7200))]
    p_red = []
    for k in range(4):
        sub = abn[abn.k == k] if k < 3 else abn[abn.k >= 3]
        p_red.append(float(sub.next_red.mean()) if len(sub) > 30 else (p_red[-1] if p_red else 0.5))
    rd = (idc[idc.redial].sec - idc[idc.redial].prev_hang).values
    ld = np.log(rd[rd > 0])
    if len(ld) >= 2:
        rmed, rsig = float(np.exp(ld.mean())), float(ld.std())
    else:   # no linked repeats to learn from: a few minutes, and nobody is assumed to ring again
        rmed, rsig, p_red = 240.0, 0.8, [0.0]

    # first attempts per day and half hour: each cell's attempts times its visible first-attempt share
    # (withheld numbers assumed to behave like visible ones; the weekday's pooled share when a cell has few visible)
    edges = np.arange(n + 1) * 1800.0
    days = sorted(c.date.unique())
    att = np.zeros((len(days), n)); vis = np.zeros((len(days), n)); visf = np.zeros((len(days), n))
    for j, (day, dd) in enumerate(c.groupby('date')):
        att[j] = np.histogram(dd.sec.values, edges)[0]
        v = dd[dd.caller != '']
        vis[j] = np.histogram(v.sec.values, edges)[0]
        visf[j] = np.histogram(v.loc[~v.linked, 'sec'].values, edges)[0]
    dts = pd.to_datetime(pd.Series(days))
    dw = dts.dt.weekday.values
    pooled = np.zeros_like(att)
    for d in range(5):
        sel_d = dw == d
        pooled[sel_d] = visf[sel_d].sum(0) / np.maximum(vis[sel_d].sum(0), 1)
    share_f = np.where(vis >= 20, visf / np.maximum(vis, 1), pooled)
    fresh = att * share_f

    # daily volume: weekday, week trend, the monthly bill cycle and the day after a closure
    closed = {pd.Timestamp(x) for x in case.get('closed_dates', [])}

    def after_closure(day):
        prev = day - pd.Timedelta(days=1)
        while prev.weekday() >= 5:
            prev -= pd.Timedelta(days=1)
        return prev if prev in closed else None
    post = np.array([after_closure(d) is not None for d in dts])
    tot = fresh.sum(axis=1)
    wk = ((dts - first).dt.days / 7.0).values

    def design(bd, when, weeks, wdays, postflag, with_trend):
        k = np.array([bill_offset(x, bd) for x in when])
        cols = [np.eye(5)[np.asarray(wdays)]]
        if with_trend:
            cols.append(np.asarray(weeks, float)[:, None])
        cols.append(np.column_stack([(k == j).astype(float) for j in range(1, 7)]))
        cols.append(np.asarray(postflag, float)[:, None])
        return np.column_stack(cols)

    def fit(bd, with_trend):
        X = design(bd, list(dts), wk, dw, post, with_trend)
        keep = X.any(axis=0)
        beta = np.zeros(X.shape[1])
        b, *_ = np.linalg.lstsq(X[:, keep], np.log(tot), rcond=None)
        beta[keep] = b
        res = np.log(tot) - X @ beta
        return beta, keep, res, X
    best = min(range(1, 29), key=lambda bd: float((fit(bd, True)[2] ** 2).sum()))
    beta, keep, res, X = fit(best, True)
    cov = res.var(ddof=int(keep.sum())) * np.linalg.pinv(X[:, keep].T @ X[:, keep])
    slope_col = int(keep[:5].sum())
    slope_se = float(np.sqrt(cov[slope_col, slope_col]))
    trend = (float(beta[5]), slope_se)

    # catch-up after a closure in the records: excess first attempts over a normal day, as a share of the closed
    # day's expected callers, and how early in the day they came (exponential weights by half hour)
    reg = ~post
    prof = {}
    for d in range(5):
        rows = fresh[(dw == d) & reg]
        prof[d] = rows.sum(0) / max(rows.sum(), 1)
    catch = None
    if post.any():
        j = int(np.flatnonzero(post)[0])
        day = dts.iloc[j]
        shut = after_closure(day)
        normal_total = float(np.exp(design(best, [day], [wk[j]], [dw[j]], [0], True) @ beta)[0])
        excess = fresh[j] - prof[dw[j]] * normal_total
        closed_volume = float(np.exp(design(best, [shut], [(shut - first).days / 7.0], [shut.weekday()], [0], True)
                                     @ beta)[0])

        def sse(tau):
            w = np.exp(-np.arange(n) / tau)
            amp = max(float(excess @ w / (w @ w)), 0.0)
            return float(((excess - amp * w) ** 2).sum())
        tau = float(min(np.linspace(0.5, 15, 146), key=sse))
        catch = dict(share=max(float(excess.sum()), 0.0) / closed_volume, tau=tau)

    plan_shut = after_closure(plan_date)
    plan_week = (plan_date - first).days / 7.0

    # handle times of answered calls
    an = c[~c.ab].copy()
    an['lh'] = np.log(an.handle_s.clip(lower=1.0))
    an0 = an[an.wait_s <= 0]
    wm = an0.groupby('week').lh.mean().reindex(range(W)).values
    wn = an0.groupby('week').lh.count().reindex(range(W)).fillna(0).values
    use_from = handle_weeks(wm, wn, W, float(an0.lh.std()))
    hu = an[an.week >= use_from]
    l0 = hu[hu.wait_s <= 0].lh
    lq = hu[hu.wait_s > 0].lh
    hsig = float(l0.std())
    hmean = float(np.exp(l0.mean() + hsig ** 2 / 2))
    qf = float(np.exp(lq.mean() - l0.mean()))

    # patience: Weibull, censored by answering
    w_ab = c.loc[c.ab, 'wait_s'].values
    w_an = c.loc[~c.ab & (c.wait_s > 0), 'wait_s'].values

    def nll(pp):
        k, s_ = np.exp(pp)
        return -(np.sum(np.log(k / s_) + (k - 1) * np.log(np.maximum(w_ab, 1e-3) / s_) - (w_ab / s_) ** k)
                 - np.sum((w_an / s_) ** k))
    pk, ps = np.exp(minimize(nll, [0.0, np.log(120.0)], method='Nelder-Mead').x)
    return dict(n=n, share=share, awt=awt, short=short, trend=trend, hmean=hmean, hsig=hsig, qf=qf, pk=float(pk),
                ps=float(ps), p_red=p_red, rmed=rmed, rsig=rsig, fit=fit, design=design, bill_day=best, first=first,
                profile=prof[plan_date.weekday()], plan=dict(date=plan_date, week=plan_week, dow=plan_date.weekday()),
                shut=plan_shut, catch=catch)


def staff(m, use_trend):
    """Fewest agents per half hour, in time order, meeting the contract's service level (answered in time / offered)."""
    beta, keep, res, X = m['fit'](m['bill_day'], use_trend)
    pl = m['plan']

    def volume(day, week, dow):
        x = m['design'](m['bill_day'], [day], [week], [dow], [0], use_trend)
        return float(np.exp(x @ beta)[0]) * bill_tail(m, beta, keep, day, use_trend)
    lam = m['profile'] * volume(pl['date'], pl['week'], pl['dow'])
    if m['shut'] is not None and m['catch'] is not None:
        shut = m['shut']
        w = np.exp(-np.arange(m['n']) / m['catch']['tau'])
        lam = lam + m['catch']['share'] * volume(shut, (shut - m['first']).days / 7.0, shut.weekday()) * w / w.sum()
    with tempfile.NamedTemporaryFile('w', suffix='.line', delete=False) as fh:
        fh.write('%d\n%s\n' % (m['n'], ' '.join('%.6f' % v for v in lam)))
        fh.write('%.6f %.6f %.6f %.6f %.6f %d %s\n' % (m['hmean'], m['hsig'], m['qf'], m['pk'], m['ps'], len(m['p_red']),
                                                     ' '.join('%.6f' % p for p in m['p_red'])))
        fh.write('%.6f %.6f %g %g %g\n' % (m['rmed'], m['rsig'], m['awt'], m['share'], m['short']))
        path = fh.name
    try:
        out = subprocess.run([_solver(), 'solve', path, str(DAYS), str(SEED)], capture_output=True, text=True, check=True)
    finally:
        os.unlink(path)
    return [int(v) for v in out.stdout.split()]


def change_point_weeks(wm, wn, W, s0):
    """First week after the strongest single change in weekly mean log handle time, if it is real; else 0."""
    best, bj = 0.0, 0
    for j in range(1, W):
        m1 = np.nansum(wm[:j] * wn[:j]) / wn[:j].sum()
        m2 = np.nansum(wm[j:] * wn[j:]) / wn[j:].sum()
        z = abs(m2 - m1) / (s0 * np.sqrt(1 / wn[:j].sum() + 1 / wn[j:].sum()))
        if z > best:
            best, bj = z, j
    if best > STEP_Z and abs(np.nansum(wm[bj:] * wn[bj:]) / wn[bj:].sum() - np.nansum(wm[:bj] * wn[:bj]) / wn[:bj].sum()) > 0.03:
        return bj
    return 0


def _solver():
    """The verifier's compiled simulator (tests/gensim.c)."""
    return os.environ.get('GENSIM', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'gensim'))


def plan(line_dir):
    m = estimate(line_dir, change_point_weeks)
    slope, se = m['trend']
    return staff(m, abs(slope) > TREND_Z * se)


def recent_weeks(wm, wn, W, s0):
    """Handle times from the last two weeks of the records."""
    return max(0, W - 2)


def recent(line_dir):
    m = estimate(line_dir, recent_weeks)
    return staff(m, True)


if __name__ == '__main__':
    method = {'reference': plan, 'recent': recent}[sys.argv[3]]
    agents = method(sys.argv[1])
    pd.DataFrame({'half_hour': range(len(agents)), 'agents': agents}).to_csv(sys.argv[2], index=False, lineterminator='\n')
