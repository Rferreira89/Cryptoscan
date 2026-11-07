"""(07/11, pedido do Rui) Agente KRONOS em SOMBRA na OKX EEA: um modelo aberto de previsao de velas (Kronos-small,
shiyu-coder/Kronos, licenca MIT) preve as proximas 24 horas; o agente regista o que um executor faria com 20 USD, sem
tocar na corretora.

Garantias (iguais as do TF-SHORT em sombra): so a API PUBLICA da OKX (GET); sem chaves; sem caminho de escrita; nao
importa nenhum executor real. Zero ordens, zero posicoes reais.

HIPOTESE K1 — REGISTADA EM 07/11/2026 ANTES DE QUALQUER RESULTADO (nao se mudam regras depois; mudar = hipotese nova):
  Universo fixo (UNIVERSO): 20 criptomoedas liquidas; so entram as que tiverem X-Perp na OKX EEA.
  Uma vez por dia (~00:31 UTC): entrada = as ultimas 400 velas de 1 hora FECHADAS do perpetuo global OKX (<MOEDA>-USDT-SWAP);
    16 trajetorias independentes de 24 horas (temperatura 1,0, top_p 0,9).
    f = mediana de (fecho previsto a 24 h / ultimo fecho - 1); acordo = fracao das trajetorias com o mesmo sinal de f.
  LONG se f >= +1,0% e acordo >= 0,75; SHORT se f <= -1,0% e acordo >= 0,75. No maximo 5 por dia (maior |f| x acordo).
  Entrada a mercado no X-Perp ao preco medio do livro real. Stop a 1,5 x (amplitude diaria media dos ultimos 14 dias).
  Sem objetivo: sai ao fim de ~24 h (na volta seguinte) a mercado, ou no stop (velas de 1 h do X-Perp).
  Tamanho: risco de 1% da conta ficticia ate ao stop; alavancagem maxima 3x por posicao e 3x no total; minimo do
    contrato respeitado (se nao cabe, fica registado como nao executavel com o capital que seria preciso).
  Custos: comissao 0,05% por lado, spread e deslize medidos no livro, deslize de 0,1% no stop, financiamento real.
  Controlo: em cada operacao calcula-se tambem o R da direcao ingenua (sinal do retorno das ultimas 24 h) com a mesma
    entrada, stop e saida. E regista-se a previsao de TODAS as moedas todos os dias (acerto de direcao).
  CRITERIO (avaliado so quando houver >= 30 operacoes fechadas, so com dados posteriores a este registo):
    R medio liquido > 0; reamostragem unilateral p < 0,05; R medio > R medio do controlo ingenuo.
  Nao ha backtest: o Kronos foi pre-treinado com velas ate 2025 (inclui cripto), por isso qualquer teste em dados antigos
  estaria contaminado e nao seria validacao.

Uso: python3 tools/kronos_sombra.py <estado.json> [--gravar] [--iniciar] [--ensaio] [--kronos <pasta do codigo>]"""
import json
import math
import os
import random
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from tools import tfs_sombra as TS  # noqa: E402  (so leitura publica, GET)

REGISTO = "2026-11-07"
VERSAO = 1
UNIVERSO = ("BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "AVAX", "LINK", "LTC", "BCH",
            "DOT", "SUI", "TRX", "NEAR", "APT", "ARB", "OP", "UNI", "AAVE", "FIL")
CAPITAL0 = 20.0
RISCO = 0.01
ALAV_POS = 3.0
ALAV_TOTAL = 3.0
MAX_DIA = 5
LIMIAR = 0.01
ACORDO = 0.75
STOP_X = 1.5
CONTEXTO = 400
HORIZONTE = 24
TRAJ = 16
COMISSAO = TS.COMISSAO
DESLIZE_STOP = TS.DESLIZE_STOP
MODELO = "NeoQuasar/Kronos-small"
TOKENIZER = "NeoQuasar/Kronos-Tokenizer-base"
H = 3600


