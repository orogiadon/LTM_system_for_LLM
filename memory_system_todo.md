# 記憶システム実装TODO

## 概要

memory.mdで設計した記憶システムの実装計画。設計は完了済みのため、実装フェーズに移行可能。

**技術スタック（決定済み）**
- Embedding: OpenAI text-embedding-3-small（1536次元）
- LLM: Claude 3.5 Haiku（temperature=0）
- ストレージ: SQLite（memories.db）
- 排他制御: SQLiteトランザクション（組み込み）
- 類似度計算: NumPy（ANN不要）

---

## Phase 1: コアシステム

最小限の機能で動作する記憶システムを構築する。

### 1.1 基盤モジュール

- [x] **config_loader.py**: 設定ファイル読み込み
  - [x] config.json のパース
  - [x] デフォルト値のマージ
  - [ ] バリデーション（任意）

- [x] **memory_store.py**: 記憶ストレージ操作（SQLite）
  - [x] MemoryStoreクラス実装
  - [x] `_init_db()`: テーブル・インデックス作成
  - [x] `_connect()`: WALモード有効化、コネクション管理
  - [x] `connection()`: 直接SQL実行用コネクション取得
  - [x] `add_memory()`: 記憶追加（bool→int変換含む）
  - [x] `get_active_memories()`: アクティブ記憶取得
  - [x] `get_archived_memories()`: アーカイブ記憶取得
  - [x] `update_memory()`: 記憶更新（JSON/Embedding変換含む）
  - [x] `mark_recalled()`: 想起フラグ一括更新
  - [x] `delete_memory()`: 記憶削除
  - [x] `get_state()` / `set_state()`: 状態管理
  - [x] `_encode_embedding()` / `_decode_embedding()`: BLOB変換
  - [x] `_row_to_dict()`: Row→dict変換（JSON/bool復元）

### 1.2 記憶生成（SessionEnd Hook）

- [x] **memory_generation.py**: セッション終了時の記憶生成
  - [x] 標準入力からHookメタデータ取得（JSON）
  - [x] transcript_path からJSONL読み込み
  - [x] ターン抽出（user + assistant ペア）
  - [x] スラッシュコマンド除外判定
  - [x] LLM呼び出し（感情分析・要約）
    - [x] emotional_intensity (0-100)
    - [x] emotional_valence (positive/negative/neutral)
    - [x] emotional_arousal (0-100)
    - [x] emotional_tags
    - [x] category (casual/work/decision/emotional)
    - [x] keywords
    - [x] trigger（ユーザーの発言・行動の要約）
    - [x] content（自分の反応・感想の要約）
  - [x] Embedding生成（text-embedding-3-small）
  - [x] memory_days 初期値計算（次回バッチまでの経過時間）
  - [x] 減衰係数決定（カテゴリ × 感情強度）
  - [x] 保護記憶検出（「覚えておいて」等のフレーズ）
  - [x] SQLiteへの追加（MemoryStore.add_memory()経由）

### 1.3 記憶想起（UserPromptSubmit Hook）

- [x] **memory_retrieval.py**: メッセージ送信時の記憶検索
  - [x] 標準入力からプロンプト取得（JSON）
  - [x] スラッシュコマンド除外判定
  - [x] クエリのEmbedding生成
  - [x] アクティブ記憶検索
  - [x] アーカイブ検索（enable_archive_recall = true の場合）
  - [x] コサイン類似度計算
  - [x] 参照優先度計算
    - [x] retention_score × 類似度 × (1 + 0.1 × recall_count)
  - [x] 感情共鳴スコア計算（resonance.py を使用）
  - [x] 閾値+フォールバック方式での上位N件抽出（retrieval.top_k, retrieval.relevance_threshold）
  - [x] 記憶フォーマット出力（`<memories>` タグ）
  - [x] アクティブ記憶の想起フラグ更新（mark_recalled）
  - [x] アーカイブ記憶の復活リクエストフラグ更新

### 1.4 日次バッチ処理

