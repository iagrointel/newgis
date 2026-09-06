"""Conserto do achado do adversário (laudo `laco/handoffs/T3/ataque-L6-hoje-ADVERSARIO.md`, item
L6-02-c-wfs-ogcapi, turno 3): o conector OGC API - Features anexava `Authorization: Bearer <credencial>` a
TODO link escolhido pelo servidor, inclusive `rel=next` para um host diferente do da conexão. Prova
determinística, offline: dois ouvintes no loopback, origens A (a conexão) e B (o `rel=next`), liberados pela
válvula `PLAT_TESTE_CONEXAO_ALVOS` (item L6-02-a). O teste correspondente do adversário
(`tests/adversario/test_advl6_conexao_externa.py::test_l6_02_c_credencial_vaza_para_host_externo_via_rel_next`,
commit 28db1c4) era `xfail(strict=True)`; aqui a mesma prova PASSA sem a marca — o conserto está em
`app.conexao.vetor_externo._conector_para_link`, chamado por `Paginador.paginas_json` antes de seguir
`pagina.proximo`.
"""

from __future__ import annotations

import http.server
import json
import socketserver
import threading

import pytest

from app.conexao import vetor_externo as ve

CREDENCIAL = "Bearer CREDENCIAL-DA-CASA"


def _sobe(handler_cls) -> tuple[socketserver.TCPServer, int]:
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def _fabrica(papel: str, recebido: dict, porta_b: int | None = None):
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            recebido.setdefault(papel, []).append(self.headers.get("Authorization"))
            if papel == "A":
                doc = {
                    "type": "FeatureCollection", "numberMatched": 2,
                    "features": [{"type": "Feature", "id": "1",
                                  "geometry": {"type": "Point", "coordinates": [10, 20]}, "properties": {}}],
                    "links": [{"rel": "next", "href": f"http://127.0.0.1:{porta_b}/coletor/items"}],
                }
            else:
                doc = {"type": "FeatureCollection", "numberMatched": 2,
                       "features": [{"type": "Feature", "id": "2",
                                     "geometry": {"type": "Point", "coordinates": [11, 21]}, "properties": {}}],
                       "links": []}
            b = json.dumps(doc).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/geo+json")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def log_message(self, *a):
            pass

    return H


@pytest.fixture
def valvula(monkeypatch):
    def _liga(*portas: int):
        monkeypatch.setenv("PLAT_TESTE_CONEXAO_ALVOS", ",".join(f"127.0.0.1:{p}" for p in portas))
    return _liga


def test_credencial_nao_atravessa_rel_next_para_outro_host(valvula):
    """A refutação do adversário, sem xfail: a credencial da conexão (host A) NÃO chega ao host B do
    `rel=next`, mas continua chegando a A (contraprova positiva — não é uma retirada cega de todo cabeçalho)."""
    recebido: dict[str, list] = {}
    sb, pb = _sobe(_fabrica("B", recebido))
    sa, pa = _sobe(_fabrica("A", recebido, porta_b=pb))
    valvula(pa, pb)
    try:
        conector = ve.Conector(tipo="ogc_api", url=f"http://127.0.0.1:{pa}/collections",
                               cabecalhos={"Authorization": CREDENCIAL})
        col = ve.Colecao(nome="obs", titulo=None, crs_nativo=None, srid_nativo=None,
                         srid_entregue=4326, extent_4326=None)
        paginador = ve.Paginador(conector, col, tam_pagina=1, limite=10)
        paginas = list(paginador.paginas_json())
    finally:
        sa.shutdown()
        sb.shutdown()

    assert len(paginas) == 2, "as duas páginas (A e B) têm de ter sido lidas — a defesa não pode parar a cópia"
    assert recebido.get("A") == [CREDENCIAL], "o host da própria conexão continua autenticado"
    assert recebido.get("B") == [None], "a credencial da casa NÃO pode chegar ao host do rel=next"
    assert any("mudou de origem" in a for a in paginador.relatorio.avisos), (
        "a mudança de origem tem de virar aviso rastreável, como todo desvio deste paginador"
    )


def test_credencial_continua_atravessando_rel_next_na_mesma_origem(valvula):
    """Controle: quando o `rel=next` fica na MESMA origem (mesmo host:porta, outro caminho), a credencial
    continua sendo enviada — a defesa é por origem, não uma retirada cega de toda credencial em toda página."""
    recebido: list[str | None] = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            recebido.append(self.headers.get("Authorization"))
            if self.path.startswith("/collections/obs/items") and "page=2" not in self.path:
                doc = {
                    "type": "FeatureCollection", "numberMatched": 2,
                    "features": [{"type": "Feature", "id": "1",
                                  "geometry": {"type": "Point", "coordinates": [10, 20]}, "properties": {}}],
                    "links": [{"rel": "next",
                               "href": f"http://127.0.0.1:{self.server.server_address[1]}"
                                       "/collections/obs/items?page=2"}],
                }
            else:
                doc = {"type": "FeatureCollection", "numberMatched": 2,
                       "features": [{"type": "Feature", "id": "2",
                                     "geometry": {"type": "Point", "coordinates": [11, 21]}, "properties": {}}],
                       "links": []}
            b = json.dumps(doc).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/geo+json")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def log_message(self, *a):
            pass

    sa, pa = _sobe(H)
    valvula(pa)
    try:
        conector = ve.Conector(tipo="ogc_api", url=f"http://127.0.0.1:{pa}/collections",
                               cabecalhos={"Authorization": CREDENCIAL})
        col = ve.Colecao(nome="obs", titulo=None, crs_nativo=None, srid_nativo=None,
                         srid_entregue=4326, extent_4326=None)
        paginador = ve.Paginador(conector, col, tam_pagina=1, limite=10)
        paginas = list(paginador.paginas_json())
    finally:
        sa.shutdown()

    assert len(paginas) == 2
    assert recebido == [CREDENCIAL, CREDENCIAL]
    assert not any("mudou de origem" in a for a in paginador.relatorio.avisos)


def test_rel_next_para_endereco_interno_continua_bloqueado(valvula):
    """Contraprova de que o conserto não afrouxou a defesa de SSRF já existente: `rel=next` para IP interno
    continua recusado por `buscar_seguro`, esteja a origem trocando de credencial ou não."""
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            doc = {"type": "FeatureCollection", "numberMatched": 2,
                   "features": [{"type": "Feature", "id": "1",
                                 "geometry": {"type": "Point", "coordinates": [10, 20]}, "properties": {}}],
                   "links": [{"rel": "next", "href": "http://169.254.169.254/latest/meta-data/"}]}
            b = json.dumps(doc).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/geo+json")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def log_message(self, *a):
            pass

    sa, pa = _sobe(H)
    valvula(pa)
    try:
        conector = ve.Conector(tipo="ogc_api", url=f"http://127.0.0.1:{pa}/collections",
                               cabecalhos={"Authorization": CREDENCIAL})
        col = ve.Colecao(nome="obs", titulo=None, crs_nativo=None, srid_nativo=None,
                         srid_entregue=4326, extent_4326=None)
        with pytest.raises(ve.ErroConector) as ei:
            list(ve.Paginador(conector, col, tam_pagina=1, limite=10).paginas_json())
        assert "ip_bloqueado" in str(ei.value)
    finally:
        sa.shutdown()
