# LTM System セットアップガイド

Claude Code用の長期記憶システムを導入するための設定手順です。

## 前提条件

- Python 3.10以上
- Claude Code CLI
- OpenAI APIキー（Embedding生成用）
- Anthropic APIキー（感情分析用）

## 1. 環境構築

### 1.1 リポジトリのクローン

```bash
git clone <repository-url>
cd LTM_system
```

### 1.2 Python仮想環境の作成

```bash
# Windows
python -m venv venv
.\venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### 1.3 依存パッケージのインストール

```bash
pip install numpy openai anthropic
```

## 2. 環境変数の設定

以下の環境変数を設定してください。

| 変数名 | 説明 |
|--------|------|
| `OPENAI_API_KEY` | OpenAI APIキー（Embedding生成に使用） |
| `ANTHROPIC_API_KEY` | Anthropic APIキー（感情分析に使用） |

### Windows（システム環境変数）

1. 「システムのプロパティ」→「環境変数」を開く
2. 「システム環境変数」または「ユーザー環境変数」に追加
3. PCを再起動するか、新しいターミナルを開く

### macOS/Linux

```bash
# ~/.bashrc または ~/.zshrc に追加
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
```

## 3. 設定ファイルの準備

### 3.1 config.json

`config/config.example.json` をコピーして `config/config.json` を作成：

```bash
cp config/config.example.json config/config.json
```

必要に応じてパラメータを調整してください。主な設定項目：

| セクション | 項目 | 説明 |
|------------|------|------|
| `embedding.model` | Embeddingモデル | デフォルト: `text-embedding-3-small` |
| `llm.model` | 感情分析用LLM | デフォルト: `claude-3-5-haiku-20241022` |
| `retrieval.top_k` | 想起する記憶の最大数 | デフォルト: `5` |
| `compression.schedule_hour` | バッチ実行時刻 | デフォルト: `3`（午前3時） |

### 3.2 データディレクトリ

```bash
mkdir -p data
```

`data/memories.db` は初回実行時に自動作成されます。

## 4. Claude Code Hook の設定

### 4.1 settings.json の作成

プロジェクトの `.claude/settings.json` を作成します。

**重要**: `command` のPythonパスは環境に合わせて変更してください。

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "<PYTHON_PATH> <PROJECT_PATH>/src/memory_retrieval.py"
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "<PYTHON_PATH> <PROJECT_PATH>/src/memory_generation.py"
          }
        ]
      }
    ]
  }
}
```

### 4.2 パスの設定例

#### Windows（フルパス）

```json
"command": "C:\\Users\\username\\project\\LTM_system\\venv\\Scripts\\python.exe C:\\Users\\username\\project\\LTM_system\\src\\memory_retrieval.py"
```

#### macOS/Linux（フルパス）

```json
"command": "/home/username/project/LTM_system/venv/bin/python /home/username/project/LTM_system/src/memory_retrieval.py"
```

#### 相対パス（作業ディレクトリがプロジェクトルートの場合）

```json
"command": "./venv/bin/python src/memory_retrieval.py"
```

## 5. 動作確認

### 5.1 テストの実行

```bash
# venvをアクティベートした状態で
pytest tests/ -v
```

全テストがパスすることを確認してください。

### 5.2 Hookの動作確認

1. Claude Codeを起動
2. 任意のメッセージを送信
3. エラーが表示されなければ成功

初回は記憶がないため、`<memories>` タグは表示されません。

## 6. 日次バッチの設定（任意）

記憶の圧縮・アーカイブ処理を定期実行する場合：

### Windows（タスクスケジューラ） - 推奨

セットアップスクリプトを使用して自動設定できます。

#### 自動セットアップ（推奨）

1. PowerShellを**管理者権限**で開く
2. プロジェクトディレクトリに移動：
   ```powershell
   cd c:\Users\XXX\Desktop\work\LTM_system
   ```
3. 実行ポリシーを設定（初回のみ）：
   ```powershell
   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
   ```
4. セットアップスクリプトを実行：
   ```powershell
   .\scripts\setup_scheduler.ps1
   ```

#### スクリプトの機能

- **タスク名**: `LTM_System_Compression`
- **実行時刻**: `config/config.json` の `compression.schedule_hour` から取得（デフォルト: 午前3時）
- **StartWhenAvailable**: 有効（PCがスリープ中でスケジュールを逃した場合、起動時に実行）
- **バッテリー動作**: 許可

#### 確認・管理コマンド

```powershell
# タスクの確認
Get-ScheduledTask -TaskName 'LTM_System_Compression'

# 手動実行（テスト用）
Start-ScheduledTask -TaskName 'LTM_System_Compression'

# タスクの削除
.\scripts\setup_scheduler.ps1 -Remove
```

#### 手動セットアップ（代替方法）

1. タスクスケジューラを開く
2. 「基本タスクの作成」を選択
3. トリガー: 毎日、午前3時
4. 操作: プログラムの開始
   - プログラム: `<venv>/Scripts/python.exe`
   - 引数: `<project>/src/compression.py`
   - 開始: `<project>`
5. プロパティで「StartWhenAvailable」を有効化

### macOS/Linux（cron）

```bash
crontab -e

# 毎日午前3時に実行
0 3 * * * cd /path/to/LTM_system && ./venv/bin/python src/compression.py
```

## トラブルシューティング

### ImportError: No module named 'xxx'

- venvがアクティベートされているか確認
- `pip install numpy openai anthropic` を再実行

### Hook実行時のエラー

- settings.jsonのパスが正しいか確認
- 環境変数が設定されているか確認
- Pythonパスがvenv内のものを指しているか確認

### APIエラー

- APIキーが正しく設定されているか確認
- APIの利用制限に達していないか確認

## ファイル構成

```
LTM_system/
├── .claude/
│   └── settings.json     # Hook設定（要作成）
├── config/
│   ├── config.example.json
│   └── config.json       # 設定ファイル（要作成）
├── data/
│   └── memories.db       # 記憶DB（自動作成）
├── src/
│   ├── memory_retrieval.py  # UserPromptSubmit Hook
│   ├── memory_generation.py # SessionEnd Hook
│   ├── compression.py       # 日次バッチ
│   └── ...
├── tests/
│   └── ...
├── venv/                 # 仮想環境（要作成）
├── SETUP.md              # このファイル
└── memory.md             # 設計ドキュメント
```
