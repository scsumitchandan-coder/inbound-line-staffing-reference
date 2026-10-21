Category: Science
Sub-Category: Operations Research

**Task: write a staffing planner for inbound customer lines. Given one line's eight weeks of call records, the agents logged in during those weeks and the client contract's service standard, the planner returns the fewest agents for every half hour of a plan date, working forward through the day. It is graded on lines generated fresh for each submission.**

## Task statement and deliverable

An outsourcing contact-centre group is replacing rosters that its workforce team drew up with an old planning engine. The planners want a tool they can run on any line's folder, not a one-off answer.

The agent works in `/app`, which holds:
- **`README.md`.** How the lines work and what a line's folder contains. Each line is one first-come-first-served queue with no callback. The README states that:
  - callers who hang up often ring again later the same day;
  - some callers withhold their number;
  - patience does not depend on time of day or staffing;
  - calls that waited get a shortened wrap-up;
  - first attempts arrive at a steady rate within each half hour;
  - lines change during the records ("a client may launch a product or a tariff, or move agents to a new system").

  It also defines the contract's service level for a half hour: offered attempts answered within the threshold, divided by offered attempts. Hang-ups within a few seconds don't count, every attempt counts, and the ratio is taken on an average day.
- **`engine/`.** The workforce team's queue engine `qplan`: C source and binary, a Python wrapper, `ENGINE.md`, and the Erlang C checks it was validated on. The README adds one sentence: the contract, not the engine, defines the service level.
- **`practice/`.** One line to try the planner on: `calls.csv` (UTC timestamps, hashed caller number, outcome, wait, handle time), `agents.csv` (logged-in agents per half hour) and `case.json` (time zone, opening time, number of half hours, plan date, service standard). No answer is supplied.

The deliverable is `/app/planner.py` with `plan(line_dir)`. It returns one whole number per half hour, from opening time.

## Why this task is genuinely difficult

**Who does this work.** Workforce-management analysts and the operations-research developers of contact-centre planning tools. They estimate arrival, patience, redial and handle-time behaviour from switch records, then size each half hour by simulation. Abandonment, redials and queues carried from one half hour into the next rule out Erlang C. Getting it wrong costs either a breached client contract or a payroll of idle agents.

**Data.** Synthetic. Each line is simulated from the standard model of a call centre with abandonment and retrials (Gans, Koole & Mandelbaum 2003):
- Poisson first attempts by weekday and half hour;
- Weibull patience;
- lognormal redial delays and handle times, with a factor for calls that waited.

Parameters are drawn per line from realistic ranges: about 25-80 agents at the peak, thresholds of 20 or 30 seconds, shares of 80-90 %. Time zones and clock-change dates are real (EU 25 October, US 1 November 2026). The records were produced under an old roster at 80-95 % of a rough requirement, so 5-8 % of offered calls were abandoned. Nothing can be looked up: every graded line is generated for the submission.

**Where the obvious method goes wrong.** Each point below is a fact in the files, not a keyword. In the prototype survey each moves at least one graded line by more than the accepted range.
1. **The records were shaped by the old roster.**
   - Repeat attempts exist because callers hung up. Under an adequate plan fewer hang up, but some still ring again into later half hours.
   - Calls that waited were handled faster. The share that waits depends on the plan.

   A model that strips the repeats and assumes nobody rings again replays the history perfectly, and so does one that uses a single handle-time distribution. Both are wrong for the new plan.
2. **The engine measures a different service level.**
   - `qplan` reports and staffs to answered-in-time over *answered* calls. That is a real vendor convention, but not this contract's, which divides by *offered* calls.
   - It matches Erlang C on every documented check, all of them lines where nobody hangs up.
   - Trusting `qplan.staff()` understaffs every line: 2-21 half hours outside the range per line in the prototype.
3. **Lines change during the records, and the instruction says only that they do.**
   - In each graded set, one line's volume rises 2-3.5 % a week.
   - One line falls 2-3 % a week and has a handle-time step.
   - One line has a 12-22 % handle-time step a few weeks before the end.

   Eight-week averages plan for a line that no longer exists: up to 6 agents off in the survey draw.
