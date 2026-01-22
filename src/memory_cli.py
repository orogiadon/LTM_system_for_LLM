#!/usr/bin/env python3
"""
memory_cli.py - 記憶管理CLIツール

記憶の一覧表示、削除、保護設定、統計表示などを行う。

使い方:
    python src/memory_cli.py list [--level N] [--archived] [--protected] [--limit N]
    python src/memory_cli.py show <memory_id>
    python src/memory_cli.py delete <memory_id> [--force]
    python src/memory_cli.py protect <memory_id>
    python src/memory_cli.py unprotect <memory_id>
    python src/memory_cli.py stats
    python src/memory_cli.py search <query>
"""

import argparse
import io
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Windows対応: UTF-8出力
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# パスを追加してモジュールをインポート可能に
sys.path.insert(0, str(Path(__file__).parent))

from memory_store import MemoryStore


def get_store() -> MemoryStore:
    """MemoryStoreインスタンスを取得"""
    db_path = Path(__file__).parent.parent / "data" / "memories.db"
    return MemoryStore(db_path)


def format_date(iso_date: str | None) -> str:
    """ISO日付を短い形式に変換"""
    if not iso_date:
        return "-"
    if "T" in iso_date:
        return iso_date.split("T")[0]
    return iso_date


def truncate(text: str, max_len: int = 50) -> str:
    """テキストを指定長に切り詰め"""
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


def cmd_list(args: argparse.Namespace) -> None:
    """記憶一覧を表示"""
    store = get_store()

    if args.archived:
        memories = store.get_archived_memories()
    else:
        memories = store.get_active_memories()

    # フィルタリング
    if args.level is not None:
        memories = [m for m in memories if m.get("current_level") == args.level]
    if args.protected:
        memories = [m for m in memories if m.get("protected")]

    # ソート（retention_score降順）
    memories.sort(key=lambda m: m.get("retention_score", 0) or 0, reverse=True)

    # 件数制限
    if args.limit:
        memories = memories[:args.limit]

    if not memories:
        print("No memories found.")
        return

    # ヘッダー
    print(f"{'ID':<25} {'Date':<12} {'L':>2} {'Score':>7} {'P':>1} {'Trigger':<40}")
    print("-" * 95)

    for mem in memories:
        mem_id = mem.get("id", "")[:24]
        date = format_date(mem.get("created"))
        level = mem.get("current_level", 1)
        score = mem.get("retention_score", 0) or 0
        protected = "P" if mem.get("protected") else ""
        trigger = truncate(mem.get("trigger", ""), 40)

        print(f"{mem_id:<25} {date:<12} {level:>2} {score:>7.1f} {protected:>1} {trigger:<40}")

    print(f"\nTotal: {len(memories)} memories")


def cmd_show(args: argparse.Namespace) -> None:
    """記憶の詳細を表示"""
    store = get_store()
    mem = store.get_memory(args.memory_id)

    if not mem:
        print(f"Memory not found: {args.memory_id}")
        sys.exit(1)

    print(f"ID:                 {mem.get('id')}")
    print(f"Created:            {mem.get('created')}")
    print(f"Level:              {mem.get('current_level')}")
    print(f"Retention Score:    {mem.get('retention_score', 0):.2f}")
    print(f"Memory Days:        {mem.get('memory_days', 0):.2f}")
    print(f"Decay Coefficient:  {mem.get('decay_coefficient', 0):.4f}")
    print(f"Recall Count:       {mem.get('recall_count', 0)}")
    print(f"Protected:          {'Yes' if mem.get('protected') else 'No'}")
    print(f"Archived:           {mem.get('archived_at') or 'No'}")
    print(f"Category:           {mem.get('category')}")
    print(f"Emotional Intensity:{mem.get('emotional_intensity')}")
    print(f"Emotional Valence:  {mem.get('emotional_valence')}")
    print(f"Emotional Arousal:  {mem.get('emotional_arousal')}")
    print(f"Emotional Tags:     {', '.join(mem.get('emotional_tags', []))}")
    print(f"Keywords:           {', '.join(mem.get('keywords', []))}")
    print(f"Relations:          {', '.join(mem.get('relations', []))}")
    print()
    print("--- Trigger ---")
    print(mem.get("trigger", ""))
    print()
    print("--- Content ---")
    print(mem.get("content", ""))


