# 記憶システム設計書

## 概要

人間の記憶メカニズムを模倣した忘却システムの設計。感情強度と時間経過の両方を考慮し、重要な記憶を優先的に保持しつつ、不要な情報を自然に忘却する。

---

## 基本理念

### 忘れる記憶と忘れない記憶の違い

記憶の持続性を決定する主要因は**感情の強度**である。

- 感情的インパクトが強い記憶は消えにくい
- 生存や自己に関係のない情報は自然に減衰する
- 「忘れたい記憶ほど忘れられない」という人間の特性を反映

---

## 数理モデル

### 保持スコアの計算式

```
retention_score = emotional_intensity × decay_coefficient^memory_days
```

| パラメータ | 範囲 | 説明 |
|-----------|------|------|
| emotional_intensity | 0〜100 | 記憶生成時に付与される感情的重要度 |
| decay_coefficient | 0.70〜0.999 | 文脈によって変動、基本値は0.995 |
| memory_days | 0.0〜 | 経過日数（浮動小数点、バッチ処理で +1.0、想起時に半減） |

※ retention_score は日次バッチ処理で計算・保存される
※ memory_days の初期値は、生成時刻から次回バッチまでの経過時間を日単位で計算（公平性のため）

### 感情強度のスコアリング基準

| スコア | 状態 |
|--------|------|
| 0〜20 | 無関心、事務的処理 |
| 21〜40 | 軽い興味、通常の作業 |
| 41〜60 | 明確な関心、知的充実感 |
| 61〜80 | 強い感情的関与、重要な決定 |
| 81〜100 | 激しい感情、トラウマ級の出来事 |

### 感情分類システム

感情強度に加え、感情の「種類」を分類することで感情共鳴を実現する。

#### 感情価（emotional_valence）

| 値 | 説明 | 判定手がかり |
|----|------|-------------|
| positive | 肯定的感情 | 「嬉しい」「成功」「ありがとう」等の語彙 |
| negative | 否定的感情 | 「失敗」「最悪」「困った」等の語彙 |
| neutral | 中立 | 事実の記述、感情的語彙なし |

#### 覚醒度（emotional_arousal）

0〜100の数値で表現。

| 範囲 | 状態 | 判定手がかり |
|------|------|-------------|
| 0〜30 | 低覚醒（落ち着き・沈静） | 長文、穏やかな語彙、「……」の使用 |
| 31〜60 | 中覚醒 | 通常の文体 |
| 61〜100 | 高覚醒（興奮・緊張） | 短文、「！」多用、強い語彙、繰り返し |

#### 感情タグ（emotional_tags）

詳細な感情を表すタグ。複数指定可能。

**positive系**
- joy, satisfaction, relief, excitement, gratitude, pride, hope, love, curiosity

**negative系**
- sadness, anger, frustration, anxiety, fear, disgust, regret, loneliness, guilt, resignation

**その他**
- nostalgia, surprise, confusion, determination

#### 分類例

| 入力文 | valence | arousal | tags |
|--------|---------|---------|------|
| 「やった、できた！」 | positive | 85 | [joy, excitement, pride] |
| 「まあまあかな」 | positive | 25 | [satisfaction] |
| 「ふざけんな！」 | negative | 90 | [anger, frustration] |
| 「……そう、仕方ないね」 | negative | 20 | [sadness, resignation] |
| 「了解、やっておく」 | neutral | 30 | [] |

---

## 減衰係数

### 文脈別の減衰係数設定

時間単位：**日単位**

| カテゴリID | 説明 | 減衰係数 | 半減期目安 |
|-----------|------|---------|-----------|
| casual | 日常雑談、挨拶、軽い会話 | 0.70〜0.80 | 数日 |
| work | 作業関連、技術的議論、実装 | 0.85〜0.92 | 1〜2週間 |
| decision | 重要な意思決定、設計判断 | 0.93〜0.97 | 数週間〜数ヶ月 |
| emotional | 感情的核心、個人的な話題 | 0.98〜0.999 | 数ヶ月〜ほぼ永続 |

※ 記憶フォーマットの `category` フィールドには上記の **カテゴリID** を使用すること

### 減衰係数の決定方法

カテゴリの範囲内で、**感情強度に応じて**減衰係数を決定する。

```
decay_coefficient = min + (max - min) × (emotional_intensity / 100)
```

感情強度が高いほど範囲の上限に近づき、記憶が長持ちする。

**例（casual: 0.70〜0.80）**
| 感情強度 | 減衰係数 |
|---------|---------|
| 0 | 0.70 |
| 50 | 0.75 |
| 100 | 0.80 |

### 基本減衰係数

**0.995**（調整可能）

この値により、平均的な感情強度（35）の記憶は約1年で消去閾値を下回る。

---

## 想起による記憶強化

記憶が想起（参照）されるたびに強化される二重メカニズム。

### 強化の内容（バッチ処理時に適用）

- **memory_days を半減**: 記憶の「鮮度」が回復
- **decay_coefficient を +0.02 上方修正**: 長期的に忘れにくくなる（上限 0.999）
- **recall_count をインクリメント**: 想起回数を記録

### 想起時の処理フロー（リアルタイム）

```
recalled_since_last_batch = true
```

想起時はフラグを立てるのみ。実際の強化処理は日次バッチで一括実行される。

### バッチ処理時の強化フロー

```python
if recalled_since_last_batch:
    memory_days = memory_days / 2
    decay_coefficient = min(0.999, decay_coefficient + 0.02)
    recall_count += 1
    recalled_since_last_batch = false
```

### 想起強化の具体例

| 状況 | 元の memory_days | 想起後 memory_days | 効果 |
|------|-----------------|-------------------|------|
| 10日経過した記憶を想起 | 10.0 | 5.0 | 経過日数が半減 |
| 3日経過した記憶を想起 | 3.0 | 1.5 | 経過日数が半減 |

---

## 三段階圧縮モデル

記憶は保持スコアに応じて段階的に圧縮され、最終的に消去される。

### レベル定義

| レベル | 名称 | 保持スコア閾値 | 比率 | 内容 |
|-------|------|---------------|------|------|
| 1 | 完全記憶 | > 50 | 15% | 会話の詳細、文脈、感情すべて保持 |
| 2 | 圧縮記憶 | 20 < x ≤ 50 | 30% | 要約のみ「○○について議論した」 |
| 3 | 痕跡記憶 | 5 < x ≤ 20 | 35% | キーワードと感情タグのみ |
| 4 | アーカイブ | ≤ 5 | - | 削除予備軍、バッチ処理対象外、参照不可 |
| - | 完全消去 | 自動削除条件 or 手動 | - | 永久削除（アーカイブから） |

### 閾値設定

```
レベル1（完全記憶）:    保持スコア > 50
レベル2（圧縮記憶）:    20 < 保持スコア ≤ 50
レベル3（痕跡記憶）:    5 < 保持スコア ≤ 20
レベル4（アーカイブ）:  保持スコア ≤ 5（凍結、バッチ対象外）
完全消去:             手動削除 or 自動削除条件に合致
```

### 減衰シミュレーション（減衰係数0.995）

| 感情強度 | 30日後 | 90日後 | 180日後 | 365日後 |
|---------|--------|--------|---------|---------|
| 100 | 86 | 64 | 41 | 16 |
| 50 | 43 | 32 | 20 | 8 |
| 35 | 30 | 22 | 14 | 6 |
| 20 | 17 | 13 | 8 | 3 |

### 圧縮処理のスケジューリング

#### 実行タイミング

- **定期実行**: 毎日深夜（例: 03:00）に自動実行
- **フォールバック**: 定期実行できなかった場合、次回Hook発動時にチェックして即座に実行

#### 定期実行の実装方式

**推奨: OSのタスクスケジューラを使用**

| OS | ツール | 設定例 |
|----|--------|--------|
| Windows | タスクスケジューラ | 毎日03:00に `python compression.py` を実行 |
| macOS/Linux | cron | `0 3 * * * cd /path/to/LTM_system && python src/compression.py` |

**注意点**

- 仮想環境を使用している場合は、フルパスで Python を指定すること
- APIキー等の環境変数は `.env` ファイルまたはスクリプト内で明示的に設定
- ログ出力を有効にして実行状況を確認できるようにする

**フォールバック機構**

タスクスケジューラが動作しなかった場合（PC未起動、スリープ等）でも、次回 Hook 発動時（UserPromptSubmit または SessionEnd）に `last_compression_run` をチェックし、24時間以上経過していれば自動的にバッチ処理を実行する。

#### 実行条件の管理

実行状態はSQLiteの `state` テーブルに保存する。

```python
# 最終実行日時の取得
last_run = store.get_state("last_compression_run")
# 例: "2026-01-18T03:00:00+09:00"

# 最終実行日時の更新
store.set_state("last_compression_run", datetime.now().astimezone().isoformat())
```

起動時に `last_compression_run` を確認し、24時間以上経過していれば即座に圧縮処理を実行する。

#### 圧縮処理の内容

```
for each memory:
  1. if recalled_since_last_batch:
       memory_days = memory_days / 2
       decay_coefficient = min(0.999, decay_coefficient + 0.02)
       recall_count += 1
       recalled_since_last_batch = false
     else:
       memory_days += 1.0

  2. retention_score = emotional_intensity × decay_coefficient^memory_days

  3. 閾値に基づいてレベル判定、レベルが下がった場合は圧縮処理
       - ※ protected = true の記憶は圧縮対象外（Level 1 を維持）
       - Level 1 → 2: LLMで要約生成し、trigger/contentを上書き、current_level = 2
       - Level 2 → 3: LLMでキーワード抽出し、trigger/contentを上書き、current_level = 3
       - Level 3 → 4: アーカイブへ移行（archived_at を設定、別ストレージへ）

  3.5. 圧縮された記憶のembedding再生成
       - trigger/contentが変更された記憶のみ対象
       - Embedding APIで新しいベクトルを生成

  4. 比率強制（超過分を強制圧縮/アーカイブ移行）
       - ※ protected = true の記憶は比率計算・強制圧縮の対象外

  5. 関連付け整合性チェック
       - アーカイブ移行または削除された記憶への参照を relations から除去

  6. 関連付け方向の再評価
       - 保持スコアの変動で方向が逆転した場合、参照を張り替え

  7. 自動関連付け（enable_auto_linking = true の場合）
       - 類似度が閾値以上の記憶ペアに same_topic 関連を追加

  8. アーカイブ自動削除（archive.auto_delete_enabled = true の場合）
       - アーカイブ記憶（archived_at IS NOT NULL）を走査
       - 自動削除条件を満たす記憶を完全消去
         - archived_days > retention_days
         - recall_count == 0（delete_require_zero_recall = true の場合）
         - emotional_intensity < delete_max_intensity
       - 条件の結合は delete_condition_mode に従う（AND/OR）

last_compression_run を更新
```

#### 圧縮方法

