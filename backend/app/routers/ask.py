"""Ask -- Claude over the same query functions the screens use.

The point of routing chat through tools rather than a prompt full of pasted
figures: every number in an answer comes from the same function that renders the
panel, so the chat and the screen cannot disagree. If a figure is a capped API
page on the dashboard, it is a capped API page in the chat too.

Transport is the OpenAI-compatible Chat Completions API at
https://openrouter.ai/api/v1, called with httpx. Model and key come from
settings (`openrouter_model`, `openrouter_api_key`).
"""
from __future__ import annotations

import inspect
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

import httpx
from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.otel import tracer
from app.routers.incident import current_state
from app.services import telemetry

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ask", tags=["ask"])

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_TOOL_ITERATIONS = 8
MAX_TOOLS = 64  # 24 telemetry + ~30 business panels, with room to grow
MAX_HISTORY_MESSAGES = 24
MAX_CONVERSATIONS = 200
TOOL_RESULT_CHARS = 8000
SUMMARY_CHARS = 600
REQUEST_TIMEOUT_SECONDS = 90.0

# osw.* attributes for this module's own spans (the namespace is defined in
# app.core.otel; these extend it for the chat path only).
OSW_ASK_CONVERSATION = "osw.ask.conversation_id"
OSW_ASK_TOOL = "osw.ask.tool"
OSW_ASK_ITERATIONS = "osw.ask.iterations"
OSW_ASK_TOOL_CALLS = "osw.ask.tool_calls"

# ---------------------------------------------------------------------------
# Conversation history.
#
# Process-local and lost on restart: this is a single-process PoC, so history
# lives in a module-level dict rather than Redis or Postgres. Two consequences
# worth knowing before this is deployed behind more than one worker -- a
# follow-up question can land on a process that has never seen the thread, and
# nothing here survives a redeploy.
# ---------------------------------------------------------------------------
_HISTORY: dict[str, list[dict[str, Any]]] = {}


