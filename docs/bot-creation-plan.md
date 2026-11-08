# Real bot creation: plan and status

Goal: `POST /v1/bots` produces a working Telegram bot without the dev activate endpoint. The classifier stays a keyword stub.

Each stage ends with a check that must pass before the next stage starts.

| Stage | What | Status |
| --- | --- | --- |
| 0 | Decisions + contract changes | Done |
| 1 | Persistent storage | Done (2026-11-07): Render + Neon |
| 2 | Telegram client + fake Telegram API for tests | Done (2026-11-07): local tests |
| 3 | Manager bot (BotFather, webhook) | Done (2026-11-07): hosted + phone |
| 4 | Real creation link + matching the new bot | Done (2026-11-07): real Telegram via Desktop |
| 5 | Activation (token, profile, webhook) | Done (2026-11-08): real Telegram via Desktop |
| 6 | Real replies | Replies work on a phone (2026-11-08); after-sleep check open |
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

`FRONTEND_API.md` and the shared contract doc get updated once Stage 5 works end to end (done in Stage 6).

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

## Stage 3 checks

Code: `stubs/manager.py`.
- **At startup:** `getMe` gives the manager's username (used in `creation_link`) and `can_manage_bots`. Then `setWebhook` points at `{PUBLIC_URL}/telegram/manager`, with `allowed_updates = ["message", "managed_bot"]` and a webhook secret derived from the token (HMAC).
- **`POST /telegram/manager`:** drops updates with a missing or wrong secret, answers private messages with an intro, and logs `managed_bot` updates (activation is Stage 5).
- **`GET /v1/_dev/manager`** (needs `X-Dev-Key`): returns `getMe` and `getWebhookInfo` results, without the token or secret.
- **Without `MANAGER_BOT_TOKEN`:** everything still runs, links use the `STUB_MANAGER_bot` placeholder, and manager updates are dropped.

- [x] Local: 28 tests; 25 pass and 3 are skipped (Stages 4, 5, 7). Five new Stage 3 tests cover webhook registration, the intro reply, forged updates, quietly accepting a `managed_bot` update, and the dev status endpoint not leaking secrets.
- [x] The tests catch breakage: removing the manager secret check makes them fail.
- [x] With no token, the smoke test passes and links use the placeholder.
- [x] Hosted: `GET /v1/_dev/manager` shows `@h4h_manager_bot`, `can_manage_bots: true`, the webhook at `/telegram/manager` with `allowed_updates` `[message, managed_bot]`, `pending_update_count: 0` and no errors. The live smoke test passes, and `creation_link` now points at `t.me/h4h_manager_bot?start=<bot_id>`.
- [x] Hosted: sending `/start` to `@h4h_manager_bot` from a phone gets the intro reply.

## Stage 4 checks

