# research — a question answered from real web pages

The research assistant leaves the local docs and **goes to the web**: it lazily
fetches seeded pages (`WebSource`, §6/§32), extracts evidence, verifies claims,
and answers with URL provenance.

It reuses the knowledge-demo pipeline (resolve → evidence → claim verification
→ answer) — only the *scout* is new, powered by `WebSource.asearch`.

## Run

```bash
.venv/bin/python examples/research/chat.py     # console (needs internet for fetch)
.venv/bin/python examples/research/web.py      # FastAPI + SSE UI on :8001
```

Seed pages come from `RESEARCH_URLS` (comma-separated) or default to two
Wikipedia topics. Without an LLM key the answer is still assembled
deterministically from the verified evidence (§68).

## Why

It demonstrates the constitution's §77 narrative on live traffic: a Reference
is cheap and lazy, `resolve()` materializes it, agents never encode "which URL
next" — the state (question, refs, evidence, claims) drives everything.