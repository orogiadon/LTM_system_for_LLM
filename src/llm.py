"""
llm.py - LLM操作モジュール

Claude APIを使用して感情分析・要約・キーワード抽出を行う。
"""

import json
import time
from typing import Any

import anthropic
from anthropic import APIError, RateLimitError, APITimeoutError

from config_loader import get_config

# デフォルトタイムアウト（秒）
DEFAULT_TIMEOUT = 60.0


# 感情分析プロンプト
EMOTION_ANALYSIS_PROMPT = """以下の会話を分析し、指定されたJSON形式で結果を返してください。

## 会話内容
ユーザー発言: {user_message}
アシスタント応答: {assistant_message}

## 出力形式
以下のJSON形式で出力してください。余計な説明は不要です。

```json
{{
  "emotional_intensity": <0-100の整数: 感情的な重要度>,
  "emotional_valence": "<positive/negative/neutral>",
  "emotional_arousal": <0-100の整数: 感情の覚醒度>,
  "emotional_tags": ["<感情タグ1>", "<感情タグ2>", ...],
  "category": "<casual/work/decision/emotional>",
  "keywords": ["<キーワード1>", "<キーワード2>", ...],
  "protected": <true/false: 「覚えておいて」等のフレーズがあればtrue>
}}
```

## 判定基準
- emotional_intensity: 単純な技術的やり取り=15-25、深い感情的やり取り=70-85
- category: 雑談=casual、仕事関連=work、重要な決定=decision、感情的なやり取り=emotional
- protected: 「覚えておいて」「忘れないで」「重要だから記憶して」等のフレーズがあればtrue"""


# 要約プロンプト（Level 1 → 2）
SUMMARIZE_PROMPT = """以下の記憶を要約してください。

## 要約の方針
- triggerは「何がきっかけだったか」を1〜2文で要約（具体的な話題や質問内容を残す）
- contentは「どう反応したか」を2〜3文で要約（説明した内容、ユーザーの反応も残す）
- 固有名詞、技術用語、具体的なトピックは省略しない
- 感情的なニュアンスがあれば残す

## 元の記憶
きっかけ（trigger）:
{trigger}

反応（content）:
{content}

## 出力形式（JSONのみ、説明不要）
```json
{{
  "trigger": "<きっかけの要約>",
  "content": "<反応の要約>"
}}
```"""




# クエリ分類プロンプト（想起時のカテゴリ・感情分類）
QUERY_CLASSIFY_PROMPT = """以下のユーザー発言を分析し、指定されたJSON形式で結果を返してください。

## ユーザー発言
{query}

## 出力形式
以下のJSON形式で出力してください。余計な説明は不要です。

```json
{{
  "category": "<casual/work/decision/emotional>",
  "valence": "<positive/negative/neutral>",
  "arousal": <0-100の整数>,
  "tags": ["<感情タグ1>", "<感情タグ2>"]
}}
```

## 判定基準
- category: 雑談・日常=casual、仕事・技術=work、重要な意思決定=decision、感情的な話題=emotional
- valence: 発言のポジティブ/ネガティブ/ニュートラル
- arousal: 感情の覚醒度（穏やか=20-30、普通=40-60、興奮=70-90）
- tags: 発言に含まれる感情を表すタグ（例: 喜び、不安、感謝）"""


def _call_claude(
    prompt: str,
    config: dict[str, Any] | None = None,
    max_retries: int = 3,
    retry_delay: float = 1.0
) -> str:
    """
    Claude APIを呼び出す

    Args:
        prompt: プロンプト
        config: 設定辞書
        max_retries: 最大リトライ回数
        retry_delay: リトライ間隔（秒）

    Returns:
        生成されたテキスト

    Raises:
        APIError: API呼び出しに失敗した場合
    """
    if config is None:
        config = get_config()

    llm_config = config.get("llm", {})
    model = llm_config.get("model", "claude-3-5-haiku-20241022")
    temperature = llm_config.get("temperature", 0)
    max_tokens = llm_config.get("max_tokens", 1024)

    client = anthropic.Anthropic(timeout=DEFAULT_TIMEOUT)

    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            return response.content[0].text

        except RateLimitError:
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (attempt + 1))
                continue
            raise

        except APITimeoutError:
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            raise

        except APIError:
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            raise

    raise APIError("Max retries exceeded")


def _parse_json_response(text: str) -> dict[str, Any]:
    """
    LLMの応答からJSONを抽出してパース

    Args:
        text: LLMの応答テキスト

    Returns:
        パースされた辞書

    Raises:
        json.JSONDecodeError: JSONのパースに失敗した場合
    """
    # コードブロック内のJSONを抽出
    if "```json" in text:
        start = text.find("```json") + 7
        end = text.find("```", start)
        text = text[start:end].strip()
    elif "```" in text:
        start = text.find("```") + 3
        end = text.find("```", start)
        text = text[start:end].strip()

    return json.loads(text)


