# LTM System

Claude Code 用の長期記憶（Long-Term Memory）システム。人間の記憶メカニズムを模倣し、感情強度と時間経過に基づいて記憶を自然に忘却・圧縮する。

## 特徴

- **感情ベースの記憶保持**: 感情的インパクトが強い記憶ほど長く保持される
- **自然な忘却曲線**: 時間経過による減衰と、想起による強化を再現
- **2段階の記憶レベル**: 完全記憶 → 要約記憶へと段階的に圧縮、閾値以下はアーカイブ
- **感情共鳴検索**: 現在の文脈の感情状態に近い記憶を優先的に想起
- **Claude Code Hook 統合**: プロンプト送信時に自動で関連記憶を挿入

## 動作イメージ

```
[ユーザー入力] → memory_retrieval.py → 関連記憶を <memories> タグで挿入
                                      ↓
[セッション終了] → memory_generation.py → 会話から記憶を生成・保存
                                      ↓
[日次バッチ]    → compression.py → 記憶の減衰・圧縮・アーカイブ
```

## 必要要件

- Python 3.10+
- Claude Code CLI
- OpenAI API キー（Embedding 生成用）
- Anthropic API キー（感情分析用）

### 動作環境

| 項目 | 状態 |
|------|------|
| Windows | 推奨（開発・テスト環境） |
| macOS / Linux | 動作するはずだが未検証 |
| ローカル LLM（Ollama 等） | 未対応 |

## クイックスタート

```bash
# 1. クローン
git clone https://github.com/your-username/LTM_system.git
cd LTM_system

# 2. 仮想環境
python -m venv venv
.\venv\Scripts\activate  # Windows
# source venv/bin/activate  # macOS/Linux

# 3. 依存パッケージ
pip install -r requirements.txt

# 4. 設定ファイル
cp config/config.example.json config/config.json

# 5. 環境変数（APIキー）
# OPENAI_API_KEY, ANTHROPIC_API_KEY を設定
```

詳細なセットアップ手順は [SETUP.md](SETUP.md) を参照。

## 設定

`config/config.json` で各種パラメータを調整可能。

| セクション | 説明 |
|-----------|------|
| `retention` | 減衰係数、カテゴリ別の忘却速度 |
| `levels` | 記憶レベルの閾値 |
| `compression` | 圧縮バッチの実行設定 |
| `retrieval` | 想起時の検索パラメータ |
| `embedding` | Embedding モデル設定 |
| `llm` | 感情分析用 LLM 設定 |

## 記憶レベル

| レベル | 保持スコア | 内容 |
|-------|-----------|------|
| Level 1 | 50以上 | 完全記憶（原文保持） |
| Level 2 | 20以上 | 要約記憶（LLM による要約） |
| Archive | 20未満 | アーカイブ（通常検索対象外） |

## コマンド

```bash
# 手動で圧縮バッチを実行
python src/compression.py

# CLI ツール
python src/memory_cli.py list           # 記憶一覧
python src/memory_cli.py show <id>      # 詳細表示
python src/memory_cli.py protect <id>   # 保護設定
python src/memory_cli.py archive <id>   # 手動アーカイブ
python src/memory_cli.py purge-archive  # アーカイブ一括削除
```

詳細は [MANUAL.md](MANUAL.md) を参照。

## ファイル構成

```
LTM_system/
├── src/
│   ├── memory_retrieval.py  # UserPromptSubmit Hook
│   ├── memory_generation.py # SessionEnd Hook
│   ├── compression.py       # 日次バッチ
│   ├── memory_store.py      # DB操作
│   ├── memory_cli.py        # CLIツール
│   └── ...
├── config/
│   ├── config.example.json  # 設定テンプレート
│   └── config.json          # 実際の設定（要作成）
├── data/
│   └── memories.db          # SQLite DB（自動生成）
├── scripts/
│   └── setup_scheduler.ps1  # Windows タスクスケジューラ設定
├── tests/                   # テストコード
├── SETUP.md                 # セットアップガイド
├── MANUAL.md                # 運用マニュアル
└── memory.md                # 設計ドキュメント
```

## コスト見積もり

1日100件の会話を1年間運用した場合の推定コスト。

### 前提条件

| 項目 | 値 |
|------|-----|
| 1日の会話数 | 100件 |
| 運用期間 | 1年（365日） |
| 総記憶数 | 36,500件 |

### 年間コスト

| 項目 | コスト（USD） | コスト（JPY, 150円換算） |
|------|--------------|-------------------------|
| Embedding (text-embedding-3-small) | $2.86 | ¥429 |
| LLM (Claude Haiku) | $322.30 | ¥48,345 |
| **合計** | **$325.16** | **¥48,774** |
| **月額換算** | **約$27** | **約¥4,100** |

### モデル別コスト比較

| モデル | 年間コスト | 月額 |
|--------|-----------|------|
| **Claude Haiku（推奨）** | **$325（¥48,800）** | **$27（¥4,100）** |
| Claude Sonnet | $1,225（¥183,800） | $102（¥15,300）|
| Claude Opus | $1,735（¥260,300） | $145（¥21,700） |

詳細な計算は [memory.md](memory.md) の「付録：年間コスト見積もり」を参照。

## ライセンス

MIT License