Code: `stubs/manager.py` (`handle_start`, `handle_managed_bot`) and a new `claimed_at` column.
- **`/start <bot_id>`:** a pending bot is claimed (the sender's `organizer_tg_id` and `claimed_at` are saved). The reply has a `request_managed_bot` button pre-filled with `display_name` and `username`.
  - A malformed, unknown, deleted or failed ID gets "invalid link". An expired one gets "expired". An active one gets its `t.me` link.
  - While the bot is pending, the latest person to open the link wins.
- **`managed_bot` update:** among the creator's claimed pending bots, it picks the one whose `config.username` matches the new bot's username; otherwise, the most recently claimed. It stores `telegram_bot_id` and `telegram_username`, and the bot stays `pending` until Stage 5.
  - If the creator has no claim, they're told and nothing is linked.
  - A repeat update for a bot that's already linked is ignored (token and owner changes are Stage 7).

- [x] Local: 35 tests; 33 pass and 2 are skipped (Stages 5, 7). Eight new Stage 4 tests.
- [x] The tests catch breakage: matching any creator's claim, ignoring the username preference, or skipping the expiry check each make a test fail.
- **Finding (2026-11-07):** Telegram's servers accept our `request_managed_bot` button. But the **iOS app** opened an empty "Forward" chat picker instead of a creation screen, so it doesn't support the button yet. **Telegram Desktop** shows the creation screen. Tell organizers to use Desktop (or an app version with support) until iOS catches up.
- [x] Keeping the suggested username (Telegram Desktop): `match: @h4h_test_89e432b_bot (9260990615) -> bot bb818040-… by username (2 candidate(s))`.
- [x] Changed username (Telegram Desktop): `match: @newname12bot (9241523573) -> bot 95f5ee45-… by most recent claim (1 candidate(s))`.

## Stage 5 checks

Code: `stubs/manager.py` (`activate`, `bot_token`) and `stubs/runtime.py` (`send`).
- **Right after the match:** `getManagedBotToken` → `setMyName` / `setMyDescription` / `setMyShortDescription` from config → `setWebhook` to `{PUBLIC_URL}/webhook/<bot_id>` with a fresh per-bot secret and `allowed_updates: ["message"]` → status `active`, `telegram_link` from the actual username. The organizer gets "Готово! Бот @… работает: t.me/…".
  - Profile failures are logged and skipped. A token or webhook failure leaves the bot `pending` (linked) and tells the organizer to open the link again; reopening it retries activation.
- **Tokens:** never stored. `bot_token` caches them in memory; the runtime fetches one on first send after a restart, and re-fetches once on a 401 (e.g. rotated in BotFather).
- The dev activate endpoint still works (the smoke test uses it); Stage 7 retires it. The lifecycle tests no longer use it.
- Hosted replies still go through the `TELEGRAM_SEND` gate, which Render doesn't set, so a hosted bot activates but only logs its replies until Stage 6.

- [x] Local: 38 tests; 37 pass and 1 is skipped (Stage 7). Five Stage 5 tests: activation end to end (renamed username, profile, webhook, secret matches, token not stored or returned, answers a reader), webhook failure then retry via the link, token fetch failure, profile failure not fatal, token rotation.
- [x] The tests catch breakage: dropping the 401 re-fetch or the retry-on-reopen each make a test fail.
- [x] With no token, the smoke test passes.
- [x] Hosted (Telegram Desktop, 2026-11-08): bot `bf529fb1-…` created via the API, opened `creation_link`, kept the suggested username. `GET /v1/bots/<id>` went from `pending` to `active` with `telegram_username: h4h_s5_bf13ee_bot` and `telegram_link: https://t.me/h4h_s5_bf13ee_bot`, without the dev endpoint.

## Stage 6 checks

Code: `stubs/runtime.py`, `stubs/common.py` (`UpdateDedup`), `stubs/manager.py`.
- **Sending is on by default.** The runtime sends whenever the bot has a token (a managed bot, or a dev-activated one given `telegram_token`). Bots without one only log their replies, so local runs without `MANAGER_BOT_TOKEN` and the dev-endpoint smoke test behave as before. `TELEGRAM_SEND=0` forces log-only.
- **Repeat updates are skipped.** Telegram re-delivers an update it thinks we missed (e.g. while Render wakes up). Each bot's last 1000 `update_id`s, and the manager's, are kept in memory; a repeat gets a silent 200. A restart forgets them, which is fine: re-deliveries after a cold start land on the same new process.
- `tools/smoke_test.py` now numbers its `update_id`s like Telegram does; reusing `1` would now be dropped as a repeat.
- Docs: `FRONTEND_API.md`, the shared contract doc and `bot-management-api.yaml` (+ the bundle) describe real creation: the manager-bot link, Telegram Desktop, `telegram_username`, retry by reopening the link, tokens not stored, `failed` reserved, data persists.

- [x] Local: 42 tests; 41 pass and 1 is skipped (Stage 7). Four new Stage 6 tests: a re-delivered update gets one reply, the same `update_id` on two bots is not a repeat, the manager skips repeats, and a tokenless bot only logs.
- [x] The tests catch breakage: turning off dedup, or making sending opt-in again, each make tests fail.
- [x] With no token, the smoke test passes.
- [x] Phone, after deploy (2026-11-08): a message to `@h4h_s5_bf13ee_bot` got a real reply in Telegram, threaded under it.
- [ ] Phone, after the service has slept (15+ min idle): send one message; exactly one reply arrives, within about a minute.
