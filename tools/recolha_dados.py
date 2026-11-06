"""(05/11, L1, preparacao isolada; NAO ATIVO) Recolha diaria de dados NOVOS para a investigacao futura (LONG, SHORT,
revercoes, laterais), so com APIs publicas e sem chaves. Regra do Rui: nenhuma hipotese volta a ser testada nos dados
ja usados; cada hipotese e registada (hipoteses.json) ANTES de ser avaliada e so conta com dados recolhidos DEPOIS da
data de registo.

Uma linha por moeda e por dia (vela diaria UTC fechada do perpetuo global da OKX), em <pasta>/AAAA-MM.csv:
data, moeda, validado (volume a vista da Binance >= 20 M), o, h, l, c, volume_usd, px_xperp, px_global,
fund_xperp_24h, oi_usd_global, oi_xperp. Incremental e idempotente (a mesma data e moeda nao se repete)."""
import csv
import json
import os
import time

import okx_tfshort as T

CAMPOS = ["data", "moeda", "validado", "o", "h", "l", "c", "volume_usd", "px_xperp", "px_global",
          "fund_xperp_24h", "oi_usd_global", "oi_xperp"]
DAY = 86400


def linhas(dados, oi_global, oi_xperp, infos, agora):
    """Linhas da ultima vela diaria FECHADA de cada moeda (a de ontem em UTC)."""
    ontem = (int(agora) // DAY - 1) * DAY
    out = []
    for a in sorted(dados):
        d = dados[a]
        v = [x for x in d.get("velas") or [] if x["t"] == ontem]
        if not v:
            continue
        v = v[0]
        fu = sum(x for t, x in d.get("fund") or [] if ontem < t <= ontem + DAY)
        out.append({"data": time.strftime("%Y-%m-%d", time.gmtime(ontem)), "moeda": a,
                    "validado": "" if d.get("validado") is None else int(bool(d.get("validado"))),
                    "o": v["o"], "h": v["h"], "l": v["l"], "c": v["c"], "volume_usd": round(v.get("usd", 0), 2),
                    "px_xperp": d.get("px") or "", "px_global": d.get("px_global") or "",
                    "fund_xperp_24h": round(fu, 8), "oi_usd_global": oi_global.get(a, ""),
                    "oi_xperp": oi_xperp.get((infos.get(a) or {}).get("inst"), "")})
    return out


def gravar(pasta, novas):
    """Acrescenta ao ficheiro do mes, sem repetir (data, moeda). Devolve quantas linhas entraram."""
    os.makedirs(pasta, exist_ok=True)
    n = 0
    por_mes = {}
    for r in novas:
        por_mes.setdefault(r["data"][:7], []).append(r)
    for mes, rs in por_mes.items():
        f = os.path.join(pasta, f"{mes}.csv")
        tem = set()
        if os.path.exists(f):
            with open(f, newline="") as fh:
                tem = {(x["data"], x["moeda"]) for x in csv.DictReader(fh)}
        novo = not os.path.exists(f)
        with open(f, "a", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=CAMPOS)
            if novo:
                w.writeheader()
            for r in rs:
                if (r["data"], r["moeda"]) not in tem:
                    w.writerow(r); tem.add((r["data"], r["moeda"])); n += 1
    return n


def dados_para_avaliar(pasta, registada_em):
    """So as linhas com data POSTERIOR ao registo da hipotese (nunca antes)."""
    out = []
    for f in sorted(os.listdir(pasta)) if os.path.isdir(pasta) else []:
        if f.endswith(".csv"):
            with open(os.path.join(pasta, f), newline="") as fh:
                out += [r for r in csv.DictReader(fh) if r["data"] > registada_em]
    return out


def oi_publico(inst_type):
    out = {}
    for x in T._get(f"/api/v5/public/open-interest?instType={inst_type}"):
        try:
            out[x["instId"]] = round(float(x.get("oiUsd") or 0), 2)
        except (KeyError, ValueError):
            pass
    return out


def main(pasta):
    agora = time.time()
    dados, infos = T.recolher()
    swap = oi_publico("SWAP")
    oi_g = {k.split("-")[0]: v for k, v in swap.items() if k.endswith("-USDT-SWAP")}
    oi_x = oi_publico("FUTURES")
    rs = linhas(dados, oi_g, oi_x, infos, agora)
    n = gravar(pasta, rs)
    print(json.dumps({"moedas": len(dados), "linhas_novas": n, "com_oi": sum(1 for r in rs if r["oi_usd_global"] != "")}))
    return 0 if rs else 1


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/dados-novos"))
