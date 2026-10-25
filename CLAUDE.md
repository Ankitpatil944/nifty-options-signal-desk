# Signal Desk

NIFTY/BANKNIFTY options signal engine. Suggestions only, never places orders. See README.md.

- Backend: `backend/` (Python, FastAPI). Venv at `backend/.venv`. CLI: `tradingbot --help`.
- Frontend: `frontend/` (React + Framer Motion + Recharts, Vite). `npm run build` -> served by `tradingbot serve`.
- Checks: `ruff check .` and `pytest -q` in backend; `npm run build` in frontend.
- Invariant: strategies must stay causal and share code between backtest and live (tests/test_no_lookahead.py).
- Exchange params (lot sizes, expiries, charges) live in backend/config/settings.yaml.
