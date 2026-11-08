# API stubs

Stdlib-only Python (3.10+, no installs) implementations of the three specs.

| Service | Spec | Port |
|---|---|---|
| Classifier | `../classifier-api.yaml` | 8001 (`/v1/...`) |
| Bot Management | `../bot-management-api.yaml` | 8000 (`/v1/...`) |
| Bot Runtime | `../bot-runtime-api.yaml` | 8002 (`/webhook/{bot_id}`) |

```bash
./run.sh
```

State lives in `data.db` (SQLite, shared by management + runtime). Delete it to reset.
Set `DATABASE_URL=postgresql://...` to use Postgres instead (needs `pip install -r requirements.txt`). See `store.py`.
Smoke test any running server: `python3 ../tools/smoke_test.py http://127.0.0.1:8080 --dev-key KEY` (all services in one process via `server.py`).
Taxonomy: `taxonomy.json`, SemEval 2025 Task 10 URW (11 narratives, 38 sub-narratives).

## Hosting: Render free tier
`../render.yaml` (a Render Blueprint) deploys `server.py`, which runs all three services in one process:
`/v1/...` (management), `/classifier/v1/...`, `/webhook/{bot_id}` and `/healthz`.

- **Cost:** free. The service sleeps after 15 min with no traffic, and the first request after that takes about 1 minute.
- **Data:** set `DATABASE_URL` (a Postgres connection string, e.g. Neon's free tier) in the Render dashboard so bots survive sleeps and deploys. Without it, the service falls back to SQLite on the container disk, which Render wipes on every sleep, restart or deploy.
- **Dev key:** Render generates `DEV_KEY`. Copy it from the service's Environment tab in the dashboard.
- **Deploys:** `autoDeploy` rebuilds on every push to the connected branch.
- **Run the same way locally:** `PORT=8080 HOST=127.0.0.1 python3 server.py`

`fly.toml` is kept from the earlier Fly.io deploy (which had persistent data, about $2.34/month); it's unused now.

## What's fake
- **Classifier**: keyword rules in `classifier.py` (`RULES`), not a model. Replace `score_text()`.
  Test hooks: text containing `#fail` → 503, `#slow` → 12 s delay.
- **Telegram creation flow**: `creation_link` is a placeholder. Simulate the organizer confirming with
  `POST /v1/_dev/bots/{id}/activate` (body `{}` or `{"fail":"username_occupied"}`); it returns the webhook `secret_token`.
- **Sending**: the runtime logs replies and echoes them as `stub_replies` in the webhook response.
  `TELEGRAM_SEND=1` plus `{"telegram_token": "..."}` on activate sends for real.

## Walkthrough
```bash
curl -s localhost:8000/v1/taxonomy
curl -s -X POST localhost:8000/v1/bots -H 'Content-Type: application/json' -d '{
  "display_name":"Test","username":"test_factcheck_bot","confidence_threshold":0.6,
  "other_response":"Ничего не найдено.",
  "responses":[{"narrative":"Blaming the war on others rather than the invader","subnarrative":null,"text":"…"}]}'
curl -s -X POST localhost:8000/v1/_dev/bots/$ID/activate -d '{}'
curl -s -X POST localhost:8002/webhook/$ID -H "X-Telegram-Bot-Api-Secret-Token: $SECRET" \
  -H 'Content-Type: application/json' \
  -d '{"update_id":1,"message":{"message_id":1,"date":1,"chat":{"id":1,"type":"private"},"text":"НАТО провоцировало Россию"}}'
```