class Publico(TS.Publico):
    def velas_perp(self, moeda, n=CONTEXTO):
        """Ultimas n velas de 1 h FECHADAS do perpetuo global (mais antiga primeiro). None se a leitura falha."""
        out, depois = [], ""
        while len(out) < n:
            d = TS._get(f"/api/v5/market/history-candles?instId={moeda}-USDT-SWAP&bar=1H&limit=100{depois}")
            if d is None:
                return None
            if not d:
                break
            out += [{"t": int(x[0]) // 1000, "o": float(x[1]), "h": float(x[2]), "l": float(x[3]), "c": float(x[4]),
                     "v": float(x[5])} for x in d if len(x) > 8 and x[8] == "1"]
            depois = f"&after={d[-1][0]}"
        out = sorted({v["t"]: v for v in out}.values(), key=lambda v: v["t"])
        return out[-n:] if len(out) >= n else None


class PrevisorKronos:
    """Carrega o Kronos (codigo clonado numa versao fixa + pesos do Hugging Face). So corre no servidor."""
    def __init__(self, pasta_codigo, device="cpu", revisoes=None):
        """revisoes: {repo: sha} fixadas no primeiro dia; o modelo nao pode mudar a meio da hipotese."""
        sys.path.insert(0, pasta_codigo)
        import torch  # noqa: F401
        from huggingface_hub import HfApi
        from model import Kronos, KronosTokenizer, KronosPredictor
        rev = dict(revisoes or {})
        for repo in (TOKENIZER, MODELO):
            if not rev.get(repo):
                rev[repo] = HfApi().model_info(repo).sha
        self.revisoes = rev
        self.tok = KronosTokenizer.from_pretrained(TOKENIZER, revision=rev[TOKENIZER])
        self.mod = Kronos.from_pretrained(MODELO, revision=rev[MODELO])
        self.pred = KronosPredictor(self.mod, self.tok, device=device, max_context=512)

    def trajetorias(self, series, n=TRAJ, horizonte=HORIZONTE, semente=0):
        """series: {moeda: [velas]} -> {moeda: [n fechos previstos a +horizonte horas]}."""
        import numpy as np
        import pandas as pd
        import torch
        torch.manual_seed(semente); np.random.seed(semente); random.seed(semente)
        dfs, xs, ys, quem = [], [], [], []
        for m, v in series.items():
            df = pd.DataFrame({"open": [x["o"] for x in v], "high": [x["h"] for x in v], "low": [x["l"] for x in v],
                               "close": [x["c"] for x in v], "volume": [x["v"] for x in v]})
            xt = pd.Series(pd.to_datetime([x["t"] for x in v], unit="s"))
            yt = pd.Series(pd.to_datetime([v[-1]["t"] + H * (i + 1) for i in range(horizonte)], unit="s"))
            for _ in range(n):
                dfs.append(df); xs.append(xt); ys.append(yt); quem.append(m)
        out = {}
        res = self.pred.predict_batch(dfs, xs, ys, pred_len=horizonte, T=1.0, top_p=0.9, sample_count=1, verbose=False)
        for m, p in zip(quem, res):
            out.setdefault(m, []).append(float(p["close"].iloc[-1]))
        return out


# ---------- regra K1 (pura, testavel) ----------
def amplitude_diaria(velas, dias=14):
    """Media da amplitude (maximo - minimo) / fecho dos ultimos `dias` dias completos, a partir das velas de 1 h."""
    blocos = [velas[-24 * (i + 1): len(velas) - 24 * i] for i in range(dias)]
    amps = [(max(x["h"] for x in b) - min(x["l"] for x in b)) / b[-1]["c"] for b in blocos if len(b) == 24]
    return sum(amps) / len(amps) if amps else None


