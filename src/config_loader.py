"""
config_loader.py - 設定ファイル読み込みモジュール

設定ファイル（config.json）を読み込み、デフォルト値とマージして返す。
"""

import json
from pathlib import Path
from typing import Any


# デフォルト設定値
DEFAULT_CONFIG = {
    "version": "1.0.0",

    "retention": {
        "base_decay_coefficient": 0.995,
        "decay_by_category": {
            "casual": {"min": 0.70, "max": 0.80},
            "work": {"min": 0.85, "max": 0.92},
            "decision": {"min": 0.93, "max": 0.97},
            "emotional": {"min": 0.98, "max": 0.999}
        },
        "max_decay_coefficient": 0.999
    },

    "levels": {
        "level1_threshold": 50,
        "level2_threshold": 20
    },

    "recall": {
        "decay_coefficient_boost": 0.02,
        "memory_days_reduction": 0.5,
        "recall_count_weight": 0.1
    },

    "resonance": {
        "valence_match_bonus": 0.3,
        "arousal_proximity_bonus": 0.2,
        "tags_overlap_weight": 0.5,
        "priority_weight_alpha": 0.3
    },

    "compression": {
        "schedule_hour": 3,
        "interval_hours": 24
    },

    "relations": {
        "score_proximity_threshold": 5.0,
        "auto_link_similarity_threshold": 0.85,
        "max_relations_per_memory": 10,
        "relation_traversal_depth": 1,
        "enable_auto_linking": True
    },

    "retrieval": {
        "top_k": 5,
        "relevance_threshold": 5.0
    },

    "archive": {
        "enable_archive_recall": True,
        "revival_decay_per_day": 0.995,
        "revival_min_margin": 3.0,
        "auto_delete_enabled": False,
        "retention_days": 365,
        "delete_require_zero_recall": True,
        "delete_max_intensity": 20,
        "delete_condition_mode": "AND"
    },

    "protection": {
        "max_protected_memories": 50
    },

    "embedding": {
        "provider": "openai",
        "model": "text-embedding-3-small",
        "dimensions": 1536
    },

    "llm": {
        "provider": "anthropic",
        "model": "claude-3-5-haiku-20241022",
        "temperature": 0,
        "max_tokens": 1024
    }
}


def deep_merge(base: dict, override: dict) -> dict:
    """
    辞書を再帰的にマージする。
    overrideの値がbaseの値を上書きする。
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """
    設定ファイルを読み込み、デフォルト値とマージして返す。

    Args:
        config_path: 設定ファイルのパス。Noneの場合はデフォルトパスを使用。

    Returns:
        マージされた設定辞書
    """
    if config_path is None:
        # デフォルトパス: このファイルの親ディレクトリの親/config/config.json
        config_path = Path(__file__).parent.parent / "config" / "config.json"
    else:
        config_path = Path(config_path)

    # 設定ファイルが存在しない場合はデフォルト値を返す
    if not config_path.exists():
        return DEFAULT_CONFIG.copy()

    with open(config_path, "r", encoding="utf-8") as f:
        user_config = json.load(f)

    return deep_merge(DEFAULT_CONFIG, user_config)


def get_config_value(config: dict, *keys: str, default: Any = None) -> Any:
    """
    ネストされた設定値を安全に取得する。

    Args:
        config: 設定辞書
        *keys: キーのパス（例: "retention", "base_decay_coefficient"）
        default: キーが存在しない場合のデフォルト値

    Returns:
        設定値またはデフォルト値
    """
    value = config
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default
    return value


# モジュールレベルでの設定キャッシュ
_config_cache: dict | None = None


def get_config(config_path: str | Path | None = None, reload: bool = False) -> dict[str, Any]:
    """
    設定を取得する（キャッシュ付き）。

    Args:
        config_path: 設定ファイルのパス
        reload: Trueの場合、キャッシュを無視して再読み込み

    Returns:
        設定辞書
    """
    global _config_cache

    if _config_cache is None or reload:
        _config_cache = load_config(config_path)

    return _config_cache
