"""(11/11, auditoria P3) Publicacao do estado de um agente num ramo do repositorio, com tentativas e recuperacao.

Causa (run 42841181999, 10/11 15:08): `git push` respondeu "remote: fatal error in commit_refs" (falha transitoria do
GitHub). O passo saiu com erro e a volta inteira perdeu-se: a volta seguinte partiu do estado ANTERIOR, sem aviso.

Agora:
  publicar  - commit e push com tentativas (backoff 5 s, 15 s, 45 s por omissao). Antes de cada tentativa guarda uma
              copia do estado numa pasta local do runner self-hosted (ESTADO_LOCAL, fora do repositorio). Sucesso ->
              apaga a copia e o contador de falhas. Falha em todas as tentativas -> mantem a copia, soma uma falha
              seguida e, a partir de FALHAS_ALERTA voltas seguidas (falha persistente), avisa UMA vez no Telegram.
  recuperar - no inicio da volta, se a copia local for MAIS RECENTE do que o ramo publicado (campo de tempo do
              estado), usa a copia: a volta seguinte continua do estado da volta que nao chegou a ser publicada.

Garantias:
  - a publicacao corre DEPOIS do agente; uma falha de publicacao nunca volta a correr o agente nem repete ordens
    (as ordens reais tambem sao idempotentes pelo clOrdId; ver okx_exec.abrir, 51016);
  - repetir a publicacao com o mesmo conteudo e inofensivo (o ramo e reescrito com o mesmo estado);
  - nada privado sai daqui: so publica os ficheiros pedidos, que ja sao os publicos ou cifrados.
Uso:
  python3 tools/publicar_estado.py publicar <pasta> <ramo> <ficheiro> [<ficheiro> ...]
  python3 tools/publicar_estado.py recuperar <pasta> <ramo> <ficheiro_estado>"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request

ESPERAS = (5, 15, 45)
FALHAS_ALERTA = 2


def pasta_local(ramo):
    base = os.environ.get("ESTADO_LOCAL") or os.path.join(os.path.expanduser("~"), ".cryptoscan_estado")
    p = os.path.join(base, ramo)
    os.makedirs(p, exist_ok=True)
    return p


def _git(pasta, *args):
    return subprocess.run(["git", *args], cwd=pasta, capture_output=True, text=True)


def _contador(ramo):
    return os.path.join(pasta_local(ramo), "falhas.json")


def ler_falhas(ramo):
    try:
        return json.load(open(_contador(ramo)))
    except (OSError, ValueError):
        return {"seguidas": 0, "avisado": False}


def _gravar_falhas(ramo, d):
    json.dump(d, open(_contador(ramo), "w"))


def telegram(txt):
    t, c = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not t or not c:
        return False
    try:
        data = urllib.parse.urlencode({"chat_id": c, "text": txt}).encode()
        urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{t}/sendMessage", data=data), timeout=20)
        return True
    except Exception as e:                       # o aviso nunca pode partir a publicacao
        print("telegram falhou:", type(e).__name__)
        return False


def guardar_copia(pasta, ramo, ficheiros):
    dst = pasta_local(ramo)
    for f in ficheiros:
        src = os.path.join(pasta, f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(dst, f))


def apagar_copia(ramo, ficheiros):
    dst = pasta_local(ramo)
    for f in ficheiros:
        try:
            os.remove(os.path.join(dst, f))
        except OSError:
            pass


def publicar(pasta, ramo, ficheiros, push_url=None, esperas=ESPERAS, dormir=time.sleep, git=_git, avisar=telegram):
    """Devolve True se o ramo ficou publicado. Nunca levanta excecao por falha de rede."""
    push_url = push_url or os.environ.get("PUSH_URL")
    presentes = [f for f in ficheiros if os.path.exists(os.path.join(pasta, f))]
    guardar_copia(pasta, ramo, presentes)                      # antes de tudo: a copia sobrevive a qualquer falha
    if not os.path.isdir(os.path.join(pasta, ".git")):
        git(pasta, "init", "-q", "-b", ramo)
    git(pasta, "config", "user.name", "cryptoscan-bot")
    git(pasta, "config", "user.email", "bot@users.noreply.github.com")
    git(pasta, "add", *presentes)
    c = git(pasta, "commit", "-q", "-m", f"{ramo} {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")
    if c.returncode != 0 and "nothing to commit" not in (c.stdout + c.stderr):
        print("commit falhou:", (c.stderr or c.stdout)[:200])
    erro = ""
    for i in range(len(esperas) + 1):
        r = git(pasta, "push", "-q", "-f", push_url, f"{ramo}:{ramo}")
        if r.returncode == 0:
            f = ler_falhas(ramo)
            if f.get("avisado"):
                avisar(f"✅ Publicação do estado '{ramo}' recuperada depois de {f['seguidas']} volta(s) com falha.")
            _gravar_falhas(ramo, {"seguidas": 0, "avisado": False})
            apagar_copia(ramo, presentes)
            if i:
                print(f"publicado a tentativa {i + 1}")
            return True
        erro = (r.stderr or r.stdout or "").strip().splitlines()[-1:] or ["?"]
        erro = erro[0][:160].replace(push_url or "\0", "<url>")
        print(f"push falhou (tentativa {i + 1}): {erro}")
        if i < len(esperas):
            dormir(esperas[i])
    f = ler_falhas(ramo)
    f["seguidas"] = int(f.get("seguidas") or 0) + 1
    f["ultimo_erro"] = erro
    f["t"] = int(time.time())
    if f["seguidas"] >= FALHAS_ALERTA and not f.get("avisado"):
        f["avisado"] = avisar(f"🚨 Cryptoscan: o estado '{ramo}' não é publicado há {f['seguidas']} voltas seguidas "
                              f"({erro}). A cópia local no runner mantém o estado e a volta seguinte retoma dela; "
                              f"as ordens e posições continuam geridas.")
    _gravar_falhas(ramo, f)
    return False


def _tempo(estado):
    for chave in ("volta", "resumo"):
        v = (estado or {}).get(chave)
        if isinstance(v, dict) and v.get("t"):
            return float(v["t"])
    return float((estado or {}).get("t") or 0)


def recuperar(pasta, ramo, ficheiro):
    """Se a copia local do runner for mais recente do que o estado publicado, passa a ser a usada. Devolve True se
    recuperou. Um estado local ilegivel nunca substitui o publicado."""
    local = os.path.join(pasta_local(ramo), ficheiro)
    alvo = os.path.join(pasta, ficheiro)
    if not os.path.exists(local):
        return False
    try:
        e_local = json.load(open(local))
    except (OSError, ValueError):
        return False
    try:
        e_pub = json.load(open(alvo))
    except (OSError, ValueError):
        e_pub = None
    if _tempo(e_local) > _tempo(e_pub):
        os.makedirs(pasta, exist_ok=True)
        shutil.copy2(local, alvo)
        print(f"estado recuperado da copia local ({ficheiro}, mais recente do que o ramo publicado)")
        return True
    return False


if __name__ == "__main__":
    acao, pasta, ramo, *fs = sys.argv[1:]
    if acao == "publicar":
        sys.exit(0 if publicar(pasta, ramo, fs) else 1)
    if acao == "recuperar":
        recuperar(pasta, ramo, fs[0])
        sys.exit(0)
    sys.exit(2)
