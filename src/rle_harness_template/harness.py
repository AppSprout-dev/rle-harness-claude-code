"""A minimal harness: keeps one work priority set and otherwise does nothing.

Replace ``step`` with your own decision-making. Everything you return goes
through RLE's ``ActionExecutor`` (same guards as every other harness) and is
scored by the same composite.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field
from rle.agents.actions import Action, ActionPlan
from rle.harness import BaseHarness, HarnessContext, StepResult
from rle.harness.brief import build_brief
from rle.rimapi.schemas import GameState
from rle.rimapi.sse_client import RimAPIEvent


class TemplateOptions(BaseModel):
    """Everything a user can tune via ``--harness-opt key=value``."""

    model_config = ConfigDict(extra="forbid")

    work_type: str = Field(default="Growing", description="Work type to prioritise.")
    priority: int = Field(
        default=1, ge=1, le=4, description="RimWorld work priority (1 = highest).",
    )


class TemplateHarness(BaseHarness):
    name: ClassVar[str] = "template"

    def __init__(self, options: TemplateOptions) -> None:
        super().__init__()
        self.options = options

    async def setup(self, ctx: HarnessContext) -> None:
        await super().setup(ctx)
        # ctx.client (RimAPI), ctx.scenario, ctx.event_log, ctx.cost_tracker
        # are available for the whole run.

    async def step(
        self, state: GameState, tick: int, macro_time: float, events: list[RimAPIEvent],
    ) -> StepResult:
        # The neutral brief is what every harness gets; use it however you like.
        brief = build_brief(
            state, tick=tick, macro_time=macro_time, scenario=self.ctx.scenario, events=events,
        )
        actions: list[Action] = []
        if state.colonists:
            first = state.colonists[0]
            actions.append(Action(
                action_type="work_priority",
                target_colonist_id=first.colonist_id,
                parameters={self.options.work_type: self.options.priority},
                reason=f"template: keep {first.name} on {self.options.work_type}",
            ))
        plan = ActionPlan(
            role=self.name,
            tick=state.colony.tick,
            actions=actions,
            summary=f"template step (day {brief.day})",
            confidence=0.5,
        )
        self.parse_successes += 1
        self.deliberation_log.append({
            "tick": tick, "agent": self.name, "status": "success",
            "num_actions": len(actions), "summary": plan.summary,
        })
        return StepResult(plan=plan, proposals=(plan,), extras={"template": True})

    def describe(self) -> dict[str, str]:
        return {"harness": self.name, "template_version": "0.1.0"}
