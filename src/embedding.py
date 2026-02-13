"""
embedding.py - Embedding操作モジュール

OpenAI APIを使用してテキストをベクトル化する。
"""

import time
from typing import Any

from openai import OpenAI, APIError, RateLimitError, APITimeoutError

from config_loader import get_config

# デフォルトタイムアウト（秒）
DEFAULT_TIMEOUT = 30.0

# Embedding APIのトークン制限に対する安全マージン付き最大文字数
# text-embedding-3-small: 8191トークン上限、日本語1文字≒1トークンで概算
MAX_EMBEDDING_CHARS = 8000


def truncate_for_embedding(text: str, max_chars: int = MAX_EMBEDDING_CHARS) -> str:
    """
    Embeddingのトークン制限を超えないようにテキストを切り詰める

    Args:
        text: 入力テキスト
        max_chars: 最大文字数（日本語1文字≒1トークンで概算）

    Returns:
        切り詰められたテキスト
    """
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def get_embedding(
    text: str,
    config: dict[str, Any] | None = None,
    max_retries: int = 3,
    retry_delay: float = 1.0
) -> list[float]:
    """
    テキストをベクトル化

    Args:
        text: ベクトル化するテキスト
        config: 設定辞書（Noneの場合は自動読み込み）
        max_retries: 最大リトライ回数
        retry_delay: リトライ間隔（秒）

    Returns:
        Embeddingベクトル（1536次元）

    Raises:
        APIError: API呼び出しに失敗した場合
    """
    if config is None:
        config = get_config()

    embedding_config = config.get("embedding", {})
    model = embedding_config.get("model", "text-embedding-3-small")

    client = OpenAI(timeout=DEFAULT_TIMEOUT)

    for attempt in range(max_retries):
        try:
            response = client.embeddings.create(
                input=text,
                model=model
            )
            return response.data[0].embedding

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

    # ここには到達しないはずだが、型チェックのため
    raise APIError("Max retries exceeded")


def get_embeddings_batch(
    texts: list[str],
    config: dict[str, Any] | None = None,
    max_retries: int = 3,
    retry_delay: float = 1.0
) -> list[list[float]]:
    """
    複数テキストを一括でベクトル化

    Args:
        texts: ベクトル化するテキストのリスト
        config: 設定辞書（Noneの場合は自動読み込み）
        max_retries: 最大リトライ回数
        retry_delay: リトライ間隔（秒）

    Returns:
        Embeddingベクトルのリスト

    Raises:
        APIError: API呼び出しに失敗した場合
    """
    if not texts:
        return []

    if config is None:
        config = get_config()

    embedding_config = config.get("embedding", {})
    model = embedding_config.get("model", "text-embedding-3-small")

    client = OpenAI(timeout=DEFAULT_TIMEOUT)

    for attempt in range(max_retries):
        try:
            response = client.embeddings.create(
                input=texts,
                model=model
            )
            # APIはinputの順序を保証するが、念のためindexでソート
            sorted_data = sorted(response.data, key=lambda x: x.index)
            return [item.embedding for item in sorted_data]

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
