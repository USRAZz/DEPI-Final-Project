"""Agent loop: plan -> act (one tool) -> observe -> repeat, until a final answer or a limit is hit.
The model answers in JSON every turn, so the same loop works with any provider (no native tool-calling needed)."""
import json
import os
import time
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from ai_core.llm import Budget, BudgetExceeded, StructuredOutputError, get_llm
from ai_core.prompts import load_prompt, untrusted

from .tools import Context, ToolRegistry

MAX_OBS_CHARS = int(os.getenv("AGENT_MAX_OBS_CHARS", "3000"))


class AgentStep(BaseModel):
    thought: str
    action: Literal["tool", "final"]
    tool: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)
    answer: str | None = None
    proposal: dict[str, Any] | None = None

    @field_validator("args", mode="before")
    @classmethod
    def _none_to_empty(cls, v):
        return v or {}

    @model_validator(mode="after")
    def _consistent(self):
        if self.action == "tool" and not self.tool:
            raise ValueError("action 'tool' needs a 'tool' name")
        if self.action == "final" and not (self.answer or "").strip():
            raise ValueError("action 'final' needs a non-empty 'answer'")
        return self


class AgentResult(BaseModel):
    status: Literal["done", "checkpoint"]
    answer: str
    proposal: dict | None = None
    tools_used: list[str] = Field(default_factory=list)
    trace: list[dict] = Field(default_factory=list)
    steps: int = 0
    tokens: int = 0
    seconds: float = 0.0


def _partial(llm, messages: list[dict], language: str, reason: str) -> str:
    ask = (f"Stop using tools ({reason}). Using only the observations above, write the best partial answer "
           f"in language '{language}'. Say what you found, what is still missing, and ask the user how to continue. "
           "Plain text, no JSON.")
    try:
        return llm.chat(messages + [{"role": "user", "content": ask}]).strip() or "I could not finish. Please narrow the question."
    except Exception:
        return "I could not finish within the allowed limits. Please narrow the question or try again."


def run_agent(question: str, ctx: Context | None = None, *, language: str = "en", history: list[dict] | None = None,
              llm=None, registry: ToolRegistry | None = None, max_steps: int | None = None,
              budget: Budget | None = None) -> AgentResult:
    ctx = ctx or Context()
    registry = registry or ToolRegistry()
    llm = llm or get_llm("agent")
    max_steps = max_steps or int(os.getenv("LLM_MAX_STEPS", "10"))
    budget = budget or Budget(max_tokens=int(os.getenv("AGENT_MAX_TOKENS", "25000")),
                              max_seconds=float(os.getenv("AGENT_MAX_SECONDS", "90")))
    system = load_prompt("finance_agent", tools=registry.describe(), role=ctx.role, language=language,
                         today=date.today().isoformat(), max_steps=max_steps)
    messages = [{"role": "system", "content": system}, *(history or []),
                {"role": "user", "content": untrusted(question)}]
    trace: list[dict] = []
    used: list[str] = []
    seen: set[str] = set()
    t0 = time.perf_counter()

    def finish(status, answer, proposal=None):
        return AgentResult(status=status, answer=answer, proposal=proposal, tools_used=sorted(set(used)),
                           trace=trace, steps=len(trace), tokens=budget.tokens,
                           seconds=round(time.perf_counter() - t0, 2))

    for n in range(1, max_steps + 1):
        try:
            step = llm.structured(messages, AgentStep, budget=budget)  # PLAN + choose the action
        except (BudgetExceeded, StructuredOutputError) as e:
            return finish("checkpoint", _partial(llm, messages, language, str(e)))
        messages.append({"role": "assistant", "content": step.model_dump_json()})

        if step.action == "final":
            trace.append({"step": n, "thought": step.thought, "action": "final"})
            return finish("done", step.answer, step.proposal)

        key = json.dumps([step.tool, step.args], sort_keys=True, default=str)  # ACT
        if key in seen:
            obs: Any = {"note": "Same call repeated. Use the earlier result or give your final answer."}
        else:
            seen.add(key)
            try:
                obs = registry.call(step.tool, step.args, ctx)
                used.append(step.tool)
            except Exception as e:  # the model sees the error and can recover
                obs = {"error": f"{type(e).__name__}: {e}"}

        obs_text = json.dumps(obs, ensure_ascii=False, default=str)  # OBSERVE
        if len(obs_text) > MAX_OBS_CHARS:
            obs_text = obs_text[:MAX_OBS_CHARS] + " ...[truncated]"
        trace.append({"step": n, "thought": step.thought, "tool": step.tool, "args": step.args,
                      "observation": obs_text[:300]})
        messages.append({"role": "user", "content": f"Observation from {step.tool}:\n{untrusted(obs_text)}"})

    return finish("checkpoint", _partial(llm, messages, language, f"reached the limit of {max_steps} steps"))