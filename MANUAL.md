# LTM System 運用マニュアル

## 目次
1. [memory_cli.py - 記憶管理CLIツール](#memory_clipy---記憶管理cliツール)
2. [compression.py - 日次バッチ処理](#compressionpy---日次バッチ処理)
3. [backup.ps1 - データベースバックアップ](#backupps1---データベースバックアップ)
4. [タスクスケジューラ設定](#タスクスケジューラ設定)
5. [トラブルシューティング](#トラブルシューティング)

---

## memory_cli.py - 記憶管理CLIツール

記憶の一覧表示、詳細確認、削除、保護設定、統計表示などを行うCLIツール。

### 基本構文

```powershell
python src/memory_cli.py <command> [options]
```

### コマンド一覧

#### list - 記憶一覧表示

```powershell
# アクティブな記憶を表示（デフォルト20件）
python src/memory_cli.py list

# 件数を指定
python src/memory_cli.py list --limit 50
python src/memory_cli.py list -n 50

# レベルでフィルタ
python src/memory_cli.py list --level 1
python src/memory_cli.py list -l 2

# アーカイブ済み記憶を表示
python src/memory_cli.py list --archived
python src/memory_cli.py list -a

# 保護された記憶のみ表示
python src/memory_cli.py list --protected
python src/memory_cli.py list -p

# 組み合わせ
python src/memory_cli.py list -l 1 -p -n 10
```

出力例：
```
ID                        Date         L   Score P Trigger
-----------------------------------------------------------------------------------------------
abc123...                 2026-01-21   1    85.0 P 長期記憶システムのテスト...
def456...                 2026-01-20   2    42.3   コスト見積もりについて...

Total: 2 memories
```

#### show - 記憶詳細表示

```powershell
python src/memory_cli.py show <memory_id>
```

出力項目：
- ID, Created, Level, Retention Score
- Memory Days, Decay Coefficient, Recall Count
- Protected, Archived, Category
- Emotional Intensity/Valence/Arousal/Tags
- Keywords, Relations
- Trigger（全文）, Content（全文）

#### delete - 記憶削除

```powershell
# 確認付き削除
python src/memory_cli.py delete <memory_id>

# 強制削除（確認スキップ、保護記憶も削除可能）
python src/memory_cli.py delete <memory_id> --force
python src/memory_cli.py delete <memory_id> -f
```

#### protect - 記憶保護

```powershell
python src/memory_cli.py protect <memory_id>
```

保護された記憶は：
- 圧縮処理でレベルダウンしない
- アーカイブされない
- `--force` なしでは削除できない

#### unprotect - 保護解除

```powershell
python src/memory_cli.py unprotect <memory_id>
```

#### stats - 統計情報表示

```powershell
python src/memory_cli.py stats
```

出力例：
```
=== Memory Statistics ===

Total Memories:     150
  Active:           120
  Archived:         30
  Protected:        5

By Level (Active):
  Level 1:             18 ( 15.0%)
  Level 2:             36 ( 30.0%)
  Level 3:             42 ( 35.0%)
  Level 4:             24 ( 20.0%)

By Category (Active):
  casual              45 ( 37.5%)
  work                50 ( 41.7%)
  decision            15 ( 12.5%)
  emotional           10 (  8.3%)

Avg Retention Score: 35.50
Pending Recall:      3
Database Size:       2.45 MB
```

#### purge-archive - アーカイブ全削除

```powershell
# 確認付き（"yes"と入力で実行）
python src/memory_cli.py purge-archive

# 強制実行（確認スキップ）
python src/memory_cli.py purge-archive --force
python src/memory_cli.py purge-archive -f
```

**注意**: 保護された記憶は削除されない。アーカイブが肥大化した際のリセット用。

#### search - キーワード検索

```powershell
# 基本検索（trigger, content, keywordsを対象）
python src/memory_cli.py search "Python"

# アクティブ記憶のみ検索
python src/memory_cli.py search "Python" --active-only
python src/memory_cli.py search "Python" -a

# 件数制限
python src/memory_cli.py search "Python" --limit 10
python src/memory_cli.py search "Python" -n 10
```

---

## compression.py - 日次バッチ処理

日次で実行される圧縮・メンテナンス処理。

### 処理内容

1. **想起強化処理** - 想起された記憶のdecay_coefficient/memory_daysを強化
2. **memory_days更新** - 想起されなかった記憶のmemory_daysを+1.0
3. **retention_score再計算** - 全アクティブ記憶のスコアを再計算
4. **閾値判定による圧縮** - スコアが閾値を下回った記憶をレベルダウン
5. **アーカイブ復活処理** - revival_requestフラグが立った記憶を復活
6. **比率強制処理** - 各レベルの比率が目標を超過した場合の強制圧縮
7. **関連付け処理** - 類似記憶間の関連付けを更新
8. **アーカイブ自動削除** - 条件を満たすアーカイブ記憶を削除

### 実行方法

```powershell
# 通常実行（同じ日に既に実行済みならスキップ）
python src/compression.py

# 強制実行（日付チェックをスキップ）
python src/compression.py --force
python src/compression.py -f

# 詳細出力付き
python src/compression.py --verbose
python src/compression.py -v

# 組み合わせ
python src/compression.py -f -v
```

### 出力例

```
Pre-batch stats: 120 active, 2.45 MB
Compression batch completed:
  Elapsed time: 45.23s
  Recalled processed: 3
  Memory days updated: 117
  Retention scores updated: 120
  Compression: {'L1_to_L2': 2, 'L2_to_L3': 5, 'L3_to_L4': 3}
  Revived: 1
  Ratio enforcement: {'L1_forced': 0, 'L2_forced': 0, 'L3_forced': 2}
  Relations: {'new': 5, 'updated': 12}
  Deleted: 0

Post-batch stats:
  Active: 118 memories
  By level: {1: 18, 2: 35, 3: 42, 4: 23}
  Protected: 5
  DB size: 2.48 MB
```

### スキップ時の出力

```
Skipped: interval_not_elapsed
```

同じ日に既に実行済みの場合、処理をスキップして上記メッセージを出力。
`--force` オプションで強制実行可能。

---

## backup.ps1 - データベースバックアップ

SQLiteデータベースのバックアップスクリプト。WALモードに対応。

### 実行方法

```powershell
# デフォルト（backup/ディレクトリに保存、5世代保持）
.\scripts\backup.ps1

# 出力先を指定
.\scripts\backup.ps1 -OutputDir D:\backup\ltm

# 保持世代数を変更
.\scripts\backup.ps1 -Keep 10

# 組み合わせ
.\scripts\backup.ps1 -OutputDir D:\backup\ltm -Keep 7
```

### バックアップファイル

- ファイル名形式: `memories_YYYYMMDD_HHMMSS.db`
- WALファイル（存在する場合）: `memories_YYYYMMDD_HHMMSS.db-wal`
- SHMファイル（存在する場合）: `memories_YYYYMMDD_HHMMSS.db-shm`

### 出力例

```
Backing up database...
  Source: C:\Users\XXX\Desktop\work\LTM_system\data\memories.db
  Target: C:\Users\XXX\Desktop\work\LTM_system\backup\memories_20260122_030000.db
Backup completed.
  Size: 2.45 MB
  Deleted old backup: memories_20260117_030000.db

Backup successful! Kept: 5 backups
```

---

## タスクスケジューラ設定

### 推奨設定

| 項目 | 値 |
|------|-----|
| トリガー | 毎日 午前3:00 |
| アクション | プログラム: `python`<br>引数: `src/compression.py`<br>開始: `C:\Users\XXX\Desktop\work\LTM_system` |
| 条件 | AC電源接続時のみ（任意） |

### 設定手順

1. タスクスケジューラを開く
2. 「タスクの作成」を選択
3. 全般タブ：名前を「LTM Compression」等に設定
4. トリガータブ：「新規」→ 毎日、午前3:00
5. 操作タブ：「新規」→ 上記設定を入力
6. 「OK」で保存

### 注意事項

- 日付ベースでスキップ判定するため、手動で `--force` 実行後も翌日3時に正常実行される
- PCがスリープ中の場合、起動時に実行されるよう「スリープ解除」オプションを有効にすることを推奨

---

## トラブルシューティング

### compression.pyが「Skipped: interval_not_elapsed」で実行されない

**原因**: 同日中に既に実行済み

**解決策**:
```powershell
python src/compression.py --force
```

### memory_cli.pyの出力が文字化けする

**原因**: コンソールの文字コード設定

**解決策**:
```powershell
chcp 65001
python src/memory_cli.py stats
```

### データベースサイズが1GBを超えた

**警告メッセージ**: `WARNING: Database size exceeds 1GB. Consider running VACUUM.`

**解決策**:
```powershell
sqlite3 data/memories.db "VACUUM;"
```

または Python から:
```python
import sqlite3
conn = sqlite3.connect("data/memories.db")
conn.execute("VACUUM")
conn.close()
```

### バックアップが失敗する

**原因**: データベースがロックされている可能性

**解決策**:
1. compression.pyの実行が終了しているか確認
2. 他のプロセスがDBを使用していないか確認
3. WALファイル（`memories.db-wal`）が存在する場合、一旦システムを停止してから再試行

### 記憶が想定より早くアーカイブされる

**確認事項**:
1. `config/config.json` の `retention.decay_by_category` 設定を確認
2. 該当記憶の `category` が正しく設定されているか確認
3. `emotional_intensity` が低すぎないか確認

**対処法**:
- 重要な記憶は `protect` コマンドで保護
- decay係数の設定を見直し

### アーカイブからの復活が機能しない

**確認事項**:
1. `revival_request` フラグがセットされているか
2. 各レベルの比率が目標値を超過していないか（超過時は復活がブロックされる）

**確認方法**:
```powershell
python src/memory_cli.py stats
```
「By Level」の比率を確認。L3が35%を超過している場合、復活はブロックされる。

---

## 関連ドキュメント

- [SETUP.md](SETUP.md) - 初期セットアップ手順
- [@memory.md](@memory.md) - システム仕様書