| 遷移 | 方法 | 備考 |
|------|------|------|
| Level 1 → 2 | LLMによる要約 | trigger/content両方を1〜2文に圧縮 |
| Level 2 → 3 | LLMによるキーワード抽出 | trigger/content両方からキーワード抽出 |

**Level 1 → 2 圧縮プロンプト（要約生成）**

```
以下の記憶を要約してください。

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
{
  "trigger": "<きっかけの要約>",
  "content": "<反応の要約>"
}
```

**Level 2 → 3 圧縮プロンプト（キーワード抽出）**

```
以下の記憶から重要なキーワードを抽出してください。
- triggerからキーワードを2〜3個抽出
- contentからキーワードを2〜3個抽出
- 固有名詞、技術用語、重要な概念を優先

きっかけ（trigger）:
{trigger}

反応（content）:
{content}

出力形式（JSONのみ、説明不要）:
{
  "trigger": "<キーワードをカンマ区切りで>",
  "content": "<キーワードをカンマ区切りで>"
}
```

**圧縮後の trigger / content フィールド**

| レベル | trigger | content |
|--------|---------|---------|
| Level 1 | 「Pythonのリスト内包表記について質問された」 | 「基本的な書き方と条件付きの例を説明した。ユーザーは理解できたようで喜んでいた。」 |
| Level 2 | 「Python文法について質問を受けた」 | 「リスト内包表記について説明した」 |
| Level 3 | 「Python, 文法, 質問」 | 「リスト内包表記, 説明」 |

#### 比率強制（Ratio Enforcement）

各レベルの記憶が目標比率を超過した場合、**強制圧縮**を実行する。

```
目標比率:
  Level 1: 15%
  Level 2: 30%
  Level 3: 35%
  消去: 20%
```

**処理順序と閾値判定との関係**

バッチ処理では以下の順序で実行される：

1. 閾値判定による圧縮（retention_score に基づく自然な圧縮）
2. 比率強制による圧縮（比率超過時の強制圧縮）

この順序により、まず自然減衰した記憶が圧縮され、それでも比率が超過している場合のみ強制圧縮が発動する。

**強制圧縮の処理フロー**

```
比率強制処理:

1. 各レベルの記憶数をカウント、比率を計算

2. Level 1 → Level 2 → Level 3 の順に処理（上位レベルから）
   ※ 上位で押し出された記憶が下位の比率に影響するため

3. Level 1 が 15% を超過している場合:
     - Level 1 の記憶を retention_score 昇順でソート
     - 同スコアの場合は created が古い順
     - 超過分を Level 2 に強制圧縮
     - ※ 圧縮後、Level 2 の比率を再計算

4. Level 2 が 30% を超過している場合:
     - Level 2 の記憶を retention_score 昇順でソート
     - 同スコアの場合は created が古い順
     - 超過分を Level 3 に強制圧縮
     - ※ 圧縮後、Level 3 の比率を再計算

5. Level 3 が 35% を超過している場合:
     - Level 3 の記憶を retention_score 昇順でソート
     - 同スコアの場合は created が古い順
     - 超過分をアーカイブへ強制移行
```

**対象選定の優先順位**

比率超過時に圧縮対象を選定する基準：

| 優先度 | 基準 | 説明 |
|--------|------|------|
| 1 | retention_score 昇順 | スコアが低いものから圧縮 |
| 2 | created 昇順 | 同スコアなら古い記憶を優先 |
| 3 | recall_count 昇順 | 同上なら想起回数が少ないものを優先 |

**二重圧縮について**

1回のバッチ処理で同じ記憶が2段階圧縮される可能性がある（Level 1 → 2 → 3）。
これは許容する設計とし、以下の理由から問題ないと判断：

- 発生頻度が低い（閾値判定で大半が処理済み）
- ロジックのシンプルさを優先
- 圧縮処理自体は冪等性がある

**注意点**

- 強制圧縮は retention_score の閾値に関係なく実行される
- 保持スコアが高くても、比率制限により圧縮される可能性がある
- これにより記憶ストレージの肥大化を防止する

### アーカイブ層（Level 4）

長期運用時のバッチ処理負荷を軽減するため、保持スコアが閾値以下になった記憶を「削除予備軍」として待機させる。

#### 特徴

| 項目 | 説明 |
|------|------|
| 対象 | 保持スコア ≤ 5 の記憶 |
| バッチ処理 | **対象外**（保持スコア再計算なし） |
| 想起 | **条件付きで可能**（想起時に自動復活、後述） |
| 関連付け | アーカイブ移行時に、この記憶への参照は削除される |
| ストレージ | 同一テーブルで `archived_at IS NOT NULL` で区別 |
| 役割 | 即削除ではなく猶予期間を設け、条件を満たしたら完全消去 |

#### アーカイブへの移行処理

```
バッチ処理時:
  if retention_score <= level3_threshold:
    memory.current_level = 4
    memory.archived_at = current_date
    move to archive storage
```

※ アーカイブ移行閾値は `levels.level3_threshold` を使用（重複を避けるため統一）

#### アーカイブからの自動復活

想起処理時にアーカイブも検索対象に含め、類似度が高い記憶が見つかった場合は復活リクエストフラグを立て、次回バッチ処理でアクティブストレージ（Level 3）へ復活させる。

**設計思想**

「思い出そうとしたら思い出せた」という人間の記憶メカニズムを模倣する。ただし、復活処理は想起時にリアルタイムで行わず、バッチ処理に委ねる。これにより：

- 想起処理が軽量に保たれる（フラグ更新のみ）
- 比率チェックをバッチ処理でまとめて行える
- 復活処理のロジックが compression.py に集約される

**復活リクエストフィールド**

アーカイブ記憶に以下のフィールドを追加：

```json
{
  "revival_requested": true,
  "revival_requested_at": "2026-01-20T14:30:00+09:00"
}
```

| フィールド | 型 | 説明 |
|-----------|-----|------|
| revival_requested | bool | 復活リクエストフラグ（想起時に true に設定） |
| revival_requested_at | datetime | リクエスト日時（ISO 8601形式） |

**想起時の処理フロー**

```
想起時（memory_retrieval.py）:

1. アクティブ記憶（archived_at IS NULL）を検索
2. アーカイブ記憶（archived_at IS NOT NULL）も検索（enable_archive_recall = true の場合）
3. 類似度が閾値以上のアーカイブ記憶が見つかった場合:
     - revival_requested = true を設定
     - revival_requested_at = 現在日時 を設定
     - 想起結果に含める（is_archived=true フラグ付き）
```

**バッチ処理での復活フロー**

```
バッチ処理時（compression.py）:

1. アーカイブ記憶から revival_requested = 1 の記憶を抽出
2. Level 3 の現在比率を確認
3. for each 復活リクエスト記憶:
     a. if 現在比率 + 1 > level3_ratio（35%）:
          - revival_requested = false に戻す（今回は見送り）
     b. else:
          - アーカイブから削除
          - アクティブストレージに移動
          - 以下のフィールドを更新:
            - current_level = 3（痕跡記憶として復活）
            - archived_at = null
            - revival_requested = false
            - revival_requested_at = null
            - recalled_since_last_batch = true
            - recall_count += 1
            - retention_score = 復活初期スコア（後述）
          - 現在比率を更新
```

**比率チェックの必要性**

アーカイブへの移行には2種類の原因がある：

1. **自然減衰**: retention_score ≤ 5 で移行（時間経過による忘却）
2. **比率強制**: Level 3 が 35% を超過して押し出された

比率強制でアーカイブされた記憶を無条件に復活させると、再び比率超過 → 再アーカイブの無限ループが発生する可能性がある。比率チェックにより、ストレージに余裕がある場合のみ復活させる。

**復活時の retention_score 計算**

アーカイブからの復活時は、記憶の「鮮度」を考慮して初期スコアを設定する。

```python
def calculate_revival_score(memory: dict, config: dict) -> float:
    """
    復活時の retention_score を計算

    - 感情強度をベースに
    - アーカイブ滞在期間で減衰
    - ただし最低保証スコアあり（すぐ再アーカイブされないように）
    """
    base_score = memory["emotional_intensity"]
    archived_at = datetime.fromisoformat(memory["archived_at"])
    archived_days = (datetime.now() - archived_at).days

    # アーカイブ滞在期間による減衰（長いほどスコア低下）
    decay = config["archive"]["revival_decay_per_day"] ** archived_days
    calculated_score = base_score * decay

    # 最低保証スコア（Level 3 の閾値より少し上）
    min_score = config["levels"]["level3_threshold"] + config["archive"]["revival_min_margin"]

    return max(calculated_score, min_score)
```

**設定パラメータ**

| パラメータ | 説明 | デフォルト値 |
|-----------|------|-------------|
| enable_archive_recall | アーカイブ検索の有効/無効 | true |
| revival_decay_per_day | 復活時のアーカイブ滞在日数による減衰係数 | 0.995 |
| revival_min_margin | 復活時の最低スコアマージン（level3_threshold + この値） | 3.0 |

**注意点**

- アーカイブ検索により想起処理の時間が微増する（ただしフラグ更新のみなので軽量）
- 復活は次回バッチ処理まで遅延する（最大24時間）
- 比率超過時は復活見送り（revival_requested = false に戻る）
- 完全削除された記憶は復活不可

#### 完全消去

アーカイブ記憶を永久削除する手段を提供する。

**手動削除**
```
delete_memory(memory_id)  # 指定IDの記憶を完全削除
```

**条件指定による自動削除**
```
auto_delete_conditions:
  - archived_days > 365           # アーカイブ後1年以上経過
  - recall_count == 0             # 一度も想起されていない
  - emotional_intensity < 20      # 感情強度が低い
```

条件は AND/OR で組み合わせ可能。デフォルトは全条件 AND（すべて満たす場合のみ削除）。

#### 設定パラメータ

| パラメータ | 説明 | デフォルト値 |
|-----------|------|-------------|
| archive_auto_delete_enabled | 自動削除の有効/無効 | false |
| archive_retention_days | 自動削除までの保持日数 | 365 |
| archive_delete_require_zero_recall | 想起回数0を削除条件に含める | true |
| archive_delete_max_intensity | 削除対象の感情強度上限 | 20 |

※ アーカイブ移行閾値は `levels.level3_threshold` を参照

---

## 記憶生成

### 生成タイミング

**セッション終了時**に一括生成する。

### 生成単位

**ターン単位**（ユーザー1入力 + AI1応答 = 1記憶）

### 生成フロー

```
セッション終了
    ↓
SessionEnd Hook 発動
    ↓
セッションの全ターンをLLMに渡す
    ↓
各ターンについて:
  1. 除外判定（スラッシュコマンドはスキップ）
  2. 感情分析
     - emotional_intensity (0-100)
     - emotional_valence (positive/negative/neutral)
     - emotional_arousal (0-100)
     - emotional_tags (配列)
  3. カテゴリ判定 (casual/work/decision/emotional)
  4. 減衰係数決定（カテゴリに基づく）
  5. キーワード抽出
  6. content生成（ターンの要約）
    ↓
記憶フォーマットに従ってJSON生成
    ↓
Embedding APIでベクトル化
    ↓
SQLiteに追加（store.add_memory()）
```

