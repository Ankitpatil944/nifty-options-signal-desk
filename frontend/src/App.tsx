import { AnimatePresence, motion } from "framer-motion";
import { Activity, BookOpen, FlaskConical, Route } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { BacktestLab } from "./pages/BacktestLab";
import { Journal } from "./pages/Journal";
import { LiveDesk } from "./pages/LiveDesk";
import { WalkForward } from "./pages/WalkForward";
import type { Meta } from "./types";
import { useLive } from "./useLive";

type Page = "live" | "lab" | "walk" | "journal";

const NAV: { id: Page; label: string; icon: typeof Activity }[] = [
  { id: "live", label: "Live desk", icon: Activity },
  { id: "lab", label: "Backtest lab", icon: FlaskConical },
  { id: "walk", label: "Walk-forward", icon: Route },
  { id: "journal", label: "Journal", icon: BookOpen },
];

function initialPage(): Page {
  const hash = location.hash.slice(1) as Page;
  return NAV.some((n) => n.id === hash) ? hash : "live";
}

export function App() {
  const [page, setPage] = useState<Page>(initialPage);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setError(null);
    api.meta().then(setMeta).catch((e) => setError(e.message));
  };
  useEffect(load, []);

  useEffect(() => {
    location.hash = page;
  }, [page]);

  const symbols = useMemo(() => meta?.symbols ?? [], [meta]);
  const live = useLive(symbols);
  const journalKey = live.signals.filter((s) => s.status !== "OPEN").length + live.signals.length;

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 16l5-5 4 4 9-9" />
            </svg>
          </span>
          <span>Signal Desk</span>
        </div>

        <nav className="nav" aria-label="Main">
          {NAV.map(({ id, label, icon: Icon }) => (
            <button key={id} className="nav-item" aria-current={page === id ? "page" : undefined} onClick={() => setPage(id)} style={{ zIndex: 0 }}>
              {page === id && <motion.span layoutId="nav-pill" className="nav-pill" transition={{ type: "spring", stiffness: 500, damping: 40 }} />}
              <Icon size={18} />
              <span className="label">{label}</span>
            </button>
          ))}
        </nav>

        <div className="sidebar-foot">
          <div className="conn">
            <span className={`dot ${live.connected ? "on" : ""}`} />
            {live.connected ? "Connected to backend" : "Backend offline"}
          </div>
          <div className="conn">
            <span className={`dot ${live.status?.running ? (live.status.risk.paused ? "warn" : "on") : ""}`} />
            {live.status?.running ? (live.status.risk.paused ? "Bot paused" : "Bot running") : "Bot stopped"}
          </div>
          <span>Suggestions only. Orders are placed by you.</span>
        </div>
      </aside>

      <main className="main">
        {error && !meta && (
          <div className="empty" style={{ minHeight: "60vh" }}>
            <h3>Can't reach the backend</h3>
            <p>Start it with <code>tradingbot serve</code> in the backend folder, then try again.</p>
            <button className="btn" onClick={load}>Try again</button>
          </div>
        )}
        {meta && (
          <AnimatePresence mode="wait">
            <motion.div
              key={page}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.18, ease: "easeOut" }}
            >
              {page === "live" && <LiveDesk meta={meta} live={live} />}
              {page === "lab" && <BacktestLab meta={meta} />}
              {page === "walk" && <WalkForward meta={meta} />}
              {page === "journal" && <Journal refreshKey={journalKey} />}
            </motion.div>
          </AnimatePresence>
        )}
      </main>

      <div className="notices" aria-live="polite">
        <AnimatePresence>
          {live.notices.map((n) => (
            <motion.div key={n.id} className={`notice ${n.tone}`} layout initial={{ opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 24 }}>
              {n.text}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}
