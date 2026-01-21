"""
relations.py - 記憶の関連付けモジュール

記憶間の関連付けを管理する。
- 整合性チェック（削除された記憶への参照除去）
- 関連付け方向の再評価
- 自動関連付け（類似度ベース）
"""

from typing import Any

import numpy as np

from config_loader import get_config
from memory_store import MemoryStore


def find_similar_memories(
    new_memory: dict[str, Any],
    all_memories: list[dict[str, Any]],
    threshold: float = 0.85
) -> list[tuple[dict[str, Any], float]]:
    """
    類似記憶を検索（NumPy行列演算で高速化）

    Args:
        new_memory: 新しい記憶
        all_memories: 比較対象の全記憶
        threshold: 類似度閾値

    Returns:
        (記憶, 類似度) のタプルのリスト
    """
    new_emb = new_memory.get("embedding")
    if new_emb is None:
        return []

    # Embeddingがある記憶のみフィルタ
    valid_memories = [(m, m.get("embedding")) for m in all_memories if m.get("embedding")]
    if not valid_memories:
        return []

    new_emb_np = np.array(new_emb)

    # 全記憶のEmbeddingを行列化
    embeddings = np.array([emb for _, emb in valid_memories])

    # コサイン類似度を一括計算
    norms = np.linalg.norm(embeddings, axis=1) * np.linalg.norm(new_emb_np)
    # ゼロ除算を防ぐ
    norms = np.where(norms == 0, 1, norms)
    similarities = np.dot(embeddings, new_emb_np) / norms

    # 閾値以上の記憶を抽出
    results = []
    for i, similarity in enumerate(similarities):
        if similarity >= threshold:
            results.append((valid_memories[i][0], float(similarity)))

    return results


def determine_relation_direction(
    memory_a: dict[str, Any],
    memory_b: dict[str, Any]
) -> tuple[str, str]:
    """
    関連付けの方向を決定（高スコア → 低スコア）

    Args:
        memory_a: 記憶A
        memory_b: 記憶B

    Returns:
        (参照元ID, 参照先ID) のタプル
    """
    score_a = memory_a.get("retention_score", 0) or 0
    score_b = memory_b.get("retention_score", 0) or 0

    if score_a >= score_b:
        return memory_a["id"], memory_b["id"]
    else:
        return memory_b["id"], memory_a["id"]


def add_relation(
    memory: dict[str, Any],
    target_id: str,
    max_relations: int = 10
) -> list[str]:
    """
    関連付けを追加

    Args:
        memory: 記憶データ
        target_id: 関連付け先のID
        max_relations: 最大関連数

    Returns:
        更新されたrelationsリスト
    """
    relations = list(memory.get("relations", []))

    if target_id in relations:
        return relations

    if len(relations) >= max_relations:
        return relations

    relations.append(target_id)
    return relations


def remove_relation(memory: dict[str, Any], target_id: str) -> list[str]:
    """
    関連付けを削除

    Args:
        memory: 記憶データ
        target_id: 削除する関連付け先のID

    Returns:
        更新されたrelationsリスト
    """
    relations = list(memory.get("relations", []))
    if target_id in relations:
        relations.remove(target_id)
    return relations


def check_integrity(
    store: MemoryStore,
    config: dict[str, Any] | None = None
) -> int:
    """
    整合性チェック（削除された記憶への参照を除去）

    Args:
        store: MemoryStoreインスタンス
        config: 設定辞書

    Returns:
        修正された関連付けの数
    """
    all_memories = store.get_all_memories(include_archived=True)
    all_ids = {m["id"] for m in all_memories}

    fixed_count = 0

    for memory in all_memories:
        relations = memory.get("relations", [])
        valid_relations = [r for r in relations if r in all_ids]

        if len(valid_relations) != len(relations):
            store.update_memory(memory["id"], {"relations": valid_relations})
            fixed_count += 1

    return fixed_count


def reevaluate_directions(
    store: MemoryStore,
    config: dict[str, Any] | None = None
) -> int:
    """
    関連付け方向の再評価（スコア逆転時の参照張り替え）

    Args:
        store: MemoryStoreインスタンス
        config: 設定辞書

    Returns:
        修正された関連付けの数
    """
    all_memories = store.get_all_memories(include_archived=True)
    memory_map = {m["id"]: m for m in all_memories}

    fixed_count = 0

    for memory in all_memories:
        relations = memory.get("relations", [])
        my_score = memory.get("retention_score", 0) or 0

        for target_id in relations:
            target = memory_map.get(target_id)
            if not target:
                continue

            target_score = target.get("retention_score", 0) or 0

            # 方向が逆転している場合
            if target_score > my_score:
                # 自分からの参照を削除
                new_relations = remove_relation(memory, target_id)
                store.update_memory(memory["id"], {"relations": new_relations})

                # 相手に参照を追加
                if config is None:
                    config = get_config()
                max_relations = config.get("relations", {}).get("max_relations_per_memory", 10)
                target_relations = add_relation(target, memory["id"], max_relations)
                store.update_memory(target_id, {"relations": target_relations})

                fixed_count += 1

    return fixed_count


def auto_link_new_memories(
    store: MemoryStore,
    new_memory_ids: list[str],
    config: dict[str, Any] | None = None
) -> int:
    """
    新規記憶の自動関連付け

    Args:
        store: MemoryStoreインスタンス
        new_memory_ids: 新規記憶のIDリスト
        config: 設定辞書

    Returns:
        作成された関連付けの数
    """
    if config is None:
        config = get_config()

    relations_config = config.get("relations", {})
    if not relations_config.get("enable_auto_linking", True):
        return 0

    threshold = relations_config.get("auto_link_similarity_threshold", 0.85)
    max_relations = relations_config.get("max_relations_per_memory", 10)

    all_memories = store.get_all_memories(include_archived=False)
    memory_map = {m["id"]: m for m in all_memories}

    # 新規記憶以外の記憶
    existing_memories = [m for m in all_memories if m["id"] not in new_memory_ids]

    link_count = 0

    for new_id in new_memory_ids:
        new_memory = memory_map.get(new_id)
        if not new_memory:
            continue

        # 類似記憶を検索
        similar = find_similar_memories(new_memory, existing_memories, threshold)

        for target_memory, similarity in similar:
            # 方向を決定
            from_id, to_id = determine_relation_direction(new_memory, target_memory)
            from_memory = memory_map.get(from_id)

            if from_memory:
                new_relations = add_relation(from_memory, to_id, max_relations)
                if len(new_relations) > len(from_memory.get("relations", [])):
                    store.update_memory(from_id, {"relations": new_relations})
                    link_count += 1

    return link_count


def process_relations(
    store: MemoryStore,
    new_memory_ids: list[str] | None = None,
    config: dict[str, Any] | None = None
) -> dict[str, int]:
    """
    関連付け処理をまとめて実行

    Args:
        store: MemoryStoreインスタンス
        new_memory_ids: 新規記憶のIDリスト（自動関連付け用）
        config: 設定辞書

    Returns:
        処理結果の辞書
    """
    results = {
        "integrity_fixed": 0,
        "direction_fixed": 0,
        "auto_linked": 0
    }

    # 整合性チェック
    results["integrity_fixed"] = check_integrity(store, config)

    # 方向再評価
    results["direction_fixed"] = reevaluate_directions(store, config)

    # 自動関連付け
    if new_memory_ids:
        results["auto_linked"] = auto_link_new_memories(store, new_memory_ids, config)

    return results