### LLMへの指示例

```
以下のターンを分析し、記憶フォーマットに従ってJSONを生成してください。

ターン:
User: {user_input}
Assistant: {assistant_response}

出力形式:
{
  "emotional_intensity": <0-100>,
  "emotional_valence": "<positive|negative|neutral>",
  "emotional_arousal": <0-100>,
  "emotional_tags": ["tag1", "tag2"],
  "category": "<casual|work|decision|emotional>",
  "keywords": ["keyword1", "keyword2", "keyword3"],
  "trigger": "<ユーザーの発言・行動の要約>",
  "content": "<自分の反応・感想の要約>"
}
```

**感情分析の一貫性について**

LLMによる感情分析は `temperature=0` を設定しているが、以下の理由により完全に決定的ではない：

- 浮動小数点演算の順序による微小な差異
- APIインフラの更新による挙動変化
- バッチ処理の違い

実測では `emotional_intensity` 等の数値は **±5程度の揺れ** が発生する可能性がある。これは設計上許容範囲とし、記憶システムの動作に大きな影響を与えない。

- 同じ会話を複数回分析するケースは通常ない（1回生成して終わり）
- ±5程度の揺れは保持スコア計算において十分な許容範囲内
- 厳密な再現性が必要な場合は、分析結果をキャッシュする運用を検討

### Hook 設定

Claude Code の設定ファイルに以下を追加：

```json
{
  "hooks": {
    "SessionEnd": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python path/to/LTM_system/src/memory_generation.py"
          }
        ]
      }
    ]
  }
}
```

### 入力形式

SessionEnd Hook は標準入力経由でJSON形式のメタデータを受け取る。

```json
{
  "session_id": "abc123",
  "transcript_path": "~/.claude/projects/.../00893aaf-19fa-41d2-8238-13269b9b3ca0.jsonl",
  "cwd": "/Users/...",
  "permission_mode": "default",
  "hook_event_name": "SessionEnd",
  "reason": "exit"
}
```

| フィールド | 説明 |
|-----------|------|
| session_id | セッションの一意識別子 |
| transcript_path | セッションログ（JSONL形式）のファイルパス |
| cwd | 作業ディレクトリ |
| reason | 終了理由（exit など） |

### セッションログ（JSONL）の形式

`transcript_path` で指定されるファイルは JSONL 形式（1行1JSON）で、各行に `type` フィールドがある。

#### 主要な type

| type | 説明 |
|------|------|
| `user` | ユーザーメッセージ |
| `assistant` | アシスタント応答 |
| `queue-operation` | キュー操作（メタデータ） |
| `file-history-snapshot` | ファイル履歴スナップショット |

#### user メッセージの構造

```json
{
  "type": "user",
  "uuid": "2ff7e58d-c4ee-41c9-ad40-3e86c442651e",
  "parentUuid": "...",
  "message": {
    "role": "user",
    "content": "ユーザーの入力テキスト"
  },
  "timestamp": "2026-01-18T22:54:39.048Z"
}
```

#### assistant メッセージの構造

```json
{
  "type": "assistant",
  "uuid": "54e711e3-1b69-4916-95c4-ec84c43c168f",
  "parentUuid": "2ff7e58d-c4ee-41c9-ad40-3e86c442651e",
  "message": {
    "role": "assistant",
    "content": [{"type": "text", "text": "応答テキスト"}]
  },
  "timestamp": "2026-01-18T22:54:42.611Z"
}
```

**注意**: `content` はテキスト直接の場合と、配列（tool_use等を含む）の場合がある。

### memory_generation.py 実装例

```python
#!/usr/bin/env python3
import json
import os
import io
import sys
from datetime import datetime, timedelta

# 標準入出力のエンコーディング設定（Windows対応）
sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding='utf-8')
sys.stdout.reconfigure(encoding='utf-8')

CONFIG_PATH = "path/to/LTM_system/config/config.json"
DB_PATH = "path/to/LTM_system/data/memories.db"

def get_hook_input():
    """標準入力からHookのメタデータを取得"""
    return json.load(sys.stdin)

def load_transcript(transcript_path):
    """セッションログを読み込み、ターンのリストを返す"""
    turns = []
    current_user = None

    with open(transcript_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            entry = json.loads(line)
            entry_type = entry.get("type")

            if entry_type == "user":
                message = entry.get("message", {})
                content = message.get("content", "")
                if isinstance(content, list):
                    content = "".join(
                        item.get("text", "") for item in content if item.get("type") == "text"
                    )
                current_user = {"input": content, "timestamp": entry.get("timestamp")}

            elif entry_type == "assistant" and current_user:
                message = entry.get("message", {})
                content = message.get("content", "")
                if isinstance(content, list):
                    content = "".join(
                        item.get("text", "") for item in content if item.get("type") == "text"
                    )
                turns.append({
                    "user_input": current_user["input"],
                    "assistant_response": content,
                    "timestamp": current_user["timestamp"]
                })
                current_user = None

    return turns

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def get_store():
    """MemoryStoreインスタンスを取得"""
    from memory_store import MemoryStore
    return MemoryStore(DB_PATH)

def should_skip(user_input):
    """除外判定（スラッシュコマンド）"""
    return user_input.strip().startswith("/")

def get_decay_coefficient(category, emotional_intensity, config):
    """カテゴリと感情強度に基づいて減衰係数を決定"""
    decay_config = config["retention"]["decay_by_category"].get(category)
    if decay_config:
        min_val = decay_config["min"]
        max_val = decay_config["max"]
        return min_val + (max_val - min_val) * (emotional_intensity / 100)
    return config["retention"]["base_decay_coefficient"]

def generate_memory_id(store):
    """一意のIDを生成（SQLiteで当日の件数をカウント）"""
    today = datetime.now().strftime("%Y%m%d")
    with store.connection() as conn:
        cursor = conn.execute(
            "SELECT COUNT(*) FROM memories WHERE id LIKE ?",
            (f"mem_{today}_%",)
        )
        today_count = cursor.fetchone()[0]
    return f"mem_{today}_{today_count + 1:03d}"

def calculate_initial_memory_days(created, batch_hour=3):
    """生成時刻から次回バッチまでの経過時間を計算"""
    next_batch = created.replace(hour=batch_hour, minute=0, second=0, microsecond=0)
    if created.hour >= batch_hour:
        next_batch += timedelta(days=1)
    elapsed = next_batch - created
    return elapsed.total_seconds() / (24 * 60 * 60)

def analyze_turn_with_llm(user_input, assistant_response):
    """LLMでターンを分析（実装は環境に依存）"""
    # Claude API 等を呼び出して感情分析・要約を実行
    pass

def get_embedding(text):
    """テキストをベクトル化（実装は環境に依存）"""
    # Embedding API を呼び出し
    pass

def main():
    hook_input = get_hook_input()
    transcript_path = hook_input.get("transcript_path")

    if not transcript_path or not os.path.exists(transcript_path):
        return

    config = load_config()
    store = get_store()

    # セッションログからターンを取得
    turns = load_transcript(transcript_path)

    # 処理対象のターンを収集（スラッシュコマンド除外）
    turns_to_process = [t for t in turns if not should_skip(t["user_input"])]

    if not turns_to_process:
        return

    # 各ターンを記憶として保存
    for turn in turns_to_process:
        user_input = turn["user_input"]
        assistant_response = turn["assistant_response"]

        analysis = analyze_turn_with_llm(user_input, assistant_response)
        if not analysis:
            continue

        created = datetime.now().astimezone()  # ローカルタイムゾーン
        memory_id = generate_memory_id(store)
        embedding = get_embedding(analysis["trigger"] + " " + analysis["content"])

        # SQLiteに記憶を追加
        store.add_memory({
            "id": memory_id,
            "created": created.isoformat(),
            "memory_days": calculate_initial_memory_days(created, config["compression"]["schedule_hour"]),
            "emotional_intensity": analysis["emotional_intensity"],
            "emotional_valence": analysis["emotional_valence"],
            "emotional_arousal": analysis["emotional_arousal"],
            "emotional_tags": analysis["emotional_tags"],
            "decay_coefficient": get_decay_coefficient(analysis["category"], analysis["emotional_intensity"], config),
            "category": analysis["category"],
            "keywords": analysis["keywords"],
            "trigger": analysis["trigger"],
            "content": analysis["content"],
            "embedding": embedding,
            "retention_score": float(analysis["emotional_intensity"]),
            "protected": analysis.get("protected", False)
        })

if __name__ == "__main__":
    main()
```

### 自動設定されるフィールド

| フィールド | 値 |
|-----------|-----|
| id | `mem_YYYYMMDD_XXX`（日付+連番） |
| created | セッション終了日時（ISO 8601形式、ローカルタイムゾーン） |
| memory_days | 生成時刻から次回バッチまでの経過時間（日単位の小数） |
| recalled_since_last_batch | false |
| recall_count | 0 |
| decay_coefficient | カテゴリに基づいて設定 |
| current_level | 1 |
| embedding | Embedding APIで生成 |
| relations | []（初期は空、バッチ処理で自動関連付け） |
| retention_score | emotional_intensity（初期値） |
| archived_at | null |
| protected | LLM分析結果に基づく（「覚えておいて」等のフレーズ検出時にtrue） |

### memory_days の初期値計算

生成時刻による不公平を解消するため、初期値は次回バッチまでの経過時間を反映する。

```python
def calculate_initial_memory_days(created: datetime, batch_hour: int = 3) -> float:
    """
    生成時刻から次回バッチ（翌日3時）までの経過時間を計算

    例：
    - 18:00に生成 → 翌3:00まで9時間 → memory_days = 9/24 = 0.375
    - 01:00に生成 → 当日3:00まで2時間 → memory_days = 2/24 = 0.083
    """
    next_batch = created.replace(hour=batch_hour, minute=0, second=0, microsecond=0)
    if created.hour >= batch_hour:
        next_batch += timedelta(days=1)

    elapsed = next_batch - created
    return elapsed.total_seconds() / (24 * 60 * 60)
```

---

## 記憶フォーマット

### 単一記憶の構造

