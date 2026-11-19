"""(19/11, ordem do Rui) Guarda dos ficheiros PUBLICOS: procura valores financeiros absolutos e dados privados antes de
publicar. O repositorio e publico; o que for dinheiro (saldos, capital, margem, nocional, risco em moeda, PnL em moeda,
quantidades/tamanhos) ou identificador de conta so pode ir cifrado ou por Telegram.

Analisa o esquema: nomes de campos (com o valor numerico) e texto livre (numeros seguidos de moeda). O que e publico
de proposito fica numa lista explicita (precos, R, percentagens, horas, contagens, limites da configuracao publica).

  verificar(dados, nome="") -> [(caminho, motivo)]      lista vazia = pode publicar
  verificar_ficheiro(caminho) -> [(caminho_campo, motivo)]
Linha de comandos: python3 -m engine.guarda_publica <ficheiro> [...]  (sai com 3 se encontrar alguma coisa)."""
import json
import re
import sys

# palavras (TOKENS do nome do campo, ja partido em "_", "-", "." e camelCase) que, com valor numerico, sao dinheiro
DINHEIRO = {"usdc", "usdt", "usd", "eur", "saldo", "saldos", "balance", "equity", "margem", "margin", "nocional",
            "notional", "capital", "pnl", "lucro", "valor", "wallet", "carteira", "disponivel", "avail", "availbal",
            "divida", "dividas", "debt", "borrow", "borrowed", "emprestimo", "comissoes", "fees", "juros", "fundo", "eq"}
TAMANHO = {"qty", "quantidade", "contratos", "contracts", "sz", "size", "accfillsz", "execqty", "pos", "held"}
CONTA = {"uid", "apikey", "passphrase", "secret", "accountid", "subuid", "token", "senha"}
# nomes inteiros permitidos: limites da configuracao PUBLICA (config.json e piloto_okx_config.json estao no
# repositorio), especificacoes publicas dos contratos e indicadores sem dinheiro
PERMITIDO = {
    "max_risk_usdc", "min_order_usdc", "capital_max", "nocional_max", "risco_max_op", "perda_max", "suspender_em",
    "perda_diaria_max", "risco_total_max", "nocional_total_max", "nocional_total", "risco_total",
    "minsz", "lotsz", "ticksz", "maxsz", "ctval", "ctmult", "min_order_qty", "base_precision", "lot", "lotes",
    "pnl_r", "pnl_por_confirmar", "pnl_pct", "juros_bybit", "juros_margem_dia_pct", "funding", "nocional_usado_pct", "margem_usada_pct", "risco_usado_pct",
}
# tokens que tornam o campo publico mesmo com uma palavra acima (unidades sem dinheiro)
NEUTROS = {"pct", "r", "n", "t", "ok", "estado", "fonte", "motivo", "pnlr", "bps", "x", "rank", "score"}
# caminhos conhecidos que nao sao dinheiro apesar do nome (contagem de contratos analisados; posicao na liga)
PERMITIDO_CAMINHO = [re.compile(x) for x in (r"^resumo\.contratos$", r"^liga\.tabela\[\d+\]\.pos$",
                                              r"(^|\.)liga\.tabela\[\d+\]\.pos$")]
MOEDA_TXT = re.compile(r"(?<![\w.])[-+]?\d+(?:[.,]\d+)?\s?(?:USDC|USDT|USD|EUR|€|\$)(?![A-Za-z])")
# texto livre: palavra de dinheiro seguida de um numero que NAO e percentagem nem R (ex.: "risco 0.0240, nocional
# 14.28", a fuga corrigida em 7453957, que nem tinha a moeda escrita)
PALAVRA_TXT = re.compile(r"(?i)\b(?:risco|nocional|saldo|margem|capital|pnl|lucro|perda|equity|balance|margin|notional|"
                         r"livre|disponivel)\b(?:\s+(?:livre|usado|aberto|realizado|de|do|da|em))?\s*[:=]?\s*"
                         r"[-+]?\d+(?:[.,]\d+)?(?!\d|[.,]\d|\s*%|\s*R\b|\s*x\b|\s*(?:h|min|s|dias?|velas?|op)\b)")
CONTA_TXT = re.compile(r"(?i)\b(?:uid|api[-_ ]?key|passphrase|secret)\s*[:=]\s*\S+")
SIMBOLO = re.compile(r"^[A-Z0-9]{1,15}([-/_][A-Z0-9]{2,8})*$")       # BTC, XLM-USDT-SWAP, SPCX-USD_UM_XPERP-310613


def tokens(nome):
    n = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(nome))
    return [t for t in re.split(r"[^a-z0-9]+", n.lower()) if t]


def _tem(nome, palavras):
    return any(t in palavras for t in tokens(nome))


