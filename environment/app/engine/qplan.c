/* qplan - half-hourly queue simulation for an inbound line.
 *
 *   qplan simulate <line-file> <days> <seed> a[0] .. a[n-1]
 *   qplan staff    <line-file> <days> <seed> <target>
 *
 * line-file:  n  arrivals[n]  handle_mean handle_sigma queued_factor
 *             patience_shape patience_scale  nred redial[nred]  redial_median redial_sigma
 *             answer_within ignore_hangups_within
 * patience_scale <= 0 means callers never hang up.
 * See ENGINE.md for the model and the output columns.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <stdint.h>

#define MAXI 48
#define TI 1800.0
#define MAXEV 400000
#define MAXAG 600

static int NI, nred;
static double lam[MAXI], hmean, hsig, qf, pshape, pscale, pr[16], rmed, rsig, awt, shab;

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

typedef struct { double t; int a; } Ev;
static Ev ev[MAXEV]; static int nev;
static void ev_push(double t, int a) {
    if (nev >= MAXEV) return;
    int i = nev++;
    while (i > 0) { int p = (i - 1) / 2; if (ev[p].t <= t) break; ev[i] = ev[p]; i = p; }
    ev[i].t = t; ev[i].a = a;
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

/* per half hour: offered (excl. hang-ups within the ignore window), answered, answered in time,
 * abandoned (offered and not answered), first attempts, repeat attempts, handle time sum */
static double O[MAXI], A[MAXI], AT[MAXI], AB[MAXI], F[MAXI], R[MAXI], H[MAXI];

static void day(const int *staff, int upto) {
    double tend = (upto + 1) * TI;
    nev = 0; nag = 0;
    for (int i = 0; i <= upto; i++) {
        if (lam[i] <= 0) continue;
        double r = lam[i] / TI, t = i * TI;
        for (;;) { t += -log(U()) / r; if (t >= (i + 1) * TI) break; ev_push(t, 0); }
    }
    int cur = -1;
    double mu = log(hmean) - hsig * hsig / 2;
    while (nev) {
        Ev e = ev_pop(); double t = e.t; int k = e.a;
        if (t >= tend) continue;
        int i = (int)(t / TI);
        while (cur < i) {
            cur++;
            while (nag < staff[cur]) ag_push(cur * TI);
            while (nag > staff[cur]) ag_pop();
        }
        if (k == 0) F[i]++; else R[i]++;
        double f = nag ? (ag[0] > t ? ag[0] : t) : 1e18;
        double w = f - t;
        double pat = pscale > 0 ? pscale * pow(-log(U()), 1.0 / pshape) : 1e18;
        if (w > pat) {
            if (pat >= shab) { O[i]++; AB[i]++; }
            double p = pr[k < nred ? k : nred - 1];
            if (U() < p) ev_push(t + pat + exp(log(rmed) + rsig * N01()), k + 1);
        } else {
            O[i]++; A[i]++;
            if (w <= awt) AT[i]++;
            double h = exp(mu + hsig * N01()) * (w > 0 ? qf : 1.0);
            H[i] += h;
            ag[0] = f + h; ag_sift0();
        }
    }
}

static void clear(void) {
    memset(O, 0, sizeof O); memset(A, 0, sizeof A); memset(AT, 0, sizeof AT); memset(AB, 0, sizeof AB);
    memset(F, 0, sizeof F); memset(R, 0, sizeof R); memset(H, 0, sizeof H);
}

/* service level of a half hour: calls answered within the threshold, as a share of calls answered */
static double service_level(int i) { return A[i] > 0 ? AT[i] / A[i] : 1.0; }

static int meets(int *staff, int i, int c, int days, uint64_t seed, double target) {
    staff[i] = c;
    clear(); seed_rng(seed + 1000003ULL * (uint64_t)i);
    for (int r = 0; r < days; r++) day(staff, i);
    return service_level(i) >= target;
}

static int readline_file(const char *fn) {
    FILE *fp = fopen(fn, "r");
    if (!fp) return 0;
    int ok = fscanf(fp, "%d", &NI) == 1 && NI >= 1 && NI <= MAXI;
    for (int i = 0; ok && i < NI; i++) ok = fscanf(fp, "%lf", &lam[i]) == 1;
    ok = ok && fscanf(fp, "%lf %lf %lf %lf %lf %d", &hmean, &hsig, &qf, &pshape, &pscale, &nred) == 6 && nred >= 1 && nred <= 16;
    for (int k = 0; ok && k < nred; k++) ok = fscanf(fp, "%lf", &pr[k]) == 1;
    ok = ok && fscanf(fp, "%lf %lf %lf %lf", &rmed, &rsig, &awt, &shab) == 4;
    fclose(fp);
    if (ok && pshape <= 0) pshape = 1;
    return ok;
}

int main(int argc, char **argv) {
    if (argc < 5 || !readline_file(argv[2])) {
        fprintf(stderr, "usage: qplan simulate <line-file> <days> <seed> a0..a(n-1)\n       qplan staff <line-file> <days> <seed> <target>\n");
        return 2;
    }
    int days = atoi(argv[3]); uint64_t seed = strtoull(argv[4], 0, 10);
    int staff[MAXI];
    if (days < 1) days = 1;
    if (!strcmp(argv[1], "simulate")) {
        if (argc < 5 + NI) { fprintf(stderr, "need %d agent numbers\n", NI); return 2; }
        for (int i = 0; i < NI; i++) staff[i] = atoi(argv[5 + i]);
        clear(); seed_rng(seed);
        for (int r = 0; r < days; r++) day(staff, NI - 1);
        printf("half_hour,agents,offered,answered,answered_in_time,abandoned,first_attempts,repeat_attempts,mean_handle_s,service_level\n");
        for (int i = 0; i < NI; i++)
            printf("%d,%d,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.2f,%.5f\n", i, staff[i], O[i] / days, A[i] / days, AT[i] / days,
                   AB[i] / days, F[i] / days, R[i] / days, A[i] > 0 ? H[i] / A[i] : 0.0, service_level(i));
        return 0;
    }
    if (!strcmp(argv[1], "staff")) {
        double target = argc > 5 ? atof(argv[5]) : 0.8;
        for (int i = 0; i < NI; i++) {
            int c = i ? staff[i - 1] : 1;
            if (c < 1) c = 1;
            if (meets(staff, i, c, days, seed, target)) { while (c > 1 && meets(staff, i, c - 1, days, seed, target)) c--; }
            else { do c++; while (c < MAXAG - 1 && !meets(staff, i, c, days, seed, target)); }
            staff[i] = c;
        }
        for (int i = 0; i < NI; i++) printf("%d%c", staff[i], i == NI - 1 ? '\n' : ' ');
        return 0;
    }
    return 2;
}
