"""Rotas de descoberta por catálogo CSW (item L6-06-descoberta-csw): `POST /api/csw/buscar` e
`POST /api/csw/conexoes`. Portão literal: "busca no CSW da INDE devolve registros e cria 2 conexões válidas;
teste com resposta gravada; ficha preenchida do ISO". Refutação: "registro ISO sem OnlineResource: a tela diz
'sem serviço ligado', não cria conexão vazia".

Sem rede: um servidor HTTP local que responde com as gravações de `tests/dados/csw/` (feitas contra a INDE em
07/09/2026), ligado ao IP PÚBLICO desta máquina — nunca loopback, porque `buscar_seguro` recusa loopback por
desenho (SSRF) e o teste tem de atravessar o MESMO caminho de rede da produção. Com rede (`lento`): a INDE de
verdade, com medida gravada."""

from __future__ import annotations

import http.server
import ipaddress
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

ITEM = "L6-06-descoberta-csw"
DADOS = Path(__file__).resolve().parents[1] / "dados" / "csw"
URL_INDE = "https://metadados.inde.gov.br/geonetwork/srv/eng/csw"
ID_WMS_WFS = "fbdd4fe6-956f-4d20-bbf9-068365edabb8"
ID_SEM_ENDERECO = "f8126f1f-1883-4ddb-90ed-1d9a519f8913"
FIXTURAS = {
    ID_WMS_WFS: DADOS / "inde_getrecordbyid_wms_wfs.xml",
    ID_SEM_ENDERECO: DADOS / "inde_getrecordbyid_wms_sem_endereco.xml",
}
VAZIO = b'<?xml version="1.0" encoding="UTF-8"?><csw:GetRecordByIdResponse xmlns:csw="http://www.opengis.net/cat/csw/2.0.2"/>'


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


class _Catalogo(http.server.BaseHTTPRequestHandler):
    """CSW gravado: GetRecords -> a busca 'tuberculose' (2 de 52); GetRecordById -> por id; o resto -> vazio."""

    pedidos: list[str] = []

    def do_GET(self):  # noqa: N802 — nome exigido pelo BaseHTTPRequestHandler
        q = {k: v[0] for k, v in parse_qs(urlsplit(self.path).query).items()}
        _Catalogo.pedidos.append(self.path)
        pedido = "" if self.path.startswith("/manutencao") else q.get("request", "")
        if pedido == "GetRecords":
            corpo = (DADOS / "inde_getrecords_tuberculose.xml").read_bytes()
        elif pedido == "GetRecordById":
            arq = FIXTURAS.get(q.get("id", ""))
            corpo = arq.read_bytes() if arq else VAZIO
        else:
            corpo = b"<html><body>catalogo de teste</body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "application/xml; charset=UTF-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def catalogo_gravado():
    ip = _ip_publico_desta_maquina()
    if ip is None:
        pytest.skip("máquina sem IP público roteável (sem interface global IPv4)")
    srv = http.server.HTTPServer((ip, 0), _Catalogo)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://{ip}:{srv.server_address[1]}/geonetwork/srv/eng/csw"
    finally:
        srv.shutdown()
        t.join(timeout=2)


@pytest.fixture
def limpar_conexoes(sessao_a):
    criadas = []
    yield criadas
    for cid in criadas:
        sessao_a.delete(f"/api/conexoes/{cid}")


def _apagar_por_url(sessao, url_base: str) -> None:
    """as conexões criadas por CSW têm nome vindo do registro (não o prefixo de teste): apaga pela URL do serviço."""
    for c in sessao.get("/api/conexoes").json()["itens"]:
        if c["url"].startswith(url_base):
            sessao.delete(f"/api/conexoes/{c['id']}")


# --------------------------------------------------------------------------- busca


def test_buscar_devolve_registros_com_servicos(sessao_a, catalogo_gravado):
    r = sessao_a.post("/api/csw/buscar", json={"url": catalogo_gravado, "texto": "tuberculose", "maximo": 2})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["total"] == 52 and corpo["devolvidos"] == 2 and corpo["proximo"] == 3 and corpo["inicio"] == 1
    assert "request=GetRecords" in corpo["url_pedida"] and "tuberculose" in corpo["url_pedida"]
    assert len(corpo["registros"]) == 2
    reg = corpo["registros"][0]
    assert reg["identificador"] and reg["titulo"] and reg["bbox"] and len(reg["bbox"]) == 4
    assert {s["tipo"] for s in reg["servicos"]} == {"wms", "wfs"} and reg["sem_servico"] is False
    assert all("?" not in s["url"] for s in reg["servicos"])


def test_buscar_por_bbox_monta_cql_e_recusa_bbox_invalida(sessao_a, catalogo_gravado):
    _Catalogo.pedidos.clear()
    r = sessao_a.post("/api/csw/buscar", json={"url": catalogo_gravado, "bbox": [-48, -25, -46, -23]})
    assert r.status_code == 200, r.text
    assert any("BBOX%28ows%3ABoundingBox%2C-48%2C-25%2C-46%2C-23%29" in p for p in _Catalogo.pedidos)
    r2 = sessao_a.post("/api/csw/buscar", json={"url": catalogo_gravado, "bbox": [10, 5, -10, 8]})
    assert r2.status_code == 422 and r2.json()["erro"] == "bbox_invalida"
    r3 = sessao_a.post("/api/csw/buscar", json={"url": catalogo_gravado})
    assert r3.status_code == 422 and r3.json()["erro"] == "busca_vazia"