def _permitido(nome):
    n = str(nome).lower()
    if n in PERMITIDO or SIMBOLO.match(str(nome)):
        return True
    return any(t in NEUTROS for t in tokens(nome))


def _numero(v):
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return True
    if isinstance(v, str):
        try:
            float(v)
            return v.strip() != ""
        except ValueError:
            return False
    return False


def _conta(nome):
    junto = re.sub(r"[^a-z0-9]", "", str(nome).lower())
    return (_tem(nome, CONTA) or junto in CONTA) and not SIMBOLO.match(str(nome))


def verificar(dados, nome=""):
    """Percorre todo o JSON. Devolve [(caminho, motivo)]. Um numero debaixo de um campo de dinheiro (ex.:
    saldos.BTC) tambem conta, mesmo que a sua propria chave seja so o simbolo."""
    out = []

    def anda(v, caminho, chave, pai):
        if isinstance(v, dict):
            for k, x in v.items():
                k = str(k)
                herda = pai
                if not _permitido(k):
                    herda = "dinheiro" if _tem(k, DINHEIRO) else "tamanho" if _tem(k, TAMANHO) else pai
                else:
                    herda = None if not SIMBOLO.match(k) else pai
                anda(x, f"{caminho}.{k}" if caminho else k, k, herda)
            return
        if isinstance(v, list):
            for i, x in enumerate(v):
                anda(x, f"{caminho}[{i}]", chave, pai)
            return
        if chave and _conta(chave) and v not in (None, "", False):
            out.append((caminho, "identificador ou credencial de conta"))
            return
        if _numero(v) and not any(r.search(caminho) for r in PERMITIDO_CAMINHO):
            if chave and SIMBOLO.match(chave):
                proprio = pai                                  # chave e so o simbolo: vale o campo de cima
            elif chave and _permitido(chave):
                proprio = None
            else:
                proprio = "dinheiro" if chave and _tem(chave, DINHEIRO) else "tamanho" if chave and _tem(chave, TAMANHO) else pai
            if proprio == "dinheiro":
                out.append((caminho, f"valor monetario absoluto no campo '{chave}'"))
                return
            if proprio == "tamanho":
                out.append((caminho, f"quantidade/tamanho no campo '{chave}'"))
                return
        if isinstance(v, str):
            if MOEDA_TXT.search(v):
                out.append((caminho, f"texto com valor em moeda: {MOEDA_TXT.search(v).group(0)!r}"))
            elif PALAVRA_TXT.search(v):
                out.append((caminho, f"texto com valor monetario: {PALAVRA_TXT.search(v).group(0)!r}"))
            elif CONTA_TXT.search(v):
                out.append((caminho, "texto com identificador de conta"))

    anda(dados, "", "", None)
    return out


def verificar_ficheiro(caminho):
    with open(caminho) as f:
        txt = f.read()
    if caminho.endswith(".jsonl"):
        out = []
        for i, linha in enumerate(txt.splitlines()):
            if linha.strip():
                out += [(f"linha {i + 1}: {c}", m) for c, m in verificar(json.loads(linha))]
        return out
    d = json.loads(txt)
    if isinstance(d, dict) and "cifra" in d and len(d) <= 4:
        return []                                         # ficheiro cifrado (engine.cifra): nada em claro
    return verificar(d, caminho)


if __name__ == "__main__":
    # --avisar: modo para estados que o proprio agente le (scan.json, state.json): avisa no Telegram e sai com 0
    # (bloquear a publicacao do estado pararia o motor); sem --avisar sai com 3 quando encontra alguma coisa
    avisar = "--avisar" in sys.argv
    total, linhas = 0, []
    for p in [a for a in sys.argv[1:] if a != "--avisar"]:
        r = verificar_ficheiro(p)
        total += len(r)
        for c, m in r[:200]:
            print(f"{p}: {c}: {m}")
        print(f"{p}: {len(r)} ocorrencia(s)")
        linhas += [f"{p.split('/')[-1]}: {c} ({m})" for c, m in r[:3]]
    if avisar:
        import os
        import time
        marca = os.environ.get("GUARDA_MARCA")              # no maximo um aviso por hora (o scan publica de 5 em 5 min)
        recente = bool(marca and os.path.exists(marca) and time.time() - os.path.getmtime(marca) < 3600)
        if total and not recente:
            if marca:
                open(marca, "w").close()
            try:
                from engine import alerts
                alerts.send(f"🛑 Cryptoscan: dados privados nos ficheiros públicos ({total} campo(s)): " + "; ".join(linhas)[:500]
                            + ". Estado publicado para não parar o motor; corrigir na origem.")
            except Exception as e:
                print("aviso falhou:", type(e).__name__)
        sys.exit(0)
    sys.exit(3 if total else 0)
