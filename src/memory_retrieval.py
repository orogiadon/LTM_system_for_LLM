#!/usr/bin/env python3
"""
memory_retrieval.py - 記憶想起モジュール（UserPromptSubmit Hook用）

ユーザーメッセージ送信時に関連記憶を検索し、プロンプトに注入する。
Claude Code の UserPromptSubmit Hook として実行される。
"""

import io
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

# 標準入出力のエンコーディング設定（Windows対応）
sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding='utf-8')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# パスを追加してモジュールをインポート可能に
sys.path.insert(0, str(Path(__file__).parent))

from config_loader import get_config
from embedding import get_embedding
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


def calculate_relevance(
    memory: dict[str, Any],
    query_embedding: list[float],
    current_emotion: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None
) -> float:
    """
    参照優先度を計算

    priority = retention_score × similarity × (1 + 0.1 × recall_count) + resonance_bonus

    Args:
        memory: 記憶データ
        query_embedding: クエリのEmbedding
        current_emotion: 現在の感情状態（任意）
        config: 設定辞書

    Returns:
        参照優先度
    """
    # 保持スコア
    retention_score = memory.get("retention_score", 0) or 0

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

    # 基本優先度
    base_priority = retention_score * similarity * recall_weight

    # 感情共鳴ボーナス
    resonance_bonus = 0
    if current_emotion:
        resonance_bonus = calculate_resonance_bonus(memory, current_emotion, config)

    return base_priority + resonance_bonus


def search_memories(
    query_embedding: list[float],
    memories: list[dict[str, Any]],
    archive: list[dict[str, Any]],
    config: dict[str, Any] | None = None
) -> list[tuple[dict[str, Any], bool]]:
    """
    関連記憶を検索（閾値+フォールバック方式）

    Args:
        query_embedding: クエリのEmbedding
        memories: アクティブ記憶のリスト
        archive: アーカイブ記憶のリスト
        config: 設定辞書

    Returns:
        (記憶, is_archived) のタプルのリスト
    """
    if config is None:
        config = get_config()

    retrieval_config = config.get("retrieval", {})
    top_k = retrieval_config.get("top_k", 5)
    relevance_threshold = retrieval_config.get("relevance_threshold", 5.0)

    archive_config = config.get("archive", {})
    enable_archive_recall = archive_config.get("enable_archive_recall", True)

    scored = []

    # アクティブ記憶を検索
    for mem in memories:
        relevance = calculate_relevance(mem, query_embedding, config=config)
        if relevance > 0:
            scored.append((relevance, mem, False))

    # アーカイブも検索（enable_archive_recall = true の場合）
    if enable_archive_recall:
        for mem in archive:
            relevance = calculate_relevance(mem, query_embedding, config=config)
            if relevance > 0:
                scored.append((relevance, mem, True))

    # 閾値以上の記憶を抽出
    high_relevance = [(r, mem, is_arch) for r, mem, is_arch in scored if r >= relevance_threshold]

    if len(high_relevance) >= top_k:
        # 十分な候補があれば閾値以上のみソート
        high_relevance.sort(key=lambda x: x[0], reverse=True)
        return [(mem, is_archived) for _, mem, is_archived in high_relevance[:top_k]]
    else:
        # 候補不足時は全件からtop_k取得（フォールバック）
        scored.sort(key=lambda x: x[0], reverse=True)
        return [(mem, is_archived) for _, mem, is_archived in scored[:top_k]]


def format_memories(results: list[tuple[dict[str, Any], bool]]) -> str:
    """
    記憶を出力形式にフォーマット

    Args:
        results: (記憶, is_archived) のタプルのリスト

    Returns:
        フォーマットされた文字列
    """
    if not results:
        return ""

    lines = ["<memories>"]
    for mem, is_archived in results:
        created = mem.get("created", "unknown")
        # ISO形式から日付部分のみ抽出
        if "T" in created:
            created = created.split("T")[0]

        trigger = mem.get("trigger", "")
        content = mem.get("content", "")
        level = mem.get("current_level", 1)
        archived_mark = "[archived]" if is_archived else ""

        lines.append(f"- [{created}][L{level}]{archived_mark} {trigger} → {content}")

    lines.append("</memories>")
    return "\n".join(lines)


def main():
    """メイン処理"""
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

    # 検索
    results = search_memories(query_embedding, memories, archive, config)

    if results:
        # 記憶を出力（ユーザーメッセージに追加される）
        print(format_memories(results))

        # アクティブ記憶の想起フラグを立てる
        recalled_ids = [mem["id"] for mem, is_archived in results if not is_archived]
        if recalled_ids:
            store.mark_recalled(recalled_ids)

        # アーカイブ記憶の復活リクエストフラグを立てる
        archived_ids = [mem["id"] for mem, is_archived in results if is_archived]
        if archived_ids:
            now = datetime.now().astimezone().isoformat()
            for mem_id in archived_ids:
                store.update_memory(mem_id, {
                    "revival_requested": True,
                    "revival_requested_at": now
                })


if __name__ == "__main__":
    main()
