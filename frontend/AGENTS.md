# This is NOT the Next.js you know

This version has breaking changes: APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing code. Heed deprecation notices. For example, `params` in a page is a Promise.

# Narrative Bots frontend

The website for the Hack4Humanity narrative-bot builder. An organizer writes replies for propaganda narratives, creates a Telegram bot, confirms it in Telegram, and manages their bots. It talks only to the Bot Management API; the contract is `../FRONTEND_API.md` and `../frontend-openapi.yaml`.

## Commands
- `npm run dev` / `npm run build` / `npm run lint` / `npm run typecheck`
- `npm run check` runs lint, typecheck and build.

## Data: mock or real
`src/lib/api.ts` is the only module the UI uses for data. With `NEXT_PUBLIC_API_BASE_URL` unset it uses the in-browser sample data in `src/lib/mock.ts` (kept in sessionStorage). With it set, every call goes to that API. Types are in `src/types/api.ts` and mirror the OpenAPI file. If the contract changes, update the types first.

## Routes
- `/` landing page, `/new` bot builder, `/bots` list, `/bots/[id]` confirmation and detail.
- A bot in `pending` status polls `GET /bots/{id}` every 3 s on its page.

## Design
Newsroom / proof-desk look: serif for voice (Source Serif 4), Golos Text for UI (Cyrillic-first), IBM Plex Mono for identifiers. Square corners, ruled lines, a highlighter yellow for what the classifier found and a red pen for problems. All tokens are CSS variables at the top of `src/app/globals.css`, with a dark theme. Keep the one motion moment (the highlighter sweep on the landing headline) and respect `prefers-reduced-motion`.

## Rules
- TypeScript strict, no `any`. 2-space indentation. Mobile-first, no horizontal scroll.
- Field limits and error messages mirror the contract. Show server 422 details next to the field.
- Never call `/v1/_dev/...` endpoints from shipped UI code.
