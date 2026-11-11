"""(11/11) Global Opportunity Hunter em SOMBRA: junta as fontes publicas que o CryptoScan ja tem, classifica
oportunidades (engine/oportunidades.py) e grava um registo para avaliacao posterior. Sem autoridade de execucao:
nao escreve em nenhum estado de estrategia, nao chama corretoras privadas, nao envia ordens.

Fontes (todas publicas, ja recolhidas pelos workflows existentes):
  <hist>/*.csv.gz       velas de 4H (t, o, h, l, c, v, volume em moeda de cotacao), ramo history
  derivados.json        ramo data: OI, funding, long/short, liquidacoes, basis (21 moedas, de hora a hora)
  dados-novos CSV       ramo dados-novos: OHLC diario, volume, funding X-Perp, OI global e X-Perp (164 moedas)
  state.json            ramo data: regime por moeda; liquidez.json: spread da Bybit UE
As caracteristicas de velas sao calculadas pela MESMA funcao (`caracteristicas_velas`) na sombra e no estudo
historico (backtest/estudos/novos/cacador_ic_historico.py), para nao haver diferenca entre investigacao e sombra.
Uso: python3 tools/cacador_global.py <hist> <pasta_publica> <dados_novos.csv|-> <saida_dir> [estudo_ic.json ...]"""
import csv
import glob
import gzip
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from engine import oportunidades as OP  # noqa: E402

H4 = 14400


def ler_velas(caminho):
    out = []
    with gzip.open(caminho, "rt") as f:
        for ln in f:
            p = ln.strip().split(",")
            if len(p) >= 6:
                out.append((int(p[0]), float(p[1]), float(p[2]), float(p[3]), float(p[4]),
                            float(p[6]) if len(p) > 6 else float(p[5]) * float(p[4])))
    return out


def _ret(c, k, n):
    return c[k] / c[k - n] - 1 if k - n >= 0 and c[k - n] else None


def _dp(xs):
    if len(xs) < 3:
        return None
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _corr(a, b):
    n = len(a)
    if n < 10:
        return None
    ma, mb = sum(a) / n, sum(b) / n
    sa = math.sqrt(sum((x - ma) ** 2 for x in a))
    sb = math.sqrt(sum((x - mb) ** 2 for x in b))
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb) if sa and sb else None


def caracteristicas_velas(v, k, btc_por_t):
    """Caracteristicas de uma moeda na vela k (usa so velas 0..k). v: [(t, o, h, l, c, qv)]; btc_por_t: {t: c}."""
    if k < 360:
        return None
    c = [x[4] for x in v]
    r24 = [c[i] / c[i - 6] - 1 for i in range(k - 359, k + 1, 6)]              # 60 retornos de 24 h
    vol_d = _dp(r24)
    qv = [sum(x[5] for x in v[i - 5:i + 1]) for i in range(k - 120, k + 1, 6)]  # volume de 24 h, ~20 dias
    out = {"t": v[k][0], "preco": c[k], "ret_24h": _ret(c, k, 6), "ret_3d": _ret(c, k, 18), "atr_pct": vol_d,
           "log_volume": math.log(qv[-1]) if qv[-1] > 0 else None,
           "log_volume_hist": [math.log(q) for q in qv[:-1] if q > 0],
           "vol_ratio": qv[-1] / (sum(qv[:-1]) / len(qv[:-1])) if sum(qv[:-1]) else None}
    ra, rb = [], []
    for i in range(k - 359, k + 1):
        b0, b1 = btc_por_t.get(v[i - 1][0]), btc_por_t.get(v[i][0])
        if b0 and b1:
            ra.append(c[i] / c[i - 1] - 1)
            rb.append(b1 / b0 - 1)
    if len(rb) >= 60:
        vb = sum((x - sum(rb) / len(rb)) ** 2 for x in rb)
        cov = sum((x - sum(ra) / len(ra)) * (y - sum(rb) / len(rb)) for x, y in zip(ra, rb))
        out["beta_btc"] = cov / vb if vb else None
        out["corr_btc_60d"] = _corr(ra, rb)
        out["corr_btc_7d"] = _corr(ra[-42:], rb[-42:])
    b0, b1 = btc_por_t.get(v[k - 6][0]), btc_por_t.get(v[k][0])
    out["btc_ret_24h"] = b1 / b0 - 1 if b0 and b1 else None
    if out.get("beta_btc") is not None and out["ret_24h"] is not None and out["btc_ret_24h"] is not None:
        out["residual_btc_24h"] = out["ret_24h"] - out["beta_btc"] * out["btc_ret_24h"]
    return out


