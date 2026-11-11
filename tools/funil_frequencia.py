"""(11/11) Funil de frequencia auditavel: de onde vem a falta de operacoes. So copias publicas; so mede.

OKX (H40 e H46): todo o sinal do agente fica seguido em PAPEL ate ao fim (registo feito antes do resultado, por isso
o resultado de um sinal rejeitado e medido sem retrospetiva). Para cada sinal: colocado em real, ou rejeitado e
porque (prefixos do registo real.avisados: p = H40 suspensa do real, i = panico isolado, x = sem X-Perp negociavel,
m = maximo de posicoes H40, r = teto de risco aberto, sem prefixo = ordem minima obrigava a mais risco), ou anterior
ao inicio do dinheiro real. Expectativa em R do papel de cada grupo: se os rejeitados tivessem R positivo, eram
oportunidades perdidas; se negativo, a rejeicao poupou dinheiro.
Bybit: scan (moedas vistas, elegiveis, com dados validos, sinais), motivo da decisao por moeda, estrategias
desligadas/suspensas e promocoes perdidas por motivo (state.promo_lost).
Uso: python3 tools/funil_frequencia.py <pasta_publica> <saida.json>"""
import json
import os
import sys
import time
from collections import Counter, defaultdict

INICIO_REAL_OKX = 1793784928                  # 04/11 09:35 UTC (47534b6: execucao real ligada)
PREFIXOS = {"p": "H40 suspensa do real", "i": "panico isolado (so mercado todo)", "x": "sem X-Perp negociavel",
            "m": "maximo de posicoes H40", "r": "teto de risco aberto", "": "ordem minima obrigava a mais risco"}


def _j(pasta, n):
    p = os.path.join(pasta, n)
    return json.load(open(p)) if os.path.exists(p) else {}


def _media(xs):
    return round(sum(xs) / len(xs), 4) if xs else None


def okx(O):
    real = O.get("real") or {}
    colocados = set(real.get("colocados") or [])
    motivo = {}
    for a in real.get("avisados") or []:
        partes = a.split(":")
        if len(partes) == 3:
            motivo[f"{partes[1]}:{partes[2]}"] = PREFIXOS.get(partes[0], partes[0])
        elif len(partes) == 2:
            motivo.setdefault(a, PREFIXOS[""])
    sinais = []
    for f in O.get("fechadas") or []:
        sinais.append({"chave": f"{f['asset']}:{f['t_sig']}", "t_sig": f["t_sig"], "tipo": f.get("tipo"), "r": f.get("r"), "estado": "fechada"})
    for a, x in (O.get("abertas") or {}).items():
        sinais.append({"chave": f"{a}:{x['t_sig']}", "t_sig": x["t_sig"], "tipo": x.get("tipo"), "r": None, "estado": "aberta"})
    for a, x in (O.get("pend") or {}).items():
        sinais.append({"chave": f"{a}:{x['t_sig']}", "t_sig": x["t_sig"], "tipo": x.get("tipo"), "r": None, "estado": "pendente"})
    grupos = defaultdict(list)
    for s in sinais:
        if s["chave"] in colocados:
            g = "colocado em real"
        elif s["chave"] in motivo:
            g = "rejeitado: " + motivo[s["chave"]]
        elif s["t_sig"] < INICIO_REAL_OKX:
            g = "antes do dinheiro real"
        else:
            g = "sem registo de decisao real"
        grupos[g].append(s)
    out = {"sinais": len(sinais), "por_tipo": dict(Counter(s["tipo"] for s in sinais)),
           "contratos_analisados": (O.get("resumo") or {}).get("analisados"), "grupos": {}}
    for g, xs in sorted(grupos.items()):
        rs = [s["r"] for s in xs if s["r"] is not None]
        out["grupos"][g] = {"n": len(xs), "fechadas_em_papel": len(rs), "r_medio_papel": _media(rs),
                            "soma_r_papel": round(sum(rs), 3) if rs else None}
    rej = [s["r"] for g, xs in grupos.items() if g.startswith("rejeitado") for s in xs if s["r"] is not None]
    out["rejeitados_r_medio_papel"] = _media(rej)
    out["leitura"] = ("os sinais rejeitados perderam em papel: a rejeicao poupou dinheiro" if rej and sum(rej) < 0 else
                      "os sinais rejeitados ganharam em papel: oportunidades perdidas" if rej else "sem rejeitados fechados")
    recuo = (O.get("recuo") or {})
    out["h46"] = {"pendentes": len(recuo.get("pend") or {}), "abertas": len(recuo.get("abertas") or {}),
                  "fechadas": len(recuo.get("fechadas") or []),
                  "btc_em_subida": ((recuo.get("resumo") or {}).get("btc_em_subida"))}
    radar = O.get("radar") or {}
    out["radar"] = {"btc_24h_pct": radar.get("btc_24h"),
                    "o_que_falta": dict(Counter(f.split(" (")[0].split(" -")[0] for x in radar.get("lista") or [] for f in x.get("falta") or []))}
    return out


