"""
test_config_loader.py - config_loader.py のテスト
"""

import json
import pytest

from src.config_loader import (
    deep_merge,
    load_config,
    get_config_value,
    DEFAULT_CONFIG,
)


class TestDeepMerge:
    """deep_merge のテスト"""

    def test_simple_merge(self):
        """単純なマージ"""
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}

        result = deep_merge(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self):
        """ネストされた辞書のマージ"""
        base = {"level1": {"a": 1, "b": 2}}
        override = {"level1": {"b": 3, "c": 4}}

        result = deep_merge(base, override)
        assert result == {"level1": {"a": 1, "b": 3, "c": 4}}

    def test_deep_nested_merge(self):
        """深くネストされた辞書のマージ"""
        base = {"l1": {"l2": {"a": 1}}}
        override = {"l1": {"l2": {"b": 2}}}

        result = deep_merge(base, override)
        assert result == {"l1": {"l2": {"a": 1, "b": 2}}}

    def test_override_non_dict_with_dict(self):
        """非辞書を辞書で上書き"""
        base = {"a": 1}
        override = {"a": {"nested": True}}

        result = deep_merge(base, override)
        assert result == {"a": {"nested": True}}

    def test_override_dict_with_non_dict(self):
        """辞書を非辞書で上書き"""
        base = {"a": {"nested": True}}
        override = {"a": 1}

        result = deep_merge(base, override)
        assert result == {"a": 1}

    def test_empty_base(self):
        """空のベース"""
        base = {}
        override = {"a": 1}

        result = deep_merge(base, override)
        assert result == {"a": 1}

    def test_empty_override(self):
        """空のオーバーライド"""
        base = {"a": 1}
        override = {}

        result = deep_merge(base, override)
        assert result == {"a": 1}


class TestLoadConfig:
    """load_config のテスト"""

    def test_load_nonexistent_file(self, tmp_path):
        """存在しないファイルの場合はデフォルト値を返す"""
        config_path = tmp_path / "nonexistent.json"
        result = load_config(config_path)

        # デフォルト設定と同じ構造を持つ
        assert "retention" in result
        assert "levels" in result
        assert "embedding" in result

    def test_load_existing_file(self, tmp_path):
        """既存ファイルの読み込み"""
        config_path = tmp_path / "config.json"
        user_config = {
            "retrieval": {"top_k": 10}
        }
        config_path.write_text(json.dumps(user_config), encoding="utf-8")

        result = load_config(config_path)

        # ユーザー設定が反映される
        assert result["retrieval"]["top_k"] == 10
        # デフォルト値も保持される
        assert result["retrieval"]["relevance_threshold"] == 5.0

    def test_load_partial_override(self, tmp_path):
        """部分的な上書き"""
        config_path = tmp_path / "config.json"
        user_config = {
            "retention": {
                "base_decay_coefficient": 0.99
            }
        }
        config_path.write_text(json.dumps(user_config), encoding="utf-8")

        result = load_config(config_path)

        # 上書きされた値
        assert result["retention"]["base_decay_coefficient"] == 0.99
        # 上書きされていない値はデフォルト
        assert result["retention"]["max_decay_coefficient"] == 0.999


class TestGetConfigValue:
    """get_config_value のテスト"""

    def test_get_nested_value(self):
        """ネストされた値の取得"""
        config = {"level1": {"level2": {"value": 42}}}

        result = get_config_value(config, "level1", "level2", "value")
        assert result == 42

    def test_get_top_level_value(self):
        """トップレベルの値の取得"""
        config = {"key": "value"}

        result = get_config_value(config, "key")
        assert result == "value"

    def test_missing_key_returns_default(self):
        """存在しないキーはデフォルト値を返す"""
        config = {"a": 1}

        result = get_config_value(config, "nonexistent", default="default")
        assert result == "default"

    def test_missing_nested_key_returns_default(self):
        """ネストされたキーが存在しない場合"""
        config = {"level1": {"a": 1}}

        result = get_config_value(config, "level1", "nonexistent", default=None)
        assert result is None

    def test_default_is_none_by_default(self):
        """デフォルト値のデフォルトはNone"""
        config = {}

        result = get_config_value(config, "missing")
        assert result is None


class TestDefaultConfig:
    """DEFAULT_CONFIG の構造テスト"""

    def test_all_sections_present(self):
        """全セクションが存在する"""
        required_sections = [
            "version", "retention", "levels", "recall", "resonance",
            "compression", "relations", "retrieval", "archive",
            "protection", "embedding", "llm"
        ]
        for section in required_sections:
            assert section in DEFAULT_CONFIG

    def test_retention_structure(self):
        """retention セクションの構造"""
        retention = DEFAULT_CONFIG["retention"]
        assert "base_decay_coefficient" in retention
        assert "decay_by_category" in retention
        assert "max_decay_coefficient" in retention

    def test_levels_thresholds(self):
        """levels の閾値"""
        levels = DEFAULT_CONFIG["levels"]
        # Level 1 > Level 2
        assert levels["level1_threshold"] > levels["level2_threshold"]