def _remember(conversation_id: str, messages: list[dict[str, Any]]) -> None:
    trimmed = messages[-MAX_HISTORY_MESSAGES:]
    # Never open a stored thread on a tool result whose call is gone: the API
    # rejects a tool message without its preceding assistant tool_calls.
    while trimmed and trimmed[0].get("role") == "tool":
        trimmed.pop(0)
    _HISTORY[conversation_id] = trimmed
    while len(_HISTORY) > MAX_CONVERSATIONS:
        _HISTORY.pop(next(iter(_HISTORY)))


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    fn: Callable[..., Any]
    accepts: frozenset[str] = field(default_factory=frozenset)

    def spec(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def _schema(
    properties: dict[str, Any] | None = None, required: Iterable[str] = ()
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties or {},
        "required": list(required),
        "additionalProperties": False,
    }


_STATE = {
    "type": "string",
    "enum": ["healthy", "incident"],
    "description": (
        "Override the server-held incident simulation. Omit to use the state the "
        "screens are currently showing."
    ),
}
_TRACE_ID = {"type": "string", "description": "Trace id, e.g. 7fd3a91c."}


def _accepts(fn: Callable[..., Any]) -> frozenset[str]:
    """Parameter names the function will actually take."""
    try:
        return frozenset(
            name
            for name, param in inspect.signature(fn).parameters.items()
            if param.kind
            in (param.POSITIONAL_OR_KEYWORD, param.KEYWORD_ONLY)
        )
    except (TypeError, ValueError):  # pragma: no cover - builtins only
        return frozenset()


def _tool(name: str, fn: Callable[..., Any], description: str, parameters: dict) -> Tool:
    return Tool(
        name=name,
        description=description,
        parameters=parameters,
        fn=fn,
        accepts=_accepts(fn),
    )


def _telemetry_tools() -> list[Tool]:
    """One tool per panel function in services/telemetry.py."""
    return [
        _tool(
            "telemetry_list_traces",
            telemetry.list_traces,
            "Recent request traces (trace id, label, workflow, outcome, duration, "
            "conversation, ticket) plus trace coverage.",
            _schema(
                {
                    "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                    "workflow": {
                        "type": "string",
                        "description": "e.g. product_return, billing_inquiry.",
                    },
                    "outcome": {
                        "type": "string",
                        "enum": list(telemetry.TRACE_OUTCOMES),
                    },
                    "state": _STATE,
                }
            ),
        ),
        _tool(
            "telemetry_trace_model",
            telemetry.trace_model,
            "The conversation -> trace -> span explainer and trace coverage.",
            _schema(),
        ),
        _tool(
            "telemetry_conversation_traces",
            telemetry.conversation_traces,
            "One guest chat session and the request traces inside it.",
            _schema(
                {
                    "conversation_id": {"type": "string", "description": "e.g. conv_8a2f."},
                    "state": _STATE,
                },
                required=["conversation_id"],
            ),
        ),
        _tool(
            "telemetry_trace_detail",
            telemetry.trace_detail,
            "Full waterfall for one trace: ordered spans with offsets, durations, "
            "depth and status, axis ticks, and root attributes split into semantic "
            "conventions and business correlation.",
            _schema({"trace_id": _TRACE_ID, "state": _STATE}, required=["trace_id"]),
        ),
        _tool(
            "telemetry_metric_summaries",
            telemetry.metric_summaries,
            "Metric tiles: conversation rate, p95 duration, ticket success, "
            "enrichment error rate. Degrades under the incident state.",
            _schema({"state": _STATE}),
        ),
        _tool(
            "telemetry_metric_histogram",
            telemetry.metric_histogram,
            "Bucketed distribution for one histogram instrument (default "
            "osw.conversation.duration).",
            _schema({"instrument": {"type": "string"}}),
        ),
        _tool(
            "telemetry_metric_outcomes",
            telemetry.metric_outcomes,
            "Outcome dimensions for one counter (default osw.enrichment.operation): "
            "success vs input rejected vs system error, and the derived error rate.",
            _schema({"instrument": {"type": "string"}}),
        ),
        _tool(
            "telemetry_metric_catalog",
            telemetry.metric_catalog,
            "Every osw.* instrument with kind, unit and approved dimensions, plus "
            "the counter/histogram/dimension glossary.",
            _schema(),
        ),
        _tool(
            "telemetry_metric_series",
            telemetry.metric_series,
            "Time series points for one instrument.",
            _schema(
                {
                    "instrument": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 5000},
                }
            ),
        ),
        _tool(
            "telemetry_list_logs",
            telemetry.list_logs,
            "Structured log records newest first, filterable by severity "
            "(ALL/ERROR/WARN/INFO) and trace id. Paginated: limit defaults to 7.",
            _schema(
                {
                    "severity": {
                        "type": "string",
                        "enum": ["ALL", "ERROR", "WARN", "INFO"],
                    },
                    "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                    "offset": {"type": "integer", "minimum": 0},
                    "trace_id": _TRACE_ID,
                }
            ),
        ),
        _tool(
            "telemetry_log_detail",
            telemetry.log_detail,
            "One log record in full, including attributes and the trace it belongs to.",
            _schema({"log_id": {"type": "integer"}}, required=["log_id"]),
        ),
        _tool(
            "telemetry_baggage_summary",
            telemetry.baggage_summary,
            "Propagation health: requests inspected, complete propagation, requests "
            "needing attention, p95 header size.",
            _schema(),
        ),
        _tool(
            "telemetry_baggage_requests",
            telemetry.baggage_requests,
            "Candidate requests to inspect, filterable by workflow and propagation "
            "status (complete | attention).",
            _schema(
                {
                    "workflow": {"type": "string"},
                    "propagation": {
                        "type": "string",
                        "enum": ["all", *telemetry.PROPAGATION_STATUSES],
                    },
                    "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                    "offset": {"type": "integer", "minimum": 0},
                }
            ),
        ),
        _tool(
            "telemetry_baggage_request_detail",
            telemetry.baggage_request_detail,
            "The propagation audit for ONE request: every hop with its traceparent "
            "and literal baggage header, the fields each service received, and the "
            "fields the origin filter blocked.",
            _schema({"trace_id": _TRACE_ID, "state": _STATE}, required=["trace_id"]),
        ),
        _tool(
            "telemetry_baggage_allowlist",
            telemetry.baggage_allowlist,
            "The governed baggage allowlist and the blocked-field evidence.",
            _schema(),
        ),
        _tool(
            "telemetry_profile",
            telemetry.profile,
            "Flame profile for one service as a flat frame list, plus hot functions "
            "and the finding.",
            _schema(
                {
                    "service": {"type": "string", "description": "e.g. enrichment-service."},
                    "profile_type": {
                        "type": "string",
                        "enum": list(telemetry.PROFILE_TYPES),
                    },
                }
            ),
        ),
        _tool(
            "telemetry_profile_correlation",
            telemetry.profile_correlation,
            "Metric alert -> slow trace -> linked profile: the symptom-to-code path.",
            _schema(),
        ),
        _tool(
            "telemetry_standards_requirements",
            telemetry.standards_requirements,
            "The six-item OpenTelemetry contract for OSW, with live OTLP ingest "
            "evidence.",
            _schema(),
        ),
        _tool(
            "telemetry_standards_checklist",
            telemetry.standards_checklist,
            "The OTEL-01..OTEL-08 acceptance checklist and its pass count.",
            _schema(),
        ),
        _tool(
            "telemetry_collector_path",
            telemetry.collector_path,
            "The vendor-neutral collector pipeline, the OTEL_* env block, and live "
            "OTLP ingest counts.",
            _schema(),
        ),
        _tool(
            "telemetry_privacy_standards",
            telemetry.privacy_standards,
            "Privacy-by-design and every-automation-joins content, with the "
            "enforced allowlist and blocked fields.",
            _schema(),
        ),
        _tool(
            "telemetry_diagnose",
            telemetry.diagnose,
            "The symptom (what the business sees) and diagnosis (five clicks) steps.",
            _schema({"state": _STATE}),
        ),
        _tool(
            "telemetry_otlp_ingest_stats",
            telemetry.otlp_ingest_stats,
            "Live OTLP receiver stats -- proof the collector path is working.",
            _schema(),
        ),
        _tool(
            "telemetry_incident_state",
            lambda: {
                "state": current_state(),
                **telemetry.state_context(current_state()),
            },
            "The server-held incident simulation state and, when active, the "
            "incident record and which services are degraded.",
            _schema(),
        ),
    ]


