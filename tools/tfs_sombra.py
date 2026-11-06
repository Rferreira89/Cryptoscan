"""(06/11, OK do Rui) TF-SHORT em SOMBRA na OKX EEA: o que um executor de short faria com 20 USD, simulado sem tocar
na corretora.

So leitura da API PUBLICA da OKX (instrumentos, livro de ordens, velas e financiamento do proprio X-Perp). Este modulo
nao tem chaves, nao assina pedidos, nao tem nenhum caminho de escrita (so GET) e nao importa o executor real de shorts
nem o okx_exec. Zero ordens, zero alteracoes de posicoes reais.

Por cada sinal do paper TF-SHORT (tools/okx_tfshort.py, livro "sinais"):
  - mede se cabia na conta de 20 USD (minimo do contrato, lote, maximo de 5 posicoes, exposicao bruta 0,5x); se nao
    cabe, regista o motivo e o capital minimo que seria preciso (oportunidade nao executavel);
  - se cabe: entrada VENDA a mercado ao preco medio do livro de ordens real nesse momento (spread e deslize medidos,
    nao assumidos), stop de compra condicional no stop do sinal (arredondado ao tick, para cima), sem objetivo fixo
    (a saida e a regra das medias do TF-SHORT);
  - acompanha com as velas de 1 hora do X-Perp: stop tocado -> sai ao stop (ou a abertura, se abriu acima) + deslize;
    regra de saida do paper -> sai ao preco medio de COMPRA do livro nesse momento;
  - custos: comissao 0,05% por lado, spread e deslize medidos, financiamento real do X-Perp (o short recebe se positivo).
Estado com versao e soma de controlo; estado adulterado ou ilegivel -> sem entradas novas (as abertas continuam a ser
acompanhadas). Uso: python3 tools/tfs_sombra.py <okx_tfshort.json> <okx_tfshort_sombra.json> [--gravar] [--iniciar]"""
import hashlib
import json
import math
import os
import socket
import sys
import time
import urllib.request

BASE = "https://eea.okx.com"
VERSAO = 1
CAPITAL0 = 20.0                     # conta ficticia da sombra (a mesma dos 20 USD reais da OKX)
COMISSAO = 0.0005                   # taker por lado
DESLIZE_STOP = 0.001                # deslize assumido so na ordem de stop (condicional a mercado)
MAX_POS = 5
BRUTA_MAX = 0.5
FRESCO_S = 26 * 3600                # so entra em sinais do proprio dia (a volta diaria corre ~00:23 UTC)


# ---------- leitura publica (so GET) ----------
def _get(path):
    _gai = socket.getaddrinfo
    socket.getaddrinfo = lambda h, p, f=0, *a, **k: _gai(h, p, socket.AF_INET, *a, **k)
    try:
        req = urllib.request.Request(BASE + path, headers={"User-Agent": "cryptoscan/1.0"}, method="GET")
        with urllib.request.urlopen(req, timeout=25) as r:
            d = json.loads(r.read())
        return d.get("data") or [] if d.get("code") == "0" else None
    except Exception:
        return None
    finally:
        socket.getaddrinfo = _gai


