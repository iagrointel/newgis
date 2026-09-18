"""Frente HTTP mínima para rodar e2e de navegador contra um uvicorn de TRILHA, sem nginx (item L0-03-e; regra do
brief de worktrees: cada trilha sobe a própria API numa porta e nunca toca o nginx da máquina). Faz as duas coisas que
o nginx faz em produção e em homologação (deploy/nginx*.conf) e que a app, de propósito, não faz:
  1. serve /static/ direto de web/ (a app não serve estático; sem isto todo teste de tela morre em 404 de JS/CSS);
  2. faz o navegador chegar com o Origin da URL pública: o CSRF da sessão (ADR 0002 seção 5.3) só aceita
     `Origin == PLAT_URL_PUBLICA` (https), e o Chromium não deixa o playwright reescrever esse cabeçalho
     (medido: route.continue_ e extra_http_headers são ignorados para Origin) — então a frente troca o cabeçalho ao
     encaminhar, como o domínio real faz por ser o próprio Origin. O CSRF continua provado em tests/api/test_sessao.py.
Contra uma URL que já tem nginx na frente (/static/ responde 200), `se_preciso` devolve None e nada muda."""

import http.client
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

WEB = (Path(__file__).resolve().parents[2] / "web").resolve()
MIME = {
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".css": "text/css",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
    ".html": "text/html",
}
NAO_ENCAMINHA = frozenset({"host", "origin", "connection", "accept-encoding"})
NAO_DEVOLVE = frozenset({"transfer-encoding", "content-length", "connection"})


class _Encaminhador(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    alvo: tuple[str, int] = ("127.0.0.1", 0)
    url_publica: str = ""

    def log_message(self, *args) -> None:  # silêncio: o pytest já captura o que importa
        return

    def _responder(self, status: int, corpo: bytes, tipo: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corpo)

    def _estatico(self) -> None:
        rel = urlparse(self.path).path[len("/static/") :]
        arq = (WEB / rel).resolve()
        if not str(arq).startswith(str(WEB)) or not arq.is_file():
            self._responder(404, b"", "text/plain")
            return
        tipo = MIME.get(arq.suffix) or mimetypes.guess_type(arq.name)[0] or "application/octet-stream"
        self._responder(200, arq.read_bytes(), tipo)

    def _encaminhar(self) -> None:
        tamanho = int(self.headers.get("Content-Length") or 0)
        corpo = self.rfile.read(tamanho) if tamanho else None
        cabecalhos = {k: v for k, v in self.headers.items() if k.lower() not in NAO_ENCAMINHA}
        if self.headers.get("Origin"):
            cabecalhos["Origin"] = self.url_publica
        cabecalhos["Host"] = f"{self.alvo[0]}:{self.alvo[1]}"
        con = http.client.HTTPConnection(self.alvo[0], self.alvo[1], timeout=60)
        try:
            con.request(self.command, self.path, body=corpo, headers=cabecalhos)
            resp = con.getresponse()
            dados = resp.read()
            self.send_response(resp.status)
            for k, v in resp.getheaders():  # lista: vários Set-Cookie sobrevivem
                if k.lower() not in NAO_DEVOLVE:
                    self.send_header(k, v)
            self.send_header("Content-Length", str(len(dados)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(dados)
        finally:
            con.close()

    def do_GET(self) -> None:
        if self.path.startswith("/static/"):
            self._estatico()
        else:
            self._encaminhar()

    do_HEAD = do_GET
    do_POST = do_PUT = do_DELETE = do_PATCH = _encaminhar


class FrenteTrilha:
    """`with FrenteTrilha(base_url, url_publica) as f: f.url` — porta efêmera em 127.0.0.1, uma thread por conexão."""

    def __init__(self, base_url: str, url_publica: str):
        u = urlparse(base_url)
        self.alvo = (u.hostname or "127.0.0.1", u.port or (443 if u.scheme == "https" else 80))
        self.url_publica = url_publica.rstrip("/")
        self.url = ""
        self._servidor = None
        self._thread = None

    @classmethod
    def se_preciso(cls, base_url: str, url_publica: str):
        """None quando o navegador já vai chegar com o Origin certo; a frente quando não vai.

        18/09/2026 — esta decisão era tomada por outra pergunta: "`/static/style.css` responde 200?". A
        premissa era que só o nginx serve estático. Deixou de ser verdade: `app/main.py` monta `/static`
        para QUALQUER ambiente que não seja produção (dois blocos `if not settings.producao`, de duas
        trilhas que acrescentaram o mesmo remendo). Com isso a resposta era sempre "sim", a frente nunca
        subia, e o navegador chegava com `Origin: http://127.0.0.1:<porta>` — que o CSRF da sessão (ADR
        0002 seção 5.3) recusa com 403 `origem da requisição não é a da plataforma`. Efeito medido no item
        L0-03-f: TODA ação de escrita pela tela (criar pasta, mover, compartilhar) reprovava o e2e de
        trilha, e a falha parecia da tela.

        A pergunta certa é a que a frente existe para responder: o Origin que o navegador vai mandar é o
        que o CSRF espera? Se for (rodando contra a URL pública, com nginx), nada a fazer."""
        def origem(u: str) -> tuple[str, str]:
            p = urlparse(u)
            return (p.scheme, p.netloc)

        if not url_publica or origem(base_url) == origem(url_publica):
            return None
        return cls(base_url, url_publica)

    def __enter__(self):
        classe = type("Encaminhador", (_Encaminhador,), {"alvo": self.alvo, "url_publica": self.url_publica})
        self._servidor = ThreadingHTTPServer(("127.0.0.1", 0), classe)
        self._servidor.daemon_threads = True
        self._thread = threading.Thread(target=self._servidor.serve_forever, daemon=True)
        self._thread.start()
        self.url = f"http://127.0.0.1:{self._servidor.server_address[1]}"
        return self

    def __exit__(self, *exc) -> None:
        if self._servidor is not None:
            self._servidor.shutdown()
            self._servidor.server_close()
