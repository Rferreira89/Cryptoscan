"""(18/11, incidente RENDER) Verificacao SO DE LEITURA, na OKX, das posicoes e ordens condicionais do piloto.

Fonte de verdade: a OKX (account/positions, trade/orders-algo-pending, trade/orders-algo-history). Nenhuma ordem.
No log (publico) so precos, estados e coberturas; tamanhos e margem vao so por Telegram (privado).
Uso: python3 tools/piloto_verificar.py [instId ...]   (sem argumentos: todas as posicoes FUTURES do piloto)"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import okx_exec as E  # noqa: E402
import piloto_id as PID  # noqa: E402


def verificar(priv, insts=None):
    pos = priv("GET", "/api/v5/account/positions?instType=FUTURES")
    if (pos or {}).get("code") != "0":
        return {"erro": f"positions: {(pos or {}).get('code')} {(pos or {}).get('msg')}"}
    out, privado = [], []
    for p in pos.get("data") or []:
        inst, q = p.get("instId"), float(p.get("pos") or 0)
        if not q or (insts and inst not in insts):
            continue
        dono = PID.do_piloto(priv, inst, int(p.get("cTime") or 0) - 1000 if p.get("cTime") else None)
        if not insts and dono is not True:
            continue
        lado = "LONG" if q > 0 else "SHORT"
        fecho = "buy" if lado == "SHORT" else "sell"
        algos = []
        for t in ("conditional", "oco", "trigger", "move_order_stop"):
            r = priv("GET", f"/api/v5/trade/orders-algo-pending?instId={inst}&ordType={t}")
            if (r or {}).get("code") != "0":
                algos.append({"erro": f"{t}: {(r or {}).get('code')}"})
                continue
            algos += [dict(a, _tipo=t) for a in r.get("data") or []]
        hist = []
        for t in ("conditional", "oco"):
            for estado in ("canceled", "effective", "order_failed"):
                r = priv("GET", f"/api/v5/trade/orders-algo-history?instType=FUTURES&ordType={t}&state={estado}&limit=20")
                hist += [dict(a, _tipo=t) for a in (r or {}).get("data") or [] if a.get("instId") == inst]
        stops = [a for a in algos if a.get("slTriggerPx") and a.get("side") == fecho]
        tps = [a for a in algos if a.get("tpTriggerPx") and a.get("side") == fecho]
        coberto = sum(float(a.get("sz") or 0) for a in stops if not a.get("closeFraction")) + \
            (abs(q) if any(a.get("closeFraction") == "1" for a in stops) else 0)
        ent = float(p.get("avgPx") or 0)
        sl_ok = [a for a in stops if (lado == "SHORT" and float(a["slTriggerPx"]) > ent) or (lado == "LONG" and float(a["slTriggerPx"]) < ent)]
        out.append({"inst": inst, "do_piloto": dono, "lado": lado, "preco_medio": ent, "alavancagem": p.get("lever"), "margem_modo": p.get("mgnMode"),
                    "stops_ativos": [{"tipo": a["_tipo"], "trigger": a["slTriggerPx"], "lado_fecho": a.get("side"), "estado": a.get("state"),
                                      "reduce_only": a.get("reduceOnly"), "fecha_posicao": a.get("closeFraction") == "1",
                                      "algoClOrdId_piloto": str(a.get("algoClOrdId") or "").startswith("pil")} for a in stops],
                    "stop_do_lado_certo": bool(sl_ok), "cobertura_do_stop": round(min(coberto, abs(q)) / abs(q), 3) if q else None,
                    "take_profit_ativo": [{"trigger": a["tpTriggerPx"], "tipo": a["_tipo"]} for a in tps],
                    "algos_de_outros_lados_ou_sem_stop": len(algos) - len(stops),
                    "historico_algos": [{"tipo": a["_tipo"], "estado": a.get("state"), "sl": a.get("slTriggerPx"), "tp": a.get("tpTriggerPx"),
                                         "uTime": a.get("uTime")} for a in hist][:10],
                    "erros": [a["erro"] for a in algos if "erro" in a]})
        privado.append(f"{inst}: {lado} {abs(q):g} contratos, preco medio {ent}, margem {p.get('margin')} {p.get('ccy') or ''}, "
                       f"{p.get('lever')}x {p.get('mgnMode')}; stop cobre {coberto:g}/{abs(q):g}")
    return {"posicoes": out, "_privado": privado}


if __name__ == "__main__":
    r = verificar(E.privado, sys.argv[1:] or None)
    priv = r.pop("_privado", [])
    print(json.dumps(r, ensure_ascii=False, indent=1))
    if priv:
        try:
            from engine import alerts
            alerts.send("🔎 Piloto OKX — verificação na OKX (só leitura):\n" + "\n".join(priv))
        except Exception as e:
            print("telegram falhou:", type(e).__name__)