def bybit(S, St):
    u = S.get("universe") or []
    dec = Counter((x.get("decision") or {}).get("reason") or "?" for x in u)
    regimes = Counter((x.get("decision") or {}).get("regime") or "?" for x in u)
    return {"contagens": S.get("counts"), "motivos_da_decisao": dict(dec.most_common()), "regimes": dict(regimes),
            "estrategias_desligadas": sorted((S.get("disabled_strategies") or {}).keys()),
            "estrategias_suspensas_pelo_criterio": sorted((St.get("suspensos") or {}).keys()),
            "so_papel": St.get("so_papel"),
            "promocoes_perdidas_por_motivo": dict(Counter((x.get("reason") or "").split(":")[0] for x in St.get("promo_lost") or []).most_common()),
            "promocoes_perdidas_por_estrategia": dict(Counter(x.get("strategy") for x in St.get("promo_lost") or []).most_common()),
            "papel_h45_perdidas": (St.get("papel_panico") or {}).get("perdidas")}


def diagnostico(o, b):
    """Causa provavel da falta de operacoes, so com o que foi medido acima."""
    causas = []
    reg = b.get("regimes") or {}
    if sum(v for k, v in reg.items() if "BEAR" in k) >= 0.4 * max(1, sum(reg.values())):
        causas.append("regime de mercado: a maioria das moedas da Bybit esta em BEAR/STRONG BEAR, onde nenhuma estrategia ativa se aplica")
    if len(b.get("estrategias_suspensas_pelo_criterio") or []) >= 10:
        causas.append(f"estrategias suspensas pelo proprio criterio de custos: {len(b['estrategias_suspensas_pelo_criterio'])} (perdiam depois de comissoes e spread)")
    liq = sum(v for k, v in (b.get("motivos_da_decisao") or {}).items() if "Bybit UE" in k)
    if liq:
        causas.append(f"liquidez ou preco da Bybit UE: {liq} moedas rejeitadas por volume, spread ou divergencia")
    if o.get("rejeitados_r_medio_papel") is not None and o["rejeitados_r_medio_papel"] < 0:
        causas.append(f"OKX: os sinais rejeitados para real deram {o['rejeitados_r_medio_papel']:+.2f}R em papel (rejeicao correta)")
    if o.get("h46", {}).get("btc_em_subida") is False:
        causas.append("H46 (unica estrategia com real ligado): exige BTC em subida; 0 sinais no regime atual")
    return causas


def correr(pasta):
    O, S, St = _j(pasta, "okx.json"), _j(pasta, "scan.json"), _j(pasta, "state.json")
    o, b = okx(O), bybit(S, St)
    return {"gerado": int(time.time()), "okx": o, "bybit": b, "diagnostico": diagnostico(o, b)}


if __name__ == "__main__":
    r = correr(sys.argv[1])
    json.dump(r, open(sys.argv[2], "w"), ensure_ascii=False, indent=1)
    print(json.dumps(r, ensure_ascii=False, indent=1))
