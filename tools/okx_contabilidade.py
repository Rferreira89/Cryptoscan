"""(11/11, auditoria P4) Contabilidade REAL da OKX, so de leitura.

Le na OKX (so GET; qualquer outro metodo e recusado ANTES de sair do programa):
  /api/v5/account/positions-history  -> preco medio de abertura e fecho, PnL de preco (pnl), comissoes (fee),
                                         funding (fundingFee), penalizacao de liquidacao e PnL realizado (liquido)
  /api/v5/trade/fills-history         -> execucoes (preco, taker/maker) para o deslize na entrada e na saida
e junta com o registo publico do executor (okx.json real.hist: estrategia, limite, stop, motivo).

Saidas:
  <pasta>/contabilidade_okx_privado.json -> com dinheiro; cifrado logo a seguir com engine.cifra (DATA_KEY).
                                            Sem DATA_KEY o ficheiro privado NAO e escrito.
  <pasta>/contabilidade_okx.json         -> publico: so contagens, R e percentagens (engine.contabilidade.publico),
                                            verificado por sem_dinheiro antes de gravar.
Credenciais: as do executor (OKX_API_KEY/SECRET/PASSPHRASE). Nao cria chaves. Bloqueio conhecido: a chave do
executor tem permissao de negociacao; o leitor so usa GET, e o teste estatico garante que nao ha outro metodo.
Uso: python3 tools/okx_contabilidade.py <okx.json> <pasta_saida>"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine import contabilidade as C  # noqa: E402


class SoLeitura(Exception):
    pass


def leitura(path):
    """Unico acesso privado deste modulo: GET assinado pelo cliente do executor."""
    import okx_exec
    return okx_exec.privado("GET", path)


def _guarda(metodo):
    if metodo != "GET":
        raise SoLeitura(f"metodo {metodo} recusado: a contabilidade e so de leitura")


def historico_posicoes(ler=leitura, paginas=5):
    out, depois = [], None
    for _ in range(paginas):
        q = "/api/v5/account/positions-history?instType=FUTURES&limit=100" + (f"&after={depois}" if depois else "")
        r = ler(q)
        d = r.get("data") or []
        if r.get("code") != "0":
            raise RuntimeError(f"positions-history: {r.get('code')} {str(r.get('msg'))[:60]}")
        out += d
        if len(d) < 100:
            break
        depois = d[-1].get("uTime")
    return out


def execucoes(inst, ler=leitura):
    r = ler(f"/api/v5/trade/fills-history?instType=FUTURES&instId={inst}&limit=100")
    return r.get("data") or [] if r.get("code") == "0" else None


def _registo_do_executor(hist, inst, t_abre, t_fecha):
    """Operacao do executor para a mesma posicao: mesmo contrato, executada perto da abertura da posicao."""
    cands = [h for h in hist if h.get("inst") == inst and h.get("estado") == "fechada"]
    if not cands:
        return None
    return min(cands, key=lambda h: abs(float(h.get("t_fill") or h.get("criado") or 0) - t_abre))


def _motivo(h, x):
    tipo = str(x.get("type") or "")
    if tipo in ("3", "4"):
        return "liquidacao"
    if tipo == "5":
        return "adl"
    m = (h or {}).get("motivo") or ""
    if m.startswith("tempo"):
        return "tempo"
    if m == "stop ou objetivo" and h:
        px = float(x.get("closeAvgPx") or 0)
        alvo, stop = h.get("alvo"), h.get("stop")
        if alvo and stop and px:
            return "objetivo" if abs(px - alvo) < abs(px - stop) else "stop"
    return m or None


def construir(posicoes, hist, fills_de=None):
    """Lista de operacoes normalizadas (engine.contabilidade.operacao) a partir dos dados lidos."""
    ops = []
    for x in posicoes:
        inst = x.get("instId") or ""
        t_abre = int(x.get("cTime") or 0) / 1000
        t_fecha = int(x.get("uTime") or 0) / 1000
        h = _registo_do_executor(hist, inst, t_abre, t_fecha)
        lado = "SHORT" if x.get("direction") == "short" or x.get("posSide") == "short" else "LONG"
        pnl = C._f(x.get("pnl"))
        fee = C._f(x.get("fee"))
        fund = C._f(x.get("fundingFee"))
        liq = C._f(x.get("liqPenalty"))
        real = C._f(x.get("realizedPnl"))
        if real is None and pnl is not None:
            real = pnl + (fee or 0) + (fund or 0) + (liq or 0)
        o = C.operacao("okx", (h or {}).get("estrategia") or ("panico" if h else "manual?"), inst.split("-")[0], lado,
                       x.get("openAvgPx"), x.get("closeAvgPx"), (h or {}).get("stop"), pnl_preco=pnl, pnl_liquido=real,
                       comissoes=fee, funding=fund, penalizacao=liq, limite=(h or {}).get("lim"),
                       motivo=_motivo(h, x), t_abertura=t_abre, t_fecho=t_fecha)
        o["no_executor"] = bool(h)
        if fills_de:
            fs = fills_de(inst)
            if fs:
                o["execucoes"] = len(fs)
                o["taker_pct"] = round(100 * sum(1 for f in fs if f.get("execType") == "T") / len(fs), 1)
        ops.append(o)
    return ops


def correr(caminho_estado, pasta, ler=leitura, cifrar=None):
    # (11/11, revisao) sem o registo do executor nao ha stop nem estrategia: o R ficaria vazio e a operacao "manual?".
    # Melhor parar do que publicar um relatorio incompleto como se fosse completo.
    if not os.path.exists(caminho_estado):
        raise FileNotFoundError(f"registo do executor em falta: {caminho_estado}")
    with open(caminho_estado) as f:
        st = json.load(f)
    hist = ((st.get("real") or {}).get("hist")) or []
    ops = construir(historico_posicoes(ler), hist, fills_de=lambda i: execucoes(i, ler))
    pub = C.publico(ops)
    maus = C.sem_dinheiro(pub)
    if maus:
        raise RuntimeError(f"relatorio publico com campos proibidos: {maus[:5]}")
    os.makedirs(pasta, exist_ok=True)
    json.dump(pub, open(os.path.join(pasta, "contabilidade_okx.json"), "w"), indent=1)
    escrito_privado = False
    if os.environ.get("DATA_KEY"):
        p = os.path.join(pasta, "contabilidade_okx_privado.json")
        json.dump(C.registo_privado(ops), open(p, "w"))
        (cifrar or _cifrar)(p)
        escrito_privado = True
    return pub, escrito_privado


def _cifrar(p):
    """Cifra no proprio sitio; se a cifra falhar, apaga o ficheiro (nunca fica em claro)."""
    import subprocess
    r = subprocess.run([sys.executable, "-m", "engine.cifra", "fechar", p],
                       cwd=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    ok = r.returncode == 0 and '"cifra"' in open(p).read()
    if not ok:
        os.remove(p)
        raise RuntimeError("cifra falhou: ficheiro privado apagado")


if __name__ == "__main__":
    pub, priv = correr(sys.argv[1], sys.argv[2])
    t = pub["relatorio"]["total"]
    print(f"operacoes {t['n']} | com custos completos {t.get('n_com_dados', 0)} | R liquido medio {t.get('expectativa_r')} | "
          f"privado cifrado {'sim' if priv else 'nao (sem DATA_KEY)'}")
