"""Rotas do catálogo de conectores públicos (item L6-02-m-catalogo-endpoints-brasil). Portão literal: "≥ 60
endpoints com teste HTTP verde na data (script + JSON em tests/medidas); 10 adicionados pela tela em e2e; entrada
morta sai da lista e vai para 'fora do ar'". A tela é `tests/e2e/test_endpoints_publicos_tela.py`; o script é
`scripts/endpoints_publicos_testar.py`. Aqui, sem rede externa: duas entradas semeadas apontando para um servidor
local no IP público (uma responde Capabilities, outra HTML de erro com HTTP 200) provam a listagem viva × fora do
ar, o "um clique" (idempotente, ficha do catálogo), a recusa de entrada morta e o isolamento A→B. Com rede
(`lento`): o job `endpoints_publicos.retestar` inteiro, com a contagem de vivos gravada como medida."""

from __future__ import annotations

import http.server
import ipaddress
import json
import os
import subprocess
import threading

import psycopg2
import pytest

from app import db as banco
from app.conexao import endpoints_publicos as ep
from app.conexao import tarefas_endpoints
from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.conftest import PREFIXO_TESTE
from tests.api.test_rls import ids_por_slug

ITEM = "L6-02-m-catalogo-endpoints-brasil"
CAPABILITIES = b'<?xml version="1.0"?><WFS_Capabilities version="2.0.0"><ows:ServiceIdentification/></WFS_Capabilities>'
HTML = b"<!DOCTYPE html><html><body>manutencao</body></html>"


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
        vivo = self.path.startswith("/vivo/")
        corpo = CAPABILITIES if vivo else HTML
        self.send_response(200)
        self.send_header("Content-Type", "application/xml" if vivo else "text/html")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def servidor_local():
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


def _con(env):
    return psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)


@pytest.fixture(scope="module")
def entradas(env, servidor_local):
    """duas entradas do catálogo, testadas pelo MESMO `testar`/`registrar` do job: uma viva, uma fora do ar."""
    marca = f"{PREFIXO_TESTE}-{os.getpid()}"
    lista = [
        {"slug": f"{marca}-viva", "orgao": f"{marca} orgao", "nome": f"{marca} servico vivo (WFS)", "tipo": "wfs",
         "url": f"{servidor_local}/vivo/ows", "licenca": "CC-BY", "origem": "curadoria", "fonte_id": None},
        {"slug": f"{marca}-morta", "orgao": f"{marca} orgao", "nome": f"{marca} servico morto (WMS)", "tipo": "wms",
         "url": f"{servidor_local}/morto/ows", "licenca": "nao-declarada", "origem": "curadoria", "fonte_id": None},
    ]
    con = _con(env)
    try:
        with con.cursor() as cur:
            cur.execute("SET search_path = plat, public")
            cur.execute("SELECT plat.endpoint_publico_semear(%s::jsonb) AS n", (json.dumps(lista),))
            assert cur.fetchone()["n"] == 2
            cur.execute(
                "SELECT id, tipo, url FROM plat.endpoint_publico WHERE orgao = %s ORDER BY id", (f"{marca} orgao",)
            )
            linhas = cur.fetchall()
            for e in linhas:
                ep.registrar(cur, e["id"], ep.testar(e["url"], e["tipo"]))
        con.commit()
        ids = {"viva": next(e["id"] for e in linhas if e["tipo"] == "wfs"),
               "morta": next(e["id"] for e in linhas if e["tipo"] == "wms"), "marca": marca}
        yield ids
    finally:
        # a tabela é só-leitura para plat_app (escrita só pelas funções SECURITY DEFINER): as duas entradas de
        # teste ficam marcadas pelo prefixo zt- e, quando o servidor local sumir, o reteste semanal as leva para
        # "fora do ar" como qualquer outra. As conexões criadas nos testes abaixo são apagadas por limpar_conexoes.
        con.close()


@pytest.fixture
def limpar_conexoes(sessao_a):
    criadas = []
    yield criadas
    for cid in criadas:
        sessao_a.delete(f"/api/conexoes/{cid}")


def test_lista_viva_e_fora_do_ar_sao_separadas(sessao_a, entradas):
    marca = entradas["marca"]
    r = sessao_a.get(f"/api/endpoints-publicos?q={marca}")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert [e["id"] for e in corpo["itens"]] == [entradas["viva"]]
    viva = corpo["itens"][0]
    assert viva["vivo"] is True and viva["motivo"] == "ok" and viva["http"] == 200 and viva["testado_em"]
    assert viva["licenca"] == "CC-BY" and viva["tipo"] == "wfs" and viva["primeiro_ok_em"]
    assert corpo["vivos"] >= 1 and corpo["fora_do_ar"] >= 1

    r2 = sessao_a.get(f"/api/endpoints-publicos?q={marca}&vivo=false")
    assert r2.status_code == 200
    mortas = r2.json()["itens"]
    assert [e["id"] for e in mortas] == [entradas["morta"]]
    assert mortas[0]["motivo"] == "html_no_lugar_do_servico" and mortas[0]["http"] == 200  # 200 com HTML = morta
    assert mortas[0]["falhas_seguidas"] >= 1

    r3 = sessao_a.get(f"/api/endpoints-publicos?q={marca}&tipo=wms")
    assert r3.status_code == 200 and r3.json()["itens"] == []  # a morta não aparece nem filtrando pelo seu tipo
    assert sessao_a.get("/api/endpoints-publicos?tipo=ftp").status_code == 422
    assert sessao_a.get(f"/api/endpoints-publicos/{entradas['morta']}").json()["vivo"] is False


