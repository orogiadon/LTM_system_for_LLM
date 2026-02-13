"""
test_batch_processing.py - バッチ処理のテスト

テスト用DBを使用して、バッチ処理が正しく動作するか検証する。
外部API（Claude, OpenAI）はモックで代替。
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# srcをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config_loader import DEFAULT_CONFIG
from embedding import MAX_EMBEDDING_CHARS, truncate_for_embedding
from memory_generation import process_turns_batch, should_skip
from memory_store import MemoryStore


# --- テストヘルパー ---


def make_mock_analysis(index: int, protected: bool = False) -> dict:
    """テスト用の感情分析結果を生成"""
    return {
        "emotional_intensity": 50 + index,
        "emotional_valence": "positive",
        "emotional_arousal": 40 + index,
        "emotional_tags": [f"tag_{index}"],
        "category": "casual",
        "keywords": [f"keyword_{index}"],
        "protected": protected,
    }


def make_mock_embedding(dim: int = 1536) -> list[float]:
    """テスト用のembeddingを生成"""
    return [0.01 * (i % 100) for i in range(dim)]


@pytest.fixture
def test_store(tmp_path):
    """テスト用DBを作成"""
    db_path = tmp_path / "test_memories.db"
    return MemoryStore(db_path)


@pytest.fixture
def config():
    """テスト用設定"""
    return DEFAULT_CONFIG.copy()


# --- truncate_for_embedding のテスト ---


class TestTruncateForEmbedding:
    def test_short_text_unchanged(self):
        """短いテキストはそのまま返る"""
        text = "短いテキスト"
        assert truncate_for_embedding(text) == text

    def test_long_text_truncated(self):
        """長いテキストはMAX_EMBEDDING_CHARS文字に切り詰められる"""
        text = "あ" * (MAX_EMBEDDING_CHARS + 500)
        result = truncate_for_embedding(text)
        assert len(result) == MAX_EMBEDDING_CHARS

    def test_exact_limit_unchanged(self):
        """ちょうど上限のテキストは切り詰められない"""
        text = "a" * MAX_EMBEDDING_CHARS
        assert len(truncate_for_embedding(text)) == MAX_EMBEDDING_CHARS

    def test_custom_limit(self):
        """カスタム上限が適用される"""
        text = "abcdefghij"
        result = truncate_for_embedding(text, max_chars=5)
        assert result == "abcde"


# --- should_skip のテスト ---


class TestShouldSkip:
    def test_slash_command_skipped(self):
        assert should_skip("/help") is True

    def test_claude_code_command_skipped(self):
        assert should_skip("<command-name>/commit</command-name>") is True

    def test_normal_message_not_skipped(self):
        assert should_skip("通常のメッセージ") is False

    def test_empty_message_skipped(self):
        assert should_skip("") is True

    def test_none_message_skipped(self):
        assert should_skip(None) is True


# --- process_turns_batch のテスト ---


class TestProcessTurnsBatch:
    @patch("memory_generation.analyze_emotion_batch")
    @patch("memory_generation.get_embeddings_batch")
    def test_basic_batch_processing(
        self, mock_embeddings, mock_analysis, test_store, config
    ):
        """基本的なバッチ処理: N件入力 → N件の記憶が生成される"""
        num_turns = 5
        turns = [
            (f"ユーザー{i}", f"アシスタント{i}") for i in range(num_turns)
        ]

        mock_analysis.return_value = {
            i: make_mock_analysis(i) for i in range(num_turns)
        }
        mock_embeddings.return_value = [
            make_mock_embedding() for _ in range(num_turns)
        ]

        memories = process_turns_batch(turns, test_store, config)

        assert len(memories) == num_turns
        mock_analysis.assert_called_once()
        mock_embeddings.assert_called_once()

    @patch("memory_generation.analyze_emotion_batch")
    @patch("memory_generation.get_embeddings_batch")
    def test_chronological_order_preserved(
        self, mock_embeddings, mock_analysis, test_store, config
    ):
        """記憶が時系列順に保存される"""
        num_turns = 10
        turns = [
            (f"メッセージ{i}", f"応答{i}") for i in range(num_turns)
        ]

        mock_analysis.return_value = {
            i: make_mock_analysis(i) for i in range(num_turns)
        }
        mock_embeddings.return_value = [
            make_mock_embedding() for _ in range(num_turns)
        ]

        memories = process_turns_batch(turns, test_store, config)

        assert len(memories) == num_turns
        for i, mem in enumerate(memories):
            assert mem["trigger"] == f"メッセージ{i}"
            assert mem["content"] == f"応答{i}"

    @patch("memory_generation.analyze_emotion_batch")
    @patch("memory_generation.get_embeddings_batch")
    def test_slash_commands_filtered(
        self, mock_embeddings, mock_analysis, test_store, config
    ):
        """スラッシュコマンドがフィルタされ、通常メッセージのみ処理される"""
        turns = [
            ("/help", "ヘルプ情報"),
            ("通常メッセージ1", "通常応答1"),
            ("/commit", "コミット結果"),
            ("通常メッセージ2", "通常応答2"),
        ]

        # フィルタ後は2件（index 0, 1）
        mock_analysis.return_value = {
            0: make_mock_analysis(0),
            1: make_mock_analysis(1),
        }
        mock_embeddings.return_value = [
            make_mock_embedding(),
            make_mock_embedding(),
        ]

        memories = process_turns_batch(turns, test_store, config)

        assert len(memories) == 2
        assert memories[0]["trigger"] == "通常メッセージ1"
        assert memories[1]["trigger"] == "通常メッセージ2"

    @patch("memory_generation.analyze_emotion_batch")
    @patch("memory_generation.get_embeddings_batch")
    def test_partial_analysis_failure(
        self, mock_embeddings, mock_analysis, test_store, config
    ):
        """一部の感情分析が失敗しても、成功分は処理される"""
        turns = [
            (f"メッセージ{i}", f"応答{i}") for i in range(5)
        ]

        # index 2 が失敗（結果なし）
        mock_analysis.return_value = {
            0: make_mock_analysis(0),
            1: make_mock_analysis(1),
            # 2 is missing
            3: make_mock_analysis(3),
            4: make_mock_analysis(4),
        }
        mock_embeddings.return_value = [
            make_mock_embedding() for _ in range(5)
        ]

        memories = process_turns_batch(turns, test_store, config)

        assert len(memories) == 4
        triggers = [m["trigger"] for m in memories]
        assert "メッセージ2" not in triggers
        assert "メッセージ0" in triggers
        assert "メッセージ4" in triggers

    @patch("memory_generation.get_embeddings_batch")
    @patch("memory_generation.analyze_emotion_batch")
    def test_embedding_retry_then_success(
        self, mock_analysis, mock_embeddings, test_store, config
    ):
        """Embeddingが初回失敗→リトライで成功する"""
        turns = [("テスト", "応答")]
        mock_analysis.return_value = {0: make_mock_analysis(0)}

        # 1回目は失敗、2回目は成功
        mock_embeddings.side_effect = [
            Exception("Temporary API Error"),
            [make_mock_embedding()],
        ]

        memories = process_turns_batch(turns, test_store, config)

        assert len(memories) == 1
        assert memories[0]["embedding"] is not None
        assert mock_embeddings.call_count == 2

    @patch("memory_generation.get_embeddings_batch")
    @patch("memory_generation.analyze_emotion_batch")
    def test_embedding_all_retries_exhausted(
        self, mock_analysis, mock_embeddings, test_store, config
    ):
        """Embeddingが全リトライ失敗しても、記憶はembedding=Noneで保存される"""
        turns = [("テスト", "応答")]
        mock_analysis.return_value = {0: make_mock_analysis(0)}

        # 3回すべて失敗
        mock_embeddings.side_effect = Exception("Persistent API Error")

        memories = process_turns_batch(turns, test_store, config)

        assert len(memories) == 1
        assert memories[0]["embedding"] is None
        assert mock_embeddings.call_count == 3

    @patch("memory_generation.analyze_emotion_batch")
    @patch("memory_generation.get_embeddings_batch")
    def test_db_persistence(
        self, mock_embeddings, mock_analysis, test_store, config
    ):
        """バッチ処理結果がDBに正しく永続化される"""
        num_turns = 3
        turns = [
            (f"ユーザー{i}", f"アシスタント{i}") for i in range(num_turns)
        ]

        mock_analysis.return_value = {
            i: make_mock_analysis(i) for i in range(num_turns)
        }
        mock_embeddings.return_value = [
            make_mock_embedding() for _ in range(num_turns)
        ]

        process_turns_batch(turns, test_store, config)

        all_memories = test_store.get_all_memories()
        assert len(all_memories) == num_turns

        # triggerの内容でDBに正しく保存されたことを検証
        db_triggers = sorted(m["trigger"] for m in all_memories)
        expected_triggers = sorted(f"ユーザー{i}" for i in range(num_turns))
        assert db_triggers == expected_triggers

    @patch("memory_generation.analyze_emotion_batch")
    @patch("memory_generation.get_embeddings_batch")
    def test_memory_fields_correct(
        self, mock_embeddings, mock_analysis, test_store, config
    ):
        """生成された記憶の各フィールドが正しい値を持つ"""
        turns = [("テスト入力", "テスト応答")]

        analysis = make_mock_analysis(0)
        mock_analysis.return_value = {0: analysis}
        mock_embeddings.return_value = [make_mock_embedding()]

        memories = process_turns_batch(turns, test_store, config)

        mem = memories[0]
        assert mem["trigger"] == "テスト入力"
        assert mem["content"] == "テスト応答"
        assert mem["emotional_intensity"] == analysis["emotional_intensity"]
        assert mem["emotional_valence"] == analysis["emotional_valence"]
        assert mem["category"] == analysis["category"]
        assert mem["current_level"] == 1
        assert mem["recall_count"] == 0
        assert mem["recalled_since_last_batch"] is False
        assert mem["archived_at"] is None
        assert mem["embedding"] is not None
        assert len(mem["embedding"]) == 1536
        assert mem["id"].startswith("mem_")
        assert mem["retention_score"] > 0

    @patch("memory_generation.analyze_emotion_batch")
    @patch("memory_generation.get_embeddings_batch")
    def test_empty_turns(
        self, mock_embeddings, mock_analysis, test_store, config
    ):
        """空のターンリストでは何も処理されない"""
        memories = process_turns_batch([], test_store, config)

        assert len(memories) == 0
        mock_analysis.assert_not_called()
        mock_embeddings.assert_not_called()

    @patch("memory_generation.analyze_emotion_batch")
    @patch("memory_generation.get_embeddings_batch")
    def test_all_slash_commands(
        self, mock_embeddings, mock_analysis, test_store, config
    ):
        """全てスラッシュコマンドの場合、APIは呼ばれない"""
        turns = [("/help", "h"), ("/commit", "c")]

        memories = process_turns_batch(turns, test_store, config)

        assert len(memories) == 0
        mock_analysis.assert_not_called()
        mock_embeddings.assert_not_called()

    @patch("memory_generation.analyze_emotion_batch")
    @patch("memory_generation.get_embeddings_batch")
    def test_large_batch_60_turns(
        self, mock_embeddings, mock_analysis, test_store, config
    ):
        """60ターンのバッチ処理が正しく動作する"""
        num_turns = 60
        turns = [
            (f"ユーザー{i:03d}", f"アシスタント{i:03d}")
            for i in range(num_turns)
        ]

        mock_analysis.return_value = {
            i: make_mock_analysis(i % 100) for i in range(num_turns)
        }
        mock_embeddings.return_value = [
            make_mock_embedding() for _ in range(num_turns)
        ]

        memories = process_turns_batch(turns, test_store, config)

        assert len(memories) == num_turns
        # 時系列順を確認
        for i, mem in enumerate(memories):
            assert mem["trigger"] == f"ユーザー{i:03d}"

        # DB件数も確認
        assert test_store.count_memories() == num_turns

    @patch("memory_generation.analyze_emotion_batch")
    @patch("memory_generation.get_embeddings_batch")
    def test_protection_limit_respected(
        self, mock_embeddings, mock_analysis, test_store, config
    ):
        """保護記憶の上限が尊重される"""
        # 上限を2に設定
        config["protection"]["max_protected_memories"] = 2

        # 事前に保護記憶を2件作成（上限到達状態）
        for i in range(2):
            test_store.add_memory({
                "id": f"existing_{i}",
                "created": "2025-01-01T00:00:00+09:00",
                "emotional_intensity": 80,
                "emotional_valence": "positive",
                "emotional_arousal": 70,
                "decay_coefficient": 0.99,
                "category": "emotional",
                "trigger": f"既存{i}",
                "content": f"既存応答{i}",
                "current_level": 1,
                "protected": True,
            })

        turns = [("保護してほしいメッセージ", "応答")]
        mock_analysis.return_value = {
            0: make_mock_analysis(0, protected=True)
        }
        mock_embeddings.return_value = [make_mock_embedding()]

        memories = process_turns_batch(turns, test_store, config)

        # 記憶は作成されるが、保護はされない（上限到達のため）
        assert len(memories) == 1
        assert memories[0]["protected"] is False
