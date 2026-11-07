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
