// Cifra dos dados (28/10, OK do Rui): o repositorio e publico, por isso os dados financeiros vao
// cifrados. Mesmo formato de engine/cifra.py: PBKDF2-SHA256 -> AES-256-CTR + HMAC-SHA256.
// A palavra-passe fica so neste telemovel (localStorage) e nunca sai dele.
(function () {
  const te = new TextEncoder(), td = new TextDecoder();
  const b64 = s => Uint8Array.from(atob(s), c => c.charCodeAt(0));
  async function abrir(env, pw) {
    const sal = b64(env.sal), iv = b64(env.iv), ct = b64(env.dados), selo = b64(env.selo);
    const base = await crypto.subtle.importKey("raw", te.encode(pw), "PBKDF2", false, ["deriveBits"]);
    const bits = new Uint8Array(await crypto.subtle.deriveBits(
      {name: "PBKDF2", hash: "SHA-256", salt: sal, iterations: env.it || 200000}, base, 512));
    const km = await crypto.subtle.importKey("raw", bits.slice(32), {name: "HMAC", hash: "SHA-256"}, false, ["verify"]);
    const msg = new Uint8Array(3 + sal.length + iv.length + ct.length);
    msg.set(te.encode("cs1"), 0); msg.set(sal, 3); msg.set(iv, 3 + sal.length); msg.set(ct, 3 + sal.length + iv.length);
    if (!await crypto.subtle.verify("HMAC", km, selo, msg)) throw new Error("palavra-passe errada");
    const ke = await crypto.subtle.importKey("raw", bits.slice(0, 32), {name: "AES-CTR"}, false, ["decrypt"]);
    return JSON.parse(td.decode(await crypto.subtle.decrypt({name: "AES-CTR", counter: iv, length: 128}, ke, ct)));
  }
  const K = "cryptoscan_pw";
  const guardada = () => { try { return localStorage.getItem(K) || ""; } catch (_) { return ""; } };
  const guardar = pw => { try { pw ? localStorage.setItem(K, pw) : localStorage.removeItem(K); } catch (_) {} };
  function pedir(erro) {
    return new Promise(res => {
      const o = document.createElement("div");
      o.style.cssText = "position:fixed;inset:0;z-index:99999;background:rgba(6,14,24,.92);display:flex;align-items:center;justify-content:center;padding:16px";
      o.innerHTML = `<form style="background:#0F2233;color:#e8eef5;border:1px solid #2a4a66;border-radius:12px;padding:20px;max-width:340px;width:100%;font:15px system-ui">
        <b style="font-size:17px">🔒 Dados cifrados</b>
        <p style="margin:8px 0 12px;color:#9fb3c8">Os teus dados financeiros estão cifrados no repositório público. Escreve a palavra-passe que guardaste no segredo DATA_KEY do GitHub. Fica só neste aparelho.</p>
        ${erro ? `<p style="color:#ff8a9a;margin:0 0 10px">${erro}</p>` : ""}
        <input type="password" autocomplete="current-password" style="width:100%;box-sizing:border-box;padding:10px;border-radius:8px;border:1px solid #2a4a66;background:#08131f;color:#fff;font-size:16px" placeholder="palavra-passe">
        <button style="margin-top:12px;width:100%;padding:10px;border:0;border-radius:8px;background:#3ee0c4;color:#04201a;font-weight:700;font-size:15px">Abrir</button></form>`;
      document.body.appendChild(o);
      const f = o.querySelector("form"), i = o.querySelector("input");
      setTimeout(() => i.focus(), 50);
      f.onsubmit = e => { e.preventDefault(); const v = i.value; o.remove(); res(v); };
    });
  }
  // devolve o objeto decifrado (ou o proprio, se nao estiver cifrado)
  async function json(obj) {
    if (!(obj && obj.cifra === "cs1" && obj.dados)) return obj;
    let pw = guardada(), erro = "";
    for (let n = 0; n < 5; n++) {
      if (!pw) pw = await pedir(erro);
      try { const d = await abrir(obj, pw); guardar(pw); return d; }
      catch (e) { guardar(""); pw = ""; erro = "Palavra-passe errada. Tenta outra vez."; }
    }
    throw new Error("dados cifrados: palavra-passe em falta");
  }
  window.CIFRA = {abrir, json, esquecer: () => guardar("")};
})();
