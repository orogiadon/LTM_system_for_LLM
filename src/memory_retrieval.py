#!/usr/bin/env python3
"""
memory_retrieval.py - 記憶想起モジュール（UserPromptSubmit Hook用）

ユーザーメッセージ送信時に関連記憶を検索し、プロンプトに注入する。
Claude Code の UserPromptSubmit Hook として実行される。
"""

import io
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

_debug_enabled: bool | None = None


def _is_debug() -> bool:
    """デバッグモードか判定（config or 環境変数）"""
    global _debug_enabled
    if _debug_enabled is not None:
        return _debug_enabled
    # 環境変数を優先、なければconfigから読む
    if os.environ.get("LTM_DEBUG", "") == "1":
        _debug_enabled = True
    else:
        try:
            config = get_config()
            _debug_enabled = config.get("retrieval", {}).get("debug", False)
        except Exception:
            _debug_enabled = False
    return _debug_enabled


def debug_log(msg: str) -> None:
    """デバッグメッセージをstderrに出力"""
    if _is_debug():
        print(f"[LTM] {msg}", file=sys.stderr)

# パスを追加してモジュールをインポート可能に
sys.path.insert(0, str(Path(__file__).parent))

from config_loader import get_config
from embedding import get_embedding
from llm import classify_query
from memory_store import MemoryStore
from resonance import calculate_resonance_bonus


def get_prompt_from_stdin() -> str:
    """標準入力からプロンプトを取得"""
    try:
        data = json.load(sys.stdin)
        return data.get("prompt", "")
    except json.JSONDecodeError:
        return ""


