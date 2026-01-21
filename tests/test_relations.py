"""
test_relations.py - relations.py のテスト
"""

import pytest

from src.relations import (
    find_similar_memories,
    determine_relation_direction,
    add_relation,
    remove_relation,
)


class TestFindSimilarMemories:
    """find_similar_memories のテスト"""

    def test_find_similar_basic(self):
        """基本的な類似検索"""
        new_memory = {"id": "new", "embedding": [1.0, 0.0, 0.0]}
        all_memories = [
            {"id": "m1", "embedding": [1.0, 0.0, 0.0]},  # 完全一致
            {"id": "m2", "embedding": [0.0, 1.0, 0.0]},  # 直交
            {"id": "m3", "embedding": [0.9, 0.1, 0.0]},  # 類似
        ]

        results = find_similar_memories(new_memory, all_memories, threshold=0.8)

        # m1とm3が閾値を超える
        result_ids = [m["id"] for m, _ in results]
        assert "m1" in result_ids
        assert "m3" in result_ids
        assert "m2" not in result_ids

    def test_find_similar_no_embedding(self):
        """Embeddingがない場合"""
        new_memory = {"id": "new", "embedding": None}
        all_memories = [{"id": "m1", "embedding": [1.0, 0.0, 0.0]}]

        results = find_similar_memories(new_memory, all_memories)
        assert results == []

    def test_find_similar_empty_list(self):
        """空リストの場合"""
        new_memory = {"id": "new", "embedding": [1.0, 0.0, 0.0]}
        results = find_similar_memories(new_memory, [])
        assert results == []

    def test_find_similar_threshold(self):
        """閾値の動作確認"""
        new_memory = {"id": "new", "embedding": [1.0, 0.0, 0.0]}
        all_memories = [
            {"id": "m1", "embedding": [0.9, 0.1, 0.0]},  # 類似度約0.99
        ]

        # 高閾値では見つからない
        results = find_similar_memories(new_memory, all_memories, threshold=1.0)
        assert len(results) == 0

        # 低閾値では見つかる
        results = find_similar_memories(new_memory, all_memories, threshold=0.9)
        assert len(results) == 1


class TestDetermineRelationDirection:
    """determine_relation_direction のテスト"""

    def test_higher_score_is_source(self):
        """高スコアが参照元になる"""
        memory_a = {"id": "a", "retention_score": 80}
        memory_b = {"id": "b", "retention_score": 40}

        from_id, to_id = determine_relation_direction(memory_a, memory_b)
        assert from_id == "a"
        assert to_id == "b"

    def test_lower_score_is_target(self):
        """低スコアが参照先になる"""
        memory_a = {"id": "a", "retention_score": 30}
        memory_b = {"id": "b", "retention_score": 70}

        from_id, to_id = determine_relation_direction(memory_a, memory_b)
        assert from_id == "b"
        assert to_id == "a"

    def test_equal_scores(self):
        """同スコアの場合はAが参照元"""
        memory_a = {"id": "a", "retention_score": 50}
        memory_b = {"id": "b", "retention_score": 50}

        from_id, to_id = determine_relation_direction(memory_a, memory_b)
        assert from_id == "a"
        assert to_id == "b"

    def test_none_scores(self):
        """スコアがNoneの場合"""
        memory_a = {"id": "a", "retention_score": None}
        memory_b = {"id": "b", "retention_score": 50}

        from_id, to_id = determine_relation_direction(memory_a, memory_b)
        assert from_id == "b"
        assert to_id == "a"


class TestAddRelation:
    """add_relation のテスト"""

    def test_add_new_relation(self):
        """新規関連の追加"""
        memory = {"id": "a", "relations": ["b"]}
        new_relations = add_relation(memory, "c")
        assert "c" in new_relations
        assert len(new_relations) == 2

    def test_add_duplicate_relation(self):
        """重複関連は追加されない"""
        memory = {"id": "a", "relations": ["b"]}
        new_relations = add_relation(memory, "b")
        assert len(new_relations) == 1

    def test_add_to_empty(self):
        """空リストへの追加"""
        memory = {"id": "a", "relations": []}
        new_relations = add_relation(memory, "b")
        assert new_relations == ["b"]

    def test_max_relations_limit(self):
        """上限チェック"""
        memory = {"id": "a", "relations": ["b", "c", "d"]}
        new_relations = add_relation(memory, "e", max_relations=3)
        # 上限に達しているので追加されない
        assert len(new_relations) == 3
        assert "e" not in new_relations


class TestRemoveRelation:
    """remove_relation のテスト"""

    def test_remove_existing(self):
        """存在する関連の削除"""
        memory = {"id": "a", "relations": ["b", "c"]}
        new_relations = remove_relation(memory, "b")
        assert "b" not in new_relations
        assert "c" in new_relations

    def test_remove_nonexistent(self):
        """存在しない関連の削除"""
        memory = {"id": "a", "relations": ["b"]}
        new_relations = remove_relation(memory, "x")
        assert new_relations == ["b"]

    def test_remove_from_empty(self):
        """空リストからの削除"""
        memory = {"id": "a", "relations": []}
        new_relations = remove_relation(memory, "b")
        assert new_relations == []
