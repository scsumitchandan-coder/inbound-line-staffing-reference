# inbound-line-staffing

The agent writes a staffing planner for inbound customer lines. `plan(line_dir)` reads one line's eight weeks of
call records, its logged-in agents and its client contract, and returns, for each half hour of the plan date, the
fewest agents that meet the contract's service level, working forward through the day. The planner is graded on
six lines generated for each submission from a hash of the submitted file.

This is everyday contact-centre workforce planning: estimate how a line's callers and agents behave from the switch
records, then size each half hour against the service standard by simulation, because abandonment, redials and
carry-over between half hours rule out the textbook formula. What makes it hard is that the records were produced
by the old, understaffed roster, and several of the things they show will not hold under the new plan.

## Difficulty

Each graded line is simulated from a stated model (one FCFS queue, Weibull patience, redials after abandonment with
lognormal delay, lognormal handle times with a factor for calls that waited, Poisson first attempts at a steady
rate within each half hour). The parameters are hidden and differ per line. The judgement points, each a fact in
`/app/README.md` or `/app/engine/ENGINE.md`, never a keyword to match:

- **Redials depend on the plan.** Under the old roster 5-8 % of offered attempts were abandoned and 3-6 % of all
  attempts are callers ringing again. Under the new plan fewer callers hang up, but some still do and ring again
  later, into later half hours. Stripping the repeats and assuming nobody rings again understates the load in every
  graded line (survey: 1-6 half hours outside the range per line); counting every recorded attempt as new demand
  is a smaller error in the other direction, about the size of the band (inert: not claimed as a lever). A replay
  of the history cannot tell these readings apart, because the history ran under the old roster.
- **Handle times depend on the queue.** Agents cut the wrap-up short when a call has waited: calls that waited are
  handled in 0.72-0.86 of the time (19-31 % of answered calls waited under the old roster). How many wait depends on
  the plan, so the handle-time mix in the records is the old roster's, not the new one's. One handle-time
  distribution fitted to all answered calls misplaces 2-6 half hours in two of the four lines of the first survey
  draw.
- **The engine's service level is not the contract's.** The shipped engine `qplan` reports and staffs to
  `answered_in_time / answered`; the contract measures `answered_in_time / offered`. The two agree on every check in
  `ENGINE.md`, which are lines where nobody hangs up. Trusting `qplan.staff()` understaffs every line.
- **Lines change during the records** (stated only as "lines change"). One graded line's first-attempt volume rises
  by 2.2-3.5 % a week, one falls 1.8-3 % a week with a handle-time step, one has a 12-22 % handle-time step a few
  weeks before the end. Averages over the eight weeks plan for a line that no longer exists.
- **The bill cycle.** Every line's client bills on a fixed day of the month and calls follow for a few days (stated;
  the day and the size are in the data: two cycles in the eight weeks). On one graded line the plan date falls one or
  two days after a bill; elsewhere the bill days sit inside the averages. A weekday-and-trend model of the volume
  misses both.
- **Catch-up after a closure.** `closed_dates` lists days the line was or will be closed; many customers who could
  not call call on the next open day, early in it (stated). The records hold one such day. On one graded line the
  plan date follows a closure, so the plan needs the share of a closed day's callers who come back and how early
  they come, both read off that one day. Assuming everyone returns, spread like an ordinary day, is the ready
  shortcut.
- **Clocks.** Records are in UTC, opening hours in local time, and one graded line's records always span the
  autumn clock change (EU 25 October or US 1 November 2026). A fixed offset shifts every busy period by an hour
  for part of the records.
- **Withheld numbers.** 3-12 % of attempts carry no caller number, so their repeats cannot be linked. Treated
  correctly or as first attempts, this changes little; it is realism, not a lever.

The practice line in `/app/practice/` is steady (no trend, no step, no clock change inside its records), so a
planner tuned to it witnesses none of the change points.

Data: synthetic, from `environment/_build/centre.py` and its simulator `gensim.c` (byte-identical copies in `tests/`).
The model is the standard contact-centre model with abandonment and retrials (Erlang-A with retrials; see Gans,
Koole & Mandelbaum 2003, Manufacturing & Service Operations Management 5(2)); the time zones and clock-change dates
are real.

## Reference solution

`solution/planner.py` (one method, no options; `tests/sound.py` runs the same method as `reference`, beside one
sound variant `recent`):
1. Convert attempts to local time with the line's IANA zone; index half hours from opening.
2. Link repeats: an attempt by the same number on the same day after an abandonment by it. Estimate the redial
   probability by attempt number and the lognormal delay from the linked chains.
3. First attempts per half hour: attempts times the share of first attempts among callers with a visible number.
4. Volume trend: regress log daily first attempts on weekday dummies and weeks; keep the slope if it is beyond 2.5
   standard errors and carry the plan-weekday days to the plan date.
5. Handle times: weekly means of log handle time of calls answered at once; take the most significant single change
   point (z > 4 and > 3 %) and use only the weeks after it. Mean and log-sd from calls answered at once; the queued
   factor from the ratio to calls that waited.
6. Patience: Weibull maximum likelihood, abandonments as events, answered calls that waited as censored.
7. Staff each half hour forward, stopping at the fewest agents whose contract service level (answered in time over
   offered) reaches the share. The search is the verifier's own simulator (`gensim.c` `solve`, 300 simulated days,
   common random numbers), embedded in the planner and compiled at first use; the shipped engine is not used, because
   its `service_level` and `staff()` divide by answered calls.

## Verification

`tests/test_outputs.py` (run by `tests/test.sh`):
- reads `/app/planner.py` without following links (regular file, one link, size-capped, inode-checked) and derives
  six line seeds from SHA-256 of a salt and its bytes, so stored answers move the lines;
- builds one line per role (rising, step, clock, falling-step, bill, holiday) with `centre.py`, as root, into a
  world-readable
  folder holding only `calls.csv`, `agents.csv` and `case.json`;
- computes, into a root-only folder, the line's true requirement (`gensim solve`, 300 days, on the generating model
  at the plan date) and the plans of two sound methods on the same records (`sound.py`: the reference; and
  handle times from the last two weeks with the trend always fitted);
- runs the planner on each line as the unprivileged user `verifier` (20 minutes per line, one line at a time), reading its
  plan from a pipe, so root never opens a path the planner controls; `/tests` is mode 0700 and the user's processes
  are killed after each run;
- accepts a half hour when the planner's number lies in `[min - 1, max + 1]` over the true requirement and the two
  sound plans. Every half hour of every line must be accepted.

The band is the envelope of the truth and sound methods, not a tolerance around the truth, so a sound method tuned
differently is not failed by the margin alone. Evidence: `authoring/evidence/` (`BATTERY.md`: the real verifier on the
reference, three sound variants, nine rivals, one unclaimed rival and six malformed submissions; `survey_draws.txt`: two further draws, in
which every sound method stays inside on every line and every rival falls outside on at least one line).
