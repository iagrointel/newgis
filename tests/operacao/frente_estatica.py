"""Frente de teste para rodar o e2e contra o uvicorn de uma trilha (itens L6-02-m e L7-11-b): faz o papel do
nginx de produção — serve `/static/` direto de `web/`, repassa o resto ao uvicorn e reescreve `Origin`/`Referer`
para a URL pública configurada (a checagem de origem da sessão exige a URL pública, que é https). Biblioteca
padrão só; nunca usar em produção.

uso: python3 tests/operacao/frente_estatica.py <porta_frente> <porta_uvicorn> <dir_web> [<PLAT_URL_PUBLICA>]"""

import http.client
import http.server
import mimetypes
import sys
from pathlib import Path

PORTA = int(sys.argv[1])
ALVO = int(sys.argv[2])
WEB = Path(sys.argv[3]).resolve()
PUBLICA = sys.argv[4].rstrip("/") if len(sys.argv) > 4 else ""
SALTO = {"connection", "keep-alive", "transfer-encoding", "content-length", "host"}


class Frente(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _estatico(self):
        rel = self.path[len("/static/"):].split("?", 1)[0]
        alvo = (WEB / rel).resolve()
        if not str(alvo).startswith(str(WEB)) or not alvo.is_file():
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        corpo = alvo.read_bytes()
        tipo = mimetypes.guess_type(str(alvo))[0] or "application/octet-stream"
        if alvo.suffix == ".js":
            tipo = "text/javascript"
        if alvo.suffix == ".pmtiles":
            tipo = "application/octet-stream"
        # Range (206) como o nginx: o PMTiles é lido por intervalo pelo navegador; nunca gzip
        faixa = self.headers.get("Range")
        inicio, fim = 0, len(corpo) - 1
        status = 200
        if faixa and faixa.startswith("bytes="):
            a, _, b = faixa[6:].partition("-")
            inicio = int(a) if a else max(0, len(corpo) - int(b))
            fim = min(int(b), len(corpo) - 1) if (b and a) else (len(corpo) - 1)
            status = 206
        pedaco = corpo[inicio : fim + 1]
        self.send_response(status)
        self.send_header("Content-Type", f"{tipo}; charset=utf-8" if tipo.startswith("text/") else tipo)
        self.send_header("Content-Length", str(len(pedaco)))
        self.send_header("Accept-Ranges", "bytes")
        if status == 206:
            self.send_header("Content-Range", f"bytes {inicio}-{fim}/{len(corpo)}")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(pedaco)

    def _proxy(self):
        n = int(self.headers.get("Content-Length") or 0)
        corpo = self.rfile.read(n) if n else None
        con = http.client.HTTPConnection("127.0.0.1", ALVO, timeout=120)
        cab = {k: v for k, v in self.headers.items() if k.lower() not in SALTO}
        cab["Host"] = f"127.0.0.1:{PORTA}"
        # o nginx termina o TLS em produção: o navegador manda Origin/Referer da URL pública https; aqui a frente
        # faz o mesmo papel, trocando a origem de teste (http://127.0.0.1:porta) pela URL pública da trilha
        meu = f"http://127.0.0.1:{PORTA}"
        for k in ("Origin", "Referer"):
            v = cab.get(k)
            if v and v.startswith(meu):
                cab[k] = PUBLICA + v[len(meu):]
        if corpo is not None:
            cab["Content-Length"] = str(len(corpo))
        con.request(self.command, self.path, body=corpo, headers=cab)
        r = con.getresponse()
        dados = r.read()
        self.send_response(r.status)
        for k, v in r.getheaders():
            if k.lower() in SALTO:
                continue
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(dados)
        con.close()

    def _tratar(self):
        if self.path.startswith("/static/"):
            self._estatico()
        else:
            self._proxy()

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = _tratar

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    http.server.ThreadingHTTPServer(("127.0.0.1", PORTA), Frente).serve_forever()