class Publico:
    """Leitura publica da OKX. Cada metodo devolve None quando falha (nunca inventa)."""
    def instrumentos(self):
        d = _get("/api/v5/public/instruments?instType=FUTURES")
        if d is None:
            return None
        out = {}
        for i in d:
            iid = i.get("instId", "")
            if "XPERP" in iid and i.get("state") == "live":
                out[iid.split("-")[0]] = {"inst": iid, "ctVal": float(i.get("ctVal") or 0), "minSz": float(i.get("minSz") or 0),
                                          "lotSz": float(i.get("lotSz") or 0), "tickSz": float(i.get("tickSz") or 0),
                                          "maxLever": float(i.get("lever") or 0)}
        return out

    def livro(self, inst):
        d = _get(f"/api/v5/market/books?instId={inst}&sz=200")
        if d is None:
            return None
        if not d:
            return {"bids": [], "asks": []}
        b = d[0]
        return {"bids": [(float(x[0]), float(x[1])) for x in b.get("bids") or []],
                "asks": [(float(x[0]), float(x[1])) for x in b.get("asks") or []]}

    def velas_1h(self, inst, desde):
        out, depois = [], ""
        for _ in range(4):                                  # ate 400 horas (~16 dias)
            d = _get(f"/api/v5/market/history-candles?instId={inst}&bar=1H&limit=100{depois}")
            if d is None:
                return None
            if not d:
                break
            out += [{"t": int(x[0]) // 1000, "o": float(x[1]), "h": float(x[2]), "l": float(x[3]), "c": float(x[4])}
                    for x in d if len(x) > 8 and x[8] == "1"]
            if int(d[-1][0]) // 1000 <= desde:
                break
            depois = f"&after={d[-1][0]}"
        return sorted([v for v in out if v["t"] >= desde], key=lambda v: v["t"])

    def financiamento(self, inst):
        d = _get(f"/api/v5/public/funding-rate-history?instId={inst}&limit=100")
        if d is None:
            return None
        return [(int(x["fundingTime"]) // 1000, float(x.get("realizedRate") or x.get("fundingRate") or 0)) for x in d]


# ---------- calculos ----------
def preco_medio(niveis, contratos):
    """Preco medio de execucao a mercado percorrendo o livro; None se o livro nao chega para a quantidade."""
    falta, custo = contratos, 0.0
    for px, sz in niveis:
        q = min(falta, sz)
        custo += q * px; falta -= q
        if falta <= 1e-12:
            return custo / contratos
    return None


def arred_tick(px, tick, cima=True):
    if not tick:
        return px
    n = px / tick
    return round((math.ceil(n - 1e-9) if cima else math.floor(n + 1e-9)) * tick, 12)


def contratos_para(capital, w, px, info):
    ct, lote, mn = info["ctVal"], info.get("lotSz") or info["minSz"], info["minSz"]
    n = math.floor(capital * w / (ct * px) / lote + 1e-9) * lote if ct and px and lote else 0
    return round(n, 10), n >= mn and n > 0


def capital_minimo(w, px, info):
    """Capital que a conta precisaria para o minimo do contrato com este peso (o risco nunca e aumentado para caber)."""
    return round(info["minSz"] * info["ctVal"] * px / w, 2) if w else None


# ---------- estado ----------
def _soma(e):
    return hashlib.sha256(json.dumps(e, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def novo():
    return {"capital": CAPITAL0, "abertas": {}, "fechadas": [], "nao_executaveis": [], "vistos": [], "voltas": []}


def carregar(caminho, iniciar=False):
    """(estado, ok, motivo). ok=False -> sem entradas novas nesta volta."""
    if not os.path.exists(caminho):
        return novo(), bool(iniciar), "estado inicializado (autorizado)" if iniciar else "estado inexistente"
    try:
        corpo = json.load(open(caminho))
    except Exception:
        return novo(), False, "estado ilegivel"
    est = corpo.get("estado") or {}
    if corpo.get("versao") != VERSAO:
        return est or novo(), False, "versao desconhecida"
    if corpo.get("soma") != _soma(est):
        return est, False, "estado adulterado (soma nao confere)"
    return est, True, "ok"


def guardar(caminho, est):
    tmp = caminho + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"versao": VERSAO, "estado": est, "soma": _soma(est)}, f, ensure_ascii=False)
    os.replace(tmp, caminho)


# ---------- uma volta ----------
def _fechar(est, op, saida, motivo, agora, fund, deslize_saida, spread_saida):
    n, ct, e = op["contratos"], op["ctVal"], op["px_fill"]
    nom_e, nom_s = n * ct * e, n * ct * saida
    comissao = COMISSAO * (nom_e + nom_s)
    fin = nom_e * fund                                       # short recebe se a taxa e positiva
    pnl = nom_e - nom_s - comissao + fin
    risco = n * ct * (op["stop"] - e)
    fe = dict(op, saida=round(saida, 10), t_saida=agora, motivo=motivo, fund=round(fund, 6),
              deslize_saida_pct=deslize_saida, spread_saida_pct=spread_saida,
              custos_usd=round(comissao, 6), fund_usd=round(fin, 6), pnl_usd=round(pnl, 6),
              R=round(pnl / risco, 3) if risco > 0 else None)
    est["capital"] = round(est["capital"] + pnl, 6)
    est["fechadas"].append(fe)
    del est["abertas"][op["moeda"]]
    return fe


def volta(tfs, est, ok_estado, motivo_estado, pub, agora):
    """tfs: estado do paper TF-SHORT (depois da volta de hoje); pub: leitura publica (Publico ou falso nos testes).
    Devolve um resumo da volta. Nunca envia ordens: nao ha nenhum cliente de corretora neste modulo."""
    res = {"t": agora, "entradas": 0, "saidas": 0, "nao_executaveis": 0, "falhas": [], "entradas_bloqueadas": None}
    infos = pub.instrumentos()
    if infos is None:                                        # falha de leitura: nada de novo, nada consumido
        res["falhas"].append("instrumentos indisponiveis")
        ok_estado, motivo_estado = False, "instrumentos da OKX indisponiveis"
        infos = {}
    S = tfs.get("sinais") or {}
    # 1) acompanhar as abertas
    for m, op in list(est["abertas"].items()):
        velas = pub.velas_1h(op["inst"], op.get("visto_ate") or op["t_fill"])
        if velas is None:
            res["falhas"].append(f"{m}: velas indisponiveis"); continue
        fundh = pub.financiamento(op["inst"])
        fund = sum(x for t, x in (fundh or []) if op["t_fill"] < t <= agora)
        toque = next((v for v in velas if v["h"] >= op["stop"]), None)
        if toque:
            base = max(op["stop"], toque["o"])               # abriu acima do stop: sai a abertura
            _fechar(est, op, base * (1 + DESLIZE_STOP), "stop", toque["t"], fund, DESLIZE_STOP, None)
            res["saidas"] += 1; continue
        if velas:
            op["visto_ate"] = velas[-1]["t"] + 3600
        if m not in (S.get("abertas") or {}):                # a regra do TF-SHORT saiu (ou o sinal fechou)
            liv = pub.livro(op["inst"])
            px = preco_medio(liv["asks"], op["contratos"]) if liv and liv["asks"] else None
            if px is None:
                res["falhas"].append(f"{m}: sem livro para sair (fica aberta ate a proxima volta)"); continue
            melhor = liv["asks"][0][0]; meio = (liv["asks"][0][0] + liv["bids"][0][0]) / 2 if liv["bids"] else melhor
            _fechar(est, op, px, "regra", agora, fund if fundh is not None else 0.0,
                    round(px / melhor - 1, 6), round(melhor / meio - 1, 6))
            if fundh is None:
                est["fechadas"][-1]["custos_incompletos"] = "financiamento indisponivel"
            res["saidas"] += 1
    # 2) sinais novos
    if not ok_estado:
        res["entradas_bloqueadas"] = motivo_estado
        est["voltas"] = (est.get("voltas") or [])[-60:] + [res]
        return res
    vistos = set(est.get("vistos") or [])
    for m, p in sorted((S.get("abertas") or {}).items()):
        sid = f"{m}-{p['t']}"
        if sid in vistos:
            continue
        vistos.add(sid)
        if agora - p["t"] > FRESCO_S:                       # sinal de outro dia (ex.: anterior ao inicio da sombra):
            est["antigos"] = int(est.get("antigos") or 0) + 1  # entrar agora nao seria o que o executor teria feito
            continue
        info = infos.get(m)
        reg = {"sinal": sid, "moeda": m, "t": agora, "validado": p.get("validado"), "peso": p.get("w")}
        motivo = None
        if not p.get("validado"):
            motivo = "fora_do_universo_validado"
        elif not info:
            motivo = "sem_instrumento_okx_eea"
        elif len(est["abertas"]) >= MAX_POS:
            motivo = "maximo_posicoes"
        elif sum(o["peso"] for o in est["abertas"].values()) + p["w"] > BRUTA_MAX + 1e-9:
            motivo = "exposicao_bruta"
        liv = None
        if not motivo:
            liv = pub.livro(info["inst"])
            if liv is None:                                  # falha de leitura: tenta na proxima volta
                vistos.discard(sid); res["falhas"].append(f"{m}: livro indisponivel"); continue
            if not liv["bids"] or not liv["asks"]:
                motivo = "sem_livro_de_ordens"
        if not motivo:
            ref = liv["bids"][0][0]
            n, cabe = contratos_para(est["capital"], p["w"], ref, info)
            reg["capital_minimo_usd"] = capital_minimo(p["w"], ref, info)
            if not cabe:
                motivo = "abaixo_minimo_do_contrato"
            else:
                px = preco_medio(liv["bids"], n)
                if px is None:
                    motivo = "livro_sem_profundidade"
        if motivo:
            if info and "capital_minimo_usd" not in reg and p.get("w"):
                ref = (liv["bids"][0][0] if liv and liv.get("bids") else p["entrada"])
                reg["capital_minimo_usd"] = capital_minimo(p["w"], ref, info)
            reg["motivo"] = motivo
            est["nao_executaveis"].append(reg); res["nao_executaveis"] += 1
            continue
        melhor = liv["bids"][0][0]; meio = (liv["asks"][0][0] + melhor) / 2
        stop = arred_tick(p["stop"], info["tickSz"], cima=True)
        est["abertas"][m] = {"moeda": m, "sinal": sid, "inst": info["inst"], "t": p["t"], "t_fill": agora,
                             "contratos": n, "ctVal": info["ctVal"], "peso": p["w"], "px_sinal": p["entrada"],
                             "px_fill": round(px, 10), "stop": stop, "objetivo": None, "saida_prevista": "regra das medias",
                             "nocional": round(n * info["ctVal"] * px, 6), "comissao_pct": COMISSAO,
                             "spread_pct": round(1 - melhor / meio, 6), "deslize_pct": round(1 - px / melhor, 6),
                             "capital_minimo_usd": reg["capital_minimo_usd"]}
        res["entradas"] += 1
    est["vistos"] = sorted(vistos)[-2000:]
    est["nao_executaveis"] = est["nao_executaveis"][-1000:]
    est["voltas"] = (est.get("voltas") or [])[-60:] + [res]
    return res


def resumo(est):
    F = [f for f in est.get("fechadas") or [] if f.get("R") is not None]
    motivos = {}
    for x in est.get("nao_executaveis") or []:
        motivos[x["motivo"]] = motivos.get(x["motivo"], 0) + 1
    return {"abertas": sorted(est.get("abertas") or {}), "fechadas": len(est.get("fechadas") or []),
            "soma_r": round(sum(f["R"] for f in F), 3), "nao_executaveis": motivos}


def main(argv):
    tfs_p, est_p = argv[0], argv[1]
    gravar, iniciar = "--gravar" in argv, "--iniciar" in argv
    tfs = json.load(open(tfs_p)) if os.path.exists(tfs_p) else {}
    est, ok, motivo = carregar(est_p, iniciar=iniciar)
    res = volta(tfs, est, ok, motivo, Publico(), int(time.time()))
    print(json.dumps({"volta": {k: v for k, v in res.items() if k != "t"}, "resumo": resumo(est)}, ensure_ascii=False))
    if gravar:
        guardar(est_p, est)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
