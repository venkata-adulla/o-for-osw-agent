/**
 * Products & services — which flow the guest needs, and what is really
 * happening inside the returns flow.
 *
 * The flows that produced nothing are listed explicitly: absence of demand on
 * this screen is a scope finding about the bot, not a finding about guests.
 */
import { fmtInt, usePanel, type CountItem } from "../lib/api";
import {
  Async,
  BarList,
  DataTable,
  Note,
  PageHead,
  Panel,
  SectionRule,
  TableToggle,
} from "../components/primitives";

type UnusedFlow = string | { label?: string; flow?: string };

interface InquiryTypesResponse {
  basis: string;
  items: { inquiry_type: string; count: number }[];
  unused_flows: UnusedFlow[];
}

interface ReturnsResponse {
  total: number;
  order_route: { label: string; count: number }[];
  return_reason: { label: string; count: number }[];
}

const flowLabel = (flow: UnusedFlow): string =>
  typeof flow === "string" ? flow : (flow.label ?? flow.flow ?? "—");

const dash = (n: number | null | undefined): string => (n === null || n === undefined ? "—" : fmtInt(n));

const sum = (items: { count: number }[]): number => items.reduce((acc, i) => acc + i.count, 0);

export default function Products() {
  const inquiries = usePanel<InquiryTypesResponse>("/api/products/inquiry-types");
  const returns = usePanel<ReturnsResponse>("/api/products/returns");

  return (
    <>
      <PageHead
        eyebrow="Business view"
        title="Products & services"
        lede="Which flow does the guest need? One flow per ticket — and one flow does almost all of the work."
      />

      <SectionRule
        title="What guests come to us about"
        note="one flow per ticket · 25 of 100 conversations carry none"
      />
      <Panel
        title="What guests come to us about"
        question="Which flow does the guest need?"
        meta={inquiries.data?.meta}
        basis={inquiries.data?.basis}
      >
        <Async query={inquiries} skeletonRows={5}>
          {(data) => {
            const items: CountItem[] = (data.items ?? []).map((i) => ({
              label: i.inquiry_type,
              count: i.count,
            }));
            const unused = data.unused_flows ?? [];
            const all = data.items ?? [];
            const top = all.find((i) => /return/i.test(i.inquiry_type)) ?? all[0];
            return (
              <div className="stack">
                <BarList items={items} />

                <div className="readout">
                  The bot is a returns machine.{" "}
                  <b>
                    {top ? `${fmtInt(top.count)} of ${fmtInt(sum(data.items ?? []))} tickets` : "—"}{" "}
                    are returns
                  </b>
                  . Everything else the form offers produced nothing at all this period:
                </div>

                <div className="row">
                  {unused.length === 0 ? (
                    <span className="tag">every flow on the form produced at least one ticket</span>
                  ) : (
                    unused.map((flow, i) => (
                      <span className="tag" key={`${flowLabel(flow)}-${i}`}>
                        {flowLabel(flow)} · 0
                      </span>
                    ))
                  )}
                </div>

                <TableToggle label="Show the flows as a table">
                  <DataTable
                    columns={["Flow", "Tickets"]}
                    numeric={[1]}
                    rows={[
                      ...(data.items ?? []).map((i) => [i.inquiry_type, fmtInt(i.count)]),
                      ...unused.map((flow) => [flowLabel(flow), fmtInt(0)]),
                    ]}
                  />
                </TableToggle>
              </div>
            );
          }}
        </Async>
      </Panel>

      <SectionRule title="Inside the returns flow" note="both breakdowns sum to the same total" />
      <Panel
        title="Inside the returns flow"
        question="Ordered how, and sent back why?"
        meta={returns.data?.meta}
      >
        <Async query={returns} skeletonRows={5}>
          {(data) => {
            const route = data.order_route ?? [];
            const reason = data.return_reason ?? [];
            const routeSum = sum(route);
            const reasonSum = sum(reason);
            const balanced = routeSum === data.total && reasonSum === data.total;
            return (
              <div className="stack">
                <div className="grid grid--split">
                  <div className="panel panel--sunk">
                    <div className="panel__basis">
                      How it was ordered · Σ {dash(routeSum)} of {dash(data.total)}
                    </div>
                    <BarList items={route} colorMode="accent" />
                  </div>
                  <div className="panel panel--sunk">
                    <div className="panel__basis">
                      Why it is being returned · Σ {dash(reasonSum)} of {dash(data.total)}
                    </div>
                    <BarList items={reason} />
                  </div>
                </div>

                {balanced ? (
                  <div className="readout">
                    Every return ticket carries exactly three tags: the return itself, one order
                    route, one reason. Both breakdowns sum to <b>{fmtInt(data.total)}</b> with
                    nothing missing — the cleanest taxonomy on the whole screen.
                  </div>
                ) : (
                  <Note
                    note={{
                      severity: "caveat",
                      body: `The two breakdowns do not both sum to ${fmtInt(data.total)} (${fmtInt(
                        routeSum,
                      )} and ${fmtInt(reasonSum)}), so a tag is missing from this extract. Read the split, not the total.`,
                    }}
                  />
                )}
              </div>
            );
          }}
        </Async>
      </Panel>
    </>
  );
}
