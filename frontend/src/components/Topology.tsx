/**
 * Live topology — the ordered business request path, plus the telemetry path.
 *
 * The two paths are drawn separately on purpose: the guest's request runs
 * through the services, and every service exports its signals sideways to the
 * Collector. Mixing them is what makes people believe observability sits inside
 * the request path.
 */
import { Fragment } from "react";
import { fmtDuration, usePanel } from "../lib/api";
import { Async, Panel } from "./primitives";

export interface TopologyHop {
  hop_no: number;
  display_name: string;
  operation: string;
  duration_ms: number | null;
  is_origin: boolean;
  tone: string | null;
}

export interface TopologyResponse {
  request_path: TopologyHop[];
  telemetry_path: {
    title: string;
    detail: string;
    collector: { display_name: string; detail: string; duration_ms: number | null } | null;
  } | null;
  reporting_text: string;
}

const dur = (ms: number | null | undefined): string =>
  ms === null || ms === undefined ? "—" : fmtDuration(ms);

export default function Topology() {
  const query = usePanel<TopologyResponse>("/api/overview/topology");

  return (
    <Panel
      title="Live topology · selected return request"
      question="Business request path — the same ordered hops shown on the Baggage page."
      meta={query.data?.meta}
      actions={
        query.data?.reporting_text ? (
          <span className="pill">{query.data.reporting_text}</span>
        ) : undefined
      }
    >
      <Async query={query} skeletonRows={2}>
        {(data) => {
          const hops = data.request_path ?? [];
          const telemetry = data.telemetry_path;
          return (
            <div className="stack">
              <div className="hops">
                {hops.map((hop, i) => (
                  <Fragment key={hop.hop_no}>
                    {i > 0 ? (
                      <span className="hop__arrow" aria-hidden="true">
                        →
                      </span>
                    ) : null}
                    <div className={`hop ${hop.tone === "critical" ? "is-degraded" : ""}`}>
                      <div className="hop__no">HOP {hop.hop_no}</div>
                      <div className="hop__service">{hop.display_name}</div>
                      <div className="hop__op">{hop.operation}</div>
                      <div className="hop__dur">{hop.is_origin ? "origin" : dur(hop.duration_ms)}</div>
                    </div>
                  </Fragment>
                ))}
              </div>

              {telemetry ? (
                <div className="panel panel--sunk">
                  <div className="panel__basis">Telemetry path · separate from the request</div>
                  <div className="hops">
                    <div className="hop">
                      <div className="hop__no">EVERY SERVICE</div>
                      <div className="hop__service">{telemetry.title}</div>
                      <div className="hop__op">{telemetry.detail}</div>
                    </div>
                    {telemetry.collector ? (
                      <>
                        <span className="hop__arrow" aria-hidden="true">
                          →
                        </span>
                        <div className="hop">
                          <div className="hop__no">COLLECTOR</div>
                          <div className="hop__service">{telemetry.collector.display_name}</div>
                          <div className="hop__op">{telemetry.collector.detail}</div>
                          <div className="hop__dur">{dur(telemetry.collector.duration_ms)}</div>
                        </div>
                      </>
                    ) : null}
                  </div>
                </div>
              ) : null}
            </div>
          );
        }}
      </Async>
    </Panel>
  );
}
