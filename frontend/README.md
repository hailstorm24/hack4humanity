# Narrative Bots frontend

Next.js 16 (App Router, React 19, Tailwind v4) website for the Hack4Humanity narrative-bot builder.

```bash
npm install
npm run dev        # http://localhost:3000, uses built-in sample data
```

To use Hailey's API instead of sample data:

```bash
cp .env.example .env.local
npm run dev
```

See `AGENTS.md` for structure and conventions. Scaffolded from the MIT-licensed [ai-website-cloner-template](https://github.com/JCodesMore/ai-website-cloner-template); none of its cloning workflow is used here.
