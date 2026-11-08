# This is NOT the Next.js you know

This version has breaking changes: APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing code. Heed deprecation notices. For example, `params` in a page is a Promise.

# Narrative Bots frontend

The website for the Hack4Humanity narrative-bot builder. An organizer writes replies for propaganda narratives, creates a Telegram bot, confirms it in Telegram, and manages their bots. It talks only to the Bot Management API; the contract is `../FRONTEND_API.md` and `../frontend-openapi.yaml`.

## Commands
- `npm run dev` / `npm run build` / `npm run lint` / `npm run typecheck`
- `npm run check` runs lint, typecheck and build.

## Data: mock or real
`src/lib/api.ts` is the only module the UI uses for data. With `NEXT_PUBLIC_API_BASE_URL` unset it uses the in-browser sample data in `src/lib/mock.ts` (kept in sessionStorage). With it set, every call goes to that API. Types are in `src/types/api.ts` and mirror the OpenAPI file. If the contract changes, update the types first.

## API contract
Types in `src/types/api.ts` come from `src/types/api.gen.ts`, which is generated from `../frontend-openapi.yaml` (`npm run types`). Errors are branched on `body.error`, never the message (`src/lib/errors.ts`). Requests time out after 90 s and show a "Waking the server…" banner after 4 s, because the hosted API sleeps when idle. A bot's real handle is `telegram_username`; `config.username` is only a suggestion. Never call `/v1/_dev/...` from shipped code. Run `npm run types` again whenever `../frontend-openapi.yaml` changes.

## Routes
- `/` landing page, `/new` bot builder, `/bots` list, `/bots/[id]` confirmation and detail.
- A bot in `pending` status polls `GET /bots/{id}` every 3 s on its page.

## Design
Warm dark by default (light follows the system, with a manual toggle stored in localStorage as `nb-theme`). Geologica for display and labels, Onest for text; both cover Cyrillic. Palette: sage and peach as the two accents, a gold for "working" states, three soft background orbs. Pills for actions, 20px surfaces, a blurred sticky header. The landing page is a sticky phone showing a Telegram (iOS) chat that follows scroll (`src/components/Landing.tsx`); its colors are Telegram's own, set with `light-dark()` under `.tgp`. All tokens are CSS variables at the top of `src/app/globals.css`. Respect `prefers-reduced-motion`.

## Rules
- TypeScript strict, no `any`. 2-space indentation. Mobile-first, no horizontal scroll.
- Field limits and error messages mirror the contract. Show server 422 details next to the field.
- Never call `/v1/_dev/...` endpoints from shipped UI code.

<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
