# Terminal-Bench 3 — Task Template

## How to submit (fork → PR)

Requires [Git](https://git-scm.com/downloads), a GitHub account with access to your assigned repository,
and the [GitHub CLI](https://cli.github.com/) (`gh`). Run these commands in a terminal, one line at a
time. Replace `<your-task-repo>` everywhere, including the angle brackets, with your assigned
repository name. The example uses `handshake-project-dynamo`; if your assignment URL has a different
owner, use that owner in the fork and PR commands below.

```bash
# Sign in to GitHub (one-time setup; follow the prompts)
gh auth login

# Create your own copy and download it
gh repo fork handshake-project-dynamo/<your-task-repo> --clone
cd <your-task-repo>
git checkout -b submission
```

**Pause here to [build your task](#build-your-task), then complete the [submission checklist](#before-you-submit-checklist).**
When your task is ready, run these commands from the same repository folder:

```bash
# Review the files you are about to include
git status
git add -A && git commit -m "Task submission"
git push -u origin submission
gh pr create --repo handshake-project-dynamo/<your-task-repo> --fill
```

Submit to **your assigned task repository**. This template supplies the starting files; it is not
where you submit an assigned task. Before creating the PR, make sure `git status` lists only files
you intend to submit. `git add -A` includes all new, changed, and deleted files.

To iterate after reading feedback, edit and save your files, then run:

```bash
git status
git add -A && git commit -m "Address review feedback"
git push
```

Pushing to the same `submission` branch updates the existing PR. You do not need to fork again or
open another PR for each fix.

**New to GitHub?** A *repository* (repo) is the project folder on GitHub. A *fork* is your own copy;
*clone* downloads it to your computer. A *branch* keeps your changes together, a *commit* records
saved changes, and *push* uploads those commits. A *pull request* (PR) asks the project team to review
and accept them. The commands above create a PR ready for review. A **draft PR does not run the
automated review**; click **Ready for review** on GitHub when you want checks to start.

---

## Before you submit: checklist

- [ ] I am working in my assigned repository, with exactly **one task folder** under `tasks/`.
      I renamed `REPLACE-with-task-name` rather than leaving a second template task behind.
- [ ] My task comes from real domain expertise, requires meaningful work in a terminal, and is my
      own creation. Its difficulty comes from the problem, not missing information or an unfair time limit.
- [ ] `instruction.md` states the goal, inputs, required outputs, absolute output paths, and any
      necessary formats or tolerances. It stays within **1,500 tokens** and contains no solution
      steps or hints. I have not moved the task requirements into another document to shorten it.
- [ ] `task.toml` is filled in: task name, description, explanations, category/subcategory, tags,
      experience, expert time estimate, time limits, and resources. The task name is `insight/<folder-name>`.
- [ ] I replaced all template placeholders, including `REPLACE-with-pinned-digest` in **both** Dockerfiles.
- [ ] The agent's starting environment contains all required input data and tools, with no reference
      solution, hidden answers, or tests accidentally copied into it.
- [ ] My reference solution completes the task from a fresh starting environment. My tests accept
      correct results and reject empty, incorrect, or shortcut answers without imposing unstated requirements.
- [ ] The grader runs separately: `environment_mode = "separate"`, a complete `tests/Dockerfile`,
      and an `artifacts = [...]` list **above the first section** in `task.toml` naming what the grader needs.
- [ ] Grading tools are installed in `tests/Dockerfile`; `tests/test.sh` runs the tests and writes the
      result. Grading does not depend on a live website or downloading its test tools.
- [ ] My scripts and text files use UTF-8 and Unix (LF) line endings. I excluded unrelated generated
      logs, caches, and credentials.
- [ ] If I ran local checks, I read the results: static checks pass, **Oracle scores 1**, and
      **Nop scores 0**, without setup or grading errors. If I could not run them locally, I will
      check those results on the PR.
- [ ] My PR targets the assigned repository and is **ready for review**, with a clear description
      of the task and any testing I performed.

After submitting, read the feedback for your **latest commit**, fix blocking findings, and wait for
the final review gate. Passing the automated checks is followed by a maintainer's review.

## What you are building

A Terminal-Bench 3 task is a self-contained challenge that an AI agent attempts in a terminal.
You provide the problem, the starting environment, a working reference solution, and tests that
decide whether the agent succeeded. **The deliverable includes all four, not just a written prompt.**

Use the [Project Insight instructions](https://project-insight-instructions.learn.joinhandshake.com/)
alongside this README for project guidance; sign in with your Handshake account if prompted.

Choose a focused problem from work you understand well. It should require domain expertise and
multiple steps of exploration, reasoning, or tool use. A correct solution must be objectively
checkable. State the end result clearly, allow different valid approaches, and ensure your tests
cover the requirements without adding hidden ones.

Agents have internet access by default. Build difficulty around expertise and reasoning rather than
an answer that can simply be looked up. Keep task-specific inputs reproducible instead of depending
on a changing website. In `task.toml`, **omit `allow_internet` entirely**; setting it to either
`true` or `false` fails the current checks.

AI tools may help you build the task, but the task must be your own creation, rooted in your domain
experience. You are responsible for understanding and verifying the instruction, solution, and tests.

## Build your task

### 1. Rename the starter folder

Rename `tasks/REPLACE-with-task-name/` to a short, lowercase, hyphenated name with at most three words,
such as `parse-server-logs`. This **task folder name** is different from your assigned **repository name**.
In that folder's `task.toml`, set `[task].name` to `insight/parse-server-logs` (using your actual folder name).

Keep your task changes inside this folder. The provided workflows, checks, and rubrics are review
infrastructure; you do not need to edit them to submit a task.

### 2. Fill in the task files

All paths in this table are relative to `tasks/<your-task-name>/`.

| File | What to put in it |
| --- | --- |
| `instruction.md` | The prompt the agent sees: goal, inputs, constraints, and exact expected outputs. Use absolute paths such as `/app/output.json`; these paths are inside the task environment, not on your laptop. Give enough information to solve the problem, without giving away the solution. |
| `task.toml` | The task's settings and background. Explain why it is difficult, how your solution works, and how you verify it. Use [the annotated settings guide](docs/task-template.toml) and [the taxonomy](docs/TAXONOMY.md) to choose a category and describe your subcategory. |
| `environment/Dockerfile` | Instructions for building the agent's starting workspace. A Docker image is a packaged environment with the files and tools needed to run the task. Include the input data and starter code here, but keep the solution and tests out. |
| `solution/solve.sh` | The entrypoint for your correct reference solution, called the **Oracle**. It must actually solve the task from the starting state. It can call helper scripts such as `solution/solve.py`. |
| `tests/test_outputs.py` | The checks that decide whether the result is correct. Test the actual outputs or behavior, accept valid alternative solutions, and cover likely wrong answers and edge cases. |
| `tests/test.sh` | The entrypoint that runs your tests and writes a binary reward: `1` for success, `0` for failure. Keep the template's test-report and reward-writing behavior. |
| `tests/Dockerfile` | The separate grading environment. Install its tools here and copy the tests into `/tests/` so grading works after the agent's workspace has been shut down. |

```text
tasks/<your-task-name>/
├── instruction.md
├── task.toml
├── environment/
│   ├── Dockerfile
│   └── ...                 # Input data, starter code, or setup scripts
├── solution/
│   ├── solve.sh
│   └── ...                 # Optional solution helper scripts
└── tests/
    ├── Dockerfile
    ├── test.sh
    ├── test_outputs.py
    └── ...                 # Optional test helpers and expected results
```

### 3. Check the details that commonly cause failures

- **Replace Docker image placeholders.** Both starter Dockerfiles contain
  `sha256:REPLACE-with-pinned-digest`. Replace it with the real digest for the image you use;
  a digest identifies an exact image version. The placeholder cannot build.
- **Declare the files the grader needs.** In separate grading, only declared agent artifacts are
  transferred. For example, put `artifacts = ["/app/output.json"]` at the very top of `task.toml`,
  before `[task]` or any other section. List all necessary outputs, including code if the grader
  must execute it. In `tests/Dockerfile`, create their parent folders (for example, `RUN mkdir -p /app`).
- **Keep reference answers private from the agent.** Expected results belong in `tests/`; the
  reference solution belongs in `solution/`. Neither should be copied into the agent image, even
  temporarily during its build.
- **Keep the required agent time limit.** Terminal-Bench 4 agents always receive **28,800 seconds
  (8 hours)**, as set in the starter `task.toml`. Do not lower or remove `[agent].timeout_sec`.
  Set the verifier and environment resource limits according to the task's actual needs; do not use
  an artificially short limit to manufacture difficulty.
- **Use the required dependency versions.** Pin Python packages installed with `pip`/`uv` to exact
  versions. The current test-tool pins are `pytest==9.1.1` and `pytest-json-ctrf==0.5.2`. System packages
  installed with `apt` are an exception: do **not** pin them with `=version`. Do not force a CPU
  architecture with `FROM --platform`.
- **Keep the instruction concise and complete.** The shared checks limit `instruction.md` to
  **1,500 tokens**, measured with the Qwen3 tokenizer. Tokens are pieces of text, not a word count;
  use the count in the PR report. Remove filler while keeping the goal and requirements in
  `instruction.md`. Do not bypass the limit by moving the actual assignment into a separate
  `SPEC.md` or other document. Supporting domain data and reference material can still be provided.

## Understand the automated checks

The review starts when a **non-draft PR changes files under `tasks/`**. Most stages wait for earlier
blocking checks to pass, so a skipped stage is not a successful result. Task-changing pushes rerun
the review; a newer run cancels an older run still in progress. Allow the checks to finish and read
the PR comments and **Checks** tab for the latest commit.

The sequence below reflects the shared workflow linked from [this template's review workflow](.github/workflows/tb3-review.yml).
Shared checks can change independently of the copies in this repository; the current PR report is
the source to follow if it differs from a local result.

| Check shown on the PR | In plain language | What to do if it needs attention |
| --- | --- | --- |
| **Artificiality (C1)** | Is this a realistic expert task with a useful outcome, rather than a contrived puzzle? This is the first blocking review. | Explain the real workflow and redesign artificial constraints or busywork. |
| **TB3 static checks** | Are the files, settings, names, paths, Docker setup, and separate grader configured correctly? These checks inspect the package without asking an AI to solve it. | Fix the named items; common issues are listed above. |
| **Task validation (Oracle + Nop)** | Does your reference solution pass, and does doing nothing fail? **Oracle** runs your solution; **Nop** leaves the starting state unchanged. | Oracle must score **1**, Nop **0**, and both must complete without execution errors. Fix setup, solution, or tests as indicated. |
| **Implementation rubric** | Does the task meet the quality criteria: clear requirements, a correct solution, reliable tests, real difficulty, and no easy grading shortcuts? A rubric is the reviewer's list of criteria. | Read each failing criterion and its explanation; align the instructions, solution, and tests. |
| **Pass@2 attempt budget** | Is there a difficulty run available within your task's attempt allowance? | Read the budget comment. If exhausted, contact a maintainer; opening another PR does not reset it. |
| **Pass@2 difficulty** | The model tries the task twice. At least **2 valid scored trials** are needed, with **at most 1 solve** and at least 1 failure. | If both solve it, increase genuine difficulty. If results are missing or invalid, investigate the reported error. |
| **TB3 deep review** | A closer review of the task and trial evidence: does the solution really work, are the tests fair, and are model failures meaningful? | Address the detailed findings. A reviewer that fails to finish has not approved the task. |
| **AVA verifier audit (advisory)** | Tries to find ways a wrong answer could pass, or a correct answer could be rejected. **Verifier** means grader; **AVA** means Adversarial Verifier Audit. | Read and assess the findings to strengthen your tests. This stage does not block the automated gate. |
| **Pass@3 difficulty (combined Pass@5)** | Runs **3 fresh trials** after the earlier reviews, then combines them with this run's initial 2. The final gate needs at least **5 valid trials**, **at most 2 solves**, and at least 3 failures. | Read the combined result. Passing the initial two-trial check alone is not enough. |
| **Conversion QC gate** | The final summary: did every required stage pass? **QC** means quality control. The job keeps this name even for newly authored tasks. | Resolve the first blocking failure. When this gate passes, a maintainer still makes the final decision. |

**Similarity is advisory in the current workflow.** A separate **Semantic similarity (shadow)**
check looks for overlap with existing tasks after static checks. “Shadow” means its findings are
reported without blocking the automated gate. Originality remains a task-quality requirement;
read any findings and discuss substantial overlap with a maintainer.

**What counts as a trial?** A trial is one model attempt. A valid scored trial produces a usable
grading result. Setup errors, verifier failures, and missing results do not count as evidence that
the task is hard. An agent timeout can count as a scored failure if grading completes, but the
quality review still checks that the task and its time allowance are fair.

**How the attempt budget works:** the current allowance is **15 counted Pass@2 executions per fellow
per task repository**, across PRs. One execution spends one attempt if it produces at least one
usable solved or failed trial; it does not spend one attempt per individual trial. Runs that stop
before Pass@2, or produce only infrastructure errors or unresolved results, do not spend the budget.
Artificiality, static checks, Oracle/Nop, and rubric feedback remain unlimited.

Maintainers can also request extra trials or audits with `/run`, `/cheat`, or `/ava`. These require
maintainer permissions and are advisory; you do not need to post them yourself.

## Test locally (optional)

You can submit through GitHub without running Docker on your computer. Local checks can catch
problems before you use a review attempt, but they do not replace the PR's full quality and
difficulty review.

For local checks, use a Bash-compatible terminal (on Windows, WSL is suitable), Python 3.11 or newer,
and [uv](https://docs.astral.sh/uv/). To run the reference solution and Nop, also install and start
[Docker](https://www.docker.com/). Run from the repository folder and replace `<your-task-name>`
with the folder name under `tasks/`:

```bash
# Inspect the task files and settings; no Docker or model API key needed
bash checks/static-report.sh tasks/<your-task-name>

# Install the same Harbor version used by the current review workflow
uv tool install "harbor==0.18.0"

# Run your reference solution: expected reward is 1
harbor run -p tasks/<your-task-name> --agent oracle --env docker

# Run a do-nothing attempt: expected reward is 0
harbor run -p tasks/<your-task-name> --agent nop --env docker
```

**Harbor** is the tool that builds the environments, runs attempts, and collects grading results.
Read its reported results and logs, not just whether the command finished. A build error or missing
reward is not an acceptable Nop failure. The local static-check copy may lag the shared PR checks.
If you already have another Harbor version installed, use a separate environment or follow uv's
instructions for updating it to the version above.

## If you get stuck

| What you see | Next step |
| --- | --- |
| `gh: command not found` or `git: command not found` | Install the tool linked at the top, then reopen your terminal. |
| “Repository not found” or permission denied | Check the repository owner/name against your assignment, run `gh auth status`, and confirm that the signed-in account has accepted its repository invitation. |
| Git asks for your identity when committing | Follow Git's instructions to set `user.name` and `user.email` for your commits, then retry. |
| No automated feedback | Confirm the PR is ready for review and changes files under `tasks/`. If so, inspect the Checks/Actions page and ask a maintainer about any access or workflow error. |
| A later check is skipped | Find and fix the earlier blocking check first. |
| A check is cancelled | Look for the newer run triggered by your latest push. Cancelled does not mean passed. |
| “Not determined,” infrastructure error, or no grading result | Read the error. Fix task setup problems if identified; ask a maintainer about service or workflow failures. Do not change task difficulty just to work around an unavailable service. |

When asking for help, include your PR link, the failing check's name, and the relevant error text.
You do not need personal model API keys for the automated PR review; the project supplies its review
credentials. A draft PR can share work in progress with a maintainer, but automatic checks start
only after it is marked ready for review.
