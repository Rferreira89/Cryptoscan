"""(19/11, ordem do Rui, ponto 11) Linha de oportunidades RAPIDAS (30 min a 4 h): estudo de eventos em velas de 1 h.

So investigacao: nao gera sinais nem ordens. Hipoteses e parametros ESCRITOS ANTES de correr (sem afinar):
  R1 rutura com volume: fecho de 1 h acima do maximo das 24 h anteriores (LONG) / abaixo do minimo (SHORT) com volume
     >= 3x a media das 24 h -> continuacao.
  R2 falsa rutura: a vela passa o maximo (minimo) das 24 h anteriores mas fecha de novo dentro, abaixo (acima) do
     nivel -> reversao (SHORT depois de falsa rutura do maximo, LONG depois da do minimo).
  R3 atraso face ao BTC: o BTC move-se >= 2% numa hora; as moedas que nessa hora se moveram menos de metade disso no
     mesmo sentido -> seguem o BTC (entrada no sentido do BTC).
  R4 excesso: movimento de uma vela >= 3x o ATR(24) -> reversao.
Entrada na ABERTURA da vela seguinte; stop a 1,5x ATR(24); saida ao fim de 1, 2 ou 4 h (as tres, nunca escolhidas
depois) ou no stop (se a vela tocar o stop conta o stop, com o salto de abertura). Sem objetivo.
Custos (dois cenarios, por lado): OKX perpetuo taker 0,05% + deslize 0,05%; e o modelo da Bybit UE spot do ringue
0,25% + 0,1%. Funding/juros de 1-4 h ignorados (sao < 0,01%/h nos dados de hoje; ficam declarados como omitidos).
Validacao: descoberta = primeira metade das datas, fora da amostra = segunda metade (separadas no tempo); IC 90% por
bootstrap em blocos de DIA (eventos do mesmo dia nao sao independentes); referencia ao acaso: mesma moeda, mesmo lado,
mesma duracao e mesmo stop em horas sorteadas (mesmo numero de eventos), para separar o padrao da deriva do mercado.
Universo: moedas com historico de 1 h no ramo history (ver 'moedas'); as deslistadas NAO tem 1 h, por isso ha vies
de sobrevivencia (declarado). Uso: python3 -m tools.estudo_rapidas_1h <pasta_1h> <saida.json>"""
import json
import random
import sys
import time

from engine import backtest as B

H, DAY = 3600, 86400
HOLDS = (1, 2, 4)
# custo de IDA E VOLTA (comissao + deslize em cada lado); medidos a 19/11: OKX futuros taker 0,05%, Bybit UE 0,25%
# (maker e taker iguais na conta), deslize de entrada medido na Bybit ~6-7 bps
CUSTOS = {"okx_perp": 2 * (0.0005 + 0.0005), "bybit_spot_modelo": 2 * (0.0025 + 0.001)}
K_STOP = 1.5


def atr(c, i, n=24):
    tr = [max(c[k]["h"], c[k - 1]["c"]) - min(c[k]["l"], c[k - 1]["c"]) for k in range(i - n + 1, i + 1)]
    return sum(tr) / n


def eventos(a, c, btc_ret=None):
    """[(hipotese, i, lado)] com a vela i FECHADA."""
    out = []
    for i in range(25, len(c) - 5):
        out += eventos_em(a, c, i, btc_ret)
    return out


def eventos_em(a, c, i, btc_ret=None):
    """Eventos da vela i (fechada), so com as 24 velas anteriores: o mesmo codigo para o estudo e para a sombra."""
    out = []
    b = c[i]
    w = c[i - 24:i]
    hi, lo = max(x["h"] for x in w), min(x["l"] for x in w)
    vavg = sum(x["v"] for x in w) / 24
    at = atr(c, i)
    if not at:
        return out
    if b["c"] > hi and vavg and b["v"] >= 3 * vavg:
        out.append(("R1", i, 1))
    elif b["c"] < lo and vavg and b["v"] >= 3 * vavg:
        out.append(("R1", i, -1))
    if b["h"] > hi and b["c"] < hi:
        out.append(("R2", i, -1))
    elif b["l"] < lo and b["c"] > lo:
        out.append(("R2", i, 1))
    if abs(b["c"] - b["o"]) >= 3 * at:
        out.append(("R4", i, -1 if b["c"] > b["o"] else 1))
    if btc_ret is not None and a != "BTC":
        br = btc_ret.get(b["t"])
        if br is not None and abs(br) >= 0.02:
            mine = b["c"] / b["o"] - 1
            if mine * (1 if br > 0 else -1) < abs(br) / 2:
                out.append(("R3", i, 1 if br > 0 else -1))
    return out


def simular(c, i, lado, hold):
    """Retorno bruto (fracao) e R bruto da entrada na abertura de i+1, stop a 1,5 ATR, saida ao fim de 'hold' h."""
    e = c[i + 1]["o"]
    dist = K_STOP * atr(c, i)
    stop = e - lado * dist
    for j in range(i + 1, i + 1 + hold):
        b = c[j]
        if (lado > 0 and b["l"] <= stop) or (lado < 0 and b["h"] >= stop):
            px = min(stop, b["o"]) if lado > 0 else max(stop, b["o"])
            return lado * (px / e - 1), lado * (px - e) / dist, "stop"
    px = c[i + hold]["c"]
    return lado * (px / e - 1), lado * (px - e) / dist, "tempo"


