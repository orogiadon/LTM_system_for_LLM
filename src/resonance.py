"""
resonance.py - 感情共鳴計算モジュール

記憶と現在の感情状態の共鳴度を計算する。
"""

from typing import Any

from .config_loader import get_config


def calculate_resonance(
    memory: dict[str, Any],
    current_emotion: dict[str, Any],
    config: dict[str, Any] | None = None
) -> float:
    """
    感情共鳴スコアを計算

    Args:
        memory: 記憶データ
        current_emotion: 現在の感情状態
            - valence: positive/negative/neutral
            - arousal: 0-100
            - tags: 感情タグのリスト
        config: 設定辞書

    Returns:
        感情共鳴スコア（0.0〜1.0程度）
    """
    if config is None:
        config = get_config()

    resonance_config = config.get("resonance", {})
    valence_bonus = resonance_config.get("valence_match_bonus", 0.3)
    arousal_bonus = resonance_config.get("arousal_proximity_bonus", 0.2)
    tags_weight = resonance_config.get("tags_overlap_weight", 0.5)

    score = 0.0

    # valence一致ボーナス
    memory_valence = memory.get("emotional_valence", "neutral")
    current_valence = current_emotion.get("valence", "neutral")
    if memory_valence == current_valence:
        score += valence_bonus

    # arousal近接ボーナス（差が小さいほどボーナス）
    memory_arousal = memory.get("emotional_arousal", 50)
    current_arousal = current_emotion.get("arousal", 50)
    arousal_diff = abs(memory_arousal - current_arousal) / 100.0
    score += max(0, arousal_bonus * (1 - arousal_diff))

    # tags重複ボーナス
    memory_tags = set(memory.get("emotional_tags", []))
    current_tags = set(current_emotion.get("tags", []))
    if memory_tags and current_tags:
        overlap = len(memory_tags & current_tags) / max(len(memory_tags), len(current_tags))
        score += overlap * tags_weight

    return score


def calculate_resonance_bonus(
    memory: dict[str, Any],
    current_emotion: dict[str, Any],
    config: dict[str, Any] | None = None
) -> float:
    """
    感情共鳴による優先度ボーナスを計算

    resonance_bonus = alpha × resonance × retention_score

    Args:
        memory: 記憶データ
        current_emotion: 現在の感情状態
        config: 設定辞書

    Returns:
        優先度ボーナス
    """
    if config is None:
        config = get_config()

    resonance_config = config.get("resonance", {})
    alpha = resonance_config.get("priority_weight_alpha", 0.3)

    resonance = calculate_resonance(memory, current_emotion, config)
    retention_score = memory.get("retention_score", 0) or 0

    return alpha * resonance * retention_score