@pytest.mark.parametrize("url", ["http://127.0.0.1:8150/csw", "http://169.254.169.254/latest/", "file:///etc/passwd"])
def test_buscar_e_criar_recusam_catalogo_inseguro_sem_tocar_a_rede(sessao_a, url):
    r = sessao_a.post("/api/csw/buscar", json={"url": url, "texto": "x"})
    assert r.status_code == 422 and r.json()["erro"] == "url_insegura", r.text
    r2 = sessao_a.post("/api/csw/conexoes", json={"url": url, "identificador": ID_WMS_WFS})
    assert r2.status_code == 422 and r2.json()["erro"] == "url_insegura", r2.text


def test_catalogo_que_responde_html_e_erro_nomeado_502(sessao_a, catalogo_gravado):
    """página de manutenção no lugar do CSW: erro nomeado (502 csw_resposta_invalida), nunca 500 nem conexão."""
    url_manutencao = catalogo_gravado.replace("/geonetwork/srv/eng/csw", "/manutencao")
    r = sessao_a.post("/api/csw/buscar", json={"url": url_manutencao, "texto": "x"})
    assert r.status_code == 502 and r.json()["erro"] == "csw_resposta_invalida", r.text
    assert r.json()["detalhe"]["motivo"] == "resposta_nao_e_csw"
    r2 = sessao_a.post("/api/csw/conexoes", json={"url": catalogo_gravado, "identificador": "nao-existe"})
    assert r2.status_code == 404 and r2.json()["erro"] == "registro_inexistente", r2.text


# --------------------------------------------------------------------------- criação em um clique


def test_um_clique_cria_2_conexoes_validas_com_ficha_do_iso(sessao_a, catalogo_gravado):
    base_ibge = "https://geoservicos.ibge.gov.br/geoserver/ODS/ows"
    _apagar_por_url(sessao_a, base_ibge)
    antes = sessao_a.get("/api/conexoes").json()["total"]
    try:
        r = sessao_a.post("/api/csw/conexoes", json={"url": catalogo_gravado, "identificador": ID_WMS_WFS})
        assert r.status_code == 201, r.text
        corpo = r.json()
        assert corpo["registro"]["identificador"] == ID_WMS_WFS
        conexoes = corpo["conexoes"]
        assert len(conexoes) == 2 and {c["tipo"] for c in conexoes} == {"wms", "wfs"}
        assert all(c["criada"] is True and c["modo"] == "referenciada" for c in conexoes)
        assert all(c["saude"] == "nunca_testada" for c in conexoes)
        assert all(c["url"] == base_ibge for c in conexoes)
        assert all("tem_credencial" in c and c["tem_credencial"] is False for c in conexoes)
        assert sessao_a.get("/api/conexoes").json()["total"] == antes + 2

        # ficha preenchida do ISO, visível na conexão (GET /api/conexoes/{id})
        for c in conexoes:
            visto = sessao_a.get(f"/api/conexoes/{c['id']}").json()
            ficha = visto["config"]["procedencia"]
            assert visto["config"]["csw"] == {"url": catalogo_gravado, "identificador": ID_WMS_WFS}
            assert visto["config"]["camada"] and ficha["url"] == base_ibge
            assert ficha["fonte"] and "Geografia" in ficha["fonte"]
            assert ficha["titulo"] and "tuberculose" in ficha["titulo"].lower()
            assert ficha["sha256"] and ficha["comando_reexecucao"].startswith("GET http")
            assert ficha["licenca"] is None and any("não declara licença" in a for a in ficha["limites"])
            assert ficha["catalogo"]["identificador"] == ID_WMS_WFS
            assert "ISO 19139" in ficha["metodo"]
        wms = next(c for c in conexoes if c["tipo"] == "wms")
        assert wms["nome"].endswith("(WMS)")

        # segundo clique: idempotente — reaproveita, não duplica
        r2 = sessao_a.post("/api/csw/conexoes", json={"url": catalogo_gravado, "identificador": ID_WMS_WFS})
        assert r2.status_code == 201, r2.text
        assert all(c["criada"] is False for c in r2.json()["conexoes"])
        assert {c["id"] for c in r2.json()["conexoes"]} == {c["id"] for c in conexoes}
        assert sessao_a.get("/api/conexoes").json()["total"] == antes + 2

        # filtro de tipos: só WFS
        _apagar_por_url(sessao_a, base_ibge)
        r3 = sessao_a.post(
            "/api/csw/conexoes", json={"url": catalogo_gravado, "identificador": ID_WMS_WFS, "tipos": ["wfs"]}
        )
        assert r3.status_code == 201 and [c["tipo"] for c in r3.json()["conexoes"]] == ["wfs"]
    finally:
        _apagar_por_url(sessao_a, base_ibge)


