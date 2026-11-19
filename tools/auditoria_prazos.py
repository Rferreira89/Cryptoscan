"""(19/11) So leitura: o prazo e a protecao da XLM como os ESTADOS CIFRADOS os guardam (Bybit: cofre_state.json e
exec.json; OKX: okx.json). Imprime so estados, horas e verdadeiro/falso; nada de tamanhos nem dinheiro."""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from engine import cifra  # noqa: E402
from engine import executor as X  # noqa: E402

ID = "XLM-SHORT_TURTLE-1794673840"
T = lambda t: time.strftime("%Y-%m-%d %H:%M", time.gmtime(t)) if t else None


def ramo(r, f):
    subprocess.run(["git", "fetch", "-q", "--depth", "1", "origin", r], check=False)
    return subprocess.run(["git", "show", f"FETCH_HEAD:{f}"], capture_output=True, text=True).stdout


out = {}
try:
    st = cifra.abrir_obj(json.loads(ramo("data", "cofre_state.json")))
    s = (st.get("signals") or {}).get(ID) or {}
    p = s.get("position") or {}
    out["bybit_estado_completo"] = {"auto_ops": (st.get("auto_ops") or {}).get(ID), "sinal": s.get("status"),
                                    "max_hold_dias": (p.get("max_hold") or 0) / 86400, "aberta_em": T(p.get("opened_at")),
                                    "saida_por_tempo_em": T((p.get("opened_at") or 0) + (p.get("max_hold") or 0)),
                                    "ledger": next((r.get("status") for r in st.get("ledger") or [] if r.get("id") == ID), None),
                                    "pedidos_pendentes": [r.get("acao") for r in st.get("exec_req") or [] if r.get("op") == ID]}
except Exception as e:
    out["bybit_estado_erro"] = f"{type(e).__name__}: {str(e)[:80]}"
try:
    ex = cifra.abrir_obj(json.loads(ramo("execucoes", "exec.json")))
    op = (ex.get("ops") or {}).get(ID) or {}
    ids = {q.get("filho") for q in op.get("partes") or []} | {q.get("stopId") for q in op.get("partes") or []}
    ids.discard(None)
    import collections
    out["bybit_executor_estados"] = dict(collections.Counter(str(o.get("status")) for o in (ex.get("ops") or {}).values()
                                                              if isinstance(o, dict)))
    out["bybit_executor_nao_finais"] = [(k[:40], o.get("status"), o.get("lado")) for k, o in (ex.get("ops") or {}).items()
                                         if isinstance(o, dict) and o.get("status") not in ("fechada", "cancelada", "recusada")]
    out["bybit_executor"] = {"estado": op.get("status"), "lado": op.get("lado"), "tem_stop_no_registo": bool(op.get("stop")),
                             "tem_emprestado_moeda": op.get("emprestado_moeda") is not None, "n_partes": len(op.get("partes") or []),
                             "criado": T(op.get("criado") or op.get("t"))}
    try:
        from engine import account as AC
        X.get = AC.get                    # so a chave de LEITURA (engine/account); nunca a de negociacao
        prot = X.tpsl_orders("XLMUSDC")
        nossos = X.ours(prot, op)
        out["bybit_executor"].update(protecoes_na_bybit=len(prot), encontradas_pelo_fecho=len(nossos),
                                     por_id_guardado=sum(o["orderId"] in ids for o in prot))
    except Exception as e:
        out["bybit_executor"]["leitura_ordens_erro"] = type(e).__name__
except Exception as e:
    out["bybit_executor_erro"] = f"{type(e).__name__}: {str(e)[:80]}"
print("AUDITORIA_PRAZOS " + json.dumps(out, ensure_ascii=False))
