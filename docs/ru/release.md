# Релиз-менеджмент

Как режется, собирается, проверяется и публикуется версия `ctxloom`.

## Версионирование

- [SemVer](https://semver.org/); пре-релизы помечаются `rc` (например,
  `0.4.0rc1`), для стабильного релиза `rc` убирается (`0.4.0`).
- Версия живёт в **двух местах** и должна совпадать:
  - `pyproject.toml` → `[project] version`;
  - `ctxloom/__init__.py` → `__version__`.

## Правило чейджлога

Каждое видимое пользователю изменение попадает в `CHANGELOG.md` (Keep a
Changelog). При бампе версии:

1. перенесите незакрытые пункты под новый заголовок `## [X.Y.Z] — <дата>`;
2. сгруппируйте `Added` / `Changed` / `Removed` (в т.ч. устаревшее);
3. явно помечайте ломающие изменения даже в `rc`.

## Обновление между версиями

Отдельного migration-гайда нет — источник истины о том, что изменилось,
`CHANGELOG.md`, ломающие изменения помечены по правилу выше. Два изменения,
о которых стоит знать при переходе через них:

- **0.4.0-rc1** — `LLMRequest.temperature` был захардкожен как `0.7`, стал
  `float | None`; `None` теперь означает «не передавать поле → дефолт
  провайдера», а не «использовать `0.7`». Форма вызова та же, поведение
  генерации — другое, ошибки не будет — если код полагался на старый неявный
  дефолт, передайте `temperature=0.7` явно (на вызов или на провайдер).
- **0.1.0-rc1** — `Produce` больше не возвращает `Patch`; вместо этого пишет
  `self.effects.create/update/link/ask/resume` и возвращает `None` (см.
  [effects](effects.md)). `InterruptPatch`, `Patch.merge_existing_patch` и
  `Patch.to_dict` удалены.

## Цикл релиза

```bash
# 1) проверки
.venv/bin/python -m pytest && .venv/bin/python -m mypy \
  && .venv/bin/python -m ruff check && .venv/bin/python -m ruff format --check

# 2) версия и чейджлог

# 3) сборка
uv build                         # dist/ctxloom-0.4.0-py3-none-any.whl + sdist

# 4) проверка wheel в чистом venv (не workspace — чтобы не цеплял PYTHONPATH)
uv venv /tmp/ctxloom-rc
/tmp/ctxloom-rc/bin/python -m pip install dist/ctxloom-0.4.0-py3-none-any.whl
/tmp/ctxloom-rc/bin/python -c "import ctxloom; print(ctxloom.__version__)"
/tmp/ctxloom-rc/bin/ctxloom --help          # console-скрипт на месте
unzip -l dist/ctxloom-0.4.0-py3-none-any.whl | grep -E "examples/|tests/|tracing/templates"

# 5) тег
git tag v0.4.0 && git push origin v0.4.0

# 6) публикация (токен PyPI в env)
uv publish --publish-url https://upload.pypi.org/legacy/
```

## Что входит в дистрибутив

`uv build` пакует только пакет `ctxloom` (setuptools `packages.find` исключает
`examples`/`tests`) плюс шаблоны трейс-дашборда
(`ctxloom/tracing/templates/*.html`). Примеры, тесты и docs остаются в
репозитории и служат документацией-примером.

## Откат

Сломанный `rc` чинится в следующем `rc`/релизе — историю тега не переписываем.
Патч-релизы строго обратно совместимы (§61).