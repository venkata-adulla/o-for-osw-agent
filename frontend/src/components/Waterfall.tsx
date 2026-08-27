/**
 * Trace waterfall.
 *
 * One row per span. The bar's left offset and width are the span's real position
 * inside the root span's duration, so the picture is the trace's own arithmetic --
 * never a decoration. Durations are right-aligned monospace so a column of spans
 * reads as a column of numbers.
 */
import { fmtDuration, type SpanRow } from "../lib/api";

export default function Waterfall({
  spans,
  axisTicks,
  rootDurationMs,
  slowRatio = 0.4,
}: {
  spans: SpanRow[];
  axisTicks: number[];
  /** Falls back to the root span, then to the furthest span end. */
  rootDurationMs?: number;
  /** A non-root span taking at least this share of the trace is marked slow. */
  slowRatio?: number;
}) {
  const total = Math.max(
    1,
    rootDurationMs ??
      spans.find((s) => s.is_root)?.duration_ms ??
      Math.max(1, ...spans.map((s) => s.start_offset_ms + s.duration_ms)),
  );

  return (
    <div className="waterfall">
      {axisTicks.length > 0 ? (
        <div className="waterfall__axis" aria-hidden="true">
          {axisTicks.map((tick, i) => (
            <span key={`${tick}-${i}`}>{tick === 0 ? "0ms" : fmtDuration(tick)}</span>
          ))}
        </div>
      ) : null}

      {spans.map((span) => {
        const left = Math.min(99, (span.start_offset_ms / total) * 100);
        const width = Math.max(0.6, Math.min(100 - left, (span.duration_ms / total) * 100));
        const variant = span.is_root
          ? "is-root"
          : span.status === "ERROR"
            ? "is-error"
            : span.duration_ms / total >= slowRatio
              ? "is-slow"
              : "";
        return (
          <div className="span-row" key={span.span_id}>
            <div className="span-row__name" style={{ paddingLeft: span.depth * 14 }}>
              <div className="span-row__service">{span.display_name || span.service_name}</div>
              <div className="span-row__op" title={span.operation}>
                {span.operation}
              </div>
            </div>
            <div className="span-row__track">
              <div
                className={`span-row__bar ${variant}`}
                style={{ left: `${left}%`, width: `${width}%` }}
                title={`${span.service_name} · ${span.operation} · ${fmtDuration(
                  span.duration_ms,
                )} · starts +${fmtDuration(span.start_offset_ms)} · ${span.status}`}
              />
            </div>
            <div className="span-row__dur">{fmtDuration(span.duration_ms)}</div>
          </div>
        );
      })}
    </div>
  );
}
