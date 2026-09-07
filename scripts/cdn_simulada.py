#!/usr/bin/env python3
"""Simulação LOCAL de uma CDN na frente do serviço de ladrilho (item L7-26-cdn-tiles).

⛔ Isto NÃO é a Cloudflare. Não há conta, não há DNS, não há Cache Rule de verdade — a regra da casa
para este item proíbe fingir acesso que não existe (ver `docs/CDN.md`). O que este servidor prova é o
MECANISMO que a hipótese descreve: chave de cache por caminho + query string completa (`Cache-Control`
do próprio ladrilho decidindo se o objeto é elegível a ficar guardado para sempre) e purge por prefixo
de caminho — a mesma operação que a API de purge da Cloudflare faz, só que contra este dicionário em
memória em vez do PoP deles.

CORREÇÃO à hipótese original (achado desta bancada, ver docs/CDN.md e o ADR 20260907T1522 §2): a
hipótese pedia "chave de cache sem query string". Isso colide duas renderizações diferentes do MESMO
`item@versao/z/x/y` (ex.: `?bandas=3,2,1` vs `?expressao=NDVI`) no mesmo slot de cache — um cliente
recebe a imagem do OUTRO. A versão no caminho resolve "o byte não muda com o TEMPO"; não resolve
"parâmetros de renderização diferentes apontam para bytes diferentes", que é outra dimensão. A chave
usada aqui é caminho + query string completa (o padrão real de uma Cache Rule sem "ignore query
string" configurado) — sem perda prática, porque o TileJSON embute os MESMOS parâmetros de
renderização em todo ladrilho que um cliente de mapa pede.

Escopo do cache: só caminhos que TERMINAM em ladrilho XYZ ou WMTS GetTile sob `/svc/...` — o mesmo
recorte que, numa conta real, seria "hostname `tiles-<x>.iagrointel.com`, regra restrita ao prefixo do
ladrilho". Toda outra rota (`/api/...`, TileJSON, WMTS GetCapabilities, `info.json`) passa direto ao
destino, sem cache, com `cf-cache-status: BYPASS` — é a prova da cláusula 4 do portão: a API do app não
tem cabeçalho de cache de CDN porque ela nem passa por este prefixo em produção (hostname separado,
D19: o app continua DNS-only).

Uso:
  scripts/cdn_simulada.py --origem http://127.0.0.1:8274 --porta 8275

Purge por prefixo (mesmo verbo que a API de purge real usa, POST com lista):
  curl -X POST http://127.0.0.1:8275/__purgar__ -d '{"prefixos": ["/svc/<token>/"]}'
"""

from __future__ import annotations

import argparse
import json
import re
import secrets
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

# ladrilho XYZ (com ou sem extensão) ou GetTile do WMTS em forma KVP — o resto de /svc/ (tilejson,
# info.json, wmts capabilities) fica de fora de propósito: essas respostas já vêm com `no-store` da
# aplicação e não são o que a CDN de ladrilho existe para guardar.
_RE_TILE_XYZ = re.compile(r"^/svc/[^/]+/(raster|mosaico)/[^/]+/\d+/\d+/\d+(\.[A-Za-z0-9]+)?$")


def _e_ladrilho(caminho: str, query: str) -> bool:
    if _RE_TILE_XYZ.match(caminho):
        return True
    if caminho.startswith("/svc/") and "/wmts" in caminho:
        return "REQUEST=GetTile" in query or "request=GetTile" in query
    return False


class Cache:
    """Dicionário protegido por lock — um processo, várias threads (ThreadingHTTPServer)."""

    def __init__(self) -> None:
        self._dados: dict[str, dict] = {}
        self._lock = threading.Lock()
        self.acertos = 0
        self.faltas = 0

    def obter(self, chave: str) -> dict | None:
        with self._lock:
            item = self._dados.get(chave)
            if item is not None:
                self.acertos += 1
            else:
                self.faltas += 1
            return item

    def guardar(self, chave: str, valor: dict) -> None:
        with self._lock:
            self._dados[chave] = valor

    def purgar_prefixos(self, prefixos: list[str]) -> int:
        with self._lock:
            removidos = [k for k in self._dados if any(k.startswith(p) for p in prefixos)]
            for k in removidos:
                del self._dados[k]
            return len(removidos)

    def tamanho(self) -> int:
        with self._lock:
            return len(self._dados)


