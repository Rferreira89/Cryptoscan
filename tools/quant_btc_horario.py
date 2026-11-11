"""(10/11) Precos horarios do BTC (fecho de cada hora, BTCUSDT da Binance publica, sem chaves) entre duas datas, para a
analise residual. So leitura de mercado publico. Uso: python3 tools/quant_btc_horario.py <desde_s> <ate_s> <saida.json>"""
import json
import sys
import time
import urllib.request

URL = "https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=1000&startTime={}"


def baixar(desde, ate):
    pts, t = [], int(desde) * 1000
    while t < int(ate) * 1000:
        with urllib.request.urlopen(URL.format(t), timeout=20) as r:
            k = json.load(r)
        if not k:
            break
        pts += [[x[6] // 1000, float(x[4])] for x in k]          # hora de fecho, preco de fecho
        t = k[-1][6] + 1
        time.sleep(0.2)
    return pts


if __name__ == "__main__":
    d, a, s = sys.argv[1:4]
    p = baixar(int(d), int(a))
    json.dump(p, open(s, "w"))
    print(f"{len(p)} horas de BTC")
