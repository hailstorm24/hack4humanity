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
Unit + lifecycle tests (fake Telegram, no network): `python3 -m unittest discover -s ../tests -v` from here, or `-s tests` from the repo root.
Smoke test any running server: `python3 ../tools/smoke_test.py http://127.0.0.1:8080 --dev-key KEY` (all services in one process via `server.py`).
Load test (a demo audience's burst): `python3 ../tools/load_test.py <base_url> [-n 100] [--dev-key KEY]`. Without a key it only classifies and hits the webhook for an unknown bot, so it's safe on the hosted URL.
Postgres connections are pooled (`DB_POOL_MAX`, default 10); see `store.py`.
Taxonomy: `taxonomy.json`, SemEval 2025 Task 10 URW (11 narratives, 38 sub-narratives).

## Hosting: Render free tier
`../render.yaml` (a Render Blueprint) deploys `server.py`, which runs all three services in one process:
`/v1/...` (management), `/classifier/v1/...`, `/webhook/{bot_id}` and `/healthz`.

- **Cost:** free. The service sleeps after 15 min with no traffic, and the first request after that takes about 1 minute.
- **Data:** set `DATABASE_URL` (a Postgres connection string, e.g. Neon's free tier) in the Render dashboard so bots survive sleeps and deploys. Without it, the service falls back to SQLite on the container disk, which Render wipes on every sleep, restart or deploy.
- **Manager bot:** set `MANAGER_BOT_TOKEN` (from @BotFather) in the dashboard. On startup the service registers the manager's webhook at `/telegram/manager`; check it with `GET /v1/_dev/manager` (`X-Dev-Key` header).
- **Dev key:** Render generates `DEV_KEY`. Copy it from the service's Environment tab in the dashboard.
- **Deploys:** `autoDeploy` rebuilds on every push to the connected branch.
- **Run the same way locally:** `PORT=8080 HOST=127.0.0.1 python3 server.py`

`fly.toml` is kept from the earlier Fly.io deploy (which had persistent data, about $2.34/month); it's unused now.

## What's fake
- **Classifier**: keyword rules in `classifier_rules.json`, not a model (`stub-keywords-0.2`). Replace `score_text()`.
  Every label in the taxonomy has a rule with Russian and English keywords and a demo sentence in each language;
  `python3 classifier.py --demo [ru|en]` prints them. Keywords are lower-case and match where a word starts
  (`ё` = `е`), so a stem like `провоцир` catches every ending. A rule's base score gets +0.03 for each extra keyword
  hit, capped at 0.97. To add a phrase, append it to the rule's `ru` or `en` list; startup fails if a keyword is
  used twice or a label isn't in `taxonomy.json`. Known limits: no negation ("это не нацисты" still matches),
  no Ukrainian. Test hooks: text containing `#fail` → 503, `#slow` → 12 s delay.
- **Telegram creation flow**: real when `MANAGER_BOT_TOKEN` is set (see `manager.py`): `creation_link` opens the
  manager bot, which offers a create button, then activates the new bot (token, profile, webhook). Without a token,
  simulate the organizer confirming with `POST /v1/_dev/bots/{id}/activate` (body `{}` or `{"fail":"username_occupied"}`);
  it returns the webhook `secret_token`.
- **Sending**: the runtime sends real replies when the bot has a token (a managed bot, or `{"telegram_token": "..."}`
  passed to dev activate). Otherwise it only logs them. Replies are always echoed as `stub_replies` in the webhook
  response. `TELEGRAM_SEND=0` forces log-only.

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
