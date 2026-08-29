"""research produce — stages → verify → lifecycle.

Mirrors the pipeline stage by stage: `stages` (routing, web search,
materialization, extraction) → `verify` (deterministic claim verification) →
`lifecycle` (turn overseer, answer builder). `common` holds the shared helpers.
Flat re-exports keep the agent containers' imports stable.
"""

from .lifecycle import BuildAnswer, EvaluateTurn
from .stages import ExtractEvidence, ResolveRef, Router, WebScout
from .verify import VerifyClaims

__all__ = [
    "BuildAnswer",
    "EvaluateTurn",
    "ExtractEvidence",
    "ResolveRef",
    "Router",
    "VerifyClaims",
    "WebScout",
]
