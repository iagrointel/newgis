"""Servidor HTTP de prova para o item L6-02-h (arquivo por URL).

Por que ele existe: a defesa de SSRF do L6-02-a recusa 127.0.0.1, ::1, 10/8, 192.168/16, 169.254/16 e qualquer
nome que RESOLVA para uma dessas faixas. Um servidor de teste em `localhost` seria — corretamente — recusado, e
testar contra ele exigiria desligar a defesa, o que tornaria o teste inútil. A saída é servir os arquivos no
endereço PÚBLICO desta máquina (`ip -4 addr`, escopo global, fora das faixas privadas) e buscá-los por ele: a
defesa continua inteira e a busca é uma requisição de rede de verdade.

O servidor entende requisição condicional (`If-None-Match`/`If-Modified-Since` -> 304), sabe trocar o conteúdo
de uma rota entre uma sincronização e outra, sabe responder 200 com o MESMO corpo ignorando o condicional (para
provar a segunda linha de defesa, o sha256) e sabe redirecionar para um destino escolhido pelo teste (para
provar que credencial não atravessa host e que redirecionamento para endereço interno é recusado).
"""

from __future__ import annotations

import hashlib
import http.server
import ipaddress
import socket
import socketserver
import subprocess
import threading
from dataclasses import dataclass, field


def ip_publico() -> str:
    """Primeiro IPv4 de escopo global desta máquina que não caia em faixa recusada pelo validador. Levanta se
    não houver: sem isso não existe teste honesto de busca por URL nesta máquina."""
    saida = subprocess.run(["ip", "-4", "-o", "addr", "show", "scope", "global"],
                           capture_output=True, text=True, check=True).stdout
    for linha in saida.splitlines():
        partes = linha.split()
        if "inet" not in partes:
            continue
        endereco = partes[partes.index("inet") + 1].split("/")[0]
        ip = ipaddress.ip_address(endereco)
        if not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast):
            return endereco
    raise RuntimeError("esta máquina não tem IPv4 público; o teste de arquivo por URL não pode ser honesto aqui")


@dataclass
class Recurso:
    corpo: bytes
    content_type: str = "application/octet-stream"
    etag: str | None = None                 # None = ETag calculado do sha256 do corpo
    last_modified: str | None = None
    ignorar_condicional: bool = False       # responde 200 mesmo com If-None-Match igual (servidor mal-educado)
    redireciona_para: str | None = None     # devolve 302 para cá em vez do corpo
    status_redirecionamento: int = 302
    pedidos: list[dict] = field(default_factory=list)   # cabeçalhos de cada requisição recebida

    def etag_atual(self) -> str:
        return self.etag or ('"' + hashlib.sha256(self.corpo).hexdigest()[:32] + '"')


class ServidorArquivos:
    """Uso: `with ServidorArquivos() as s: s.publicar("/a.csv", corpo); s.url("/a.csv")`."""

    def __init__(self):
        self.recursos: dict[str, Recurso] = {}
        servidor_pai = self

        class Manipulador(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def _responder(self, status: int, corpo: bytes = b"", cabecalhos: dict | None = None):
                self.send_response(status)
                for k, v in (cabecalhos or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                if corpo:
                    self.wfile.write(corpo)

            def do_GET(self):  # noqa: N802 — nome exigido pela BaseHTTPRequestHandler
                caminho = self.path.split("?")[0]
                recurso = servidor_pai.recursos.get(caminho)
                if recurso is None:
                    self._responder(404, b"nao encontrado", {"Content-Type": "text/plain"})
                    return
                recurso.pedidos.append({k.lower(): v for k, v in self.headers.items()})
                if recurso.redireciona_para:
                    self._responder(recurso.status_redirecionamento, b"",
                                    {"Location": recurso.redireciona_para, "Content-Type": "text/plain"})
                    return
                etag = recurso.etag_atual()
                condicional = self.headers.get("If-None-Match")
                modificado_desde = self.headers.get("If-Modified-Since")
                if not recurso.ignorar_condicional and (
                    (condicional and condicional == etag)
                    or (modificado_desde and recurso.last_modified and modificado_desde == recurso.last_modified)
                ):
                    self._responder(304, b"", {"ETag": etag})
                    return
                cabecalhos = {"Content-Type": recurso.content_type, "ETag": etag}
                if recurso.last_modified:
                    cabecalhos["Last-Modified"] = recurso.last_modified
                self._responder(200, recurso.corpo, cabecalhos)

            def log_message(self, *args):  # silencia o log do http.server na saída do pytest
                return

        class Servidor(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True

        self._servidor = Servidor(("0.0.0.0", 0), Manipulador)  # noqa: S104 — o teste precisa do IP público
        self.porta = self._servidor.server_address[1]
        self.host = ip_publico()
        self._thread = threading.Thread(target=self._servidor.serve_forever, daemon=True)

    def __enter__(self) -> ServidorArquivos:
        self._thread.start()
        # confirma que o socket responde no endereço público antes de qualquer teste depender disso
        with socket.create_connection((self.host, self.porta), timeout=5):
            pass
        return self

    def __exit__(self, *exc):
        self._servidor.shutdown()
        self._servidor.server_close()
        self._thread.join(timeout=5)

    def publicar(self, caminho: str, corpo: bytes, **kw) -> Recurso:
        r = Recurso(corpo=corpo, **kw)
        self.recursos[caminho] = r
        return r

    def url(self, caminho: str) -> str:
        return f"http://{self.host}:{self.porta}{caminho}"
