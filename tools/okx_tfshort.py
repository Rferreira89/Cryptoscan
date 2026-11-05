"""(05/11, preparacao isolada; NAO ATIVO) TF-SHORT U2: short de tendencia em altcoins liquidas da OKX Europa, SO PAPEL.

Regras exatamente as do backtest pre-registado (tf1/tf2, 05/11) mais o stop de protecao testado a parte:
- Velas diarias UTC fechadas. s = quantas das medias de 20, 50, 100 e 200 dias estao abaixo do fecho (0 a 4).
- Short entra quando s <= 1 e sai quando s >= 3 (s = 2 mantem). Execucao na primeira volta depois do fecho.
- Stop de protecao: entrada + 3 x ATR20 (preco) fixado na entrada; se tocar, sai e so volta depois de a regra sair
  (s >= 3) e voltar a dar entrada. (Testado: R +0,148 -> +0,166, pior operacao -8R -> -1,7R.)
- Universo U2: X-Perps de cripto da conta, sem BTC/ETH/SOL nem estaveis, com volume mediano de 30 dias >= 20 M USD
  e >= 220 dias de historia. Liquidez e sinal medidos no perpetuo USDT global da mesma moeda (historia longa);
  as entradas e saidas em papel usam o preco do X-Perp.
- Tamanho: peso = min(1, 0,25% / vol diaria de 30 dias) do capital; no maximo 5 posicoes e exposicao bruta <= 0,5x;
  arredonda ao lote do contrato; abaixo da ordem minima NAO entra (fica registado "abaixo_minimo").
  Desempate no mesmo dia: ordem alfabetica (como no backtest).
- Custos em papel: 0,05% taxa + 0,10% deslize + 0,02% spread por lado; financiamento real (o short recebe se > 0).
Dois registos: "sinais" (todas as operacoes da regra, sem limites de capital, em R) e "conta" (o que caberia numa
conta de 20 USD com os minimos reais). Validacao operacional, nao prova estatistica: >= 30 operacoes fechadas.
Este modulo NAO tem acesso a chave nem a ordens: so le dados publicos."""
import json, math, os, socket, time, urllib.request

BASE = "https://eea.okx.com"
DAY = 86400
MEDIAS = (20, 50, 100, 200)
VOL_ALVO, MAX_POS, BRUTA_MAX = 0.0025, 5, 0.5
LIQ_MIN, HIST_MIN = 20e6, 220
CUSTO = 0.0005 + 0.0010 + 0.0002
STOP_ATR = 3.0
EXCLUIR = {"BTC", "ETH", "SOL", "USDC", "USDT", "DAI", "FDUSD", "TUSD", "USDE", "PYUSD", "EURC", "USD1", "RLUSD", "PAXG", "XAUT"}
CONTA0 = 20.0


# ---------- regra (funcoes puras, testadas) ----------
def estado_medias(fechos):
    """s (0..4) com o ultimo fecho, ou None sem 200 dias."""
    if len(fechos) < max(MEDIAS):
        return None
    c = fechos[-1]
    return sum(1 for L in MEDIAS if c > sum(fechos[-L:]) / L)


def atr20(velas):
    if len(velas) < 21:
        return None
    tr = [max(v["h"], p["c"]) - min(v["l"], p["c"]) for p, v in zip(velas[-21:-1], velas[-20:])]
    return sum(tr) / 20


def vol30(fechos):
    if len(fechos) < 31:
        return None
    r = [math.log(b / a) for a, b in zip(fechos[-31:-1], fechos[-30:])]
    m = sum(r) / 30
    return math.sqrt(sum((x - m) ** 2 for x in r) / 29)


