# map_reduce

**Port of the fan-out → aggregate pattern** (LangChain/LangGraph map-reduce;
Haystack pipelines): split a document deterministically → summarize each chunk
(produces run in parallel as the chunk events fan out) → combine into one final
summary.

```bash
uv run python -m examples.map_reduce.main
```

Artifacts: `Doc → Chunk×3 → ChunkSummary×3 → FinalSummary`, with `from_doc`,
`derived_from` and `supported_by` provenance kept (§34). The combine waits for
*every* chunk summary before running (a guard on the state, §69).

Demonstrates: parallelized fan-out through ordinary artifact events (§24),
`self.effects.create(...).link(...)` handles, and state-eligibility guards.
