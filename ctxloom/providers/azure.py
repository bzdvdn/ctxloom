"""Azure OpenAI — chat (OpenAI-compatible, deployment-as-model)."""

from __future__ import annotations

from typing import Any

from .chat import OpenAICompatProvider, _network_knobs


def azure_llm(
    endpoint: str,
    api_key: str | None = None,
    deployment: str | None = None,
    **kwargs: Any,
) -> OpenAICompatProvider:
    """OpenAI-compatible Azure provider.

    `endpoint` is the resource URL, e.g.
    https://my-resource.openai.azure.com/openai/deployments/my-deployment;
    pass `deployment` or set AZURE_OPENAI_API_KEY / AZURE_OPENAI_DEPLOYMENT.
    """
    import os

    if api_key is None:
        api_key = kwargs.get("api_key") or os.getenv("AZURE_OPENAI_API_KEY")
    if deployment is None:
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
    merged = {**_network_knobs("AZURE", kwargs), **kwargs}
    return OpenAICompatProvider(
        base_url=endpoint, api_key=api_key, model=deployment, **merged
    )
