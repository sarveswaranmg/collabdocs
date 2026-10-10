# CollabDocs API

Django REST Framework + PostgreSQL implementation of the Airtribe CollabDocs brief.

## Setup

1. Create and activate a virtual environment.
2. Install pinned dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and set a strong `SECRET_KEY` and database password.
4. Start PostgreSQL:
   ```bash
   docker compose up -d
   ```
5. Create/apply migrations:
   ```bash
   python manage.py makemigrations api
   python manage.py migrate
   ```
6. Start Django:
   ```bash
   python manage.py runserver
   ```

## Authentication

Register with `POST /api/users/`. The response includes JWT `access` and `refresh` tokens.
Send `Authorization: Bearer <access-token>` on authenticated requests.

## Main endpoint operations

- `POST /api/users/` — register
- `GET /api/users/{id}/` — retrieve the authenticated user's own profile
- `POST /api/workspaces/` — create workspace and add owner as admin atomically
- `GET /api/workspaces/{id}/` — retrieve workspace
- `POST /api/workspaces/{id}/members/` — add member (admin only)
- `GET /api/workspaces/{id}/members/` — list members
- `GET /api/workspaces/{id}/summary/` — workspace aggregate summary
- `POST /api/documents/` — create document and first version atomically
- `PUT /api/documents/{id}/` — update document and create a version atomically
- `GET /api/documents/` — list/filter documents
- `GET /api/documents/{id}/versions/` — list versions
- `GET /api/documents/{id}/stats/` — document counts
- `POST /api/documents/{id}/tags/` — add tags
- `POST /api/comments/` — create top-level or threaded comment
- `GET /api/comments/?document={uuid}` — list document comments
- `POST /api/tags/` — create tag
- `GET /api/audit-logs/` — list the authenticated actor's audit records

The PDF says “17 endpoints”; the table has 17 method/path operations when counting each listed method separately. The router also exposes standard detail/list routes where ModelViewSet requires them; review the route list before submission if your instructor strictly counts every HTTP method.

## Useful document filters

`?workspace=<uuid>&status=draft,published&title=plan&search=roadmap&updated_after=2026-01-01T00:00:00Z&updated_before=2026-12-31T23:59:59Z&ids=<uuid>,<uuid>&tag=python`

## Postman

Import `CollabDocs.postman_collection.json`. Set collection variables `base_url` and `access_token`. Register a user first, then copy the returned access token into `access_token`. Create a workspace before documents/comments.

## Before submission

- Commit all generated migrations.
- Test all requested operations and permission/error cases in Postman.
- Record the required 5–10 minute demo with audio showing transaction rollback, middleware logs, an aggregation endpoint, and a signal-created AuditLog after document update. Add the video link here.


## Screen Record link
https://drive.google.com/file/d/1ICKIWXcldeKXKiUprL8d51DI3gFGo51g/view?usp=sharing