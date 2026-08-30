# Examples

Five working applications ship in `examples/` (in-repo, not packaged). They are
the reference implementations for the [recipes](recipes.md) and
[patterns](patterns.md) — canonical examples are split into a `produce/`
package (stages) + thin `web.py`/`chat.py` entries.

All demos run **with or without API keys**: configure `.env` (copy
`.env.example`) for LLM/embedder/image providers, or let them fall back to
deterministic demo mode.

## `knowledge` — multi-source chat with evidence

**What it shows:** `fan_out_sources` search over file + CSV sources → lazy
`materialize_doc` → evidence extraction → claim verification → answer with
provenance; deterministic CSV calculation (`Spreadsheet` → `Calculation`).

```bash
uv run python ./examples/knowledge/web.py    # FastAPI/SSE + trace dashboard
uv run python ./examples/knowledge/chat.py   # interactive CLI
```

Key files: `produce/` (common, router, search, evidence, calc, lifecycle),
`agents.py`, `web.py`.

## `research` — goes to the web

**What it shows:** `WebSource` with real URL discovery; *lazy* page resolution
only for pages the model ranks relevant (§6); evidence → verified claims →
answer with URL provenance; `StatusMachine` turn lifecycle.

```bash
uv run python ./examples/research/web.py
uv run python ./examples/research/chat.py
```

## `medic-lab` — hypothesis laboratory

**What it shows:** one question spawns competing hypotheses; each is
investigated over an evidence pool; **scored** by support/contradiction counts
(scores are calculated, not guessed); HITL steering via `PendingQuestion`;
honest report when evidence is insufficient; `concurrency_limit` (LLM agents = 2,
global cap = 6).

```bash
uv run python ./examples/medic_lab/main.py    # serves uvicorn automatically
```

## `devops` — HITL tool agent (ops assistant)

**What it shows:** `HITLLMAgent` + LLM **tool router** (routing is a separate
structured step, `StructuredLLM`), HITL-approved mutations for Kubernetes,
GitLab, Ansible (each is a fateful operation the LLM cannot dream up on its
own); trace dashboard with the `create_trace_router` UI.

```bash
uv run python ./examples/devops/web.py
```

## `repair` — budget-aware replanning (Russian by design)

**What it shows:** chat and catalog data are intentionally **Russian** — the
contrast with other English examples is deliberate (localization is a product
concern, not a framework one). The flow: fact collection → LLM design options →
3 photo previews → plan → **deterministic catalog estimate** → HITL approval →
budget complaint triggers a rebuild from an earlier stage with a `_downstream_resets`
rollback. Everything explicit is deterministic; only genuinely generative steps
use the LLM.

```bash
uv run python ./examples/repair/web.py
uv run python ./examples/repair/chat.py
```

## `forklab` — branch & merge (§39-§40)

**What it shows:** deterministic alternative-state exploration — one question,
two research strategies on **their own forks** (`Context.branch()`); a
three-way `merge()` that either unions cleanly or raises an explicit
`MergeConflict` (§40, never a silent choice); an evaluator over the merged
state whose `Answer` is linked `supported_by` to findings from **both**
branches. Fully offline (§67) — the point is the state semantics, not a model.
A `--conflict` flag demonstrates the conflict-and-policy-resolve loop.

```bash
uv run python -m examples.forklab.main            # happy path
uv run python -m examples.forklab.main --mermaid  # merged provenance graph
uv run python -m examples.forklab.main --conflict # explicit MergeConflict + policy
```

The same pattern is the natural base for rewriting `medic-lab`: hypotheses
become real forks instead of tag-routed channels.

## Running tests

```bash
.venv/bin/python -m pytest      # 245 tests
.venv/bin/mypy                  # strict typing across the repo
.venv/bin/ruff check            # lint
```

`uv sync` installs the dev+web groups from `pyproject.toml`; `uv build` ships
only the `ctxloom` wheel (examples and docs are not packaged).