def liquidez(velas):
    v = sorted(x.get("usd", 0.0) for x in velas[-30:])
    return v[len(v) // 2] if len(v) >= 30 else 0.0


def peso(vol):
    return min(1.0, VOL_ALVO / vol) if vol and vol > 0 else 0.0


def tamanho(capital, w, px, info):
    """(contratos, nocional, minimo, cabe). Arredonda para baixo ao lote; nunca aumenta o risco para caber."""
    ct, lote, mn = info["ctVal"], info.get("lotSz") or info["minSz"], info["minSz"]
    alvo = capital * w
    n = math.floor(alvo / (ct * px) / lote + 1e-9) * lote
    return n, round(n * ct * px, 4), round(mn * ct * px, 4), n >= mn and n > 0


def r_op(entrada, saida, atr_pct, fund):
    ret = -(saida / entrada - 1) - 2 * CUSTO + fund
    return round(ret / (2 * atr_pct), 3), round(ret, 5)


# ---------- uma volta diaria ----------
def correr(st, dados, now, infos):
    """dados: {BASE: {"velas": [velas diarias fechadas do perpetuo global, a mais recente no fim, com "usd"],
                      "px": preco atual do X-Perp, "fund": [(t, taxa)]}}; infos: {BASE: ctVal/minSz/lotSz do X-Perp}.
    Atualiza st e devolve a lista de eventos (para o registo e o relatorio). Nunca envia ordens."""
    st.setdefault("sinais", {"abertas": {}, "fechadas": []})
    st.setdefault("conta", {"capital": CONTA0, "abertas": {}, "fechadas": [], "ignoradas": []})
    st.setdefault("parados", {})                     # moedas que bateram no stop: esperam s >= 3
    ev = []
    sinal = {}
    for a in sorted(dados):
        d = dados[a]
        if a in EXCLUIR or a not in infos:
            continue
        f = [v["c"] for v in d["velas"]]
        s = estado_medias(f)
        if s is None or len(f) < HIST_MIN:
            continue
        sinal[a] = s
        if s >= 3:
            st["parados"].pop(a, None)
    for livro in ("sinais", "conta"):
        L = st[livro]
        for a, p in list(L["abertas"].items()):
            d = dados.get(a)
            if not d:
                continue
            px = d["px"]
            hi = max([v["h"] for v in d["velas"] if v["t"] >= p["t"]] or [px])
            fund = sum(x for t, x in d.get("fund", []) if p["t"] < t <= now)
            motivo = None
            if hi >= p["stop"] or px >= p["stop"]:
                motivo, saida = "stop", max(p["stop"], px) * 1.001     # se ja abriu acima do stop, sai ao preco
                st["parados"][a] = now
            elif sinal.get(a, 2) >= 3:
                motivo, saida = "regra", px
            if motivo:
                R, ret = r_op(p["entrada"], saida, p["atr_pct"], fund)
                fe = dict(p, moeda=a, saida=round(saida, 8), t_saida=now, motivo=motivo, R=R, ret=ret, fund=round(fund, 6))
                L["fechadas"].append(fe); del L["abertas"][a]
                if livro == "conta":
                    L["capital"] = round(L["capital"] * (1 + p["w"] * ret), 6)
                ev.append((livro, "saida", fe))
    cand = [a for a, s in sinal.items() if s <= 1 and a not in st["parados"]
            and liquidez(dados[a]["velas"]) >= LIQ_MIN]
    for a in cand:                                    # alfabetico
        d = dados[a]; f = [v["c"] for v in d["velas"]]
        atr, vol = atr20(d["velas"]), vol30(f)
        if not atr or not vol:
            continue
        e = d["px"]; atr_pct = atr / f[-1]; w = peso(vol)
        op = {"t": now, "entrada": e, "stop": round(e * (1 + STOP_ATR * atr_pct), 8), "atr_pct": round(atr_pct, 6), "w": round(w, 5), "s": sinal[a]}
        if a not in st["sinais"]["abertas"]:
            st["sinais"]["abertas"][a] = op; ev.append(("sinais", "entrada", dict(op, moeda=a)))
        C = st["conta"]
        if a in C["abertas"]:
            continue
        motivo = None
        if len(C["abertas"]) >= MAX_POS:
            motivo = "maximo_posicoes"
        elif sum(p["w"] for p in C["abertas"].values()) + w > BRUTA_MAX + 1e-9:
            motivo = "exposicao_bruta"
        else:
            n, nom, mn, cabe = tamanho(C["capital"], w, e, infos[a])
            if not cabe:
                motivo = "abaixo_minimo"
        if motivo:
            if not any(x["moeda"] == a and x["t"] == now for x in C["ignoradas"]):
                C["ignoradas"].append({"moeda": a, "t": now, "motivo": motivo})
            ev.append(("conta", "ignorada", {"moeda": a, "motivo": motivo}))
            continue
        C["abertas"][a] = dict(op, contratos=n, nocional=nom)
        C["capital"] = round(C["capital"] * (1 - w * CUSTO), 6)   # custo de entrada (a saida desconta no fecho)
        ev.append(("conta", "entrada", dict(op, moeda=a, contratos=n, nocional=nom)))
    C = st["conta"]; C["ignoradas"] = C["ignoradas"][-500:]
    return ev


def resumo(st):
    out = {}
    for livro in ("sinais", "conta"):
        F = [x["R"] for x in st.get(livro, {}).get("fechadas", [])]
        out[livro] = {"fechadas": len(F), "abertas": len(st.get(livro, {}).get("abertas", {})),
                      "r_medio": round(sum(F) / len(F), 3) if F else None,
                      "acerto_pct": round(100 * sum(1 for x in F if x > 0) / len(F)) if F else None,
                      "stops": sum(1 for x in st.get(livro, {}).get("fechadas", []) if x["motivo"] == "stop")}
    out["pronto_para_avaliar"] = out["conta"]["fechadas"] >= 30
    return out


# ---------- dados publicos (so leitura; nao usado nos testes) ----------
def _get(path):
    _gai = socket.getaddrinfo
    socket.getaddrinfo = lambda h, p, f=0, *a, **k: _gai(h, p, socket.AF_INET, *a, **k)
    try:
        req = urllib.request.Request(BASE + path, headers={"User-Agent": "cryptoscan/1.0"})
        with urllib.request.urlopen(req, timeout=25) as r:
            d = json.loads(r.read())
        return d.get("data") or [] if d.get("code") == "0" else []
    except Exception:
        return []
    finally:
        socket.getaddrinfo = _gai


def recolher():
    """(dados, infos) so com a API publica: X-Perps de cripto, velas diarias do perpetuo USDT global, financiamento."""
    infos = {}
    for i in _get("/api/v5/public/instruments?instType=FUTURES"):
        iid = i.get("instId", "")
        if "XPERP" in iid and i.get("state") == "live" and str(i.get("instCategory") or "1") == "1":
            infos[iid.split("-")[0]] = {"inst": iid, "ctVal": float(i.get("ctVal") or 0), "minSz": float(i.get("minSz") or 0), "lotSz": float(i.get("lotSz") or 0)}
    px = {t["instId"]: float(t.get("last") or 0) for t in _get("/api/v5/market/tickers?instType=FUTURES")}
    dados = {}
    for a, info in sorted(infos.items()):
        if a in EXCLUIR:
            continue
        velas = []
        depois = ""
        for _ in range(2):                                   # 2 x 300 dias
            d = _get(f"/api/v5/market/history-candles?instId={a}-USDT-SWAP&bar=1Dutc&limit=300{depois}")
            if not d:
                break
            velas += [{"t": int(x[0]) // 1000, "o": float(x[1]), "h": float(x[2]), "l": float(x[3]), "c": float(x[4]),
                       "usd": float(x[7] or 0)} for x in d if len(x) > 8 and x[8] == "1"]
            depois = f"&after={d[-1][0]}"
            time.sleep(0.1)
        velas = sorted({v["t"]: v for v in velas}.values(), key=lambda v: v["t"])
        fund = [(int(x["fundingTime"]) // 1000, float(x.get("realizedRate") or x.get("fundingRate") or 0))
                for x in _get(f"/api/v5/public/funding-rate-history?instId={info['inst']}&limit=100")]
        dados[a] = {"velas": velas, "px": px.get(info["inst"]) or (velas[-1]["c"] if velas else 0), "fund": fund}
    return dados, infos


def main(caminho, ensaio=True):
    """Volta de papel. Por omissao e um ENSAIO: calcula e imprime, sem gravar estado."""
    st = json.load(open(caminho)) if os.path.exists(caminho) else {}
    dados, infos = recolher()
    ev = correr(st, dados, int(time.time()) // DAY * DAY, infos)
    print(json.dumps({"universo": len(dados), "eventos": len(ev), "resumo": resumo(st)}, ensure_ascii=False))
    if not ensaio:
        json.dump(st, open(caminho, "w"), ensure_ascii=False)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/okx_tfshort.json", ensaio="--gravar" not in sys.argv))