def cmd_delete(args: argparse.Namespace) -> None:
    """記憶を削除"""
    store = get_store()
    mem = store.get_memory(args.memory_id)

    if not mem:
        print(f"Memory not found: {args.memory_id}")
        sys.exit(1)

    if mem.get("protected") and not args.force:
        print(f"Memory is protected. Use --force to delete.")
        sys.exit(1)

    if not args.force:
        print(f"Delete memory: {args.memory_id}")
        print(f"  Trigger: {truncate(mem.get('trigger', ''), 60)}")
        confirm = input("Are you sure? (y/N): ")
        if confirm.lower() != "y":
            print("Cancelled.")
            return

    store.delete_memory(args.memory_id)
    print(f"Deleted: {args.memory_id}")


def cmd_protect(args: argparse.Namespace) -> None:
    """記憶を保護"""
    store = get_store()
    mem = store.get_memory(args.memory_id)

    if not mem:
        print(f"Memory not found: {args.memory_id}")
        sys.exit(1)

    if mem.get("protected"):
        print(f"Memory is already protected.")
        return

    store.update_memory(args.memory_id, {"protected": True})
    print(f"Protected: {args.memory_id}")


def cmd_unprotect(args: argparse.Namespace) -> None:
    """記憶の保護を解除"""
    store = get_store()
    mem = store.get_memory(args.memory_id)

    if not mem:
        print(f"Memory not found: {args.memory_id}")
        sys.exit(1)

    if not mem.get("protected"):
        print(f"Memory is not protected.")
        return

    store.update_memory(args.memory_id, {"protected": False})
    print(f"Unprotected: {args.memory_id}")


def cmd_stats(args: argparse.Namespace) -> None:
    """統計情報を表示"""
    store = get_store()

    # 基本統計
    total = store.count_memories(include_archived=True)
    active = store.count_memories(include_archived=False)
    archived = total - active
    protected = store.count_protected()
    by_level = store.count_by_level()

    # 追加統計（直接クエリ）
    with store.connection() as conn:
        # 最近の想起
        recalled_row = conn.execute(
            "SELECT COUNT(*) as count FROM memories WHERE recalled_since_last_batch = 1"
        ).fetchone()
        recalled = recalled_row["count"] if recalled_row else 0

        # 平均retention_score
        avg_row = conn.execute(
            "SELECT AVG(retention_score) as avg FROM memories WHERE archived_at IS NULL"
        ).fetchone()
        avg_score = avg_row["avg"] if avg_row and avg_row["avg"] else 0

        # カテゴリ別
        cat_rows = conn.execute("""
            SELECT category, COUNT(*) as count
            FROM memories
            WHERE archived_at IS NULL
            GROUP BY category
        """).fetchall()
        by_category = {row["category"]: row["count"] for row in cat_rows}

        # DBファイルサイズ
        db_path = Path(__file__).parent.parent / "data" / "memories.db"
        db_size = db_path.stat().st_size if db_path.exists() else 0

    print("=== Memory Statistics ===")
    print()
    print(f"Total Memories:     {total}")
    print(f"  Active:           {active}")
    print(f"  Archived:         {archived}")
    print(f"  Protected:        {protected}")
    print()
    print("By Level (Active):")
    for level in sorted(by_level.keys()):
        count = by_level[level]
        pct = (count / active * 100) if active > 0 else 0
        print(f"  Level {level}:          {count:>5} ({pct:>5.1f}%)")
    print()
    print("By Category (Active):")
    for cat in ["casual", "work", "decision", "emotional"]:
        count = by_category.get(cat, 0)
        pct = (count / active * 100) if active > 0 else 0
        print(f"  {cat:<12}      {count:>5} ({pct:>5.1f}%)")
    print()
    print(f"Avg Retention Score: {avg_score:.2f}")
    print(f"Pending Recall:      {recalled}")
    print(f"Database Size:       {db_size / 1024 / 1024:.2f} MB")


