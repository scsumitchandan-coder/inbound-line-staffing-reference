# Inbound lines and their records

We run inbound customer lines for several clients. Every line is one queue: one skill, every agent takes every
call, and calls are answered strictly in the order they joined the queue. There is no callback option and no
message that sends callers away. A line is open on weekdays only, for the hours its `case.json` gives.

`/app/practice/` holds one line exactly as a line reaches the planning team. The lines your planner will be run
on come in the same form and from the same kind of client, but differ in size, opening hours, time zone, service
contract, how their callers and agents behave, and what happened during their records.

## A line's folder

`case.json`

| key | meaning |
|---|---|
| `time_zone` | the line's local time zone (IANA name). Opening hours, half hours and dates are local |
| `opens` | local opening time; the line is open for `half_hours` consecutive half hours |
| `plan_date` | the weekday to plan, in the week after the records end |
| `closed_dates` | days the line was closed, or will be closed, in the records' weeks and the plan week |
| `standard` | the client contract's service standard (below) |

`calls.csv`: one row per attempt that reached the queue during the eight weeks before the plan week.

| column | meaning |
|---|---|
| `call_id` | row id |
| `offered_utc` | when the attempt joined the queue, UTC |
| `caller` | hashed calling number; empty when the caller withheld it |
| `outcome` | `answered` or `abandoned` |
| `wait_s` | answered: seconds in the queue before an agent picked up. Abandoned: seconds before the caller hung up |
| `handle_s` | answered only: talk plus wrap-up, seconds |

`agents.csv`: agents logged in to the queue in each half hour of each day of the records (`interval_start` is
local time). That many agents are available for the whole half hour; when the number drops at a boundary, those
leaving finish the call they are on.

## What is known about the lines

- Callers who hang up in the queue often ring again a little later the same day, sometimes several times. A new
  attempt joins the back of the queue like any other call. Nobody rings back after closing time.
- How long a caller is prepared to wait does not depend on the time of day or on how many agents are on.
- When a call has had to wait before an agent picked it up, the team leaders have the agent cut the wrap-up short,
  so calls that waited are handled faster than calls answered at once. Otherwise handle times do not depend on
  the time of day.
- Callers' first attempts arrive at a steady rate within each half hour; that rate follows the line's weekday
  and time-of-day pattern.
- Each client bills its customers on the same day every month. Calls about a bill come in over the days after it,
  most of them on the first days.
- On a closed day nobody can call. Many of the customers who wanted to call that day call on the next open day
  instead, and earlier in that day than callers usually do.
- Lines change. A client may launch a product or a tariff, or move the agents to a new system, and the weeks in
  the records are not always alike. The plan is for the line as it will run on `plan_date`.
- During the records every line was run on the roster drawn up with the old planning engine, which was short of
  agents at busy times.

## The service standard

Each line's contract fixes, in `standard`:
- `answered_within_s`: the threshold, in seconds from joining the queue;
- `share`: the share that must be met;
- `ignore_hangups_within_s`: attempts abandoned this quickly are not counted.

For every half hour, the attempts **offered** in it are those that joined the queue in that half hour, except
attempts abandoned within `ignore_hangups_within_s` seconds. Every attempt counts, first or repeat. The service
level of the half hour is the number of offered attempts answered within `answered_within_s`, divided by the
number offered. The contract judges it on an average day: the expected number answered in time over the expected
number offered, for a typical `plan_date` weekday.

## The planning engine

`/app/engine/` holds `qplan`, the queue engine the workforce team has used until now, with its notes in
`ENGINE.md`. Use it or not as you see fit; the grader has it exactly as shipped. The contract, not the engine,
defines how the service level is measured.
