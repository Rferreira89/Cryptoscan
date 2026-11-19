"""(19/11, ordem do Rui, pontos 11, 12 e 16) SOMBRA ao vivo das hipoteses rapidas R1-R4 (tools/estudo_rapidas_1h):
o mesmo codigo de eventos e de simulacao, aplicado a velas de 1 h PUBLICAS da OKX (perpetuos USDT mais negociados).
Classificacao: SHADOW. Nunca gera ordens nem sinais para executores; nao usa chaves; so precos, R e contagens.

Cada volta (de hora a hora):
  1. universo: os N perpetuos USDT-SWAP da OKX com mais volume em 24 h (sem estaveis);
  2. eventos na ULTIMA vela fechada de cada moeda (so o passado);
  3. resolve os eventos abertos quando ja ha as velas de 1, 2 e 4 h depois da entrada (abertura da vela seguinte);
     custos de ida e volta da OKX (0,05% taker + 0,05% deslize por lado);
  4. resumo por hipotese, duracao e lado (n, dias independentes, media R).
Dados em falta: um evento cuja moeda deixa de ter velas fica 'sem_dados' ao fim de 48 h (nao conta, nao e zero).
Uso: python3 tools/sombra_rapidas.py <estado.json>"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from tools import estudo_rapidas_1h as ER  # noqa: E402

H = 3600
N_MOEDAS = 60
ESTAVEIS = {"USDC", "USDT", "DAI", "FDUSD", "TUSD", "USDE", "PYUSD", "EURT", "EUR", "USD1"}
CUSTO = ER.CUSTOS["okx_perp"]
MAX_FECHADAS = 20000


def _get_publico(path):
    from tools import tfs_sombra as TS
    return TS._get(path)


def universo(get=_get_publico, n=N_MOEDAS):
    tk = get("/api/v5/market/tickers?instType=SWAP") or []
    xs = []
    for t in tk:
        inst = t.get("instId") or ""
        if not inst.endswith("-USDT-SWAP"):
            continue
        base = inst.split("-")[0]
        if base in ESTAVEIS:
            continue
        try:
            vol = float(t.get("volCcy24h") or 0) * float(t.get("last") or 0)
        except ValueError:
            continue
        xs.append((vol, base))
    return [b for _, b in sorted(xs, reverse=True)[:n]]


def velas(base, get=_get_publico, n=60):
    d = get(f"/api/v5/market/candles?instId={base}-USDT-SWAP&bar=1H&limit={n}")
    if not d:
        return None
    out = [{"t": int(x[0]) // 1000, "o": float(x[1]), "h": float(x[2]), "l": float(x[3]), "c": float(x[4]),
            "v": float(x[5])} for x in d if len(x) > 8 and str(x[8]) == "1"]
    return sorted(out, key=lambda b: b["t"])


def resolver(ev, c):
    """Resultados de 1, 2 e 4 h quando ja existem; None enquanto faltam velas."""
    idx = {b["t"]: k for k, b in enumerate(c)}
    i = idx.get(ev["t"])
    if i is None or i < 24 or i + 4 >= len(c):
        return None
    out = {}
    for hold in ER.HOLDS:
        ret, r, mot = ER.simular(c, i, ev["lado"], hold)
        dist = ER.K_STOP * ER.atr(c, i) / c[i + 1]["o"]
        out[f"{hold}h"] = {"r_bruto": round(r, 4), "r_liquido": round((ret - CUSTO) / dist, 4) if dist else None,
                           "motivo": mot}
    return out


def resumo(fechadas):
    g = {}
    for f in fechadas:
        for hold, x in (f.get("resultado") or {}).items():
            if x.get("r_liquido") is None:
                continue
            k = f"{f['hip']}|{hold}|{'LONG' if f['lado'] > 0 else 'SHORT'}"
            a = g.setdefault(k, {"n": 0, "soma": 0.0, "dias": set()})
            a["n"] += 1
            a["soma"] += x["r_liquido"]
            a["dias"].add(f["t"] // 86400)
    return {k: {"n": a["n"], "dias_independentes": len(a["dias"]), "media_R_liquido": round(a["soma"] / a["n"], 4)}
            for k, a in sorted(g.items())}


def volta(estado, now=None, get=_get_publico):
    now = int(now or time.time())
    st = dict(estado or {})
    st.setdefault("abertas", {})
    st.setdefault("fechadas", [])
    moedas = universo(get)
    if not moedas:
        st["ultima_falha"] = {"t": now, "motivo": "OKX sem resposta (universo)"}
        return st
    cache = {}
    btc = velas("BTC", get) or []
    btc_ret = {b["t"]: b["c"] / b["o"] - 1 for b in btc}
    novos = 0
    for b in moedas:
        c = velas(b, get)
        cache[b] = c
        if not c or len(c) < 26:
            continue
        i = len(c) - 1                                             # ultima vela fechada
        for hip, _, lado in ER.eventos_em(b, c, i, btc_ret):
            k = f"{hip}|{b}|{c[i]['t']}|{lado}"
            if k in st["abertas"] or k in set(st.get("chaves") or []):
                continue
            st["abertas"][k] = {"hip": hip, "ativo": b, "t": c[i]["t"], "lado": lado, "preco_ref": c[i]["c"],
                                "visto": now, "btc_1h": round(btc_ret.get(c[i]["t"], 0.0), 4)}
            st.setdefault("chaves", []).append(k)
            novos += 1
    fechar = []
    for k, ev in st["abertas"].items():
        c = cache.get(ev["ativo"])
        if c is None and now - ev["t"] <= 48 * H:
            c = velas(ev["ativo"], get)
        res = resolver(ev, c) if c else None
        if res is not None:
            fechar.append((k, dict(ev, resultado=res, fechado=now)))
        elif now - ev["t"] > 48 * H:
            fechar.append((k, dict(ev, resultado=None, sem_dados=True, fechado=now)))
    for k, f in fechar:
        st["abertas"].pop(k, None)
        st["fechadas"].append(f)
    st["fechadas"] = st["fechadas"][-MAX_FECHADAS:]
    st["chaves"] = (st.get("chaves") or [])[-20000:]
    st.update(t=now, classificacao="SHADOW", moedas=len(moedas), novos_ultima_volta=novos,
              resumo=resumo(st["fechadas"]), custo_ida_volta=CUSTO,
              nota="so precos publicos da OKX; nenhuma ordem; resultados hipoteticos (sombra), nao sao reais")
    return st


if __name__ == "__main__":
    caminho = sys.argv[1]
    try:
        with open(caminho) as f:
            estado = json.load(f)
    except (OSError, ValueError):
        estado = {}
    novo = volta(estado)
    with open(caminho, "w") as f:
        json.dump(novo, f, ensure_ascii=False, separators=(",", ":"))
    print(json.dumps({k: novo.get(k) for k in ("t", "moedas", "novos_ultima_volta")}), len(novo["abertas"]), len(novo["fechadas"]))
