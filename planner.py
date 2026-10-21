"""Reference planner: plan(line_dir) -> agents per half hour for the line's plan date (see /app/README.md).

One method, no options:
1. attempts in local time (the line's IANA zone), half hours counted from opening;
2. repeats linked by calling number within a day after an abandonment: redial probability by attempt number and a
   lognormal redial delay; withheld numbers assumed to behave like visible ones, so each half hour's attempts are
   scaled by the visible first-attempt share of that weekday and half hour;
3. a volume trend (log daily first attempts on weekday and week) kept when beyond 2.5 standard errors, carrying the
   plan-weekday days to the plan date;
4. handle times of calls answered at once: the strongest single weekly change point is used when it is beyond
   4 standard errors and 3 %, keeping the weeks after it; the queued factor is the ratio to calls that waited;
5. Weibull patience by maximum likelihood (abandonments are events, answered calls that waited are censored);
6. each half hour in time order gets the fewest agents whose contract service level -- attempts answered within
   the threshold divided by attempts offered, hang-ups within the ignore window not offered, every attempt counted
   -- reaches the share on an average day. The search runs in SIM_C below, a copy of the verifier's own simulator
   (tests/gensim.c, `solve`), compiled at first use: 300 simulated days, common random numbers, each day cut after
   the half hour being decided. The shipped engine qplan is not used: its `service_level` and `staff()` divide by
   answered calls, which is not the contract's measure.

Measured margins (the verifier's band is the envelope of the true requirement and two sound methods, one of which
is this method, widened by one agent each way):
- battery draw 20261015 through the real verifier on this tree (authoring/evidence/BATTERY.md): reward 1, every half
  hour of all six lines inside, deviation from the true requirement -3..+4 agents; three other sound variants also
  inside on every line; nine rivals outside on at least one line;
- local harbor Oracle on this tree: reward 1 (authoring/evidence/local_validation.txt); as a band member the plan
  sits at least one agent inside each edge.
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
    """Compile SIM_C once (gcc) into the temporary folder and return the binary's path."""
    tag = hashlib.sha256(SIM_C.encode()).hexdigest()[:12]
    exe = os.path.join(tempfile.gettempdir(), f'contract-sim-{tag}')
    if not os.path.exists(exe):
        src = exe + '.c'
        with open(src, 'w') as fh:
            fh.write(SIM_C)
        subprocess.run(['gcc', '-O2', '-o', exe + '.tmp', src, '-lm'], check=True, capture_output=True)
        os.replace(exe + '.tmp', exe)
    return exe


def plan(line_dir):
    m = estimate(line_dir, change_point_weeks)
    slope, se = m['trend']
    return staff(m, abs(slope) > TREND_Z * se)