- [x] **compression.py**: 圧縮・アーカイブ処理（メイン）
  - [x] 実行条件チェック（last_compression_run + interval_hours）
  - [x] recall.py を呼び出して想起強化処理
  - [x] memory_days +1.0（想起されなかった記憶）
  - [x] retention.py を呼び出して retention_score 再計算
  - [x] 閾値判定による圧縮
    - [x] Level 1 → 2: LLM要約生成
    - [x] Level 2 → 3: LLMキーワード抽出
    - [x] Level 3 → 4: アーカイブ移行（archived_at設定）
  - [x] 圧縮後のEmbedding再生成（trigger + content で再生成）
  - [x] アーカイブ復活処理
    - [x] revival_requested = 1 の記憶を抽出
    - [x] 比率チェック（Level 3 が 35% 未満なら復活）
    - [x] 復活時の retention_score 計算
    - [x] archived_at を NULL に更新してアクティブ化
  - [x] 比率強制処理
    - [x] Level 1 超過 → Level 2 へ強制圧縮
    - [x] Level 2 超過 → Level 3 へ強制圧縮
    - [x] Level 3 超過 → アーカイブへ強制移行
    - [x] 対象選定（retention_score → created → recall_count）
    - [x] 保護記憶は除外
  - [x] relations.py を呼び出して関連付け処理
  - [x] アーカイブ自動削除（条件に合致する記憶を完全消去）
  - [x] last_compression_run 更新

- [x] **recall.py**: 想起強化処理
  - [x] recalled_since_last_batch = 1 の記憶を処理
  - [x] memory_days 半減（memory_days_reduction: 0.5）
  - [x] decay_coefficient +0.02（上限 max_decay_coefficient: 0.999）
  - [x] recall_count インクリメント
  - [x] recalled_since_last_batch = 0 にリセット

- [x] **retention.py**: 保持スコア計算
  - [x] retention_score = emotional_intensity × decay_coefficient^memory_days
  - [x] レベル判定（閾値: 50 / 20 / 5）

- [x] **relations.py**: 記憶の関連付け
  - [x] 整合性チェック（削除された記憶への参照除去）
  - [x] 関連付け方向の再評価（スコア逆転時の参照張り替え）
  - [x] 自動関連付け（enable_auto_linking = true の場合）
    - [x] 新規記憶 vs 全記憶 のみ比較（O(m×n)）
    - [x] find_similar_memories()（NumPy行列演算）
    - [x] 関連付け方向決定（高スコア → 低スコア）
    - [x] max_relations_per_memory 上限チェック

### 1.5 補助モジュール

- [x] **resonance.py**: 感情共鳴計算
  - [x] valence一致ボーナス（0.3）
  - [x] arousal近接ボーナス（最大0.2）
  - [x] tags重複ボーナス（重み0.5）

- [x] **embedding.py**: Embedding操作
  - [x] OpenAI API呼び出し（text-embedding-3-small）
  - [x] バッチ生成対応
  - [x] エラーハンドリング（リトライ等）

- [x] **llm.py**: LLM操作
  - [x] Claude API呼び出し（Haiku、temperature=0）
  - [x] 感情分析プロンプト
  - [x] 圧縮プロンプト
    - [x] Level 1→2: content要約（元の30%程度に圧縮）
    - [x] Level 2→3: trigger・contentをキーワード抽出（各5〜10語）
  - [x] JSON出力パース
  - [x] エラーハンドリング

### 1.6 Hook設定

- [x] `.claude/settings.json` にHook設定を追加
  - [x] UserPromptSubmit: memory_retrieval.py
  - [x] SessionEnd: memory_generation.py

### 1.7 初期データ

- [x] `config/config.json` の作成（設計書のテンプレートをコピー）
- [x] `data/memories.db` の初期化（MemoryStore初回接続時に自動作成）

### Phase 1 完了基準

- [x] セッション終了時に記憶が生成される
- [x] メッセージ送信時に関連記憶が注入される
- [x] 日次バッチで圧縮・アーカイブが動作する
- [x] 想起による強化が機能する

---

## Phase 2: 機能拡充

Phase 1 の基盤上に追加機能を実装する。

### 2.1 アーカイブ復活

- [ ] 想起時のアーカイブ検索
- [ ] 比率チェック（Level 3 が 35% 未満なら復活）
- [ ] 復活時の retention_score 計算（revival_decay_per_day使用）
- [ ] archived_at フィールドでの区別（NULL=アクティブ）

### 2.2 保護記憶

- [ ] protected フラグの処理
- [ ] 圧縮・アーカイブ・削除からの除外
- [ ] 比率計算からの除外
- [ ] 上限チェック（max_protected_memories: 50件）
- [ ] 上限超過時のユーザー確認フロー

### 2.3 バッチ処理スケジューリング

- [ ] スケジューラの実装方法決定
  - [ ] 案A: OS のタスクスケジューラ（cron / Task Scheduler）← 推奨
  - [ ] 案B: 常駐プロセス + sleep
  - [ ] 案C: 起動時フォールバックのみ
- [ ] フォールバック処理（前回実行から24時間以上経過時）

### 2.4 関連記憶の展開

- [ ] get_with_relations() の実装
- [ ] 深度制限（relation_traversal_depth: 1）
- [ ] 想起結果への関連記憶追加

### Phase 2 完了基準

