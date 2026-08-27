/**
 * Service health banner for the command centre.
 *
 * The incident state is held server-side (`/api/incident/simulate`) so every
 * page agrees; this component only reads it.
 */
import { fmtAgoSeconds, usePanel } from "../lib/api";
import { Async } from "./primitives";

export interface HealthIncident {
  code: string;
  title: string;
  detail: string;
  severity: string;
  started_at: string | null;
}

export interface HealthResponse {
  state: "healthy" | "incident";
  headline: string;
  detail: string;
  tone: string;
  services_reporting: number;
  services_total: number;
  last_signal_seconds: number | null;
  incident: HealthIncident | null;
}

function startedAgo(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const started = Date.parse(iso);
  if (Number.isNaN(started)) return null;
  const mins = Math.max(0, Math.round((Date.now() - started) / 60_000));
  if (mins < 1) return "started just now";
  return `started ${mins} minute${mins === 1 ? "" : "s"} ago`;
}

export default function HealthBanner() {
  const query = usePanel<HealthResponse>("/api/overview/health", undefined, {
    refetchInterval: 30_000,
  });

  return (
    <Async query={query} skeletonRows={1}>
      {(data) => {
        const isIncident = data.state === "incident";
        const incident = data.incident;
        const ago = startedAgo(incident?.started_at);
        return (
          <div
            className={`banner ${isIncident ? "banner--critical" : "banner--good"}`}
            role="status"
            aria-live="polite"
          >
            <span className="banner__mark" aria-hidden="true">
              {isIncident ? "!" : "✓"}
            </span>
            <div>
              <div className="banner__title">
                {isIncident && incident ? incident.title : data.headline}
              </div>
              <div className="banner__detail">
                {isIncident && incident ? incident.detail : data.detail}
                {ago && isIncident ? ` · ${ago}` : null}
              </div>
              <div
                className="banner__detail mono"
                title={
                  data.last_signal_seconds === null || data.last_signal_seconds === undefined
                    ? undefined
                    : `${data.last_signal_seconds} seconds ago`
                }
              >
                {data.services_reporting} of {data.services_total} services reporting · last
                signal {fmtAgoSeconds(data.last_signal_seconds)}
              </div>
            </div>
            <span className="topbar__spacer" />
            {isIncident ? (
              <span className="banner__sev">{incident?.severity ?? "SEV-2"}</span>
            ) : (
              <span className="pill pill--live">Healthy</span>
            )}
          </div>
        );
      }}
    </Async>
  );
}
