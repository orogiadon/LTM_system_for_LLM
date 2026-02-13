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
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

# パスを追加してモジュールをインポート可能に
sys.path.insert(0, str(Path(__file__).parent))

from config_loader import get_config
from embedding import get_embedding, get_embeddings_batch, truncate_for_embedding
from llm import analyze_emotion, analyze_emotion_batch
from memory_store import MemoryStore
from retention import calculate_initial_decay_coefficient, calculate_retention_score


def get_hook_metadata() -> dict[str, Any]:
    """標準入力からHookメタデータを取得"""
    try:
        data = json.load(sys.stdin)
        return data
    except Exception:
        # すべての例外を無視して空のdictを返す
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

    Claude Codeのトランスクリプト形式:
    {"type":"user","message":{"role":"user","content":[{"type":"text","text":"..."}]}}
    {"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"..."}]}}

    注意: アシスタントのメッセージは同じIDで複数行に分割されて記録されるため、
    IDごとにテキストを集約する必要がある。

    Args:
        messages: メッセージのリスト

    Returns:
        (user_message, assistant_message) のタプルのリスト
    """
    turns = []
    current_user_message = None
    current_user_uuid = None
    assistant_texts: dict[str, list[str]] = {}  # message_id -> texts
    assistant_order: list[tuple[str, str]] = []  # (user_uuid, message_id) の順序

    for msg in messages:
        msg_type = msg.get("type", "")
        inner_msg = msg.get("message", {})

        if not inner_msg:
            continue

        role = inner_msg.get("role", "")
        content = inner_msg.get("content", "")

        # isMeta=trueのメッセージはスキップ（システムメッセージ等）
        if msg.get("isMeta", False):
            continue

        # contentが配列の場合はテキスト部分を抽出
        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text_parts.append(part.get("text", ""))
                elif isinstance(part, str):
                    text_parts.append(part)
            content = "\n".join(text_parts)

        if role == "user" and msg_type == "user":
            # 新しいユーザーメッセージ
            if content and content.strip():
                current_user_message = content
                current_user_uuid = msg.get("uuid", "")
        elif role == "assistant" and msg_type == "assistant":
            # アシスタントメッセージ（同じIDで複数回出現する可能性あり）
            message_id = inner_msg.get("id", "")
            if message_id and content and content.strip():
                if message_id not in assistant_texts:
                    assistant_texts[message_id] = []
                    # ユーザーメッセージとの紐付けを記録
                    if current_user_message and current_user_uuid:
                        assistant_order.append((current_user_uuid, message_id))
                assistant_texts[message_id].append(content)

    # ユーザーメッセージとアシスタントメッセージをペアにする
    user_messages: dict[str, str] = {}
    for msg in messages:
        if msg.get("type") == "user":
            inner_msg = msg.get("message", {})
            if inner_msg.get("role") == "user":
                content = inner_msg.get("content", "")
                if isinstance(content, list):
                    text_parts = []
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            text_parts.append(part.get("text", ""))
                        elif isinstance(part, str):
                            text_parts.append(part)
                    content = "\n".join(text_parts)
                if content and content.strip():
                    user_messages[msg.get("uuid", "")] = content

    # 順序に従ってペアを作成
    seen_user_uuids = set()
    for user_uuid, message_id in assistant_order:
        if user_uuid in seen_user_uuids:
            continue
        seen_user_uuids.add(user_uuid)

        user_text = user_messages.get(user_uuid, "")
        assistant_text = "\n".join(assistant_texts.get(message_id, []))

        if user_text and assistant_text:
            turns.append((user_text, assistant_text))

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

    # スラッシュコマンドはスキップ（従来形式）
    if stripped.startswith("/"):
        return True

    # スラッシュコマンドはスキップ（Claude Code形式: <command-name>/xxx</command-name>）
    if "<command-name>/" in stripped:
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


def check_protection_limit(
    store: MemoryStore,
    config: dict[str, Any],
    log_func=None
) -> bool:
    """
    保護記憶の上限をチェック

    Args:
        store: MemoryStoreインスタンス
        config: 設定辞書
        log_func: ログ関数（デバッグ用）

    Returns:
        保護可能ならTrue、上限に達していればFalse
    """
    protection_config = config.get("protection", {})
    max_protected = protection_config.get("max_protected_memories", 50)
    current_count = store.count_protected()

    if current_count >= max_protected:
        if log_func:
            log_func(f"WARNING: Protected memory limit reached ({current_count}/{max_protected}). New protection request will be skipped.")
        return False
    return True


def process_turn(
    user_message: str,
    assistant_message: str,
    store: MemoryStore,
    config: dict[str, Any],
    log_func=None
) -> dict[str, Any] | None:
    """
    1ターンを処理して記憶を生成

    Args:
        user_message: ユーザーの発言
        assistant_message: アシスタントの応答
        store: MemoryStoreインスタンス
        config: 設定辞書
        log_func: ログ関数（デバッグ用）

    Returns:
        生成された記憶データ、またはNone
    """
    def log(msg):
        if log_func:
            log_func(msg)

    if should_skip(user_message):
        log(f"Skipped: slash command or empty")
        return None

    # LLMで感情分析
    try:
        analysis = analyze_emotion(user_message, assistant_message, config)
    except Exception as e:
        # LLM呼び出しに失敗した場合はスキップ
        log(f"LLM error: {type(e).__name__}: {e}")
        return None

    # 必須フィールドの検証
    required_fields = [
        "emotional_intensity", "emotional_valence", "emotional_arousal",
        "category"
    ]
    for field in required_fields:
        if field not in analysis:
            return None

    # Level 1記憶では元の会話をそのまま保存（要約はLevel 2圧縮時に行う）
    trigger = user_message
    content = assistant_message

    # Embedding生成
    embedding_text = f"{trigger} {content}"
    try:
        embedding = get_embedding(embedding_text, config)
    except Exception as e:
        log(f"Embedding error: {type(e).__name__}: {e}")
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

    # 保護フラグの処理（上限チェック）
    protected = analysis.get("protected", False)
    if protected:
        if not check_protection_limit(store, config, log_func=log):
            # 上限に達している場合は保護せず通常記憶として保存
            protected = False
            log("Protection skipped due to limit, saving as normal memory")

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
        "trigger": trigger,
        "content": content,
        "embedding": embedding,
        "relations": [],
        "retention_score": retention_score,
        "archived_at": None,
        "protected": protected
    }

    # DBに保存
    store.add_memory(memory)

    return memory


def process_turns_batch(
    turns: list[tuple[str, str]],
    store: MemoryStore,
    config: dict[str, Any],
    log_func=None
) -> list[dict[str, Any]]:
    """
    複数ターンをバッチ処理して記憶を生成・保存

    LLM感情分析（Message Batch API）とEmbedding生成（一括API）を
    並列実行し、結果を時系列順にDBへ保存する。

    Args:
        turns: (user_message, assistant_message) のリスト（時系列順）
        store: MemoryStoreインスタンス
        config: 設定辞書
        log_func: ログ関数

    Returns:
        生成された記憶データのリスト（時系列順）
    """
    def log(msg):
        if log_func:
            log_func(msg)

    # Phase 0: フィルタリング
    valid_turns = []
    for i, (user_msg, assistant_msg) in enumerate(turns):
        if should_skip(user_msg):
            log(f"Skipped turn {i}: slash command or empty")
            continue
        valid_turns.append((i, user_msg, assistant_msg))

    if not valid_turns:
        log("No valid turns to process")
        return []

    log(f"Valid turns: {len(valid_turns)}/{len(turns)}")

    # バッチ処理用のデータ準備
    turn_pairs = [(u, a) for _, u, a in valid_turns]
    embedding_texts = [
        truncate_for_embedding(f"{u} {a}") for _, u, a in valid_turns
    ]

    # Phase 1: LLM Batch + Embedding を並列実行
    log("Starting parallel API calls (LLM batch + Embedding)")

    analyses = {}
    embeddings = []
    embedding_max_retries = 3
    embedding_retry_delay = 2.0

    def run_embeddings_with_retry():
        """Embedding一括取得（リトライ付き）"""
        import time as _time
        for attempt in range(embedding_max_retries):
            try:
                return get_embeddings_batch(embedding_texts, config)
            except Exception as e:
                log(f"Embedding batch attempt {attempt + 1}/{embedding_max_retries} "
                    f"failed: {type(e).__name__}: {e}")
                if attempt < embedding_max_retries - 1:
                    _time.sleep(embedding_retry_delay * (attempt + 1))
        log("WARNING: Embedding batch failed after all retries")
        return []

    with ThreadPoolExecutor(max_workers=2) as executor:
        batch_future = executor.submit(
            analyze_emotion_batch, turn_pairs, config, log_func=log_func
        )
        embedding_future = executor.submit(run_embeddings_with_retry)

        try:
            analyses = batch_future.result()
        except Exception as e:
            log(f"Batch analysis failed: {type(e).__name__}: {e}")

        embeddings = embedding_future.result()

    log(f"API calls completed: {len(analyses)} analyses, {len(embeddings)} embeddings")

    # Phase 2: 結果結合 + DB保存（時系列順）
    memories = []
    for idx, (orig_idx, user_msg, assistant_msg) in enumerate(valid_turns):
        analysis = analyses.get(idx)
        if not analysis:
            log(f"No analysis for turn {orig_idx}, skipping")
            continue

        # 必須フィールド検証
        required_fields = [
            "emotional_intensity", "emotional_valence",
            "emotional_arousal", "category"
        ]
        if not all(f in analysis for f in required_fields):
            log(f"Missing required fields for turn {orig_idx}, skipping")
            continue

        embedding = embeddings[idx] if idx < len(embeddings) else None

        # 減衰係数計算
        decay_coefficient = calculate_initial_decay_coefficient(
            category=analysis["category"],
            emotional_intensity=analysis["emotional_intensity"],
            config=config
        )

        memory_days = calculate_initial_memory_days(config)

        retention_score = calculate_retention_score(
            emotional_intensity=analysis["emotional_intensity"],
            decay_coefficient=decay_coefficient,
            memory_days=memory_days
        )

        # 保護フラグ処理
        protected = analysis.get("protected", False)
        if protected:
            if not check_protection_limit(store, config, log_func=log):
                protected = False
                log(f"Protection skipped for turn {orig_idx} due to limit")

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
            "trigger": user_msg,
            "content": assistant_msg,
            "embedding": embedding,
            "relations": [],
            "retention_score": retention_score,
            "archived_at": None,
            "protected": protected
        }

        store.add_memory(memory)
        memories.append(memory)
        log(f"Memory created: {memory['id']} (turn {orig_idx})")

    return memories


def write_completion_marker(
    count: int,
    transcript_path: str,
    log_func=None
) -> None:
    """完了マーカーファイルを書き込む"""
    marker_path = Path(__file__).parent.parent / "data" / "last_write.json"
    marker_data = {
        "completed_at": datetime.now().astimezone().isoformat(),
        "success": True,
        "count": count,
        "transcript_path": transcript_path
    }
    try:
        marker_path.write_text(
            json.dumps(marker_data, ensure_ascii=False),
            encoding="utf-8"
        )
        if log_func:
            log_func(f"Completion marker written: {marker_path}")
    except Exception as e:
        if log_func:
            log_func(f"Failed to write marker: {e}")


def notify_completion(count: int, log_func=None) -> None:
    """完了通知を送信する"""
    try:
        from plyer import notification
        notification.notify(
            title="LTM System",
            message=f"記憶書き込み完了: {count}件",
            timeout=5
        )
        if log_func:
            log_func("Notification sent")
    except Exception as e:
        if log_func:
            log_func(f"Notification failed: {e}")


def main():
    """メイン処理"""
    # デバッグログファイル
    log_path = Path(__file__).parent.parent / "data" / "debug.log"

    def log(msg: str):
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()} {msg}\n")

    try:
        log("=== SessionEnd Hook started ===")

        # 標準入出力のエンコーディング設定（Windows対応）- メタデータ取得前に行う
        sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding='utf-8')
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

        # 標準入力から直接読み取ってみる
        raw_input = sys.stdin.read()
        log(f"Raw input length: {len(raw_input)}")
        log(f"Raw input (first 500): {raw_input[:500]}")

        # JSONとしてパース
        if raw_input.strip():
            metadata = json.loads(raw_input)
        else:
            metadata = {}
        log(f"Metadata parsed: {json.dumps(metadata, ensure_ascii=False)}")
        transcript_path = metadata.get("transcript_path")

        if not transcript_path:
            log("No transcript_path, exiting")
            return

        log(f"Transcript path: {transcript_path}")

        # 設定読み込み
        config = get_config()
        log("Config loaded")

        # DB接続
        db_path = Path(__file__).parent.parent / "data" / "memories.db"
        store = MemoryStore(db_path)
        log(f"DB connected: {db_path}")

        # トランスクリプト読み込み
        messages = load_transcript(transcript_path)
        log(f"Messages loaded: {len(messages)}")
        if not messages:
            log("No messages, exiting")
            return

        # ターン抽出
        turns = extract_turns(messages)
        log(f"Turns extracted: {len(turns)}")
        if not turns:
            log("No turns, exiting")
            return

        # バッチ処理で記憶を生成
        memories = process_turns_batch(turns, store, config, log_func=log)
        processed = len(memories)

        log(f"=== SessionEnd Hook completed: {processed} memories created ===")

        # 完了マーカーファイル書き込み
        write_completion_marker(processed, transcript_path, log)

        # 完了通知
        notify_completion(processed, log)

    except Exception as e:
        log(f"ERROR: {type(e).__name__}: {e}")
        import traceback
        log(traceback.format_exc())

        # エラー時もマーカーに記録
        marker_path = Path(__file__).parent.parent / "data" / "last_write.json"
        try:
            marker_path.write_text(json.dumps({
                "completed_at": datetime.now().astimezone().isoformat(),
                "success": False,
                "error": f"{type(e).__name__}: {e}",
                "count": 0
            }, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass


if __name__ == "__main__":
    main()
