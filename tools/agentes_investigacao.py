"""(11/11) Agentes de investigacao: funcoes com papel definido sobre dados identificaveis, com resultado estruturado
e reprodutivel. NAO executam ordens, nao alteram posicoes, parametros, estrategias, risco nem configuracoes: so leem
copias publicas e ficheiros de investigacao e escrevem um relatorio.

Avaliacao da arquitetura (11/11): nao e preciso infraestrutura nova nem servicos pagos. Cada "agente" e um modulo ja
existente com uma funcao clara, orquestrado aqui; correm no GitHub Actions como os outros estudos. Criar processos
separados ou modelos de linguagem por agente nao acrescentava evidencia, so complexidade; por isso nao foi feito.

Agentes e o que usam:
  dados        Data Quality: frescura, cobertura e falhas de cada fonte publica
  mercado      Market Intelligence: regimes da Bybit, BTC, radar do panico, liquidez
  oportunidades Global Opportunity Hunter (engine/oportunidades.py, tools/cacador_global.py)
  quant        Quant Research / Strategy Validation: tools/quant_robustez.py (se houver operacoes de backtest)
  execucao     Execution Intelligence: papel contra real no mesmo sinal (engine/risco_intel.papel_contra_real)
  risco        Risk Intelligence: engine/risco_intel.relatorio por estrategia e ambiente
  frequencia   funil de frequencia (tools/funil_frequencia.py)
Cada resultado separa FACTOS (medidos), HIPOTESES (por testar) e PREVISOES (nenhuma e feita sem evidencia), regista as
fontes com a hora e o comando para reproduzir.
Uso: python3 tools/agentes_investigacao.py <pasta_publica> <saida.json> [--hist <dir>] [--bt <bt_ops.json>] [--dn <csv>]"""
import json
import os
import subprocess
import sys
import time

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FONTES = {"okx.json": ("volta", "t"), "state.json": ("ordens_ok", "t"), "scan.json": (None, "generated_at"),
          "derivados.json": (None, "t"), "liquidez.json": None, "okx_tfshort.json": None}