def analyze_emotion_batch(
    turns: list[tuple[str, str]],
    config: dict[str, Any] | None = None,
    max_retries: int = 2,
    poll_interval: float = 5.0,
    log_func=None
) -> dict[int, dict[str, Any]]:
    """
    複数ターンの感情分析をMessage Batch APIで一括実行

    Args:
        turns: (user_message, assistant_message) のリスト
        config: 設定辞書
        max_retries: 失敗したリクエストのリトライ回数（個別フォールバック）
        poll_interval: バッチ完了ポーリング間隔（秒）
        log_func: ログ関数

    Returns:
        {ターンインデックス: 感情分析結果} の辞書
    """
    if not turns:
        return {}

    if config is None:
        config = get_config()

    def log(msg):
        if log_func:
            log_func(msg)

    llm_config = config.get("llm", {})
    model = llm_config.get("model", "claude-3-5-haiku-20241022")
    temperature = llm_config.get("temperature", 0)
    max_tokens = llm_config.get("max_tokens", 1024)

    client = anthropic.Anthropic(timeout=DEFAULT_TIMEOUT)

    # バッチリクエスト構築
    requests = []
    for i, (user_msg, assistant_msg) in enumerate(turns):
        prompt = EMOTION_ANALYSIS_PROMPT.format(
            user_message=user_msg,
            assistant_message=assistant_msg
        )
        requests.append({
            "custom_id": f"turn_{i}",
            "params": {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}]
            }
        })

    log(f"Submitting emotion analysis batch: {len(requests)} requests")

    batch = client.messages.batches.create(requests=requests)
    log(f"Batch created: {batch.id}")

    # ポーリングで完了待ち
    while batch.processing_status != "ended":
        time.sleep(poll_interval)
        batch = client.messages.batches.retrieve(batch.id)
        counts = batch.request_counts
        log(f"Batch {batch.id}: {batch.processing_status} "
            f"(succeeded={counts.succeeded}, errored={counts.errored}, "
            f"processing={counts.processing})")

    # 結果収集
    results = {}
    failed_indices = []

    for result in client.messages.batches.results(batch.id):
        idx = int(result.custom_id.split("_")[1])
        if result.result.type == "succeeded":
            try:
                text = result.result.message.content[0].text
                parsed = _parse_json_response(text)
                results[idx] = parsed
            except Exception as e:
                log(f"Parse error for turn_{idx}: {e}")
                failed_indices.append(idx)
        else:
            log(f"Batch error for turn_{idx}: {result.result.type}")
            failed_indices.append(idx)

    log(f"Batch completed: {len(results)} succeeded, {len(failed_indices)} failed")

    # 失敗分を個別リクエストでリトライ
    for retry_attempt in range(max_retries):
        if not failed_indices:
            break
        log(f"Retrying {len(failed_indices)} failed requests "
            f"(attempt {retry_attempt + 1}/{max_retries})")
        still_failed = []
        for idx in failed_indices:
            user_msg, assistant_msg = turns[idx]
            try:
                analysis = analyze_emotion(user_msg, assistant_msg, config)
                results[idx] = analysis
                log(f"Retry succeeded for turn_{idx}")
            except Exception as e:
                log(f"Retry failed for turn_{idx}: {e}")
                still_failed.append(idx)
        failed_indices = still_failed

    if failed_indices:
        log(f"WARNING: {len(failed_indices)} turns permanently failed: {failed_indices}")

    return results


def classify_query(
    query: str,
    config: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    ユーザー発言のカテゴリと感情状態を分類する（想起時に使用）

    Args:
        query: ユーザーの発言
        config: 設定辞書

    Returns:
        分類結果の辞書:
            - category: casual/work/decision/emotional
            - valence: positive/negative/neutral
            - arousal: 0-100
            - tags: 感情タグのリスト
    """
    prompt = QUERY_CLASSIFY_PROMPT.format(query=query)
    response = _call_claude(prompt, config)
    result = _parse_json_response(response)

    # バリデーション: categoryが不正な場合はcasualにフォールバック
    valid_categories = {"casual", "work", "decision", "emotional"}
    if result.get("category") not in valid_categories:
        result["category"] = "casual"

    return result


def analyze_emotion(
    user_message: str,
    assistant_message: str,
    config: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    会話の感情分析を行う

    Args:
        user_message: ユーザーの発言
        assistant_message: アシスタントの応答
        config: 設定辞書

    Returns:
        感情分析結果の辞書
    """
    prompt = EMOTION_ANALYSIS_PROMPT.format(
        user_message=user_message,
        assistant_message=assistant_message
    )

    response = _call_claude(prompt, config)
    return _parse_json_response(response)


def summarize_memory(
    trigger: str,
    content: str,
    config: dict[str, Any] | None = None
) -> tuple[str, str]:
    """
    記憶を要約する（Level 1 → 2 圧縮用）

    Args:
        trigger: 元のtrigger
        content: 元のcontent
        config: 設定辞書

    Returns:
        (要約されたtrigger, 要約されたcontent) のタプル
    """
    prompt = SUMMARIZE_PROMPT.format(trigger=trigger, content=content)
    response = _call_claude(prompt, config)
    result = _parse_json_response(response)
    return result.get("trigger", trigger), result.get("content", content)


def compress_to_level2(
    trigger: str,
    content: str,
    config: dict[str, Any] | None = None
) -> tuple[str, str]:
    """
    Level 1 → Level 2 への圧縮

    Args:
        trigger: 元のtrigger
        content: 元のcontent
        config: 設定辞書

    Returns:
        (要約されたtrigger, 要約されたcontent) のタプル
    """
    return summarize_memory(trigger, content, config)


