import { AnimatePresence, motion } from "framer-motion";
import type { ReactNode } from "react";
import { useId } from "react";

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
  label: string;
}) {
  const id = useId();
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.value} type="button" aria-pressed={o.value === value} onClick={() => onChange(o.value)}>
          {o.value === value && (
            <motion.span layoutId={`seg-${id}`} className="seg-pill" transition={{ type: "spring", stiffness: 500, damping: 38 }} />
          )}
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Panel({ title, aside, children, className = "" }: { title?: string; aside?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`panel ${className}`}>
      {title && (
        <div className="panel-title">
          <h3>{title}</h3>
          {aside && <span>{aside}</span>}
        </div>
      )}
      {children}
    </section>
  );
}

export function Stat({ label, value, tone }: { label: string; value: ReactNode; tone?: "pos" | "neg" }) {
  return (
    <div className="stat">
      <dt>{label}</dt>
      <dd className={tone}>{value}</dd>
    </div>
  );
}

export function LoadingLine({ active }: { active: boolean }) {
  return (
    <AnimatePresence>
      {active && (
        <motion.div
          className="loading-line"
          initial={{ scaleX: 0, opacity: 1 }}
          animate={{ scaleX: [0, 0.7, 0.92], transition: { duration: 8, ease: "easeOut" } }}
          exit={{ scaleX: 1, opacity: 0, transition: { duration: 0.4 } }}
        />
      )}
    </AnimatePresence>
  );
}

export function tone(v: number | null | undefined): "pos" | "neg" | undefined {
  if (v === null || v === undefined || v === 0) return undefined;
  return v > 0 ? "pos" : "neg";
}
