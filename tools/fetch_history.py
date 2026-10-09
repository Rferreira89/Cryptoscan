"""Descarrega o historico de velas (Binance spot, USDT) dos ativos listados
na Bybit UE: 4H desde 2021 na raiz da pasta e 1H dos ultimos 25 meses na
subpasta 1h/ (para a investigacao de day trade). As velas diarias sao
derivadas das de 4H no backtest.
Uso: python -m tools.fetch_history <pasta>
"""
import csv
import gzip
import os
import sys
import time

from engine import sources, venue

START_MS = 1609459200000          # 2021-01-01
TF_MS = {"4h": 14400000, "1h": 3600000}
START_1H_DAYS = 760               # ~25 meses: a janela da investigacao e 24


def history(base, interval="4h", start_ms=START_MS):
    out, start = [], start_ms
    while True:
        d = sources._get("https://data-api.binance.vision/api/v3/klines",
                         {"symbol": base + "USDT", "interval": interval,
                          "startTime": start, "limit": 1000})
        if not d:
            break
        out += d
        if len(d) < 1000:
            break
        start = d[-1][0] + TF_MS[interval]
        time.sleep(0.15)
    return out


def write(path, rows):
    with gzip.open(path, "wt", newline="") as f:
        w = csv.writer(f)
        for r in rows:      # t(s), o, h, l, c, volume, volume comprador
            w.writerow([r[0] // 1000, r[1], r[2], r[3], r[4], r[5], r[9]])


def main(out):
    os.makedirs(os.path.join(out, "1h"), exist_ok=True)
    listed = sorted(venue.fetch("USDC"))
    report = []
    start_1h = (int(time.time()) - START_1H_DAYS * 86400) * 1000
    for base in listed:
        try:
            rows = history(base)
        except sources.SourceError as e:
            report.append(f"{base}: sem dados na Binance ({str(e)[:60]})")
            continue
        if len(rows) < 500:
            report.append(f"{base}: historico curto ({len(rows)} velas)")
            continue
        write(os.path.join(out, base + ".csv.gz"), rows)
        try:
            h1 = history(base, "1h", start_1h)
        except sources.SourceError:
            h1 = []
        if len(h1) >= 2000:
            write(os.path.join(out, "1h", base + ".csv.gz"), h1)
        report.append(f"{base}: {len(rows)} velas de 4H, {len(h1)} de 1H")
    with open(os.path.join(out, "relatorio.txt"), "w") as f:
        f.write("\n".join(report) + "\n")
    print("\n".join(report))


if __name__ == "__main__":
    main(sys.argv[1])
