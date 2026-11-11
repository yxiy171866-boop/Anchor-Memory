"""Amygdala-Hippocampus Ebbinghaus Decay Algorithm.

Models how emotional arousal prolongs memory retention half-life.
Core memories (importance >= 0.8) are protected with a non-zero floor weight.
"""
import math

try:
    from anchor.config import (
        DECAY_BASE_HALF_LIFE_DAYS,
        DECAY_AROUSAL_MULTIPLIER,
        CORE_MEMORY_IMPORTANCE_THRESHOLD,
        CORE_MEMORY_FLOOR_WEIGHT,
    )
except ImportError:
    from config import (
        DECAY_BASE_HALF_LIFE_DAYS,
        DECAY_AROUSAL_MULTIPLIER,
        CORE_MEMORY_IMPORTANCE_THRESHOLD,
        CORE_MEMORY_FLOOR_WEIGHT,
    )


def calculate_half_life(
    arousal: float,
    base_lambda: float = DECAY_BASE_HALF_LIFE_DAYS,
    k: float = DECAY_AROUSAL_MULTIPLIER,
) -> float:
    """Calculate half-life lambda in days based on emotional arousal (0.0 to 1.0).

    Formula: lambda = base_lambda * (1 + arousal * k)
    """
    safe_arousal = max(0.0, min(1.0, float(arousal or 0.0)))
    return base_lambda * (1.0 + safe_arousal * k)


def calculate_decay_score(
    importance: float,
    arousal: float,
    days_elapsed: float,
    base_lambda: float = DECAY_BASE_HALF_LIFE_DAYS,
    k: float = DECAY_AROUSAL_MULTIPLIER,
) -> float:
    """Calculate the effective retention weight score.

    Formula: EffectiveWeight = importance * e^(-days / lambda)

    Protections:
    - If importance >= CORE_MEMORY_IMPORTANCE_THRESHOLD (0.8), the decay score
      will never drop below CORE_MEMORY_FLOOR_WEIGHT (0.5).
    - If days_elapsed <= 0, returns importance directly.
    - If importance >= 1.0, returns 1.0 (permanent retention).
    """
    safe_importance = max(0.0, min(1.0, float(importance or 0.5)))
    safe_days = max(0.0, float(days_elapsed or 0.0))

    if safe_days == 0.0:
        return safe_importance

    # Infinite retention for absolute core facts (importance == 1.0)
    if safe_importance >= 0.999:
        return 1.0

    half_life = calculate_half_life(arousal, base_lambda, k)
    raw_decay = safe_importance * math.exp(-safe_days / half_life)

    # Core memory protection floor
    if safe_importance >= CORE_MEMORY_IMPORTANCE_THRESHOLD:
        return max(CORE_MEMORY_FLOOR_WEIGHT, raw_decay)

    return round(raw_decay, 4)