def derivados(D, ativo, now):
    m = (D.get("moedas") or {}).get(ativo)
    if not m:
        return {}
    campos = D.get("campos") or []
    linhas = [dict(zip(campos, r)) for r in m if r and r[0] <= now]
    if not linhas:
        return {}
    u = linhas[-1]
    hist = linhas[-24 * 21:-1]
    f = lambda x, d: None if x is None else x / d
    out = {"funding": f(u.get("funding_ppm"), 1e6), "funding_hist": [f(l.get("funding_ppm"), 1e6) for l in hist],
           "ls": f(u.get("ls_x100"), 100), "ls_hist": [f(l.get("ls_x100"), 100) for l in hist],
           "oi_chg_24h": f(u.get("oi_chg_24h_x100"), 1e4), "liq_long": u.get("liq_long_kusd"), "liq_short": u.get("liq_short_kusd"),
           "liq_total_hist": [((l.get("liq_long_kusd") or 0) + (l.get("liq_short_kusd") or 0)) if l.get("liq_long_kusd") is not None else None for l in hist],
           "idade_deriv_s": now - u["t"]}
    return out


def dados_novos(caminho):
    """{ativo: [linhas diarias]} do CSV do ramo dados-novos (validado = 1 ou 0, ambos guardados)."""
    out = {}
    if not caminho or caminho == "-" or not os.path.exists(caminho):
        return out
    for r in csv.DictReader(open(caminho)):
        out.setdefault(r["moeda"], []).append(r)
    return out


def painel(hist, pasta, dn_csv, now=None):
    now = now or time.time()
    j = lambda n: json.load(open(os.path.join(pasta, n))) if os.path.exists(os.path.join(pasta, n)) else {}
    D, St, Lq = j("derivados.json"), j("state.json"), j("liquidez.json")
    regimes = {a: (r or {}).get("regime") for a, r in (St.get("regimes") or {}).items()}
    spreads = {a: am[-1][1] * 100 for a, am in (((Lq.get("hoje") or {}).get("amostras")) or {}).items() if am}
    btc = ler_velas(os.path.join(hist, "BTC.csv.gz")) if os.path.exists(os.path.join(hist, "BTC.csv.gz")) else []
    btc_t = {x[0]: x[4] for x in btc}
    dn = dados_novos(dn_csv)
    ativos = {}
    for f in sorted(glob.glob(os.path.join(hist, "*.csv.gz"))):
        a = os.path.basename(f).split(".")[0]
        if a == "BTC":
            continue
        v = ler_velas(f)
        k = len(v) - 1
        while k >= 0 and v[k][0] > now - H4:                           # so velas ja fechadas
            k -= 1
        x = caracteristicas_velas(v, k, btc_t) if k >= 0 else None
        if x:
            x["fontes"] = ["history 4H"]
            x["idade_s"] = now - (x["t"] + H4)
            ativos[a] = x
    for a in set(dn) | set((D.get("moedas") or {})):
        x = ativos.setdefault(a, {"fontes": []})
        d = derivados(D, a, now)
        if d:
            x.update(d)
            x["fontes"].append("derivados (Binance)")
        rows = sorted(dn.get(a) or [], key=lambda r: r["data"])
        if len(rows) >= 2:
            u, p = rows[-1], rows[-2]
            if x.get("funding") is None and u.get("fund_xperp_24h"):
                x["funding"] = OP._f(u["fund_xperp_24h"])
                x["funding_hist"] = [OP._f(r.get("fund_xperp_24h")) for r in rows[:-1]]
            if x.get("oi_chg_24h") is None and OP._f(p.get("oi_usd_global")):
                x["oi_chg_24h"] = OP._f(u.get("oi_usd_global")) / OP._f(p["oi_usd_global"]) - 1 if OP._f(u.get("oi_usd_global")) else None
            if x.get("preco") is None:
                x["preco"] = OP._f(u.get("c"))
                x["ret_24h"] = OP._f(u.get("c")) / OP._f(p.get("c")) - 1 if OP._f(p.get("c")) else None
            x["fontes"].append("dados-novos (OKX/global)")
    for a, x in ativos.items():
        x["ativo"] = a
        x["regime"] = regimes.get(a)
        if a in spreads:
            x["spread_bps"] = spreads[a]
        x.setdefault("t", int(now))
    return ativos


