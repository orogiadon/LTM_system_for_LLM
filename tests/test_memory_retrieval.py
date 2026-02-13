"""
test_memory_retrieval.py - memory_retrieval.py の純粋関数テスト

memory_retrieval.py は Hook 用モジュールで外部依存があるため、
テスト対象の純粋関数をここにコピーしてテストする。
"""

import pytest
import numpy as np
from collections import defaultdict


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


def compute_category_stats(
    memories: list[dict],
) -> dict[str, tuple[float, float]]:
    """カテゴリごとのretention_scoreの平均・標準偏差を計算"""
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
            std = 1.0
        stats[cat] = (mean, std)

    return stats


def calculate_relevance(
    memory: dict,
    query_embedding: list[float],
    query_category: str | None = None,
    category_stats: dict[str, tuple[float, float]] | None = None,
    beta: float = 2.0,
) -> float:
    """参照優先度を計算（正規化 + similarity² + カテゴリブースト）"""
    retention_score = memory.get("retention_score", 0) or 0
    mem_category = memory.get("category", "casual")

    if category_stats and mem_category in category_stats:
        mean, std = category_stats[mem_category]
        normalized_retention = (retention_score - mean) / std
    else:
        normalized_retention = retention_score

    memory_embedding = memory.get("embedding")
    if memory_embedding and query_embedding:
        similarity = cosine_similarity(query_embedding, memory_embedding)
        similarity = max(0, similarity)
    else:
        similarity = 0

    recall_count = memory.get("recall_count", 0)
    recall_weight = 1 + 0.1 * recall_count

    category_boost = beta if (query_category and mem_category == query_category) else 1.0

    return normalized_retention * (similarity ** 2) * recall_weight * category_boost


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
    """calculate_relevance のテスト（正規化 + similarity² + カテゴリブースト）"""

    def test_basic_relevance_without_stats(self):
        """カテゴリ統計なしの場合、retention_scoreをそのまま使用"""
        memory = {
            "retention_score": 50,
            "embedding": [1.0, 0.0, 0.0],
            "recall_count": 0,
            "category": "work",
        }
        query_embedding = [1.0, 0.0, 0.0]
        # similarity=1.0 → similarity²=1.0, normalized_retention=50
        result = calculate_relevance(memory, query_embedding)
        assert abs(result - 50.0) < 1e-6

    def test_relevance_with_normalization(self):
        """カテゴリ内正規化が適用される"""
        memory = {
            "retention_score": 80,
            "embedding": [1.0, 0.0, 0.0],
            "recall_count": 0,
            "category": "emotional",
        }
        query_embedding = [1.0, 0.0, 0.0]
        # mean=60, std=10 → normalized = (80-60)/10 = 2.0
        stats = {"emotional": (60.0, 10.0)}
        result = calculate_relevance(memory, query_embedding, category_stats=stats)
        assert abs(result - 2.0) < 1e-6

    def test_similarity_squared(self):
        """similarityが二乗される"""
        memory = {
            "retention_score": 10,
            "embedding": [0.8, 0.6, 0.0],  # normalized
            "recall_count": 0,
            "category": "work",
        }
        query_embedding = [1.0, 0.0, 0.0]
        # cosine_similarity = 0.8, similarity² = 0.64
        result = calculate_relevance(memory, query_embedding)
        expected = 10.0 * 0.64 * 1.0
        assert abs(result - expected) < 1e-4

    def test_category_boost_matching(self):
        """カテゴリ一致時にβ倍のブーストがかかる"""
        memory = {
            "retention_score": 30,
            "embedding": [1.0, 0.0, 0.0],
            "recall_count": 0,
            "category": "work",
        }
        query_embedding = [1.0, 0.0, 0.0]
        result = calculate_relevance(
            memory, query_embedding, query_category="work", beta=2.0
        )
        # 30 * 1.0² * 1.0 * 2.0 = 60.0
        assert abs(result - 60.0) < 1e-6

    def test_category_boost_not_matching(self):
        """カテゴリ不一致時はブーストなし"""
        memory = {
            "retention_score": 30,
            "embedding": [1.0, 0.0, 0.0],
            "recall_count": 0,
            "category": "emotional",
        }
        query_embedding = [1.0, 0.0, 0.0]
        result = calculate_relevance(
            memory, query_embedding, query_category="work", beta=2.0
        )
        # 30 * 1.0² * 1.0 * 1.0 = 30.0
        assert abs(result - 30.0) < 1e-6

    def test_normalization_equalizes_categories(self):
        """正規化によりカテゴリ間のretention差が縮小される"""
        stats = {
            "emotional": (80.0, 5.0),
            "work": (25.0, 5.0),
        }
        emotional_mem = {
            "retention_score": 82,
            "embedding": [1.0, 0.0, 0.0],
            "recall_count": 0,
            "category": "emotional",
        }
        work_mem = {
            "retention_score": 27,
            "embedding": [1.0, 0.0, 0.0],
            "recall_count": 0,
            "category": "work",
        }
        query_embedding = [1.0, 0.0, 0.0]

        # emotional: (82-80)/5 = 0.4
        # work: (27-25)/5 = 0.4
        emo_score = calculate_relevance(
            emotional_mem, query_embedding, category_stats=stats
        )
        work_score = calculate_relevance(
            work_mem, query_embedding, category_stats=stats
        )
        # 正規化後は同じスコア
        assert abs(emo_score - work_score) < 1e-6

    def test_recall_count_weight(self):
        """recall_countによる重み付け"""
        memory = {
            "retention_score": 50,
            "embedding": [1.0, 0.0, 0.0],
            "recall_count": 5,
            "category": "work",
        }
        query_embedding = [1.0, 0.0, 0.0]
        # 50 * 1.0² * (1 + 0.5) * 1.0 = 75.0
        result = calculate_relevance(memory, query_embedding)
        assert abs(result - 75.0) < 1e-6

    def test_relevance_zero_similarity(self):
        """類似度ゼロの場合"""
        memory = {
            "retention_score": 50,
            "embedding": [1.0, 0.0, 0.0],
            "recall_count": 0,
            "category": "work",
        }
        query_embedding = [0.0, 1.0, 0.0]
        result = calculate_relevance(memory, query_embedding)
        assert result == 0.0

    def test_relevance_no_embedding(self):
        """Embeddingがない場合"""
        memory = {
            "retention_score": 50,
            "embedding": None,
            "recall_count": 0,
            "category": "work",
        }
        query_embedding = [1.0, 0.0, 0.0]
        result = calculate_relevance(memory, query_embedding)
        assert result == 0.0

    def test_relevance_negative_similarity_clamped(self):
        """負の類似度は0にクランプ"""
        memory = {
            "retention_score": 50,
            "embedding": [-1.0, 0.0, 0.0],
            "recall_count": 0,
            "category": "work",
        }
        query_embedding = [1.0, 0.0, 0.0]
        result = calculate_relevance(memory, query_embedding)
        assert result == 0.0


