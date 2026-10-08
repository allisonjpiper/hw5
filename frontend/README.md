# Campus Customs Desk — dashboard

React + Vite + TypeScript frontend for the FastAPI backend in `../backend`.

```bash
# 1. backend (from Homework 5/backend)
../.venv/bin/uvicorn main:app --reload --port 8000

# 2. dashboard (from Homework 5/frontend)
npm install      # first time only
npm run dev      # http://localhost:5180
```

The API base URL defaults to `http://localhost:8000`. Override it with `VITE_API_BASE` in `.env.local` (see `.env.example`). See `../output/harness.md` → "Agent dashboard" for what each screen does and which routes it calls.
