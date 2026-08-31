# Release management

How a `ctxloom` version is cut, built, verified, and published.

## Versioning

- [SemVer](https://semver.org/); pre-releases carry an `rc` mark — `0.1.0rc1`.
- The version lives in **two places** and must stay in sync:
  - `pyproject.toml` → `[project] version`;
  - `ctxloom/__init__.py` → `__version__`.

## Changelog rule

Every user-visible change lands in `CHANGELOG.md` (Keep a Changelog). Cut the
entry when the version is bumped:

1. move unreleased items under a new `## [X.Y.Z] — <date>` heading;
2. group them as `Added` / `Changed` / `Removed` (deprecations too);
3. mark breaking changes explicitly, even in `rc`s.

## The release loop

```bash
# 1) sanity
.venv/bin/python -m pytest
.venv/bin/python -m mypy
.venv/bin/python -m ruff check
.venv/bin/python -m ruff format --check

# 2) version + changelog (see above)

# 3) build artifacts
uv build                     # dist/ctxloom-0.1.0rc1-py3-none-any.whl + sdist

# 4) verify the wheel in a scratch venv (not the workspace, so no PYTHONPATH)
uv venv /tmp/ctxloom-rc
/tmp/ctxloom-rc/bin/python -m pip install --quiet dist/ctxloom-0.1.0rc1-py3-none-any.whl
/tmp/ctxloom-rc/bin/python -c "import ctxloom; print(ctxloom.__version__)"
/tmp/ctxloom-rc/bin/python -m ctxloom graph examples.knowledge.agents 2>/dev/null \
    || /tmp/ctxloom-rc/bin/ctxloom --help >/dev/null   # console script present
# confirm the wheel contains ctxloom + tracing templates and NOT examples/tests:
unzip -l dist/ctxloom-0.1.0rc1-py3-none-any.whl | grep -E "examples/|tests/|tracing/templates" 

# 5) tag
git tag v0.1.0rc1
git push origin v0.1.0rc1

# 6) publish (PyPI token in env)
uv publish --publish-url https://upload.pypi.org/legacy/
```

## What ships

`uv build` packages only the `ctxloom` package (setuptools `packages.find`
excludes `examples`/`tests`) plus the trace dashboard templates
(`ctxloom/tracing/templates/*.html`). Examples, tests and docs stay in the
repository and are the documentation-by-example.

## Rollback

A broken `rc` is fixed in the next `rc`/release — never rewrite history of a
tagged version. Keep patch releases strictly backwards-compatible (§61: the
framework is stable at the stated surface).