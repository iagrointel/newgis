"""Catálogo de conectores públicos sem rede externa (item L6-02-m-catalogo-endpoints-brasil): a regra de "vivo"
(assinatura do corpo, não só HTTP 200 — refutação: "endpoint 200 que devolve HTML de erro conta como morto"),
a derivação de (tipo, url base) a partir das URLs do registro e a validade da semente curada. O servidor de
teste liga no IP PÚBLICO da máquina (buscar_seguro recusa loopback por desenho)."""

from __future__ import annotations

import http.server
import ipaddress
import subprocess
import threading

import pytest

from app.conexao import endpoints_publicos as ep

CAPABILITIES = (
    b'<?xml version="1.0"?><WMS_Capabilities version="1.3.0"><Service><Title>x</Title></Service></WMS_Capabilities>'
)
EXCEPTION = (
    b'<?xml version="1.0"?><ServiceExceptionReport><ServiceException>x</ServiceException></ServiceExceptionReport>'
)
HTML = b"<!DOCTYPE html><html><body><h1>Erro 200</h1></body></html>"
ARCGIS_OK = b'{"currentVersion": 11.1, "folders": [], "services": []}'
ARCGIS_ERRO = b'{"error": {"code": 500, "message": "Token Required"}}'
STAC_OK = b'{"stac_version": "1.0.0", "id": "x", "links": []}'
OGC_API_OK = b'{"title": "x", "links": [{"rel": "self", "href": "/"}]}'
RESPOSTAS = {
    "/wms-ok": ("application/xml", CAPABILITIES), "/wms-exc": ("application/xml", EXCEPTION),
    "/wms-html": ("text/html", HTML), "/wms-vazio": ("application/xml", b""),
    "/arcgis-ok": ("application/json", ARCGIS_OK), "/arcgis-erro": ("application/json", ARCGIS_ERRO),
    "/stac-ok": ("application/json", STAC_OK), "/stac-html": ("text/html", HTML),
    "/ogc-ok": ("application/json", OGC_API_OK), "/ogc-lista": ("application/json", b"[1,2]"),
}


def _ip_publico_desta_maquina() -> str | None:
    try:
        saida = subprocess.run(
            ["ip", "-4", "-o", "addr", "show", "scope", "global"], capture_output=True, text=True, timeout=3
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for linha in saida.splitlines():
        partes = linha.split()
        if len(partes) < 4:
            continue
        ip = partes[3].split("/")[0]
        try:
            if ipaddress.ip_address(ip).is_global:
                return ip
        except ValueError:
            continue
    return None


class _Servidor(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        caminho = self.path.split("?", 1)[0]
        tipo, corpo = RESPOSTAS.get(caminho, ("text/html", HTML))
        self.send_response(404 if caminho == "/nao-existe" else 200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def base():
    ip = _ip_publico_desta_maquina()
    if ip is None:
        pytest.skip("máquina sem IP público roteável")
    srv = http.server.HTTPServer((ip, 0), _Servidor)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://{ip}:{srv.server_address[1]}"
    finally:
        srv.shutdown()
        t.join(timeout=2)


@pytest.mark.parametrize(
    "caminho,tipo,vivo,motivo",
    [
        ("/wms-ok", "wms", True, "ok"),
        ("/wms-ok", "wfs", True, "ok"),
        ("/wms-ok", "wmts", True, "ok"),
        ("/wms-exc", "wms", False, "exception_report"),
        ("/wms-html", "wms", False, "html_no_lugar_do_servico"),  # HTTP 200 com HTML: morto (refutação)
        ("/wms-vazio", "wms", False, "corpo_vazio"),
        ("/arcgis-ok", "esri_rest", True, "ok"),
        ("/arcgis-erro", "esri_rest", False, "arcgis_error"),  # 200 com {"error": ...}: morto
        ("/stac-ok", "stac", True, "ok"),
        ("/stac-html", "stac", False, "html_no_lugar_do_servico"),
        ("/ogc-ok", "ogc_api", True, "ok"),
        ("/ogc-lista", "ogc_api", False, "json_nao_e_objeto"),
        ("/nao-existe", "wms", False, "http_404"),
    ],
)
def test_vivo_exige_a_assinatura_do_protocolo(base, caminho, tipo, vivo, motivo):
    r = ep.testar(f"{base}{caminho}", tipo)
    assert (r.vivo, r.motivo) == (vivo, motivo), r
    assert r.ms >= 0


def test_tipo_desconhecido_e_url_interna_nunca_levantam():
    assert ep.testar("https://exemplo.invalido/x", "ftp").motivo.startswith("tipo_desconhecido")
    r = ep.testar("http://127.0.0.1:8150/geoserver/ows", "wms")
    assert r.vivo is False and r.motivo.startswith("url_insegura")


def test_url_de_teste_por_tipo():
    assert ep.url_de_teste("https://a/geoserver/ows", "wms") == "https://a/geoserver/ows?SERVICE=WMS&REQUEST=GetCapabilities"
    assert ep.url_de_teste("https://a/ows?x=1", "wfs") == "https://a/ows?x=1&SERVICE=WFS&REQUEST=GetCapabilities"
    assert ep.url_de_teste("https://a/ows?request=GetCapabilities&service=WMS", "wms").count("GetCapabilities") == 1
    assert ep.url_de_teste("https://a/arcgis/rest/services", "esri_rest") == "https://a/arcgis/rest/services?f=json"
    assert ep.url_de_teste("https://a/stac/v1", "stac") == "https://a/stac/v1"


@pytest.mark.parametrize(
    "url,esperado",
    [
        ("https://x.gov.br/geoserver/ows?service=WFS&request=GetCapabilities", [("wfs", "https://x.gov.br/geoserver/ows")]),
        ("https://x.gov.br/geoserver/ows", [("wms", "https://x.gov.br/geoserver/ows"), ("wfs", "https://x.gov.br/geoserver/ows")]),
        ("https://x.gov.br/geoserver/a/wms?layers=b", [("wms", "https://x.gov.br/geoserver/a/wms")]),
        ("https://x.gov.br/arcgis/rest/services/A/B/MapServer/0/query?f=json", [("esri_rest", "https://x.gov.br/arcgis/rest/services/A/B/MapServer/0")]),
        ("https://x.gov.br/server/rest/services/A/FeatureServer", [("esri_rest", "https://x.gov.br/server/rest/services/A/FeatureServer")]),
        ("https://x.org.br/onrgisserver/rest/services/H/i/FeatureServer/0/query", [("esri_rest", "https://x.org.br/onrgisserver/rest/services/H/i/FeatureServer/0")]),
        ("https://x.gov.br/bdc/stac/v1", [("stac", "https://x.gov.br/bdc/stac/v1")]),
        ("https://ftp.ibge.gov.br/Censos/", []),
        ("https://x.gov.br/geonetwork/srv/eng/csw", []),
    ],
)
def test_tipos_da_url_do_registro(url, esperado):
    assert ep.tipos_da_url(url) == esperado


def test_semente_curada_e_valida_e_sem_repeticao():
    lista = ep.candidatos_da_semente()
    assert len(lista) >= 60
    chaves = [(c["tipo"], c["url"]) for c in lista]
    assert len(chaves) == len(set(chaves)), "semente com (tipo, url) repetido"
    for c in lista:
        assert c["tipo"] in ep.TIPOS and c["url"].startswith("https://") and c["orgao"] and c["nome"]
        assert c["origem"] in ("curadoria", "fila_keyless")
        assert c["licenca"]  # vocabulário B3, 'nao-declarada' quando o órgão não publica termo
        assert "?" not in c["url"] or c["tipo"] == "stac"
