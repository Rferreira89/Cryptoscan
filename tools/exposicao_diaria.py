"""(ordem do Rui de 10/11, ponto 4) Mapa diario de exposicao e correlacao, Bybit e OKX SEPARADAS.

So leitura: copias publicas dos agentes (ramos data, okx, okx-tfshort) e velas PUBLICAS de 1 hora da OKX (30 dias,
perpetuo global <MOEDA>-USDT-SWAP). Sem chaves, sem ordens, sem valores em dinheiro (so ativos, lados, R e %).

Blocos (nunca somados entre si):
  okx_real    - posicoes e ordens reais do executor da OKX (com preco atual, R, distancia ao stop e ao objetivo);
  bybit_real  - operacoes reais abertas da Bybit visiveis na copia publica (a tendencia BTC/nucleo so na privada);
  papel_sombra- posicoes de papel e sombra de todas as estrategias (H40, H45, TF-SHORT, fases, ...).
Em cada bloco: LONG/SHORT, o mesmo ativo em varias estrategias, grupos de ativos correlacionados (>= 0,7 nos
retornos de 1 h), e o numero efetivo de apostas independentes (engine/exposicao.py).
Uso: python3 tools/exposicao_diaria.py <pasta com state.json, okx.json, okx_tfshort.json, okx_tfshort_sombra.json>"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from engine import exposicao as X  # noqa: E402
from tools import tfs_sombra as TS  # noqa: E402  (GET publico)

H = 3600
CUSTOS_IDA_VOLTA = 0.0005 * 2 + 0.001          # comissao taker dos dois lados + deslize no stop (estimativa)


def _c(p, n):
    f = os.path.join(p, n)
    if not os.path.exists(f):
        return {}
    d = json.load(open(f))
    return d.get("estado", d) if isinstance(d, dict) and "soma" in d else d


def exposicoes(pasta):
    st, okx, tfs, som = (_c(pasta, n) for n in ("state.json", "okx.json", "okx_tfshort.json", "okx_tfshort_sombra.json"))
    okx_real = [{"ativo": a, "lado": "LONG", "origem": f"OKX {v.get('estrategia') or 'panico'} ({v.get('estado')})", "op": v}
                for a, v in ((okx.get("real") or {}).get("ops") or {}).items()]
    bybit_real = [{"ativo": r.get("asset"), "lado": r.get("side") or "LONG", "origem": f"Bybit {r.get('strategy')}"}
                  for r in st.get("ledger") or [] if r.get("executed") is True and r.get("status") == "OPEN"]
    papel = [{"ativo": a, "lado": "LONG", "origem": f"H40 papel ({v.get('tipo')})"} for a, v in (okx.get("abertas") or {}).items()]
    papel += [{"ativo": a, "lado": "LONG", "origem": "H46 papel"} for a in ((okx.get("recuo") or {}).get("abertas") or [])]
    papel += [{"ativo": a, "lado": "SHORT", "origem": "TF-SHORT papel"} for a in ((tfs.get("conta") or {}).get("abertas") or {})]
    papel += [{"ativo": a, "lado": "SHORT", "origem": "TF-SHORT sombra"} for a in (som.get("abertas") or {})]
    papel += [{"ativo": a, "lado": "LONG", "origem": "H45 papel"} for a in ((st.get("papel_panico") or {}).get("abertas") or {})]
    for fase, lado in (("lateral", "SHORT"), ("subida", "LONG")):
        papel += [{"ativo": a, "lado": lado, "origem": f"fases {fase} papel"}
                  for a in (((st.get("papel_fases") or {}).get(fase) or {}).get("abertas") or {})]
    return {"okx_real": okx_real, "bybit_real": bybit_real, "papel_sombra": papel}


def velas(moeda, horas=720):
    out, depois = {}, ""
    for _ in range(horas // 100 + 1):
        d = TS._get(f"/api/v5/market/history-candles?instId={moeda}-USDT-SWAP&bar=1H&limit=100{depois}")
        if not d:
            break
        for x in d:
            if len(x) > 8 and x[8] == "1":
                out[int(x[0]) // 1000] = float(x[4])
        depois = f"&after={d[-1][0]}"
        time.sleep(0.12)
    return [out[t] for t in sorted(out)][-horas:]


def posicao_real(op, px):
    """R atual e distancias, para um long da OKX; risco efetivo ate ao stop com custos previsiveis (sem financiamento)."""
    e, s, a, rp = op.get("entrada") or op.get("lim"), op.get("stop"), op.get("alvo"), op.get("risco_pct")
    if not (e and s and px) or e <= s:
        return {}
    dist = (e - s) / e
    return {"preco": px, "entrada": e, "R_atual": round((px - e) / (e - s), 2),
            "dist_stop_pct": round(100 * (px - s) / px, 2), "dist_objetivo_pct": round(100 * (a - px) / px, 2) if a else None,
            "risco_plano_pct_conta": rp,
            "risco_com_custos_pct_conta": round(rp * (dist + CUSTOS_IDA_VOLTA) / dist, 3) if rp else None,
            "stop_confirmado_na_okx": op.get("stop_ok"), "estado": op.get("estado")}


def conflitos(expos, grupos):
    """Tres tipos (ordem de 10/11, ponto 5):
      mesmo_ativo_oposto  - o mesmo ativo LONG numa estrategia e SHORT noutra;
      grupo_oposto        - ativos fortemente correlacionados com LONG e SHORT ao mesmo tempo (anulam-se em parte);
      mesma_exposicao     - estrategias diferentes no mesmo ativo e na mesma direcao (parecem duas apostas, sao uma)."""
    por_ativo, por_grupo = {}, {}
    for e in expos:
        por_ativo.setdefault(e["ativo"], []).append(e)
        g = grupos.get(e["ativo"])
        if g:
            por_grupo.setdefault(g, []).append(e)
    out = {"mesmo_ativo_oposto": {}, "grupo_oposto": [], "mesma_exposicao": {}}
    for a, v in por_ativo.items():
        lados = {e["lado"] for e in v}
        origens = sorted({e["origem"] for e in v})
        if len(lados) > 1:
            out["mesmo_ativo_oposto"][a] = sorted(f"{e['origem']} {e['lado']}" for e in v)
        elif len(origens) > 1:
            out["mesma_exposicao"][a] = origens
    for g, v in por_grupo.items():
        longs = sorted({e["ativo"] for e in v if e["lado"] == "LONG"}); shorts = sorted({e["ativo"] for e in v if e["lado"] == "SHORT"})
        if longs and shorts and set(longs) != set(shorts):
            out["grupo_oposto"].append({"long": longs, "short": shorts,
                                        "estrategias": sorted({e["origem"].split(" (")[0] for e in v})})
    return out


def bloco(expos, fechos):
    m = X.mapa(fechos, expos)
    ativos = {}
    for e in expos:
        ativos.setdefault(e["ativo"], []).append(f"{e['origem']} {e['lado']}")
    mesmo = {a: v for a, v in ativos.items() if len(v) > 1}
    return {"n": len(expos), "long": sum(e["lado"] == "LONG" for e in expos), "short": sum(e["lado"] == "SHORT" for e in expos),
            "mesmo_ativo_varias_estrategias": mesmo, "grupos_correlacionados": m["concentracoes"],
            "apostas_efetivas": m["apostas_efetivas"], "conflitos": conflitos(expos, m["grupos"]),
            "sem_precos": sorted({e["ativo"] for e in expos if e["ativo"] not in fechos})}


def texto(mapa_):
    """Bloco do relatorio (sem valores em dinheiro)."""
    nomes = {"okx_real": "OKX real", "bybit_real": "Bybit real", "papel_sombra": "Papel e sombra (todas as estratégias)"}
    L = ["", "EXPOSIÇÃO E CORRELAÇÃO (informativo; contas separadas)"]
    for k, b in mapa_["blocos"].items():
        L.append(f"- {nomes.get(k, k)}: {b['n']} posições ({b['long']} LONG, {b['short']} SHORT) = "
                 f"{b['apostas_efetivas']} apostas independentes")
        for g in b["grupos_correlacionados"][:3]:
            L.append(f"  · {g['n']} {g['lado']} correlacionados: {', '.join(g['ativos'][:8])}")
        c = b["conflitos"]
        if c["mesmo_ativo_oposto"]:
            L.append("  · mesmo ativo em sentidos opostos: " + "; ".join(f"{a} ({', '.join(v)})" for a, v in list(c["mesmo_ativo_oposto"].items())[:5]))
        if c["mesma_exposicao"]:
            L.append("  · a mesma aposta em estratégias diferentes: " + "; ".join(f"{a} ({', '.join(v)})" for a, v in list(c["mesma_exposicao"].items())[:5]))
        if c["grupo_oposto"]:
            L.append(f"  · grupos correlacionados com LONG e SHORT ao mesmo tempo: {len(c['grupo_oposto'])}")
        if b["sem_precos"]:
            L.append(f"  · sem preços (correlação desconhecida): {', '.join(b['sem_precos'][:10])}")
    if "bybit_real" in mapa_["blocos"]:
        L.append("- Bybit: a tendência BTC (núcleo) só aparece na cópia privada; não está neste mapa.")
    return "\n".join(L) + "\n"


def correr(pasta, obter=velas):
    ex = exposicoes(pasta)
    moedas = sorted({e["ativo"] for b in ex.values() for e in b if e.get("ativo")})
    fechos = {}
    for m in moedas:
        v = obter(m)
        if len(v) >= 48:
            fechos[m] = v
    out = {"t": int(time.time()), "blocos": {k: bloco(v, fechos) for k, v in ex.items()}}
    out["okx_posicoes_reais"] = {e["ativo"]: posicao_real(e["op"], (fechos.get(e["ativo"]) or [None])[-1])
                                 for e in ex["okx_real"]}
    return out


if __name__ == "__main__":
    print(json.dumps(correr(sys.argv[1]), ensure_ascii=False, indent=1, default=str))
