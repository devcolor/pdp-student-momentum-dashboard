# Host it yourself

How to run the Playground on your institution's own server, with your own PDP files. Read it all
before loading real student records: the app was built for a datathon on mock data, and some of
what an institution needs isn't built.

This repo isn't maintained. Whoever deploys it owns its security, upgrades and data handling.

## Before you start: what the app doesn't do

- **It has no login.** No endpoint checks who's calling. Anyone who can reach the web app or the
  API can upload files, run loads, delete uploads and read every view. Put both behind your
  institution's single sign-on (see [Put it behind your sign-on](#put-it-behind-your-sign-on)),
  and never expose either port directly.
- **One endpoint returns student-level rows.** `GET /api/v1/sandbox/pipeline/tables/{name}`
  returns up to 200 rows a page from any data model table, students included. Small-group hiding
  doesn't apply to it. The Workbench uses it to preview loaded tables. With real data, block it at
  the proxy (the preview then stops working) or limit it to the people allowed to see records.
- **Small-group hiding is display protection, not a guarantee.** Groups under 10 students are
  hidden in the views, and it was checked only on mock data. It isn't a disclosure review.
- **It was tested on mock data only.** A real export may name columns differently. See
  [Swapping in your own PDP files](../README.md#swapping-in-your-own-pdp-files).

Get your institution's data-security approval before loading real records.

## What you need

- **A Linux server** (or VM) you control, with outbound internet for the first install. Only
  macOS and Ubuntu (in CI) have been tested.
- **The toolchain** from the README's [Prerequisites](../README.md#prerequisites): mise, which
  installs Python 3.14, Node, bun and uv at the pinned versions.
- **The whole repo.** The API imports code from `measures/`, `normalized-data-model/`, `mcp/`,
  `gap_finder/`, `data/dictionaries/` and `.agents/skills/metadata-advisor/`, so run it from a full
  clone, not a copy of `playground/server_application/` alone.
- **A database.** SQLite (one file, simplest) or PostgreSQL. PostgreSQL needs the
  [pgvector](https://github.com/pgvector/pgvector) extension, because a migration enables it.
  Development used PostgreSQL 18 (`pgvector/pgvector:pg18`), and it has had less testing than
  SQLite.
- **Disk:** about 2 GB for the code and packages, plus:
  - the published results file, about 650 MB, and the same again while a run rebuilds it;
  - uploads, up to 100 MB per file by default (`PIPELINE_UPLOAD_MAX_BYTES`);
  - the database, which holds the loaded data model.
- **Memory:** not measured. The mock load (10,313 students, 100,951 course rows) runs on a laptop.
  Watch the first real load.
- **A reverse proxy** that does HTTPS and your sign-on, such as nginx or Apache with
  oauth2-proxy, Shibboleth or your identity provider's module.

## 1. Install

As a dedicated service user, from the repo root, run quick start steps 1 to 4 in the
[README](../README.md#quick-start). On PostgreSQL, skip `mise run db:choose sqlite`. Then build
the web app:

```bash
cd playground/client_application
NEXT_PUBLIC_APP_ENV=production \
NEXT_PUBLIC_SANDBOX_ENABLED=true \
NEXT_PUBLIC_API_BASE_URL=https://sympa.your-school.edu/api/v1 \
NEXT_PUBLIC_REPOSITORY_URL=https://github.com/your-org/your-copy \
bun run build
```

`NEXT_PUBLIC_` values are fixed at build time, so rebuild after changing any of them. Without
`NEXT_PUBLIC_API_BASE_URL`, a production build calls the placeholder `https://api.example.com`.

## 2. Configure the API

Set these as real environment variables on the API's process (a systemd unit's `Environment=`
lines, or an `EnvironmentFile` only the service user can read). Real environment variables win
over the committed `.env.production`.

| Variable | Value | Why |
| --- | --- | --- |
| `APP_ENV` | `production` | Hides the Swagger page at `/docs`. Must be a real environment variable: the env files are chosen by it |
| `SANDBOX_ENABLED` | `true` | `.env.production` turns the views and Workbench off; this turns them back on |
| `DATABASE_URL` | `sqlite:////srv/sympa/data/sympa.db` or `postgresql://user:password@host:5432/sympa` | The app's database. Keep the password out of the repo |
| `CORS_ORIGINS` | `["https://sympa.your-school.edu"]` | Replaces the placeholder in `.env.production`. Not needed when the web app and API share one address, as below |
| `RESULTS_DB` | An absolute path, such as `/srv/sympa/data/success_measures.sqlite` | Where the published results live. Default `measures/output/success_measures.sqlite` in the clone |
| `SANDBOX_CHAT_ENABLED` | `false` | Keeps the AI chat off until your institution approves it. See [The AI chat](#the-ai-chat) |
| `DATABASE_ECHO` | leave unset (`false`) | `true` writes every SQL statement to the log, which can include student values |

The folder `RESULTS_DB` is in must be writable by the service user, or a Workbench run loads the
tables but skips rebuilding the results.

The OpenAPI schema at `/api/v1/openapi.json` stays available in production. It describes the
endpoints, not data.

## 3. Create the tables

Run the migrations once, and again after every upgrade, from `playground/server_application/`
with the same environment as the service:

```bash
uv run --no-dev alembic upgrade head
```

The API never creates tables on startup.

## 4. Run both services

Run each under a process manager (systemd, supervisord) that restarts it and keeps its logs.

```bash
# API, from playground/server_application/
uv run --no-dev fastapi run app/main.py --host 127.0.0.1 --port 8000 --workers 1

# Web app, from playground/client_application/
bun run start --hostname 127.0.0.1 --port 3000
```

**Run exactly one API worker.** The run lock and run status live in the worker's memory; with more
than one, two loads can run at once and status checks miss runs.

Both listen on `127.0.0.1` only, so the proxy is the only way in.

## Put it behind your sign-on

Serve both from one address, so the browser sends the sign-on cookie to both and no CORS setup is
needed. Every request the app makes to the API comes from the browser, not the web server.

```nginx
server {
    listen 443 ssl;
    server_name sympa.your-school.edu;
    # ssl_certificate ... ; your sign-on module or auth_request ... ;

    client_max_body_size 100m;  # match PIPELINE_UPLOAD_MAX_BYTES

    # Student-level rows: block, or allow only staff cleared to see records.
    location ~ ^/api/v1/sandbox/pipeline/tables/[^/]+$ { return 403; }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_read_timeout 300s;
    }
    location / {
        proxy_pass http://127.0.0.1:3000;
    }
}
```

Apply the sign-on to every location, the API included. Check from outside the network that
`https://sympa.your-school.edu/api/v1/health` asks for sign-on.

## 5. Load your data

1. Open the Workbench's Upload page (`/workbench/upload`).
2. Upload your PDP Analysis-Ready cohort and course files, and any supplemental files. The format,
   template and refused columns are in [Uploads and more data](../README.md#uploads-and-more-data).
3. Start a run. It loads the tables, then rebuilds the published results, which takes a few
   minutes. The upload screen shows each step.

The results only rebuild if your files cover every cohort year in `measures/manifest.yaml`
(2021-22 to 2024-25). Otherwise the tables still load, the run names the missing years, and the
views that read published results keep their earlier results. See
[known issues](known-issues.md).

To check the setup on mock data first, click **Use the mock files** instead.

## Where student data ends up

| Place | What's there |
| --- | --- |
| `normalized-data-model/data/uploads/` | Every uploaded file, as uploaded |
| The database at `DATABASE_URL` | The loaded data model: one row per student, course and term, plus supplemental values |
| The file at `RESULTS_DB` | Published results: counts and rates by group, including the hidden small groups' rows |
| `normalized-data-model/output/` | The mock data model from quick start step 3. Mock data only, unless you ran the loader on real files |
| Backups and logs | Whatever you back up, and any log written with `DATABASE_ECHO=true` |

**Deleting an upload in the Workbench removes its file and supplemental values, not the loaded
tables or the results.** To remove all student data:

1. Stop the API.
2. Delete everything in `normalized-data-model/data/uploads/`.
3. Delete the SQLite file, or drop and recreate the PostgreSQL database, then run
   `uv run --no-dev alembic upgrade head`.
4. Delete the file at `RESULTS_DB` and the `.publication.json` beside it.
5. Remove copies from backups, per your retention policy.

## The AI chat

The chat is optional and off when `SANDBOX_CHAT_ENABLED=false` or no `ANTHROPIC_API_KEY` is set.
If you turn it on:

- Each question sends the question, the page it was asked from, the conversation's earlier turns,
  and the aggregate results and column definitions the chat looks up, to Anthropic's API. Its
  checks refuse rows that look like individual students, but they catch mistakes; they aren't a
  security boundary.
- Everyone shares one key, and nothing records who asked what.
- Check Anthropic's current commercial terms and data retention with your institution's privacy
  office first, and set a spending limit on the key.
- A typical question costs a few cents. The app caps each question at 8 model calls.

## Operating it

- **Health check:** `GET /api/v1/health` answers 200 when the database is reachable, 503 when not.
- **Logs:** both services log to standard output; the process manager keeps them. Unexpected
  errors are logged with a stack trace, and the browser gets a generic message.
- **Back up:** the database and the uploads folder. The results file can be rebuilt with
  `python -m measures.publish` from the repo root, or by a Workbench run.
- **Upgrade:** there are no releases to upgrade to. Patching dependencies is up to you; check the
  Next.js and Python package advisories before going live, then rebuild the web app and rerun the
  migrations.
- **Restart** after changing API environment variables. A results rebuild doesn't need a restart.

## The Vercel example

[Deploy options](../README.md#deploy-options) describes the example deploy on Vercel, which serves
a trimmed, read-only copy of the mock data. It runs as `staging` with the docs page public, and
its uploads don't persist. Don't use it for real student data.