def cmd_search(args: argparse.Namespace) -> None:
    """キーワードで記憶を検索"""
    store = get_store()
    query = args.query.lower()

    memories = store.get_all_memories(include_archived=not args.active_only)

    # テキスト検索
    results = []
    for mem in memories:
        trigger = (mem.get("trigger") or "").lower()
        content = (mem.get("content") or "").lower()
        keywords = [k.lower() for k in mem.get("keywords", [])]

        if query in trigger or query in content or query in keywords:
            results.append(mem)

    # ソート
    results.sort(key=lambda m: m.get("retention_score", 0) or 0, reverse=True)

    if args.limit:
        results = results[:args.limit]

    if not results:
        print(f"No memories found for: {args.query}")
        return

    print(f"Found {len(results)} memories for '{args.query}':")
    print()
    print(f"{'ID':<25} {'Date':<12} {'L':>2} {'Score':>7} {'Trigger':<40}")
    print("-" * 90)

    for mem in results:
        mem_id = mem.get("id", "")[:24]
        date = format_date(mem.get("created"))
        level = mem.get("current_level", 1)
        score = mem.get("retention_score", 0) or 0
        trigger = truncate(mem.get("trigger", ""), 40)
        archived = "[A]" if mem.get("archived_at") else ""

        print(f"{mem_id:<25} {date:<12} {level:>2} {score:>7.1f} {archived}{trigger:<40}")


def cmd_purge_archive(args: argparse.Namespace) -> None:
    """アーカイブ記憶を全削除"""
    store = get_store()
    archived = store.get_archived_memories()

    if not archived:
        print("No archived memories to delete.")
        return

    # 保護記憶を除外
    to_delete = [m for m in archived if not m.get("protected")]
    protected_count = len(archived) - len(to_delete)

    if not to_delete:
        print(f"All {len(archived)} archived memories are protected. Nothing to delete.")
        return

    print(f"Found {len(to_delete)} archived memories to delete.")
    if protected_count > 0:
        print(f"  ({protected_count} protected memories will be preserved)")

    if not args.force:
        confirm = input("Are you sure you want to delete ALL archived memories? (yes/N): ")
        if confirm.lower() != "yes":
            print("Cancelled.")
            return

    deleted = 0
    for mem in to_delete:
        store.delete_memory(mem["id"])
        deleted += 1

    print(f"Deleted {deleted} archived memories.")


def main():
    parser = argparse.ArgumentParser(
        description="Memory Management CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # list
    list_parser = subparsers.add_parser("list", help="List memories")
    list_parser.add_argument("--level", "-l", type=int, help="Filter by level (1-4)")
    list_parser.add_argument("--archived", "-a", action="store_true", help="Show archived memories")
    list_parser.add_argument("--protected", "-p", action="store_true", help="Show only protected")
    list_parser.add_argument("--limit", "-n", type=int, default=20, help="Limit results (default: 20)")

    # show
    show_parser = subparsers.add_parser("show", help="Show memory details")
    show_parser.add_argument("memory_id", help="Memory ID")

    # delete
    delete_parser = subparsers.add_parser("delete", help="Delete a memory")
    delete_parser.add_argument("memory_id", help="Memory ID")
    delete_parser.add_argument("--force", "-f", action="store_true", help="Force delete (skip confirmation)")

    # protect
    protect_parser = subparsers.add_parser("protect", help="Protect a memory")
    protect_parser.add_argument("memory_id", help="Memory ID")

    # unprotect
    unprotect_parser = subparsers.add_parser("unprotect", help="Unprotect a memory")
    unprotect_parser.add_argument("memory_id", help="Memory ID")

    # stats
    subparsers.add_parser("stats", help="Show statistics")

    # search
    search_parser = subparsers.add_parser("search", help="Search memories by keyword")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--active-only", "-a", action="store_true", help="Search active only")
    search_parser.add_argument("--limit", "-n", type=int, default=20, help="Limit results")

    # purge-archive
    purge_parser = subparsers.add_parser("purge-archive", help="Delete ALL archived memories")
    purge_parser.add_argument("--force", "-f", action="store_true", help="Skip confirmation")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "list": cmd_list,
        "show": cmd_show,
        "delete": cmd_delete,
        "protect": cmd_protect,
        "unprotect": cmd_unprotect,
        "stats": cmd_stats,
        "search": cmd_search,
        "purge-archive": cmd_purge_archive,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
