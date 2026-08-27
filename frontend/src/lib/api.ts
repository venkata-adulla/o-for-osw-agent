/**
 * Single API surface for the dashboard.
 *
 * Every panel fetches through `usePanel`, which carries the provenance envelope
 * along with the payload -- so a panel physically cannot render a number without
 * having its basis and caveats in hand.
 */
import { useQuery, type UseQueryResult } from "@tanstack/react-query";

export const API_BASE: string =
  (import.meta as { env?: Record<string, string> }).env?.VITE_API_BASE ?? "http://localhost:8010";

export type Severity = "caveat" | "critical" | "thin" | "info";

export interface PanelNote {
  severity: Severity;
  body: string;
}

export interface PanelMeta {
  panel_id: string;
  population: string;
  basis: string;
  notes: PanelNote[];
}

/** Anything the API returns for a panel. `meta` is present on business panels. */
export type WithMeta<T> = T & { meta?: PanelMeta };

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function apiGet<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  // `new URL("/api/...")` throws without a base -- it's not a valid absolute
  // URL on its own. Passing the page's own origin as the base makes a
  // relative API_BASE (the default: same-origin, proxied by nginx) resolve
  // correctly; an already-absolute path or API_BASE overrides it as normal,
  // since a URL string with a scheme ignores the base argument.
  const url = new URL(path.startsWith("http") ? path : `${API_BASE}${path}`, window.location.origin);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== "") url.searchParams.set(key, String(value));
    }
  }
  const res = await fetch(url.toString(), { headers: { Accept: "application/json" } });
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body?.detail) detail = body.detail;
    } catch {
      /* keep the status-based message */
    }
    throw new ApiError(detail, res.status);
  }
  return (await res.json()) as T;
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new ApiError(`Request failed (${res.status})`, res.status);
  return (await res.json()) as T;
}

/** Panel-scoped query. The key includes params so incident state re-fetches. */
export function usePanel<T>(
  path: string,
  params?: Record<string, string | number | undefined>,
  options?: { enabled?: boolean; refetchInterval?: number },
): UseQueryResult<WithMeta<T>, ApiError> {
  return useQuery<WithMeta<T>, ApiError>({
    queryKey: [path, params ?? {}],
    queryFn: () => apiGet<WithMeta<T>>(path, params),
    staleTime: 30_000,
    retry: 1,
    ...options,
  });
}

/* ------------------------------------------------------------------------- */
/* Shared response shapes                                                    */
/* ------------------------------------------------------------------------- */

export interface Kpi {
  code: string;
  label: string;
  value_text: string;
  unit: string;
  sub_text: string;
  delta_text: string | null;
  delta_direction: "up" | "down" | "flat" | null;
  delta_is_good: boolean | null;
  tone: "neutral" | "good" | "warning" | "serious" | "critical";
  panel_id: string;
  footnote: string;
}

export interface JourneyStage {
  stage_no: number;
  code: string;
  label: string;
  reached: number;
  pct_of_sample: number | null;
  lost_here: number | null;
  why: string;
  basis_change: boolean;
}

export interface Callout {
  code: string;
  label: string;
  value_text: string;
  body: string;
  tone: "neutral" | "good" | "warning" | "critical";
}

export interface CountItem {
  label: string;
  count: number;
  share_pct?: number | null;
  tone?: string | null;
}

export interface TraceListItem {
  trace_id: string;
  label: string;
  workflow: string | null;
  outcome: string;
  duration_ms: number;
  started_at: string;
  conversation_id: string | null;
  ticket_ref: string | null;
}

export interface SpanRow {
  span_id: string;
  service_name: string;
  display_name: string;
  operation: string;
  start_offset_ms: number;
  duration_ms: number;
  status: string;
  depth: number;
  is_root: boolean;
}

export interface LogRecord {
  id: number;
  observed_at: string;
  severity_text: "INFO" | "WARN" | "ERROR" | "DEBUG" | "TRACE" | "FATAL";
  service_name: string;
  event_name: string;
  body: string;
  trace_id: string | null;
  span_id: string | null;
  error_type: string | null;
  attributes?: Record<string, unknown>;
}

/* ------------------------------------------------------------------------- */
/* Formatting helpers                                                        */
/* ------------------------------------------------------------------------- */

export const fmtInt = (n: number | null | undefined): string =>
  n === null || n === undefined ? "--" : n.toLocaleString("en-GB");

export function fmtDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(2)}s`;
  const mins = Math.floor(ms / 60_000);
  return `${mins}m ${Math.round((ms % 60_000) / 1000)}s`;
}

export function fmtTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString("en-GB", { hour12: false });
}

export function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

/**
 * A raw "X seconds ago" is unreadable once X climbs into the tens of
 * thousands (177539 seconds is 2 days, and nobody reads it as that at a
 * glance). Steps up through seconds, minutes, hours and days -- whichever
 * unit keeps the number small -- the same relative-time approach the top
 * bar's freshness clock already uses for ETL runs.
 */
export function fmtAgoSeconds(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return "—";
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s}s ago`;
  const mins = Math.round(s / 60);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}

/**
 * A display-safe short id. A blind `.slice(0, 8)` looks fine on the 8-char
 * reference trace ids, but this app also holds 10-char generated ids
 * (`bg00000000`, `bg00000001`, ...) and 32-char derived ids (`derived-<24 hex
 * session id>`) -- an 8-char prefix makes two different traces render
 * identically. Anything already at or under `max` is shown whole; anything
 * longer keeps a head and a tail (with a distinguishing suffix) instead of
 * just a head, so collisions across the ids this app actually uses are far
 * less likely.
 */
export function shortId(id: string, max = 12): string {
  if (id.length <= max) return id;
  return `${id.slice(0, max - 5)}…${id.slice(-4)}`;
}

/** Ordinal ramp for a value's position in a series -- var(--o1)..var(--o5). */
export function rampColor(index: number, total: number): string {
  const step = Math.min(5, Math.max(1, Math.round(((index + 1) / Math.max(1, total)) * 5)));
  return `var(--o${step})`;
}

export const SERIES_COLORS = [
  "var(--s1)",
  "var(--s2)",
  "var(--s3)",
  "var(--s4)",
  "var(--s5)",
  "var(--s6)",
] as const;
