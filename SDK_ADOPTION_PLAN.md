# OpenAI Agents Python SDK — Adoption Design Plan

## Context

This document is the deliverable for the request "Review this repo and create a design plan on how to adopt this SDK. Propose multiple use cases." It summarizes what the `openai-agents-python` SDK is, why a team might adopt it, how to roll it out in phases, and six concrete use cases with recommended building blocks. The goal is to give an engineering team enough shared vocabulary and sequencing to move from zero to a production agent with confidence, and to pick the right extras instead of reinventing plumbing that already ships in the box.

Assumption: adopters are a Python 3.10+ team that already uses (or can use) the OpenAI platform, but wants the option to route to other providers via LiteLLM / any-llm.

---

## 1. What the SDK Is (One-Page Summary)

`openai-agents-python` is a lightweight, async-first framework for building single- and multi-agent workflows on top of the OpenAI Responses API (default), Chat Completions, or 100+ LLMs via LiteLLM / any-llm. The runtime is intentionally small — a handful of primitives that compose.

Core primitives:

| Primitive | Module | Role |
|-----------|--------|------|
| `Agent` | `src/agents/agent.py` | Instructions + tools + handoffs + guardrails + output type |
| `Runner` / `AgentRunner` | `src/agents/run.py` | Orchestrator; sync + async + streaming entry points |
| Tools | `src/agents/tool.py` | `@function_tool`, hosted tools (web search, file search, code interpreter, image gen, shell, computer use), MCP tools |
| Handoffs | `src/agents/handoffs/` | Agent-to-agent delegation with input filters |
| Guardrails | `src/agents/guardrail.py`, `tool_guardrails.py` | `@input_guardrail` / `@output_guardrail` / tool-level checks |
| Sessions | `src/agents/memory/`, `src/agents/extensions/memory/` | Conversation history: SQLite, OpenAI Conversations, Redis, SQLAlchemy, MongoDB, Dapr, encrypted wrapper |
| Tracing | `src/agents/tracing/` | Built-in spans, default OpenAI traces dashboard, pluggable processors (Logfire, Braintrust, LangSmith, Langfuse, Phoenix, Weave, MLflow, …) |
| Voice / Realtime | `src/agents/voice/`, `src/agents/realtime/` | Speech agents and `gpt-realtime` streaming |
| MCP | `src/agents/mcp/` | Model Context Protocol clients and server-tool filtering |
| Sandbox agents | `src/agents/sandbox/`, `src/agents/extensions/sandbox/` | Persistent containerized workspaces (Docker, E2B, Modal, Daytona, Vercel, Cloudflare, Runloop, Blaxel) |

Typical entry point:

```python
from agents import Agent, Runner

agent = Agent(name="Assistant", instructions="...", tools=[...], handoffs=[...])
result = await Runner.run(agent, "user input")
print(result.final_output)
```

See `examples/basic/hello_world.py` for the minimal pattern; `examples/financial_research_agent/` for a multi-agent workflow.

---

## 2. Why Adopt It

- **Small surface, composable** — Agent + Runner + tools covers most needs; you don't inherit a framework, you import functions.
- **OpenAI-native but provider-portable** — Responses API by default for best tool-calling + reasoning; swap in LiteLLM or any-llm per-agent (`src/agents/extensions/models/`).
- **Observability on day one** — Tracing is on by default; spans cover agent runs, LLM calls, tool calls, handoffs, and guardrails. Exporters exist for every major eval/observability vendor.
- **Safety primitives are first-class** — Input/output guardrails, tool approval, MCP approval hooks, and tool guardrails are not bolted on.
- **Real session story** — Not just in-memory; production backends (Redis, SQLAlchemy, MongoDB, Dapr) + server-managed Conversations + automatic compaction + encryption wrapper.
- **Human-in-the-loop and resumption** — `RunState` serialization lets you pause on tool approvals and resume without re-running the whole turn.

---

## 3. Adoption Phases

### Phase 0 — Prep (½ day)
- Confirm Python 3.10+; install with `uv` (`uv sync`) or `pip install openai-agents`.
- Pick only the extras you need now. Recommended starting set: none (core works), add `litellm` only if multi-provider is a day-one requirement.
- Set `OPENAI_API_KEY`; decide on a tracing destination (default is OpenAI traces dashboard).

### Phase 1 — Single agent, one tool (1–2 days)
- Build one `Agent` with instructions, one `@function_tool`, and a structured `output_type` (Pydantic model).
- Wire the default tracing dashboard; look at a few traces to internalize the span model.
- Write a smoke test using the `examples/basic/` patterns as a reference.