4. **The bill cycle.** Each client bills on a fixed day of the month and calls follow for a few days. The README says
   so; the day and the size are in the data, two cycles in eight weeks. On one graded line the plan date falls 1-2
   days after a bill (+15-45 % volume); elsewhere the bill days sit inside every average. A weekday-and-trend model
   misses both.
5. **Catch-up after a closure.** `closed_dates` lists the days the line was or will be closed, and many customers
   who could not call do so on the next open day, early in it. The records hold one such day. On one graded line
   the plan date follows a closure, so the plan needs the share of a closed day's callers who return (55-80 %) and
   how early they come, both read off that one day. Assuming everyone returns, spread like an ordinary day, is the
   ready shortcut.
6. **Clocks.** Records are in UTC and opening hours are local. One graded line's records always span a clock change, and a fixed offset moves the busy periods by an hour for part of the records (up to 14 agents off).

The practice line is steady, so a planner tuned on it meets none of these change points. The planner has to look for them in data it never sees.

## Intended solution approach

1. Convert attempts to local time with the line's zone.
2. Link repeats by caller number and day. Estimate redial probability by attempt number and the delay distribution.
3. Scale first attempts per half hour by the visible first-attempt share, to cover withheld numbers.
4. Test for a volume trend: log daily first attempts against weekday and week. If it is significant, carry the plan-weekday counts to the plan date.
5. Test weekly handle times of calls answered at once for a change point, and use only the weeks after it. Estimate the waited-call factor and the Weibull patience; answered calls censor patience.
6. Simulate the plan date with all of these, including the residual redials. Stop each half hour, in time order, at the fewest agents whose service level, measured the contract's way, reaches the share.

Before step 6 the daily volume model adds the bill cycle (bill day searched over the month, a multiplier per day
after the bill) and the post-closure catch-up (returning share and an exponential morning profile from the one past
closure). The reference does exactly this, staffing with the verifier's own contract-measure simulator, embedded
and compiled at first use. It never uses the shipped engine's `service_level` or `staff()`. Each line takes about
1-3 minutes.

Expert time: about 12 hours.
- 4 h exploring the records and the line behaviour;
- 4 h for the estimators, including the change-point and trend tests;
- 2 h for the staffing search and the engine;
- 2 h validating.

## How the solution will be verified

The verifier hashes `/app/planner.py` (read without following links) to derive six line seeds, one per role: rising, step, clock change, falling with a step, bill window, after a closure. Changing the submission changes the lines. For each line it computes, out of the planner's reach:
- the **true requirement**: the same forward staffing search on the generating model at the plan date;
- the plans of **two sound methods** run on the same records: the reference, and a variant with the last two weeks' handle times and the trend always fitted.

The planner runs on each line as an unprivileged user, with 20 minutes and 2 cores. Its plan is read through a pipe.

**Acceptance.** A half hour passes when the planner's number lies between the lowest and highest of the truth and the two sound plans, widened by one agent each way. Every half hour of every line must pass, and the reward is binary.
- **Why a range and not a point.** Sound estimators differ by a few agents, because eight weeks of records are a finite sample (about 1-3 % on half-hour volumes) and because simulation noise moves a requirement by about one agent.
- **What the range rejects.** In the battery through the real verifier, every sound variant stayed inside on every line. Each wrong reading above fell outside on at least one line of the draw: engine service level, stripped repeats, single handle-time distribution, no trend, fixed UTC offset, no bill cycle, no closure effect, and everyone returning evenly. Counting every attempt as new demand is about the size of the band, so it is reported as inert rather than claimed.

The battery in `authoring/evidence` runs the real verifier on the reference, sound variants, these rivals and malformed submissions (missing, crashing, wrong length, constant, reading the grader's files, hanging).

## Category and sub-category justification

**Science / Operations Research.** This is queueing-based capacity planning: estimating a stochastic service system's parameters from operational records shaped by the policy in force, then choosing the least capacity per period that meets a service constraint under a new policy. Both halves are standard operations research (call-centre staffing with abandonment and retrials). The grade rests on a computable requirement of a stated model, not on judgement calls about the business.
