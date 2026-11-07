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
Taxonomy: `taxonomy.json`, SemEval 2025 Task 10 URW (11 narratives, 38 sub-narratives).

## Hosted (Fly.io)
Base URL: https://h4h-narrative-stubs.fly.dev. All three services run in one process (`server.py`):

| Path | Service |
|---|---|
| `/v1/...` | Bot Management |
| `/classifier/v1/...` | Classifier |
| `/webhook/{bot_id}` | Bot Runtime |

- One machine in `ams` with a 1 GB volume at `/data` (SQLite). Keep it to one machine, since SQLite can't be shared.
- The `/v1/_dev/...` endpoints need header `X-Dev-Key: $(cat .dev_key)`. The key is a Fly secret.
- To redeploy: `fly deploy --local-only --ha=false`. Fly's remote builder returned 401 errors on this app, so build with local Docker.
- Run locally as one process: `PORT=8080 HOST=127.0.0.1 python3 server.py`, or as three with `./run.sh`.

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