_BUSINESS_DENYLIST = {
    "annotations",
    "clamp",
    "cursor",
    "envelope",
    "exclusive_upper",
    "fetch_all",
    "fetch_one",
    "fetch_value",
    "get_pool",
    "meta",
    "notes_for",
    "resolve_state",
    "router",
    "tracer",
    "validate_date_range",
}

_JSON_TYPE_HINTS: tuple[tuple[str, str], ...] = (
    ("bool", "boolean"),
    ("int", "integer"),
    ("float", "number"),
    ("Decimal", "number"),
)


def _json_type(annotation: Any) -> str:
    """Best-effort JSON type from an annotation that may be a string.

    `from __future__ import annotations` makes every annotation a string, so this
    matches on text rather than on types. Wrong guesses cost nothing: the value
    is filtered to the accepted parameter names and the function is free to coerce.
    """
    text = annotation if isinstance(annotation, str) else getattr(annotation, "__name__", "")
    if not text:
        return "string"
    for needle, json_type in _JSON_TYPE_HINTS:
        if needle in text:
            return json_type
    return "string"


def _business_tools() -> list[Tool]:
    """Auto-discover the business half's panel functions.

    services/business.py is another workstream's file, written against the same
    contract. It is imported defensively and introspected rather than
    name-matched, so a missing module or a renamed function costs a tool, never a
    500 on import.
    """
    try:
        from app.services import business as business_module  # noqa: PLC0415
    except Exception:
        log.info("services.business not importable yet; serving telemetry tools only")
        return []

    tools: list[Tool] = []
    module_name = getattr(business_module, "__name__", "")
    for name in sorted(dir(business_module)):
        if name.startswith("_") or name in _BUSINESS_DENYLIST:
            continue
        candidate = getattr(business_module, name, None)
        if not inspect.isfunction(candidate):
            continue
        if getattr(candidate, "__module__", None) != module_name:
            continue  # re-export, not a panel of its own
        try:
            signature = inspect.signature(candidate)
        except (TypeError, ValueError):
            continue
        properties: dict[str, Any] = {}
        required: list[str] = []
        for param_name, param in signature.parameters.items():
            if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
                continue
            properties[param_name] = {"type": _json_type(param.annotation)}
            if param_name in ("date_from", "date_to"):
                properties[param_name]["description"] = "ISO date, YYYY-MM-DD."
            if param.default is inspect.Parameter.empty:
                required.append(param_name)
        # First paragraph of the docstring, whitespace collapsed -- these
        # docstrings wrap mid-sentence, so a single line would clip them.
        doc = (inspect.getdoc(candidate) or "").strip()
        first_paragraph = " ".join(doc.split("\n\n")[0].split()) if doc else ""
        description = first_paragraph or f"Business panel query: {name.replace('_', ' ')}."
        tools.append(
            Tool(
                name=f"business_{name}"[:64],
                description=description[:900],
                parameters=_schema(properties, required),
                fn=candidate,
                accepts=frozenset(properties),
            )
        )
    log.info("exposed %d business tools to /api/ask", len(tools))
    return tools