def _commit():
    try:
        return subprocess.check_output(["git", "-C", RAIZ, "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return None


def _j(pasta, n):
    p = os.path.join(pasta, n)
    try:
        return json.load(open(p))
    except (OSError, ValueError):
        return None


def resultado(agente, funcao, fontes, factos, hipoteses=None, previsoes=None, evidencias=None, comando=None):
    return {"agente": agente, "funcao": funcao, "fontes": fontes, "factos": factos, "hipoteses": hipoteses or [],
            "previsoes": previsoes or [], "evidencias": evidencias or {},
            "reproducao": {"commit": _commit(), "comando": comando}, "autoridade": "nenhuma (so leitura)"}


def _t_iso(t):
    try:
        t = float(t)
    except (TypeError, ValueError):
        return t
    return time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime(t))


def agente_dados(pasta, now):
    fontes, factos = [], []
    for nome, chave in FONTES.items():
        d = _j(pasta, nome)
        if d is None:
            factos.append(f"{nome}: em falta")
            fontes.append({"nome": nome, "t": None, "estado": "em falta"})
            continue
        t = None
        if chave:
            sub, campo = chave
            v = d.get(sub) if sub else d
            t = (v or {}).get(campo) if isinstance(v, dict) else None
        if isinstance(t, str):
            try:
                t = time.mktime(time.strptime(t[:19], "%Y-%m-%dT%H:%M:%S")) - time.timezone
            except ValueError:
                t = None
        idade = None if t is None else round((now - float(t)) / 3600, 1)
        estado = "sem hora" if t is None else ("fresco" if idade <= 3 else "atrasado")
        fontes.append({"nome": nome, "t": _t_iso(t) if t else None, "idade_h": idade, "estado": estado})
        if estado == "atrasado":
            factos.append(f"{nome}: atualizado ha {idade} h")
    D = _j(pasta, "derivados.json") or {}
    buracos = {}
    for a, linhas in (D.get("moedas") or {}).items():
        ts = [l[0] for l in linhas if l]
        falhas = sum(1 for x, y in zip(ts, ts[1:]) if y - x > 2 * 3600)
        if falhas:
            buracos[a] = falhas
    if buracos:
        factos.append(f"derivados.json: {len(buracos)} moedas com intervalos > 2 h na serie horaria")
    L = _j(pasta, "liquidez.json") or {}
    paradas = [a for a, am in ((L.get("hoje") or {}).get("amostras") or {}).items() if am and am[-1][2]]
    if paradas:
        factos.append(f"liquidez.json: preco parado na Bybit UE em {len(paradas)} moedas ({', '.join(paradas[:8])})")
    S = _j(pasta, "scan.json") or {}
    c = S.get("counts") or {}
    if c:
        factos.append(f"scan: {c.get('data_valid')} de {c.get('deep_checked')} moedas com dados validos; {c.get('data_invalid')} invalidas")
    return resultado("dados", "Data Quality", fontes, factos, evidencias={"buracos_derivados": buracos, "precos_parados": paradas},
                     comando="python3 tools/agentes_investigacao.py <pasta> <saida>")


def agente_mercado(pasta):
    from collections import Counter
    St, O, S = _j(pasta, "state.json") or {}, _j(pasta, "okx.json") or {}, _j(pasta, "scan.json") or {}
    reg = Counter((r or {}).get("regime") for r in (St.get("regimes") or {}).values())
    rad = O.get("radar") or {}
    factos = [f"regimes das moedas da Bybit: {dict(reg.most_common())}",
              f"BTC: regime {((St.get('regimes') or {}).get('BTC') or {}).get('regime')}; 24 h {rad.get('btc_24h')}%",
              f"radar do panico (OKX): {len(rad.get('lista') or [])} moedas perto do criterio"]
    mf = S.get("market_filter") or {}
    if mf:
        factos.append(f"BTC {'acima' if mf.get('btc_above_sma200') else 'abaixo'} da media de 200 dias ({mf.get('distance_pct')}%)")
    hip = ["com a maioria das moedas em BEAR, as estrategias long em teste tem poucos sinais; so estrategias curtas com "
           "prova acrescentariam frequencia (nenhuma tem prova hoje: H44, H47, H48 chumbadas; H52 e H59 a acumular)"]
    return resultado("mercado", "Market Intelligence", [{"nome": "state.json"}, {"nome": "okx.json"}, {"nome": "scan.json"}], factos, hip)


def agente_oportunidades(pasta, hist, dn, saida_dir, now, evidencia_ic=None):
    if not hist:
        return resultado("oportunidades", "Global Opportunity Hunter", [], ["sem velas do ramo history: nao corrido"])
    import cacador_global as CG
    ev = CG.evidencia_de_ic(evidencia_ic) if evidencia_ic else None
    ops, p = CG.correr(hist, pasta, dn or "-", saida_dir, now, ev)
    from collections import Counter
    factos = [f"{len(p)} ativos analisados; {len(ops)} com pelo menos um detetor",
              f"direcoes: {dict(Counter(o['direcao_potencial'] for o in ops))}",
              f"qualidade dos dados: {dict(Counter(o['qualidade_dados']['nivel'] for o in ops))}",
              f"expectativa: {dict(Counter(o['expectativa_estimada'] for o in ops))}"]
    return resultado("oportunidades", "Global Opportunity Hunter (sombra)", [{"nome": "history 4H"}, {"nome": "derivados.json"}, {"nome": "dados-novos"}],
                     factos, hipoteses=[f"{o['ativo']} {o['direcao_potencial']}: {o['motivo']}" for o in ops[:10]],
                     previsoes=[], evidencias={"evidencia_ic": ev}, comando="python3 tools/cacador_global.py <hist> <pasta> <dn.csv> <saida> [ic.json ...]")


def agente_quant(pasta, bt):
    if not bt:
        return resultado("quant", "Quant Research / Strategy Validation", [], ["sem operacoes de backtest: nao corrido"])
    import quant_robustez as QR
    r = QR.correr(json.load(open(bt)), pasta)
    factos = []
    for k, a in r["resultados"].items():
        if a["n_operacoes"] >= 10:
            factos.append(f"{k}: {a['n_operacoes']} op. em {a['n_dias']} dias, R medio {a['media_r']}, p diario {a['teste_diario']['p_unilateral']}")
    factos += [f"Holm: {k} p ajustado {v['p_ajustado']} ({'rejeita' if v['rejeita'] else 'nao rejeita'} H0)" for k, v in r["holm_backtest"].items()]
    return resultado("quant", "Quant Research / Strategy Validation", [{"nome": "bt_ops"}, {"nome": "copias publicas"}], factos,
                     evidencias={"walk_forward": r["walk_forward"], "sensibilidade": r["sensibilidade"]},
                     comando="python3 tools/quant_robustez.py <bt_ops.json> <pasta> <saida.json> <saida.md>")


def agente_execucao(pasta):
    from engine import risco_intel as RI
    O = _j(pasta, "okx.json") or {}
    r = RI.papel_contra_real((O.get("real") or {}).get("hist") or [], O.get("fechadas") or [])
    factos = [f"{x['ativo']}: real {x['r_real_preco']:+.3f}R (so precos), papel {x['r_papel']}R" for x in r["pares"]]
    factos.append(f"diferenca media real - papel: {r['diferenca_media_r']}R em {r['n']} operacoes (amostra minima: nao generalizar)")
    return resultado("execucao", "Execution Intelligence", [{"nome": "okx.json"}], factos, evidencias=r)


def agente_risco(pasta, bt):
    from engine import risco_intel as RI
    from backtest.quant import dados as D
    ops = D.carregar(pasta)["operacoes"] + (json.load(open(bt))["operacoes"] if bt else [])
    out, factos = {}, []
    for amb, est, rp in (("BACKTEST", "H40 (panico do mercado)", 1.0), ("BACKTEST", "H46 (RSI<30)", 1.0),
                         ("PAPEL", "H40", 1.0), ("PAPEL", "H45", 2.0)):
        xs = [o for o in ops if o["ambiente"] == amb and o["estrategia"] == est]
        if not xs:
            continue
        r = RI.relatorio(xs, risco_pct=rp)
        out[f"{amb} | {est}"] = r
        factos += [f"{amb} {est}: {x}" for x in r["recomendacoes"]]
    return resultado("risco", "Risk Intelligence", [{"nome": "copias publicas"}, {"nome": "bt_ops"}], factos, evidencias=out)


def agente_frequencia(pasta):
    import funil_frequencia as F
    r = F.correr(pasta)
    return resultado("frequencia", "Funil de frequencia", [{"nome": "okx.json"}, {"nome": "scan.json"}, {"nome": "state.json"}],
                     r["diagnostico"], evidencias={"okx": r["okx"]["grupos"], "bybit": r["bybit"]["contagens"]})


def correr(pasta, saida, hist=None, bt=None, dn=None, ic=None, now=None):
    now = now or time.time()
    d = os.path.dirname(os.path.abspath(saida))
    ags = [agente_dados(pasta, now), agente_mercado(pasta), agente_oportunidades(pasta, hist, dn, d, now, ic),
           agente_quant(pasta, bt), agente_execucao(pasta), agente_risco(pasta, bt), agente_frequencia(pasta)]
    r = {"gerado": _t_iso(now), "agentes": ags}
    json.dump(r, open(saida, "w"), ensure_ascii=False, indent=1, default=str)
    return r


if __name__ == "__main__":
    a = sys.argv
    opt = lambda k: a[a.index(k) + 1] if k in a else None
    ic = [x for x in (opt("--ic") or "").split(",") if x]
    r = correr(a[1], a[2], hist=opt("--hist"), bt=opt("--bt"), dn=opt("--dn"), ic=ic or None)
    for g in r["agentes"]:
        print(f"== {g['agente']} ({g['funcao']})")
        for f in g["factos"][:12]:
            print("  -", f)