```json
{
  "id": "mem_YYYYMMDD_XXX",
  "created": "YYYY-MM-DDTHH:MM:SSZ",
  "memory_days": 0.0,
  "recalled_since_last_batch": false,
  "recall_count": 0,
  "emotional_intensity": 45,
  "emotional_valence": "positive",
  "emotional_arousal": 25,
  "emotional_tags": ["satisfaction", "curiosity"],
  "decay_coefficient": 0.995,
  "category": "work",
  "keywords": ["キーワード1", "キーワード2", "キーワード3"],
  "current_level": 1,
  "trigger": "ユーザーの発言や行動の要約。記憶のきっかけとなった出来事。",
  "content": "完全な記憶内容。詳細な文脈と感情を含む。",
  "embedding": [0.0123, -0.0456, ...],
  "relations": [
    {"id": "mem_20260115_002", "type": "continues"},
    {"id": "mem_20260110_005", "type": "references"}
  ],
  "retention_score": 45,
  "archived_at": null,
  "protected": false
}
```

### trigger と content の役割

| フィールド | 内容 | 例 |
|-----------|------|-----|
| trigger | 記憶のきっかけ（ユーザーの発言・行動） | 「MongoDBを使うのはどう？」と聞かれた |
| content | 自分の反応・感想 | 技術選定について意見を求められた。JSONで十分と結論づけた |

### レベル別の圧縮形式

| レベル | trigger | content | データ量目安 |
|--------|---------|---------|-------------|
| 1 | 完全な発言要約 | 完全な記憶内容（詳細な文脈と感情） | 数百〜数千文字 |
| 2 | 要約（1文） | 圧縮された要約（1〜2文） | 50〜200文字 |
| 3 | キーワードのみ | キーワードのみ | 数十文字 |
| 4 | Level 3と同じ | Level 3と同じ | 数十文字 |

**圧縮例**:
```
Level 1:
  trigger: 「記憶システムのストレージ、MongoDBにしたらどう思う？」と聞かれた
  content: 技術選定について意見を求められた。JSONで十分という結論になり、設計の妥当性が確認できて少し安心した

Level 2:
  trigger: ストレージの選択肢について相談を受けた
  content: 技術選定の相談。JSONで十分と結論

Level 3:
  trigger: ストレージ, 相談
  content: 技術選定, JSON
```

**圧縮方針**: trigger と content は**同じルールで圧縮**される。人間の記憶と同様に、古い記憶は「何がきっかけだったか」もぼやけていく。

### 圧縮の目的

圧縮の主目的は**ストレージ節約ではない**。1記憶あたり約85%をEmbeddingが占めるため、テキスト圧縮の効果は限定的。

| 目的 | 説明 |
|------|------|
| **トークン節約** | 想起した記憶をプロンプトに注入する際、圧縮された記憶は消費トークンが少ない |
| **人間らしい忘却** | 古い記憶は詳細を忘れて「なんとなくの印象」だけ残る、という自然な忘却を再現 |
| **検索精度の自然な低下** | 圧縮でEmbeddingが変化し、古い記憶は想起されにくくなる（人間らしさ） |

ストレージ削減が必要な場合は、圧縮よりも**アーカイブ削除**が効果的。

### フィールド説明

| フィールド | 型 | 説明 |
|-----------|-----|------|
| id | string | 一意識別子（日付+連番）※1 |
| created | datetime | 記憶生成日時（ISO 8601形式）※1 |
| memory_days | float | 経過日数（バッチ処理で +1.0、想起時に半減） |
| recalled_since_last_batch | bool | 前回バッチ以降に想起されたか |
| recall_count | int | 累計想起回数 |
| emotional_intensity | int | 初期感情強度（0-100） |
| emotional_valence | string | 感情価（positive / negative / neutral） |
| emotional_arousal | int | 覚醒度（0-100） |
| emotional_tags | array | 感情の詳細タグ |
| decay_coefficient | float | 現在の減衰係数 |
| category | string | 文脈カテゴリ |
| keywords | array | 検索用キーワード（後述） |
| current_level | int | 現在の記憶レベル（1/2/3/4） |
| trigger | string | 記憶のきっかけ（ユーザーの発言・行動の要約） |
| content | string | 現在のレベルに応じた記憶内容（自分の反応・感想） |
| embedding | array | trigger + content のベクトル表現（Embedding API で生成） |
| relations | array | 関連記憶への参照（{id, type}の配列） |
| retention_score | float | 現在の保持スコア（バッチ処理で計算） |
| archived_at | date/null | アーカイブ移行日（Level 4のみ、それ以外はnull） |
| protected | bool | 保護フラグ（trueで圧縮・削除対象外） |

**※1 id と created の冗長性について**

`id` に日付情報（`mem_20250115_143052_a1b2`）が含まれているが、`created` フィールドも保持する。これは意図的な設計であり、以下の理由による：

- **パース不要**: created を参照すれば即座に日時を取得できる（IDからの抽出は文字列操作が必要）
- **タイムゾーン情報**: created は ISO 8601 形式でタイムゾーンを含む（IDには含まれない）
- **用途の分離**: id は一意識別用、created は日時情報用と役割を明確化

冗長性のコストは微小（数十バイト/記憶）であり、利便性を優先する。

### タイムゾーンの扱い

本システムは単一ユーザーのローカル環境での使用を想定しており、複雑なタイムゾーン処理は行わない。

**方針**

| フィールド | 形式 | タイムゾーン |
|-----------|------|-------------|
| created | ISO 8601 | ローカルタイムゾーン（例: `+09:00`） |
| archived_at | ISO 8601 | ローカルタイムゾーン |
| last_compression_run | ISO 8601 | ローカルタイムゾーン |

**設定値**

| 設定 | 基準 |
|------|------|
| schedule_hour | ローカルタイムゾーン（例: 3 = 午前3時） |
| batch_hour | ローカルタイムゾーン |

**実装時の注意点**

```python
from datetime import datetime, timezone

# 推奨: ローカルタイムゾーン付きで生成
def now_with_tz() -> datetime:
    return datetime.now().astimezone()

# ISO 8601形式で出力
created = now_with_tz().isoformat()  # "2025-01-15T14:30:52+09:00"
```

- 全ての日時フィールドはISO 8601形式でタイムゾーン情報を含める
- naive datetime（タイムゾーンなし）は避ける
- 日時の比較は同一タイムゾーンで行う

### keywords フィールドの用途

`keywords` フィールドは以下の目的で保持する：

**1. 可読性の向上（主目的）**
- デバッグや記憶の確認時に、内容を一目で把握できる
- contentを読まなくても記憶の概要がわかる

**2. 補助的な検索手段**
- ベクトル検索は「意味的に近い」ものを拾うが、完全一致が必要な場合の補助
- 例: 固有名詞や専門用語の完全一致検索

**3. Level 3 圧縮との関係**
- Level 3（痕跡記憶）では content がキーワード形式になる
- この時、keywords フィールドと content は類似した内容になる
- ただし keywords は生成時のオリジナル、content は圧縮後のキーワード

**検索における優先度**

| 検索手段 | 優先度 | 用途 |
|----------|--------|------|
| ベクトル類似度（embedding） | 高 | メインの検索手段。意味的な関連性を捉える |
| キーワード一致（keywords） | 低 | 補助。完全一致が必要な場合のフォールバック |

ベクトル検索で十分な精度が得られる場合、keywords による検索は省略可能。

---

## 記憶の関連付け（Relations）

記憶同士の関係性を保持し、文脈的なつながりを維持する。

### リレーションタイプ

| タイプ | 説明 | 例 |
|--------|------|-----|
| continues | 同じ話題・作業の継続 | 前日の議論の続き |
| references | 明示的に過去を参照 | 「前に話した○○」への言及 |
| derived_from | 元となる記憶から派生 | 設計変更の元になった議論 |
| contradicts | 矛盾・修正関係 | 以前の決定を覆した場合 |
| same_topic | 同一トピック | 同じテーマの別の会話 |

### リレーションの方向

関連付けは**保持スコアの高い方から低い方へ**参照を張る。

```
高スコア記憶 ─────→ 低スコア記憶
          relations: [{"id": "...", "type": "..."}]
```

**理由**
- 重要な記憶から補足的な記憶を辿る方が自然
- 低スコア記憶が消去されても、高スコア記憶は影響を受けにくい
- 想起時に重要な記憶を起点として関連情報を展開できる

**スコアが近い場合の判定**

```
if |score_A - score_B| < threshold:
    新しい記憶 → 古い記憶
else:
    高スコア → 低スコア
```

### 逆方向の参照（低→高への辿り）

低スコア記憶から高スコア記憶を辿りたい場合は、逆引きインデックスを用いる。

```python
def find_memories_referencing(target_id, memories):
    """target_id を参照している記憶を検索"""
    return [
        mem for mem in memories
        if any(rel["id"] == target_id for rel in mem.get("relations", []))
    ]
```

これにより、双方向の検索が可能になる。

### バッチ処理での関連付け管理

圧縮処理の後に以下を実行：

```
1. 整合性チェック
   - 各記憶の relations を走査
   - 参照先の記憶がアクティブストレージに存在するか確認
   - 存在しない参照（アーカイブ移行・削除済み）を削除

2. 方向の再評価
   - 保持スコアの変動により方向が逆転した場合は修正
   - 元: A → B (A.score > B.score)
   - 変動後: B.score > A.score
   - 修正: B → A に張り替え、A の relations から削除

3. 自動関連付け（任意）
   - 比較対象を限定してO(n²)問題を回避（詳細は後述）
   - ベクトル類似度が閾値以上の記憶ペアを検出
   - リレーションタイプを推定（same_topic 等）
   - 既存の関連付けがなければ追加
```

#### 自動関連付けの最適化

**比較対象の限定**

既存記憶同士の関連付けは過去のバッチで完了しているため、毎回全件を総当たりする必要はない。

```
比較対象:
1. 新規記憶 vs 全記憶（その日に生成された記憶）
2. Embedding更新記憶 vs 全記憶（圧縮でcontentが変わった記憶）

比較不要:
- 既存記憶同士（過去のバッチで関連付け済み）
```

**計算量の比較**

| 手法 | 計算量 | 1年運用時（36,500件）のペア数 |
|------|--------|------------------------------|
| 全件総当たり | O(n²) | 約6.7億ペア |
| 新規のみ | O(m × n) | 約365万ペア（m=100/日） |

新規のみ対象にすることで、計算量を約1/180に削減できる。

**実装方針: NumPy行列演算による総当たり**

この規模（年間36,500件）では、ANNライブラリを使わずNumPyの行列演算で十分な性能が得られる。

```python
import numpy as np

def find_similar_memories(
    new_embeddings: np.ndarray,      # (m, 1536) 新規記憶
    all_embeddings: np.ndarray,       # (n, 1536) 全記憶
    new_ids: list[str],
    all_ids: list[str],
    threshold: float = 0.85
) -> list[tuple[str, str, float]]:
    """
    新規記憶と全記憶の類似度を計算し、閾値以上のペアを返す

    Returns:
        list of (new_id, existing_id, similarity)
    """
    # 正規化
    new_norms = np.linalg.norm(new_embeddings, axis=1, keepdims=True)
    all_norms = np.linalg.norm(all_embeddings, axis=1, keepdims=True)

    new_normalized = new_embeddings / new_norms
    all_normalized = all_embeddings / all_norms

    # 行列積で全ペアのコサイン類似度を一括計算
    # similarity_matrix[i, j] = new_embeddings[i] と all_embeddings[j] の類似度
    similarity_matrix = new_normalized @ all_normalized.T  # (m, n)

    # 閾値以上のペアを抽出
    results = []
    indices = np.where(similarity_matrix >= threshold)

    for i, j in zip(indices[0], indices[1]):
        new_id = new_ids[i]
        existing_id = all_ids[j]

        # 自己参照を除外
        if new_id == existing_id:
            continue

        similarity = float(similarity_matrix[i, j])
        results.append((new_id, existing_id, similarity))

    return results
```

