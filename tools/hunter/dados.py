"""Dados do Hunter: universo completo dos X-Perps da OKX, historico do universo, velas, funding e falhas de API.

Porque so 100 de 262 e so 59 validos (scanner de 17/11): o scanner pede max_assets=100 (os de maior volume) e o
Quick Opportunities so aceita velas com estado VALID; 41 dos 100 vinham DEGRADED por avisos NAO fatais (velas sem
volume nas ultimas 50: 31; velas com volume > 50x a mediana: 27). Aqui: todos os contratos vivos entram na pesquisa;
avisos nao fatais NAO excluem (ficam como atributos de negociabilidade); so erros fatais (velas impossiveis,
desalinhadas, buracos recentes, dados atrasados) excluem, e cada exclusao fica registada com o motivo.

Mercados de PESQUISA (todos os X-Perps vivos, dados publicos) e mercados NEGOCIAVEIS (os que a conta pode
negociar: so o executor com chaves sabe; aqui nunca se assume) estao separados no campo "negociavel": "por confirmar".
"""
import json
import os
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

OKX = "https://www.okx.com"
BAR = {"30m": 1800, "1H": 3600, "4H": 14400}
UA = {"User-Agent": "cryptoscan-hunter/1.0"}
CLASSES = {"1": "crypto", "3": "equity", "4": "precious_metal"}


class Falhas:
    """Registo das falhas de API (endpoint, codigo, mensagem) para o funil e para identificar APIs com problemas."""

    def __init__(self):
        self.lista = []

    def add(self, onde, erro):
        self.lista.append({"onde": onde[:80], "erro": str(erro)[:160], "t": int(time.time())})

    def resumo(self):
        por = {}
        for f in self.lista:
            k = f["onde"].split("?")[0]
            por[k] = por.get(k, 0) + 1
        return {"total": len(self.lista), "por_endpoint": por, "ultimas": self.lista[-10:]}


FALHAS = Falhas()


def get(path, params=None, tent=4, espera=1.0):
    url = OKX + path + ("?" + urllib.parse.urlencode(params) if params else "")
    erro = None
    for k in range(tent):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
                d = json.loads(r.read().decode())
            if d.get("code") == "0":
                return d.get("data") or []
            erro = f"code {d.get('code')}: {d.get('msg')}"
            if d.get("code") in ("50011", "50061"):            # limite de pedidos
                time.sleep(espera * (k + 2))
                continue
            break
        except Exception as e:
            erro = f"{type(e).__name__}: {e}"
            time.sleep(espera * (k + 1))
    FALHAS.add(path, erro)
    return None


def is_xperp(iid):
    head, _, tail = str(iid).rpartition("-")
    return head.endswith("_UM_XPERP") and tail.isdigit()


def universo(request=get):
    """{base: info} de TODOS os X-Perps vivos (sem pre-mercado), com volume de 24 h em USD e classe."""
    inst = request("/api/v5/public/instruments", {"instType": "FUTURES"}) or []
    tick = {t["instId"]: t for t in (request("/api/v5/market/tickers", {"instType": "FUTURES"}) or [])}
    out = {}
    for i in inst:
        iid = i.get("instId", "")
        if not is_xperp(iid) or i.get("state") != "live" or str(i.get("ruleType")).lower() == "pre_market":
            continue
        base = iid.split("-")[0]
        t = tick.get(iid) or {}
        try:
            ctv, last = float(i.get("ctVal") or 0), float(t.get("last") or 0)
            vol_usd = float(t.get("vol24h") or 0) * ctv * (last if (i.get("ctValCcy") or "").upper() != "USD" else 1)
        except (TypeError, ValueError):
            vol_usd, last = 0.0, 0.0
        info = {"inst": iid, "base": base, "classe": CLASSES.get(str(i.get("instCategory")), "outra"),
                "ctVal": float(i.get("ctVal") or 0), "ctValCcy": i.get("ctValCcy"), "minSz": float(i.get("minSz") or 0),
                "lotSz": float(i.get("lotSz") or 0), "tick": float(i.get("tickSz") or 0), "lever": i.get("lever"),
                "listTime": int(i.get("listTime") or 0) // 1000, "settleCcy": i.get("settleCcy"),
                "vol24h_usd": round(vol_usd), "last": last, "negociavel": "por confirmar (so o executor com chaves sabe)"}
        if base not in out or info["listTime"] > out[base]["listTime"]:
            out[base] = info
    return out


def atualizar_historico(hist, uni, now):
    """Historico do universo: primeira e ultima vez visto; os que desaparecem ficam marcados (deslistados ou
    suspensos) e continuam no ficheiro - base para medir survivorship."""
    for b, i in uni.items():
        h = hist.setdefault(b, {"primeiro": int(now), "inst": i["inst"], "classe": i["classe"]})
        h.update(ultimo=int(now), inst=i["inst"], ativo=True)
        h.pop("desaparecido_em", None)
    for b, h in hist.items():
        if b not in uni and h.get("ativo"):
            h.update(ativo=False, desaparecido_em=int(now))
    return {"novos": [b for b, h in hist.items() if h["primeiro"] == int(now)],
            "desaparecidos": [b for b, h in hist.items() if not h.get("ativo")]}


def tier(info, velas):
    """Negociabilidade pelos dados: volume de 24 h e fracao de velas sem volume nas ultimas 200."""
    zero = sum(1 for b in velas[-200:] if b["v"] <= 0) / max(1, min(200, len(velas)))
    v = info.get("vol24h_usd") or 0
    t = "A" if v >= 5e6 and zero < 0.02 else "B" if v >= 5e5 and zero < 0.10 else "C"
    return {"tier": t, "fracao_velas_sem_volume": round(zero, 3)}


