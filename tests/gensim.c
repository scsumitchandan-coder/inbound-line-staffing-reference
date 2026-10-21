/* Verifier-side contact-centre simulator (generator and truth). Not shipped to the agent.
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
