# summarize

**Port of conversation-memory summarization** (LangChain memory / summarize
node in LangGraph): long chats are condensed into memory notes.

Memory is just state: `Msg` artifacts accumulate; a `Summarize` produce
condenses the recent `context.view` into a `Summary` artifact every N messages;
a `Prune` produce keeps the working window bounded by deleting the oldest
messages (§27, §37). No chat buffer — the same artifacts feed both the prompt
and the summarizer.

```bash
uv run python -m examples.summarize.main
```

Demonstrates: `context.view` as chat memory, summary-as-artifact, windowing by
deterministic deletion.
