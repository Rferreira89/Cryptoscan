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
Universo VALIDADO (05/11, Rui): o backtest escolheu as moedas pelo volume A VISTA da Binance (mediana 30 d >= 20 M USD).
O volume do perpetuo global da OKX da mais moedas (27 contra ~15). Cada moeda leva a marca "validado" (volume Binance):
so as validadas entram no registo "conta" e na avaliacao; as outras ficam so no registo de sinais, como informacao.
Registos INDEPENDENTES (nunca somados):
  "sinais": todas as operacoes da regra nas moedas elegiveis (sem limites de capital), em R, com a marca "validado";
  "conta":  so o que caberia de facto numa conta simulada de 20 USD (universo validado, 0,5x, 5 posicoes, minimos
            reais), com custos, financiamento, stops e as ignoradas com o motivo;
  "qualidade": falhas de dados de cada volta (preco do X-Perp contra o perpetuo global ATUAL, velas velhas, etc.).
Validacao operacional, nao prova estatistica: >= 30 operacoes fechadas no registo "conta".
Este modulo NAO tem acesso a chave nem a ordens: so le dados publicos."""
import json, math, os, socket, time, urllib.error, urllib.request

BASE = "https://eea.okx.com"
BINANCE = "https://data-api.binance.vision"
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
    falhas = qualidade(dados, infos, now)
    q = st.setdefault("qualidade", [])
    q.append({"t": now, "n": len(falhas), "falhas": falhas[:60]}); st["qualidade"] = q[-120:]
    velhas = {f.split(":")[0] for f in falhas if "velas velhas" in f}
    for a in sorted(dados):
        d = dados[a]
        if a in EXCLUIR or a not in infos or a in velhas:
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
                if livro == "conta":
                    nom = p["nocional"]
                    fe.update(pnl_usd=round(nom * ret, 4), custos_usd=round(nom * 2 * CUSTO, 4), fund_usd=round(nom * fund, 4))
                    L["capital"] = round(L["capital"] + nom * ret, 6)        # ret ja inclui os custos dos dois lados
                L["fechadas"].append(fe); del L["abertas"][a]
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
        val = bool(d.get("validado"))
        if a not in st["sinais"]["abertas"]:
            st["sinais"]["abertas"][a] = dict(op, validado=val); ev.append(("sinais", "entrada", dict(op, moeda=a, validado=val)))
        C = st["conta"]
        if a in C["abertas"]:
            continue
        motivo = None
        if not val:
            motivo = "fora_do_universo_validado"
        elif len(C["abertas"]) >= MAX_POS:
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
        C["abertas"][a] = dict(op, contratos=n, nocional=nom, minimo_usd=mn)
        ev.append(("conta", "entrada", dict(op, moeda=a, contratos=n, nocional=nom)))
    C = st["conta"]; C["ignoradas"] = C["ignoradas"][-500:]
    return ev


def _stats(F):
    R = [x["R"] for x in F]
    return {"fechadas": len(R), "r_medio": round(sum(R) / len(R), 3) if R else None,
            "acerto_pct": round(100 * sum(1 for x in R if x > 0) / len(R)) if R else None,
            "stops": sum(1 for x in F if x["motivo"] == "stop")}


def resumo(st):
    """Tres blocos que NUNCA se somam: sinais do universo validado, sinais fora dele (informativo) e a conta executavel."""
    S = st.get("sinais", {}); C = st.get("conta", {})
    fs = S.get("fechadas", [])
    out = {"sinais_validados": dict(_stats([x for x in fs if x.get("validado")]),
                                    abertas=sum(1 for x in S.get("abertas", {}).values() if x.get("validado"))),
           "sinais_fora_do_universo_validado": dict(_stats([x for x in fs if not x.get("validado")]),
                                                   abertas=sum(1 for x in S.get("abertas", {}).values() if not x.get("validado"))),
           "conta_executavel": dict(_stats(C.get("fechadas", [])), abertas=len(C.get("abertas", {})),
                                    capital_simulado=C.get("capital"),
                                    custos_usd=round(sum(x.get("custos_usd", 0) for x in C.get("fechadas", [])), 4),
                                    financiamento_usd=round(sum(x.get("fund_usd", 0) for x in C.get("fechadas", [])), 4))}
    ign = {}
    for x in C.get("ignoradas", []):
        ign[x["motivo"]] = ign.get(x["motivo"], 0) + 1
    out["conta_executavel"]["ignoradas_por_motivo"] = ign
    qq = st.get("qualidade", [])
    out["qualidade"] = {"voltas": len(qq), "voltas_com_falhas": sum(1 for x in qq if x["n"]), "ultima": qq[-1]["falhas"][:10] if qq else []}
    out["pronto_para_avaliar"] = out["conta_executavel"]["fechadas"] >= 30
    out["nota"] = "os sinais sao teoricos; so a conta executavel conta como operacoes que caberiam nos 20 USD"
    return out


def qualidade(dados, infos, now=None):
    """Falhas de dados: sem preco do X-Perp, X-Perp a mais de 2% do perpetuo global ATUAL, sem financiamento,
    velas diarias velhas (ultima com mais de 2 dias), sem volume da Binance para a marca de universo validado."""
    out = []
    for a in sorted(dados):
        if a in EXCLUIR or a not in infos:
            continue
        d = dados[a]; px, pg = d.get("px") or 0, d.get("px_global") or 0
        if not px:
            out.append(f"{a}: sem preco do X-Perp")
        elif pg and abs(px / pg - 1) > 0.02:
            out.append(f"{a}: X-Perp {px:g} difere {100*abs(px/pg-1):.1f}% do perpetuo global atual {pg:g}")
        elif not pg:
            out.append(f"{a}: sem preco atual do perpetuo global")
        if not d.get("fund"):
            out.append(f"{a}: sem historico de financiamento do X-Perp")
        v = d.get("velas") or []
        if now and v and now - v[-1]["t"] > 2 * DAY + 3600:
            out.append(f"{a}: velas velhas (ultima de ha {(now - v[-1]['t']) // DAY} dias)")
        if d.get("validado") is None:
            out.append(f"{a}: sem volume da Binance (universo validado desconhecido; conta como nao validado)")
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


def volume_binance_ok(base):
    """Marca do universo validado: mediana de 30 velas diarias FECHADAS do volume a vista da Binance (base/USDT)
    >= 20 M USD, a mesma medida do backtest. None se a Binance nao responder (conta como nao validado)."""
    try:
        req = urllib.request.Request(f"{BINANCE}/api/v3/klines?symbol={base}USDT&interval=1d&limit=32",
                                     headers={"User-Agent": "cryptoscan/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            k = json.loads(r.read())
    except urllib.error.HTTPError as e:
        return False if e.code == 400 else None              # 400 = par inexistente na Binance
    except Exception:
        return None
    q = sorted(float(x[7]) for x in k[:-1][-30:])            # sem a vela do dia (ainda aberta)
    return len(q) >= 30 and q[len(q) // 2] >= LIQ_MIN


def recolher():
    """(dados, infos) so com a API publica: X-Perps de cripto, velas diarias do perpetuo USDT global, financiamento."""
    infos = {}
    for i in _get("/api/v5/public/instruments?instType=FUTURES"):
        iid = i.get("instId", "")
        if "XPERP" in iid and i.get("state") == "live" and str(i.get("instCategory") or "1") == "1":
            infos[iid.split("-")[0]] = {"inst": iid, "ctVal": float(i.get("ctVal") or 0), "minSz": float(i.get("minSz") or 0), "lotSz": float(i.get("lotSz") or 0)}
    px = {t["instId"]: float(t.get("last") or 0) for t in _get("/api/v5/market/tickers?instType=FUTURES")}
    pg = {t["instId"]: float(t.get("last") or 0) for t in _get("/api/v5/market/tickers?instType=SWAP")}
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
        dados[a] = {"velas": velas, "px": px.get(info["inst"]) or 0, "px_global": pg.get(f"{a}-USDT-SWAP") or 0,
                    "fund": fund, "validado": volume_binance_ok(a)}
    return dados, infos


def main(caminho, ensaio=True):
    """Volta de papel. Por omissao e um ENSAIO: calcula e imprime, sem gravar estado."""
    st = json.load(open(caminho)) if os.path.exists(caminho) else {}
    dados, infos = recolher()
    ev = correr(st, dados, int(time.time()) // DAY * DAY, infos)
    print(json.dumps({"universo": len(dados), "eventos": len(ev), "resumo": resumo(st)}, ensure_ascii=False, indent=1))
    for e in ev:
        print(e[0], e[1], json.dumps(e[2], ensure_ascii=False))
    if not ensaio:
        json.dump(st, open(caminho, "w"), ensure_ascii=False)
    return 0



# ---------- ensaio so de leitura (05/11, autorizado pelo Rui: universo, minimos, financiamento, falhas) ----------
def ensaio(dados, infos, capital=CONTA0, falhas=None):
    """Relatorio do universo real sem gravar nada: elegiveis, sinais de hoje, minimos, o que cabe em `capital`,
    financiamento do X-Perp e falhas de dados. Devolve um dicionario (impresso pelo workflow)."""
    falhas = list(falhas or [])
    cripto = sorted(infos)
    sem_velas, curtas, iliquidas, eleg = [], [], [], []
    for a in cripto:
        if a in EXCLUIR:
            continue
        d = dados.get(a) or {}
        v = d.get("velas") or []
        if not v:
            sem_velas.append(a); continue
        if len(v) < HIST_MIN:
            curtas.append(a); continue
        if liquidez(v) < LIQ_MIN:
            iliquidas.append(a); continue
        eleg.append(a)
    linhas = []
    for a in eleg:
        d = dados[a]; v = d["velas"]; f = [x["c"] for x in v]
        s = estado_medias(f); vol = vol30(f); w = peso(vol); px = d.get("px") or 0
        info = infos[a]
        n, nom, mn, cabe = tamanho(capital, w, px, info) if px else (0, 0, 0, False)
        fu = [x for _, x in d.get("fund", [])]
        linhas.append({"moeda": a, "s": s, "sinal_short": s is not None and s <= 1, "validado": bool(d.get("validado")),
                       "liq_musd": round(liquidez(v) / 1e6, 1),
                       "vol_diaria_pct": round(100 * vol, 2) if vol else None, "peso": round(w, 4),
                       "alvo_usd": round(capital * w, 2), "minimo_usd": mn, "cabe": cabe,
                       "fund_ultimas": len(fu), "fund_soma_pct": round(100 * sum(fu), 4) if fu else None})
    sinais = [x for x in linhas if x["sinal_short"]]
    falhas += qualidade({a: dados[a] for a in eleg}, infos, int(time.time()))
    return {"elegiveis_validados": sum(1 for x in linhas if x["validado"]),
            "sinais_validados_hoje": sum(1 for x in sinais if x["validado"]),
            "sinais_validados_que_cabem": sum(1 for x in sinais if x["validado"] and x["cabe"]),"xperps_cripto": len(cripto), "excluidas": sorted(set(cripto) & EXCLUIR),
            "sem_velas_globais": sem_velas, "historia_curta": curtas, "iliquidas": len(iliquidas), "elegiveis": len(eleg),
            "sinais_hoje": len(sinais), "cabem_em_capital": sum(1 for x in sinais if x["cabe"]),
            "elegiveis_que_caberiam": sum(1 for x in linhas if x["cabe"]), "capital_teste_usd": capital,
            "linhas": linhas, "falhas": falhas}


def main_ensaio():
    """So leitura: recolhe dados publicos e imprime o relatorio do ensaio. Nao grava estado, nao usa chave."""
    t0 = time.time()
    dados, infos = recolher()
    falhas = [] if infos else ["lista de X-Perps vazia (API publica sem resposta?)"]
    rel = ensaio(dados, infos, falhas=falhas)
    rel["segundos"] = round(time.time() - t0)
    linhas = rel.pop("linhas")
    print(json.dumps(rel, ensure_ascii=False, indent=1))
    print("moeda | s | sinal | validado | liquidez M USD | vol diaria % | alvo USD (20) | minimo USD | cabe | financiamento: n, soma %")
    for x in sorted(linhas, key=lambda x: (not x["sinal_short"], not x["validado"], x["moeda"])):
        print(f"{x['moeda']} | {x['s']} | {'SHORT' if x['sinal_short'] else '-'} | {'sim' if x['validado'] else 'nao'} | {x['liq_musd']} | {x['vol_diaria_pct']} | "
              f"{x['alvo_usd']} | {x['minimo_usd']} | {'sim' if x['cabe'] else 'nao'} | {x['fund_ultimas']}, {x['fund_soma_pct']}")
    return 0


if __name__ == "__main__":
    import sys
    if "--ensaio" in sys.argv:
        sys.exit(main_ensaio())
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/okx_tfshort.json", ensaio="--gravar" not in sys.argv))