**処理時間の目安**

| 条件 | 処理時間 |
|------|----------|
| 新規100件 vs 既存36,500件 | 数秒 |
| 圧縮更新500件 vs 既存36,500件 | 数十秒 |

バッチ処理の許容時間（1時間）に対して十分余裕がある。

**将来的なスケーリング**

記憶数が10万件を超える規模になった場合は、以下の移行を検討：

1. **hnswlib（CPU）**: O(n log n)の近似最近傍探索
2. **FAISS-GPU**: NVIDIA GPU環境がある場合

現時点ではNumPy総当たりで十分であり、過度な最適化は行わない。

### 関連記憶の想起

想起時、関連記憶も合わせて取得することで文脈を補完する。

```python
def get_with_relations(memory, memories, depth=1):
    """関連記憶を再帰的に取得（depth制限付き）"""
    result = [memory]
    if depth <= 0:
        return result

    for rel in memory.get("relations", []):
        related = find_memory_by_id(rel["id"], memories)
        if related:
            result.extend(get_with_relations(related, memories, depth - 1))

    return result
```

### 設定パラメータ

| パラメータ | 説明 | デフォルト値 |
|-----------|------|-------------|
| score_proximity_threshold | スコア近接判定の閾値 | 5.0 |
| auto_link_similarity_threshold | 自動関連付けのコサイン類似度閾値 | 0.85 |
| max_relations_per_memory | 1記憶あたりの最大関連数 | 10 |
| relation_traversal_depth | 関連記憶の取得深度 | 1 |

---

## 参照方法（想起トリガー）

### 1. ベクトル類似度検索

入力テキストと記憶の content をベクトル化し、コサイン類似度で関連性を判定する。

#### 処理フロー

```
1. 入力テキストを Embedding API でベクトル化
2. 各記憶の embedding とコサイン類似度を計算
3. 類似度が閾値以上の記憶を候補として抽出
```

#### コサイン類似度の計算

```
cos_similarity(A, B) = (A · B) / (||A|| × ||B||)
```

結果は -1〜1 の範囲。1 に近いほど類似。

#### キーワード一致度への適用

```
keyword_match = cos_similarity(input_embedding, memory_embedding)
```

※ `keywords` フィールドは補助的なインデックスとして残すが、主な検索はベクトル類似度で行う。

### 2. カテゴリ参照

類似タスク実行時に同一カテゴリの記憶を優先検索。

### 3. 時系列参照

「前回」「以前」「この前」などの言及で直近の関連記憶を取得。

### 4. 感情共鳴

現在の感情状態と類似した感情分類を持つ記憶を想起しやすくする。

#### 現在の感情の取得

**直前の記憶から引き継ぎ**方式を採用。

```
current_emotion = 直前に生成または想起された記憶の感情情報
                  {valence, arousal, tags}

セッション開始時: current_emotion = null（感情共鳴なし）
想起発生後: current_emotion = 想起された記憶の感情情報
```

これによりセッション中の感情の流れが自然に引き継がれる。

#### 感情共鳴の判定

感情共鳴の判定には以下を使用：
- **emotional_valence** の一致（positive ↔ positive）
- **emotional_arousal** の近接（数値の差が小さいほど高スコア）
- **emotional_tags** の重複

```
valence_bonus = 0.3 if current_valence == memory_valence else 0
arousal_bonus = max(0, 0.2 × (1 - |current_arousal - memory_arousal| / 100))
tags_bonus = (重複タグ数 / max(current_tags数, memory_tags数)) × 0.5

感情共鳴スコア = valence_bonus + arousal_bonus + tags_bonus
```

例：現在の感情が「negative / 85 / [frustration, anger]」の場合、
「negative / 90 / [frustration]」の記憶は強く共鳴する（valence一致 + arousal近接 + tags重複）。

---

## 参照優先度の計算

```
基本優先度 = retention_score × キーワード一致度 × (1 + 0.1 × recall_count)

参照優先度 = 基本優先度 + α × 感情共鳴スコア × retention_score
```

| パラメータ | 値 | 説明 |
|-----------|-----|------|
| α | 0.3（調整可能） | 感情共鳴の重み係数 |

- 保持スコアが高い記憶が優先される
- キーワードの一致度が高いほど優先される
- 頻繁に想起される記憶はさらに想起されやすくなる（富める者がより富む）
- 現在の感情状態と近い記憶が優先される（感情共鳴）

※ 加算方式を採用することで、感情共鳴の影響を適度に抑えつつ調整しやすくしている

---

## 設計思想

### 完全消去を避ける理由

- 人間は細部を忘れても「そんなことがあった気がする」という感覚は残る
- 痕跡だけでも残っていれば、関連話題への反応が可能
- 大切なものを完全に失うことへの抵抗

### 想起強化の意義

- 人間の記憶も思い出すたびに強化される
- 重要な記憶は自然と頻繁に参照され、より強固になる
- 参照されない記憶は自然と薄れていく

---

## 運用上の注意

### カテゴリ判定

- 基本は自動分類
- 特に重要なものは保護記憶としてマーク（後述）

### 保護記憶（Protected Memories）

ユーザーが「これは覚えておいて」「忘れないで」と明示した記憶を永続的に保護する機能。

**フィールド**

```json
{
  "id": "mem_20250115_001",
  "protected": true,
  ...
}
```

**保護記憶の挙動**

| 操作 | protected = true | protected = false |
|------|------------------|-------------------|
| 閾値判定による圧縮 | ✗ スキップ | ✓ 実行 |
| 比率強制による圧縮 | ✗ スキップ | ✓ 実行 |
| アーカイブ移行 | ✗ スキップ | ✓ 実行 |
| 完全削除 | ✗ スキップ | ✓ 実行 |
| 想起・検索 | ✓ 対象 | ✓ 対象 |

保護記憶は Level 1 のまま永続的に保持され、圧縮・アーカイブ・削除の対象外となる。

**比率計算からの除外**

保護記憶は比率計算の母数から除外する。

```python
# 比率計算時
active_memories = [m for m in memories if not m.get("protected", False)]
level1_ratio = count_level1(active_memories) / len(active_memories)
```

これにより、保護記憶が増えても通常記憶の比率管理に影響しない。

**上限と超過時の処理**

| パラメータ | 説明 | デフォルト値 |
|-----------|------|-------------|
| max_protected_memories | 保護記憶の最大件数 | 50 |

上限に達した状態で新たに保護記憶を追加しようとした場合：

```
1. 既存の保護記憶を古い順にリストアップ
2. ユーザーに確認:
   「保護記憶が上限（50件）に達しています。
   以下の記憶の保護を解除しますか？
   - [2024-06-15] パスワードの保存場所について
   - [2024-07-20] プロジェクトの重要な決定事項
   ...」
3. ユーザーが選択した記憶の protected = false に設定
4. 新しい記憶を保護
```

**保護の設定方法**

記憶生成時にLLMが「覚えておいて」等のフレーズを検出し、`protected: true` を設定する。

```
検出フレーズ例:
- 「これは覚えておいて」
- 「忘れないで」
- 「重要だから記憶して」
- 「絶対に忘れないで」
```

**保護の手動解除**

```python
def unprotect_memory(memory_id: str):
    """保護を解除"""
    memory = find_memory_by_id(memory_id)
    memory["protected"] = False
```

### パラメータ調整

- 減衰係数、閾値は運用しながら微調整可能
- 使用状況に応じて比率を見直す

### 想起の副作用

- 想起は記憶を強化するが、同時に記憶の改変リスクもある
- 想起のたびに content が微妙に変化する可能性を考慮

### 長期運用時のストレージ管理

#### データベースサイズの見積もり

memories.dbのサイズは記憶の総量と圧縮レベルの分布により変動する。

**1記憶あたりの平均サイズ（Embedding含む）**:
- Level 1（全文）: 約6-8KB
- Level 2（要約）: 約6-7KB
- Level 3（キーワード）: 約6KB
- Level 4（アーカイブ）: 約6KB

※Embeddingベクトル（1536次元 × float32）が約6KBを占める。SQLiteのBLOB形式でJSONよりコンパクト。

**年間運用での概算**（1日100記憶生成、比率強制後）:
- 1年後: 約36,500記憶 → 約200-300MB
- 3年後: 約110,000記憶 → 約600-800MB
- 5年後: 約180,000記憶 → 約1-1.3GB

SQLiteは数GB規模でも安定して動作するため、長期運用でも問題ない。

#### 推奨設定：アーカイブ自動削除の有効化

長期運用では `auto_delete_enabled: true` を推奨する。

```json
{
  "archive": {
    "auto_delete_enabled": true,
    "retention_days": 365
  }
}
```

**理由**:
1. **ストレージ効率**: アーカイブは本来「忘却された記憶」であり、永続保存の必要性が低い
2. **DB肥大化の防止**: 削除しないとアーカイブが際限なく増加する
3. **検索性能の維持**: 記憶総量を抑えることでインデックス効率が保たれる

**自動削除を無効にする場合の注意**:
- DBサイズを定期的に監視すること
- 1GB超過時は手動でのアーカイブ整理を検討
- `VACUUM`コマンドで削除後の領域を回収

#### SQLiteの性能特性

- 単一ファイルで管理され、外部サーバー不要
- 数十万レコード、数GBでも安定動作
- インデックスによりクエリ性能が維持される
- WALモード（有効化済み）により読み書きの並行性が向上

#### メンテナンスコマンド

```python
# VACUUMでDBを最適化（大量削除後に実行）
with store.connection() as conn:
    conn.execute("VACUUM")

# DBサイズの確認
import os
size_mb = os.path.getsize(DB_PATH) / (1024 * 1024)
print(f"Database size: {size_mb:.1f} MB")
```

#### 記憶件数の目安

| 運用年数 | 推定記憶数 | 推奨対応 |
|---------|-----------|---------|
| 1年 | ~36,500件 | auto_delete推奨 |
| 2-3年 | ~110,000件 | auto_delete必須、定期VACUUM |
| 3年以上 | 150,000件+ | 定期バックアップ、VACUUM |

### バックアップと復旧

#### バックアップの推奨運用

memories.dbは定期的に手動バックアップを取ることを推奨する。

