# web — hackathon-review frontend

Next.js frontend for the hackathon-review web app mode. Talks to the FastAPI backend in [`../api`](../api) and the shared pipeline in [`../src/hackathon_reviewer`](../src/hackathon_reviewer).

For setup, run instructions, and configuration, see the [main README](../README.md#mode-2--web-app).

## Local dev

```bash
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

Make sure the FastAPI backend is also running on `:8000` (see main README).
