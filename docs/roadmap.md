# Roadmap

reactifact is pre-1.0 (`0.6.x`), one maintainer. This page is the honest
current state of "what's next" — not a wishlist. See [CHANGELOG.md](../CHANGELOG.md)
for what's already shipped, release by release.

## Now

- API is stabilizing around the primitives in the README's
  ["Core primitives"](../README.md#core-primitives) section
  (`Context`, `Artifact`, `Effects`, `Patch`, `Agent`, `Source`, `Provenance`).
  `0.5.0` already trimmed the public surface down to this set.
- MCP support (`reactifact.mcp`, shipped in `0.6.1`) is the newest primitive —
  hardening it (more transport coverage, more real-server testing) comes
  before adding new integration surfaces.

## Next

- **Stable 1.0** — freeze the public API surface (`Context`/`Artifact`/`Effects`/
  `Agent`/`Source`/`Provenance` and the recipes in
  [docs/en/recipes.md](en/recipes.md)), commit to semver guarantees, and close
  out breaking changes before they accumulate further (see the `### Breaking`
  entries already in `CHANGELOG.md` — the goal is for `1.0` to be the last one
  of those for a while).
- **More `Source` integrations** — today's built-in sources are filesystem,
  CSV, embeddings, and `WebSource` (see the `research` example). The
  `Source` protocol (`reactifact/sources.py`) is intentionally small so this
  grows by adding new implementations, not by changing the abstraction:
  direct API sources, SQL, and keyword search are the concrete gaps between
  what's documented as "equally first-class" in the README and what actually
  ships today.

## Non-goals (for now)

Carried over from [docs/en/comparison.md](en/comparison.md#where-reactifact-is-not-the-right-choice) —
worth repeating here since a roadmap page is where people look for the
opposite promise:

- **No managed hosting / SaaS platform.** reactifact is a library; there is no
  hosted execution or UI for non-engineers planned.
- **No large pre-built agent/tool marketplace.** The `Source` and MCP
  abstractions stay small and composable rather than growing a plugin
  ecosystem to compete with LangGraph/CrewAI's integration count.

## Contributing to the direction

Roadmap changes and feature discussion happen in
[GitHub Discussions](https://github.com/bzdvdn/reactifact/discussions), not
silently in code. If something here looks wrong or missing, open one.
