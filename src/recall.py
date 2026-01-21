"""
recall.py - 想起強化処理モジュール

想起された記憶の強化処理を行う。
バッチ処理で recalled_since_last_batch = 1 の記憶を処理する。
"""

from typing import Any

from .config_loader import get_config
from .memory_store import MemoryStore


def process_recalled_memory(
    memory: dict[str, Any],
    config: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    想起された記憶を強化

    - memory_days を半減
    - decay_coefficient を +0.02（上限あり）
    - recall_count をインクリメント

    Args:
        memory: 記憶データ
        config: 設定辞書

    Returns:
        更新された記憶データ（変更されたフィールドのみ）
    """
    if config is None:
        config = get_config()

    recall_config = config.get("recall", {})
    retention_config = config.get("retention", {})

    memory_days_reduction = recall_config.get("memory_days_reduction", 0.5)
    decay_boost = recall_config.get("decay_coefficient_boost", 0.02)
    max_decay = retention_config.get("max_decay_coefficient", 0.999)

    updates = {}

    # memory_days を半減
    current_memory_days = memory.get("memory_days", 0.0)
    updates["memory_days"] = current_memory_days * memory_days_reduction

    # decay_coefficient を増加（上限あり）
    current_decay = memory.get("decay_coefficient", 0.995)
    new_decay = min(current_decay + decay_boost, max_decay)
    updates["decay_coefficient"] = new_decay

    # recall_count をインクリメント
    current_recall_count = memory.get("recall_count", 0)
    updates["recall_count"] = current_recall_count + 1

    # recalled_since_last_batch をリセット
    updates["recalled_since_last_batch"] = False

    return updates


def process_all_recalled_memories(
    store: MemoryStore,
    config: dict[str, Any] | None = None
) -> int:
    """
    すべての想起された記憶を処理

    recalled_since_last_batch = 1 の記憶を検索し、強化処理を適用する。

    Args:
        store: MemoryStoreインスタンス
        config: 設定辞書

    Returns:
        処理された記憶の件数
    """
    if config is None:
        config = get_config()

    processed_count = 0

    # アクティブ記憶のうち、想起フラグが立っているものを取得
    with store.connection() as conn:
        rows = conn.execute('''
            SELECT * FROM memories
            WHERE recalled_since_last_batch = 1 AND archived_at IS NULL
        ''').fetchall()

        for row in rows:
            memory = store._row_to_dict(row)
            updates = process_recalled_memory(memory, config)
            store.update_memory(memory["id"], updates)
            processed_count += 1

    return processed_count


def calculate_recall_weight(recall_count: int, config: dict[str, Any] | None = None) -> float:
    """
    recall_countに基づく重みを計算

    Args:
        recall_count: 想起回数
        config: 設定辞書

    Returns:
        重み（1 + recall_count_weight × recall_count）
    """
    if config is None:
        config = get_config()

    recall_config = config.get("recall", {})
    recall_count_weight = recall_config.get("recall_count_weight", 0.1)

    return 1 + recall_count_weight * recall_count
