# Релиз-менеджмент

Как режется, собирается, проверяется и публикуется версия `ctxloom`.

## Версионирование

- [SemVer](https://semver.org/); пре-релизы помечаются `rc` — `0.1.0rc1`.
- Версия живёт в **двух местах** и должна совпадать:
  - `pyproject.toml` → `[project] version`;
  - `ctxloom/__init__.py` → `__version__`.

## Правило чейджлога

Каждое видимое пользователю изменение попадает в `CHANGELOG.md` (Keep a
Changelog). При бампе версии:

1. перенесите незакрытые пункты под новый заголовок `## [X.Y.Z] — <дата>`;
2. сгруппируйте `Added` / `Changed` / `Removed` (в т.ч. устаревшее);
3. явно помечайте ломающие изменения даже в `rc`.

## Цикл релиза

```bash
# 1) проверки
.venv/bin/python -m pytest && .venv/bin/python -m mypy \
  && .venv/bin/python -m ruff check && .venv/bin/python -m ruff format --check

# 2) версия и чейджлог

# 3) сборка
uv build                         # dist/ctxloom-0.1.0rc1-py3-none-any.whl + sdist

# 4) проверка wheel в чистом venv (не workspace — чтобы не цеплял PYTHONPATH)
uv venv /tmp/ctxloom-rc
/tmp/ctxloom-rc/bin/python -m pip install dist/ctxloom-0.1.0rc1-py3-none-any.whl
/tmp/ctxloom-rc/bin/python -c "import ctxloom; print(ctxloom.__version__)"
/tmp/ctxloom-rc/bin/ctxloom --help          # console-скрипт на месте
unzip -l dist/ctxloom-0.1.0rc1-py3-none-any.whl | grep -E "examples/|tests/|tracing/templates"

# 5) тег
git tag v0.1.0rc1 && git push origin v0.1.0rc1

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