def test_registro_sem_servico_ligado_nao_cria_conexao(sessao_a, catalogo_gravado):
    """Refutação do item: ISO com OnlineResource WMS mas sem endereço (caso real da INDE) -> 422 'sem serviço
    ligado' e a contagem de conexões NÃO muda."""
    antes = sessao_a.get("/api/conexoes").json()["total"]
    r = sessao_a.post("/api/csw/conexoes", json={"url": catalogo_gravado, "identificador": ID_SEM_ENDERECO})
    assert r.status_code == 422, r.text
    corpo = r.json()
    assert corpo["erro"] == "sem_servico_ligado" and "sem serviço ligado" in corpo["mensagem"]
    assert any("sem endereço" in a for a in corpo["detalhe"]["avisos"])
    assert sessao_a.get("/api/conexoes").json()["total"] == antes


def test_conexoes_de_a_nao_aparecem_para_b(sessao_a, sessao_b, catalogo_gravado):
    base_ibge = "https://geoservicos.ibge.gov.br/geoserver/ODS/ows"
    _apagar_por_url(sessao_a, base_ibge)
    try:
        r = sessao_a.post("/api/csw/conexoes", json={"url": catalogo_gravado, "identificador": ID_WMS_WFS})
        assert r.status_code == 201, r.text
        ids_a = {c["id"] for c in r.json()["conexoes"]}
        vistos_b = {c["id"] for c in sessao_b.get("/api/conexoes").json()["itens"]}
        assert not (ids_a & vistos_b)
        for cid in ids_a:
            assert sessao_b.get(f"/api/conexoes/{cid}").status_code == 404
    finally:
        _apagar_por_url(sessao_a, base_ibge)


def test_visualizador_nao_busca_nem_cria(usuarios_a, catalogo_gravado):
    """perfil visualizador não tem conteudo.criar: as duas rotas devolvem 403 antes de tocar a rede."""
    sessao_v, _, _ = usuarios_a.sessao("visualizador")
    _Catalogo.pedidos.clear()
    r = sessao_v.post("/api/csw/buscar", json={"url": catalogo_gravado, "texto": "x"})
    assert r.status_code == 403, r.text
    r2 = sessao_v.post("/api/csw/conexoes", json={"url": catalogo_gravado, "identificador": ID_WMS_WFS})
    assert r2.status_code == 403, r2.text
    assert _Catalogo.pedidos == []


# --------------------------------------------------------------------------- rede real (INDE), marcado


@pytest.mark.lento
def test_inde_real_busca_e_cria_2_conexoes(sessao_a, medida):
    """A cláusula do portão com o catálogo de verdade. Nunca reprova por indisponibilidade alheia: quando a INDE
    não responde, grava a medida como 'indisponível' e pula."""
    m = medida(ITEM)
    t0 = time.monotonic()
    r = sessao_a.post("/api/csw/buscar", json={"url": URL_INDE, "texto": "tuberculose", "maximo": 5})
    dt = int((time.monotonic() - t0) * 1000)
    if r.status_code == 502:
        m("inde_getrecords_status", r.json()["erro"], "erro", f"POST /api/csw/buscar url={URL_INDE} texto=tuberculose")
        pytest.skip(f"INDE indisponível agora: {r.json()}")
    assert r.status_code == 200, r.text
    corpo = r.json()
    m("inde_getrecords_total_tuberculose", corpo["total"], "registros",
      f"POST /api/csw/buscar texto=tuberculose ({URL_INDE})")
    m("inde_getrecords_ms", dt, "ms", "tempo de POST /api/csw/buscar maximo=5, ida e volta pela INDE")
    assert corpo["total"] >= 1 and corpo["registros"]
    com_servico = [x for x in corpo["registros"] if not x["sem_servico"]]
    assert com_servico, "a INDE devolveu registros de tuberculose sem nenhum serviço ligado"
    reg = com_servico[0]
    base = reg["servicos"][0]["url"]
    _apagar_por_url(sessao_a, base)
    try:
        t1 = time.monotonic()
        r2 = sessao_a.post("/api/csw/conexoes", json={"url": URL_INDE, "identificador": reg["identificador"]})
        assert r2.status_code == 201, r2.text
        conexoes = r2.json()["conexoes"]
        m("inde_conexoes_criadas_por_registro", len(conexoes), "conexões",
          f"POST /api/csw/conexoes id={reg['identificador']}")
        m("inde_getrecordbyid_e_criacao_ms", int((time.monotonic() - t1) * 1000), "ms", "GetRecordById + INSERT")
        assert len(conexoes) >= 2 and {c["tipo"] for c in conexoes} >= {"wms", "wfs"}
        # válidas de verdade: o teste de saúde do serviço declarado responde 2xx/3xx
        ok = 0
        for c in conexoes[:2]:
            rs = sessao_a.post(f"/api/conexoes/{c['id']}/testar")
            ok += int(rs.status_code == 200 and rs.json()["ok"])
        m("inde_conexoes_saude_ok_de_2", ok, "conexões", "POST /api/conexoes/{id}/testar nas 2 conexões criadas")
        assert ok == 2
    finally:
        _apagar_por_url(sessao_a, base)
