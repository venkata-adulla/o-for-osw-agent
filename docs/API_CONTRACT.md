# O for OSW — API contract

Base URL: `http://localhost:8010` (container `backend:8000`). All routes are `GET`
unless stated. All responses are JSON objects (never bare arrays) so fields can be
added without breaking clients.

Common query params, accepted by every business route:
`bot_id` (default `marina`), `date_from`, `date_to` (ISO dates), `state`
(`healthy` | `incident`, telemetry routes only — drives the incident simulation).

Every panel payload carries a `meta` envelope so the UI can render provenance
without a second call:

```json
"meta": {
  "panel_id": "P-09",
  "population": "B",
  "basis": "28 bot-raised tickets, 17-19 Aug",
  "notes": [{"severity": "caveat", "body": "Raw counts. No sailing or passenger divisor yet."}]
}
```

`severity` is one of `caveat` (!), `critical` (!!), `thin` (~), `info`.

---

## System

| Route | Returns |
|---|---|
| `/health` | `{status, db, version}` |
| `/api/meta/bots` | `{items:[{bot_id, bot_name, environment, instrumented, data_held, note}]}` |
| `/api/meta/populations` | `{items:[{code, letter, label, source_system, window_from, window_to, row_count, is_capped, cap_rows, more_available, caveat, figures:[{value_text,label}]}]}` |
| `/api/meta/coverage` | `{items:[{code,label,numerator,denominator,pct,basis}]}` |
| `/api/meta/freshness` | `{updated_at, next_run_at, sources:[{source,status,rows_loaded,finished_at}]}` |

## Command centre — `/api/overview`

| Route | Returns |
|---|---|
| `/api/overview/kpis?view=business\|technical&state=` | `{view, state, items:[{code,label,value_text,unit,sub_text,delta_text,delta_direction,delta_is_good,tone,panel_id,footnote}]}` |
| `/api/overview/health?state=` | `{state, headline, detail, tone, services_reporting, services_total, last_signal_seconds, incident:{code,title,detail,severity,started_at}\|null}` |
| `/api/overview/topology?state=` | `{request_path:[{hop_no,display_name,operation,duration_ms,is_origin,tone}], telemetry_path:{title,detail,collector:{display_name,detail,duration_ms}}, reporting_text}` |
| `/api/overview/signals` | `{items:[{signal,glyph,volume_text,coverage_text,description,route}]}` |
| `/api/overview/journey?source=telemetry\|review` | `{source, basis, stages:[{stage_no,code,label,reached,pct_of_sample,lost_here,why,basis_change}], callouts:[{code,label,value_text,body,tone}]}` |
| `/api/overview/operating-model` | `{pillars:[...], signals:[...], journey_stages:[...]}` — the four-pillar slide |

## Guest journey — `/api/journey`

| Route | Returns |
|---|---|
| `/api/journey/chain` | funnel rows + callouts + table rows (`stage, reached, of_sample, lost_here, why`) |
| `/api/journey/quit-reasons` | `{items:[{code,label,count,category}], totals:{never_spoke,paperwork,mid_flow}}` |
| `/api/journey/outcomes` | `{reviewed, made_request, never_spoke, got_ticket, no_ticket, tickets, duplicates, by_day:[{day,reviewed,ticket_created,no_ticket,was_read}]}` |
| `/api/journey/enrichment` | `{outcomes:[{code,label,count,meaning}], failures:[{code,label,count,is_intake}], automation_gaps:[{change,effect}]}` |
| `/api/journey/duplicates` | `{sessions,extra_tickets,exact_repeats,pairs:[{ticket_a,ticket_b,is_exact_repeat,evidence}],cause}` |
| `/api/journey/durations` | `{fastest_text,typical_text,longest_text,basis}` |

## Tickets — `/api/tickets`

| Route | Returns |
|---|---|
| `/api/tickets/summary` | `{total,bot_raised,requests_raised,requests_pct,still_waiting:{untouched,open,solved,note}}` |
| `/api/tickets/status` | `{items:[{status,count,tone}]}` |
| `/api/tickets/activity` | `{items:[{day,conversations,bot_tickets,in_kore_extract,in_zendesk_extract}]}` |
| `/api/tickets/correlation` | `{conversations,carry_ticket_number,backend_step_done,note}` |
| `/api/tickets/backend-failures` | `{items:[{tag,label,ticket_count,stage}],affected,total}` |
| `/api/tickets/recent?limit=50` | `{items:[{ticket_id,created_at,status,priority,cruise_line,ship_name,inquiry_type,sentiment,is_bot_raised}]}` |

## Cruise lines — `/api/lines`

| Route | Returns |
|---|---|
| `/api/lines/contacts` | `{named,total,items:[{cruise_line,ticket_count,share_pct}]}` |
| `/api/lines/ships` | `{items:[{ship_name,cruise_line,ticket_count}]}` |
| `/api/lines/mood` | `{scored,total,unhappy,unhappy_pct,items:[{sentiment,count,tone}]}` |

## Products — `/api/products`

| Route | Returns |
|---|---|
| `/api/products/inquiry-types` | `{basis,items:[{inquiry_type,count}],unused_flows:[...]}` |
| `/api/products/returns` | `{total,order_route:[{label,count}],return_reason:[{label,count}]}` |

## Customers — `/api/customers`

| Route | Returns |
|---|---|
| `/api/customers/repeat` | `{guests,repeat_guests,repeat_pct,their_tickets,raised_two_plus,chasing_older,method,top_repeat_guests:[{requester_id,ticket_count,ticket_ids,chasing_older,last_ticket_at}]}` |

## Conversations — `/api/conversations`

