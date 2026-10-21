# qplan

`qplan` is the planning engine the workforce team has used since the old roster was drawn up. It simulates
one opening day of a single queue, half hour by half hour, many times over, and reports averages. `qplan.py`
is the Python front end; `qplan` is the compiled core (source in `qplan.c`, built with
`gcc -O2 -o qplan qplan.c -lm`).

## The model

- Callers making a first attempt arrive at random (a Poisson stream) at a steady rate within each half hour.
  `arrivals[i]` is the expected number of first attempts in half hour `i`.
- Calls are answered strictly in arrival order by the first free agent.
- `agents[i]` agents are logged in for the whole of half hour `i`. When the number drops at a boundary, the
  agents who leave finish the call they are on.
- A caller waits at most a Weibull-distributed time (`patience_shape`, `patience_scale`) and then hangs up.
  With `patience_scale=None` nobody hangs up.
- After hanging up, a caller rings again with probability `redial[k]` (`k` = how many times they have hung up
  before, the last entry repeating), after a lognormal delay with median `redial_median` and log-sd
  `redial_sigma`. The new attempt joins the back of the queue.
- Handle time is lognormal with mean `handle_mean` and log-sd `handle_sigma`; a call that waited at all
  before an agent picked it up is handled in `queued_factor` times that.
- Calls that are still waiting at the end of the day are not answered.

## Output of `simulate`

One row per half hour, averaged over the simulated days. A call is counted in the half hour in which it
joined the queue.

| column | meaning |
|---|---|
| `offered` | attempts that joined the queue, except those that hung up within `ignore_hangups_within` seconds |
| `answered` | attempts answered |
| `answered_in_time` | attempts answered within `answer_within` seconds of joining the queue |
| `abandoned` | offered attempts that hung up |
| `first_attempts`, `repeat_attempts` | all attempts, split by whether the caller had hung up earlier that day |
| `mean_handle_s` | mean handle time of the answered attempts |
| `service_level` | `answered_in_time / answered`, the share of answered calls picked up within `answer_within` |

`staff(line, target)` works through the day from the first half hour and returns, for each half hour, the
fewest agents whose `service_level` reaches `target`, given the numbers already chosen for the half hours
before it.

## Checks

Before the engine was adopted it was checked against the Erlang C formula on lines where nobody hangs up
(`patience_scale=None`, `redial=[0]`, `queued_factor=1`), with handle times whose spread matches the exponential
(`handle_sigma=0.8326`). Each case is a run of identical half hours, simulated for 1500 days, read in the
steady second half of the day. `checks.csv` has every case:

| case | arrivals per half hour | handle_mean | agents | threshold | qplan `service_level` | Erlang C |
|---|---|---|---|---|---|---|
| A | 120 | 300 | 23 | 20 | 0.6605 | 0.6596 |
| B | 120 | 300 | 22 | 20 | 0.5043 | 0.5030 |
| C | 300 | 240 | 45 | 20 | 0.7811 | 0.7754 |
| D | 300 | 240 | 43 | 30 | 0.6371 | 0.6282 |
| E | 60 | 420 | 17 | 20 | 0.6940 | 0.6981 |
| F | 500 | 300 | 89 | 20 | 0.7072 | 0.7030 |

The small differences come from the lognormal handle times, which are not exactly exponential.
