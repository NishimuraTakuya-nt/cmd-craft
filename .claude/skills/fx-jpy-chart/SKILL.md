---
name: fx-jpy-chart
description: ドル円(USD/JPY)とラリ円(GEL/JPY, ジョージア・ラリ)の推移グラフを、最新レートと最新ニュースを調査した上で作成する。「ドル円」「ラリ円」「為替推移」「GEL JPY」「USDJPY チャート」などの依頼で使う。
---

# ドル円・ラリ円 推移グラフ

USD/JPY と GEL/JPY の推移を取得してグラフ化し、直近の値動きの背景（最新ニュース）を添えて報告する。

## 手順

### 1. 期間を決める
- ユーザー指定がなければ **直近1年 (365日)**。「最近」「直近」なら 90 日。
- 今日の日付を確認し、「最新」= 今日時点として扱う。

### 2. 最新情報を調査する（WebSearch）
グラフを出す前に必ず実施する。以下を並列で検索する（クエリには現在の年月を入れる）:
- `ドル円 最新 <YYYY年M月>` / `USD JPY latest <Month YYYY>` — 現在値・直近の材料（日銀・FRB の政策、介入、米指標）
- `Georgian lari GEL exchange rate <Month YYYY>` / `ラリ 為替 <YYYY年>` — ラリの材料（ジョージア国立銀行 NBG の政策金利・介入、政治情勢）
- 必要なら `日銀 金融政策決定会合 <YYYY年M月>`, `FOMC <Month YYYY>`, `National Bank of Georgia refinancing rate`

調査結果から、期間内の重要イベントを **最大 8 件** 程度選び、作業ディレクトリに `events.json` として保存する:
```json
[
  {"date": "2026-07-31", "label": "日銀 会合で利上げ", "url": "https://..."},
  {"date": "2026-09-17", "label": "FOMC 0.25%利下げ", "url": "https://..."}
]
```
日付が確認できないイベントは入れない。推測で日付を作らない。

### 3. データ取得とグラフ生成
スクリプトは標準ライブラリのみで動く（PNG だけ matplotlib が必要）:
```bash
python3 .claude/skills/fx-jpy-chart/scripts/fx_chart.py \
  --days 365 --out fx_out --events events.json \
  --summary "<調査結果の2〜3文の要約>" [--png]
```
- 出力: `fx_out/fx_jpy.csv`, `fx_out/fx_jpy.html`（ダーク/ライト対応 SVG、ホバーで値表示）, `fx_out/fx_jpy.png`（`--png` 時）
- 標準出力の JSON に最新値・期間変化率・高値/安値が入る。報告にはこの値を使う。
- データソースは fawazahmed0/currency-api（jsdelivr / pages.dev）→ Yahoo Finance の順にフォールバック。
- GEL/JPY は `USD/JPY ÷ USD/GEL` のクロスレート。
- 再描画だけなら `--from-csv fx_out/fx_jpy.csv`。

**取得が全滅した場合**（ネットワーク制限など）: 失敗したホスト名をユーザーに伝える。
WebSearch/WebFetch で得たレートを `date,USDJPY,USDGEL` の CSV に手で起こして `--from-csv` で描画してもよいが、
その場合は「検索で得た点のみで粗いグラフ」であることを明記する。数値を捏造しない。

### 4. 検証
- スクリプト出力の最新値と、WebSearch で確認した直近レートが大きく乖離していないか確認する（目安: USD/JPY ±2%, GEL/JPY ±3%）。乖離していたらその旨を報告する。
- データ最終日が今日から 4 日以上前なら、古い旨を明記する。

### 5. 報告
ユーザーには日本語で簡潔に:
1. 最新値（USD/JPY, GEL/JPY, 参考 USD/GEL）とデータ日付
2. 期間変化（円・%）、期間高値/安値
3. 値動きの背景 2〜4 点（調査したニュース、出典リンク付き）
4. グラフ（HTML は表示/共有できる環境なら Artifact として公開、PNG はファイル送付）

投資助言はしない。レートは参考値で、公式レートは日銀・NBG 等で確認するよう一言添える。
