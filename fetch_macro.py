"""
fetch_macro.py — собирает макро-данные для BTC-терминала.
Сейчас фокус на ETF FLOWS (Farside Investors).
Запускается раз в сутки через GitHub Actions, пишет macro.json.

Стратегия: Playwright headless Chromium + playwright-stealth для маскировки.
Ожидаем не просто <table>, а конкретный текст 'IBIT' — иначе Cloudflare
отдаст интерстишал страницу с пустой структурой.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

# --- Settings ---
FARSIDE_URL = "https://farside.co.uk/btc/"
TIMEOUT_MS = 60000
OUT_FILE = Path(__file__).parent / "macro.json"
DEBUG_FILE = Path(__file__).parent / "debug.html"

ETF_NAMES = {
    "IBIT": "BlackRock iShares",
    "FBTC": "Fidelity Wise Origin",
    "BITB": "Bitwise Bitcoin",
    "ARKB": "ARK 21Shares",
    "BTCO": "Invesco Galaxy",
    "EZBC": "Franklin",
    "BRRR": "Valkyrie",
    "HODL": "VanEck",
    "BTCW": "WisdomTree",
    "GBTC": "Grayscale Trust",
    "BTC":  "Grayscale Mini Trust",
}


def parse_value(raw):
    if raw is None:
        return 0.0
    s = str(raw).strip().replace(",", "").replace("$", "")
    if s in ("", "-", "—", "N/A", "n/a"):
        return 0.0
    if s.startswith("(") and s.endswith(")"):
        try:
            return -float(s[1:-1])
        except ValueError:
            return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_date(raw):
    s = str(raw).strip()
    for fmt in ("%d %b %Y", "%d %B %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def fetch_html():
    """Headless Chromium + stealth, ждём появление 'IBIT' в DOM."""
    from playwright.sync_api import sync_playwright
    try:
        from playwright_stealth import stealth_sync
        has_stealth = True
    except ImportError:
        has_stealth = False
        print("[warn] playwright-stealth не установлен, продолжаем без stealth")

    print("[fetch] Playwright headless Chromium" + (" + stealth" if has_stealth else ""))
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="America/New_York",
        )
        page = context.new_page()
        if has_stealth:
            try:
                stealth_sync(page)
            except Exception as e:
                print(f"[stealth_sync error] {e}")

        try:
            page.goto(FARSIDE_URL, wait_until="domcontentloaded", timeout=TIMEOUT_MS)
            print("[fetch] domcontentloaded — ждём networkidle...")
            try:
                page.wait_for_load_state("networkidle", timeout=20000)
            except Exception as e:
                print(f"[networkidle timeout] {e} — продолжаем")
            # Дополнительно ждём появления конкретного текста IBIT
            print("[fetch] ждём text=IBIT в DOM (макс 30 сек)...")
            try:
                page.wait_for_selector("text=IBIT", timeout=30000)
                print("[fetch] нашёл IBIT в DOM ✓")
            except Exception as e:
                print(f"[wait IBIT timeout] {e}")
            page.wait_for_timeout(2000)
            html = page.content()
            print(f"[fetch] HTML получен, {len(html)} chars")
        finally:
            browser.close()

    # Проверка: если в HTML нет IBIT — это интерстишал, сохраняем для отладки
    if "IBIT" not in html:
        try:
            DEBUG_FILE.write_text(html, encoding="utf-8")
            print(f"[debug] IBIT не найден, HTML сохранён в {DEBUG_FILE.name}")
        except Exception as e:
            print(f"[debug write error] {e}")
        raise RuntimeError("HTML не содержит 'IBIT' — Cloudflare challenge?")

    return html


def parse_table(html):
    soup = BeautifulSoup(html, "lxml")
    # Берём ВСЕ таблицы и выбираем ту в которой есть тикеры
    tables = soup.find_all("table")
    if not tables:
        raise RuntimeError("На странице нет ни одной <table>")

    table = None
    for t in tables:
        text = t.get_text()
        if "IBIT" in text and "FBTC" in text:
            table = t
            break
    if table is None:
        raise RuntimeError("Не нашёл таблицу с тикерами IBIT/FBTC")

    rows = table.find_all("tr")
    if len(rows) < 2:
        raise RuntimeError("В таблице меньше 2 строк")

    header_cells = []
    for r in rows[:5]:
        cells = [c.get_text(strip=True) for c in r.find_all(["th", "td"])]
        if cells and any(t in cells for t in ETF_NAMES):
            header_cells = cells
            break
    if not header_cells:
        header_cells = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]

    ticker_positions = {}
    for i, c in enumerate(header_cells):
        if c in ETF_NAMES:
            ticker_positions[c] = i

    if not ticker_positions:
        raise RuntimeError(f"Не нашёл ни одного тикера в headers: {header_cells}")

    headers_list = list(ticker_positions.keys())

    daily_rows = []
    for tr in rows:
        cells = [c.get_text(strip=True) for c in tr.find_all(["th", "td"])]
        if not cells:
            continue
        date_iso = parse_date(cells[0])
        if not date_iso:
            continue
        row = {"date": date_iso}
        for ticker, pos in ticker_positions.items():
            if pos < len(cells):
                row[ticker] = parse_value(cells[pos])
            else:
                row[ticker] = 0.0
        daily_rows.append(row)

    if not daily_rows:
        raise RuntimeError("Не извлёк ни одной строки с данными")

    daily_rows.sort(key=lambda r: r["date"])
    return headers_list, daily_rows


def compute_per_etf(headers, rows):
    if not rows:
        return []
    out = []
    last = rows[-1]
    last_30 = rows[-30:] if len(rows) >= 30 else rows
    last_7 = rows[-7:] if len(rows) >= 7 else rows
    ytd_rows = [r for r in rows if r["date"] >= "2024-01-01"]

    for ticker in headers:
        today = last.get(ticker, 0.0)
        sum_7d = sum(r.get(ticker, 0.0) for r in last_7)
        sum_30d = sum(r.get(ticker, 0.0) for r in last_30)
        sum_ytd = sum(r.get(ticker, 0.0) for r in ytd_rows)
        history_30 = [round(r.get(ticker, 0.0), 2) for r in last_30]
        out.append({
            "ticker": ticker,
            "name": ETF_NAMES.get(ticker, ticker),
            "today": round(today, 2),
            "sum7d": round(sum_7d, 2),
            "sum30d": round(sum_30d, 2),
            "sumYtd": round(sum_ytd, 2),
            "history30d": history_30,
        })
    return out


def compute_totals(rows):
    if not rows:
        return {"today": 0.0, "sum7d": 0.0, "sum30d": 0.0, "sumYtd": 0.0}
    last = rows[-1]
    last_7 = rows[-7:] if len(rows) >= 7 else rows
    last_30 = rows[-30:] if len(rows) >= 30 else rows
    ytd = [r for r in rows if r["date"] >= "2024-01-01"]

    def sum_row(r):
        return sum(v for k, v in r.items() if k != "date" and isinstance(v, (int, float)))

    return {
        "today": round(sum_row(last), 2),
        "sum7d": round(sum(sum_row(r) for r in last_7), 2),
        "sum30d": round(sum(sum_row(r) for r in last_30), 2),
        "sumYtd": round(sum(sum_row(r) for r in ytd), 2),
    }


def compute_signal(rows):
    if not rows:
        return {"consecutivePositiveDays": 0, "consecutiveNegativeDays": 0,
                "interpretation": "NO_DATA", "score": 0.0}

    def sum_row(r):
        return sum(v for k, v in r.items() if k != "date" and isinstance(v, (int, float)))

    daily_totals = [sum_row(r) for r in rows]

    consec_pos = 0
    consec_neg = 0
    for v in reversed(daily_totals):
        if v > 0 and consec_neg == 0:
            consec_pos += 1
        elif v < 0 and consec_pos == 0:
            consec_neg += 1
        else:
            break

    sum_7d = sum(daily_totals[-7:]) if len(daily_totals) >= 7 else sum(daily_totals)
    today = daily_totals[-1]

    if consec_pos >= 5 and sum_7d > 1000:
        interp, score = "INSTITUTIONAL_BULL", 0.50
    elif consec_pos >= 3 and sum_7d > 500:
        interp, score = "STRONG_INFLOW", 0.30
    elif consec_neg >= 5 and sum_7d < -1000:
        interp, score = "INSTITUTIONAL_BEAR", -0.50
    elif consec_neg >= 3 and sum_7d < -500:
        interp, score = "DISTRIBUTION", -0.30
    elif abs(sum_7d) < 200:
        interp, score = "CONSOLIDATION", 0.0
    elif sum_7d > 0:
        interp, score = "MILD_INFLOW", 0.10
    else:
        interp, score = "MILD_OUTFLOW", -0.10

    return {
        "consecutivePositiveDays": consec_pos,
        "consecutiveNegativeDays": consec_neg,
        "interpretation": interp,
        "score": score,
        "todayTotal": round(today, 2),
        "weekTotal": round(sum_7d, 2),
    }


def main():
    try:
        html = fetch_html()
    except Exception as e:
        print(f"[error] не удалось скачать Farside: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        headers, rows = parse_table(html)
        print(f"[parse] OK: {len(headers)} ETF, {len(rows)} дней истории")
    except Exception as e:
        print(f"[error] парсинг сломался: {e}", file=sys.stderr)
        # Сохраняем HTML для разбора
        try:
            DEBUG_FILE.write_text(html, encoding="utf-8")
            print(f"[debug] HTML сохранён в {DEBUG_FILE.name} для разбора", file=sys.stderr)
        except Exception:
            pass
        sys.exit(1)

    per_etf = compute_per_etf(headers, rows)
    totals = compute_totals(rows)
    signal = compute_signal(rows)

    payload = {
        "schema": "btc_terminal_macro",
        "version": 1,
        "updatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "farside.co.uk/btc",
        "etfFlows": {
            "totals": totals,
            "byEtf": per_etf,
            "signal": signal,
            "lastDate": rows[-1]["date"] if rows else None,
            "history": rows[-90:],
        },
    }

    OUT_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[write] {OUT_FILE} OK")


if __name__ == "__main__":
    main()
