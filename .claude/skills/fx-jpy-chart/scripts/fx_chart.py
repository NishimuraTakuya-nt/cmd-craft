#!/usr/bin/env python3
"""USD/JPY と GEL/JPY (ドル円・ラリ円) の推移を取得してグラフ化する。

標準ライブラリのみで動作する。出力:
  - <out>/fx_jpy.csv   : 日付, USDJPY, GELJPY, USDGEL
  - <out>/fx_jpy.html  : インライン SVG のグラフ (外部依存なし)
  - <out>/fx_jpy.png   : matplotlib がある場合のみ (--png)

データソース (上から順に試す):
  1. fawazahmed0/currency-api (jsdelivr CDN / Cloudflare Pages ミラー) — 日次・GEL 対応
  2. Yahoo Finance chart API (JPY=X, GEL=X)

使い方:
  python3 fx_chart.py --days 365 --out ./fx_out
  python3 fx_chart.py --days 90 --events events.json --png
  python3 fx_chart.py --from-csv fx_out/fx_jpy.csv   # 取得せず再描画
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import json
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

UA = "fx-jpy-chart/1.0 (+https://github.com/nishimuratakuya-nt/cmd-craft)"
TIMEOUT = 20

CURRENCY_API_URLS = [
    "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@{tag}/v1/currencies/usd.min.json",
    "https://{tag}.currency-api.pages.dev/v1/currencies/usd.min.json",
]


# ---------------------------------------------------------------- fetching
def _get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def _currency_api_one(tag: str):
    """tag は 'latest' か 'YYYY-MM-DD'。(date, usdjpy, usdgel) を返す。"""
    last_err = None
    for tpl in CURRENCY_API_URLS:
        try:
            d = _get_json(tpl.format(tag=tag))
            usd = d["usd"]
            return d.get("date", tag), float(usd["jpy"]), float(usd["gel"])
        except (urllib.error.URLError, KeyError, ValueError, TimeoutError, OSError) as e:
            last_err = e
    raise RuntimeError(f"currency-api {tag}: {last_err}")


def fetch_currency_api(days: int, max_points: int = 150) -> list[tuple[str, float, float]]:
    today = dt.date.today()
    step = max(1, days // max_points)
    dates = [(today - dt.timedelta(days=i)).isoformat() for i in range(days, 0, -step)]
    tags = dates + ["latest"]
    rows: dict[str, tuple[float, float]] = {}
    errors = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        for res in ex.map(lambda t: _safe(_currency_api_one, t), tags):
            if res is None:
                errors += 1
                continue
            date, jpy, gel = res
            rows[date] = (jpy, gel)
    if not rows:
        raise RuntimeError("currency-api: 全リクエスト失敗")
    if errors:
        print(f"[warn] currency-api: {errors}/{len(tags)} 件取得失敗", file=sys.stderr)
    return [(d, *rows[d]) for d in sorted(rows)]


def _safe(fn, *a):
    try:
        return fn(*a)
    except Exception:  # noqa: BLE001
        return None


def _yahoo_series(symbol: str, days: int) -> dict[str, float]:
    rng = "5d" if days <= 5 else "1mo" if days <= 31 else "3mo" if days <= 92 else \
          "6mo" if days <= 183 else "1y" if days <= 366 else "2y" if days <= 731 else "5y"
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={rng}&interval=1d"
    res = _get_json(url)["chart"]["result"][0]
    closes = res["indicators"]["quote"][0]["close"]
    out = {}
    for ts, c in zip(res["timestamp"], closes):
        if c is not None:
            out[dt.datetime.fromtimestamp(ts, dt.timezone.utc).date().isoformat()] = float(c)
    return out


def fetch_yahoo(days: int) -> list[tuple[str, float, float]]:
    jpy = _yahoo_series("JPY=X", days)   # USD/JPY
    gel = _yahoo_series("GEL=X", days)   # USD/GEL
    start = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    common = sorted(d for d in jpy.keys() & gel.keys() if d >= start)
    if not common:
        raise RuntimeError("yahoo: データなし")
    return [(d, jpy[d], gel[d]) for d in common]


def fetch(days: int) -> tuple[list[dict], str]:
    errors = []
    for name, fn in (("fawazahmed0/currency-api", fetch_currency_api), ("Yahoo Finance", fetch_yahoo)):
        try:
            raw = fn(days)
            return [to_row(d, j, g) for d, j, g in raw], name
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name}: {e}")
            print(f"[warn] {name} 失敗: {e}", file=sys.stderr)
    raise SystemExit("全データソースで取得に失敗しました:\n  " + "\n  ".join(errors))


def to_row(date: str, usdjpy: float, usdgel: float) -> dict:
    return {"date": date, "USDJPY": usdjpy, "GELJPY": usdjpy / usdgel, "USDGEL": usdgel}


# ---------------------------------------------------------------- csv
def write_csv(rows: list[dict], path: Path) -> None:
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "USDJPY", "GELJPY", "USDGEL"])
        w.writeheader()
        for r in rows:
            w.writerow({k: (f"{v:.4f}" if isinstance(v, float) else v) for k, v in r.items()})


def read_csv(path: Path) -> list[dict]:
    with path.open() as f:
        out = []
        for r in csv.DictReader(f):
            row = {"date": r["date"], "USDJPY": float(r["USDJPY"]), "USDGEL": float(r["USDGEL"])}
            row["GELJPY"] = float(r.get("GELJPY") or row["USDJPY"] / row["USDGEL"])
            out.append(row)
        return sorted(out, key=lambda x: x["date"])


# ---------------------------------------------------------------- stats
def stats(rows: list[dict], key: str) -> dict:
    vals = [r[key] for r in rows]
    first, last = vals[0], vals[-1]
    hi = max(range(len(vals)), key=vals.__getitem__)
    lo = min(range(len(vals)), key=vals.__getitem__)
    return {
        "first": first, "last": last, "change": last - first,
        "pct": (last / first - 1) * 100,
        "high": vals[hi], "high_date": rows[hi]["date"],
        "low": vals[lo], "low_date": rows[lo]["date"],
    }


# ---------------------------------------------------------------- svg/html
def _svg_panel(rows, key, title, color, events, w=880, h=300) -> str:
    pl, pr, pt, pb = 56, 16, 28, 34
    vals = [r[key] for r in rows]
    dates = [dt.date.fromisoformat(r["date"]) for r in rows]
    d0, d1 = dates[0], dates[-1]
    span = max((d1 - d0).days, 1)
    vmin, vmax = min(vals), max(vals)
    pad = (vmax - vmin) * 0.08 or vmax * 0.01
    vmin, vmax = vmin - pad, vmax + pad

    def x(d):
        return pl + (d - d0).days / span * (w - pl - pr)

    def y(v):
        return pt + (vmax - v) / (vmax - vmin) * (h - pt - pb)

    parts = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{html.escape(title)}">']
    # grid + y labels
    for i in range(5):
        v = vmin + (vmax - vmin) * i / 4
        yy = y(v)
        parts.append(f'<line class="grid" x1="{pl}" x2="{w-pr}" y1="{yy:.1f}" y2="{yy:.1f}"/>')
        parts.append(f'<text class="tick" x="{pl-6}" y="{yy+4:.1f}" text-anchor="end">{v:.2f}</text>')
    # x labels (~6)
    for i in range(6):
        d = d0 + dt.timedelta(days=round(span * i / 5))
        anchor = "start" if i == 0 else "end" if i == 5 else "middle"
        parts.append(f'<text class="tick" x="{x(d):.1f}" y="{h-10}" text-anchor="{anchor}">{d:%Y-%m-%d}</text>')
    # events
    for ev in events:
        try:
            ed = dt.date.fromisoformat(ev["date"])
        except (KeyError, ValueError):
            continue
        if d0 <= ed <= d1:
            xx = x(ed)
            label = html.escape(ev.get("label", ""))
            parts.append(f'<line class="ev" x1="{xx:.1f}" x2="{xx:.1f}" y1="{pt}" y2="{h-pb}"><title>{ev["date"]} {label}</title></line>')
    # line
    pts = " ".join(f"{x(d):.1f},{y(v):.1f}" for d, v in zip(dates, vals))
    parts.append(f'<polyline fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round" points="{pts}"/>')
    lx, ly = x(dates[-1]), y(vals[-1])
    parts.append(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="3.5" fill="{color}"/>')
    parts.append(f'<text class="last" x="{lx-6:.1f}" y="{ly-8:.1f}" text-anchor="end">{vals[-1]:.2f}</text>')
    # hover targets
    for d, v in zip(dates, vals):
        parts.append(f'<circle class="hit" cx="{x(d):.1f}" cy="{y(v):.1f}" r="6"><title>{d} : {v:.3f}</title></circle>')
    parts.append(f'<text class="ptitle" x="{pl}" y="18">{html.escape(title)}</text></svg>')
    return "".join(parts)


def _stat_html(name, s) -> str:
    sign = "+" if s["change"] >= 0 else ""
    cls = "up" if s["change"] >= 0 else "down"
    return (f'<div class="tile"><div class="lbl">{name}</div><div class="val">{s["last"]:.2f}<span>円</span></div>'
            f'<div class="chg {cls}">{sign}{s["change"]:.2f} ({sign}{s["pct"]:.2f}%)</div>'
            f'<div class="rng">高値 {s["high"]:.2f} ({s["high_date"]}) / 安値 {s["low"]:.2f} ({s["low_date"]})</div></div>')


def write_html(rows, path: Path, source: str, events: list[dict], summary: str) -> None:
    su, sg = stats(rows, "USDJPY"), stats(rows, "GELJPY")
    ev_html = ""
    if events:
        items = "".join(
            f'<li><time>{html.escape(e.get("date", ""))}</time> {html.escape(e.get("label", ""))}'
            + (f' <a href="{html.escape(e["url"])}" rel="noopener">出典</a>' if e.get("url") else "")
            + "</li>"
            for e in sorted(events, key=lambda e: e.get("date", ""))
        )
        ev_html = f"<h2>主なイベント</h2><ul class='ev'>{items}</ul>"
    summary_html = f"<p class='summary'>{html.escape(summary)}</p>" if summary else ""
    doc = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ドル円・ラリ円推移</title>
<style>
:root{{--bg:#fff;--fg:#1f2328;--mut:#656d76;--grid:#e6e8eb;--usd:#2f6fdb;--gel:#c2410c;--up:#1a7f37;--down:#cf222e;--card:#f6f8fa}}
@media (prefers-color-scheme:dark){{:root:not([data-theme=light]){{--bg:#0d1117;--fg:#e6edf3;--mut:#8b949e;--grid:#262c33;--usd:#6ea8fe;--gel:#fb923c;--up:#3fb950;--down:#f85149;--card:#161b22}}}}
:root[data-theme=dark]{{--bg:#0d1117;--fg:#e6edf3;--mut:#8b949e;--grid:#262c33;--usd:#6ea8fe;--gel:#fb923c;--up:#3fb950;--down:#f85149;--card:#161b22}}
body{{background:var(--bg);color:var(--fg);font-family:system-ui,-apple-system,"Hiragino Sans","Noto Sans JP",sans-serif;margin:0 auto;max-width:920px;padding:16px}}
h1{{font-size:1.4rem;margin:.2em 0}} h2{{font-size:1.1rem;margin-top:1.6em}}
.meta,.rng,.tick{{color:var(--mut);fill:var(--mut);font-size:12px}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin:12px 0}}
.tile{{background:var(--card);border-radius:10px;padding:12px 14px}} .lbl{{color:var(--mut);font-size:13px}}
.val{{font-size:1.8rem;font-weight:600;font-variant-numeric:tabular-nums}} .val span{{font-size:.9rem;margin-left:2px}}
.chg{{font-variant-numeric:tabular-nums}} .up{{color:var(--up)}} .down{{color:var(--down)}}
svg{{width:100%;height:auto;display:block;margin:8px 0}} .grid{{stroke:var(--grid)}} .ptitle{{fill:var(--fg);font-weight:600;font-size:14px}}
.last{{fill:var(--fg);font-size:12px;font-weight:600}} .ev{{stroke:var(--mut);stroke-dasharray:3 3}} .hit{{fill:transparent}} .hit:hover{{fill:var(--mut);opacity:.4}}
ul.ev{{padding-left:1.1em}} ul.ev li{{margin:.3em 0}} time{{color:var(--mut);font-variant-numeric:tabular-nums;margin-right:.4em}}
.summary{{line-height:1.7}} a{{color:var(--usd)}}
</style></head><body>
<h1>ドル円・ラリ円 推移</h1>
<div class="meta">期間 {rows[0]["date"]} 〜 {rows[-1]["date"]} ・ データ: {html.escape(source)} ・ 生成 {dt.datetime.now():%Y-%m-%d %H:%M}</div>
<div class="tiles">{_stat_html("USD/JPY (1ドル)", su)}{_stat_html("GEL/JPY (1ラリ)", sg)}</div>
{summary_html}
{_svg_panel(rows, "USDJPY", "USD/JPY（円/ドル）", "var(--usd)", events)}
{_svg_panel(rows, "GELJPY", "GEL/JPY（円/ラリ）", "var(--gel)", events)}
{ev_html}
<p class="meta">GEL/JPY は USD/JPY ÷ USD/GEL のクロスレートで算出。参考値であり投資判断には公式レート（日銀・ジョージア国立銀行 NBG 等）を確認してください。</p>
</body></html>"""
    path.write_text(doc, encoding="utf-8")


