# web

Next.js 16 frontend (App Router, TypeScript, Tailwind CSS 4). Project rules: [../../CLAUDE.md](../../CLAUDE.md).

```bash
pnpm install
cp .env.example .env.local      # API_INTERNAL_URL for server-side API calls
pnpm dev                        # http://localhost:3000
pnpm lint && pnpm typecheck && pnpm test && pnpm build
pnpm gen:api                    # regenerate src/lib/api/schema.d.ts from ../api/openapi.json
```

`AGENTS.md` / `CLAUDE.md` in this folder are maintained by Next.js (`next dev` re-adds them).
