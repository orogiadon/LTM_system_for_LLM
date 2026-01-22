"""
memory_store.py - 記憶ストレージ操作モジュール（SQLite）

すべての記憶操作はこのクラスを経由して行う。
直接SQLを実行しないこと。
"""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

import numpy as np


class MemoryStore:
    """記憶ストレージを管理するクラス"""

    def __init__(self, db_path: str | Path):
        """
        Args:
            db_path: SQLiteデータベースファイルのパス
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """データベース初期化（テーブル・インデックス作成）"""
        with self._connect() as conn:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    created TEXT NOT NULL,
                    memory_days REAL DEFAULT 0.0,
                    recalled_since_last_batch INTEGER DEFAULT 0,
                    recall_count INTEGER DEFAULT 0,
                    emotional_intensity INTEGER NOT NULL,
                    emotional_valence TEXT NOT NULL,
                    emotional_arousal INTEGER NOT NULL,
                    emotional_tags TEXT,
                    decay_coefficient REAL NOT NULL,
                    category TEXT NOT NULL,
                    keywords TEXT,
                    current_level INTEGER DEFAULT 1,
                    trigger TEXT NOT NULL,
                    content TEXT NOT NULL,
                    embedding BLOB,
                    relations TEXT,
                    retention_score REAL,
                    archived_at TEXT,
                    protected INTEGER DEFAULT 0,
                    revival_requested INTEGER DEFAULT 0,
                    revival_requested_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_retention_score ON memories(retention_score);
                CREATE INDEX IF NOT EXISTS idx_current_level ON memories(current_level);
                CREATE INDEX IF NOT EXISTS idx_archived_at ON memories(archived_at);
                CREATE INDEX IF NOT EXISTS idx_created ON memories(created);

                CREATE TABLE IF NOT EXISTS state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
            ''')

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        """コネクション管理（WALモード有効）"""
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        """コネクションを取得（直接SQL実行用）"""
        with self._connect() as conn:
            yield conn

    def add_memory(self, memory: dict[str, Any]) -> None:
        """
        記憶を追加

        Args:
            memory: 記憶データ（id, created, emotional_intensity等を含む辞書）
        """
        with self._connect() as conn:
            conn.execute('''
                INSERT INTO memories (
                    id, created, memory_days, recalled_since_last_batch, recall_count,
                    emotional_intensity, emotional_valence, emotional_arousal, emotional_tags,
                    decay_coefficient, category, keywords, current_level, trigger, content,
                    embedding, relations, retention_score, archived_at, protected
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                memory['id'],
                memory['created'],
                memory.get('memory_days', 0.0),
                int(memory.get('recalled_since_last_batch', False)),
                memory.get('recall_count', 0),
                memory['emotional_intensity'],
                memory['emotional_valence'],
                memory['emotional_arousal'],
                json.dumps(memory.get('emotional_tags', []), ensure_ascii=False),
                memory['decay_coefficient'],
                memory['category'],
                json.dumps(memory.get('keywords', []), ensure_ascii=False),
                memory.get('current_level', 1),
                memory['trigger'],
                memory['content'],
                self._encode_embedding(memory.get('embedding')),
                json.dumps(memory.get('relations', []), ensure_ascii=False),
                memory.get('retention_score'),
                memory.get('archived_at'),
                int(memory.get('protected', False))
            ))

    def get_memory(self, memory_id: str) -> dict[str, Any] | None:
        """
        IDで記憶を取得

        Args:
            memory_id: 記憶ID

        Returns:
            記憶データまたはNone
        """
        with self._connect() as conn:
            row = conn.execute(
                'SELECT * FROM memories WHERE id = ?', (memory_id,)
            ).fetchone()
            return self._row_to_dict(row) if row else None

    def get_active_memories(self) -> list[dict[str, Any]]:
        """アクティブ記憶を取得（アーカイブ以外）"""
        with self._connect() as conn:
            rows = conn.execute(
                'SELECT * FROM memories WHERE archived_at IS NULL'
            ).fetchall()
            return [self._row_to_dict(row) for row in rows]

    def get_archived_memories(self) -> list[dict[str, Any]]:
        """アーカイブ記憶を取得"""
        with self._connect() as conn:
            rows = conn.execute(
                'SELECT * FROM memories WHERE archived_at IS NOT NULL'
            ).fetchall()
            return [self._row_to_dict(row) for row in rows]

    def get_memories_by_level(self, level: int, include_archived: bool = False) -> list[dict[str, Any]]:
        """
        レベルで記憶を取得

        Args:
            level: 記憶レベル（1-4）
            include_archived: アーカイブも含めるか

        Returns:
            記憶リスト
        """
        with self._connect() as conn:
            if include_archived:
                rows = conn.execute(
                    'SELECT * FROM memories WHERE current_level = ?', (level,)
                ).fetchall()
            else:
                rows = conn.execute(
                    'SELECT * FROM memories WHERE current_level = ? AND archived_at IS NULL',
                    (level,)
                ).fetchall()
            return [self._row_to_dict(row) for row in rows]

    def update_memory(self, memory_id: str, updates: dict[str, Any]) -> None:
        """
        記憶を更新

        Args:
            memory_id: 記憶ID
            updates: 更新するフィールドと値の辞書
        """
        # JSON/Embedding フィールドの変換
        if 'emotional_tags' in updates:
            updates['emotional_tags'] = json.dumps(updates['emotional_tags'], ensure_ascii=False)
        if 'keywords' in updates:
            updates['keywords'] = json.dumps(updates['keywords'], ensure_ascii=False)
        if 'relations' in updates:
            updates['relations'] = json.dumps(updates['relations'], ensure_ascii=False)
        if 'embedding' in updates:
            updates['embedding'] = self._encode_embedding(updates['embedding'])
        if 'recalled_since_last_batch' in updates:
            updates['recalled_since_last_batch'] = int(updates['recalled_since_last_batch'])
        if 'protected' in updates:
            updates['protected'] = int(updates['protected'])
        if 'revival_requested' in updates:
            updates['revival_requested'] = int(updates['revival_requested'])

        set_clause = ', '.join(f'{k} = ?' for k in updates.keys())
        values = list(updates.values()) + [memory_id]

        with self._connect() as conn:
            conn.execute(f'UPDATE memories SET {set_clause} WHERE id = ?', values)

    def mark_recalled(self, memory_ids: list[str]) -> None:
        """
        想起フラグを立てる

        Args:
            memory_ids: 想起された記憶IDのリスト
        """
        if not memory_ids:
            return

        with self._connect() as conn:
            placeholders = ','.join('?' * len(memory_ids))
            conn.execute(f'''
                UPDATE memories
                SET recalled_since_last_batch = 1
                WHERE id IN ({placeholders}) AND archived_at IS NULL
            ''', memory_ids)

    def delete_memory(self, memory_id: str) -> None:
        """
        記憶を完全削除

        Args:
            memory_id: 削除する記憶ID
        """
        with self._connect() as conn:
            conn.execute('DELETE FROM memories WHERE id = ?', (memory_id,))

    def get_state(self, key: str) -> str | None:
        """
        状態を取得

        Args:
            key: 状態キー

        Returns:
            状態値またはNone
        """
        with self._connect() as conn:
            row = conn.execute(
                'SELECT value FROM state WHERE key = ?', (key,)
            ).fetchone()
            return row['value'] if row else None

    def set_state(self, key: str, value: str) -> None:
        """
        状態を設定

        Args:
            key: 状態キー
            value: 状態値
        """
        with self._connect() as conn:
            conn.execute('''
                INSERT OR REPLACE INTO state (key, value) VALUES (?, ?)
            ''', (key, value))

    def get_all_memories(self, include_archived: bool = True) -> list[dict[str, Any]]:
        """
        全記憶を取得

        Args:
            include_archived: アーカイブも含めるか

        Returns:
            記憶リスト
        """
        with self._connect() as conn:
            if include_archived:
                rows = conn.execute('SELECT * FROM memories').fetchall()
            else:
                rows = conn.execute(
                    'SELECT * FROM memories WHERE archived_at IS NULL'
                ).fetchall()
            return [self._row_to_dict(row) for row in rows]

    def count_memories(self, include_archived: bool = True) -> int:
        """
        記憶の総数を取得

        Args:
            include_archived: アーカイブも含めるか

        Returns:
            記憶の総数
        """
        with self._connect() as conn:
            if include_archived:
                row = conn.execute('SELECT COUNT(*) as count FROM memories').fetchone()
            else:
                row = conn.execute(
                    'SELECT COUNT(*) as count FROM memories WHERE archived_at IS NULL'
                ).fetchone()
            return row['count']

    def count_by_level(self) -> dict[int, int]:
        """
        レベル別の記憶数を取得

        Returns:
            レベルをキー、件数を値とする辞書
        """
        with self._connect() as conn:
            rows = conn.execute('''
                SELECT current_level, COUNT(*) as count
                FROM memories
                WHERE archived_at IS NULL
                GROUP BY current_level
            ''').fetchall()
            return {row['current_level']: row['count'] for row in rows}

    def count_protected(self) -> int:
        """
        保護記憶の件数を取得

        Returns:
            保護記憶の件数
        """
        with self._connect() as conn:
            row = conn.execute(
                'SELECT COUNT(*) as count FROM memories WHERE protected = 1'
            ).fetchone()
            return row['count']

    def _encode_embedding(self, embedding: list[float] | None) -> bytes | None:
        """EmbeddingをBLOBに変換"""
        if embedding is None:
            return None
        return np.array(embedding, dtype=np.float32).tobytes()

    def _decode_embedding(self, blob: bytes | None) -> list[float] | None:
        """BLOBからEmbeddingを復元"""
        if blob is None:
            return None
        return np.frombuffer(blob, dtype=np.float32).tolist()

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        """sqlite3.Rowを辞書に変換"""
        d = dict(row)
        # JSON フィールドをパース
        d['emotional_tags'] = json.loads(d['emotional_tags']) if d['emotional_tags'] else []
        d['keywords'] = json.loads(d['keywords']) if d['keywords'] else []
        d['relations'] = json.loads(d['relations']) if d['relations'] else []
        # Embedding を復元
        d['embedding'] = self._decode_embedding(d['embedding'])
        # Boolean 変換
        d['recalled_since_last_batch'] = bool(d['recalled_since_last_batch'])
        d['protected'] = bool(d['protected'])
        d['revival_requested'] = bool(d.get('revival_requested', 0))
        return d
