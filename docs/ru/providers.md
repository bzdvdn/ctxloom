# Провайдеры

Провайдеры — это *способности*: LLM, эмбеддеры, модели изображений/речи/видео.
Они живут в `ctxloom.providers`, не в ядре. Приложение подключает нужные в
`RuntimeResources`; ядро общается с ними только через узкие контракты
(`LLMProvider`, `EmbeddingProvider`, …).

## Контракты

Ядро знает четыре контракта:

| Контракт | Роль |
| --- | --- |
| `LLMProvider` | генерация текста (`generate`, `stream`) |
| `EmbeddingProvider` | векторные эмбеддинги |
| `ImageProvider` | генерация изображений |
| `SpeechProvider` / `TranscriberProvider` | TTS / STT |
| `VideoProvider` | генерация видео из текста |

`LLMRequest` / `LLMResponse` / `LLMResponseChunk` и `Message` — проводные типы.
`FakeLLM` и `FakeEmbedder` живут в `providers.fake` — детерминированные заглушки,
чтобы демо и тесты работали без ключей API.

## Переключатели через .env

Самая простая схема подключения — фабрики `*_from_env`, читающие `.env`:

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

Паттерн: **`llm_from_env() or <вендор по умолчанию>`**. Когда ключа нет, фабрика
возвращает `None`, и демо переходит на детерминированное поведение (поэтому каждый
пример работает вообще без ключей API).

Примеры в репозитории предпочитают **явные фабрики** (`openai_llm(...)`,
`openrouter_llm(...)`) с явным `max_tokens`: каждое демо определяет маленький
`build_llm()`, который читает `.env` и выбирает провайдера, — всегда видно,
какой провайдер работает, и при отсутствии ключа оно остаётся офлайн-совместимым.

## Чат-провайдеры

`OpenAICompatProvider` — универсальный клиент, совместимый с OpenAI, он же основа
вендорных фабрик. Поддерживает:

- `api_base` / кастомный `proxy` (базовый URL) и `auth_scheme`/`auth_header`.
- `_network_knobs` — батчинг, таймауты на запрос, политики ретраев.
- `stream` для посимвольных `LLMResponseChunk`.

| Фабрика | Вендор |
| --- | --- |
| `openai_llm` / `openai_embedder` | OpenAI |
| `anthropic_llm` | Anthropic |
| `mistral_llm` / `mistral_embedder` | Mistral |
| `deepseek_llm` | DeepSeek |
| `openrouter_llm` | OpenRouter (множество вендоров) |
| `groq_llm` | Groq (быстрый инференс) |
| `xai_llm` | xAI (`grok`) |
| `together_llm` | Together AI |
| `fireworks_llm` | Fireworks |
| `azure_llm` | Azure OpenAI |
| `cerebras_llm` | Cerebras (быстрый инференс) |
| `github_models_llm` | GitHub Models |
| `qwen_llm` | Qwen/百炼 |
| `nvidia_nim_llm` | NVIDIA NIM |
| `perplexity_llm` | Perplexity |
| `zai_llm` | Z.ai |
| `ollama_llm` | локальный Ollama |
| `gemini_llm` | Google Gemini (`GeminiProvider`) |

## Изображения, речь, видео

| Способность | Провайдеры |
| --- | --- |
| Изображения | `OpenAICompatImageProvider` (любой image API), `OpenRouterImageProvider`, `GeminiImageProvider`, `gemini_image`, `image_from_env` |
| Речь (TTS) | `OpenAICompatSpeech`, `speech_from_env` |
| Речь (STT) | `OpenAICompatTranscriber`, `transcriber_from_env` |
| Видео | `SoraVideoProvider`, `RunwayVideoProvider`, `LumaVideoProvider`, `OpenRouterVideoProvider`, `video_from_env` |

Каждая `*_from_env` принимает `**overrides`, чтобы в тестах можно было внедрить
конфигурацию без переменных окружения.

## .env-справочник (примеры)

В каждом демо есть `.env.example`; типичный набор для чат-модели:

```dotenv
# выбор модели (его читают фабрики *_from_env)
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-...
OPENROUTER_MODEL=deepseek/deepseek-chat

# опционально
EMBEDDING_PROVIDER=mistral
MISTRAL_API_KEY=...
IMAGE_PROVIDER=openrouter
IMAGE_MODEL=google/gemini-2.0-flash-exp:free
```

## Температура и max_tokens — дефолты провайдера, переопределение на вызове

`temperature` и `max_tokens` — это **дефолты уровня провайдера**, которые можно
переопределить на каждом вызове. `None` на обоих уровнях означает, что поле не
отправляется в запрос и API применит свой дефолт.

```python
from ctxloom.providers import openai_llm

# дефолт провайдера для всех запросов через него
llm = openai_llm(model="gpt-4o-mini", temperature=0.7, max_tokens=2048)
```

Переопределение на вызове побеждает (например, детерминированный экстрактор,
который не должен «блуждать»):

```python
body = await structured_llm(context, schema=AnswerBody, user=text, temperature=0.0)
```

Порядок разрешения: **вызов → провайдер → поле не отправляется**. То же
касается `llm_reply`, `ToolUse`, `LLMAgent`/`HITLLMAgent` (атрибуты класса
`temperature`/`max_tokens`, `None` = дефолт провайдера) и image-провайдера
(дефолты `n`/`size`/`quality` в конструкторе, переопределение на вызове через
`generate(prompt, size=...)`). Anthropic всегда отправляет `max_tokens` (этого
требует API) — по умолчанию `4096`, меняется в конструкторе.

## Детерминированный демо-режим

Когда LLM не настроен (`llm_from_env()` возвращает `None` и фолбэк не задан),
демо переходят на детерминированное поведение: заготовленные варианты, фолбэк-
планы, правило-суммирование. Правило строгое: настроенная модель, *вернувшая
ничего полезного*, сообщается честно (никогда не подменяется заглушками
молча); детерминированный фолбэк — только для режима «модели нет вовсе».