| Route | Returns |
|---|---|
| `/api/conversations?limit=&offset=&channel=&containment_type=&q=` | `{items:[...],total,limit,offset}` |
| `/api/conversations/{session_id}` | conversation + `messages:[{turn_no,direction,body,task_name,created_at,is_template}]` + `trace_ids:[...]` |

## Telemetry — traces

| Route | Returns |
|---|---|
| `/api/traces?limit=&workflow=&outcome=` | `{items:[{trace_id,label,workflow,outcome,duration_ms,started_at,conversation_id,ticket_ref}],coverage_pct}` |
| `/api/traces/model` | the conversation→trace→span explainer rows |
| `/api/traces/conversations/{conversation_id}` | `{conversation_id,guest_ref,channel,started_at,status,summary,trace_count,ticket_count,traces:[...]}` |
| `/api/traces/{trace_id}` | `{trace_id,label,status,duration_ms,span_count,axis_ticks_ms:[...],spans:[{span_id,service_name,display_name,operation,start_offset_ms,duration_ms,status,depth,is_root}],attributes:{semconv:[{key,value}],business:[{key,value}]}}` |

## Telemetry — metrics

| Route | Returns |
|---|---|
| `/api/metrics/summaries` | `{active_series,items:[{code,label,value_text,unit,description,instrument,window}]}` |
| `/api/metrics/histogram?instrument=` | `{instrument,unit,total,buckets:[{bucket_label,count}],explainer}` |
| `/api/metrics/outcomes?instrument=` | `{instrument,total,items:[{result,count,is_error}],note}` |
| `/api/metrics/catalog` | `{namespace,items:[{name,kind,unit,description,dimensions}],glossary:[{term,body}]}` |
| `/api/metrics/series?instrument=` | `{instrument,points:[{bucket_at,value}]}` |

## Telemetry — logs

| Route | Returns |
|---|---|
| `/api/logs?severity=&limit=&offset=&trace_id=` | `{items:[{id,observed_at,severity_text,service_name,event_name,body,trace_id,span_id,error_type}],total,limit,offset,window}` |
| `/api/logs/{id}` | the full record incl. `attributes` — rendered as the expanded JSON block |

## Telemetry — baggage

| Route | Returns |
|---|---|
| `/api/baggage/summary` | `{requests_inspected,complete_propagation,complete_pct,needs_attention,header_p95_bytes,spec}` |
| `/api/baggage/requests?workflow=&propagation=` | `{items:[{trace_id,conversation_id,ticket_ref,request_label,workflow,propagation_status,fields_present,fields_expected,header_bytes,outcome,started_at}],workflows:[...],total}` |
| `/api/baggage/requests/{trace_id}` | `{request:{...},hops:[{hop_no,service_name,display_name,operation,trace_offset_ms,fields_present,fields_expected,header_bytes,result,traceparent,baggage_value}],hop_fields:{"3":[{key,value,purpose,status}]},blocked:[{field,observed_value,reason}]}` |
| `/api/baggage/allowlist` | `{allowed:[{key,purpose}],blocked:[{field,observed_value,reason}]}` |

## Telemetry — profiles

| Route | Returns |
|---|---|
| `/api/profiles?service=&type=cpu\|allocations` | `{service_name,profile_type,window_label,sample_hz,finding,frames:[{id,parent_id,function_name,pct,self_ms,depth}],hot_functions:[{function_name,pct,total_ms}]}` |
| `/api/profiles/correlation` | `{steps:[{step_no,title,body}]}` |

## Governance

| Route | Returns |
|---|---|
| `/api/standards/requirements` | `{items:[{code,badge,title,body,is_required,is_met}]}` |
| `/api/standards/checklist` | `{passing,total,items:[{code,statement,is_passing}]}` |
| `/api/standards/collector-path` | `{steps:[{step_no,code,title,detail}],env_block:"OTEL_SERVICE_NAME=..."}` |
| `/api/standards/privacy` | `{items:[...]}` — privacy-by-design + every-automation-joins panels |
| `/api/diagnose` | `{symptom:[{step_no,title,body}],diagnosis:[{step_no,title,body,route}],summary}` |

## Incident simulation

| Route | Method | Notes |
|---|---|---|
| `/api/incident/state` | GET | `{state, incident\|null}` |
| `/api/incident/simulate` | POST | body `{state:"healthy"\|"incident"}` → same shape. Server-side, so every page agrees. |

## OTLP ingestion (forward path for real instrumentation)

| Route | Method | Notes |
|---|---|---|
| `/v1/traces` `/v1/metrics` `/v1/logs` | POST | OTLP/HTTP JSON. Persists to `otlp_ingest`, returns `{"partialSuccess":{}}`. The bundled Collector forwards here. |
| `/api/otlp/ingest-stats` | GET | `{items:[{signal,batches,promoted,last_received_at}]}` |

The same stats are also embedded as `ingest` on `/api/standards/collector-path`,
`/api/standards/requirements` and `/api/standards/checklist`, shaped
`{batches_total,last_received_at,by_signal:[{signal,batches,promoted,last_received_at}],receiver_routes,endpoint,is_live}`.
Note the field names: `batches_total` (not `total`) and `by_signal` (not
`signals`/`items`) — this shape was not pinned down before two workstreams
each built against it independently, which is exactly how they drifted.

## Ask (LLM)

| Route | Method | Notes |
|---|---|---|
| `/api/ask` | POST | body `{question, conversation_id?}` → `{reply, conversation_id, tool_calls:[{name,arguments,result_summary}]}`. Claude via OpenRouter, tools map 1:1 onto the query functions above so chat and screen can never disagree. |
