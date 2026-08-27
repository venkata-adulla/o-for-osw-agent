/**
 * Histogram of one instrument's buckets.
 *
 * One metric, many buckets -- so the ordinal ramp is used in bucket order rather
 * than the categorical series. Counts are monospace and tabular.
 */
import { fmtInt, rampColor } from "../lib/api";

export interface HistogramBucket {
  bucket_label: string;
  count: number;
}

export default function Histogram({
  buckets,
  total,
}: {
  buckets: HistogramBucket[];
  /** Denominator for the share column. Falls back to the bucket sum. */
  total?: number;
}) {
  const max = Math.max(1, ...buckets.map((b) => b.count));
  const sum = total ?? buckets.reduce((acc, b) => acc + b.count, 0);

  return (
    <div className="bars">
      {buckets.map((bucket, i) => (
        <div className="bar" key={`${bucket.bucket_label}-${i}`}>
          <div className="bar__label mono" title={bucket.bucket_label}>
            {bucket.bucket_label}
          </div>
          <div className="bar__track">
            <div
              className="bar__fill"
              style={{
                width: `${(bucket.count / max) * 100}%`,
                background: rampColor(i, buckets.length),
              }}
            />
          </div>
          <div className="bar__value">
            {fmtInt(bucket.count)}
            {sum > 0 ? (
              <span className="bar__pct">{((bucket.count / sum) * 100).toFixed(1)}%</span>
            ) : null}
          </div>
        </div>
      ))}
    </div>
  );
}
