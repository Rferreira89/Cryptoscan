"""Cifra dos dados financeiros do Rui (28/10, OK do Rui: o repositorio e publico).

Formato (igual em Python e na app, WebCrypto):
  chave   = PBKDF2-HMAC-SHA256(palavra-passe, sal, ITER, 64 bytes): 32 para AES, 32 para HMAC
  cifra   = AES-256-CTR com contador de 128 bits a comecar no iv
  selo    = HMAC-SHA256(chave_mac, b"cs1" + sal + iv + cifrado)   (cifrar-depois-autenticar)
  ficheiro = {"cifra":"cs1","it":ITER,"sal":b64,"iv":b64,"selo":b64,"dados":b64}

A palavra-passe vem do segredo DATA_KEY do GitHub (variavel de ambiente). Sem DATA_KEY nada e
cifrado (transicao) e os ficheiros em claro leem-se como antes. Um ficheiro cifrado sem chave
levanta SemChave: nunca se le lixo nem se apaga nada.

Usa a biblioteca cryptography quando existe (rapida); senao AES em Python puro (mais lento,
mesmo resultado, testado contra o vetor FIPS-197 e contra a biblioteca).

Linha de comandos (workflows):
  python -m engine.cifra abrir F...           decifra no proprio ficheiro (se estiver cifrado)
  python -m engine.cifra fechar F...          cifra no proprio ficheiro (so com DATA_KEY)
  python -m engine.cifra abrir-campo F CAMPO  o mesmo para um campo de um JSON (dados.json -> conta)
  python -m engine.cifra fechar-campo F CAMPO
"""
import base64
import hashlib
import hmac
import json
import os
import sys

VERSAO, ITER = "cs1", 200_000
_CACHE = {}


class SemChave(Exception):
    pass


class Invalido(Exception):
    pass


def senha():
    return (os.environ.get("DATA_KEY") or "").strip()


def ativa():
    return bool(senha())


def e_envelope(obj):
    return isinstance(obj, dict) and obj.get("cifra") == VERSAO and "dados" in obj


# ---------- AES-256 (so cifra: em CTR a decifra e a mesma operacao) ----------

_SBOX = bytes.fromhex(
    "637c777bf26b6fc53001672bfed7ab76ca82c97dfa5947f0add4a2af9ca472c0"
    "b7fd9326363ff7cc34a5e5f171d8311504c723c31896059a071280e2eb27b275"
    "09832c1a1b6e5aa0523bd6b329e32f8453d100ed20fcb15b6acbbe394a4c58cf"
    "d0efaafb434d338545f9027f503c9fa851a3408f929d38f5bcb6da2110fff3d2"
    "cd0c13ec5f974417c4a77e3d645d197360814fdc222a908846eeb814de5e0bdb"
    "e0323a0a4906245cc2d3ac629195e479e7c8376d8dd54ea96c56f4ea657aae08"
    "ba78252e1ca6b4c6e8dd741f4bbd8b8a703eb5664803f60e613557b986c11d9e"
    "e1f8981169d98e949b1e87e9ce5528df8ca1890dbfe6426841992d0fb054bb16")


def _xt(a):
    a <<= 1
    return (a ^ 0x11B) & 0xFF if a & 0x100 else a


_T0 = []
for _s in _SBOX:
    _s2, _s3 = _xt(_s), _xt(_s) ^ _s
    _T0.append((_s2 << 24) | (_s << 16) | (_s << 8) | _s3)
_T1 = [((t >> 8) | (t << 24)) & 0xFFFFFFFF for t in _T0]
_T2 = [((t >> 16) | (t << 16)) & 0xFFFFFFFF for t in _T0]
_T3 = [((t >> 24) | (t << 8)) & 0xFFFFFFFF for t in _T0]


def _expandir(chave):
    w = [int.from_bytes(chave[4 * i:4 * i + 4], "big") for i in range(8)]
    rcon = 1
    for i in range(8, 60):
        t = w[i - 1]
        if i % 8 == 0:
            t = ((t << 8) | (t >> 24)) & 0xFFFFFFFF
            t = (_SBOX[t >> 24] << 24) | (_SBOX[(t >> 16) & 255] << 16) | (_SBOX[(t >> 8) & 255] << 8) | _SBOX[t & 255]
            t ^= rcon << 24
            rcon = _xt(rcon)
        elif i % 8 == 4:
            t = (_SBOX[t >> 24] << 24) | (_SBOX[(t >> 16) & 255] << 16) | (_SBOX[(t >> 8) & 255] << 8) | _SBOX[t & 255]
        w.append(w[i - 8] ^ t)
    return w


def _bloco(w, b):
    s0, s1, s2, s3 = (int.from_bytes(b[0:4], "big") ^ w[0], int.from_bytes(b[4:8], "big") ^ w[1],
                      int.from_bytes(b[8:12], "big") ^ w[2], int.from_bytes(b[12:16], "big") ^ w[3])
    T0, T1, T2, T3, k = _T0, _T1, _T2, _T3, 4
    for _ in range(13):
        t0 = T0[s0 >> 24] ^ T1[(s1 >> 16) & 255] ^ T2[(s2 >> 8) & 255] ^ T3[s3 & 255] ^ w[k]
        t1 = T0[s1 >> 24] ^ T1[(s2 >> 16) & 255] ^ T2[(s3 >> 8) & 255] ^ T3[s0 & 255] ^ w[k + 1]
        t2 = T0[s2 >> 24] ^ T1[(s3 >> 16) & 255] ^ T2[(s0 >> 8) & 255] ^ T3[s1 & 255] ^ w[k + 2]
        t3 = T0[s3 >> 24] ^ T1[(s0 >> 16) & 255] ^ T2[(s1 >> 8) & 255] ^ T3[s2 & 255] ^ w[k + 3]
        s0, s1, s2, s3, k = t0, t1, t2, t3, k + 4
    S = _SBOX
    out = []
    for a, b2, c, d, wk in ((s0, s1, s2, s3, w[56]), (s1, s2, s3, s0, w[57]),
                            (s2, s3, s0, s1, w[58]), (s3, s0, s1, s2, w[59])):
        out.append(((S[a >> 24] << 24) | (S[(b2 >> 16) & 255] << 16) | (S[(c >> 8) & 255] << 8) | S[d & 255]) ^ wk)
    return b"".join(x.to_bytes(4, "big") for x in out)


