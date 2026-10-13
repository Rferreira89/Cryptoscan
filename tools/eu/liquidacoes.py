"""Escuta das liquidacoes da Binance Futures em tempo real (servidor europeu).

Programa de fundo, separado do trabalhador do GitHub: liga-se ao canal
publico !forceOrder@arr (a maior liquidacao de cada segundo por moeda) e
grava uma linha por liquidacao em ~/liq/AAAAMMDD.jsonl. Guarda 10 dias.
Nao usa chaves nem mexe em nada da conta. Se a ligacao cair, volta a ligar.

  python3 -m tools.eu.liquidacoes correr     # o programa de escuta
  python3 -m tools.eu.liquidacoes garantir   # lanca-o se nao estiver vivo
  resumo(dir, agora) -> {moeda: [[fecho_4h, longs_usd, shorts_usd], ...]}
"""
import glob
import json
import os
import subprocess
import sys
import time

DIR = os.path.expanduser("~/liq")
PID = os.path.join(DIR, "escuta.pid")
VENV = os.path.expanduser("~/liq-venv")
URL = "wss://fstream.binance.com/ws/!forceOrder@arr"
KEEP_DAYS = 10
VERSION = "2"                    # muda quando o codigo da escuta muda (relanca)
H4 = 14400


def _clean():
    lim = time.strftime("%Y%m%d", time.gmtime(time.time() - KEEP_DAYS * 86400))
    for f in glob.glob(os.path.join(DIR, "2*.jsonl")):
        if os.path.basename(f)[:8] < lim:
            os.remove(f)


def correr():
    import asyncio
    import websockets
    os.makedirs(DIR, exist_ok=True)
    with open(PID, "w") as f:
        f.write(f"{os.getpid()} {VERSION}")

    async def loop():
        while True:
            try:
                async with websockets.connect(URL, ping_interval=60, close_timeout=5,
                                              open_timeout=20) as ws:
                    print(time.strftime("%H:%M:%S"), "ligado", flush=True)
                    n, last = 0, time.time()
                    async for msg in ws:
                        n += 1
                        if time.time() - last > 600:
                            print(time.strftime("%H:%M:%S"), f"{n} mensagens", flush=True)
                            last = time.time()
                        o = (json.loads(msg) or {}).get("o") or {}
                        if not o.get("s", "").endswith("USDT"):
                            continue
                        rec = {"t": int(o.get("T", 0)) // 1000, "s": o["s"], "lado": o.get("S"),
                               "q": float(o.get("z") or o.get("q") or 0),
                               "p": float(o.get("ap") or o.get("p") or 0)}
                        day = time.strftime("%Y%m%d", time.gmtime(rec["t"] or time.time()))
                        with open(os.path.join(DIR, f"{day}.jsonl"), "a") as f:
                            f.write(json.dumps(rec, separators=(",", ":")) + "\n")
            except Exception as e:                 # rede: espera e volta a ligar
                print("ligacao caiu:", type(e).__name__, flush=True)
                await asyncio.sleep(5)
            _clean()
    asyncio.run(loop())


def vivo(version=None):
    try:
        parts = open(PID).read().split()
        pid = int(parts[0])
        os.kill(pid, 0)
        if version and (parts[1:] or [""])[0] != version:
            os.kill(pid, 15)                 # versao antiga: termina para relancar
            time.sleep(1)
            return None
        return pid
    except Exception:
        return None


def garantir():
    """Lanca a escuta em segundo plano se nao estiver a correr. Fica fora do
    controlo do trabalhador (sem RUNNER_TRACKING_ID), por isso sobrevive ao
    fim da tarefa do GitHub."""
    os.makedirs(DIR, exist_ok=True)
    py = os.path.join(VENV, "bin", "python3")
    if not os.path.exists(py):
        subprocess.run([sys.executable, "-m", "venv", VENV], check=True)
        subprocess.run([py, "-m", "pip", "install", "-q", "websockets==12.0"], check=True)
    pid = vivo(VERSION)
    if pid:
        print(f"escuta viva (pid {pid})")
        return
    env = {k: v for k, v in os.environ.items() if k != "RUNNER_TRACKING_ID"}
    env["PYTHONPATH"] = os.getcwd()
    code_dir = os.path.join(DIR, "codigo")
    os.makedirs(code_dir, exist_ok=True)
    # copia o proprio ficheiro: a pasta do repositorio e limpa entre tarefas
    import shutil
    shutil.copy(os.path.abspath(__file__), os.path.join(code_dir, "liquidacoes.py"))
    log = open(os.path.join(DIR, "escuta.log"), "a")
    subprocess.Popen([py, os.path.join(code_dir, "liquidacoes.py"), "correr"],
                     env=env, stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                     start_new_session=True, cwd=DIR)
    time.sleep(3)
    print(f"escuta lancada (pid {vivo()})")


def resumo(d=DIR, now=None, days=30):
    """Liquidacoes por moeda em velas de 4H: [[fecho, longs_usd, shorts_usd]].
    lado SELL = posicao longa liquidada (venda forcada)."""
    from engine.europa import base_of
    now = now or time.time()
    out = {}
    for f in sorted(glob.glob(os.path.join(d, "2*.jsonl"))):
        for line in open(f):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r["t"] < now - days * 86400:
                continue
            b = base_of(r["s"])
            k = (r["t"] // H4) * H4 + H4
            row = out.setdefault(b, {}).setdefault(k, [0.0, 0.0])
            row[0 if r.get("lado") == "SELL" else 1] += r["q"] * r["p"]
    return {b: [[k, round(v[0]), round(v[1])] for k, v in sorted(m.items())] for b, m in out.items()}


if __name__ == "__main__":
    {"correr": correr, "garantir": garantir}[sys.argv[1]]()
