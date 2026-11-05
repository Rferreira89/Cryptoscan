"""Historico publico de derivados para a investigacao (so dados; nao mexe em nada do que opera).

(05/11, OK do Rui: "Autorizo") Fase 1: open interest e racios em velas de 4 h para o ramo "derivados".
(05/11 14:17, autorizacao limitada do Rui para o Passo 1 da Fase 2) recolha completa, num ramo de dados NOVO
("derivados-fase2"), sem tocar no ramo "derivados" existente nem no main:
  - metrics (5 em 5 min) agregadas em velas de 30 min: OI (contratos e USD, ultimo valor da vela), racio long/short
    dos grandes traders por CONTAS e por POSICOES, racio de todas as CONTAS e racio compra/venda agressiva (medias);
  - financiamento (todas as liquidacoes, arquivos mensais);
  - liquidacoes (liquidationSnapshot diario: somas em USD dos longs e dos shorts liquidados, em 30 min);
  - moedas vivas (as 66 da investigacao) e retiradas (as do ramo history-delistadas), cada uma com o que existir;
  - indice.json: por moeda, primeiro e ultimo dia, dias em falta (intervalos), cobertura, linhas invalidas,
    meses de financiamento e dias de liquidacoes, e totais.
Fonte: arquivo publico data.binance.vision (futuros USDT-M); a lista de ficheiros vem do indice S3 do arquivo,
por isso os dias em falta sao os que o proprio arquivo nao tem (nunca sao preenchidos nem estimados).
Retoma: estado/<BASE>.json guarda os dias e meses ja descarregados; cada execucao so busca o que falta.
Escrita atomica (ficheiro temporario + troca). Uma vela repetida substitui a anterior (chave = carimbo de tempo).
Uso:
  python -m tools.fetch_derivados <pasta> <BASE> [<BASE> ...]                      (fase 1: velas de 4 h)
  python -m tools.fetch_derivados --fase2 <pasta> --vivas A,B,... --retiradas C,D,...
"""
import calendar
import csv
import gzip
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

URL = "https://data.binance.vision/data/futures/um/daily/metrics/{s}/{s}-metrics-{d}.zip"
ARQ = "https://data.binance.vision/"
S3 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
DESDE = date(2021, 12, 1)
H4, M30 = 14400, 1800
LIMITE_S = int(os.environ.get("DERIVADOS_LIMITE_S", 5 * 3600))
TENTATIVAS = 3


# ---------------------------------------------------------------- comum

def _get(url, timeout=30):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


def _zip(url):
    """Linhas CSV do primeiro ficheiro do zip; None se nao existe (404); 'erro' depois de 3 tentativas."""
    for k in range(TENTATIVAS):
        try:
            z = zipfile.ZipFile(io.BytesIO(_get(url)))
            return list(csv.reader(io.TextIOWrapper(z.open(z.namelist()[0]))))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
        except Exception:
            pass
        time.sleep(1 + 2 * k)
    return "erro"


def _ts(v):
    """Carimbo em segundos a partir de '2025-01-01 00:00:00' ou de milissegundos."""
    v = v.strip()
    if "-" in v:
        return calendar.timegm(time.strptime(v[:19], "%Y-%m-%d %H:%M:%S"))
    return int(float(v) / 1000)


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def escreve_csv(caminho, cab, linhas):
    """Escrita atomica de um csv.gz."""
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    tmp = caminho + ".tmp"
    with gzip.open(tmp, "wt") as f:
        w = csv.writer(f)
        w.writerow(cab)
        w.writerows(linhas)
    os.replace(tmp, caminho)


def escreve_json(caminho, obj):
    os.makedirs(os.path.dirname(caminho) or ".", exist_ok=True)
    tmp = caminho + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, separators=(",", ":"), sort_keys=True)
    os.replace(tmp, caminho)


def ler_csv(caminho):
    """{t: linha} de um csv.gz com cabecalho (vazio se nao existe)."""
    if not os.path.exists(caminho):
        return {}
    with gzip.open(caminho, "rt") as f:
        return {int(r[0]): r for r in csv.reader(f) if r and r[0].isdigit()}