def should_skip(query: str) -> bool:
    """
    記憶処理をスキップすべきか判定

    Args:
        query: ユーザー入力

    Returns:
        スキップすべきならTrue
    """
    if not query:
        return True

    stripped = query.strip()

    # スラッシュコマンドはスキップ
    if stripped.startswith("/"):
        return True

    return False


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """
    コサイン類似度を計算

    Args:
        vec_a: ベクトルA
        vec_b: ベクトルB

    Returns:
        コサイン類似度（-1〜1）
    """
    a = np.array(vec_a)
    b = np.array(vec_b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return float(np.dot(a, b) / (norm_a * norm_b))


def compute_category_stats(
    memories: list[dict[str, Any]]
) -> dict[str, tuple[float, float]]:
    """
    カテゴリごとのretention_scoreの平均・標準偏差を計算

    Args:
        memories: 記憶リスト

    Returns:
        {category: (mean, std)} の辞書
    """
    from collections import defaultdict

    by_category: dict[str, list[float]] = defaultdict(list)
    for mem in memories:
        cat = mem.get("category", "casual")
        retention = mem.get("retention_score", 0) or 0
        by_category[cat].append(retention)

    stats: dict[str, tuple[float, float]] = {}
    for cat, values in by_category.items():
        arr = np.array(values)
        mean = float(np.mean(arr))
        std = float(np.std(arr))
        if std == 0:
            std = 1.0  # ゼロ除算防止
        stats[cat] = (mean, std)

    return stats


def calculate_relevance(
    memory: dict[str, Any],
    query_embedding: list[float],
    query_category: str | None = None,
    category_stats: dict[str, tuple[float, float]] | None = None,
    current_emotion: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None
) -> float:
    """
    参照優先度を計算（正規化 + similarity² + カテゴリブースト）

    Args:
        memory: 記憶データ
        query_embedding: クエリのEmbedding
        query_category: クエリのカテゴリ（LLM分類結果）
        category_stats: {category: (mean, std)} カテゴリ別統計
        current_emotion: 現在の感情状態（任意）
        config: 設定辞書

    Returns:
        参照優先度
    """
    if config is None:
        config = get_config()

    retrieval_config = config.get("retrieval", {})
    beta = retrieval_config.get("category_boost_beta", 2.0)

    # 保持スコア → カテゴリ内正規化
    retention_score = memory.get("retention_score", 0) or 0
    mem_category = memory.get("category", "casual")

    if category_stats and mem_category in category_stats:
        mean, std = category_stats[mem_category]
        normalized_retention = (retention_score - mean) / std
    else:
        normalized_retention = retention_score

    # ベクトル類似度
    memory_embedding = memory.get("embedding")
    if memory_embedding and query_embedding:
        similarity = cosine_similarity(query_embedding, memory_embedding)
        similarity = max(0, similarity)  # 負の類似度は0に
    else:
        similarity = 0

    # recall_countによる重み
    recall_count = memory.get("recall_count", 0)
    recall_weight = 1 + 0.1 * recall_count

    # カテゴリブースト
    category_boost = beta if (query_category and mem_category == query_category) else 1.0

    # 基本優先度
    base_priority = normalized_retention * (similarity ** 2) * recall_weight * category_boost

    # 感情共鳴ボーナス
    resonance_bonus = 0
    if current_emotion:
        resonance_config = config.get("resonance", {})
        alpha = resonance_config.get("priority_weight_alpha", 0.3)
        from resonance import calculate_resonance
        resonance = calculate_resonance(memory, current_emotion, config)
        resonance_bonus = alpha * resonance * normalized_retention

    return base_priority + resonance_bonus


def get_related_memories(
    memory: dict[str, Any],
    memory_map: dict[str, dict[str, Any]],
    depth: int = 1,
    visited: set[str] | None = None
) -> list[dict[str, Any]]:
    """
    関連記憶を再帰的に取得（深度制限付き）

    Args:
        memory: 起点となる記憶
        memory_map: ID → 記憶データのマップ
        depth: 探索深度（1なら直接関連のみ）
        visited: 訪問済みIDセット（循環防止）

    Returns:
        関連記憶のリスト
    """
    if depth <= 0:
        return []

    if visited is None:
        visited = {memory["id"]}

    related = []
    relations = memory.get("relations", [])

    for rel_id in relations:
        if rel_id in visited:
            continue

        related_mem = memory_map.get(rel_id)
        if related_mem:
            visited.add(rel_id)
            related.append(related_mem)

            # 再帰的に関連を取得
            if depth > 1:
                deeper = get_related_memories(related_mem, memory_map, depth - 1, visited)
                related.extend(deeper)

    return related


def search_memories(
    query_embedding: list[float],
    memories: list[dict[str, Any]],
    archive: list[dict[str, Any]],
    query_category: str | None = None,
    current_emotion: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None
) -> list[tuple[dict[str, Any], bool]]:
    """
    関連記憶を検索（閾値+フォールバック方式）

    Args:
        query_embedding: クエリのEmbedding
        memories: アクティブ記憶のリスト
        archive: アーカイブ記憶のリスト
        query_category: クエリのカテゴリ（LLM分類結果）
        current_emotion: 現在の感情状態
        config: 設定辞書

    Returns:
        (記憶, is_archived) のタプルのリスト
    """
    if config is None:
        config = get_config()

    retrieval_config = config.get("retrieval", {})
    top_k = retrieval_config.get("top_k", 10)
    relevance_threshold = retrieval_config.get("relevance_threshold", 0.5)

    archive_config = config.get("archive", {})
    enable_archive_recall = archive_config.get("enable_archive_recall", True)

    # カテゴリ統計を計算（全記憶対象）
    all_memories = list(memories)
    if enable_archive_recall:
        all_memories.extend(archive)
    category_stats = compute_category_stats(all_memories)

    scored = []

    # アクティブ記憶を検索
    for mem in memories:
        relevance = calculate_relevance(
            mem, query_embedding,
            query_category=query_category,
            category_stats=category_stats,
            current_emotion=current_emotion,
            config=config
        )
        scored.append((relevance, mem, False))

    # アーカイブも検索（enable_archive_recall = true の場合）
    if enable_archive_recall:
        for mem in archive:
            relevance = calculate_relevance(
                mem, query_embedding,
                query_category=query_category,
                category_stats=category_stats,
                current_emotion=current_emotion,
                config=config
            )
            scored.append((relevance, mem, True))

    # 正のスコアのみ残す
    scored = [(r, mem, is_arch) for r, mem, is_arch in scored if r > 0]

    # 閾値以上の記憶を抽出
    high_relevance = [(r, mem, is_arch) for r, mem, is_arch in scored if r >= relevance_threshold]

    if len(high_relevance) >= top_k:
        high_relevance.sort(key=lambda x: x[0], reverse=True)
        return [(mem, is_archived) for _, mem, is_archived in high_relevance[:top_k]]
    else:
        # 候補不足時は全件からtop_k取得（フォールバック）
        scored.sort(key=lambda x: x[0], reverse=True)
        return [(mem, is_archived) for _, mem, is_archived in scored[:top_k]]


def expand_with_relations(
    results: list[tuple[dict[str, Any], bool]],
    memories: list[dict[str, Any]],
    archive: list[dict[str, Any]],
    config: dict[str, Any] | None = None
) -> list[tuple[dict[str, Any], bool, bool]]:
    """
    検索結果に関連記憶を追加

    Args:
        results: (記憶, is_archived) のタプルのリスト
        memories: アクティブ記憶のリスト
        archive: アーカイブ記憶のリスト
        config: 設定辞書

    Returns:
        (記憶, is_archived, is_related) のタプルのリスト
    """
    if config is None:
        config = get_config()

    relations_config = config.get("relations", {})
    depth = relations_config.get("relation_traversal_depth", 1)

    if depth <= 0:
        # 関連展開無効
        return [(mem, is_archived, False) for mem, is_archived in results]

    # 全記憶のマップを作成
    memory_map: dict[str, dict[str, Any]] = {}
    archive_ids: set[str] = set()

    for mem in memories:
        memory_map[mem["id"]] = mem
    for mem in archive:
        memory_map[mem["id"]] = mem
        archive_ids.add(mem["id"])

    # 既に結果に含まれるIDを記録
    result_ids = {mem["id"] for mem, _ in results}

    # 関連記憶を収集
    expanded: list[tuple[dict[str, Any], bool, bool]] = []

    for mem, is_archived in results:
        # 元の結果を追加
        expanded.append((mem, is_archived, False))

        # 関連記憶を取得
        related = get_related_memories(mem, memory_map, depth, visited={mem["id"]})

        for rel_mem in related:
            if rel_mem["id"] not in result_ids:
                result_ids.add(rel_mem["id"])
                is_rel_archived = rel_mem["id"] in archive_ids
                expanded.append((rel_mem, is_rel_archived, True))

    return expanded


def format_memories(
    results: list[tuple[dict[str, Any], bool]] | list[tuple[dict[str, Any], bool, bool]]
) -> str:
    """
    記憶を出力形式にフォーマット

    Args:
        results: (記憶, is_archived) または (記憶, is_archived, is_related) のタプルのリスト

    Returns:
        フォーマットされた文字列
    """
    if not results:
        return ""

    lines = ["<memories>"]
    for item in results:
        # 2要素タプル（旧形式）と3要素タプル（新形式）の両方に対応
        if len(item) == 3:
            mem, is_archived, is_related = item
        else:
            mem, is_archived = item
            is_related = False

        created = mem.get("created", "unknown")
        # ISO形式から日付部分のみ抽出
        if "T" in created:
            created = created.split("T")[0]

        trigger = mem.get("trigger", "")
        content = mem.get("content", "")
        level = mem.get("current_level", 1)

        # マーカーを組み立て
        markers = []
        if is_archived:
            markers.append("[archived]")
        if is_related:
            markers.append("[related]")
        marker_str = "".join(markers)

        lines.append(f"- [{created}][L{level}]{marker_str} {trigger} → {content}")

    lines.append("</memories>")
    return "\n".join(lines)


def main():
    """メイン処理"""
    # 標準入出力のエンコーディング設定（Windows対応）
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding='utf-8')
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    # プロンプト取得
    query = get_prompt_from_stdin()

    if not query.strip() or should_skip(query):
        return

    # 設定読み込み
    config = get_config()

    # DB接続
    db_path = Path(__file__).parent.parent / "data" / "memories.db"
    store = MemoryStore(db_path)

    # アクティブ記憶とアーカイブ記憶を取得
    memories = store.get_active_memories()
    archive = store.get_archived_memories()

    if not memories and not archive:
        return

    # クエリをベクトル化
    try:
        query_embedding = get_embedding(query, config)
    except Exception:
        # Embedding生成に失敗した場合は終了
        return

    # クエリのカテゴリ・感情分類
    query_category = None
    current_emotion = None
    try:
        classification = classify_query(query, config)
        query_category = classification.get("category")
        current_emotion = {
            "valence": classification.get("valence", "neutral"),
            "arousal": classification.get("arousal", 50),
            "tags": classification.get("tags", []),
        }
        debug_log(f"query_category={query_category} emotion={current_emotion}")
    except Exception as e:
        # 分類失敗時はNoneのまま（旧挙動にフォールバック）
        debug_log(f"classify_query failed: {e}")

    # 検索
    results = search_memories(
        query_embedding, memories, archive,
        query_category=query_category,
        current_emotion=current_emotion,
        config=config
    )

    if results:
        # デバッグ: 想起結果のスコアを表示
        if _is_debug():
            debug_log(f"--- recall results (top {len(results)}) ---")
            # スコアを再計算して表示（search_memoriesはスコアを返さないため）
            all_mems = list(memories)
            archive_config = config.get("archive", {})
            if archive_config.get("enable_archive_recall", True):
                all_mems.extend(archive)
            category_stats = compute_category_stats(all_mems)
            debug_log(f"category_stats: { {k: (round(m,2), round(s,2)) for k, (m,s) in category_stats.items()} }")
            for i, (mem, is_archived) in enumerate(results):
                score = calculate_relevance(
                    mem, query_embedding,
                    query_category=query_category,
                    category_stats=category_stats,
                    current_emotion=current_emotion,
                    config=config
                )
                trigger = (mem.get("trigger", ""))[:40]
                cat = mem.get("category", "?")
                arch = " [arch]" if is_archived else ""
                debug_log(f"  {i+1:2d}. score={score:8.4f} cat={cat:10s}{arch} {trigger}")
            debug_log("---")

        # 関連記憶を展開
        expanded = expand_with_relations(results, memories, archive, config)

        # 記憶を出力（ユーザーメッセージに追加される）
        print(format_memories(expanded))

        # アクティブ記憶の想起フラグを立てる（関連記憶も含む）
        recalled_ids = [mem["id"] for mem, is_archived, _ in expanded if not is_archived]
        if recalled_ids:
            store.mark_recalled(recalled_ids)

        # アーカイブ記憶の復活リクエストフラグを立てる（関連記憶も含む）
        archived_ids = [mem["id"] for mem, is_archived, _ in expanded if is_archived]
        if archived_ids:
            now = datetime.now().astimezone().isoformat()
            for mem_id in archived_ids:
                store.update_memory(mem_id, {
                    "revival_requested": True,
                    "revival_requested_at": now
                })


if __name__ == "__main__":
    main()
