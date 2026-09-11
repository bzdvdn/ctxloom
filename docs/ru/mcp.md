# MCP

reactifact говорит на [MCP](https://modelcontextprotocol.io) в обе стороны:
вызывает инструменты внешнего MCP-сервера как обычные `Tool`, или отдаёт
собственные `Tool` (и работающий `Context`) как MCP-сервер — для Claude
Desktop, Claude Code или другого агента. Оба направления требуют extra `mcp`:

```bash
pip install "reactifact[mcp]"
```

Ядро reactifact нигде не импортирует `mcp` — обычный `pip install reactifact`
никогда не тянет SDK; `reactifact.mcp` кидает читаемый `ImportError` с
подсказкой по установке, если вызвать его без extra.

## Клиент: вызов удалённых MCP-инструментов

`mcp_stdio_tools`/`mcp_http_tools` подключаются к MCP-серверу и отдают его
инструменты как `list[Tool]` — тот же контракт `Tool`, что уже принимают
`ToolUse`/`LLMAgent`, поэтому удалённый MCP-инструмент и локальная функция с
`@tool` взаимозаменяемы:

```python
from reactifact import Consume, create_agent
from reactifact.mcp import mcp_stdio_tools
from reactifact.tool_use import ToolUse

async with mcp_stdio_tools(
    "npx", ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
) as tools:
    fs_agent = create_agent(
        "fs",
        consumes=[Consume(Question)],
        produces=[ToolUse("Отвечай на вопросы о файлах в /tmp.", tools)],
    )
    # tools (и fs_agent) работают, пока открыт блок `async with`
```

`mcp_http_tools(url)` подключается так же, но по streamable HTTP. Оба —
тонкие обёртки над `mcp.ClientSession`; используйте `mcp_tools(session)`
напрямую, если сами управляете сессией (авторизация, свой транспорт, …).

## Сервер: отдать reactifact как MCP

`create_mcp_server` строит `mcp.server.mcpserver.MCPServer` из списка `Tool` —
как рукописных подклассов `Tool`, так и функций с `@tool`, потому что у обоих
уже есть JSON-схема (`Tool.schema`), которая становится реальными именами и
типами аргументов MCP-инструмента, а не одним непрозрачным `**kwargs`:

```python
from reactifact.mcp import create_mcp_server
from reactifact.tools import tool

@tool
async def search_catalog(query: str, limit: int = 10) -> str:
    """Ищет по каталогу товаров."""
    ...

server = create_mcp_server([search_catalog], name="my-app")
await server.run_stdio_async()
```

`destructive=True` у `Tool` становится аннотацией `destructiveHint` у
MCP-инструмента — тот же сигнал, что читает собственный UI подтверждения в
Claude Desktop.

### Публикация Context

Передайте `context=`, чтобы дополнительно опубликовать два read-only
ресурса по MCP — внешний клиент сможет заглянуть в состояние работающего
reactifact-приложения, включая provenance, так же, как ваш собственный код
через `context.list_artifacts()`/`context.get()`:

```python
server = create_mcp_server(tools, context=ctx, name="my-app")
```

- `context://artifacts/{artifact_type}` — все артефакты одного типа, сначала
  новые (например, `context://artifacts/Answer`).
- `context://artifact/{artifact_id}` — данные и версия одного артефакта.

### Монтирование по HTTP

`server.streamable_http_app()` возвращает Starlette-приложение — монтируйте
его на то же FastAPI-приложение, что и `create_trace_router`/
`create_chat_router`:

```python
app.mount("/mcp", server.streamable_http_app())
```

## Ошибки: `ToolOutput.error` → MCP `is_error`

`Tool`, вернувший `ToolOutput(error=...)` (или выбросивший исключение),
доходит до MCP-клиента как `is_error=True` с сохранённым сообщением —
reactifact внутри кидает собственный `ToolError` из SDK: единственный тип
исключения, который SDK не маскирует до общего "Error executing tool …" для
вызывающей стороны.
