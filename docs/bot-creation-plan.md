# Real bot creation: plan and status

Goal: `POST /v1/bots` produces a working Telegram bot without the dev activate endpoint. The classifier stays a keyword stub.

Each stage ends with a check that must pass before the next stage starts.

| Stage | What | Status |
| --- | --- | --- |
| 0 | Decisions + contract changes | Done |
| 1 | Persistent storage | Done (2026-11-07): Render + Neon |
| 2 | Telegram client + fake Telegram API for tests | Done (2026-11-07): local tests |
| 3 | Manager bot (BotFather, webhook) | Not started |
| 4 | Real creation link + matching the new bot | Not started |
| 5 | Activation (token, profile, webhook) | Not started |
| 6 | Real replies | Not started |
| 7 | Lifecycle: delete, token change, expiry, retire dev endpoint | Not started |

## Stage 0 decisions

| Decision | Choice | Why |
| --- | --- | --- |
| Storage | Neon free Postgres via `DATABASE_URL`; SQLite when it's unset | Render's free disk is wiped on every sleep or deploy. Neon's free tier needs no card, doesn't pause projects for inactivity, and wakes in a few hundred ms. |
| Matching a new Telegram bot to its pending record | `creation_link` = `https://t.me/<manager_bot>?start=<bot_id>`. The manager bot records the organizer's Telegram id from `/start`, replies with a `request_managed_bot` button, and matches the later `managed_bot` update by creator id. | Still works if the organizer changes the username. Costs one extra tap. |
| Organizer changes the username | Accept it. Store and return `telegram_username`; `config` stays unchanged. | Telegram checks usernames in its own app, so a taken name never reaches us as a failure. |
| Managed bot tokens | Don't store long-term. Fetch with `getManagedBotToken` and cache in memory (Stage 5). | The manager bot token can always re-fetch them; fewer secrets at rest. |

Contract changes (in `bot-management-api.yaml`, bundled into `frontend-openapi.yaml`):
- `Bot.telegram_username` added (present when `active`).
- `creation_link` is now a manager-bot deep link. The UI should still treat it as opaque.
- `failure_reason: username_occupied` no longer happens in practice.

`FRONTEND_API.md` and the shared contract doc get updated once Stage 5 works end to end.

## Telegram facts this relies on (Bot API 10.0, May 2026)

- Manager bots enable bot management in BotFather's Mini App; `getMe` then returns `can_manage_bots: true`.
- `KeyboardButtonRequestManagedBot` (`request_id`, `suggested_name`, `suggested_username`) asks the user to create a managed bot. There is also a link form: `t.me/newbot/<manager>/<username>?name=<name>`.
- The manager receives `Update.managed_bot` (`ManagedBotUpdated`: `user` = creator, `bot` = the bot) on creation and on token or owner changes.
- `getManagedBotToken(user_id)` returns the token; `replaceManagedBotToken(user_id)` rotates it.
- `setWebhook.secret_token`: 1–256 chars of `A-Z a-z 0-9 _ -`, sent back as `X-Telegram-Bot-Api-Secret-Token`.

## Stage 1 checks

Run `python3 tools/smoke_test.py <base_url> --dev-key <key>`, which exercises every endpoint. Persistence is checked by creating a bot, restarting or redeploying, then confirming it's still there:

```bash
python3 tools/smoke_test.py <base_url> --dev-key <key> --persist-create   # prints a bot id
# restart or redeploy the service
python3 tools/smoke_test.py <base_url> --persist-check <bot_id>
```

- [x] Local SQLite: smoke test passes; a bot survives a server restart; an old-schema `data.db` is upgraded in place.
- [x] Local Postgres (Docker): smoke test passes; a bot survives recreating the app container; an old-schema table is upgraded in place.
- [x] Render + Neon: smoke test passes on the live URL; an active bot (with a changed username) survives a manual redeploy.

## Stage 2 checks

```bash
python3 -m unittest discover -s tests -v
```

- `stubs/telegram.py`: the Bot API client. Base URL from `TELEGRAM_API_BASE`, tokens kept out of errors, and one retry on a short 429 wait.
- `tests/fake_telegram.py`: a fake Bot API. It records calls, can inject errors, and delivers updates to webhooks with the secret header, including `managed_bot` creation.
- `tests/test_telegram_client.py` (13 tests): every client method against the fake.
- `tests/test_lifecycle.py`: runs the real `server.py` against the fake. It currently covers replies, threading, `/start`, photos, no-match, group messages, filtered updates, forged updates, send failures and deletion. Stages 3, 4, 5 and 7 are skipped tests with their final assertions already written; each stage removes its skip.

- [x] All 24 tests pass (20 run, 4 skipped for later stages).
- [x] The tests catch breakage: removing reply threading or the secret check makes them fail.
- [x] The runtime sends replies through `telegram.py` (`TELEGRAM_SEND=1`), not hand-built requests.

The fake follows the docs, not observed behaviour. Stages 3–4 check the real API; if Telegram differs, fix the fake first, then the code.