def test_um_clique_cria_conexao_com_ficha_do_catalogo(sessao_a, entradas, limpar_conexoes):
    r = sessao_a.post(f"/api/endpoints-publicos/{entradas['viva']}/adicionar")
    assert r.status_code == 201, r.text
    c = r.json()
    limpar_conexoes.append(c["id"])
    assert c["criada"] is True and c["tipo"] == "wfs" and c["modo"] == "referenciada"
    assert c["url"].endswith("/vivo/ows") and c["nome"].startswith(entradas["marca"])
    ficha = c["config"]["procedencia"]
    assert ficha["licenca"] == "CC-BY" and ficha["confianca"] == "declarado" and ficha["responsavel"]
    assert ficha["comando_reexecucao"].endswith("?SERVICE=WFS&REQUEST=GetCapabilities")
    assert "testado por HTTP em" in ficha["metodo"] and ficha["frescor"].startswith("último teste HTTP")
    assert c["config"]["endpoint_publico_id"] == entradas["viva"]

    r2 = sessao_a.post(f"/api/endpoints-publicos/{entradas['viva']}/adicionar")
    assert r2.status_code == 201 and r2.json()["criada"] is False and r2.json()["id"] == c["id"]
    assert sessao_a.get(f"/api/conexoes/{c['id']}").status_code == 200


def test_entrada_fora_do_ar_nao_vira_conexao(sessao_a, entradas):
    antes = sessao_a.get("/api/conexoes").json()["total"]
    r = sessao_a.post(f"/api/endpoints-publicos/{entradas['morta']}/adicionar")
    assert r.status_code == 409 and r.json()["erro"] == "endpoint_fora_do_ar", r.text
    assert r.json()["detalhe"]["motivo"] == "html_no_lugar_do_servico"
    assert sessao_a.get("/api/conexoes").json()["total"] == antes
    assert sessao_a.post("/api/endpoints-publicos/999999999/adicionar").status_code == 404


def test_catalogo_e_global_mas_a_conexao_e_do_inquilino(sessao_a, sessao_b, entradas, limpar_conexoes):
    assert sessao_b.get(f"/api/endpoints-publicos/{entradas['viva']}").status_code == 200  # B vê o catálogo
    r = sessao_a.post(f"/api/endpoints-publicos/{entradas['viva']}/adicionar")
    assert r.status_code == 201
    cid = r.json()["id"]
    limpar_conexoes.append(cid)
    assert sessao_b.get(f"/api/conexoes/{cid}").status_code == 404  # a conexão criada por A não existe para B


def test_visualizador_ve_catalogo_mas_nao_adiciona(usuarios_a, entradas):
    sessao_v, _, _ = usuarios_a.sessao("visualizador")
    assert sessao_v.get(f"/api/endpoints-publicos?q={entradas['marca']}").status_code == 200
    assert sessao_v.post(f"/api/endpoints-publicos/{entradas['viva']}/adicionar").status_code == 403


class _CtxMinimo:
    """o que `tarefas_endpoints.retestar` usa do ContextoJob: db() no inquilino técnico, verificar(), progresso()."""

    def __init__(self, tenant_id: int):
        self._ctx = banco.Contexto(tenant_id, 0, "worker")

    def db(self):
        return banco.db(self._ctx)

    def verificar(self) -> None:
        pass

    def progresso(self, pct: int, mensagem: str = "") -> None:
        pass


@pytest.mark.lento
def test_job_retestar_semeia_e_deixa_pelo_menos_60_vivos(env, medida):
    """rede real: semente + registro do acervo testados pelo job inteiro; grava a contagem como medida."""
    con = _con(env)
    try:
        ids = ids_por_slug(con)
    finally:
        con.close()
    resultado = tarefas_endpoints.retestar(_CtxMinimo(ids["demo"]), limite=1000, semear=True)
    m = medida(ITEM)
    for chave in ("semeados", "testados", "vivos", "fora_do_ar"):
        m(f"job_retestar_{chave}", resultado[chave], "endpoints",
          "tests/api/test_endpoints_publicos.py::test_job_retestar (tarefas_endpoints.retestar, rede real)")
    assert resultado["testados"] >= 60
    assert resultado["vivos"] >= 60, resultado