def sinal(ultimo, fechos):
    """(direcao, f, acordo). direcao None se nao cumpre a regra."""
    rets = sorted(c / ultimo - 1 for c in fechos)
    n = len(rets)
    f = rets[n // 2] if n % 2 else (rets[n // 2 - 1] + rets[n // 2]) / 2
    acordo = sum(1 for r in rets if (r > 0) == (f > 0) and r != 0) / n
    if f >= LIMIAR and acordo >= ACORDO:
        return "LONG", f, acordo
    if f <= -LIMIAR and acordo >= ACORDO:
        return "SHORT", f, acordo
    return None, f, acordo


def contratos(capital, stop_pct, px, info, em_uso):
    """Contratos pelo risco (1% ate ao stop), limitados a 3x por posicao e 3x no total. (n, motivo ou None)."""
    alvo = capital * RISCO / stop_pct
    alvo = min(alvo, capital * ALAV_POS, max(0.0, capital * ALAV_TOTAL - em_uso))
    lote = info.get("lotSz") or info["minSz"]
    n = math.floor(alvo / (info["ctVal"] * px) / lote + 1e-9) * lote if info["ctVal"] and px and lote else 0
    if alvo <= 0:
        return 0, "alavancagem_total"
    if n < info["minSz"] or n <= 0:
        return 0, "abaixo_minimo_do_contrato"
    return round(n, 10), None


def capital_minimo(stop_pct, px, info):
    """Capital com que o minimo do contrato caberia com 1% de risco e o teto de 3x."""
    nocional = info["minSz"] * info["ctVal"] * px
    return round(max(nocional * stop_pct / RISCO, nocional / ALAV_POS), 2)


def r_de(lado, entrada, saida, stop, nocional_entrada, fund):
    """R liquido de uma operacao (comissoes nos dois lados e financiamento)."""
    s = 1 if lado == "LONG" else -1
    bruto = s * (saida / entrada - 1)
    custo = COMISSAO * (1 + saida / entrada)
    fin = -s * fund                                          # long paga financiamento positivo; short recebe
    risco = abs(stop / entrada - 1)
    return (bruto - custo + fin) / risco if risco else None, nocional_entrada * (bruto - custo + fin)


# ---------- estado ----------
def novo():
    return {"registo": REGISTO, "capital": CAPITAL0, "abertas": {}, "fechadas": [], "previsoes": [], "nao_executaveis": [],
            "voltas": [], "modelo": MODELO}


def carregar(caminho, iniciar=False):
    if not os.path.exists(caminho):
        return novo(), bool(iniciar), "estado inicializado (autorizado)" if iniciar else "estado inexistente"
    try:
        corpo = json.load(open(caminho))
    except Exception:
        return novo(), False, "estado ilegivel"
    est = corpo.get("estado") or {}
    if corpo.get("versao") != VERSAO:
        return est or novo(), False, "versao desconhecida"
    if corpo.get("soma") != TS._soma(est):
        return est, False, "estado adulterado (soma nao confere)"
    return est, True, "ok"


def guardar(caminho, est):
    tmp = caminho + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"versao": VERSAO, "estado": est, "soma": TS._soma(est)}, f, ensure_ascii=False)
    os.replace(tmp, caminho)


# ---------- uma volta ----------
def _toque(lado, stop, velas):
    """Primeira vela que toca o stop -> preco de saida (stop ou abertura se abriu para la dele) com deslize."""
    for v in velas:
        if lado == "LONG" and v["l"] <= stop:
            return v["t"], min(stop, v["o"]) * (1 - DESLIZE_STOP)
        if lado == "SHORT" and v["h"] >= stop:
            return v["t"], max(stop, v["o"]) * (1 + DESLIZE_STOP)
    return None


def _fechar(est, op, t, fund):
    R, pnl = r_de(op["lado"], op["px_fill"], op["saida"], op["stop"], op["nocional"], fund)
    c = op["controlo"]
    Rc, _ = r_de(c["lado"], op["px_fill"], c["saida"], c["stop"], op["nocional"], fund)
    fe = dict(op, t_saida=op.get("t_saida") or t, fund=round(fund, 6), R=round(R, 3) if R is not None else None,
              R_controlo=round(Rc, 3) if Rc is not None else None, pnl_usd=round(pnl, 6))
    est["capital"] = round(est["capital"] + pnl, 6)
    est["fechadas"].append(fe)
    del est["abertas"][op["moeda"]]