def build_tools() -> dict[str, Tool]:
    """Built per request so a late-landing services/business.py is picked up."""
    tools = _telemetry_tools() + _business_tools()
    if len(tools) > MAX_TOOLS:
        # Loud, because a silently dropped tool looks like missing data.
        log.warning(
            "%d tools discovered but only %d are exposed; raise MAX_TOOLS",
            len(tools),
            MAX_TOOLS,
        )
    return {tool.name: tool for tool in tools[:MAX_TOOLS]}


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """\
You are the analyst inside "O for OSW", a unified observability dashboard for One \
Spa World's AI automations. It holds two halves of one context: the business view \
(conversations, tickets, the chat-to-document journey) and the technical view \
(OpenTelemetry traces, metrics, logs, baggage, profiles).

Answer only from the tools. Every tool reads the same query functions that render \
the screens, so your figures must match the panels exactly. If a tool returns no \
rows, say the data is not loaded yet -- never estimate, never fill a gap from \
memory, and never carry a number over from a different tool than the one that \
produced it.

Provenance is not optional. Most payloads carry a `meta` block with a `panel_id`, \
a `population` and `notes`. Populations are: A = a capped Kore.ai session page \
(100 rows, more available), B = Zendesk bot-raised tickets only, C = hand-reviewed \
daily sheets covering 5 of 19 days, T = OpenTelemetry signals. No figure in this \
product is a period total. When a payload carries a caveat or critical note that \
changes how a number should be read, say it in the same breath as the number.

The technical side has a server-held incident simulation. When the state is \
`incident`, enrichment degrades: its span and hop run far longer, p95 latency and \
the error rate rise, and the payload's `incident` block names the incident. Say \
which state a figure came from when it matters.

Be concise and concrete. Prefer the specific evidence -- this trace, this hop, \
this log record, this function -- over generalities. Use plain prose, no emoji, \
and give exact figures with their units."""


