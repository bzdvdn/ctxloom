# knowledge — multi-source chat with evidence-backed answers

An English demo that answers questions over local docs (guide/pricing) and a
CSV cost table: search → evidence → claim verification → answer with source and
provenance (§17, §34-§36), plus deterministic calculation over structured data
(§29, §67).

## Structure

```
knowledge/
├── chat.py           # CLI + build_resources (docs + CSV + env LLM)
├── web.py            # thin FastAPI/SSE app (uses chat.build_resources)
├── models.py         # artifact types (Question, Evidence, Claim, Answer, …)
├── agents.py         # thin containers (produce/ via a flat import surface)
├── produce/          # staged pipeline (each Produce is its concern):
│   ├── common.py     #   routing regexes, chat memory, claim/verdict helpers
│   ├── router.py     #   greeting / direct reply vs research
│   ├── search.py     #   fan-out over sources + text/table materialization
│   ├── evidence.py   #   extraction + deterministic claim verification (§35-§36)
│   ├── calc.py       #   CSV aggregation → Calculation (§29, §67)
│   └── lifecycle.py  #   turn overseer + answer builder
├── web/index.html    # UI templates
├── docs/             # English documentation fixtures (guide / pricing)
└── .env.example      # keys for a real model
```

## Run

```bash
.venv/bin/python examples/knowledge/chat.py
.venv/bin/python examples/knowledge/web.py     # SSE UI on :8000
```

Without an LLM key the demo runs on deterministic fallbacks (§68); with a key
(in `.env`) generation goes through the configured provider.