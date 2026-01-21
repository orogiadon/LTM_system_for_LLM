#!/usr/bin/env python3
"""
memory_generation.py - 記憶生成モジュール（SessionEnd Hook用）

セッション終了時に会話から記憶を生成する。
Claude Code の SessionEnd Hook として実行される。
"""

import io
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

# パスを追加してモジュールをインポート可能に
sys.path.insert(0, str(Path(__file__).parent))

from config_loader import get_config
from embedding import get_embedding
from llm import analyze_emotion
from memory_store import MemoryStore
from retention import calculate_initial_decay_coefficient, calculate_retention_score


def get_hook_metadata() -> dict[str, Any]:
    """標準入力からHookメタデータを取得"""
    try:
        data = json.load(sys.stdin)
        return data
    except json.JSONDecodeError:
        return {}


def load_transcript(transcript_path: str) -> list[dict[str, Any]]:
    """
    トランスクリプトファイルからJSONLを読み込む

    Args:
        transcript_path: トランスクリプトファイルのパス

    Returns:
        メッセージのリスト
    """
    messages = []
    path = Path(transcript_path)

    if not path.exists():
        return messages

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    messages.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    return messages


def extract_turns(messages: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """
    メッセージからユーザー・アシスタントのペアを抽出

    Args:
        messages: メッセージのリスト

    Returns:
        (user_message, assistant_message) のタプルのリスト
    """
    turns = []
    user_message = None

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        # contentが配列の場合はテキスト部分を結合
        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text_parts.append(part.get("text", ""))
                elif isinstance(part, str):
                    text_parts.append(part)
            content = "\n".join(text_parts)

        if role == "user":
            user_message = content
        elif role == "assistant" and user_message is not None:
            turns.append((user_message, content))
            user_message = None

    return turns


def should_skip(message: str) -> bool:
    """
    記憶処理をスキップすべきか判定

    Args:
        message: ユーザーメッセージ

    Returns:
        スキップすべきならTrue
    """
    if not message:
        return True

    stripped = message.strip()

    # スラッシュコマンドはスキップ
    if stripped.startswith("/"):
        return True

    return False


def generate_memory_id() -> str:
    """記憶IDを生成"""
    now = datetime.now()
    date_str = now.strftime("%Y%m%d")
    unique_id = uuid.uuid4().hex[:8]
    return f"mem_{date_str}_{unique_id}"


def calculate_initial_memory_days(config: dict[str, Any] | None = None) -> float:
    """
    初期memory_daysを計算

    次回バッチまでの経過時間を考慮して初期値を設定。
    簡易的に0.5日（12時間相当）を初期値とする。

    Args:
        config: 設定辞書

    Returns:
        初期memory_days
    """
    # 次回バッチまでの時間を概算で0.5日とする
    return 0.5


def process_turn(
    user_message: str,
    assistant_message: str,
    store: MemoryStore,
    config: dict[str, Any]
) -> dict[str, Any] | None:
    """
    1ターンを処理して記憶を生成

    Args:
        user_message: ユーザーの発言
        assistant_message: アシスタントの応答
        store: MemoryStoreインスタンス
        config: 設定辞書

    Returns:
        生成された記憶データ、またはNone
    """
    if should_skip(user_message):
        return None

    # LLMで感情分析
    try:
        analysis = analyze_emotion(user_message, assistant_message, config)
    except Exception:
        # LLM呼び出しに失敗した場合はスキップ
        return None

    # 必須フィールドの検証
    required_fields = [
        "emotional_intensity", "emotional_valence", "emotional_arousal",
        "category", "trigger", "content"
    ]
    for field in required_fields:
        if field not in analysis:
            return None

    # Embedding生成
    embedding_text = f"{analysis['trigger']} {analysis['content']}"
    try:
        embedding = get_embedding(embedding_text, config)
    except Exception:
        embedding = None

    # 減衰係数計算
    decay_coefficient = calculate_initial_decay_coefficient(
        category=analysis["category"],
        emotional_intensity=analysis["emotional_intensity"],
        config=config
    )

    # memory_days初期値
    memory_days = calculate_initial_memory_days(config)

    # retention_score計算
    retention_score = calculate_retention_score(
        emotional_intensity=analysis["emotional_intensity"],
        decay_coefficient=decay_coefficient,
        memory_days=memory_days
    )

    # 記憶データ作成
    memory = {
        "id": generate_memory_id(),
        "created": datetime.now().astimezone().isoformat(),
        "memory_days": memory_days,
        "recalled_since_last_batch": False,
        "recall_count": 0,
        "emotional_intensity": analysis["emotional_intensity"],
        "emotional_valence": analysis["emotional_valence"],
        "emotional_arousal": analysis["emotional_arousal"],
        "emotional_tags": analysis.get("emotional_tags", []),
        "decay_coefficient": decay_coefficient,
        "category": analysis["category"],
        "keywords": analysis.get("keywords", []),
        "current_level": 1,
        "trigger": analysis["trigger"],
        "content": analysis["content"],
        "embedding": embedding,
        "relations": [],
        "retention_score": retention_score,
        "archived_at": None,
        "protected": analysis.get("protected", False)
    }

    # DBに保存
    store.add_memory(memory)

    return memory


def main():
    """メイン処理"""
    # 標準入出力のエンコーディング設定（Windows対応）
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding='utf-8')
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    # Hookメタデータ取得
    metadata = get_hook_metadata()
    transcript_path = metadata.get("transcript_path")

    if not transcript_path:
        return

    # 設定読み込み
    config = get_config()

    # DB接続
    db_path = Path(__file__).parent.parent / "data" / "memories.db"
    store = MemoryStore(db_path)

    # トランスクリプト読み込み
    messages = load_transcript(transcript_path)
    if not messages:
        return

    # ターン抽出
    turns = extract_turns(messages)
    if not turns:
        return

    # 各ターンを処理
    for user_message, assistant_message in turns:
        process_turn(user_message, assistant_message, store, config)


if __name__ == "__main__":
    main()