def velas_30m(inst, inicio, fim, request=get, pausa=0.11):
    """Velas de 30 min FECHADAS (confirm=1) em [inicio, fim) por paginacao para tras; ordenadas e sem duplicados."""
    rows, cursor = {}, fim * 1000
    while cursor > inicio * 1000:
        d = request("/api/v5/market/history-candles", {"instId": inst, "bar": "30m", "after": cursor, "limit": 300})
        if d is None:
            return None
        if not d:
            break
        for x in d:
            t = int(x[0]) // 1000
            if inicio <= t < fim and len(x) > 8 and str(x[8]) == "1":
                rows[t] = {"t": t, "o": float(x[1]), "h": float(x[2]), "l": float(x[3]), "c": float(x[4]),
                           "v": float(x[5])}
        velho = min(int(x[0]) for x in d)
        if velho >= cursor:
            break
        cursor = velho
        if len(d) < 300:
            break
        if pausa:
            time.sleep(pausa)
    return [rows[t] for t in sorted(rows)]


def validar(velas, tf_s, now):
    """So erros FATAIS excluem: velas impossiveis, desalinhadas, buraco nas ultimas 50 ou dados atrasados."""
    if len(velas) < 120:
        return False, [f"historico curto ({len(velas)} velas)"]
    fatal = []
    if any(b["t"] % tf_s for b in velas):
        fatal.append("timestamps desalinhados")
    if any(min(b["o"], b["h"], b["l"], b["c"]) <= 0 or b["h"] < b["l"] for b in velas):
        fatal.append("precos impossiveis")
    rec = velas[-50:]
    if (rec[-1]["t"] - rec[0]["t"]) // tf_s + 1 != len(rec):
        fatal.append("buraco nas ultimas 50 velas")
    if now - (velas[-1]["t"] + tf_s) > 3 * tf_s:
        fatal.append("dados atrasados")
    return not fatal, fatal


def reamostrar(velas30, tf):
    """30m -> 1H/4H (so blocos completos e alinhados ao UTC)."""
    s = BAR[tf]
    if s == 1800:
        return list(velas30)
    k = s // 1800
    grupos = {}
    for b in velas30:
        grupos.setdefault(b["t"] // s * s, []).append(b)
    out = []
    for t in sorted(grupos):
        g = grupos[t]
        if len(g) != k:
            continue
        out.append({"t": t, "o": g[0]["o"], "h": max(x["h"] for x in g), "l": min(x["l"] for x in g),
                    "c": g[-1]["c"], "v": sum(x["v"] for x in g)})
    return out


def funding(inst, request=get):
    """[(t, taxa)] dos ultimos ~3 meses (limite da OKX). None se a API falhar."""
    rows, after = {}, None
    for _ in range(4):
        p = {"instId": inst, "limit": 100}
        if after:
            p["after"] = after
        d = request("/api/v5/public/funding-rate-history", p)
        if d is None:
            return None if not rows else sorted(rows.items())
        if not d:
            break
        for x in d:
            r = x.get("realizedRate") or x.get("fundingRate")
            if r not in (None, ""):
                rows[int(x["fundingTime"]) // 1000] = float(r)
        after = min(int(x["fundingTime"]) for x in d)
        if len(d) < 100:
            break
    return sorted(rows.items())


def recolher(dias=240, n_max=None, now=None, workers=4, request=get):
    """Universo completo + velas 30m + funding. Devolve (dados, funil_dados)."""
    now = int(now or time.time())
    uni = universo(request)
    bases = sorted(uni, key=lambda b: -uni[b]["vol24h_usd"])
    if n_max:
        bases = bases[:int(n_max)]
    fim = now // 1800 * 1800
    inicio = fim - int(dias) * 86400

    def um(b):
        i = uni[b]
        v = velas_30m(i["inst"], max(inicio, i["listTime"] // 1800 * 1800), fim, request)
        if v is None:                                  # API falhou: uma segunda tentativa mais lenta
            time.sleep(2)
            v = velas_30m(i["inst"], max(inicio, i["listTime"] // 1800 * 1800), fim, request, pausa=0.3)
        f = funding(i["inst"], request)
        return b, v, f
    with ThreadPoolExecutor(max_workers=workers) as ex:
        got = list(ex.map(um, bases))
    dados, motivos = {}, {}
    for b, v, f in got:
        if v is None:
            motivos[b] = ["API falhou"]
            continue
        ok, fat = validar(v, 1800, now)
        if not ok:
            motivos[b] = fat
            continue
        dados[b] = {"info": {**uni[b], **tier(uni[b], v)}, "30m": v, "funding": f or []}
    funil = {"instrumentos_descobertos": len(uni), "pedidos": len(bases), "com_dados_validos": len(dados),
             "excluidos": motivos, "por_classe": {c: sum(1 for d in dados.values() if d["info"]["classe"] == c)
                                                 for c in ("crypto", "equity", "precious_metal")},
             "por_tier": {t: sum(1 for d in dados.values() if d["info"]["tier"] == t) for t in "ABC"},
             "falhas_api": FALHAS.resumo()}
    return dados, uni, funil


def guardar_historico(caminho, uni, now):
    hist = {}
    if os.path.exists(caminho):
        with open(caminho, encoding="utf-8") as f:
            hist = json.load(f)
    mud = atualizar_historico(hist, uni, now)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=0)
    return mud
