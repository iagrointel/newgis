"""Adversário independente dos itens L6-02-c-wfs-ogcapi (sha b2bd88e) e L6-02-h-csv-url-geojson-kml
(sha 323f271). Nada é consertado aqui — cada achado é um teste `xfail(strict=True)`, determinístico e
offline (servidor de prova no loopback, liberado pela válvula `PLAT_TESTE_CONEXAO_ALVOS`).

Rodar (na trilha do adversário, base própria `plat_tadvl6`):
    set -a; source /home/dev/plataforma/laco/var/trilha/advl6.env; set +a
    venv/bin/pytest tests/adversario/test_advl6_conexao_externa.py -q -p no:randomly
"""

from __future__ import annotations

import http.server
import io
import json
import os
import socketserver
import threading
import zipfile

import pytest


def _sobe(handler_cls) -> tuple[socketserver.TCPServer, int]:
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


@pytest.mark.xfail(strict=True, reason="L6-02-c: o Bearer da conexão vaza para qualquer host público "
                   "indicado no link rel=next (controlado pelo servidor). buscar_seguro só retira a "
                   "credencial em REDIRECT cross-host; o rel=next é caminho do CHAMADOR e não é coberto.")
def test_l6_02_c_credencial_vaza_para_host_externo_via_rel_next():
    from app.conexao import vetor_externo as ve

    recebido: dict[str, list] = {}

    def fabrica(papel: str, porta_b: int | None = None):
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

    sb, pb = _sobe(fabrica("B"))
    sa, pa = _sobe(fabrica("A", porta_b=pb))
    os.environ["PLAT_TESTE_CONEXAO_ALVOS"] = f"127.0.0.1:{pa},127.0.0.1:{pb}"
    try:
        conector = ve.Conector(tipo="ogc_api", url=f"http://127.0.0.1:{pa}/collections",
                               cabecalhos={"Authorization": "Bearer CREDENCIAL-DA-CASA"})
        col = ve.Colecao(nome="obs", titulo=None, crs_nativo=None, srid_nativo=None,
                         srid_entregue=4326, extent_4326=None)
        list(ve.Paginador(conector, col, tam_pagina=1, limite=10).paginas_json())
    finally:
        sa.shutdown(); sb.shutdown()
        os.environ.pop("PLAT_TESTE_CONEXAO_ALVOS", None)

    vazou = "Bearer CREDENCIAL-DA-CASA" in (recebido.get("B") or [])
    # o teste PASSA (xfail vira xpass=falha) se a credencial NÃO chegar ao host B do rel=next.
    assert not vazou, "a credencial da casa chegou ao host do rel=next (host diferente do da conexão)"


def test_l6_02_c_rel_next_para_endereco_interno_e_bloqueado():
    """Contraprova (NÃO xfail): o rel=next para um endereço interno É recusado por buscar_seguro. A defesa
    de SSRF do rel=next funciona; o que falha é a proteção da CREDENCIAL para host EXTERNO (teste acima)."""
    from app.conexao import vetor_externo as ve

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
    os.environ["PLAT_TESTE_CONEXAO_ALVOS"] = f"127.0.0.1:{pa}"
    try:
        conector = ve.Conector(tipo="ogc_api", url=f"http://127.0.0.1:{pa}/collections",
                               cabecalhos={"Authorization": "Bearer K"})
        col = ve.Colecao(nome="obs", titulo=None, crs_nativo=None, srid_nativo=None,
                         srid_entregue=4326, extent_4326=None)
        with pytest.raises(ve.ErroConector) as ei:
            list(ve.Paginador(conector, col, tam_pagina=1, limite=10).paginas_json())
        assert "ip_bloqueado" in str(ei.value)
    finally:
        sa.shutdown()
        os.environ.pop("PLAT_TESTE_CONEXAO_ALVOS", None)


@pytest.mark.xfail(strict=True, reason="L6-02-h: o teto de memória dos formatos XML (40 MiB) é aplicado "
                   "sobre os bytes COMPRIMIDOS. Um KMZ de ~1 MiB que declara ~300 MiB descomprimidos passa "
                   "por analisar(); o teto anunciado ('o GDAL lê o documento inteiro na memória') não segura "
                   "o KMZ. O bound real é o RLIMIT_DATA do job, não os 40 MiB.")
def test_l6_02_h_teto_xml_do_kmz_burlado_por_compressao():
    from app import limites
    from app.conexao import arquivo_url as au

    cab = '<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
    pm = '<Placemark><name>x</name><Point><coordinates>10,20</coordinates></Point></Placemark>'
    alvo = 300 * 1024 * 1024
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        with z.open("doc.kml", "w") as f:
            f.write(cab.encode())
            bloco = (pm * 2000).encode()
            escrito = 0
            while escrito < alvo:
                f.write(bloco)
                escrito += len(bloco)
            f.write(b"</Document></kml>")
    dados = buf.getvalue()
    with zipfile.ZipFile(io.BytesIO(dados)) as z:
        descomprimido = sum(i.file_size for i in z.infolist())

    assert len(dados) <= limites.CONEXAO_ARQUIVO_XML_MAX_BYTES  # o download passa no teto XML
    assert descomprimido > limites.CONEXAO_ARQUIVO_XML_MAX_BYTES  # mas o conteúdo o estoura de longe

    # o teste PASSA (xfail vira xpass=falha) só se analisar() RECUSAR o KMZ que estoura o teto de memória.
    with pytest.raises(au.ArquivoRecusado):
        au.analisar(dados)
