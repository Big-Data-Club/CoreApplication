"""Domain-neutral contracts for the BDC agentic platform.

The platform passes bounded, attributable artifacts between specialists rather
than replaying a full chat transcript.  Specialists are registered by capability
and the orchestration policy selects a minimal DAG for each task, so adding a
researcher, code runner, or domain reviewer does not require replacing the
orchestrator's control flow.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MemoryKind(str, Enum):
    ANCHOR = "anchor"
    PREFERENCE = "preference"
    DECISION = "decision"
    PENDING_ACTION = "pending_action"
    LEARNING_SIGNAL = "learning_signal"
    ARTIFACT = "artifact"


@dataclass(frozen=True)
class MemoryItem:
    """A compact durable memory with explicit scope and provenance."""
    kind: MemoryKind
    value: str
    scope: str = "session"  # session | course | user
    confidence: float = 0.7
    status: str = "active"  # active | completed | superseded
    source: str = "conversation_summary"
    course_id: int | None = None


@dataclass(frozen=True)
class AgentArtifact:
    """Typed hand-off between agents; source references are never discarded."""
    kind: str
    content: str
    provenance: tuple[str, ...] = ()
    confidence: float = 0.7
    token_budget: int = 2800
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentCapability:
    name: str
    provides: frozenset[str]
    max_input_tokens: int
    requires_evidence: bool = False
    can_mutate: bool = False


@dataclass(frozen=True)
class AgentTask:
    objective: str
    intent: str
    require_evidence: bool
    quality_gate: bool
    allow_mutation: bool = False


@dataclass(frozen=True)
class OrchestrationStep:
    capability: str
    consumes: tuple[str, ...]
    produces: str


@dataclass(frozen=True)
class OrchestrationPlan:
    task: AgentTask
    steps: tuple[OrchestrationStep, ...]
    rationale: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "objective": self.task.objective,
            "intent": self.task.intent,
            "require_evidence": self.task.require_evidence,
            "quality_gate": self.task.quality_gate,
            "steps": [
                {"capability": step.capability, "consumes": list(step.consumes), "produces": step.produces}
                for step in self.steps
            ],
            "rationale": list(self.rationale),
        }


class CapabilityRegistry:
    """Small registry so orchestration is capability-driven, not class-driven."""

    def __init__(self) -> None:
        self._items: dict[str, AgentCapability] = {}

    def register(self, capability: AgentCapability) -> None:
        self._items[capability.name] = capability

    def has(self, name: str) -> bool:
        return name in self._items

    def names(self) -> set[str]:
        return set(self._items)


def default_capability_registry() -> CapabilityRegistry:
    registry = CapabilityRegistry()
    registry.register(AgentCapability(
        "evidence_retrieval", frozenset({"grounded_context"}), 2800, requires_evidence=True,
    ))
    registry.register(AgentCapability(
        "response_drafting", frozenset({"draft"}), 3200,
    ))
    registry.register(AgentCapability(
        "quality_critique", frozenset({"quality_report"}), 3200, requires_evidence=True,
    ))
    return registry


def build_orchestration_plan(task: AgentTask, registry: CapabilityRegistry) -> OrchestrationPlan:
    """Select the smallest evidence-preserving DAG available for a task.

    This is policy, not a fixed pipeline.  Future specialists only need to
    register their capability; policy can then prefer them without making the
    prompt or a monolithic supervisor aware of implementation details.
    """
    steps: list[OrchestrationStep] = []
    rationale: list[str] = []
    draft_input = "task"
    if task.require_evidence and registry.has("evidence_retrieval"):
        steps.append(OrchestrationStep("evidence_retrieval", ("task",), "grounded_context"))
        draft_input = "grounded_context"
        rationale.append("The request needs verifiable evidence, so retrieve and reduce sources first.")
    if registry.has("response_drafting"):
        steps.append(OrchestrationStep("response_drafting", (draft_input,), "draft"))
    if task.quality_gate and registry.has("quality_critique"):
        steps.append(OrchestrationStep("quality_critique", (draft_input, "draft"), "quality_report"))
        rationale.append("A quality gate is required before returning a deep or high-stakes response.")
    return OrchestrationPlan(task=task, steps=tuple(steps), rationale=tuple(rationale))
