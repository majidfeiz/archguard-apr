"""Pure V2.1A micro-pilot fairness and cost-guard contracts."""

from dataclasses import dataclass
from decimal import Decimal

from archguard.domain.repository import check

MODEL_SNAPSHOT = "gpt-5.4-2026-03-05"
RESPONSE_SCHEMA = "archguard.repair-response/v2.1"
MAX_CALLS = 8
MAX_INPUT_TOKENS = 35_000
MAX_OUTPUT_TOKENS = 2_000
INPUT_PER_MILLION = Decimal("2.50")
OUTPUT_PER_MILLION = Decimal("15.00")
PER_CALL_RESERVATION = Decimal("0.1175")
TOTAL_RESERVATION = Decimal("0.9400")
HARD_CEILING = Decimal("1.0000")


@dataclass(frozen=True)
class SyntheticUsage:
    input_tokens: int
    output_tokens: int

    def __post_init__(self) -> None:
        check(0 <= self.input_tokens <= MAX_INPUT_TOKENS, "invalid input usage")
        check(0 <= self.output_tokens <= MAX_OUTPUT_TOKENS, "invalid output usage")

    @property
    def cost(self) -> Decimal:
        return (
            Decimal(self.input_tokens) * INPUT_PER_MILLION
            + Decimal(self.output_tokens) * OUTPUT_PER_MILLION
        ) / Decimal(1_000_000)


@dataclass(frozen=True)
class CostState:
    completed_calls: int = 0
    observed_cost: Decimal = Decimal("0")
    reserved_cost: Decimal = Decimal("0")

    def reserve(self) -> "CostState":
        check(self.completed_calls < MAX_CALLS, "provider call ceiling reached")
        check(self.reserved_cost == 0, "ambiguous in-flight reservation")
        check(
            self.observed_cost + PER_CALL_RESERVATION <= HARD_CEILING,
            "cost ceiling would be exceeded",
        )
        return CostState(self.completed_calls, self.observed_cost, PER_CALL_RESERVATION)

    def reconcile(self, usage: SyntheticUsage | None) -> "CostState":
        check(self.reserved_cost == PER_CALL_RESERVATION, "missing reservation")
        if usage is None:
            raise ValueError("missing provider usage")
        check(usage.cost <= self.reserved_cost, "usage contradicts reservation")
        return CostState(self.completed_calls + 1, self.observed_cost + usage.cost, Decimal("0"))


SHARED_FAIRNESS_FIELDS = (
    "evaluator",
    "failure_classifications",
    "maximum_calls_per_pair",
    "maximum_input_tokens",
    "maximum_output_tokens",
    "model_snapshot",
    "patch_validator",
    "response_schema",
    "resource_ceilings",
    "retries",
    "sandbox",
    "task_revisions",
)
ALLOWED_VARIANTS = (
    "architecture_constraints",
    "execution_feedback",
    "graph_retrieval",
    "orchestration",
)


def validate_condition_fairness(conditions: dict[str, dict[str, object]]) -> tuple[str, ...]:
    check(
        tuple(sorted(conditions))
        == ("BASELINE", "FULL_ARCHGUARD", "GRAPH_CONSTRAINTS", "GRAPH_ONLY"),
        "invalid condition set",
    )
    baseline = conditions["BASELINE"]
    differences: list[str] = []
    for name, condition in sorted(conditions.items()):
        check(set(condition) == set(SHARED_FAIRNESS_FIELDS) | set(ALLOWED_VARIANTS), "bad fields")
        for field in SHARED_FAIRNESS_FIELDS:
            if condition[field] != baseline[field]:
                differences.append(f"{name}:{field}")
    return tuple(differences)
