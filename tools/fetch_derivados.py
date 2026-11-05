"""(05/11, OK do Rui: "Autorizo") Fase 1 do plano de expansao das estrategias: historico publico de derivados
(open interest e racios long/short) para testar a familia funding + OI + liquidacoes sem esperar meses.

Fonte gratuita: arquivos diarios de data.binance.vision, futuros USDT-M, "metrics" (linhas de 5 em 5 minutos desde
finais de 2021): create_time, symbol, sum_open_interest, sum_open_interest_value, count_toptrader_long_short_ratio,
sum_toptrader_long_short_ratio, count_long_short_ratio, sum_taker_long_short_vol_ratio.
Saida (agregada em velas de 4H, como o resto do historico): <pasta>/metrics/<BASE>.csv.gz com
t(s), oi (contratos, ultimo da vela), oi_usd (ultimo), ls_top (media do racio dos maiores traders por contas),
ls_contas (media do racio long/short por contas), taker (media do racio compra/venda agressiva).
Incremental: so descarrega os dias que faltam (a pasta pode vir do ramo "derivados" ja publicado).
So dados: nao mexe em nada do que opera. Uso: python -m tools.fetch_derivados <pasta> <BASE> [<BASE> ...]
"""
import calendar
import csv
import gzip
import io
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

URL = "https://data.binance.vision/data/futures/um/daily/metrics/{s}/{s}-metrics-{d}.zip"
DESDE = date(2021, 12, 1)
H4 = 14400
LIMITE_S = int(os.environ.get("DERIVADOS_LIMITE_S", 5 * 3600))


def _dia(sym, d):
    try:
        with urllib.request.urlopen(URL.format(s=sym, d=d.isoformat()), timeout=30) as r:
            z = zipfile.ZipFile(io.BytesIO(r.read()))
    except urllib.error.HTTPError as e:
        return d, (None if e.code == 404 else "erro")
    except Exception:
        return d, "erro"
    linhas = []
    for row in csv.reader(io.TextIOWrapper(z.open(z.namelist()[0]))):
        if not row or not row[0][:1].isdigit():
            continue
        linhas.append(row)
    return d, linhas


def agrega(linhas):
    """{t4h: [oi, oi_usd, ls_top_soma, ls_contas_soma, taker_soma, n]} a partir das linhas de 5 minutos."""
    out = {}
    for row in linhas:
        try:
            ts = row[0]
            t = calendar.timegm(time.strptime(ts[:19], "%Y-%m-%d %H:%M:%S")) if "-" in ts else int(float(ts) / 1000)
            oi, oiu = float(row[2] or 0), float(row[3] or 0)
            top, contas, tk = float(row[5] or 0), float(row[6] or 0), float(row[7] or 0)
        except (ValueError, IndexError):
            continue
        k = t // H4 * H4
        v = out.setdefault(k, [0.0, 0.0, 0.0, 0.0, 0.0, 0, -1])
        if t >= v[6]:
            v[0], v[1], v[6] = oi, oiu, t
        v[2] += top; v[3] += contas; v[4] += tk; v[5] += 1
    return out


def ler(caminho):
    if not os.path.exists(caminho):
        return {}
    with gzip.open(caminho, "rt") as f:
        return {int(r[0]): r for r in csv.reader(f) if r and r[0].isdigit()}


def moeda(pasta, base, fim, t0):
    sym = f"{base}USDT"
    caminho = os.path.join(pasta, "metrics", f"{base}.csv.gz")
    tem = ler(caminho)
    ult = date.fromtimestamp(max(tem) + 86400) if tem else DESDE
    dias = [ult + timedelta(n) for n in range((fim - ult).days + 1)]
    if not dias:
        return base, 0, len(tem)
    novos, falhas = {}, 0
    with ThreadPoolExecutor(12) as ex:
        for d, linhas in ex.map(lambda d: _dia(sym, d), dias):
            if linhas == "erro":
                falhas += 1
            elif linhas:
                for k, v in agrega(linhas).items():
                    if v[5]:
                        novos[k] = [str(k), f"{v[0]:.4f}", f"{v[1]:.2f}", f"{v[2] / v[5]:.4f}", f"{v[3] / v[5]:.4f}", f"{v[4] / v[5]:.4f}"]
            if time.time() - t0 > LIMITE_S:
                break
    tem.update(novos)
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with gzip.open(caminho, "wt") as f:
        w = csv.writer(f)
        w.writerow(["t", "oi", "oi_usd", "ls_top", "ls_contas", "taker"])
        for k in sorted(tem):
            w.writerow(tem[k])
    return base, len(novos), falhas


def main(pasta, bases):
    t0 = time.time()
    fim = date.today() - timedelta(1)
    for base in bases:
        if time.time() - t0 > LIMITE_S:
            print("limite de tempo: continua na proxima execucao")
            break
        b, n, f = moeda(pasta, base, fim, t0)
        print(f"{b}: {n} velas de 4H novas, {f} dias com erro", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2:]))
