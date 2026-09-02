# Providers

Providers are *capabilities* — LLMs, embedders, image/speech/video models.
They live in `ctxloom.providers`, never in the core package. The app wires the
ones it needs into `RuntimeResources`; the core communicates with them only
through narrow contracts (`LLMProvider`, `EmbeddingProvider`, …).

## Contracts

The core itself knows four contracts:

| Contract | Role |
| --- | --- |
| `LLMProvider` | text generation (`generate`, `stream`) |
| `EmbeddingProvider` | vector embeddings |
| `ImageProvider` | image generation |
| `SpeechProvider` / `TranscriberProvider` | TTS / STT |
| `VideoProvider` | text → video generation |

`LLMRequest` / `LLMResponse` / `LLMResponseChunk` and `Message` are the wire
types. `FakeLLM` and `FakeEmbedder` ship in `providers.fake` — deterministic
stand-ins so demos and tests run with no API keys.

## The env-based switchers

The simplest wiring is `*_from_env` factory functions that read `.env`:

```python
from ctxloom.providers import (
    embedder_from_env,
    image_from_env,
    llm_from_env,
    openrouter_llm,
)

resources = RuntimeResources(llm=llm_from_env() or openrouter_llm())
emb = embedder_from_env()
if emb is not None:
    resources.embedder = emb
img = image_from_env()
if img is not None:
    resources.set("images", img)
```

Pattern: **`llm_from_env() or <vendor default>`**. If no key is set the factory
returns `None`, and the demo falls back to deterministic behavior (this is why
every example keeps working with no API key at all).

The in-repo examples prefer the **explicit factories** (`openai_llm(...)`,
`openrouter_llm(...)`) with an explicit `max_tokens` — each demo defines a small
`build_llm()` that reads `.env` and picks the provider, so you always see which
provider runs and it stays offline-capable when no key is present.

## Chat providers

`OpenAICompatProvider` is the generic OpenAI-compatible client and is the
backing for the vendor factories. It supports:

- `api_base` / custom `proxy` (base URL) and `auth_scheme`/`auth_header`.
- `_network_knobs` — batching, per-request timeouts, and retry policies.
- `stream` for token-wise `LLMResponseChunk`s.

| Factory | Vendor |
| --- | --- |
| `openai_llm` / `openai_embedder` | OpenAI |
| `anthropic_llm` | Anthropic |
| `mistral_llm` / `mistral_embedder` | Mistral |
| `deepseek_llm` | DeepSeek |
| `openrouter_llm` | OpenRouter (multi-vendor) |
| `groq_llm` | Groq (fast inference) |
| `xai_llm` | xAI (`grok`) |
| `together_llm` | Together AI |
| `fireworks_llm` | Fireworks |
| `azure_llm` | Azure OpenAI |
| `cerebras_llm` | Cerebras (fast inference) |
| `github_models_llm` | GitHub Models |
| `qwen_llm` | Qwen/百炼 |
| `nvidia_nim_llm` | NVIDIA NIM |
| `perplexity_llm` | Perplexity |
| `zai_llm` | Z.ai |
| `ollama_llm` | local Ollama |
| `gemini_llm` | Google Gemini (`GeminiProvider`) |

## Image, speech, video

| Capability | Providers |
| --- | --- |
| Image | `OpenAICompatImageProvider` (any image API), `OpenRouterImageProvider`, `GeminiImageProvider`, `gemini_image`, `image_from_env` |
| Speech (TTS) | `OpenAICompatSpeech`, `speech_from_env` |
| Speech (STT) | `OpenAICompatTranscriber`, `transcriber_from_env` |
| Video | `SoraVideoProvider`, `RunwayVideoProvider`, `LumaVideoProvider`, `OpenRouterVideoProvider`, `video_from_env` |

Each `*_from_env` accepts `**overrides` so you can inject config in tests without
setting environment variables.

## .env reference (examples)

Every demo ships an `.env.example`; a typical one for a chat model looks like:

```dotenv
# model selection (the *_from_env factories read these)
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-...
OPENROUTER_MODEL=deepseek/deepseek-chat

# optional
EMBEDDING_PROVIDER=mistral
MISTRAL_API_KEY=...
IMAGE_PROVIDER=openrouter
IMAGE_MODEL=google/gemini-2.0-flash-exp:free
```

## Temperature & max_tokens — provider defaults, per-call overrides

`temperature` and `max_tokens` are **provider-level defaults**, overridable per
call. A `None` at both levels means the field is omitted from the request and
the API applies its own default.

```python
from ctxloom.providers import openai_llm, openrouter_llm

# provider default for every request made through it
llm = openai_llm(model="gpt-4o-mini", temperature=0.7, max_tokens=2048)
```

Per-call overrides win (e.g. a deterministic extractor that must not wander):

```python
body = await structured_llm(context, schema=AnswerBody, user=text, temperature=0.0)
```

Resolution order: **call → provider → omit the field**. The same applies to
`llm_reply`, `ToolUse`, `LLMAgent`/`HITLLMAgent` (`temperature`/`max_tokens`
class attributes, `None` = provider default), and to the image provider
(`n`/`size`/`quality` defaults in the constructor, per-call override via
`generate(prompt, size=...)`). Anthropic always sends `max_tokens` (the API
requires it) — default `4096`, change it in the constructor.

## Deterministic demo mode

When no LLM is configured (`llm_from_env()` returns `None` and no fallback is
set), demos switch to deterministic behavior: canned options, fallback plans,
rule-based summarizing (§68). The rule is strict: a configured model that
*returns nothing usable* is reported honestly (never silently substituted with
stubs); the deterministic fallback is only for "no model at all" mode.