# ---------------------------------------------------------------- fase 1 (velas de 4 h; inalterada)

def _dia(sym, d):
    r = _zip(URL.format(s=sym, d=d.isoformat()))
    if r is None or r == "erro":
        return d, r
    return d, [row for row in r if row and row[0][:1].isdigit()]


def agrega(linhas):
    """{t4h: [oi, oi_usd, ls_top_soma, ls_contas_soma, taker_soma, n, t_ult]} a partir das linhas de 5 minutos."""
    out = {}
    for row in linhas:
        try:
            t = _ts(row[0])
            oi, oiu = float(row[2] or 0), float(row[3] or 0)
            top, contas, tk = float(row[5] or 0), float(row[6] or 0), float(row[7] or 0)
        except (ValueError, IndexError):
            continue
        k = t // H4 * H4
        v = out.setdefault(k, [0.0, 0.0, 0.0, 0.0, 0.0, 0, -1])
        if t >= v[6]:
            v[0], v[1], v[6] = oi, oiu, t
        v[2] += top; v[3] += contas; v[4] += tk; v[5] += 1
    return out


def ler(caminho):
    return ler_csv(caminho)


def moeda(pasta, base, fim, t0):
    sym = f"{base}USDT"
    caminho = os.path.join(pasta, "metrics", f"{base}.csv.gz")
    tem = ler(caminho)
    ult = date.fromtimestamp(max(tem) + 86400) if tem else DESDE
    dias = [ult + timedelta(n) for n in range((fim - ult).days + 1)]
    if not dias:
        return base, 0, len(tem)
    novos, falhas = {}, 0
    with ThreadPoolExecutor(12) as ex:
        for d, linhas in ex.map(lambda d: _dia(sym, d), dias):
            if linhas == "erro":
                falhas += 1
            elif linhas:
                for k, v in agrega(linhas).items():
                    if v[5]:
                        novos[k] = [str(k), f"{v[0]:.4f}", f"{v[1]:.2f}", f"{v[2] / v[5]:.4f}", f"{v[3] / v[5]:.4f}", f"{v[4] / v[5]:.4f}"]
            if time.time() - t0 > LIMITE_S:
                break
    tem.update(novos)
    escreve_csv(caminho, ["t", "oi", "oi_usd", "ls_top", "ls_contas", "taker"], [tem[k] for k in sorted(tem)])
    return base, len(novos), falhas


def main(pasta, bases):
    t0 = time.time()
    fim = date.today() - timedelta(1)
    for base in bases:
        if time.time() - t0 > LIMITE_S:
            print("limite de tempo: continua na proxima execucao")
            break
        b, n, f = moeda(pasta, base, fim, t0)
        print(f"{b}: {n} velas de 4H novas, {f} dias com erro", flush=True)
    return 0


# ---------------------------------------------------------------- fase 2

def lista_s3(prefixo):
    """Chaves (caminhos) do arquivo debaixo de um prefixo, com paginacao."""
    out, marker = [], ""
    for _ in range(100):
        url = f"{S3}?prefix={prefixo}" + (f"&marker={marker}" if marker else "")
        for k in range(TENTATIVAS):
            try:
                xml = _get(url, 60).decode()
                break
            except Exception:
                time.sleep(2 + 3 * k)
        else:
            raise RuntimeError("indice do arquivo inacessivel")
        chaves = re.findall(r"<Key>([^<]+)</Key>", xml)
        out += chaves
        if "<IsTruncated>true</IsTruncated>" not in xml or not chaves:
            break
        marker = chaves[-1]
    return out


def datas_do_indice(chaves, mensal=False):
    """Datas (YYYY-MM-DD ou YYYY-MM) dos .zip de uma lista de chaves."""
    pad = r"-(\d{4}-\d{2})\.zip$" if mensal else r"-(\d{4}-\d{2}-\d{2})\.zip$"
    return sorted({m.group(1) for c in chaves for m in [re.search(pad, c)] if m})