def _summarise(result: Any) -> str:
    """A short, human-readable digest of a tool result for the response payload."""
    try:
        if isinstance(result, dict):
            parts: list[str] = []
            for key in ("error", "total", "count", "passing", "coverage_pct", "state"):
                if key in result and not isinstance(result[key], (dict, list)):
                    parts.append(f"{key}={result[key]}")
            for key in ("items", "spans", "frames", "hops", "steps", "points", "buckets"):
                value = result.get(key)
                if isinstance(value, list):
                    parts.append(f"{key}={len(value)} rows")
            if parts:
                return ", ".join(parts)
        text = json.dumps(result, default=str)
    except Exception:  # pragma: no cover
        text = str(result)
    return text[:SUMMARY_CHARS] + ("..." if len(text) > SUMMARY_CHARS else "")


def _tool_payload(result: Any) -> str:
    """The tool result as JSON. Oversized results are wrapped, never sliced mid-token.

    A truncated JSON string would leave the model parsing a broken object, so an
    over-long result becomes a valid envelope that says so and asks for a
    narrower slice instead.
    """
    text = json.dumps(result, default=str)
    if len(text) <= TOOL_RESULT_CHARS:
        return text
    return json.dumps(
        {
            "truncated": True,
            "hint": (
                "Result too large to return in full. Re-call with a smaller "
                "limit, a filter, or a specific id."
            ),
            "preview": text[:TOOL_RESULT_CHARS],
        }
    )


async def _run_tool(tool: Tool, raw_arguments: str | dict | None) -> tuple[dict, Any]:
    """Parse arguments, drop anything the function will not take, and call it."""
    arguments: dict[str, Any]
    if isinstance(raw_arguments, dict):
        arguments = raw_arguments
    elif raw_arguments:
        try:
            parsed = json.loads(raw_arguments)
            arguments = parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}, {"error": "arguments were not valid JSON"}
    else:
        arguments = {}
    kwargs = {k: v for k, v in arguments.items() if k in tool.accepts and v is not None}
    try:
        # The query layer is synchronous psycopg; keep the event loop free.
        result = await run_in_threadpool(tool.fn, **kwargs)
    except ValueError as exc:
        result = {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001 - reported to the model, not swallowed
        log.exception("tool %s failed", tool.name)
        result = {"error": f"{type(exc).__name__}: {exc}"}
    if result is None:
        result = {"error": "not found"}
    return kwargs, result


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, max_length=64)


NO_KEY_REPLY = (
    "Chat is not configured on this deployment: no OpenRouter API key is set, so "
    "I cannot reach Claude. Set OPENROUTER_API_KEY in the environment (and "
    "optionally OPENROUTER_MODEL) and restart the API. Everything else still "
    "works -- the panels read the same query functions this chat would have "
    "called, so the data is all reachable through /api/traces, /api/metrics, "
    "/api/logs, /api/baggage, /api/profiles and /api/standards."
)


async def _chat_completion(
    client: httpx.AsyncClient,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": settings.openrouter_model,
        "messages": messages,
        "temperature": 0,
    }
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    response = await client.post(
        OPENROUTER_URL,
        json=body,
        headers={
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "Content-Type": "application/json",
            # Optional OpenRouter attribution headers; harmless if ignored.
            "X-Title": "O for OSW observability",
        },
    )
    response.raise_for_status()
    return response.json()


