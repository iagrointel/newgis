"""Proxy HTTP de captura para provar que a tela não pede nada fora da instalação (item
L7-11-b-appliance-sem-internet). O navegador do e2e é apontado para cá (`PLAT_E2E_PROXY=http://127.0.0.1:<porta>`,
lido por `tests/e2e/conftest.py`); todo pedido passa por aqui. Host permitido (lista branca: a própria
instalação) é repassado — em fluxo, sem bufferizar, porque a plataforma usa SSE (`EventSource`) e um proxy que
espera o fim da resposta trava a tela; `CONNECT` (https, ou o "HTTPS upgrade" do Chromium) para host permitido
vira túnel. Qualquer outro host (CDN, fonte de letra, tile de terceiro, telemetria) é RECUSADO com 502 e contado
— o número de bloqueados é a medida "0 pedido a host externo" do portão. Biblioteca padrão só.

Uso como módulo: `p = ProxyCaptura(permitidos={"127.0.0.1", "localhost"}); p.iniciar(); ... p.parar()`;
`p.externos` é a lista de (método, host, caminho) recusados; `p.total` conta tudo que passou.
Uso como programa: `python -m tests.operacao.proxy_captura <porta> <host permitido,...> <arquivo de log>`."""

from __future__ import annotations

import http.client
import http.server
import json
import select
import socket
import sys
import threading
from urllib.parse import urlsplit

SALTO = {"connection", "keep-alive", "proxy-connection", "transfer-encoding", "content-length", "host"}
QUIETOS = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError)


class _Estado:
    def __init__(self, permitidos: set[str], log: str | None):
        self.permitidos = permitidos
        self.log = log
        self.externos: list[tuple[str, str, str]] = []
        self.total = 0
        self.trava = threading.Lock()

    def registrar(self, metodo: str, host: str, caminho: str, bloqueado: bool) -> None:
        with self.trava:
            self.total += 1
            if bloqueado:
                self.externos.append((metodo, host, caminho))
            if self.log:
                with open(self.log, "a", encoding="utf-8") as f:
                    linha = {"metodo": metodo, "host": host, "caminho": caminho, "bloqueado": bloqueado}
                    f.write(json.dumps(linha) + "\n")


def _tratador(estado: _Estado):
    class Tratador(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def handle(self):
            try:
                super().handle()
            except QUIETOS:
                pass  # o navegador fechou do lado dele (aborto de navegação): não é erro do proxy

        def _recusar(self, metodo: str, host: str, caminho: str) -> None:
            estado.registrar(metodo, host, caminho, True)
            corpo = b"proxy de captura: host fora da instalacao\n"
            self.send_response(502)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(corpo)
            self.close_connection = True

        def do_CONNECT(self):  # noqa: N802 — túnel para host permitido; recusa para o resto
            host, _, porta = self.path.rpartition(":")
            if host not in estado.permitidos:
                self._recusar("CONNECT", host, f":{porta}")
                return
            estado.registrar("CONNECT", host, f":{porta}", False)
            try:
                alvo = socket.create_connection((host, int(porta or 443)), timeout=10)
            except OSError:
                self._recusar("CONNECT", host, f":{porta}")
                return
            self.send_response(200, "Connection Established")
            self.end_headers()
            self.close_connection = True
            cliente = self.connection
            cliente.setblocking(True)
            alvo.setblocking(True)
            try:
                while True:
                    prontos, _, _ = select.select([cliente, alvo], [], [], 60)
                    if not prontos:
                        break
                    for s in prontos:
                        dados = s.recv(65536)
                        if not dados:
                            return
                        (alvo if s is cliente else cliente).sendall(dados)
            except QUIETOS:
                return
            finally:
                alvo.close()

        def _proxy(self):
            u = urlsplit(self.path)
            host = u.hostname or ""
            if host not in estado.permitidos:
                self._recusar(self.command, host, u.path)
                return
            estado.registrar(self.command, host, u.path, False)
            n = int(self.headers.get("Content-Length") or 0)
            corpo = self.rfile.read(n) if n else None
            con = http.client.HTTPConnection(host, u.port or 80, timeout=300)
            cab = {k: v for k, v in self.headers.items() if k.lower() not in SALTO}
            cab["Host"] = u.netloc
            if corpo is not None:
                cab["Content-Length"] = str(len(corpo))
            alvo = u.path + (f"?{u.query}" if u.query else "")
            try:
                con.request(self.command, alvo, body=corpo, headers=cab)
                r = con.getresponse()
            except OSError:
                self._recusar(self.command, host, u.path)
                return
            self.send_response(r.status)
            tamanho = r.getheader("Content-Length")
            for k, v in r.getheaders():
                if k.lower() in SALTO:
                    continue
                self.send_header(k, v)
            if tamanho is not None:
                self.send_header("Content-Length", tamanho)
            else:
                self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            # em FLUXO: SSE e respostas longas chegam ao navegador conforme o servidor escreve
            try:
                if self.command == "HEAD":
                    return
                while True:
                    pedaco = r.read(65536)
                    if not pedaco:
                        break
                    if tamanho is None:
                        self.wfile.write(f"{len(pedaco):x}\r\n".encode() + pedaco + b"\r\n")
                    else:
                        self.wfile.write(pedaco)
                    self.wfile.flush()
                if tamanho is None:
                    self.wfile.write(b"0\r\n\r\n")
            except QUIETOS:
                pass
            finally:
                con.close()

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = _proxy

        def log_message(self, *a):
            pass

    return Tratador


class ProxyCaptura:
    def __init__(self, permitidos: set[str], porta: int = 0, log: str | None = None):
        self.estado = _Estado(set(permitidos), log)
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", porta), _tratador(self.estado))
        self.srv.daemon_threads = True
        self.porta = self.srv.server_address[1]
        self.t = threading.Thread(target=self.srv.serve_forever, daemon=True)

    def iniciar(self) -> "ProxyCaptura":
        self.t.start()
        return self

    def parar(self) -> None:
        self.srv.shutdown()
        self.t.join(timeout=3)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.porta}"

    @property
    def externos(self) -> list[tuple[str, str, str]]:
        return list(self.estado.externos)

    @property
    def total(self) -> int:
        return self.estado.total


if __name__ == "__main__":
    porta = int(sys.argv[1])
    permitidos = set(sys.argv[2].split(","))
    log = sys.argv[3] if len(sys.argv) > 3 else None
    p = ProxyCaptura(permitidos, porta, log)
    print(f"proxy de captura em {p.url}; permitidos {sorted(permitidos)}; log {log}", flush=True)
    p.srv.serve_forever()