def intervalos_em_falta(dias):
    """Dias (ISO) em falta entre o primeiro e o ultimo, como intervalos [inicio, fim]."""
    if not dias:
        return []
    ds = sorted(date.fromisoformat(d) for d in dias)
    out = []
    for a, b in zip(ds, ds[1:]):
        if (b - a).days > 1:
            out.append([(a + timedelta(1)).isoformat(), (b - timedelta(1)).isoformat()])
    return out


def agrega30(linhas):
    """Metrics de 5 min -> {t30: [oi, oi_usd, top_contas, top_pos, contas, taker, n, t_ult]} (OI = ultimo valor;
    racios = media). Usa o cabecalho do ficheiro quando existe. Devolve (velas, linhas_invalidas)."""
    cab = None
    out, mas = {}, 0
    for row in linhas:
        if not row:
            continue
        if not row[0][:1].isdigit():
            cab = [c.strip() for c in row]
            continue
        try:
            if cab:
                g = dict(zip(cab, row))
                t = _ts(g["create_time"])
                v = [_f(g.get("sum_open_interest")), _f(g.get("sum_open_interest_value")),
                     _f(g.get("count_toptrader_long_short_ratio")), _f(g.get("sum_toptrader_long_short_ratio")),
                     _f(g.get("count_long_short_ratio")), _f(g.get("sum_taker_long_short_vol_ratio"))]
            else:
                t = _ts(row[0])
                v = [_f(x) for x in row[2:8]]
        except (ValueError, KeyError, IndexError):
            mas += 1
            continue
        if v[0] is None or v[0] <= 0:
            mas += 1
            continue
        k = t // M30 * M30
        a = out.setdefault(k, [None, None, 0.0, 0.0, 0.0, 0.0, 0, [0, 0, 0, 0], -1])
        if t >= a[8]:
            a[0], a[1], a[8] = v[0], v[1], t
        for j in range(4):
            if v[2 + j] is not None:
                a[2 + j] += v[2 + j]; a[7][j] += 1
        a[6] += 1
    velas = {}
    for k, a in out.items():
        med = [f"{a[2 + j] / a[7][j]:.4f}" if a[7][j] else "" for j in range(4)]
        velas[k] = [str(k), f"{a[0]:.4f}", f"{a[1]:.2f}" if a[1] is not None else ""] + med + [str(a[6])]
    return velas, mas


def agrega_liq(linhas):
    """liquidationSnapshot -> {t30: [usd_longs_liquidados, usd_shorts_liquidados, n]}. Uma ordem SELL fecha um long."""
    cab = None
    out = {}
    for row in linhas:
        if not row:
            continue
        if not row[0][:1].isdigit():
            cab = [c.strip() for c in row]
            continue
        try:
            g = dict(zip(cab, row)) if cab else {"time": row[0], "side": row[1], "average_price": row[6],
                                                   "accumulated_fill_quantity": row[9], "price": row[5]}
            t = _ts(g["time"])
            px = _f(g.get("average_price")) or _f(g.get("price")) or 0.0
            q = _f(g.get("accumulated_fill_quantity")) or _f(g.get("original_quantity")) or 0.0
            lado = g["side"].strip().upper()
        except (ValueError, KeyError, IndexError):
            continue
        k = t // M30 * M30
        a = out.setdefault(k, [0.0, 0.0, 0])
        if lado == "SELL":
            a[0] += px * q
        elif lado == "BUY":
            a[1] += px * q
        a[2] += 1
    return {k: [str(k), f"{a[0]:.2f}", f"{a[1]:.2f}", str(a[2])] for k, a in out.items()}


def funde(antigo, novo):
    """Junta velas por carimbo; nunca perde velas antigas (uma repetida e substituida pela nova)."""
    r = dict(antigo)
    r.update(novo)
    return r


def _estado(pasta, base):
    p = os.path.join(pasta, "estado", f"{base}.json")
    try:
        with open(p) as f:
            e = json.load(f)
    except Exception:
        e = {}
    for k in ("m", "f", "l", "m_disp", "f_disp", "l_disp", "erros"):
        e.setdefault(k, [] if k != "erros" else {})
    e.setdefault("invalidas", 0)
    return p, e


