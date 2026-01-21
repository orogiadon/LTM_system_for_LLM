"""
test_memory_retrieval.py - memory_retrieval.py の純粋関数テスト

memory_retrieval.py は Hook 用モジュールで外部依存があるため、
テスト対象の純粋関数をここにコピーしてテストする。
"""

import pytest
import numpy as np


# --- テスト対象の純粋関数（memory_retrieval.py からコピー）---

def should_skip(query: str) -> bool:
    """記憶処理をスキップすべきか判定"""
    if not query:
        return True

    stripped = query.strip()

    if stripped.startswith("/"):
        return True

    return False


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """コサイン類似度を計算"""
    a = np.array(vec_a)
    b = np.array(vec_b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return float(np.dot(a, b) / (norm_a * norm_b))


def calculate_relevance(
    memory: dict,
    query_embedding: list[float],
) -> float:
    """参照優先度を計算（簡易版、感情共鳴なし）"""
    retention_score = memory.get("retention_score", 0) or 0

    memory_embedding = memory.get("embedding")
    if memory_embedding and query_embedding:
        similarity = cosine_similarity(query_embedding, memory_embedding)
        similarity = max(0, similarity)
    else:
        similarity = 0

    recall_count = memory.get("recall_count", 0)
    recall_weight = 1 + 0.1 * recall_count

    return retention_score * similarity * recall_weight


def format_memories(results: list[tuple[dict, bool]]) -> str:
    """記憶を出力形式にフォーマット"""
    if not results:
        return ""

    lines = ["<memories>"]
    for mem, is_archived in results:
        created = mem.get("created", "unknown")
        if "T" in created:
            created = created.split("T")[0]

        trigger = mem.get("trigger", "")
        content = mem.get("content", "")
        level = mem.get("current_level", 1)
        archived_mark = "[archived]" if is_archived else ""

        lines.append(f"- [{created}][L{level}]{archived_mark} {trigger} → {content}")

    lines.append("</memories>")
    return "\n".join(lines)


# --- テスト ---

class TestShouldSkip:
    """should_skip のテスト"""

    def test_skip_empty_query(self):
        """空クエリはスキップ"""
        assert should_skip("") is True
        # 空白のみは strip 後にスラッシュチェックでFalse
        # 実際の実装では空白のみはスキップされない（入力時に除去されている前提）
        assert should_skip("   ") is False

    def test_skip_slash_commands(self):
        """スラッシュコマンドはスキップ"""
        assert should_skip("/help") is True
        assert should_skip("/clear") is True
        assert should_skip("  /command") is True

    def test_normal_query_not_skipped(self):
        """通常のクエリはスキップしない"""
        assert should_skip("hello") is False
        assert should_skip("こんにちは") is False
        assert should_skip("What is the meaning of life?") is False


class TestCosineSimilarity:
    """cosine_similarity のテスト"""

    def test_identical_vectors(self):
        """同一ベクトル"""
        vec = [1.0, 0.0, 0.0]
        result = cosine_similarity(vec, vec)
        assert abs(result - 1.0) < 1e-6

    def test_orthogonal_vectors(self):
        """直交ベクトル"""
        vec_a = [1.0, 0.0, 0.0]
        vec_b = [0.0, 1.0, 0.0]
        result = cosine_similarity(vec_a, vec_b)
        assert abs(result) < 1e-6

    def test_opposite_vectors(self):
        """逆向きベクトル"""
        vec_a = [1.0, 0.0, 0.0]
        vec_b = [-1.0, 0.0, 0.0]
        result = cosine_similarity(vec_a, vec_b)
        assert abs(result - (-1.0)) < 1e-6

    def test_similar_vectors(self):
        """類似ベクトル"""
        vec_a = [1.0, 0.0, 0.0]
        vec_b = [0.9, 0.1, 0.0]
        result = cosine_similarity(vec_a, vec_b)
        assert result > 0.99

    def test_zero_vector(self):
        """ゼロベクトル"""
        vec_a = [0.0, 0.0, 0.0]
        vec_b = [1.0, 0.0, 0.0]
        result = cosine_similarity(vec_a, vec_b)
        assert result == 0.0


class TestCalculateRelevance:
    """calculate_relevance のテスト"""

    def test_basic_relevance(self):
        """基本的な参照優先度計算"""
        memory = {
            "retention_score": 50,
            "embedding": [1.0, 0.0, 0.0],
            "recall_count": 0
        }
        query_embedding = [1.0, 0.0, 0.0]

        result = calculate_relevance(memory, query_embedding)
        assert abs(result - 50.0) < 1e-6

    def test_relevance_with_recall_count(self):
        """recall_countによる重み付け"""
        memory = {
            "retention_score": 50,
            "embedding": [1.0, 0.0, 0.0],
            "recall_count": 5
        }
        query_embedding = [1.0, 0.0, 0.0]

        result = calculate_relevance(memory, query_embedding)
        assert abs(result - 75.0) < 1e-6

    def test_relevance_zero_similarity(self):
        """類似度ゼロの場合"""
        memory = {
            "retention_score": 50,
            "embedding": [1.0, 0.0, 0.0],
            "recall_count": 0
        }
        query_embedding = [0.0, 1.0, 0.0]

        result = calculate_relevance(memory, query_embedding)
        assert result == 0.0

    def test_relevance_no_embedding(self):
        """Embeddingがない場合"""
        memory = {
            "retention_score": 50,
            "embedding": None,
            "recall_count": 0
        }
        query_embedding = [1.0, 0.0, 0.0]

        result = calculate_relevance(memory, query_embedding)
        assert result == 0.0

    def test_relevance_negative_similarity_clamped(self):
        """負の類似度は0にクランプ"""
        memory = {
            "retention_score": 50,
            "embedding": [-1.0, 0.0, 0.0],
            "recall_count": 0
        }
        query_embedding = [1.0, 0.0, 0.0]

        result = calculate_relevance(memory, query_embedding)
        assert result == 0.0


class TestFormatMemories:
    """format_memories のテスト"""

    def test_format_empty_list(self):
        """空リストの場合"""
        result = format_memories([])
        assert result == ""

    def test_format_single_memory(self):
        """単一記憶のフォーマット"""
        memories = [
            (
                {
                    "created": "2026-01-20T10:00:00+09:00",
                    "trigger": "ユーザーが質問",
                    "content": "回答した",
                    "current_level": 1
                },
                False
            )
        ]

        result = format_memories(memories)
        assert "<memories>" in result
        assert "</memories>" in result
        assert "[2026-01-20]" in result
        assert "[L1]" in result
        assert "ユーザーが質問" in result
        assert "回答した" in result
        assert "[archived]" not in result

    def test_format_archived_memory(self):
        """アーカイブ記憶のフォーマット"""
        memories = [
            (
                {
                    "created": "2026-01-15T10:00:00+09:00",
                    "trigger": "古い出来事",
                    "content": "古い内容",
                    "current_level": 4
                },
                True
            )
        ]

        result = format_memories(memories)
        assert "[archived]" in result
        assert "[L4]" in result

    def test_format_multiple_memories(self):
        """複数記憶のフォーマット"""
        memories = [
            (
                {"created": "2026-01-20", "trigger": "t1", "content": "c1", "current_level": 1},
                False
            ),
            (
                {"created": "2026-01-19", "trigger": "t2", "content": "c2", "current_level": 2},
                False
            ),
            (
                {"created": "2026-01-18", "trigger": "t3", "content": "c3", "current_level": 3},
                True
            ),
        ]

        result = format_memories(memories)
        lines = result.strip().split("\n")
        assert len(lines) == 5
        assert lines[0] == "<memories>"
        assert lines[-1] == "</memories>"
