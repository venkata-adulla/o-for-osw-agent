/**
 * Hop chain -- the ordered services one request passed through.
 *
 * Every hop is a real button: the chain is a selector, not a picture, so the
 * HTTP headers and snapshot below it can follow the hop the reader picked.
 */
import { Fragment } from "react";

export interface HopChainItem {
  hop_no: number;
  /** Service display name. */
  title: string;
  /** Operation performed at this hop. */
  subtitle?: string;
  /** Role, duration or field count -- whatever this chain is measuring. */
  meta?: string;
  is_degraded?: boolean;
}

export default function HopChain({
  hops,
  selectedHopNo,
  onSelect,
  label = "Request hops",
}: {
  hops: HopChainItem[];
  selectedHopNo?: number | null;
  onSelect: (hopNo: number) => void;
  label?: string;
}) {
  return (
    <div className="hops" role="group" aria-label={label}>
      {hops.map((hop, i) => {
        const isSelected = selectedHopNo === hop.hop_no;
        return (
          <Fragment key={hop.hop_no}>
            {i > 0 ? (
              <span className="hop__arrow" aria-hidden="true">
                →
              </span>
            ) : null}
            <button
              type="button"
              className={`hop${isSelected ? " is-selected" : ""}${hop.is_degraded ? " is-degraded" : ""}`}
              style={{ textAlign: "left" }}
              aria-pressed={isSelected}
              onClick={() => onSelect(hop.hop_no)}
            >
              <div className="hop__no">HOP {hop.hop_no}</div>
              <div className="hop__service">{hop.title}</div>
              {hop.subtitle ? <div className="hop__op">{hop.subtitle}</div> : null}
              {hop.meta ? <div className="hop__dur">{hop.meta}</div> : null}
            </button>
          </Fragment>
        );
      })}
    </div>
  );
}