def aes256_bloco(chave, bloco):
    """Um bloco AES-256 (para os testes contra o FIPS-197)."""
    return _bloco(_expandir(chave), bloco)


def _ctr_puro(chave, iv, dados):
    w = _expandir(chave)
    c = int.from_bytes(iv, "big")
    out = bytearray(len(dados))
    for i in range(0, len(dados), 16):
        ks = _bloco(w, ((c + i // 16) & ((1 << 128) - 1)).to_bytes(16, "big"))
        pedaco = dados[i:i + 16]
        out[i:i + len(pedaco)] = bytes(x ^ y for x, y in zip(pedaco, ks))
    return bytes(out)


def _ctr(chave, iv, dados):
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except Exception:
        return _ctr_puro(chave, iv, dados)
    e = Cipher(algorithms.AES(chave), modes.CTR(iv)).encryptor()
    return e.update(dados) + e.finalize()


# ---------- envelope ----------

def _chaves(pw, sal, it):
    k = (pw, sal, it)
    if k not in _CACHE:
        _CACHE[k] = hashlib.pbkdf2_hmac("sha256", pw.encode(), sal, it, 64)
    dk = _CACHE[k]
    return dk[:32], dk[32:]


def cifrar_bytes(dados, pw=None):
    pw = pw if pw is not None else senha()
    if not pw:
        raise SemChave("DATA_KEY em falta")
    sal, iv = os.urandom(16), os.urandom(16)
    ke, km = _chaves(pw, sal, ITER)
    ct = _ctr(ke, iv, dados)
    selo = hmac.new(km, VERSAO.encode() + sal + iv + ct, hashlib.sha256).digest()
    b = lambda x: base64.b64encode(x).decode()
    return {"cifra": VERSAO, "it": ITER, "sal": b(sal), "iv": b(iv), "selo": b(selo), "dados": b(ct)}


def decifrar_bytes(env, pw=None):
    pw = pw if pw is not None else senha()
    if not pw:
        raise SemChave("ficheiro cifrado e DATA_KEY em falta")
    d = base64.b64decode
    sal, iv, ct, selo = d(env["sal"]), d(env["iv"]), d(env["dados"]), d(env["selo"])
    ke, km = _chaves(pw, sal, int(env.get("it") or ITER))
    if not hmac.compare_digest(selo, hmac.new(km, VERSAO.encode() + sal + iv + ct, hashlib.sha256).digest()):
        raise Invalido("selo errado: palavra-passe diferente ou ficheiro alterado")
    return _ctr(ke, iv, ct)


def abrir_obj(obj):
    """Objeto JSON: se for um envelope, devolve o conteudo decifrado; senao o proprio objeto."""
    return json.loads(decifrar_bytes(obj).decode()) if e_envelope(obj) else obj


def fechar_obj(obj):
    """Envelope do objeto se houver chave; senao o proprio objeto (transicao)."""
    if not ativa() or e_envelope(obj):
        return obj
    return cifrar_bytes(json.dumps(obj, separators=(",", ":")).encode())


def ler_texto(caminho):
    """Texto do ficheiro, decifrado se for um envelope."""
    with open(caminho, "rb") as f:
        raw = f.read()
    if raw[:12].lstrip().startswith(b'{"cifra"'):
        try:
            env = json.loads(raw)
        except ValueError:
            env = None
        if e_envelope(env):
            return decifrar_bytes(env).decode()
    return raw.decode()


def gravar_texto(caminho, texto):
    """Grava cifrado com DATA_KEY, em claro sem ela."""
    if ativa():
        texto = json.dumps(cifrar_bytes(texto.encode()), separators=(",", ":"))
    with open(caminho, "w") as f:
        f.write(texto)


# ---------- linha de comandos ----------

def _main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd, args = argv[0], argv[1:]
    if cmd in ("abrir", "fechar"):
        for p in args:
            if not os.path.exists(p) or os.path.getsize(p) == 0:
                continue
            if cmd == "abrir":
                t = ler_texto(p)
                with open(p, "w") as f:
                    f.write(t)
            elif ativa():
                with open(p) as f:
                    t = f.read()
                if not t.lstrip().startswith('{"cifra"'):
                    gravar_texto(p, t)
        if cmd == "fechar" and not ativa():
            print("cifra: DATA_KEY em falta, ficheiros ficam em claro")
        return 0
    if cmd in ("abrir-campo", "fechar-campo") and len(args) == 2:
        p, campo = args
        if not os.path.exists(p) or os.path.getsize(p) == 0:
            return 0
        with open(p) as f:
            d = json.load(f)
        if isinstance(d, dict) and campo in d:
            d[campo] = abrir_obj(d[campo]) if cmd == "abrir-campo" else fechar_obj(d[campo])
            with open(p, "w") as f:
                json.dump(d, f, separators=(",", ":"))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
