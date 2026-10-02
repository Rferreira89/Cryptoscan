"""Descarrega o historico de velas de 4H (Binance spot, USDT) dos ativos
listados na Bybit UE. As velas diarias sao derivadas das de 4H no backtest.
Uso: python -m tools.fetch_history <pasta>
"""
import csv
import gzip
import os
import sys
import time

from engine import sources, venue

START_MS = 1609459200000          # 2021-01-01
TF_MS = 14400000


def history(base):
    out, start = [], START_MS
    while True:
        d = sources._get("https://data-api.binance.vision/api/v3/klines",
                         {"symbol": base + "USDT", "interval": "4h",
                          "startTime": start, "limit": 1000})
        if not d:
            break
        out += d
        if len(d) < 1000:
            break
        start = d[-1][0] + TF_MS
        time.sleep(0.15)
    return out


def main(out):
    os.makedirs(out, exist_ok=True)
    listed = sorted(venue.fetch("USDC"))
    report = []
    for base in listed:
        try:
            rows = history(base)
        except sources.SourceError as e:
            report.append(f"{base}: sem dados na Binance ({str(e)[:60]})")
            continue
        if len(rows) < 500:
            report.append(f"{base}: historico curto ({len(rows)} velas)")
            continue
        with gzip.open(os.path.join(out, base + ".csv.gz"), "wt", newline="") as f:
            w = csv.writer(f)
            for r in rows:      # t(s), o, h, l, c, volume, volume comprador
                w.writerow([r[0] // 1000, r[1], r[2], r[3], r[4], r[5], r[9]])
        report.append(f"{base}: {len(rows)} velas")
    with open(os.path.join(out, "relatorio.txt"), "w") as f:
        f.write("\n".join(report) + "\n")
    print("\n".join(report))


if __name__ == "__main__":
    main(sys.argv[1])
