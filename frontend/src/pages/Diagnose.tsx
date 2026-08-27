/**
 * Diagnose -- the runbook.
 *
 * The left column is what the business sees. The right column is what an engineer
 * does about it, and every step is a real link to the page that performs it. Below
 * that, steps 2-4 aren't just links out -- they're the actual trace, log and
 * profile for whatever is happening right now, so reading the investigation and
 * seeing the evidence never requires leaving this page. Each panel still keeps a
 * link to its full page, for whoever wants to go further than the worked example.
 */
import { Link } from "react-router-dom";
import Waterfall from "../components/Waterfall";
import { Async, DataTable, Empty, PageHead, Panel, SectionRule } from "../components/primitives";
import { fmtDuration, fmtInt, fmtTime, usePanel, type SpanRow } from "../lib/api";

interface DiagnoseStep {
  step_no: number;
  title: string;
  body: string;
  route?: string;
}

interface IncidentInfo {
  code: string;
  title: string;
  detail: string;
  severity: string;
  started_at?: string | null;
}

interface DegradedService {
  hop_no: number;
  service_name: string;
  display_name: string;
  operation: string;
  healthy_ms: number;
  incident_ms: number;
}

interface EvidenceTrace {
  trace_id: string;
  label: string;
  status: string;
  duration_ms: number;
  span_count: number;
  axis_ticks_ms: number[];
  spans: SpanRow[];
  conversation_id?: string | null;
}

interface EvidenceLog {
  id: number;
  observed_at: string;
  severity_text: string;
  service_name: string;
  event_name: string;
  body: string;
}

interface EvidenceProfile {
  service_name: string | null;
  display_name: string | null;
  profile_type: string | null;
  finding: string;
  hot_functions: { function_name: string; pct: number; total_ms: number }[];
}

interface Evidence {
  trace: EvidenceTrace | null;
  logs: EvidenceLog[];
  profile: EvidenceProfile;
}

interface DiagnoseResponse {
  symptom: DiagnoseStep[];
  diagnosis: DiagnoseStep[];
  summary: string;
  state: "healthy" | "incident";
  incident: IncidentInfo | null;
  degraded_services: DegradedService[];
  evidence: Evidence;
}

/** The five clicks, in order, when the API does not name a route itself. */
const ROUTE_FALLBACK = ["/", "/traces", "/logs", "/profiles", "/"];

const ACTION_LABEL: Record<string, string> = {
  "/": "Open the command centre",
  "/traces": "Open the traces",
  "/logs": "Open the logs",
  "/profiles": "Open the profiles",
  "/metrics": "Open the metrics",
  "/baggage": "Open the baggage audit",
  "/journey": "Open the guest journey",
};