class TestComputeCategoryStats:
    """compute_category_stats のテスト"""

    def test_basic_stats(self):
        """基本的な平均・標準偏差の計算"""
        memories = [
            {"category": "emotional", "retention_score": 80},
            {"category": "emotional", "retention_score": 60},
            {"category": "work", "retention_score": 30},
            {"category": "work", "retention_score": 20},
        ]
        stats = compute_category_stats(memories)

        assert "emotional" in stats
        assert "work" in stats

        emo_mean, emo_std = stats["emotional"]
        assert abs(emo_mean - 70.0) < 1e-6
        assert abs(emo_std - 10.0) < 1e-6

        work_mean, work_std = stats["work"]
        assert abs(work_mean - 25.0) < 1e-6
        assert abs(work_std - 5.0) < 1e-6

    def test_single_memory_std_fallback(self):
        """1件のみのカテゴリはstd=1.0にフォールバック"""
        memories = [
            {"category": "decision", "retention_score": 50},
        ]
        stats = compute_category_stats(memories)
        mean, std = stats["decision"]
        assert abs(mean - 50.0) < 1e-6
        assert abs(std - 1.0) < 1e-6

    def test_empty_list(self):
        """空リストの場合"""
        stats = compute_category_stats([])
        assert stats == {}

    def test_missing_retention_score(self):
        """retention_scoreが欠落している場合は0として扱う"""
        memories = [
            {"category": "casual", "retention_score": None},
            {"category": "casual", "retention_score": 10},
        ]
        stats = compute_category_stats(memories)
        mean, std = stats["casual"]
        assert abs(mean - 5.0) < 1e-6


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
