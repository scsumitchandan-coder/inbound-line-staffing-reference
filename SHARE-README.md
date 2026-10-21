# inbound-line-staffing — reference task bundle

A complete, **pipeline-green** TB-Science task repo, shared as a worked reference for how one
of these tasks is put together end to end.

- Domain: mathematical-sciences / operations-research (contact-centre staffing under
  abandonment and retrials)
- Status: TB3 Review pipeline green (2026-10-15); Pass@5 **0/5** — the frontier model did not
  solve it in five attempts
- Expert time estimate: 12 h

## What the task asks

From eight weeks of a phone line's call records, logged-in agents and the contract service
standard, write a planner that returns the fewest agents per half hour of a plan date that
still meet the standard, working forward through the day. Records are deliberately shaped by
an understaffed old roster, repeat attempts, withheld numbers, queue-dependent handle times,
clock changes and mid-record policy changes — so naively replaying history gives the wrong
requirement.

## Layout

```
tasks/inbound-line-staffing/
  instruction.md        what the solver model is given
  task.toml             task metadata, timeouts, environment limits
  environment/          Docker image + input data the solver sees
  solution/             reference solution (planner.py, solve.sh)
  tests/                verifier: grading engine, simulator, output tests
  authoring/            evidence + provenance for every graded number
README.md               repo-level narrative (TB-Science mode keeps narratives here)
checks/ rubrics/ docs/  static checks, grading rubrics, supporting docs
tests/                  repo-level authoring battery
PROPOSAL-inbound-line-staffing.md   the proposal this task was accepted from
```

## Reading order

1. `PROPOSAL-inbound-line-staffing.md` — the idea and why it is hard
2. `tasks/inbound-line-staffing/instruction.md` — exactly what the solver is told
3. `tasks/inbound-line-staffing/tests/` — how it is graded (the crux lives here)
4. `tasks/inbound-line-staffing/solution/planner.py` — the reference answer
5. `tasks/inbound-line-staffing/authoring/` — the evidence behind each graded field

Git history is not included; this is the final green tree.