def recolhe_moeda(pasta, base, estado_moeda, t0, listar=lista_s3, baixar=_zip):
    """Uma moeda: metrics (30 min), financiamento e liquidacoes. Devolve o resumo para o indice."""
    sym = f"{base}USDT"
    pe, e = estado_moeda
    tipos = (("m", "metrics", f"data/futures/um/daily/metrics/{sym}/", False),
             ("f", "funding", f"data/futures/um/monthly/fundingRate/{sym}/", True),
             ("l", "liq30m", f"data/futures/um/daily/liquidationSnapshot/{sym}/", False))
    parou = False
    for k, pasta_saida, prefixo, mensal in tipos:
        disp = datas_do_indice(listar(prefixo), mensal)
        e[f"{k}_disp"] = disp
        feitos = set(e[k])
        falta = [d for d in disp if d not in feitos]
        if not falta:
            continue
        nome = {"m": "metrics30m", "f": "funding", "l": "liq30m"}[k]
        caminho = os.path.join(pasta, nome, f"{base}.csv.gz")
        tem = ler_csv(caminho)
        novos = {}

        def url(d):
            kind = {"m": "metrics", "f": "fundingRate", "l": "liquidationSnapshot"}[k]
            per = "monthly" if mensal else "daily"
            return f"{ARQ}data/futures/um/{per}/{kind}/{sym}/{sym}-{kind}-{d}.zip"
        lote = 400
        for i0 in range(0, len(falta), lote):
            if time.time() - t0 > LIMITE_S:
                parou = True
                break
            parte = falta[i0:i0 + lote]
            with ThreadPoolExecutor(16) as ex:
                res = list(ex.map(lambda d: (d, baixar(url(d))), parte))
            for d, linhas in res:
                if linhas == "erro":
                    e["erros"][f"{k}:{d}"] = e["erros"].get(f"{k}:{d}", 0) + 1
                    continue
                e["erros"].pop(f"{k}:{d}", None)
                if linhas:
                    if k == "m":
                        v, mas = agrega30(linhas)
                        e["invalidas"] += mas
                        novos.update(v)
                    elif k == "f":
                        for row in linhas:
                            if row and row[0][:1].isdigit():
                                taxa = _f(row[2]) if len(row) > 2 else _f(row[1])
                                if taxa is not None:
                                    t = _ts(row[0])
                                    novos[t] = [str(t), f"{taxa:.8f}", row[1] if len(row) > 2 else ""]
                    else:
                        novos.update(agrega_liq(linhas))
                feitos.add(d)
        if novos:
            junto = funde(tem, novos)
            if len(junto) < len(tem):                    # salvaguarda: nunca gravar menos do que havia
                raise RuntimeError(f"{base}/{nome}: menos linhas do que antes")
            cab = {"m": ["t", "oi", "oi_usd", "top_contas", "top_posicoes", "contas", "taker", "n5m"],
                   "f": ["t", "taxa", "intervalo_h"], "l": ["t", "usd_longs", "usd_shorts", "n"]}[k]
            escreve_csv(caminho, cab, [junto[t] for t in sorted(junto)])
        e[k] = sorted(feitos)
        escreve_json(pe, e)
        if parou:
            break
    return parou


