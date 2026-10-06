# Agenclave

[![ci](https://github.com/daveck11/BlackBox-Agenclave/actions/workflows/ci.yml/badge.svg)](https://github.com/daveck11/BlackBox-Agenclave/actions/workflows/ci.yml)

Live demo: <https://agenclave.onrender.com> (free instance, the first load can take
30 s). Walkthrough: [Loom](https://www.loom.com/share/38124557b68b4372ac44e7d3d5875210).

Agenclave sends a bug to several coding models at once, runs each model's patch
against the bug's tests, and keeps the one that passes. It also keeps a per-model
record of what passed before and uses that to decide which models get the next bug.

I built it on BlackBox's API after meeting the team at London Tech Week. BlackBox's
Chairman pattern runs several agents and has a judge pick the best patch by reading
it. Agenclave started as a reproduction of that, then replaced "pick by reading" with
"pick by running" and put learned routing in front. It is meant to sit on top of
BlackBox, not compete with it.

## How a run works

```
issue {title, body}
   |
   v
triage          TF-IDF classifier: bug / feature_request / documentation / question_other
   |            only a bug goes on; anything else stops here, for free
   v
routing         one Beta(passed+1, failed+1) draw per model, send the task to the top 3 of 4
   |
   v
dispatch        each model returns one unified diff, concurrently
   |
   v
verify          apply each diff to a scratch copy of the repo, run its tests
   |            trusted / applies_but_fails / broken
   v
rank + record   tier first, reliability only breaks ties; each outcome goes in the store
   |
   v
chairman        explains the verified winner and says which patch it would have picked by reading
```

Logged-in users can save issues and runs to a Workspace.

## Three rules

1. Reliability decides who competes. Each model has a pass count per category in
   `results/model_reliability.json`. The router draws one Thompson sample from
   `Beta(passed+1, failed+1)` per model and dispatches the top `route_k` (default 3).
   I use a random draw rather than "take the highest" because the greedy pick locks
   in the leader forever. A model with little data has a wide posterior and still gets
   picked sometimes.
2. Verification decides who wins. For each run I apply every patch in a scratch copy
   of the repo, run the tests, and sort: passed, applied but failed, didn't apply.
   Reliability is only a tiebreak. A model with a bad history can still win a run if
   its patch is the one that works, so the store never becomes self-fulfilling.
3. Only verification writes the store. There are two call sites,
   `scripts/verified_run.py` and a web run on one of the practice bugs, and both run
   the task's own tests first. A free-text web run has no repo to test against, so
   the Chairman judges it by reading and nothing is written.

## Providers

Every model call goes through one `Agent` interface
(`src/agenclave/harness/interfaces.py`). Three backends: `direct` (Anthropic or OpenAI
by model name), and `blackbox` / `openrouter`, which are the same OpenAI-compatible
adapter with a different key and base URL. BlackBox closed self-serve API keys in
October 2026, so the live demo runs through OpenRouter with the same four models and
the same ids. Switching back is one environment variable.

## The app

- Triage: classify an issue and get next steps. A bug gets a "Send to the code-fix
  agents" button.
- Code-fix: the issue is routed and dispatched. Dry run by default; live spends
  credits. The routing table, every candidate's diff, the verification tiers and the
  Chairman's explanation are shown. When a practice bug is loaded, its own category
  drives the gate (the classifier reads three of the ten as documentation or feature
  requests, and still runs and is shown).
- A live run needs a logged-in user, and all users share one cap of
  `AGENCLAVE_LIVE_DAILY_CAP` runs per UTC day (default 20). Triage, dry runs and the
  About page need no account.
- Workspace: saved issues and runs, per user. Nothing auto-saves.
- `make app` builds the React app and serves UI + API from one `uvicorn` process.

## Quickstart

```bash
make setup     # venv + pinned deps (CPU-only torch)
make stage1    # data -> train -> eval  (writes results/classifier_metrics.json)

make app       # builds frontend/dist, serves everything on http://localhost:8000

# Develop with hot reload (two terminals):
make serve     # FastAPI on :8000
make demo      # Vite dev server on :5173 (proxies to :8000)

make test      # pytest
make trust     # verified best-of-N -> per-model reliability (dry run by default)
```

SQLite is created on first start (`data/agenclave.db`). Set a real `SECRET_KEY` in
`.env` for anything beyond local use. Live runs need a key in `.env`
(`OPENROUTER_API_KEY`, `BLACKBOX_API_KEY`, or `ANTHROPIC_API_KEY` /
`OPENAI_API_KEY` with `AGENCLAVE_PROVIDER` set to match), a logged-in user, and room
under the daily cap. Deploy notes: [`DEPLOY.md`](DEPLOY.md).

Windows without `make`: run the one-line equivalent per target (see the `Makefile`).

## Results

### Triage classifier (issue type, 4 classes, held-out test n = 1,793)

| Estimator        | Features      | Macro-F1  | Accuracy |
| ---------------- | ------------- | --------- | -------- |
| Logistic Reg.    | TF-IDF        | 0.675     | 0.674    |
| Random Forest    | TF-IDF        | 0.653     | 0.655    |
| Logistic Reg.    | MiniLM embed. | 0.628     | 0.628    |
| Random Forest    | MiniLM embed. | 0.569     | 0.578    |

I expected the MiniLM embeddings to win and they didn't. Issue text is short and the
signal sits in a few tokens, which suits a bag-of-words model. TF-IDF also serves
without torch and gives me the top tokens to show in the UI. Per-class numbers and the
confusion matrix are in [`results/`](results/) and the
[model card](models/MODEL_CARD.md).

### Per-model reliability

Learned by the verified harness (`make trust`, `scripts/verified_run.py`) and by web
runs on the practice bugs, stored in `results/model_reliability.json`. Committed
snapshot, 6 October 2026:

| Model                              | Verified pass rate (bug fixtures) |
| ---------------------------------- | --------------------------------- |
| `moonshotai/kimi-k2.7-code`        | 19 / 19                           |
| `deepseek/deepseek-v4-pro`         | 17 / 18                           |
| `nvidia/nemotron-3-nano-30b-a3b`   | 16 / 17                           |
| `mistralai/devstral-2512`          | 2 / 5                             |

These are tiny samples on ten practice bugs, and they move; the live instance has
already added runs on top of this snapshot. I show them because the store is real,
not because the numbers mean much yet. The counts started through BlackBox's API and
continued through OpenRouter; the ids are the same, so the history carries over.
Offline, with no network or keys: `scripts/demo_router.py` (routing) and
`scripts/demo_trust.py` (verified ranking).

## Datasets

The classifier predicts issue type only: `bug`, `feature_request`, `documentation`,
`question_other`, from the NLBSE'23 issue dataset (AGPL-3.0, used for a
non-commercial portfolio project with attribution). I wanted a severity head too, but
the only severity dataset I could download at a useful size has no licence beyond
"cite the paper", so I left it out; the training path still exists behind
`--with-severity`. There is no `performance` class because no public dataset labels
one. Sources, sizes and licences: [`data/README.md`](data/README.md).

## Repo layout

```
src/agenclave/
  classifier/   feature pipeline, training, inference, recommendations (triage)
  api/          FastAPI app factory; routes/ (triage, auth, issues, runs, fixtures);
                db.py + models.py (SQLAlchemy), auth.py (bcrypt + JWT)
  harness/      Agent interface, providers, dispatch, Chairman judge,
                router + reliability store + patch verification
scripts/        prepare_data | train_classifier | evaluate_classifier | verified_run
frontend/src/   React SPA: pages/ (Triage, CodeFix, Workspace, About, Login, Register),
                components/, auth + issue contexts, api.js
tests/          pytest; fixtures/ = 10 practice bugs, each with its own tests
results/        metrics JSON + plots + the per-model reliability store
.github/        CI: pytest on every push and PR (torch-free install)
```

The project began as a reproduction of the Chairman pattern benchmarked on SWE-bench
resolve rate. That version is archived in [`OLD_BUILD.md`](OLD_BUILD.md).

## Author

David Nkpa. Code is [MIT](LICENSE).