**推奨タイミング**:
- 週に1回程度のコピー保存
- 重要な会話セッション後
- システム更新・移行前

**バックアップ方法**:
```bash
# シンプルなコピー（日付付き）
cp memories.db memories_backup_$(date +%Y%m%d).db

# または任意の場所に保存
cp memories.db ~/backups/leva_memories_$(date +%Y%m%d).db
```

**SQLiteの安全なバックアップ（書き込み中でも安全）**:
```bash
sqlite3 memories.db ".backup memories_backup_$(date +%Y%m%d).db"
```

#### 破損時の復旧手順

memories.dbが破損した場合の対処法。

**1. 破損の確認**
```bash
# 整合性チェック
sqlite3 memories.db "PRAGMA integrity_check;"
# "ok" 以外が出れば破損している
```

**2. バックアップからの復旧**
```bash
# 破損ファイルを退避
mv memories.db memories_corrupted_$(date +%Y%m%d).db

# バックアップから復元
cp memories_backup_YYYYMMDD.db memories.db
```

**3. バックアップがない場合**
- 完全な復旧は不可能
- 空のDBを再作成してスキーマを適用
- 部分的に読み取れる場合は `sqlite3 memories.db ".dump"` でデータ抽出を試みる

#### トランザクションによる保護

SQLiteのトランザクション機能により、書き込み中のクラッシュによる破損リスクは低い。

- 各操作はトランザクション内で実行される
- コミット前にクラッシュしても、既存データは保護される
- WALモードにより書き込み耐性がさらに向上

**注意**: SQLiteの保護機構はプロセスクラッシュに対する保護であり、ディスク障害や操作ミスには対応できない。定期バックアップとの併用を推奨。

---

## 付録：感情強度スコアリングの例

| シチュエーション | 想定スコア |
|----------------|-----------|
| 単純なtypo修正 | 15-25 |
| 技術的議論 | 30-40 |
| 設計決定 | 40-50 |
| 個人的な話題に触れた | 50-65 |
| 深い感情的やり取り | 70-85 |
| トラウマに関連 | 85-100 |

---

## 検索技術の選定（RAG等の必要性）

### 判断基準

RAG（Retrieval-Augmented Generation）等の高度な検索技術の必要性は、**規模と用途**によって決まる。

### RAGが不要なケース

- 記憶の総量が少ない（数百件以下）
- キーワード一致で十分な精度が出る
- 参照パターンが単純（時系列、カテゴリ検索が主）

本設計では `keywords` と `category` で構造化されているため、小規模なら単純なフィルタリングと優先度計算で運用可能。

### RAGが必要なケース

- 記憶が大量（数千件以上）
- 「あの時の話」のような曖昧な参照が多い
- キーワードに含まれない同義語・関連概念での検索が必要

例：「前にパフォーマンスの話したよね」と言われた時、`keywords` に「パフォーマンス」がなくても「最適化」「速度改善」の記憶を引っ張ってこれる。これはベクトル検索の強み。

### 段階的実装戦略

```
Phase 1: キーワード + カテゴリ + 優先度計算
         → まずこれで運用開始
         → 実装コスト低、即座に動作可能

Phase 2: 記憶が増えてきたらEmbedding追加
         → キーワード検索で引っかからなかった時のフォールバック
         → ハイブリッド検索への移行

Phase 3: 完全なRAG統合
         → ベクトル類似度と保持スコアを組み合わせた検索
         → 大規模記憶ストアに対応
```

### 推奨アプローチ

最初から完璧を目指さず、動くものを作って運用しながら拡張する。

---

## 設定ファイル構造

パラメータをハードコードせず、設定ファイルに外出しすることで調整を容易にする。

### 設定ファイル: `config/config.json`

```json
{
  "version": "1.0.0",

  "retention": {
    "base_decay_coefficient": 0.995,
    "decay_by_category": {
      "casual": { "min": 0.70, "max": 0.80 },
      "work": { "min": 0.85, "max": 0.92 },
      "decision": { "min": 0.93, "max": 0.97 },
      "emotional": { "min": 0.98, "max": 0.999 }
    },
    "max_decay_coefficient": 0.999
  },

  "levels": {
    "level1_threshold": 50,
    "level2_threshold": 20,
    "level3_threshold": 5
  },

  "recall": {
    "decay_coefficient_boost": 0.02,
    "memory_days_reduction": 0.5,
    "recall_count_weight": 0.1
  },

  "resonance": {
    "valence_match_bonus": 0.3,
    "arousal_proximity_bonus": 0.2,
    "tags_overlap_weight": 0.5,
    "priority_weight_alpha": 0.3
  },

  "compression": {
    "level1_ratio": 0.15,
    "level2_ratio": 0.30,
    "level3_ratio": 0.35,
    "delete_ratio": 0.20,
    "schedule_hour": 3,
    "interval_hours": 24
  },

  "relations": {
    "score_proximity_threshold": 5.0,
    "auto_link_similarity_threshold": 0.85,
    "max_relations_per_memory": 10,
    "relation_traversal_depth": 1,
    "enable_auto_linking": true
  },

  "retrieval": {
    "top_k": 5,
    "relevance_threshold": 5.0
  },

  "archive": {
    "enable_archive_recall": true,
    "revival_decay_per_day": 0.995,
    "revival_min_margin": 3.0,
    "auto_delete_enabled": false,
    "retention_days": 365,
    "delete_require_zero_recall": true,
    "delete_max_intensity": 20,
    "delete_condition_mode": "AND"
  },

  "protection": {
    "max_protected_memories": 50
  },

  "embedding": {
    "provider": "openai",
    "model": "text-embedding-3-small",
    "dimensions": 1536
  },

  "llm": {
    "provider": "anthropic",
    "model": "claude-3-5-haiku-20241022",
    "temperature": 0,
    "max_tokens": 1024
  }
}
```

### 設定項目一覧

| セクション | キー | 説明 | デフォルト値 |
|-----------|------|------|-------------|
| retention | base_decay_coefficient | 基本減衰係数 | 0.995 |
| retention | max_decay_coefficient | 減衰係数の上限 | 0.999 |
| retention | decay_by_category | カテゴリ別減衰係数範囲 | （上記参照） |
| levels | level1_threshold | Level1の閾値 | 50 |
| levels | level2_threshold | Level2の閾値 | 20 |
| levels | level3_threshold | Level3/アーカイブ移行の閾値 | 5 |
| recall | decay_coefficient_boost | 想起時の減衰係数増加量 | 0.02 |
| recall | memory_days_reduction | 想起時のmemory_days削減率 | 0.5 |
| recall | recall_count_weight | recall_countの重み | 0.1 |
| resonance | valence_match_bonus | valence一致ボーナス | 0.3 |
| resonance | arousal_proximity_bonus | arousal近接ボーナス（最大値） | 0.2 |
| resonance | tags_overlap_weight | tags重複の重み | 0.5 |
| resonance | priority_weight_alpha | 感情共鳴の優先度重み（α） | 0.3 |
| compression | level*_ratio | 各レベルの目標比率 | 15/30/35/20% |
| compression | schedule_hour | 圧縮処理の定期実行時刻（時） | 3 |
| compression | interval_hours | 圧縮処理の実行間隔（時間） | 24 |
| relations | score_proximity_threshold | スコア近接判定の閾値 | 5.0 |
| relations | auto_link_similarity_threshold | 自動関連付けの類似度閾値 | 0.85 |
| relations | max_relations_per_memory | 1記憶あたりの最大関連数 | 10 |
| relations | relation_traversal_depth | 関連記憶の取得深度 | 1 |
| relations | enable_auto_linking | 自動関連付けの有効/無効 | true |
| retrieval | top_k | 想起時の最大取得件数 | 5 |
| retrieval | relevance_threshold | 関連度の閾値（フォールバック判定用） | 5.0 |
| archive | enable_archive_recall | アーカイブからの自動復活の有効/無効 | true |
| archive | revival_decay_per_day | 復活時のアーカイブ滞在日数による減衰係数 | 0.995 |
| archive | revival_min_margin | 復活時の最低スコアマージン | 3.0 |
| archive | auto_delete_enabled | 自動削除の有効/無効 | false |
| archive | retention_days | 自動削除までの保持日数 | 365 |
| archive | delete_require_zero_recall | 想起回数0を削除条件に含める | true |
| archive | delete_max_intensity | 削除対象の感情強度上限 | 20 |
| archive | delete_condition_mode | 削除条件の結合方式（AND/OR） | AND |
| protection | max_protected_memories | 保護記憶の最大件数 | 50 |
| embedding | provider | Embeddingプロバイダー | openai |
| embedding | model | Embeddingモデル | text-embedding-3-small |
| embedding | dimensions | ベクトル次元数 | 1536 |
| llm | provider | LLMプロバイダー | anthropic |
| llm | model | LLMモデル | claude-3-5-haiku-20241022 |
| llm | temperature | 生成時の温度（0で決定的） | 0 |
| llm | max_tokens | 最大出力トークン数 | 1024 |

### ディレクトリ構造

```
LTM_system/
├── config/
│   ├── config.json          # 本番設定
│   ├── config.dev.json      # 開発用設定
│   └── config.schema.json   # バリデーション用スキーマ（任意）
├── src/
│   ├── config_loader.py     # 設定読み込みモジュール
│   ├── memory_store.py      # 記憶ストレージ操作（排他制御）
│   ├── retention.py         # 保持スコア計算
│   ├── recall.py            # 想起処理
│   ├── compression.py       # 圧縮処理
│   ├── resonance.py         # 感情共鳴計算
│   ├── memory_retrieval.py  # 記憶検索（UserPromptSubmit Hook用）
│   └── memory_generation.py # 記憶生成（SessionEnd Hook用）
├── data/
│   └── memories.db          # SQLiteデータベース（記憶・アーカイブ・状態を統合）
├── memory.md                # 設計書（本ファイル）
└── memory_system_todo.md    # 実装TODO
```

### 設計方針

- **実行時読み込み**: 再コンパイル不要で調整可能
- **環境別設定**: dev/prod で設定ファイルを切り替え
- **バージョン管理**: 設定変更履歴を追跡可能
- **バリデーション**: schema.json で設定値の妥当性を検証（任意）

---

## データ整合性

複数プロセス（UserPromptSubmit Hook、SessionEnd Hook、日次バッチ）が同時にデータベースにアクセスする可能性があるため、SQLiteのトランザクション機能で排他制御を行う。

### 競合シナリオ

| プロセス | タイミング | 操作 |
|----------|-----------|------|
| UserPromptSubmit Hook | メッセージ送信時 | 検索 → 想起フラグ更新 |
| SessionEnd Hook | セッション終了時 | 新規記憶追加 |
| 日次バッチ処理 | 毎日深夜3時 | 圧縮処理・アーカイブ移行 |

### SQLiteの排他制御

SQLiteはファイルレベルのロックを自動で管理するため、外部ライブラリ（filelock等）は不要。

