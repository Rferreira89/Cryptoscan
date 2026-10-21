"""D5 da auditoria (OK do Rui, 21/10): historico de 4H das moedas que deixaram
de negociar na Binance desde 2021 (delistadas), para os testes deixarem de ter
vies de sobrevivencia: hoje so se testa com moedas que sobreviveram.

Fonte gratuita: arquivos mensais publicos de data.binance.vision (ficam la
mesmo depois de a moeda sair). Lista de pares: o indice publico do arquivo
(S3) e, de reserva, os pares USDT com estado diferente de TRADING na
exchangeInfo da Binance.

Saida: <pasta>/<BASE>.csv.gz com t(s), o, h, l, c, volume, volume comprador
(o mesmo formato de tools/fetch_history) e <pasta>/indice.json com o primeiro
e o ultimo dia de cada moeda.
Uso: python -m tools.fetch_delistadas <pasta>
"""
import csv
import gzip
import io
import json
import os
import re
import sys
import time
import urllib.request
import zipfile

S3 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
ARQ = "https://data.binance.vision/data/spot/monthly/klines/{s}/4h/{s}-4h-{y:04d}-{m:02d}.zip"
INFO = "https://data-api.binance.vision/api/v3/exchangeInfo"
DESDE = (2021, 1)
# tokens alavancados, estaveis e pares que nao sao moedas
FORA = re.compile(r"(UP|DOWN|BULL|BEAR)USDT$")
ESTAVEIS = {"USDC", "BUSD", "TUSD", "USDP", "DAI", "FDUSD", "PAX", "SUSD", "UST", "USDS", "EUR", "GBP", "AUD", "TRY"}


def _get(url, timeout=30):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


def simbolos_arquivo():
    """Todos os pares com velas mensais no arquivo publico (indice S3)."""
    out, marker = set(), ""
    for _ in range(50):
        url = f"{S3}?delimiter=/&prefix=data/spot/monthly/klines/" + (f"&marker={marker}" if marker else "")
        xml = _get(url).decode()
        pref = re.findall(r"<Prefix>data/spot/monthly/klines/([A-Z0-9]+)/</Prefix>", xml)
        out.update(pref)
        if "<IsTruncated>true</IsTruncated>" not in xml or not pref:
            break
        marker = f"data/spot/monthly/klines/{pref[-1]}/"
    return out


def estado_atual():
    """{par: estado} da exchangeInfo (TRADING = ainda negociado)."""
    d = json.loads(_get(INFO, 60))
    return {s["symbol"]: s.get("status") for s in d.get("symbols") or []}


def candidatas(arquivo, estados):
    """Pares USDT do arquivo que ja nao estao em TRADING (ou nem aparecem)."""
    out = []
    for s in sorted(arquivo | {k for k, v in estados.items() if v != "TRADING"}):
        if not s.endswith("USDT") or FORA.search(s):
            continue
        base = s[:-4]
        if not base or base in ESTAVEIS or estados.get(s) == "TRADING":
            continue
        out.append(s)
    return out


def linhas_zip(raw):
    """Linhas de velas de um zip mensal; aceita tempos em ms ou em microssegundos (2025+)."""
    z = zipfile.ZipFile(io.BytesIO(raw))
    out = []
    for name in z.namelist():
        for row in csv.reader(io.TextIOWrapper(z.open(name))):
            try:
                t = int(row[0])
            except (ValueError, IndexError):
                continue                       # cabecalho
            t = t // 1000 if t > 10 ** 14 else t
            out.append([t // 1000, row[1], row[2], row[3], row[4], row[5], row[9]])
    return out


def meses(fim):
    y, m = DESDE
    while (y, m) <= fim:
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


def baixar(sym, fim):
    rows, falhas = [], 0
    for y, m in meses(fim):
        try:
            rows += linhas_zip(_get(ARQ.format(s=sym, y=y, m=m)))
            falhas = 0
        except Exception:
            falhas += 1
            if rows and falhas >= 3:          # 3 meses seguidos sem ficheiro depois de ter dados: saiu
                break
        time.sleep(0.05)
    rows = sorted({r[0]: r for r in rows}.values())
    return rows


def main(pasta):
    os.makedirs(pasta, exist_ok=True)
    try:
        arquivo = simbolos_arquivo()
    except Exception as e:
        print("indice do arquivo indisponivel:", e, file=sys.stderr)
        arquivo = set()
    estados = estado_atual()
    cand = candidatas(arquivo, estados)
    t = time.gmtime()
    fim = (t.tm_year, t.tm_mon - 1) if t.tm_mon > 1 else (t.tm_year - 1, 12)
    print(f"{len(arquivo)} pares no arquivo · {len(cand)} candidatos delistados")
    indice = {}
    for sym in cand:
        rows = baixar(sym, fim)
        if len(rows) < 6 * 60:                # menos de 2 meses de velas: nao serve
            continue
        base = sym[:-4]
        with gzip.open(os.path.join(pasta, f"{base}.csv.gz"), "wt", newline="") as f:
            csv.writer(f).writerows(rows)
        indice[base] = {"de": rows[0][0], "ate": rows[-1][0], "velas": len(rows), "estado": estados.get(sym, "fora da lista")}
        print(f"{base}: {len(rows)} velas")
    with open(os.path.join(pasta, "indice.json"), "w") as f:
        json.dump({"gerado": int(time.time()), "moedas": indice}, f, indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
