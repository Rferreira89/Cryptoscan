"""Arquivo gratuito e incremental de dados de derivados dos X-Perps da OKX (so endpoints publicos, sem chaves).

Corre dentro do papel continuo (uma fotografia por volta de 30 min; funding, fluxo comprador/vendedor e
profundidade so de hora a hora). Cada linha tem a hora real da leitura, o instrumento, a fonte e o tipo
(instantaneo). NUNCA preenche periodos sem leitura: cada falha e cada buraco entre leituras fica em lacunas.json.

Ficheiros (ramo autonomo): hunter/derivados/AAAA-MM-DD.csv.gz (append) e hunter/derivados/lacunas.json.
Disponibilidade por endpoint fica registada (alguns podem nao existir para X-Perps: fica escrito, nao inventado).
"""
import csv
import gzip
import io
import json
import os
import time

from tools.hunter import dados as DD

COLS = ["t", "fonte", "inst", "base", "tipo", "last", "vol24h_contratos", "oi_contratos", "oi_usd", "bid", "ask",
        "spread_pct", "funding_taxa", "funding_proximo_t", "taker_compra", "taker_venda", "prof_bid_05pct_usd",
        "prof_ask_05pct_usd"]
INTERVALO_MAX = 45 * 60


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def fotografia(uni, now, request=DD.get, completa=True, workers=6):
    """{inst: linha} + disponibilidade por endpoint."""
    from concurrent.futures import ThreadPoolExecutor
    disp = {}
    tick = request("/api/v5/market/tickers", {"instType": "FUTURES"})
    disp["tickers"] = tick is not None
    oi = request("/api/v5/public/open-interest", {"instType": "FUTURES"})
    disp["open_interest"] = oi is not None
    tick = {t["instId"]: t for t in tick or []}
    oi = {x["instId"]: x for x in oi or []}
    linhas = {}
    for b, i in uni.items():
        t, o = tick.get(i["inst"]) or {}, oi.get(i["inst"]) or {}
        bid, ask = _f(t.get("bidPx")), _f(t.get("askPx"))
        linhas[i["inst"]] = {"t": int(now), "fonte": "okx-publico", "inst": i["inst"], "base": b, "tipo": "instantaneo",
                             "last": _f(t.get("last")), "vol24h_contratos": _f(t.get("vol24h")),
                             "oi_contratos": _f(o.get("oi")), "oi_usd": _f(o.get("oiUsd")), "bid": bid, "ask": ask,
                             "spread_pct": round(100 * (ask - bid) / ((ask + bid) / 2), 5) if bid and ask else None}
    if completa:
        def extra(b):
            i = uni[b]
            out = {}
            f = request("/api/v5/public/funding-rate", {"instId": i["inst"]})
            if f:
                out.update(funding_taxa=_f(f[0].get("fundingRate")), funding_proximo_t=int(_f(f[0].get("fundingTime")) or 0) // 1000)
            tv = request("/api/v5/rubik/stat/taker-volume-contract", {"instId": i["inst"], "period": "1H", "limit": 1})
            if tv:
                try:
                    out.update(taker_compra=_f(tv[0][2]), taker_venda=_f(tv[0][1]))
                except (IndexError, TypeError):
                    pass
            if i.get("tier") in ("A", "B") or (i.get("vol24h_usd") or 0) >= 5e5:
                bk = request("/api/v5/market/books", {"instId": i["inst"], "sz": 50})
                if bk:
                    mid = linhas[i["inst"]]
                    if mid.get("bid") and mid.get("ask"):
                        m = (mid["bid"] + mid["ask"]) / 2
                        ctv = i.get("ctVal") or 0
                        conv = m if (i.get("ctValCcy") or "").upper() != "USD" else 1
                        out["prof_bid_05pct_usd"] = round(sum(_f(x[1]) * ctv * conv for x in bk[0].get("bids", [])
                                                              if _f(x[0]) >= m * 0.995), 2)
                        out["prof_ask_05pct_usd"] = round(sum(_f(x[1]) * ctv * conv for x in bk[0].get("asks", [])
                                                              if _f(x[0]) <= m * 1.005), 2)
            return i["inst"], out, bool(f), bool(tv)
        with ThreadPoolExecutor(max_workers=workers) as ex:
            got = list(ex.map(extra, sorted(uni)))
        for inst, out, okf, okt in got:
            linhas[inst].update(out)
        disp["funding_rate"] = sum(1 for g in got if g[2])
        disp["taker_volume"] = sum(1 for g in got if g[3])
    return linhas, disp


def arquivar(pasta, linhas, disp, now):
    """Acrescenta ao ficheiro do dia (nunca reescreve leituras antigas) e regista lacunas."""
    d = os.path.join(pasta, "hunter", "derivados")
    os.makedirs(d, exist_ok=True)
    dia = time.strftime("%Y-%m-%d", time.gmtime(now))
    p = os.path.join(d, f"{dia}.csv.gz")
    antigo = b""
    if os.path.exists(p):
        with gzip.open(p, "rb") as f:
            antigo = f.read()
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLS)
    if not antigo:
        w.writeheader()
    for l in linhas.values():
        w.writerow({c: l.get(c) for c in COLS})
    with gzip.open(p, "wb") as f:
        f.write(antigo + buf.getvalue().encode())
    pl = os.path.join(d, "lacunas.json")
    lac = {"ultima_leitura": None, "lacunas": [], "disponibilidade": {}}
    if os.path.exists(pl):
        with open(pl, encoding="utf-8") as f:
            lac = json.load(f)
    if lac.get("ultima_leitura") and now - lac["ultima_leitura"] > INTERVALO_MAX:
        lac["lacunas"].append({"de": lac["ultima_leitura"], "ate": int(now), "minutos": (now - lac["ultima_leitura"]) // 60})
    for k, v in disp.items():
        lac["disponibilidade"][k] = v
    if not disp.get("tickers") or not disp.get("open_interest"):
        lac["lacunas"].append({"de": int(now), "ate": int(now), "motivo": f"endpoint em falha: {disp}"})
    lac["ultima_leitura"] = int(now)
    lac["nota"] = "lacunas nunca sao preenchidas: os periodos sem leitura ficam sem dados"
    with open(pl, "w", encoding="utf-8") as f:
        json.dump(lac, f, ensure_ascii=False, indent=0)
    return p