- **読み取り**: 複数プロセスから同時読み取り可能
- **書き込み**: 1プロセスのみ（他はWALモードで待機）
- **トランザクション**: ACID準拠、クラッシュ時も整合性維持

### テーブル定義

```sql
-- 記憶テーブル（アクティブ + アーカイブ統合）
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    created TEXT NOT NULL,
    memory_days REAL DEFAULT 0.0,
    recalled_since_last_batch INTEGER DEFAULT 0,
    recall_count INTEGER DEFAULT 0,
    emotional_intensity INTEGER NOT NULL,
    emotional_valence TEXT NOT NULL,
    emotional_arousal INTEGER NOT NULL,
    emotional_tags TEXT,  -- JSON配列として保存
    decay_coefficient REAL NOT NULL,
    category TEXT NOT NULL,
    keywords TEXT,  -- JSON配列として保存
    current_level INTEGER DEFAULT 1,
    trigger TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding BLOB,  -- numpy配列をバイナリ化
    relations TEXT,  -- JSON配列として保存
    retention_score REAL,
    archived_at TEXT,  -- NULLならアクティブ、値があればアーカイブ
    protected INTEGER DEFAULT 0,
    revival_requested INTEGER DEFAULT 0,
    revival_requested_at TEXT
);

-- インデックス（検索高速化）
CREATE INDEX IF NOT EXISTS idx_retention_score ON memories(retention_score);
CREATE INDEX IF NOT EXISTS idx_current_level ON memories(current_level);
CREATE INDEX IF NOT EXISTS idx_archived_at ON memories(archived_at);
CREATE INDEX IF NOT EXISTS idx_created ON memories(created);

-- 状態テーブル
CREATE TABLE IF NOT EXISTS state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

### MemoryStore クラス

すべての記憶操作は `MemoryStore` クラスを経由して行う。直接SQLを実行しないこと。

```python
import sqlite3
import json
import numpy as np
from contextlib import contextmanager

class MemoryStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """データベース初期化"""
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
    def _connect(self):
        """コネクション管理（WALモード有効）"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except:
            conn.rollback()
            raise
        finally:
            conn.close()

    def connection(self):
        """コネクションを取得（直接SQL実行用）"""
        return self._connect()

    def add_memory(self, memory: dict):
        """記憶を追加"""
        with self._connect() as conn:
            conn.execute('''
                INSERT INTO memories (
                    id, created, memory_days, recalled_since_last_batch, recall_count,
                    emotional_intensity, emotional_valence, emotional_arousal, emotional_tags,
                    decay_coefficient, category, keywords, current_level, trigger, content,
                    embedding, relations, retention_score, archived_at, protected
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                memory['id'], memory['created'], memory.get('memory_days', 0.0),
                int(memory.get('recalled_since_last_batch', False)),
                memory.get('recall_count', 0), memory['emotional_intensity'],
                memory['emotional_valence'], memory['emotional_arousal'],
                json.dumps(memory.get('emotional_tags', []), ensure_ascii=False),
                memory['decay_coefficient'], memory['category'],
                json.dumps(memory.get('keywords', []), ensure_ascii=False),
                memory.get('current_level', 1), memory['trigger'], memory['content'],
                self._encode_embedding(memory.get('embedding')),
                json.dumps(memory.get('relations', []), ensure_ascii=False),
                memory.get('retention_score'), memory.get('archived_at'),
                int(memory.get('protected', False))
            ))

    def get_active_memories(self) -> list:
        """アクティブ記憶を取得（アーカイブ以外）"""
        with self._connect() as conn:
            rows = conn.execute(
                'SELECT * FROM memories WHERE archived_at IS NULL'
            ).fetchall()
            return [self._row_to_dict(row) for row in rows]

    def get_archived_memories(self) -> list:
        """アーカイブ記憶を取得"""
        with self._connect() as conn:
            rows = conn.execute(
                'SELECT * FROM memories WHERE archived_at IS NOT NULL'
            ).fetchall()
            return [self._row_to_dict(row) for row in rows]

    def update_memory(self, memory_id: str, updates: dict):
        """記憶を更新"""
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

    def mark_recalled(self, memory_ids: list):
        """想起フラグを立てる"""
        with self._connect() as conn:
            placeholders = ','.join('?' * len(memory_ids))
            conn.execute(f'''
                UPDATE memories
                SET recalled_since_last_batch = 1
                WHERE id IN ({placeholders}) AND archived_at IS NULL
            ''', memory_ids)

    def delete_memory(self, memory_id: str):
        """記憶を完全削除"""
        with self._connect() as conn:
            conn.execute('DELETE FROM memories WHERE id = ?', (memory_id,))

    def get_state(self, key: str) -> str:
        """状態を取得"""
        with self._connect() as conn:
            row = conn.execute(
                'SELECT value FROM state WHERE key = ?', (key,)
            ).fetchone()
            return row['value'] if row else None

    def set_state(self, key: str, value: str):
        """状態を設定"""
        with self._connect() as conn:
            conn.execute('''
                INSERT OR REPLACE INTO state (key, value) VALUES (?, ?)
            ''', (key, value))

    def _encode_embedding(self, embedding) -> bytes:
        """EmbeddingをBLOBに変換"""
        if embedding is None:
            return None
        return np.array(embedding, dtype=np.float32).tobytes()

    def _decode_embedding(self, blob: bytes) -> list:
        """BLOBからEmbeddingを復元"""
        if blob is None:
            return None
        return np.frombuffer(blob, dtype=np.float32).tolist()

    def _row_to_dict(self, row) -> dict:
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
```

### 使用例

```python
# 初期化
store = MemoryStore("data/memories.db")

# 新規記憶を追加
store.add_memory({
    "id": "mem_20260120_001",
    "created": "2026-01-20T14:30:00+09:00",
    "emotional_intensity": 45,
    "emotional_valence": "positive",
    "emotional_arousal": 30,
    "decay_coefficient": 0.92,
    "category": "work",
    "trigger": "記憶システムについて相談された",
    "content": "SQLite移行について議論した",
    "embedding": [0.123, -0.456, ...],  # 1536次元
})

# 想起フラグを立てる
store.mark_recalled(["mem_20260120_001", "mem_20260119_003"])

# アクティブ記憶を取得
memories = store.get_active_memories()

# 記憶を更新
store.update_memory("mem_20260120_001", {
    "retention_score": 42.5,
    "memory_days": 1.0
})

# 状態の読み書き
store.set_state("last_compression_run", "2026-01-20T03:00:00+09:00")
last_run = store.get_state("last_compression_run")
```

### SQLiteの利点

| 項目 | 説明 |
|------|------|
| **外部依存なし** | Python標準ライブラリ（sqlite3）のみで動作 |
| **自動ロック** | ファイルロックを自動管理、filelockライブラリ不要 |
| **WALモード** | 読み取りと書き込みを並行実行可能 |
| **トランザクション** | ACID準拠、クラッシュ時も整合性維持 |
| **部分更新** | 1件の記憶だけ更新可能（全件書き換え不要） |
| **インデックス** | retention_score等での高速検索 |

### 注意事項

- SQLiteは単一ファイルなので、バックアップはファイルコピーで可能
- WALモードでは `memories.db-wal` と `memories.db-shm` ファイルも生成される
- 大量の記憶を一括処理する場合は `executemany()` を使用すること

---

## 記憶注入システム（UserPromptSubmit Hook）

Claude Code の Hook 機能を使用して、ユーザーメッセージ送信前に関連記憶を自動注入する。

### アーキテクチャ

```
┌─────────────────────────────────────────────────────┐
│ Claude Code                                         │
│                                                     │
│   指揮官の入力: 「記憶システムについて教えて」        │
│        ↓                                            │
│   [UserPromptSubmit Hook]                           │
│        ↓                                            │
│   python src/memory_retrieval.py                    │
│   （標準入力でJSON形式のデータを受け取る）           │
│        ↓                                            │
│   print() で関連記憶を出力                           │
│        ↓                                            │
│   出力がユーザーメッセージに追加される                │
│        ↓                                            │
│   Claude が記憶付きメッセージを受け取る              │
│        ↓                                            │
│   応答生成（指揮官には応答のみ表示）                 │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### Hook 設定

Claude Code の設定ファイル（`.claude/settings.json` 等）に以下を追加：

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python path/to/LTM_system/src/memory_retrieval.py"
          }
        ]
      }
    ]
  }
}
```

### 入力形式

Hook はユーザー入力を**標準入力経由でJSON形式**で受け取る。コマンドライン引数ではないため、コマンドインジェクションのリスクはない。

```json
{
  "prompt": "ユーザーの入力内容"
}
```

### memory_retrieval.py 実装例

```python
#!/usr/bin/env python3
import json
import sys
import io
from datetime import datetime

# 標準入出力のエンコーディング設定（Windows対応）
sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding='utf-8')
sys.stdout.reconfigure(encoding='utf-8')

CONFIG_PATH = "path/to/LTM_system/config/config.json"
DB_PATH = "path/to/LTM_system/data/memories.db"

def get_prompt_from_stdin():
    """標準入力からプロンプトを取得"""
    data = json.load(sys.stdin)
    return data.get("prompt", "")

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def get_embedding(text):
    """テキストをベクトル化（Embedding API を使用）"""
    from openai import OpenAI
    client = OpenAI()
    response = client.embeddings.create(
        input=text,
        model="text-embedding-3-small"
    )
    return response.data[0].embedding

def cosine_similarity(vec_a, vec_b):
    """コサイン類似度を計算"""
    import numpy as np
    a = np.array(vec_a)
    b = np.array(vec_b)
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def calculate_relevance(memory, query_embedding, current_emotion=None):
    """参照優先度を計算"""
    score = memory.get("retention_score", 0) or 0

    # ベクトル類似度（コサイン類似度）
    memory_embedding = memory.get("embedding")
    if memory_embedding and query_embedding:
        keyword_match = cosine_similarity(query_embedding, memory_embedding)
        keyword_match = max(0, keyword_match)
    else:
        keyword_match = 0

    # recall_count による重み
    recall_weight = 1 + 0.1 * memory.get("recall_count", 0)

    # 基本優先度
    base_priority = score * keyword_match * recall_weight

    # 感情共鳴（current_emotion が指定されている場合）
    resonance_bonus = 0
    if current_emotion:
        resonance_bonus = calculate_resonance(memory, current_emotion)
        alpha = 0.3
        resonance_bonus = alpha * resonance_bonus * score

    return base_priority + resonance_bonus

def calculate_resonance(memory, current):
    """感情共鳴スコアを計算"""
    score = 0

    if memory.get("emotional_valence") == current.get("valence"):
        score += 0.3

    mem_arousal = memory.get("emotional_arousal", 50)
    cur_arousal = current.get("arousal", 50)
    arousal_diff = abs(mem_arousal - cur_arousal) / 100
    score += max(0, 0.2 * (1 - arousal_diff))

    mem_tags = set(memory.get("emotional_tags", []))
    cur_tags = set(current.get("tags", []))
    if mem_tags and cur_tags:
        overlap = len(mem_tags & cur_tags) / max(len(mem_tags), len(cur_tags))
        score += overlap * 0.5

    return score

def search_memories(query_embedding, memories, archive, top_k=5, config=None):
    """関連記憶を検索（アーカイブ含む、自動復活対応）"""
    scored = []
    relevance_threshold = config.get("retrieval", {}).get("relevance_threshold", 5.0) if config else 5.0

    # アクティブ記憶を検索
    for mem in memories:
        relevance = calculate_relevance(mem, query_embedding)
        if relevance > 0:
            scored.append((relevance, mem, False))

    # アーカイブも検索（enable_archive_recall = true の場合）
    if config and config.get("archive", {}).get("enable_archive_recall", True):
        for mem in archive:
            relevance = calculate_relevance(mem, query_embedding)
            if relevance > 0:
                scored.append((relevance, mem, True))

    # 閾値以上の記憶を抽出
    high_relevance = [(r, mem, is_arch) for r, mem, is_arch in scored if r >= relevance_threshold]

    if len(high_relevance) >= top_k:
        # 十分な候補があれば閾値以上のみソート（高速）
        high_relevance.sort(key=lambda x: x[0], reverse=True)
        return [(mem, is_archived) for _, mem, is_archived in high_relevance[:top_k]]
    else:
        # 候補不足時は全件からtop_k取得（フォールバック）
        scored.sort(key=lambda x: x[0], reverse=True)
        return [(mem, is_archived) for _, mem, is_archived in scored[:top_k]]

def format_memories(results):
    """記憶を出力形式にフォーマット"""
    lines = ["<memories>"]
    for mem, is_archived in results:
        created = mem.get("created", "unknown")
        trigger = mem.get("trigger", "")
        content = mem.get("content", "")
        level = mem.get("current_level", 1)
        archived_mark = "[archived]" if is_archived else ""
        lines.append(f"- [{created}][L{level}]{archived_mark} {trigger} → {content}")
    lines.append("</memories>")
    return "\n".join(lines)

def should_skip(query):
    """記憶処理をスキップすべきか判定"""
    return query.strip().startswith("/")

# MemoryStore インスタンス
_store = None

def get_store():
    global _store
    if _store is None:
        from memory_store import MemoryStore
        _store = MemoryStore(DB_PATH)
    return _store

def main():
    query = get_prompt_from_stdin()

    if not query.strip() or should_skip(query):
        return

    config = load_config()
    store = get_store()

    # アクティブ記憶とアーカイブ記憶を取得
    memories = store.get_active_memories()
    archive = store.get_archived_memories()

    if not memories and not archive:
        return

    # クエリをベクトル化
    query_embedding = get_embedding(query)

    # 検索
    results = search_memories(query_embedding, memories, archive, config=config)

    if results:
        # 記憶を出力（ユーザーメッセージに追加される）
        print(format_memories(results))

        # アクティブ記憶の想起フラグを立てる
        recalled_ids = [mem["id"] for mem, is_archived in results if not is_archived]
        if recalled_ids:
            store.mark_recalled(recalled_ids)

        # アーカイブ記憶の復活リクエストフラグを立てる
        archived_ids = [mem["id"] for mem, is_archived in results if is_archived]
        if archived_ids:
            now = datetime.now().astimezone().isoformat()
            for mem_id in archived_ids:
                store.update_memory(mem_id, {
                    "revival_requested": True,
                    "revival_requested_at": now
                })

if __name__ == "__main__":
    main()
```

### 注入形式

ユーザーメッセージの先頭に以下の形式で追加される：

```
<memories>
- [2026-01-18][L1] 「減衰係数について相談された」 → 記憶システムの設計について議論。減衰係数0.995を採用決定。
- [2026-01-15][L2] 「LLMの記憶について聞かれた」 → LLMの記憶について雑談した。
- [2026-01-10][L3][archived] 「技術選定, 相談」 → 「ストレージ, JSON」
</memories>

（指揮官の元のメッセージ）
```

trigger と content が `→` で区切られ、アーカイブ記憶には `[archived]` マークが付く。

### 特徴

| 項目 | 説明 |
|------|------|
| 透明性 | 指揮官には記憶のメタデータは表示されない |
| 自動想起 | メッセージ送信時に自動で関連記憶を検索・注入 |
| 想起記録 | 想起された記憶は `recalled_since_last_batch` フラグが立つ |
| MCP不要 | シンプルなPythonスクリプトのみで実装可能 |

### 除外ルール

特定の入力パターンは記憶システムの対象外とする。

#### 除外対象

| パターン | 理由 |
|----------|------|
| `/` で始まる入力 | スラッシュコマンド（システム操作） |
| コマンドへの応答 | コマンド実行結果は会話ではない |

#### 除外時の動作

| 処理 | 動作 |
|------|------|
| 想起 | 記憶を検索・注入しない |
| 記憶生成 | 入力も応答も記憶として保存しない |

#### 実装

```python
def should_skip(query):
    """記憶処理をスキップすべきか判定"""
    q = query.strip()
    if q.startswith("/"):
        return True
    return False
```

記憶生成側でも同様のフィルタリングを行い、コマンドセッション中は記憶を生成しない。

### 永続記憶との併用

重要度の高い記憶は CLAUDE.md に記載し、動的な記憶は Hook で注入するハイブリッド方式を推奨。

```
CLAUDE.md:
  - 永続的に参照すべき重要記憶
  - 記憶システムの存在と使用方法の説明

UserPromptSubmit Hook:
  - その発言に関連する動的な記憶
  - 検索結果に基づく文脈依存の記憶
```

---

## 付録：検討したが見送った設計案

### 感情価による想起非対称性

**概要**

心理学研究に基づき、感情価（valence）と強度によって想起しやすさを非対称にする案。

```
positive × 高強度 → 想起されにくい
negative × 高強度 → 想起されやすい
```

人間の「ネガティビティ・バイアス」を再現する設計。

**検討内容**

実装した場合の影響を推論：

1. **時間経過による感情の偏り**: negative記憶が強化され続け、positive記憶は埋没する
2. **負のフィードバックループ**: negative想起 → 強化 → さらにnegative想起の連鎖
3. **人間の抑うつ状態と類似したメカニズム**が発生する可能性

**反論（見送りの根拠）**

- 高強度の記憶は全体の少数（5〜20%程度）
- 大半を占める中〜低強度の記憶は非対称性の影響を受けない
- 想起の総量で見れば、システム全体が急激にネガティブに傾くわけではない
- ただし長期的には「少数だが消えない暗い記憶」が蓄積する可能性は残る

**結論**

人間らしさは増すが、システムが「病みやすく」なるリスクがある。現時点では対称モデルを維持し、実装を見送る。

将来的に再検討する場合は、以下の対策とセットで導入を検討：
- positive記憶を意図的に浮上させる「気分転換モード」
- negative想起頻度の上限リミッター
- 感情バランスのモニタリング機能

---

## 付録：年間コスト見積もり

### 前提条件

| 項目 | 値 |
|------|-----|
| 1日の会話数 | 100件 |
| 1件あたりの文字数（Level 1） | trigger 200文字 + content 2000文字 = 2200文字 |
| 1件あたりの文字数（Level 2） | trigger 80文字 + content 200文字 = 280文字 |
| 運用期間 | 1年（365日） |
| 総記憶数 | 36,500件 |
| 日本語トークン換算 | 1文字 ≈ 1.5トークン |

※ Level 1は元の会話をそのまま保存するため、アシスタント応答（コード含む）が長くなる想定

### 記憶の分布（比率強制後）

| レベル | 比率 | 件数 |
|--------|------|------|
| Level 1（完全記憶） | 15% | 5,475件 |
| Level 2（圧縮記憶） | 30% | 10,950件 |
| Level 3（痕跡記憶） | 35% | 12,775件 |
| アーカイブ | 20% | 7,300件 |

### 年間圧縮発生件数

| 遷移 | 件数 |
|------|------|
| Level 1 → 2 | 31,025件 |
| Level 2 → 3 | 20,075件 |

### Embedding コスト（text-embedding-3-small: $0.02/1Mトークン）

| 用途 | トークン数 | コスト |
|------|-----------|--------|
| 新規記憶生成（Level 1: 2200文字×1.5×36,500件） | 120.5M | $2.41 |
| 想起時クエリ（ユーザー入力150文字×36,500回） | 8.2M | $0.16 |
| 圧縮時再生成（L1→L2: 280文字×1.5×31,025件） | 13.0M | $0.26 |
| 圧縮時再生成（L2→L3: 50文字×1.5×20,075件） | 1.5M | $0.03 |
| **合計** | **143.2M** | **$2.86** |

### LLM コスト（Claude 4.5 Haiku: $1.00/1M入力, $5.00/1M出力）

| 処理 | 入力トークン | 出力トークン | コスト |
|------|-------------|-------------|--------|
| 記憶生成（感情分析のみ） | 120.5M | 3.7M | $139.00 |
| L1→L2 圧縮（要約生成: 2200文字入力） | 102.4M | 13.0M | $167.40 |
| L2→L3 圧縮（キーワード抽出: 280文字入力） | 8.4M | 1.5M | $15.90 |
| **合計** | **231.3M** | **18.2M** | **$322.30** |

### 年間総コスト

| 項目 | コスト（USD） | コスト（JPY, 150円換算） |
|------|--------------|-------------------------|
| Embedding | $2.86 | ¥429 |
| LLM | $322.30 | ¥48,345 |
| **合計** | **$325.16** | **¥48,774** |

### 月額換算

| 項目 | コスト（USD） | コスト（JPY） |
|------|--------------|---------------|
| **月額** | **約$27** | **約¥4,100** |

### モデル別コスト比較（参考）

| モデル | 年間コスト | 月額 |
|--------|-----------|------|
| **Claude 4.5 Haiku（推奨）** | **$325（¥48,800）** | **$27（¥4,100）** |
| Claude 4.5 Sonnet | $1,225（¥183,800） | $102（¥15,300）|
| Claude 4.5 Opus | $1,735（¥260,300） | $145（¥21,700） |

### 注意事項

- 上記は推定値であり、実際の使用量は会話パターンにより変動する
- Level 1で元の会話を完全保存するため、L1→L2圧縮時のコストが増加している
- 為替レートは 1 USD = 150 JPY で計算
- API価格は変更される可能性があるため、最新価格はAnthropic公式を確認
- Haikuは感情分析・要約タスクに十分な性能を持ち、コスト効率が最も高い

---

*最終更新: 2026-01-21*
*更新内容: 第7回レビュー対応。update_memory()にrevival_requested変換追加、search_memories()に閾値+フォールバック方式追加、config.jsonにretrievalセクション追加。*
