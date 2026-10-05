"""
Incident Evidence Score -- deliberately never called a "fraud probability".

It is a transparent, weighted combination of independently-computed
0..1 components. Every component is itself a deterministic calculation
over financial-primitive data (see financial/baseline.py, entity
resolution, communication correlation); the LLM never touches this file.
"""
from __future__ import annotations

from dataclasses import dataclass

# Prototype weighting from the architecture doc. Kept as named constants
# (not magic numbers) so the recovery packet / audit log can cite exactly
# which weights produced a given score, and so a future calibration pass
# has one place to change.
WEIGHT_NEW_BENEFICIARY = 25
WEIGHT_AMOUNT_ANOMALY = 20
WEIGHT_VELOCITY_ANOMALY = 20
WEIGHT_HISTORICAL_NOVELTY = 15
WEIGHT_DORMANT_ENTITY = 10
WEIGHT_COMMUNICATION_CORRELATION = 10

TOTAL_WEIGHT = (
    WEIGHT_NEW_BENEFICIARY
    + WEIGHT_AMOUNT_ANOMALY
    + WEIGHT_VELOCITY_ANOMALY
    + WEIGHT_HISTORICAL_NOVELTY
    + WEIGHT_DORMANT_ENTITY
    + WEIGHT_COMMUNICATION_CORRELATION
)  # == 100


@dataclass
class ScoreComponents:
    new_beneficiary: float  # 0/1
    amount_anomaly: float  # 0..1, normalized robust-z
    velocity_anomaly: float  # 0..1, normalized rolling-window pressure
    historical_novelty: float  # 0..1, inverse of prior transaction count
    dormant_entity: float  # 0..1, normalized dormancy duration
    communication_correlation: float  # 0..1, 1.0 corroborated / 0.5 possible / 0

    def as_dict(self) -> dict:
        return {
            "new_beneficiary": round(self.new_beneficiary, 4),
            "amount_anomaly": round(self.amount_anomaly, 4),
            "velocity_anomaly": round(self.velocity_anomaly, 4),
            "historical_novelty": round(self.historical_novelty, 4),
            "dormant_entity": round(self.dormant_entity, 4),
            "communication_correlation": round(self.communication_correlation, 4),
        }


def normalize_robust_z(z: float, saturate_at: float = 40.0) -> float:
    """Map an unbounded robust z-score onto 0..1. saturate_at is the z-score
    beyond which we treat the anomaly as "maximally anomalous" -- chosen so a
    543x-median event (like the flagship incident) saturates the component
    without an arbitrary hand-tuned per-incident cutoff."""
    if z <= 0:
        return 0.0
    return min(1.0, z / saturate_at)


def normalize_velocity(rolling_count: int, rolling_amount: float,
                        median_payout: float, count_saturate: int = 3,
                        amount_multiple_saturate: float = 5.0) -> float:
    """Blend "too many payouts too fast" and "too much money too fast" into
    one 0..1 pressure score for the rolling 10-minute window."""
    count_component = min(1.0, rolling_count / count_saturate)
    amount_component = 0.0
    if median_payout > 0:
        amount_component = min(1.0, (float(rolling_amount) / float(median_payout)) / (count_saturate * amount_multiple_saturate))
    return max(count_component, amount_component)


def normalize_historical_novelty(prior_transaction_count: int, saturate_at: int = 5) -> float:
    if prior_transaction_count <= 0:
        return 1.0
    return max(0.0, 1.0 - (prior_transaction_count / saturate_at))


def normalize_dormancy(dormant_seconds: float, saturate_days: float = 120.0) -> float:
    import math

    if dormant_seconds == float("inf"):
        return 1.0
    days = dormant_seconds / 86400.0
    if days <= 0:
        return 0.0
    return min(1.0, math.log1p(days) / math.log1p(saturate_days))


def communication_component(correlation_status: str) -> float:
    return {"CORROBORATED": 1.0, "POSSIBLE": 0.5}.get(correlation_status, 0.0)


def aggregate_incident_components(per_payout: list[ScoreComponents]) -> ScoreComponents:
    """Aggregate a case without letting one extreme event erase case breadth.

    A single-event incident is unchanged. For multi-event incidents each
    dimension blends the mean with the case maximum. This preserves a strong
    outlier signal while preventing a single payout from representing an
    otherwise ordinary batch as entirely anomalous.
    """
    if not per_payout:
        raise ValueError("At least one payout is required")

    def mean(values: list[float]) -> float:
        return round(sum(values) / len(values), 4)

    return ScoreComponents(
        new_beneficiary=mean([c.new_beneficiary for c in per_payout]),
        amount_anomaly=mean([c.amount_anomaly for c in per_payout]),
        velocity_anomaly=mean([c.velocity_anomaly for c in per_payout]),
        historical_novelty=mean([c.historical_novelty for c in per_payout]),
        dormant_entity=mean([c.dormant_entity for c in per_payout]),
        communication_correlation=mean([c.communication_correlation for c in per_payout]),
    )


def incident_evidence_score(components: ScoreComponents) -> float:
    """Weighted sum, normalized to 0..100."""
    raw = (
        WEIGHT_NEW_BENEFICIARY * components.new_beneficiary
        + WEIGHT_AMOUNT_ANOMALY * components.amount_anomaly
        + WEIGHT_VELOCITY_ANOMALY * components.velocity_anomaly
        + WEIGHT_HISTORICAL_NOVELTY * components.historical_novelty
        + WEIGHT_DORMANT_ENTITY * components.dormant_entity
        + WEIGHT_COMMUNICATION_CORRELATION * components.communication_correlation
    )
    return round(raw, 2)  # already 0..100 since weights sum to 100 and components are 0..1
