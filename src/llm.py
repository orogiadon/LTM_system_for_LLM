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


# キーワード抽出プロンプト（Level 2 → 3）
KEYWORD_EXTRACT_PROMPT = """以下のテキストから重要なキーワードを5〜10語抽出してください。

## テキスト
{text}

## 出力形式
以下のJSON形式で出力してください。余計な説明は不要です。

```json
{{
  "keywords": ["キーワード1", "キーワード2", ...]
}}
```"""


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


def extract_keywords(text: str, config: dict[str, Any] | None = None) -> list[str]:
    """
    テキストからキーワードを抽出する（Level 2 → 3 圧縮用）

    Args:
        text: キーワード抽出対象のテキスト
        config: 設定辞書

    Returns:
        キーワードのリスト
    """
    prompt = KEYWORD_EXTRACT_PROMPT.format(text=text)
    response = _call_claude(prompt, config)
    result = _parse_json_response(response)
    return result.get("keywords", [])


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


def compress_to_level3(
    trigger: str,
    content: str,
    config: dict[str, Any] | None = None
) -> tuple[str, str]:
    """
    Level 2 → Level 3 への圧縮

    Args:
        trigger: 元のtrigger
        content: 元のcontent
        config: 設定辞書

    Returns:
        (キーワード化されたtrigger, キーワード化されたcontent) のタプル
    """
    # trigger と content をそれぞれキーワード化
    trigger_keywords = extract_keywords(trigger, config)
    content_keywords = extract_keywords(content, config)

    # キーワードをカンマ区切りの文字列に
    trigger_result = ", ".join(trigger_keywords) if trigger_keywords else trigger
    content_result = ", ".join(content_keywords) if content_keywords else content

    return trigger_result, content_result