def write_png(rows, path: Path, events) -> bool:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
    except ImportError:
        print("[warn] matplotlib が無いため PNG はスキップ", file=sys.stderr)
        return False
    dates = [dt.date.fromisoformat(r["date"]) for r in rows]
    fig, axes = plt.subplots(2, 1, figsize=(10, 6.5), sharex=True)
    for ax, key, title, c in ((axes[0], "USDJPY", "USD/JPY", "#2f6fdb"), (axes[1], "GELJPY", "GEL/JPY", "#c2410c")):
        ax.plot(dates, [r[key] for r in rows], color=c, lw=1.8)
        ax.set_title(title, loc="left", fontsize=11)
        ax.grid(alpha=.3)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for ev in events:
            try:
                ed = dt.date.fromisoformat(ev["date"])
            except (KeyError, ValueError):
                continue
            if dates[0] <= ed <= dates[-1]:
                ax.axvline(ed, color="gray", ls=":", lw=1)
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return True


# ---------------------------------------------------------------- main
def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--days", type=int, default=365, help="遡る日数 (default: 365)")
    p.add_argument("--out", default="fx_out", help="出力ディレクトリ")
    p.add_argument("--from-csv", help="取得せず既存 CSV から描画")
    p.add_argument("--events", help='イベント JSON: [{"date":"YYYY-MM-DD","label":"...","url":"..."}]')
    p.add_argument("--summary", default="", help="グラフ上部に載せる解説文")
    p.add_argument("--png", action="store_true", help="matplotlib で PNG も出力")
    a = p.parse_args(argv)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.from_csv:
        rows, source = read_csv(Path(a.from_csv)), f"CSV ({Path(a.from_csv).name})"
    else:
        rows, source = fetch(a.days)
    if len(rows) < 2:
        raise SystemExit("データ点が不足しています")
    events = json.loads(Path(a.events).read_text(encoding="utf-8")) if a.events else []

    csv_path = out / "fx_jpy.csv"
    if not a.from_csv or Path(a.from_csv).resolve() != csv_path.resolve():
        write_csv(rows, csv_path)
    write_html(rows, out / "fx_jpy.html", source, events, a.summary)
    made_png = a.png and write_png(rows, out / "fx_jpy.png", events)

    su, sg = stats(rows, "USDJPY"), stats(rows, "GELJPY")
    print(json.dumps({
        "source": source, "period": [rows[0]["date"], rows[-1]["date"]], "points": len(rows),
        "USDJPY": su, "GELJPY": sg, "USDGEL_last": rows[-1]["USDGEL"],
        "files": [str(csv_path), str(out / "fx_jpy.html")] + ([str(out / "fx_jpy.png")] if made_png else []),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