# The verifier's simulator (tests/gensim.c), unchanged; its `solve` is the contract staffing search.
SIM_C = r'''/* Verifier-side contact-centre simulator (generator and truth). Not shipped to the agent.
 * FCFS multi-server queue, Weibull patience, redials after abandonment, lognormal handle times
 * (factor q for calls that queued), Poisson arrivals per half hour, staffing per half hour.
 *
 *   gensim log   <params> <ndays> <seed>   stdin per day: s[0..n-1] vol_scale aht_scale -> attempts
 *   gensim solve <params> <reps> <seed>    -> fewest agents per half hour meeting the HOUSE service level
 *   gensim eval  <params> <reps> <seed> s[0..n-1] -> per-half-hour expected counts
 *
 * params file:  n  lam[n]  aht sig q  pshape pscale  nred p[nred]  rmed rsig  awt target short_ab
 * House service level of a half hour = answered within awt / offered, where offered excludes callers
 * who hung up within short_ab seconds; every attempt counts; ratio of expectations.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <stdint.h>

#define MAXI 40
#define TI 1800.0
#define MAXEV 400000
#define MAXAG 600

static int NI, nred, logmode;
static double lam[MAXI], aht, sig, qf, pshape, pscale, pr[16], rmed, rsig, awt, target, shab;
static double aht_scale = 1.0;

static uint64_t s[4];
static inline uint64_t rotl(const uint64_t x, int k) { return (x << k) | (x >> (64 - k)); }
static uint64_t nxt(void) {
    const uint64_t r = rotl(s[1] * 5, 7) * 9, t = s[1] << 17;
    s[2] ^= s[0]; s[3] ^= s[1]; s[1] ^= s[2]; s[0] ^= s[3]; s[2] ^= t; s[3] = rotl(s[3], 45);
    return r;
}
static double U(void) { return ((nxt() >> 11) + 0.5) * (1.0 / 9007199254740992.0); }
static void seed_rng(uint64_t x) {
    for (int i = 0; i < 4; i++) {
        x += 0x9E3779B97F4A7C15ULL; uint64_t z = x;
        z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL; z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
        s[i] = z ^ (z >> 31);
    }
}
static double N01(void) { return sqrt(-2 * log(U())) * cos(6.283185307179586 * U()); }

typedef struct { double t; int a, c; } Ev;
static Ev ev[MAXEV]; static int nev;
static void ev_push(double t, int a, int c) {
    int i = nev++;
    while (i > 0) { int p = (i - 1) / 2; if (ev[p].t <= t) break; ev[i] = ev[p]; i = p; }
    ev[i].t = t; ev[i].a = a; ev[i].c = c;
}
static Ev ev_pop(void) {
    Ev top = ev[0], last = ev[--nev]; int i = 0;
    for (;;) {
        int c = 2 * i + 1;
        if (c >= nev) break;
        if (c + 1 < nev && ev[c + 1].t < ev[c].t) c++;
        if (ev[c].t >= last.t) break;
        ev[i] = ev[c]; i = c;
    }
    ev[i] = last; return top;
}
static double ag[MAXAG]; static int nag;
static void ag_push(double t) { int i = nag++; while (i > 0) { int p = (i - 1) / 2; if (ag[p] <= t) break; ag[i] = ag[p]; i = p; } ag[i] = t; }
static void ag_sift0(void) {
    double lt = ag[0]; int i = 0;
    for (;;) {
        int c = 2 * i + 1;
        if (c >= nag) break;
        if (c + 1 < nag && ag[c + 1] < ag[c]) c++;
        if (ag[c] >= lt) break;
        ag[i] = ag[c]; i = c;
    }
    ag[i] = lt;
}
static void ag_pop(void) { ag[0] = ag[--nag]; ag_sift0(); }

static double T_off[MAXI], T_ok[MAXI], T_ab[MAXI], T_fr[MAXI], T_rd[MAXI], T_ans[MAXI], T_ht[MAXI];

static void day(const int *staff, int upto) {
    double tend = (upto + 1) * TI;
    int nchain = 0;
    nev = 0; nag = 0;
    for (int i = 0; i <= upto; i++) {
        if (lam[i] <= 0) continue;
        double r = lam[i] / TI, t = i * TI;
        for (;;) { t += -log(U()) / r; if (t >= (i + 1) * TI) break; ev_push(t, 0, nchain++); }
    }
    int cur = -1;
    double mu = log(aht * aht_scale) - sig * sig / 2;
    while (nev) {
        Ev e = ev_pop(); double t = e.t; int k = e.a;
        if (t >= tend) continue;
        int i = (int)(t / TI);
        while (cur < i) {
            cur++;
            while (nag < staff[cur]) ag_push(cur * TI);
            while (nag > staff[cur]) ag_pop();
        }
        if (k == 0) T_fr[i]++; else T_rd[i]++;
        double f = (nag && ag[0] > t) ? ag[0] : t;
        if (!nag) f = 1e18;
        double w = f - t;
        double pat = pscale * pow(-log(U()), 1.0 / pshape);
        if (w > pat) {
            if (pat >= shab) { T_off[i]++; T_ab[i]++; }
            if (logmode) printf("%.3f %d %d A %.3f\n", t, e.c, k, pat);
            double p = pr[k < nred ? k : nred - 1];
            if (U() < p) ev_push(t + pat + exp(log(rmed) + rsig * N01()), k + 1, e.c);
        } else {
            T_off[i]++; T_ans[i]++;
            if (w <= awt) T_ok[i]++;
            double h = exp(mu + sig * N01()) * (w > 0 ? qf : 1.0);
            T_ht[i] += h;
            if (logmode) printf("%.3f %d %d S %.3f %.3f\n", t, e.c, k, w, h);
            ag[0] = f + h; ag_sift0();
        }
    }
}

static void clear(void) {
    memset(T_off, 0, sizeof T_off); memset(T_ok, 0, sizeof T_ok); memset(T_ab, 0, sizeof T_ab);
    memset(T_fr, 0, sizeof T_fr); memset(T_rd, 0, sizeof T_rd); memset(T_ans, 0, sizeof T_ans); memset(T_ht, 0, sizeof T_ht);
}

static int meets(int *staff, int i, int c, int reps, uint64_t seed) {
    staff[i] = c;
    clear(); seed_rng(seed + 1000003ULL * (uint64_t)i);
    for (int r = 0; r < reps; r++) day(staff, i);
    return T_off[i] <= 0 || T_ok[i] / T_off[i] >= target;
}

static int readp(const char *fn) {
    FILE *fp = fopen(fn, "r");
    if (!fp) return 0;
    if (fscanf(fp, "%d", &NI) != 1 || NI < 1 || NI > MAXI) return 0;
    for (int i = 0; i < NI; i++) if (fscanf(fp, "%lf", &lam[i]) != 1) return 0;
    if (fscanf(fp, "%lf %lf %lf %lf %lf %d", &aht, &sig, &qf, &pshape, &pscale, &nred) != 6 || nred < 1 || nred > 16) return 0;
    for (int k = 0; k < nred; k++) if (fscanf(fp, "%lf", &pr[k]) != 1) return 0;
    if (fscanf(fp, "%lf %lf %lf %lf %lf", &rmed, &rsig, &awt, &target, &shab) != 5) return 0;
    fclose(fp);
    return 1;
}

int main(int argc, char **argv) {
    if (argc < 5 || !readp(argv[2])) { fprintf(stderr, "usage: gensim log|solve|eval params reps seed [staff]\n"); return 2; }
    int reps = atoi(argv[3]); uint64_t seed = strtoull(argv[4], 0, 10);
    int staff[MAXI];
    if (!strcmp(argv[1], "log")) {
        logmode = 1; seed_rng(seed);
        double keep[MAXI];
        for (int d = 0; d < reps; d++) {
            for (int i = 0; i < NI; i++) if (scanf("%d", &staff[i]) != 1) return 3;
            double vs; if (scanf("%lf %lf", &vs, &aht_scale) != 2) return 3;
            for (int i = 0; i < NI; i++) { keep[i] = lam[i]; lam[i] *= vs; }
            printf("DAY %d\n", d); day(staff, NI - 1);
            for (int i = 0; i < NI; i++) lam[i] = keep[i];
        }
        printf("END\n");
        return 0;
    }
    if (!strcmp(argv[1], "eval")) {
        if (argc < 5 + NI) return 2;
        for (int i = 0; i < NI; i++) staff[i] = atoi(argv[5 + i]);
        clear(); seed_rng(seed);
        for (int r = 0; r < reps; r++) day(staff, NI - 1);
        for (int i = 0; i < NI; i++)
            printf("%d %.4f %.4f %.4f %.4f %.4f %.4f %.3f\n", i, T_off[i] / reps, T_ok[i] / reps, T_ab[i] / reps,
                   T_fr[i] / reps, T_rd[i] / reps, T_ans[i] / reps, T_ht[i] / (T_ans[i] > 0 ? T_ans[i] : 1));
        return 0;
    }
    if (!strcmp(argv[1], "solve")) {
        for (int i = 0; i < NI; i++) {
            int c = i ? staff[i - 1] : 1;
            if (c < 1) c = 1;
            if (meets(staff, i, c, reps, seed)) { while (c > 1 && meets(staff, i, c - 1, reps, seed)) c--; }
            else { do c++; while (c < MAXAG - 1 && !meets(staff, i, c, reps, seed)); }
            staff[i] = c;
        }
        for (int i = 0; i < NI; i++) printf("%d%c", staff[i], i == NI - 1 ? '\n' : ' ');
        return 0;
    }
    return 2;
}
'''


if __name__ == '__main__':
    print(plan(sys.argv[1]))