### Phase 2 — Sessions & guardrails (2–3 days)
- Attach a `SQLiteSession` for local dev (see `docs/sessions/index.md`).
- Add an `@input_guardrail` for cheap content / policy checks and an `@output_guardrail` for structured validation.
- Introduce retries via the built-in retry policy in `src/agents/retry.py`.

### Phase 3 — Multi-agent & handoffs (3–5 days)
- Split responsibilities into specialist agents; use `handoffs=[...]` with input filters to keep each agent's context focused.
- Pattern references: `examples/agent_patterns/` (deterministic, routing, agents-as-tools, LLM-as-judge, parallelization).

### Phase 4 — Production hardening (1–2 weeks)
- Swap `SQLiteSession` for `RedisSession` or `SQLAlchemySession`; add `EncryptedSession` wrapper if PII is persisted.
- Replace / augment the default trace processor with your vendor (Logfire, Braintrust, LangSmith, Langfuse, Phoenix, …) via `add_trace_processor()`.
- Add tool approval for any tool with real-world side effects.
- If long conversations are expected, wrap with `OpenAIResponsesCompactionSession`.

### Phase 5 — Specialized channels (optional)
- Voice (`agents[voice]`) or Realtime (`agents[realtime]`) for phone/voice UX.
- Sandbox agents (`agents[e2b]` / `agents[modal]` / `agents[docker]` / …) for code-execution or browser-automation workloads.
- MCP servers (`src/agents/mcp/`) for re-using existing tool ecosystems.

---

## 4. Proposed Use Cases

Each use case names the building blocks, the relevant example in-tree to read first, and what to customize. All six are realistic first- or second-project scopes.

### UC1 — Internal "Ask-our-docs" Knowledge Agent
- **Shape**: Single agent, hosted `file_search` over an uploaded vector store + `web_search` fallback + structured citation output.
- **Building blocks**: `Agent`, `file_search` tool, `web_search` tool, `output_type=AnswerWithCitations`, `SQLiteSession` → `RedisSession` in prod.
- **Reference**: `examples/tools/file_search.py`, `examples/tools/web_search.py`.
- **Why first**: low blast radius, immediately useful internally, exercises sessions + structured output + hosted tools.

### UC2 — Tiered Customer Support with Handoffs
- **Shape**: Triage agent → FAQ agent, Billing agent, Escalation agent. Input guardrail for PII; output guardrail validating the response schema.
- **Building blocks**: multiple `Agent`s, `handoffs` with input filters, `@input_guardrail`, `@output_guardrail`, `RedisSession` keyed by user id.
- **Reference**: `examples/customer_service/` (airline triage).
- **Why**: canonical multi-agent proof of value; directly reusable pattern across support orgs.

### UC3 — Financial / Market Research Assistant
- **Shape**: Planner agent fans out to parallel analyst agents (fundamentals, risk, news) using `web_search`; a verifier agent double-checks claims; final report is a Pydantic model.
- **Building blocks**: `Runner.run` with agents-as-tools, `web_search`, parallelization pattern, LLM-as-judge verifier, tracing for cost/latency attribution.
- **Reference**: `examples/financial_research_agent/`, `examples/research_bot/`.
- **Why**: demonstrates orchestration + parallelism + verification; a good template for any "deep research over the internet" product.

### UC4 — Code / Data Automation in a Sandbox
- **Shape**: Agent with persistent sandbox (E2B, Modal, or local Docker) that can run shell, apply patches, and use the code interpreter to analyze uploaded CSVs or diff a branch.
- **Building blocks**: sandbox agent runtime (`src/agents/extensions/sandbox/`), `code_interpreter`, `shell`, `apply_patch`, tool approval for destructive shell commands.
- **Reference**: `examples/sandbox/` (incl. `healthcare_support`, code-review tutorials), `examples/tools/code_interpreter.py`, `examples/tools/apply_patch.py`.
- **Why**: unlocks a class of "agent that does work, not just writes text" features while keeping side effects isolated and approvable.

### UC5 — Voice / Phone Agent
- **Shape**: Realtime agent behind a Twilio SIP bridge (or web widget), with a small tool palette (schedule lookup, create ticket) and an escalation handoff to a human queue.
- **Building blocks**: `agents[realtime]`, `src/agents/realtime/`, `handoffs` for human escalation, tracing for turn-level analytics.
- **Reference**: `examples/realtime/` (CLI, Twilio SIP, web app), `examples/voice/`.
- **Why**: voice is a distinct product surface; the SDK already solves streaming audio, barge-in, and tool calling over the realtime API.

### UC6 — Internal Developer Platform: MCP Tool Host
- **Shape**: A thin agent that fronts your internal MCP servers (Git, filesystem, ticketing, deploy console) with approval gates and per-user audit trail via tracing.
- **Building blocks**: `src/agents/mcp/` client, MCP tool filtering, tool approval hooks, `EncryptedSession`, external trace processor (Logfire / LangSmith) for audit.
- **Reference**: `examples/mcp/` and hosted MCP examples.
- **Why**: reuses existing MCP tooling across the org; central place to enforce approvals + audit without re-implementing tool wrappers.

