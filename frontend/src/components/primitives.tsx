/**
 * Shared presentation primitives.
 *
 * Panel is the important one: it renders the provenance envelope (basis line and
 * severity notes) so no figure in this product can appear without its caveat.
 */
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  fmtInt,
  rampColor,
  type Callout,
  type CountItem,
  type Kpi,
  type PanelMeta,
  type PanelNote,
  type Severity,
} from "../lib/api";

const GLYPH: Record<Severity, string> = {
  caveat: "!",
  critical: "!!",
  thin: "~",
  info: "i",
};

export function Note({ note }: { note: PanelNote }) {
  return (
    <div className={`note note--${note.severity}`}>
      <span className="note__glyph" aria-hidden="true">
        {GLYPH[note.severity]}
      </span>
      <span>{note.body}</span>
    </div>
  );
}

export function Panel({
  title,
  question,
  meta,
  basis,
  actions,
  children,
  readout,
  className = "",
}: {
  title: string;
  question?: string;
  meta?: PanelMeta;
  basis?: string;
  actions?: ReactNode;
  children: ReactNode;
  readout?: ReactNode;
  className?: string;
}) {
  const basisText = basis ?? meta?.basis;
  return (
    <section className={`panel ${className}`}>
      <header className="panel__head">
        <div className="panel__title">
          {title}
          {question ? <div className="panel__question">{question}</div> : null}
        </div>
        {actions}
      </header>
      {basisText ? <div className="panel__basis">{basisText}</div> : null}
      {children}
      {readout ? <div className="readout">{readout}</div> : null}
      {meta?.notes?.map((note, i) => <Note key={`${note.severity}-${i}`} note={note} />)}
    </section>
  );
}

export function SectionRule({ title, note }: { title: string; note?: string }) {
  return (
    <div className="section-rule">
      <h2>{title}</h2>
      {note ? <span className="section-rule__note">{note}</span> : null}
    </div>
  );
}

export function PageHead({
  eyebrow,
  title,
  lede,
}: {
  eyebrow: string;
  title: string;
  lede?: string;
}) {
  return (
    <header className="page__head">
      <div className="page__eyebrow">{eyebrow}</div>
      <h1 className="page__title">{title}</h1>
      {lede ? <p className="page__lede">{lede}</p> : null}
    </header>
  );
}

export function KpiTile({ kpi }: { kpi: Kpi }) {
  return (
    <div className={`panel kpi kpi--${kpi.tone}`}>
      <div className="kpi__label">{kpi.label}</div>
      <div className="kpi__value">
        {kpi.value_text}
        {kpi.unit ? <span className="kpi__unit">{kpi.unit}</span> : null}
      </div>
      <div className="row" style={{ gap: "var(--sp-2)" }}>
        {kpi.delta_text ? (
          <span
            className={`delta ${
              kpi.delta_is_good === null ? "" : kpi.delta_is_good ? "delta--good" : "delta--bad"
            }`}
          >
            {kpi.delta_direction === "up" ? "↑" : kpi.delta_direction === "down" ? "↓" : "→"}
            {kpi.delta_text}
          </span>
        ) : null}
        {kpi.sub_text ? <span className="kpi__sub">{kpi.sub_text}</span> : null}
      </div>
      {kpi.footnote ? <div className="kpi__foot">{kpi.footnote}</div> : null}
    </div>
  );
}

/** Categorical counts. Uses the ordinal ramp so one metric reads as one metric. */
export function BarList({
  items,
  showPct = false,
  colorMode = "ramp",
}: {
  items: CountItem[];
  showPct?: boolean;
  colorMode?: "ramp" | "accent" | "tone";
}) {
  const max = Math.max(1, ...items.map((i) => i.count));
  return (
    <div className="bars">
      {items.map((item, i) => {
        const fill =
          colorMode === "tone" && item.tone
            ? `var(--${item.tone})`
            : colorMode === "accent"
              ? "var(--accent)"
              : rampColor(items.length - 1 - i, items.length);
        return (
          <div className="bar" key={`${item.label}-${i}`}>
            <div className="bar__label" title={item.label}>
              {item.label}
            </div>
            <div className="bar__track">
              <div
                className="bar__fill"
                style={{ width: `${(item.count / max) * 100}%`, background: fill }}
              />
            </div>
            <div className="bar__value">
              {fmtInt(item.count)}
              {showPct && item.share_pct != null ? (
                <span className="bar__pct">{item.share_pct}%</span>
              ) : null}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function Callouts({ items }: { items: Callout[] }) {
  return (
    <div className="callouts">
      {items.map((c) => (
        <div className={`callout callout--${c.tone}`} key={c.code}>
          <div className="callout__label">{c.label}</div>
          <div className="callout__value">{c.value_text}</div>
          <div className="callout__body">{c.body}</div>
        </div>
      ))}
    </div>
  );
}

export function DataTable({
  columns,
  rows,
  numeric = [],
  onRowClick,
  selectedIndex,
}: {
  columns: string[];
  rows: (string | number | null | ReactNode)[][];
  numeric?: number[];
  onRowClick?: (index: number) => void;
  selectedIndex?: number;
}) {
  return (
    <div className="table-wrap">
      <table className="data">
        <thead>
          <tr>
            {columns.map((c, i) => (
              <th key={c} className={numeric.includes(i) ? "num" : undefined}>
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length}>
                <div className="empty">Nothing in this extract for the selected window.</div>
              </td>
            </tr>
          ) : (
            rows.map((row, ri) => (
              <tr
                key={ri}
                className={[
                  onRowClick ? "is-clickable" : "",
                  selectedIndex === ri ? "is-selected" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                onClick={onRowClick ? () => onRowClick(ri) : undefined}
              >
                {row.map((cell, ci) => (
                  <td key={ci} className={numeric.includes(ci) ? "num" : ci === 0 ? "strong" : undefined}>
                    {cell === null || cell === undefined ? "—" : cell}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

export function TableToggle({ label, children }: { label: string; children: ReactNode }) {
  return (
    <details className="tabler">
      <summary>{label}</summary>
      <div style={{ marginTop: "var(--sp-3)" }}>{children}</div>
    </details>
  );
}

export function Loading({ rows = 3 }: { rows?: number }) {
  return (
    <div className="stack" aria-busy="true" aria-live="polite">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skeleton" style={{ height: i === 0 ? 34 : 20 }} />
      ))}
    </div>
  );
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <div className="note note--critical">
      <span className="note__glyph" aria-hidden="true">
        !!
      </span>
      <span>{message}</span>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

/** Wraps the loading / error / empty triad so pages stay readable. */
export function Async<T>({
  query,
  children,
  skeletonRows,
}: {
  query: { isLoading: boolean; error: { message: string } | null; data: T | undefined };
  children: (data: T) => ReactNode;
  skeletonRows?: number;
}) {
  if (query.isLoading) return <Loading rows={skeletonRows} />;
  if (query.error) return <ErrorNote message={query.error.message} />;
  if (!query.data) return <Empty>No data.</Empty>;
  return <>{children(query.data)}</>;
}

export function SignalCard({
  glyph,
  name,
  volume,
  coverage,
  desc,
  to,
}: {
  glyph: string;
  name: string;
  volume: string;
  coverage: string;
  desc?: string;
  to: string;
}) {
  return (
    <Link className="signal" to={to}>
      <span className="signal__glyph" aria-hidden="true">
        {glyph}
      </span>
      <span className="signal__name">{name}</span>
      <span className="signal__vol">{volume}</span>
      <span className="signal__cov">{coverage}</span>
      {desc ? <span className="signal__desc">{desc}</span> : null}
    </Link>
  );
}
