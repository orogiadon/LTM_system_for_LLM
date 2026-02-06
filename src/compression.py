"""
compression.py - 圧縮・アーカイブ処理モジュール（日次バッチ）

日次バッチ処理のメインモジュール。
- 想起強化処理
- memory_days更新
- retention_score再計算
- レベル間圧縮
- アーカイブ復活
- 関連付け処理
- アーカイブ自動削除
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from config_loader import get_config
from embedding import get_embedding
from llm import compress_to_level2, compress_to_level3
from memory_store import MemoryStore
from recall import process_all_recalled_memories
from relations import process_relations
from retention import calculate_retention_score, determine_level, should_compress


def should_run_compression(store: MemoryStore, config: dict[str, Any] | None = None) -> bool:
    """
    圧縮処理を実行すべきか判定（日付ベース）

    同じ日に既に実行済みならスキップ。
    日付が変わっていれば実行する。

    Args:
        store: MemoryStoreインスタンス
        config: 設定辞書

    Returns:
        実行すべきならTrue
    """
    last_run = store.get_state("last_compression_run")
    if not last_run:
        return True

    try:
        last_run_dt = datetime.fromisoformat(last_run)
        now = datetime.now().astimezone()
        # 日付が異なれば実行
        return last_run_dt.date() != now.date()
    except (ValueError, TypeError):
        return True


def increment_memory_days(store: MemoryStore, config: dict[str, Any] | None = None) -> int:
    """
    想起されなかった記憶のmemory_daysを+1.0

    Args:
        store: MemoryStoreインスタンス
        config: 設定辞書

    Returns:
        更新された記憶の数
    """
    count = 0

    with store.connection() as conn:
        # 想起されていないアクティブ記憶を更新
        result = conn.execute('''
            UPDATE memories
            SET memory_days = memory_days + 1.0
            WHERE recalled_since_last_batch = 0 AND archived_at IS NULL
        ''')
        count = result.rowcount

    return count


def update_retention_scores(store: MemoryStore, config: dict[str, Any] | None = None) -> int:
    """
    全アクティブ記憶のretention_scoreを再計算

    Args:
        store: MemoryStoreインスタンス
        config: 設定辞書

    Returns:
        更新された記憶の数
    """
    memories = store.get_active_memories()
    count = 0

    for memory in memories:
        new_score = calculate_retention_score(
            emotional_intensity=memory["emotional_intensity"],
            decay_coefficient=memory["decay_coefficient"],
            memory_days=memory["memory_days"]
        )
        store.update_memory(memory["id"], {"retention_score": new_score})
        count += 1

    return count


def compress_memory(
    memory: dict[str, Any],
    new_level: int,
    store: MemoryStore,
    config: dict[str, Any] | None = None
) -> bool:
    """
    記憶を圧縮

    Args:
        memory: 記憶データ
        new_level: 新しいレベル
        store: MemoryStoreインスタンス
        config: 設定辞書

    Returns:
        圧縮が成功したらTrue
    """
    current_level = memory.get("current_level", 1)
    trigger = memory.get("trigger", "")
    content = memory.get("content", "")

    updates = {"current_level": new_level}

    try:
        if current_level == 1 and new_level >= 2:
            # Level 1 → 2: 要約
            new_trigger, new_content = compress_to_level2(trigger, content, config)
            updates["trigger"] = new_trigger
            updates["content"] = new_content

        if current_level <= 2 and new_level >= 3:
            # Level 2 → 3: キーワード化
            # Level 1から3に直接移行する場合も考慮
            src_trigger = updates.get("trigger", trigger)
            src_content = updates.get("content", content)
            new_trigger, new_content = compress_to_level3(src_trigger, src_content, config)
            updates["trigger"] = new_trigger
            updates["content"] = new_content

        if new_level == 4:
            # Level 4: アーカイブ
            updates["archived_at"] = datetime.now().astimezone().isoformat()

        # Embedding再生成
        final_trigger = updates.get("trigger", trigger)
        final_content = updates.get("content", content)
        embedding_text = f"{final_trigger} {final_content}"
        new_embedding = get_embedding(embedding_text, config)
        updates["embedding"] = new_embedding

    except Exception:
        # LLM/Embedding呼び出しに失敗した場合はレベルのみ更新
        pass

    store.update_memory(memory["id"], updates)
    return True


def process_compression(store: MemoryStore, config: dict[str, Any] | None = None) -> dict[str, int]:
    """
    閾値判定による圧縮処理

    Args:
        store: MemoryStoreインスタンス
        config: 設定辞書

    Returns:
        圧縮結果の辞書
    """
    if config is None:
        config = get_config()

    results = {"l1_to_l2": 0, "l2_to_l3": 0, "l3_to_archive": 0}

    memories = store.get_active_memories()

    for memory in memories:
        should, new_level = should_compress(memory, config)

        if not should:
            continue

        current_level = memory.get("current_level", 1)

        if compress_memory(memory, new_level, store, config):
            if current_level == 1 and new_level == 2:
                results["l1_to_l2"] += 1
            elif current_level == 2 and new_level == 3:
                results["l2_to_l3"] += 1
            elif new_level == 4:
                results["l3_to_archive"] += 1

    return results


def process_revival(store: MemoryStore, config: dict[str, Any] | None = None) -> int:
    """
    アーカイブ復活処理

    Args:
        store: MemoryStoreインスタンス
        config: 設定辞書

    Returns:
        復活した記憶の数
    """
    if config is None:
        config = get_config()

    archive_config = config.get("archive", {})
    revival_decay = archive_config.get("revival_decay_per_day", 0.995)
    revival_margin = archive_config.get("revival_min_margin", 3.0)

    # revival_requested = 1 の記憶を取得
    with store.connection() as conn:
        rows = conn.execute('''
            SELECT * FROM memories
            WHERE revival_requested = 1 AND archived_at IS NOT NULL
        ''').fetchall()

    revived_count = 0
    levels_config = config.get("levels", {})
    level3_threshold = levels_config.get("level3_threshold", 5)

    for row in rows:
        memory = store._row_to_dict(row)

        # アーカイブ滞在日数を計算
        archived_at = memory.get("archived_at")
        if archived_at:
            try:
                archived_dt = datetime.fromisoformat(archived_at)
                now = datetime.now().astimezone()
                days_in_archive = (now - archived_dt).days
            except (ValueError, TypeError):
                days_in_archive = 0
        else:
            days_in_archive = 0

        # 復活時のretention_score計算
        original_intensity = memory.get("emotional_intensity", 0)
        new_score = original_intensity * (revival_decay ** days_in_archive)

        # 最低マージンを確保
        min_score = level3_threshold + revival_margin
        new_score = max(new_score, min_score)

        # 復活
        store.update_memory(memory["id"], {
            "archived_at": None,
            "current_level": 3,
            "retention_score": new_score,
            "revival_requested": False,
            "revival_requested_at": None
        })
        revived_count += 1

    return revived_count


def process_auto_delete(store: MemoryStore, config: dict[str, Any] | None = None) -> int:
    """
    アーカイブ自動削除

    Args:
        store: MemoryStoreインスタンス
        config: 設定辞書

    Returns:
        削除された記憶の数
    """
    if config is None:
        config = get_config()

    archive_config = config.get("archive", {})

    if not archive_config.get("auto_delete_enabled", False):
        return 0

    retention_days = archive_config.get("retention_days", 365)
    require_zero_recall = archive_config.get("delete_require_zero_recall", True)
    max_intensity = archive_config.get("delete_max_intensity", 20)
    condition_mode = archive_config.get("delete_condition_mode", "AND")

    cutoff_date = datetime.now().astimezone() - timedelta(days=retention_days)
    cutoff_iso = cutoff_date.isoformat()

    deleted_count = 0
    archived = store.get_archived_memories()

    for memory in archived:
        # 保護記憶は削除しない
        if memory.get("protected", False):
            continue

        archived_at = memory.get("archived_at")
        if not archived_at:
            continue

        # 条件チェック
        conditions = []

        # 保持日数条件
        conditions.append(archived_at < cutoff_iso)

        # 想起回数条件
        if require_zero_recall:
            conditions.append(memory.get("recall_count", 0) == 0)

        # 感情強度条件
        conditions.append(memory.get("emotional_intensity", 100) <= max_intensity)

        # 条件結合
        if condition_mode == "AND":
            should_delete = all(conditions)
        else:  # OR
            should_delete = any(conditions)

        if should_delete:
            store.delete_memory(memory["id"])
            deleted_count += 1

    return deleted_count


def run_compression_batch(
    store: MemoryStore | None = None,
    config: dict[str, Any] | None = None,
    force: bool = False
) -> dict[str, Any]:
    """
    日次バッチ処理を実行

    Args:
        store: MemoryStoreインスタンス（Noneの場合はデフォルトパス）
        config: 設定辞書
        force: Trueの場合、interval_hoursを無視して強制実行

    Returns:
        処理結果の辞書
    """
    if config is None:
        config = get_config()

    if store is None:
        db_path = Path(__file__).parent.parent / "data" / "memories.db"
        store = MemoryStore(db_path)

    results = {
        "executed": False,
        "skipped_reason": None,
        "recalled_processed": 0,
        "memory_days_updated": 0,
        "retention_scores_updated": 0,
        "compression": {},
        "revived": 0,
        "relations": {},
        "deleted": 0
    }

    # 実行条件チェック
    if not force and not should_run_compression(store, config):
        results["skipped_reason"] = "interval_not_elapsed"
        return results

    results["executed"] = True

    # 1. 想起強化処理
    results["recalled_processed"] = process_all_recalled_memories(store, config)

    # 2. memory_days更新
    results["memory_days_updated"] = increment_memory_days(store, config)

    # 3. retention_score再計算
    results["retention_scores_updated"] = update_retention_scores(store, config)

    # 4. 閾値判定による圧縮
    results["compression"] = process_compression(store, config)

    # 5. アーカイブ復活処理
    results["revived"] = process_revival(store, config)

    # 6. 関連付け処理
    results["relations"] = process_relations(store, config=config)

    # 7. アーカイブ自動削除
    results["deleted"] = process_auto_delete(store, config)

    # 8. last_compression_run更新
    store.set_state("last_compression_run", datetime.now().astimezone().isoformat())

    return results


def get_db_stats() -> dict[str, Any]:
    """
    データベースの統計情報を取得

    Returns:
        統計情報の辞書
    """
    db_path = Path(__file__).parent.parent / "data" / "memories.db"
    store = MemoryStore(db_path)

    stats = {
        "total": store.count_memories(include_archived=True),
        "active": store.count_memories(include_archived=False),
        "by_level": store.count_by_level(),
        "protected": store.count_protected(),
        "db_size_mb": 0.0
    }

    if db_path.exists():
        stats["db_size_mb"] = db_path.stat().st_size / 1024 / 1024

    return stats


if __name__ == "__main__":
    # コマンドラインから実行可能
    import sys
    import time as time_module

    force = "--force" in sys.argv or "-f" in sys.argv
    verbose = "--verbose" in sys.argv or "-v" in sys.argv

    # 処理前の統計
    if verbose:
        pre_stats = get_db_stats()
        print(f"Pre-batch stats: {pre_stats['active']} active, {pre_stats['db_size_mb']:.2f} MB")

    # 処理時間計測
    start_time = time_module.time()
    result = run_compression_batch(force=force)
    elapsed = time_module.time() - start_time

    if result["executed"]:
        print("Compression batch completed:")
        print(f"  Elapsed time: {elapsed:.2f}s")
        print(f"  Recalled processed: {result['recalled_processed']}")
        print(f"  Memory days updated: {result['memory_days_updated']}")
        print(f"  Retention scores updated: {result['retention_scores_updated']}")
        print(f"  Compression: {result['compression']}")
        print(f"  Revived: {result['revived']}")
        print(f"  Relations: {result['relations']}")
        print(f"  Deleted: {result['deleted']}")

        # 処理後の統計
        if verbose:
            post_stats = get_db_stats()
            print(f"\nPost-batch stats:")
            print(f"  Active: {post_stats['active']} memories")
            print(f"  By level: {post_stats['by_level']}")
            print(f"  Protected: {post_stats['protected']}")
            print(f"  DB size: {post_stats['db_size_mb']:.2f} MB")

            # 警告（1GB超過時）
            if post_stats['db_size_mb'] > 1024:
                print("\n  WARNING: Database size exceeds 1GB. Consider running VACUUM.")
    else:
        print(f"Skipped: {result['skipped_reason']}")