def resumo_moeda(pasta, base, e, estado_lista):
    md = e["m_disp"]
    falta = intervalos_em_falta(md)
    n_falta = sum((date.fromisoformat(b) - date.fromisoformat(a)).days + 1 for a, b in falta)
    tot = (date.fromisoformat(md[-1]) - date.fromisoformat(md[0])).days + 1 if md else 0
    tam = {n: os.path.getsize(os.path.join(pasta, n, f"{base}.csv.gz")) for n in ("metrics30m", "funding", "liq30m")
           if os.path.exists(os.path.join(pasta, n, f"{base}.csv.gz"))}
    return {"grupo": estado_lista, "tem_oi": bool(md),
            "oi_primeiro": md[0] if md else None, "oi_ultimo": md[-1] if md else None,
            "oi_dias": len(md), "oi_dias_em_falta": n_falta, "oi_intervalos_em_falta": falta,
            "oi_cobertura_pct": round(100 * len(md) / tot, 2) if tot else 0.0,
            "oi_dias_descarregados": len(e["m"]), "linhas_invalidas": e["invalidas"],
            "funding_meses": len(e["f_disp"]), "funding_primeiro": e["f_disp"][0] if e["f_disp"] else None,
            "funding_ultimo": e["f_disp"][-1] if e["f_disp"] else None, "funding_descarregados": len(e["f"]),
            "liq_dias": len(e["l_disp"]), "liq_primeiro": e["l_disp"][0] if e["l_disp"] else None,
            "liq_ultimo": e["l_disp"][-1] if e["l_disp"] else None, "liq_descarregados": len(e["l"]),
            "erros_pendentes": len(e["erros"]), "bytes": tam}


def main_fase2(pasta, vivas, retiradas):
    t0 = time.time()
    grupos = {**{b: "retirada" for b in retiradas}, **{b: "viva" for b in vivas}}
    indice_p = os.path.join(pasta, "indice.json")
    try:
        with open(indice_p) as f:
            indice = json.load(f)
    except Exception:
        indice = {"moedas": {}}
    parou = False
    for base in sorted(grupos, key=lambda b: (grupos[b] != "viva", b)):
        if time.time() - t0 > LIMITE_S:
            parou = True
            break
        pe = _estado(pasta, base)
        try:
            parou = recolhe_moeda(pasta, base, pe, t0)
        except RuntimeError as er:
            print(f"{base}: parado ({er})", flush=True)
            parou = True
        indice["moedas"][base] = resumo_moeda(pasta, base, pe[1], grupos[base])
        r = indice["moedas"][base]
        print(f"{base} ({grupos[base]}): OI {r['oi_primeiro']}..{r['oi_ultimo']} {r['oi_dias']} dias "
              f"({r['oi_cobertura_pct']}%), descarregados {r['oi_dias_descarregados']}; funding {r['funding_meses']} meses; "
              f"liquidacoes {r['liq_dias']} dias; erros {r['erros_pendentes']}", flush=True)
        escreve_json(indice_p, indice)
        if parou:
            break
    M = indice["moedas"]
    completas = all(m["oi_dias_descarregados"] >= m["oi_dias"] and m["funding_descarregados"] >= m["funding_meses"]
                    and m["liq_descarregados"] >= m["liq_dias"] for b, m in M.items() if b in grupos) and len(
        [b for b in grupos if b in M]) == len(grupos)
    ficheiros = sum(len(fs) for _, _, fs in os.walk(pasta) if ".git" not in _)
    indice["totais"] = {"vivas": len(vivas), "retiradas": len(retiradas),
                        "vivas_com_oi": sum(1 for b, m in M.items() if m["grupo"] == "viva" and m["tem_oi"]),
                        "retiradas_com_oi": sum(1 for b, m in M.items() if m["grupo"] == "retirada" and m["tem_oi"]),
                        "com_funding": sum(1 for m in M.values() if m["funding_meses"]),
                        "com_liquidacoes": sum(1 for m in M.values() if m["liq_dias"]),
                        "bytes": sum(sum(m["bytes"].values()) for m in M.values()),
                        "recolha_completa": completas, "atualizado": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    escreve_json(indice_p, indice)
    print("totais:", json.dumps(indice["totais"]), flush=True)
    print("parado pelo limite de tempo: continua na proxima execucao" if parou else "recolha desta execucao terminada", flush=True)
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--fase2":
        a = sys.argv[2:]
        pasta = a[0]
        vivas = a[a.index("--vivas") + 1].split(",") if "--vivas" in a else []
        retiradas = a[a.index("--retiradas") + 1].split(",") if "--retiradas" in a else []
        sys.exit(main_fase2(pasta, [b for b in vivas if b], [b for b in retiradas if b]))
    sys.exit(main(sys.argv[1], sys.argv[2:]))
