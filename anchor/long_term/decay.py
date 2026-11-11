"""Amygdala-Hippocampus Ebbinghaus Decay Algorithm.

Models how emotional arousal prolongs memory retention half-life.
Core memories (importance >= 0.8 or is_protected == 1) are protected with a non-zero floor weight.

Mathematical Standard:
Retention(t) = importance * 2^(-t / half_life) = importance * e^(- (t * ln 2) / half_life)
where half_life = base_half_life * (1 + arousal * k)
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

LN2 = math.log(2.0)


def calculate_half_life(
    arousal: float,
    base_half_life: float = DECAY_BASE_HALF_LIFE_DAYS,
    k: float = DECAY_AROUSAL_MULTIPLIER,
) -> float:
    """Calculate the true half-life in days based on emotional arousal (0.0 to 1.0).

    Formula: half_life = base_half_life * (1 + arousal * k)
    """
    safe_arousal = max(0.0, min(1.0, float(arousal if arousal is not None else 0.0)))
    return base_half_life * (1.0 + safe_arousal * k)


def calculate_decay_score(
    importance: float,
    arousal: float,
    days_elapsed: float,
    base_half_life: float = DECAY_BASE_HALF_LIFE_DAYS,
    k: float = DECAY_AROUSAL_MULTIPLIER,
    is_protected: bool = False,
) -> float:
    """Calculate the effective retention weight score.

    Formula:
    EffectiveWeight = importance * 2^(-days / half_life)

    Protections:
    - If is_protected is True: never decays below max(CORE_MEMORY_FLOOR_WEIGHT, importance).
    - If importance >= CORE_MEMORY_IMPORTANCE_THRESHOLD (0.8): never drops below CORE_MEMORY_FLOOR_WEIGHT (0.5).
    - If days_elapsed <= 0: returns importance.
    - If importance >= 1.0: returns 1.0 (permanent retention).
    - Supports legitimate importance=0.0 (returns 0.0).
    """
    if importance is None:
        safe_importance = 0.5
    else:
        safe_importance = max(0.0, min(1.0, float(importance)))

    safe_days = max(0.0, float(days_elapsed or 0.0))

    if safe_days == 0.0 or safe_importance == 0.0:
        return safe_importance

    if is_protected:
        return max(CORE_MEMORY_FLOOR_WEIGHT, safe_importance)

    if safe_importance >= 0.999:
        return 1.0

    half_life = calculate_half_life(arousal, base_half_life, k)
    # Standard radioactive / forgetting decay: 2^(-t / T_1/2)
    raw_decay = safe_importance * math.exp(- (safe_days * LN2) / half_life)

    # Core memory protection floor
    if safe_importance >= CORE_MEMORY_IMPORTANCE_THRESHOLD:
        return max(CORE_MEMORY_FLOOR_WEIGHT, raw_decay)

    return round(raw_decay, 4)