export default function Diagnose() {
  const diagnose = usePanel<DiagnoseResponse>("/api/diagnose");

  return (
    <>
      <PageHead
        eyebrow="Trust & scale · Diagnose"
        title="From symptom to code"
        lede="When something breaks, know why in minutes — not hours or days. Each conversation is tied to its traces and spans, so a business symptom leads straight to the technical root cause."
      />

      <SectionRule title="The investigation" note="Symptom on the left · evidence on the right" />

      <div className="grid grid--split">
        <Panel
          title="The symptom — what the business sees"
          question="Nobody reports a p95. They report that guests are not getting their paperwork."
        >
          <Async query={diagnose} skeletonRows={4}>
            {(d) => (
              <div className="steps">
                {d.symptom.map((step) => (
                  <div className="step" key={step.step_no}>
                    <span className="step__no">{step.step_no}</span>
                    <div>
                      <div className="step__title">{step.title}</div>
                      <div className="step__body">{step.body}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Async>
        </Panel>

        <Panel
          title="The diagnosis — five clicks, one tool"
          question="Every step below is a link. This is the runbook, not a diagram of one."
        >
          <Async query={diagnose} skeletonRows={5}>
            {(d) => (
              <div className="steps">
                {d.diagnosis.map((step, i) => {
                  const route =
                    step.route && step.route !== ""
                      ? step.route
                      : (ROUTE_FALLBACK[i] ?? "/");
                  return (
                    <div className="step" key={step.step_no}>
                      <span className="step__no">{step.step_no}</span>
                      <div>
                        <div className="step__title">{step.title}</div>
                        <div className="step__body">{step.body}</div>
                        <Link className="btn" to={route}>
                          {ACTION_LABEL[route] ?? "Open"} →
                        </Link>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </Async>
        </Panel>
      </div>

      <SectionRule title="Live evidence" note="not a mock — the same signals a real investigation would open" />

      <Panel
        title={
          diagnose.data?.state === "incident"
            ? (diagnose.data?.incident?.title ?? "Active incident")
            : "All systems healthy"
        }
        question="Step 1 — alerts trigger. This is what the platform is actually seeing right now."
        actions={
          diagnose.data ? (
            <span className={`pill ${diagnose.data.state === "incident" ? "" : "pill--live"}`}>
              {diagnose.data.state === "incident"
                ? (diagnose.data.incident?.severity ?? "SEV-2")
                : "Live"}
            </span>
          ) : undefined
        }
      >
        <Async query={diagnose} skeletonRows={2}>
          {(d) =>
            d.state === "incident" && d.incident ? (
              <div className="stack">
                <div className="readout">
                  <b>{d.incident.title}</b> — {d.incident.detail}
                </div>
                {d.degraded_services.length ? (
                  <DataTable
                    columns={["Service", "Operation", "Healthy", "Under incident"]}
                    rows={d.degraded_services.map((s) => [
                      s.display_name || s.service_name,
                      s.operation,
                      fmtDuration(s.healthy_ms),
                      fmtDuration(s.incident_ms),
                    ])}
                  />
                ) : null}
              </div>
            ) : (
              <p className="readout">
                No active incident. The trace, log and profile below are a live, healthy
                example — this is what step 5, "fix and verify", looks like once it's done.
              </p>
            )
          }
        </Async>
      </Panel>

      <div className="grid grid--split">
        <Panel
          title="Open the trace"
          question="Step 2 — the guest's exact request, timed hop by hop across every service."
          actions={
            diagnose.data?.evidence.trace ? (
              <Link className="btn" to={`/traces/${diagnose.data.evidence.trace.trace_id}`}>
                ⑂ Open full trace →
              </Link>
            ) : undefined
          }
        >
          <Async query={diagnose} skeletonRows={4}>
            {(d) =>
              d.evidence.trace ? (
                <div className="stack">
                  <div className="panel__basis">
                    {d.evidence.trace.label} · {fmtDuration(d.evidence.trace.duration_ms)} ·{" "}
                    {d.evidence.trace.status}
                  </div>
                  <Waterfall
                    spans={d.evidence.trace.spans}
                    axisTicks={d.evidence.trace.axis_ticks_ms}
                    rootDurationMs={d.evidence.trace.duration_ms}
                  />
                </div>
              ) : (
                <Empty>No trace held to show yet.</Empty>
              )
            }
          </Async>
        </Panel>

        <Panel
          title="Read the log"
          question="Step 3 — the error event carries its trace context, one click from the waterfall."
          actions={
            diagnose.data?.evidence.trace ? (
              <Link className="btn" to={`/logs?trace_id=${diagnose.data.evidence.trace.trace_id}`}>
                ≡ Open full logs →
              </Link>
            ) : undefined
          }
        >
          <Async query={diagnose} skeletonRows={4}>
            {(d) =>
              d.evidence.logs.length ? (
                <DataTable
                  columns={["Time", "Level", "Service / event", "Message"]}
                  rows={d.evidence.logs.map((r) => [
                    <span className="mono" key={`t-${r.id}`}>
                      {fmtTime(r.observed_at)}
                    </span>,
                    <span className={`sev sev--${r.severity_text}`} key={`s-${r.id}`}>
                      {r.severity_text}
                    </span>,
                    <span key={`e-${r.id}`}>
                      <span className="span-row__service">{r.service_name}</span>
                      <span className="span-row__op">{r.event_name}</span>
                    </span>,
                    r.body,
                  ])}
                />
              ) : (
                <Empty>No log records held for this trace.</Empty>
              )
            }
          </Async>
        </Panel>
      </div>

      <Panel
        title="Profile the code"
        question="Step 4 — flame graphs point to the exact function consuming the time."
        actions={
          <Link className="btn" to="/profiles">
            ▥ Open full profile →
          </Link>
        }
      >
        <Async query={diagnose} skeletonRows={3}>
          {(d) => (
            <div className="stack">
              <div className="panel__basis">
                {d.evidence.profile.display_name ?? d.evidence.profile.service_name ?? "—"} ·{" "}
                {d.evidence.profile.profile_type ?? "cpu"} samples
              </div>
              {d.evidence.profile.hot_functions.length ? (
                <DataTable
                  columns={["Function", "% of samples", "Total"]}
                  numeric={[1, 2]}
                  rows={d.evidence.profile.hot_functions.map((f) => [
                    <span className="mono" key={f.function_name}>
                      {f.function_name}
                    </span>,
                    `${f.pct}%`,
                    `${fmtInt(f.total_ms)} ms`,
                  ])}
                />
              ) : (
                <Empty>No profile held for this service.</Empty>
              )}
              {d.evidence.profile.finding ? (
                <div className="callouts">
                  <div className="callout callout--warning">
                    <div className="callout__label">Finding</div>
                    <div className="callout__body">{d.evidence.profile.finding}</div>
                  </div>
                </div>
              ) : null}
            </div>
          )}
        </Async>
      </Panel>
    </>
  );
}