class Handler(BaseHTTPRequestHandler):
    origem: str = ""
    cache: Cache = None  # type: ignore[assignment]
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # silencioso: bancada, não terminal do dono
        pass

    def _cf_ray(self) -> str:
        return f"{secrets.token_hex(8)}-GRU"

    def do_GET(self):  # noqa: N802
        self._tratar()

    def do_HEAD(self):  # noqa: N802
        self._tratar(sem_corpo=True)

    def do_POST(self):  # noqa: N802
        if self.path == "/__purgar__":
            tamanho = int(self.headers.get("Content-Length", "0") or "0")
            corpo = self.rfile.read(tamanho) if tamanho else b"{}"
            try:
                pedido = json.loads(corpo or b"{}")
            except json.JSONDecodeError:
                pedido = {}
            prefixos = pedido.get("prefixos") or []
            if not isinstance(prefixos, list) or not prefixos or len(prefixos) > 100:
                self._responder(422, {"erro": "de 1 a 100 prefixos, em lista"}, {})
                return
            removidos = self.cache.purgar_prefixos([str(p) for p in prefixos])
            self._responder(200, {"prefixos": prefixos, "removidos": removidos}, {})
            return
        self._tratar()

    def _responder(self, status: int, corpo_json: dict, cabecalhos: dict) -> None:
        dados = json.dumps(corpo_json).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(dados)))
        for k, v in cabecalhos.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(dados)

    def _tratar(self, sem_corpo: bool = False) -> None:
        partes = urlsplit(self.path)
        cacheavel = _e_ladrilho(partes.path, partes.query)
        # ACHADO desta bancada, correção da hipótese original do item (que pedia "chave de cache sem
        # query string"): ignorar a query string faz DUAS renderizações do MESMO z/x/y colidirem no
        # mesmo slot de cache — um cliente pedindo NDVI (`?expressao=...`) e outro pedindo RGB
        # (`?bandas=3,2,1`) do MESMO `item@versao` recebiam, um dos dois, a imagem ERRADA (confirmado
        # nesta bancada: o 2º pedido, com query DIFERENTE do 1º, veio como HIT com os bytes do 1º). A
        # versão no CAMINHO garante que o BYTE não muda AO LONGO DO TEMPO; não garante que dois
        # PARÂMETROS DE RENDERIZAÇÃO diferentes apontem para bytes iguais — são dimensões diferentes.
        # Correção: a chave de cache é caminho + query string completa (o padrão real da Cloudflare,
        # que só ignora query string se alguém configurar isso explicitamente na Cache Rule — o que
        # NÃO deve ser feito para este prefixo, ver docs/CDN.md). O cliente de mapa nunca sente
        # diferença: o TileJSON já embute os mesmos parâmetros de renderização em TODO ladrilho que
        # ele pede, então a query string é idêntica pedido a pedido dentro de uma mesma sessão de mapa.
        chave = self.path

        if cacheavel:
            guardado = self.cache.obter(chave)
            if guardado is not None:
                self._servir_guardado(guardado, sem_corpo)
                return

        try:
            status, cabecalhos, corpo = self._buscar_origem()
        except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
            self._responder(502, {"erro": "origem_inacessivel", "detalhe": str(e)}, {})
            return

        cabecalhos_saida = dict(cabecalhos)
        cabecalhos_saida["cf-ray"] = self._cf_ray()
        if cacheavel:
            cabecalhos_saida["cf-cache-status"] = "MISS"
            if status in (200, 204):
                self.cache.guardar(chave, {
                    "status": status, "headers": dict(cabecalhos), "body": corpo,
                    "guardado_em": time.time(),
                })
        else:
            cabecalhos_saida["cf-cache-status"] = "BYPASS"

        self.send_response(status)
        for k, v in cabecalhos_saida.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        if not sem_corpo:
            self.wfile.write(corpo)

    def _servir_guardado(self, guardado: dict, sem_corpo: bool) -> None:
        self.send_response(guardado["status"])
        for k, v in guardado["headers"].items():
            if k.lower() in ("content-length", "connection"):
                continue
            self.send_header(k, v)
        self.send_header("cf-cache-status", "HIT")
        self.send_header("cf-ray", self._cf_ray())
        self.send_header("Content-Length", str(len(guardado["body"])))
        self.end_headers()
        if not sem_corpo:
            self.wfile.write(guardado["body"])

    def _buscar_origem(self) -> tuple[int, dict, bytes]:
        url = self.origem.rstrip("/") + self.path
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                corpo = resp.read()
                cabecalhos = {k: v for k, v in resp.headers.items()
                             if k.lower() not in ("connection", "content-length", "transfer-encoding")}
                return resp.status, cabecalhos, corpo
        except urllib.error.HTTPError as e:
            corpo = e.read()
            cabecalhos = {k: v for k, v in e.headers.items()
                         if k.lower() not in ("connection", "content-length", "transfer-encoding")}
            return e.code, cabecalhos, corpo


def subir(origem: str, porta: int) -> ThreadingHTTPServer:
    Handler.origem = origem
    Handler.cache = Cache()
    servidor = ThreadingHTTPServer(("127.0.0.1", porta), Handler)
    return servidor


def principal() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--origem", required=True, help="URL base da aplicação (origem)")
    ap.add_argument("--porta", type=int, required=True, help="porta em que a CDN simulada escuta")
    args = ap.parse_args()
    servidor = subir(args.origem, args.porta)
    print(f"cdn simulada: 127.0.0.1:{args.porta} -> {args.origem} (Ctrl+C para sair)")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()


if __name__ == "__main__":
    principal()