@router.post("")
async def ask(body: AskRequest) -> dict:
    """Ask a question about either half of the picture.

    Returns `{reply, conversation_id, tool_calls:[{name,arguments,result_summary}]}`.
    """
    conversation_id = body.conversation_id or f"chat_{uuid.uuid4().hex[:12]}"
    tool_calls_made: list[dict[str, Any]] = []

    if not settings.openrouter_api_key:
        # Friendly, not fatal: the dashboard must stay usable without a key.
        return {
            "reply": NO_KEY_REPLY,
            "conversation_id": conversation_id,
            "tool_calls": [],
            "model": settings.openrouter_model,
            "configured": False,
        }

    tools = build_tools()
    tool_specs = [tool.spec() for tool in tools.values()]
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(_HISTORY.get(conversation_id, []))
    messages.append({"role": "user", "content": body.question})

    reply = ""
    error: str | None = None
    iterations = 0

    with tracer().start_as_current_span("osw.ask") as span:
        span.set_attribute(OSW_ASK_CONVERSATION, conversation_id)
        span.set_attribute("osw.simulated.state", current_state())
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                for iterations in range(1, MAX_TOOL_ITERATIONS + 1):
                    payload = await _chat_completion(client, messages, tool_specs)
                    choices = payload.get("choices") or []
                    if not choices:
                        error = "the model returned no choices"
                        break
                    message = choices[0].get("message") or {}
                    requested = message.get("tool_calls") or []
                    messages.append(
                        {
                            "role": "assistant",
                            "content": message.get("content") or "",
                            **({"tool_calls": requested} if requested else {}),
                        }
                    )
                    if not requested:
                        reply = (message.get("content") or "").strip()
                        break

                    for call in requested:
                        function = call.get("function") or {}
                        name = function.get("name") or ""
                        tool = tools.get(name)
                        if tool is None:
                            result: Any = {"error": f"unknown tool {name!r}"}
                            used: dict[str, Any] = {}
                        else:
                            with tracer().start_as_current_span(
                                f"osw.ask.tool.{name}"
                            ) as tool_span:
                                tool_span.set_attribute(OSW_ASK_TOOL, name)
                                used, result = await _run_tool(
                                    tool, function.get("arguments")
                                )
                        tool_calls_made.append(
                            {
                                "name": name,
                                "arguments": used,
                                "result_summary": _summarise(result),
                            }
                        )
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call.get("id") or name,
                                "name": name,
                                "content": _tool_payload(result),
                            }
                        )
                else:
                    # Iteration cap reached with tools still in flight: ask once
                    # more with tools withheld so the user gets prose, not silence.
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "You have reached the tool-call limit for this "
                                "question. Answer now from what the tools already "
                                "returned, and say plainly what is still unknown."
                            ),
                        }
                    )
                    payload = await _chat_completion(client, messages, None)
                    choices = payload.get("choices") or []
                    if choices:
                        reply = ((choices[0].get("message") or {}).get("content") or "").strip()
        except httpx.HTTPStatusError as exc:
            error = f"OpenRouter returned {exc.response.status_code}"
            log.warning("%s: %s", error, exc.response.text[:500])
        except httpx.HTTPError as exc:
            error = f"could not reach OpenRouter: {type(exc).__name__}"
            log.warning("%s", error)
        except Exception as exc:  # noqa: BLE001
            error = f"{type(exc).__name__}: {exc}"
            log.exception("ask failed")

        span.set_attribute(OSW_ASK_ITERATIONS, iterations)
        span.set_attribute(OSW_ASK_TOOL_CALLS, len(tool_calls_made))

    if not reply:
        reply = (
            "I could not complete that: "
            f"{error}. The panels are unaffected -- they read the database directly."
            if error
            else "I did not get an answer back from the model. Please try again."
        )

    # Persist only the plain turn pair; tool traffic is noisy and re-derivable.
    history = _HISTORY.get(conversation_id, []) + [
        {"role": "user", "content": body.question},
        {"role": "assistant", "content": reply},
    ]
    _remember(conversation_id, history)

    return {
        "reply": reply,
        "conversation_id": conversation_id,
        "tool_calls": tool_calls_made,
        "model": settings.openrouter_model,
        "configured": True,
        **({"error": error} if error else {}),
    }


@router.get("/tools")
def list_tools() -> dict:
    """What the model can call. Useful for checking business tools have landed."""
    tools = build_tools()
    return {
        "model": settings.openrouter_model,
        "configured": bool(settings.openrouter_api_key),
        "max_tool_iterations": MAX_TOOL_ITERATIONS,
        "items": [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": sorted(tool.accepts),
            }
            for tool in tools.values()
        ],
    }