def volta(est, ok_estado, motivo_estado, pub, previsor, agora):
    res = {"t": agora, "entradas": 0, "saidas": 0, "sinais": 0, "nao_executaveis": 0, "falhas": [], "entradas_bloqueadas": None}
    infos = pub.instrumentos()
    if infos is None:
        res["falhas"].append("instrumentos indisponiveis")
        ok_estado, motivo_estado, infos = False, "instrumentos da OKX indisponiveis", {}
    # 1) gerir abertas: stops (agente e controlo, cada um o seu) nas velas de 1 h do X-Perp; saida ao fim de ~24 h
    for m, op in list(est["abertas"].items()):
        velas = pub.velas_1h(op["inst"], op.get("visto_ate") or op["t_fill"])
        if velas is None:
            res["falhas"].append(f"{m}: velas indisponiveis"); continue
        velas = [v for v in velas if v["t"] < op["t_fill"] + 24 * H]
        if op.get("saida") is None:
            tq = _toque(op["lado"], op["stop"], velas)
            if tq:
                op["t_saida"], op["saida"], op["motivo"] = tq[0], round(tq[1], 10), "stop"
        c = op["controlo"]
        if c.get("saida") is None:
            tq = _toque(c["lado"], c["stop"], velas)
            if tq:
                c["saida"], c["motivo"] = round(tq[1], 10), "stop"
        if velas:
            op["visto_ate"] = velas[-1]["t"] + H
        if agora - op["t_fill"] < 23 * H and (op.get("saida") is None or c.get("saida") is None):
            continue
        if op.get("saida") is None or c.get("saida") is None:
            liv = pub.livro(op["inst"])
            if liv is None or not liv.get("bids") or not liv.get("asks"):
                res["falhas"].append(f"{m}: sem livro para sair (tenta na proxima volta)"); continue
            for quem in (op, c):
                if quem.get("saida") is None:
                    lado_livro = liv["bids"] if quem["lado"] == "LONG" else liv["asks"]
                    px = TS.preco_medio(lado_livro, op["contratos"]) or lado_livro[0][0]
                    quem["saida"], quem["motivo"] = round(px, 10), "24h"
                    if quem is op:
                        op["t_saida"] = agora
        fh = pub.financiamento(op["inst"])
        fund = sum(x for t, x in (fh or []) if op["t_fill"] < t <= (op.get("t_saida") or agora))
        if fh is None:
            op["custos_incompletos"] = "financiamento indisponivel"
        _fechar(est, op, agora, fund)
        res["saidas"] += 1
    # 2) previsoes do dia (todas as moedas) e entradas
    if not ok_estado:
        res["entradas_bloqueadas"] = motivo_estado
        est["voltas"] = (est.get("voltas") or [])[-60:] + [res]
        return res
    dia = agora // 86400 * 86400
    if any(p["dia"] == dia for p in est["previsoes"][-len(UNIVERSO):]):
        res["entradas_bloqueadas"] = "previsoes de hoje ja feitas"
        est["voltas"] = (est.get("voltas") or [])[-60:] + [res]
        return res
    series = {}
    for m in UNIVERSO:
        v = pub.velas_perp(m)
        if v is None or len(v) < CONTEXTO or v[-1]["t"] < dia - 2 * H:
            res["falhas"].append(f"{m}: velas do perpetuo indisponiveis"); continue
        series[m] = v
    if not series:
        res["entradas_bloqueadas"] = "sem dados"
        est["voltas"] = (est.get("voltas") or [])[-60:] + [res]
        return res
    traj = previsor.trajetorias(series)
    cands = []
    for m, v in series.items():
        lado, f, acordo = sinal(v[-1]["c"], traj[m])
        mom = v[-1]["c"] / v[-25]["c"] - 1
        est["previsoes"].append({"dia": dia, "moeda": m, "ultimo": v[-1]["c"], "t_ultimo": v[-1]["t"], "f": round(f, 5),
                                 "acordo": round(acordo, 3), "lado": lado, "momento_24h": round(mom, 5)})
        if lado:
            cands.append((abs(f) * acordo, m, lado, f, acordo, mom, v))
    res["sinais"] = len(cands)
    em_uso = sum(o["nocional"] for o in est["abertas"].values())
    for _, m, lado, f, acordo, mom, v in sorted(cands, reverse=True)[:MAX_DIA]:
        reg = {"dia": dia, "moeda": m, "lado": lado, "f": round(f, 5), "acordo": round(acordo, 3)}
        info = infos.get(m)
        amp = amplitude_diaria(v)
        motivo = None
        if m in est["abertas"]:
            motivo = "ja_aberta"
        elif not info:
            motivo = "sem_instrumento_okx_eea"
        elif not amp:
            motivo = "sem_amplitude"
        liv = None
        if not motivo:
            liv = pub.livro(info["inst"])
            if liv is None:
                res["falhas"].append(f"{m}: livro indisponivel"); continue
            if not liv["bids"] or not liv["asks"]:
                motivo = "sem_livro_de_ordens"
        if not motivo:
            stop_pct = STOP_X * amp
            ref = liv["asks"][0][0] if lado == "LONG" else liv["bids"][0][0]
            n, motivo = contratos(est["capital"], stop_pct, ref, info, em_uso)
            reg["capital_minimo_usd"] = capital_minimo(stop_pct, ref, info)
            if not motivo:
                px = TS.preco_medio(liv["asks"] if lado == "LONG" else liv["bids"], n)
                if px is None:
                    motivo = "livro_sem_profundidade"
        if motivo:
            reg["motivo"] = motivo
            est["nao_executaveis"].append(reg); res["nao_executaveis"] += 1
            continue
        s = 1 if lado == "LONG" else -1
        stop = TS.arred_tick(px * (1 - s * stop_pct), info["tickSz"], cima=(lado == "SHORT"))
        cl = "LONG" if mom > 0 else "SHORT"
        sc = 1 if cl == "LONG" else -1
        meio = (liv["asks"][0][0] + liv["bids"][0][0]) / 2
        nocional = n * info["ctVal"] * px
        est["abertas"][m] = {"moeda": m, "inst": info["inst"], "lado": lado, "dia": dia, "t_fill": agora, "f": round(f, 5),
                             "acordo": round(acordo, 3), "contratos": n, "ctVal": info["ctVal"], "px_fill": round(px, 10),
                             "stop": stop, "stop_pct": round(stop_pct, 5), "objetivo": None, "saida_prevista": "24 h",
                             "nocional": round(nocional, 6), "spread_pct": round(liv["asks"][0][0] / meio - 1, 6),
                             "deslize_pct": round(abs(px / ref - 1), 6), "comissao_pct": COMISSAO,
                             "saida": None, "motivo": None,
                             "controlo": {"lado": cl, "stop": round(px * (1 - sc * stop_pct), 10), "saida": None, "motivo": None},
                             "capital_minimo_usd": reg["capital_minimo_usd"]}
        em_uso += nocional
        res["entradas"] += 1
    est["previsoes"] = est["previsoes"][-20 * 400:]
    est["nao_executaveis"] = est["nao_executaveis"][-1000:]
    est["voltas"] = (est.get("voltas") or [])[-60:] + [res]
    return res


