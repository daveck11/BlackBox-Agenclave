# Agenclave frontend

React 19 + Vite single-page app. The pages are Triage, Code-fix, Workspace, About,
Login and Register; `src/api.js` is the one fetch wrapper.

```bash
npm install
npm run dev      # on :5173, proxies the API to :8000 (run `make serve` in the repo root)
npm run build    # writes dist/, which the FastAPI app serves at /
```

Everything else is in the root [README](../README.md).
