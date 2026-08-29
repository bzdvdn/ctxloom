# REST API

The platform provides a REST API for automation: creating projects, running
calculations, and accessing the catalog and estimates.

## Methods

| Method | Path                    | Purpose              |
| ------ | ----------------------- | -------------------- |
| GET    | /api/v1/projects        | list projects        |
| POST   | /api/v1/projects        | create a project     |
| GET    | /api/v1/projects/{id}   | project details      |
| POST   | /api/v1/projects/{id}/plan | run a plan calculation |
| GET    | /api/v1/catalog         | material catalog     |

## Response format

Responses are JSON. Lists support pagination: pass the `page` and `page_size`
parameters; the response includes `total` and a link to the next page.

## Error codes

- 400 — invalid request parameters;
- 401 — key missing or invalid;
- 403 — insufficient permissions for the operation;
- 404 — object not found;
- 409 — version conflict (the project was already changed);
- 429 — request limit exceeded;
- 500 — internal error.

## Versioning

The path includes a version: `/api/v1/...`. Backward-compatible changes do not
break the old version; deprecated versions are supported for at least two
quarters after a new one ships.

## Limits

By default — 300 requests per minute per key. The limit can be raised in the
organization settings; a rate-limit response arrives with the `Retry-After`
header.