def boot(por_dia, n=1500, seed=11):
    dias = [v for v in por_dia.values() if v]
    if len(dias) < 10:
        return None
    rng = random.Random(seed)
    ms = []
    for _ in range(n):
        xs = [x for _ in dias for x in dias[rng.randrange(len(dias))]]
        ms.append(sum(xs) / len(xs))
    ms.sort()
    return [round(ms[int(0.05 * n)], 4), round(ms[int(0.95 * n)], 4)]


def resumo(ops, custo):
    if not ops:
        return {"n": 0}
    pd = {}
    rs = []
    for o in ops:
        ret = o["ret"] - custo
        r = ret / o["dist_frac"] if o["dist_frac"] else 0.0
        rs.append(r)
        pd.setdefault(o["t"] // DAY, []).append(r)
    ganhos, perdas = sum(r for r in rs if r > 0), -sum(r for r in rs if r < 0)
    eq, pico, dd = 0.0, 0.0, 0.0
    for r in rs:
        eq += r
        pico = max(pico, eq)
        dd = min(dd, eq - pico)
    return {"n": len(rs), "dias_independentes": len(pd), "media_R": round(sum(rs) / len(rs), 4), "ic90_R": boot(pd),
            "acerto_pct": round(100 * sum(r > 0 for r in rs) / len(rs), 1),
            "profit_factor": round(ganhos / perdas, 2) if perdas else None, "drawdown_R": round(dd, 1),
            "custo_medio_R": round(sum(custo / o["dist_frac"] for o in ops if o["dist_frac"]) / len(ops), 3),
            "stop_pct": round(100 * sum(o["motivo"] == "stop" for o in ops) / len(ops), 1)}


def correr(pasta):
    data, ign = B.load_all(pasta, min_bars=2000, tf=H)
    btc = data.get("BTC") or []
    btc_ret = {b["t"]: b["c"] / b["o"] - 1 for b in btc}
    t_all = sorted({b["t"] for c in data.values() for b in c})
    meio = t_all[len(t_all) // 2]
    ops = []
    rng = random.Random(5)
    for a, c in data.items():
        idx = {b["t"]: k for k, b in enumerate(c)}
        evs = eventos(a, c, btc_ret)
        for hip, i, lado in evs:
            at = atr(c, i)
            for hold in HOLDS:
                if i + hold >= len(c):
                    continue
                ret, r, mot = simular(c, i, lado, hold)
                ops.append({"hip": hip, "ativo": a, "t": c[i]["t"], "lado": lado, "hold": hold, "ret": ret,
                            "dist_frac": K_STOP * at / c[i + 1]["o"], "motivo": mot, "acaso": False})
                # referencia ao acaso: mesma moeda, lado, duracao e regra de stop, numa hora sorteada
                j = rng.randrange(25, len(c) - 6)
                at_j = atr(c, j)
                if at_j:
                    ret2, _, mot2 = simular(c, j, lado, hold)
                    ops.append({"hip": hip, "ativo": a, "t": c[j]["t"], "lado": lado, "hold": hold, "ret": ret2,
                                "dist_frac": K_STOP * at_j / c[j + 1]["o"], "motivo": mot2, "acaso": True})
    out = {}
    for hip in ("R1", "R2", "R3", "R4"):
        for hold in HOLDS:
            for lado in (1, -1):
                g = [o for o in ops if o["hip"] == hip and o["hold"] == hold and o["lado"] == lado]
                chave = f"{hip}|{hold}h|{'LONG' if lado > 0 else 'SHORT'}"
                out[chave] = {}
                for nome, custo in CUSTOS.items():
                    out[chave][nome] = {
                        "descoberta": resumo([o for o in g if not o["acaso"] and o["t"] < meio], custo),
                        "fora_da_amostra": resumo([o for o in g if not o["acaso"] and o["t"] >= meio], custo),
                        "acaso_fora_da_amostra": resumo([o for o in g if o["acaso"] and o["t"] >= meio], custo)}
                out[chave]["bruto_fora_da_amostra"] = resumo([o for o in g if not o["acaso"] and o["t"] >= meio], 0.0)
    return {"moedas": sorted(data), "ignoradas": ign, "meio": time.strftime("%Y-%m-%d", time.gmtime(meio)),
            "de": time.strftime("%Y-%m-%d", time.gmtime(t_all[0])), "ate": time.strftime("%Y-%m-%d", time.gmtime(t_all[-1])),
            "resultados": out}


if __name__ == "__main__":
    t0 = time.time()
    r = correr(sys.argv[1])
    r["segundos"] = round(time.time() - t0, 1)
    with open(sys.argv[2], "w") as f:
        json.dump(r, f, ensure_ascii=False, indent=1)
    print(len(r["moedas"]), r["de"], r["meio"], r["ate"], r["segundos"])