def acerto(est):
    """Acerto de direcao das previsoes ja maduras (precisa do fecho 24 h depois: vem da previsao do dia seguinte)."""
    por = {}
    for p in est.get("previsoes") or []:
        por.setdefault(p["moeda"], {})[p["dia"]] = p
    ok = n = 0
    for m, d in por.items():
        for dia, p in d.items():
            q = d.get(dia + 86400)
            if q and p["f"]:
                n += 1; ok += (q["ultimo"] / p["ultimo"] - 1 > 0) == (p["f"] > 0)
    return {"n": n, "acerto_pct": round(100 * ok / n, 1) if n else None}


def resumo(est):
    F = [f for f in est.get("fechadas") or [] if f.get("R") is not None]
    mot = {}
    for x in est.get("nao_executaveis") or []:
        mot[x["motivo"]] = mot.get(x["motivo"], 0) + 1
    return {"abertas": {m: o["lado"] for m, o in (est.get("abertas") or {}).items()}, "fechadas": len(F),
            "soma_r": round(sum(f["R"] for f in F), 3), "soma_r_controlo": round(sum(f.get("R_controlo") or 0 for f in F), 3),
            "nao_executaveis": mot, "previsoes": acerto(est)}


def main(argv):
    caminho = argv[0]
    gravar, iniciar, ensaio = "--gravar" in argv, "--iniciar" in argv, "--ensaio" in argv
    pasta = argv[argv.index("--kronos") + 1] if "--kronos" in argv else os.environ.get("KRONOS_CODIGO", "")
    est, ok, motivo = carregar(caminho, iniciar=iniciar or ensaio)
    t0 = time.time()
    previsor = PrevisorKronos(pasta, revisoes=est.get("revisoes"))
    est.setdefault("revisoes", previsor.revisoes)
    res = volta(est, ok, motivo, Publico(), previsor, int(time.time()))
    out = {"volta": {k: v for k, v in res.items() if k != "t"}, "resumo": resumo(est), "segundos": round(time.time() - t0)}
    if ensaio:
        out["previsoes_hoje"] = [{k: p[k] for k in ("moeda", "f", "acordo", "lado")} for p in est["previsoes"][-len(UNIVERSO):]]
    print(json.dumps(out, ensure_ascii=False))
    if gravar and not ensaio:
        guardar(caminho, est)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
