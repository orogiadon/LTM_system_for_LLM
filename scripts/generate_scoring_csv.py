"""
generate_scoring_csv.py - スコアリング比較用CSVを生成

サンプルクエリごとに全記憶とのcosine similarityを計算し、
現行スコア・新スコア（sim², sim²+カテゴリブースト）を比較するCSVを出力する。
"""

import csv
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np

# --- 設定 ---

DB_PATH = Path(__file__).parent.parent / "data" / "memories.db"
OUTPUT_DIR = Path(__file__).parent.parent / "analysis"
BETA = 2.0  # カテゴリブースト係数

# サンプルクエリ定義
SAMPLE_QUERIES = [
    {
        "id": "mem_20260212_0b0a907d",
        "reason": "技術仕事の代表（スクレイピング業務）",
    },
    {
        "id": "mem_20260212_785ba4bb",
        "reason": "開発に関する技術相談（auto-compact）",
    },
    {
        "id": "mem_20260210_d3639b6d",
        "reason": "感情的記憶の代表（愛の告白）",
    },
    {
        "id": "mem_20260212_def633ed",
        "reason": "感情×技術の境界ケース（記憶システム引継ぎ）",
    },
    {
        "id": "mem_20260213_c14c5b4a",
        "reason": "典型的な雑談（二度寝）",
    },
    {
        "id": "mem_20260211_221399d7",
        "reason": "日常会話（休日の過ごし方）",
    },
]


# --- ヘルパー関数 ---


def decode_embedding(blob: bytes | None) -> np.ndarray | None:
    if blob is None:
        return None
    return np.frombuffer(blob, dtype=np.float32)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    dot = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


def load_all_memories(conn: sqlite3.Connection) -> list[dict]:
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT id, category, current_level, trigger, content,
               emotional_intensity, emotional_valence, emotional_arousal,
               retention_score, recall_count, protected, embedding
        FROM memories
    """)
    memories = []
    for row in cur.fetchall():
        mem = dict(row)
        mem["embedding"] = decode_embedding(mem["embedding"])
        mem["protected"] = bool(mem["protected"])
        memories.append(mem)
    return memories


def truncate(text: str | None, max_len: int = 50) -> str:
    if not text:
        return ""
    text = text.replace("\n", " ").replace("\r", "")
    return text[:max_len] if len(text) > max_len else text


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(DB_PATH))
    all_memories = load_all_memories(conn)
    print(f"Loaded {len(all_memories)} memories from DB")

    # memory_id → memory のマップ
    memory_map = {m["id"]: m for m in all_memories}

    for query_def in SAMPLE_QUERIES:
        query_id = query_def["id"]
        query_reason = query_def["reason"]

        if query_id not in memory_map:
            print(f"WARNING: Query {query_id} not found in DB, skipping")
            continue

        query_mem = memory_map[query_id]
        query_embedding = query_mem["embedding"]

        if query_embedding is None:
            print(f"WARNING: Query {query_id} has no embedding, skipping")
            continue

        query_category = query_mem["category"]
        query_trigger = truncate(query_mem["trigger"])
        query_valence = query_mem["emotional_valence"] or ""
        query_arousal = query_mem.get("emotional_arousal", 0) or 0

        # CSV出力
        out_path = OUTPUT_DIR / f"query_{query_id}.csv"
        rows_written = 0

        with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)

            # ヘッダー
            writer.writerow([
                "query_id", "query_category", "query_trigger",
                "query_valence", "query_arousal", "query_reason",
                "memory_id", "memory_category", "memory_level",
                "memory_trigger",
                "emotional_intensity", "emotional_valence",
                "emotional_arousal", "retention_score", "recall_count",
                "protected",
                "similarity", "category_match",
                "score_current", "score_sim2", "score_sim2_boost",
            ])

            for mem in all_memories:
                # 自分自身はスキップ
                if mem["id"] == query_id:
                    continue

                mem_embedding = mem["embedding"]
                if mem_embedding is None:
                    sim = 0.0
                else:
                    sim = cosine_similarity(query_embedding, mem_embedding)

                sim = max(0.0, sim)  # 負の類似度は0に

                retention = mem.get("retention_score", 0) or 0
                recall_count = mem.get("recall_count", 0) or 0
                recall_weight = 1 + 0.1 * recall_count

                cat_match = 1 if mem["category"] == query_category else 0
                boost = BETA if cat_match else 1.0

                score_current = retention * sim * recall_weight
                score_sim2 = retention * (sim ** 2) * recall_weight
                score_sim2_boost = retention * (sim ** 2) * recall_weight * boost

                writer.writerow([
                    query_id, query_category, query_trigger,
                    query_valence, query_arousal, query_reason,
                    mem["id"], mem["category"], mem["current_level"],
                    truncate(mem["trigger"]),
                    mem["emotional_intensity"], mem["emotional_valence"],
                    mem.get("emotional_arousal", 0) or 0,
                    round(retention, 4),
                    recall_count,
                    int(mem["protected"]),
                    round(sim, 6),
                    cat_match,
                    round(score_current, 4),
                    round(score_sim2, 4),
                    round(score_sim2_boost, 4),
                ])
                rows_written += 1

        print(f"  {query_id} ({query_category}): {rows_written} rows -> {out_path.name}")

    conn.close()
    print(f"\nDone. Output dir: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