- [ ] アーカイブから記憶が復活する
- [ ] 保護記憶が圧縮されない
- [ ] 定期的にバッチ処理が実行される
- [ ] 関連記憶が一緒に想起される

---

## Phase 3: 運用機能

長期運用に必要な機能を追加する。

### 3.1 デバッグ・管理ツール

- [ ] 記憶一覧表示コマンド
- [ ] 記憶の手動削除
- [ ] 保護の手動設定/解除（unprotect_memory）
- [ ] 統計表示（総数、レベル別分布、想起頻度等）

### 3.2 バックアップ

- [ ] 手動バックアップスクリプト（bash / PowerShell）
- [ ] SQLiteの安全なバックアップ（`.backup`コマンド）
- [ ] 復旧手順のドキュメント

### 3.3 エラーハンドリング

- [ ] API タイムアウト時の処理
- [ ] JSON パースエラー時のフォールバック
- [ ] ログ出力の実装
- [ ] エラー時の通知（任意）

### 3.4 パフォーマンス監視

- [ ] バッチ処理時間の計測
- [ ] DBサイズの監視
- [ ] 警告閾値の設定（1GB等）
- [ ] VACUUM実行の推奨通知

### Phase 3 完了基準

- [ ] 記憶の状態を確認・管理できる
- [ ] バックアップ・復旧が可能
- [ ] エラー時に適切に処理される
- [ ] 長期運用の問題を早期発見できる

---

## テスト

### 単体テスト

- [x] retention.py: 保持スコア計算
- [x] recall.py: 想起強化処理
- [x] resonance.py: 感情共鳴計算
- [x] relations.py: 類似度計算、関連付け方向
- [x] memory_store.py: CRUD操作、トランザクション
- [x] config_loader.py: 設定読み込み
- [x] memory_retrieval.py: 純粋関数（cosine_similarity, format_memories等）

### 統合テスト

- [ ] 記憶生成フロー全体
- [ ] 記憶想起フロー全体
- [ ] バッチ処理フロー全体
- [ ] アーカイブ復活フロー

### エッジケース

- [ ] 感情強度 0 / 100 の挙動
- [ ] 記憶 0 件時の想起
- [ ] 同時アクセス時の排他制御（SQLite WALモード）
- [ ] 大量記憶時のパフォーマンス（36,500件想定）

---

## 進捗管理

| Phase | ステータス | 開始日 | 完了日 | 備考 |
|-------|-----------|--------|--------|------|
| Phase 1 | 完了 | 2026-01-18 | 2026-01-21 | コアシステム |
| Phase 2 | 未着手 | - | - | 機能拡充 |
| Phase 3 | 未着手 | - | - | 運用機能 |
| テスト | 進行中 | 2026-01-21 | - | 単体テスト完了 |

---

## 実装優先順位（推奨）

1. **config_loader.py** - 他の全モジュールが依存
2. **memory_store.py** - ストレージ操作の基盤
3. **embedding.py** / **llm.py** - API連携
4. **memory_generation.py** - 記憶生成（これがないと始まらない）
5. **retention.py** / **recall.py** - スコア計算・想起強化
6. **memory_retrieval.py** - 記憶想起
7. **compression.py** - バッチ処理
8. **relations.py** / **resonance.py** - 追加機能

---

## ディレクトリ構造（設計書準拠）

```
LTM_system/
├── config/
│   ├── config.json          # 本番設定
│   ├── config.dev.json      # 開発用設定（任意）
│   └── config.schema.json   # バリデーション用スキーマ（任意）
├── src/
│   ├── config_loader.py     # 設定読み込みモジュール
│   ├── memory_store.py      # 記憶ストレージ操作（SQLite）
│   ├── retention.py         # 保持スコア計算
│   ├── recall.py            # 想起強化処理
│   ├── compression.py       # 圧縮処理
│   ├── resonance.py         # 感情共鳴計算
│   ├── relations.py         # 記憶の関連付け
│   ├── embedding.py         # Embedding操作
│   ├── llm.py               # LLM操作
│   ├── memory_retrieval.py  # 記憶検索（UserPromptSubmit Hook用）
│   └── memory_generation.py # 記憶生成（SessionEnd Hook用）
├── data/
│   └── memories.db          # SQLiteデータベース
├── memory.md                # 設計書
└── memory_system_todo.md    # 実装TODO（本ファイル）
```

---

*作成日: 2026-01-18*
*更新日: 2026-01-21*
*更新内容: 設計書（memory.md）との整合性を確認し全面改訂。SQLite移行に伴うmemory_store.py更新、recall.py独立モジュール化、archived_atフィールドでの区別方式に統一。*
