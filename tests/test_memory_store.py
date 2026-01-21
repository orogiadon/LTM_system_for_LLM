"""
test_memory_store.py - memory_store.py のテスト
"""

import pytest
import tempfile
from pathlib import Path

from src.memory_store import MemoryStore


@pytest.fixture
def temp_db():
    """一時的なDBファイルを作成"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield f.name
    # テスト後にファイルを削除
    Path(f.name).unlink(missing_ok=True)
    Path(f"{f.name}-wal").unlink(missing_ok=True)
    Path(f"{f.name}-shm").unlink(missing_ok=True)


@pytest.fixture
def store(temp_db):
    """MemoryStoreインスタンスを作成"""
    return MemoryStore(temp_db)


@pytest.fixture
def sample_memory():
    """サンプル記憶データ"""
    return {
        "id": "mem_test_001",
        "created": "2026-01-21T12:00:00+09:00",
        "memory_days": 0.0,
        "recalled_since_last_batch": False,
        "recall_count": 0,
        "emotional_intensity": 50,
        "emotional_valence": "positive",
        "emotional_arousal": 40,
        "emotional_tags": ["happy", "curious"],
        "decay_coefficient": 0.995,
        "category": "work",
        "keywords": ["test", "memory"],
        "current_level": 1,
        "trigger": "テストの実行について相談された",
        "content": "テストの書き方について説明した",
        "embedding": [0.1] * 1536,  # ダミーEmbedding
        "relations": [],
        "retention_score": 50.0,
        "archived_at": None,
        "protected": False,
    }


class TestMemoryStoreInit:
    """MemoryStore初期化のテスト"""

    def test_init_creates_db(self, temp_db):
        """DBファイルが作成される"""
        store = MemoryStore(temp_db)
        assert Path(temp_db).exists()

    def test_init_creates_tables(self, store):
        """テーブルが作成される"""
        with store.connection() as conn:
            # memoriesテーブルの存在確認
            result = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='memories'"
            ).fetchone()
            assert result is not None

            # stateテーブルの存在確認
            result = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='state'"
            ).fetchone()
            assert result is not None


class TestAddMemory:
    """add_memory のテスト"""

    def test_add_memory_basic(self, store, sample_memory):
        """基本的な記憶追加"""
        store.add_memory(sample_memory)
        memories = store.get_active_memories()
        assert len(memories) == 1
        assert memories[0]["id"] == "mem_test_001"

    def test_add_memory_fields(self, store, sample_memory):
        """全フィールドが正しく保存される"""
        store.add_memory(sample_memory)
        memory = store.get_memory("mem_test_001")

        assert memory["emotional_intensity"] == 50
        assert memory["emotional_valence"] == "positive"
        assert memory["category"] == "work"
        assert memory["trigger"] == "テストの実行について相談された"
        assert memory["protected"] is False

    def test_add_memory_json_fields(self, store, sample_memory):
        """JSONフィールドが正しくパースされる"""
        store.add_memory(sample_memory)
        memory = store.get_memory("mem_test_001")

        assert memory["emotional_tags"] == ["happy", "curious"]
        assert memory["keywords"] == ["test", "memory"]
        assert memory["relations"] == []

    def test_add_memory_embedding(self, store, sample_memory):
        """Embeddingが正しく保存・復元される"""
        store.add_memory(sample_memory)
        memory = store.get_memory("mem_test_001")

        assert memory["embedding"] is not None
        assert len(memory["embedding"]) == 1536
        assert abs(memory["embedding"][0] - 0.1) < 0.0001


class TestGetMemories:
    """記憶取得のテスト"""

    def test_get_active_memories(self, store, sample_memory):
        """アクティブ記憶の取得"""
        store.add_memory(sample_memory)

        archived_memory = sample_memory.copy()
        archived_memory["id"] = "mem_test_002"
        archived_memory["archived_at"] = "2026-01-20T12:00:00+09:00"
        store.add_memory(archived_memory)

        active = store.get_active_memories()
        assert len(active) == 1
        assert active[0]["id"] == "mem_test_001"

    def test_get_archived_memories(self, store, sample_memory):
        """アーカイブ記憶の取得"""
        store.add_memory(sample_memory)

        archived_memory = sample_memory.copy()
        archived_memory["id"] = "mem_test_002"
        archived_memory["archived_at"] = "2026-01-20T12:00:00+09:00"
        store.add_memory(archived_memory)

        archived = store.get_archived_memories()
        assert len(archived) == 1
        assert archived[0]["id"] == "mem_test_002"

    def test_get_memory_not_found(self, store):
        """存在しない記憶の取得"""
        memory = store.get_memory("nonexistent")
        assert memory is None


class TestUpdateMemory:
    """update_memory のテスト"""

    def test_update_single_field(self, store, sample_memory):
        """単一フィールドの更新"""
        store.add_memory(sample_memory)
        store.update_memory("mem_test_001", {"retention_score": 75.0})

        memory = store.get_memory("mem_test_001")
        assert memory["retention_score"] == 75.0

    def test_update_multiple_fields(self, store, sample_memory):
        """複数フィールドの更新"""
        store.add_memory(sample_memory)
        store.update_memory("mem_test_001", {
            "memory_days": 5.0,
            "recall_count": 3,
            "current_level": 2,
        })

        memory = store.get_memory("mem_test_001")
        assert memory["memory_days"] == 5.0
        assert memory["recall_count"] == 3
        assert memory["current_level"] == 2

    def test_update_json_field(self, store, sample_memory):
        """JSONフィールドの更新"""
        store.add_memory(sample_memory)
        store.update_memory("mem_test_001", {
            "keywords": ["updated", "keywords"],
        })

        memory = store.get_memory("mem_test_001")
        assert memory["keywords"] == ["updated", "keywords"]

    def test_update_boolean_field(self, store, sample_memory):
        """booleanフィールドの更新"""
        store.add_memory(sample_memory)
        store.update_memory("mem_test_001", {
            "protected": True,
            "recalled_since_last_batch": True,
        })

        memory = store.get_memory("mem_test_001")
        assert memory["protected"] is True
        assert memory["recalled_since_last_batch"] is True


class TestMarkRecalled:
    """mark_recalled のテスト"""

    def test_mark_single_memory(self, store, sample_memory):
        """単一記憶の想起フラグ更新"""
        store.add_memory(sample_memory)
        store.mark_recalled(["mem_test_001"])

        memory = store.get_memory("mem_test_001")
        assert memory["recalled_since_last_batch"] is True

    def test_mark_multiple_memories(self, store, sample_memory):
        """複数記憶の想起フラグ更新"""
        store.add_memory(sample_memory)

        memory2 = sample_memory.copy()
        memory2["id"] = "mem_test_002"
        store.add_memory(memory2)

        store.mark_recalled(["mem_test_001", "mem_test_002"])

        m1 = store.get_memory("mem_test_001")
        m2 = store.get_memory("mem_test_002")
        assert m1["recalled_since_last_batch"] is True
        assert m2["recalled_since_last_batch"] is True

    def test_mark_empty_list(self, store, sample_memory):
        """空リストの場合"""
        store.add_memory(sample_memory)
        store.mark_recalled([])  # エラーにならない

        memory = store.get_memory("mem_test_001")
        assert memory["recalled_since_last_batch"] is False


class TestDeleteMemory:
    """delete_memory のテスト"""

    def test_delete_existing(self, store, sample_memory):
        """存在する記憶の削除"""
        store.add_memory(sample_memory)
        store.delete_memory("mem_test_001")

        memory = store.get_memory("mem_test_001")
        assert memory is None

    def test_delete_nonexistent(self, store):
        """存在しない記憶の削除（エラーにならない）"""
        store.delete_memory("nonexistent")  # エラーにならない


class TestState:
    """状態管理のテスト"""

    def test_set_and_get_state(self, store):
        """状態の設定と取得"""
        store.set_state("last_run", "2026-01-21T03:00:00+09:00")
        value = store.get_state("last_run")
        assert value == "2026-01-21T03:00:00+09:00"

    def test_get_nonexistent_state(self, store):
        """存在しない状態の取得"""
        value = store.get_state("nonexistent")
        assert value is None

    def test_update_state(self, store):
        """状態の更新"""
        store.set_state("counter", "1")
        store.set_state("counter", "2")
        value = store.get_state("counter")
        assert value == "2"


class TestCountMethods:
    """カウント系メソッドのテスト"""

    def test_count_memories(self, store, sample_memory):
        """記憶数のカウント"""
        store.add_memory(sample_memory)

        memory2 = sample_memory.copy()
        memory2["id"] = "mem_test_002"
        store.add_memory(memory2)

        count = store.count_memories()
        assert count == 2

    def test_count_by_level(self, store, sample_memory):
        """レベル別カウント"""
        store.add_memory(sample_memory)  # Level 1

        memory2 = sample_memory.copy()
        memory2["id"] = "mem_test_002"
        memory2["current_level"] = 2
        store.add_memory(memory2)

        memory3 = sample_memory.copy()
        memory3["id"] = "mem_test_003"
        memory3["current_level"] = 2
        store.add_memory(memory3)

        counts = store.count_by_level()
        assert counts.get(1, 0) == 1
        assert counts.get(2, 0) == 2