---

## 5. Architecture & Extras Recommendations

Default project layout for an adopter:

```
your_app/
├── agents_app/
│   ├── agents.py         # Agent definitions (instructions, tools, handoffs)
│   ├── tools.py          # @function_tool wrappers over your domain
│   ├── guardrails.py     # @input_guardrail / @output_guardrail
│   ├── sessions.py       # Session backend factory (env-driven)
│   ├── tracing.py        # add_trace_processor() wiring
│   └── runner.py         # Thin Runner.run wrapper w/ context injection
├── tests/
└── pyproject.toml        # depends on openai-agents[<extras>]
```

Extras decision matrix (from `pyproject.toml`):

| Need | Extra | Backend module |
|------|-------|----------------|
| Multi-provider | `litellm` or `any-llm` | `src/agents/extensions/models/` |
| Distributed sessions | `redis` | `src/agents/extensions/memory/` |
| Existing SQL DB | `sqlalchemy` | `src/agents/extensions/memory/` |
| Document store sessions | `mongodb` | `src/agents/extensions/memory/` |
| Cloud-native state | `dapr` | `src/agents/extensions/memory/` |
| Encrypted history | `encrypt` | `EncryptedSession` wrapper |
| Voice | `voice` | `src/agents/voice/` |
| Realtime | `realtime` | `src/agents/realtime/` |
| Viz of agent graphs | `viz` | `graphviz` |
| Sandboxed code exec | one of `e2b`, `modal`, `docker`, `daytona`, `blaxel`, `cloudflare`, `vercel`, `runloop` | `src/agents/extensions/sandbox/` |

Rule of thumb: start with **no extras** for the first agent; add per real requirement.

---

## 6. Observability & Safety Defaults

- Keep default tracing on; only call `set_trace_processors()` if you need to replace OpenAI's dashboard entirely. Prefer `add_trace_processor()` so you keep the default and add your vendor (docs: `docs/tracing.md`).
- Treat guardrails as required, not optional. At minimum: one input guardrail (content/policy) and one output guardrail (schema or policy).
- For any tool with side effects (shell, HTTP write, DB mutation, email/Slack), require `needs_approval` or a tool-level guardrail.
- Use `RunState` serialization for resumable human-in-the-loop flows instead of custom plumbing.

---

## 7. Verification (End-to-End Checklist)

This plan is conceptual (markdown deliverable only) — no runtime code changes. To validate each proposed use case when it's implemented:

1. **Local run** — copy the nearest in-tree example (`examples/basic/hello_world.py` for UC1; `examples/customer_service/` for UC2; etc.) and replace instructions/tools with your own; run with `uv run python -m your_app.main`.
2. **Tracing check** — open the OpenAI traces dashboard (or your configured processor) and confirm one span per agent turn, nested tool spans, and guardrail spans.
3. **Session check** — invoke the agent twice with the same session id; assert turn 2 sees turn 1's history.
4. **Guardrail check** — send a crafted input that should trip the input guardrail; assert the run short-circuits with the tripwire.
5. **Handoff check** (multi-agent UCs) — instrument a test that asserts the expected agent sequence in `result` / trace.
6. **Test suite** — run `make format`, `make lint`, `make typecheck`, `make tests` per `CLAUDE.md` before shipping any code changes.

---

## 8. Critical Files to Know

| Concern | Path |
|---------|------|
| Exports / public surface | `src/agents/__init__.py` |
| Agent definition | `src/agents/agent.py` |
| Runner / orchestration | `src/agents/run.py`, `src/agents/run_internal/` |
| Tools | `src/agents/tool.py` |
| Sessions | `src/agents/memory/`, `src/agents/extensions/memory/` |
| Tracing | `src/agents/tracing/`, `docs/tracing.md` |
| MCP | `src/agents/mcp/`, `examples/mcp/` |
| Voice / Realtime | `src/agents/voice/`, `src/agents/realtime/` |
| Sandbox agents | `src/agents/sandbox/`, `src/agents/extensions/sandbox/` |
| Optional extras | `pyproject.toml` (`[project.optional-dependencies]`) |
| Docs nav | `mkdocs.yml`, `docs/` |
| Contributor rules | `CLAUDE.md` (root) |

---

## 9. Recommended First Project

**Ship UC1 (internal doc-QA agent) in week one.** It exercises: `Agent`, one hosted tool, structured output, a session, and tracing — the five things every later use case depends on. Then pick UC2 or UC3 as the second project depending on whether the higher-value path is customer-facing support or internal research.