# detetor -> (caracteristica estudada, sinal que poe o IC na direcao do detetor). So os detetores com direcao e cuja
# caracteristica existe no estudo historico; os outros ficam sem evidencia (nunca inventada).
MAPA_EVIDENCIA = {"reversao_continuacao": ("ret_3d", -1), "aceleracao": ("aceleracao_24h", +1),
                  "relativo_btc": ("residual_btc_24h", +1)}


def evidencia_de_ic(caminhos):
    """Evidencia por detetor a partir de um ou mais estudos de IC (ex.: so moedas vivas e com as retiradas). Fica a
    versao MAIS conservadora: o menor IC na direcao e o menor liquido entre os estudos."""
    ev = {}
    for p in caminhos:
        r = json.load(open(p))
        for det, (car, sinal) in MAPA_EVIDENCIA.items():
            c = (r.get("caracteristicas") or {}).get(car)
            if not c or c.get("ic_medio") is None:
                continue
            q = c.get("quintis_baixo_menos_alto") or {}
            liq = q.get("liquido_estimado_pct")
            if liq is not None and sinal > 0:
                liq = round(-q["spread_medio_pct"] - q["custo_ida_volta_dois_lados_pct"], 3)
            novo = {"ic_na_direcao": round(sinal * c["ic_medio"], 4), "t": round(sinal * (c.get("t") or 0), 2), "dias": c["dias"],
                    "liquido_pct": liq, "fonte": c.get("fonte")}
            a = ev.get(det)
            if a is None or novo["ic_na_direcao"] < a["ic_na_direcao"] or (liq is not None and (a.get("liquido_pct") is None or liq < a["liquido_pct"])):
                if a is not None:
                    novo = {**novo, "ic_na_direcao": min(novo["ic_na_direcao"], a["ic_na_direcao"]),
                            "t": min(novo["t"], a["t"], key=abs) if novo["ic_na_direcao"] > 0 else novo["t"],
                            "liquido_pct": min(x for x in (liq, a.get("liquido_pct")) if x is not None) if (liq is not None or a.get("liquido_pct") is not None) else None,
                            "fonte": f"{a.get('fonte')} | {novo['fonte']}"}
                ev[det] = novo
    return ev


def correr(hist, pasta, dn_csv, saida, now=None, evidencia=None):
    now = now or time.time()
    p = painel(hist, pasta, dn_csv, now)
    ops = [o for o in (OP.classificar(a, evidencia) for a in p.values()) if o]
    ops.sort(key=lambda o: -sum(s["forca"] for s in o["sinais"]))
    dia = time.strftime("%Y-%m-%d", time.gmtime(now))
    os.makedirs(saida, exist_ok=True)
    json.dump({"t": int(now), "ativos_analisados": len(p), "oportunidades": ops,
               "nota": "sombra: sem autoridade de execucao; direcao e uma hipotese"},
              open(os.path.join(saida, "oportunidades.json"), "w"), ensure_ascii=False, indent=1, default=str)
    # linha por ativo para a avaliacao posterior (o retorno seguinte junta-se quando existir)
    with open(os.path.join(saida, "registo_sombra.jsonl"), "a") as f:
        for a, x in p.items():
            car = {k: x.get(k) for k in ("preco", "ret_24h", "ret_3d", "vol_ratio", "residual_btc_24h", "funding", "oi_chg_24h", "ls")}
            f.write(json.dumps({"dia": dia, "ativo": a, **car}) + "\n")
    return ops, p


if __name__ == "__main__":
    ev = evidencia_de_ic(sys.argv[5:]) if len(sys.argv) > 5 else None
    ops, p = correr(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], evidencia=ev)
    print(f"ativos {len(p)} | oportunidades {len(ops)}")
    for o in ops[:15]:
        print(f"- {o['ativo']}: {o['direcao_potencial']} | {o['motivo']} | dados {o['qualidade_dados']['nivel']} | "
              f"custos {o['custos_estimados_pct']}% | expectativa {o['expectativa_estimada']}")
