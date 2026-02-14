"""
retention.py - 保持スコア計算モジュール

記憶の保持スコア（retention_score）を計算し、レベルを判定する。
"""

from typing import Any

from config_loader import get_config


def calculate_retention_score(
    emotional_intensity: int,
    decay_coefficient: float,
    memory_days: float
) -> float:
    """
    保持スコアを計算

    retention_score = emotional_intensity × decay_coefficient^memory_days

    Args:
        emotional_intensity: 感情強度（0-100）
        decay_coefficient: 減衰係数（0-1）
        memory_days: 経過日数

    Returns:
        保持スコア
    """
    return emotional_intensity * (decay_coefficient ** memory_days)


def determine_level(
    retention_score: float,
    config: dict[str, Any] | None = None
) -> int:
    """
    保持スコアからレベルを判定

    Args:
        retention_score: 保持スコア
        config: 設定辞書

    Returns:
        レベル（1-4）
    """
    if config is None:
        config = get_config()

    levels = config.get("levels", {})
    level1_threshold = levels.get("level1_threshold", 50)
    level2_threshold = levels.get("level2_threshold", 20)

    if retention_score >= level1_threshold:
        return 1  # 完全記憶
    elif retention_score >= level2_threshold:
        return 2  # 圧縮記憶
    else:
        return 4  # アーカイブ


def calculate_initial_decay_coefficient(
    category: str,
    emotional_intensity: int,
    config: dict[str, Any] | None = None
) -> float:
    """
    カテゴリと感情強度から初期減衰係数を計算

    Args:
        category: カテゴリ（casual/work/decision/emotional）
        emotional_intensity: 感情強度（0-100）
        config: 設定辞書

    Returns:
        初期減衰係数
    """
    if config is None:
        config = get_config()

    retention = config.get("retention", {})
    decay_by_category = retention.get("decay_by_category", {})

    # カテゴリの減衰係数範囲を取得
    category_range = decay_by_category.get(category, {"min": 0.85, "max": 0.92})
    min_decay = category_range.get("min", 0.85)
    max_decay = category_range.get("max", 0.92)

    # 感情強度に基づいて線形補間
    # 感情強度が高いほど減衰係数が高い（記憶が残りやすい）
    ratio = emotional_intensity / 100.0
    return min_decay + (max_decay - min_decay) * ratio


def update_retention_score(memory: dict[str, Any]) -> float:
    """
    記憶の保持スコアを再計算

    Args:
        memory: 記憶データ

    Returns:
        新しい保持スコア
    """
    return calculate_retention_score(
        emotional_intensity=memory["emotional_intensity"],
        decay_coefficient=memory["decay_coefficient"],
        memory_days=memory["memory_days"]
    )


def should_compress(
    memory: dict[str, Any],
    config: dict[str, Any] | None = None
) -> tuple[bool, int]:
    """
    記憶を圧縮すべきか判定

    Args:
        memory: 記憶データ
        config: 設定辞書

    Returns:
        (圧縮すべきか, 新しいレベル) のタプル
    """
    current_level = memory.get("current_level", 1)
    retention_score = memory.get("retention_score", 0)

    if retention_score is None:
        retention_score = update_retention_score(memory)

    new_level = determine_level(retention_score, config)

    # 保護記憶は圧縮しない
    if memory.get("protected", False):
        return False, current_level

    # レベルが上がる場合のみ圧縮
    if new_level > current_level:
        return True, new_level

    return False, current_level
