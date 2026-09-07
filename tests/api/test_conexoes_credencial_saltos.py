"""Rota `POST /api/conexoes/{id}/testar` (item L6-02-a-modelo-conexao-e-seguranca): o "Bearer da casa" não
sai da origem que o inquilino cadastrou.

A parte de mecânica está em `tests/unit/test_conexao_credencial_redirect.py` (função `buscar_seguro`) e em
`tests/unit/test_conexao_credencial_chamadores.py` (job `conexoes.saude_verificar`). Aqui a prova é pela ROTA
HTTP de verdade, com inquilino real no banco de teste da trilha e a credencial passando pelo caminho completo
(cifra no POST -> decifra no `testar` -> cabeçalho -> salto). A rede é substituída por `monkeypatch` de
`socket.getaddrinfo` e de `app.conexao.seguranca.cliente_pinado`: nenhum socket é aberto, e o resultado é o
mesmo em toda máquina.

A guarda `xfail(strict=True)` do fim afirma o comportamento VULNERÁVEL de propósito — se o conserto for
desfeito, ela passa (XPASS) e a suíte fica vermelha.
"""

import json
import socket

import httpx
import pytest

from app.conexao import seguranca as s
from tests.api.conftest import PREFIXO_TESTE

SEGREDO = "segredo-de-teste-nao-e-real-QRS456"
_MAPA = {"host-a.teste": "8.8.8.8", "host-b.teste": "9.9.9.9"}
URL_A = "http://host-a.teste/servico"


def _gai(host, port, *a, **kw):
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (_MAPA.get(host, host), port))]


class _Resposta:
    def __init__(self, status, headers):
        self.status_code, self.headers = status, headers

    def iter_bytes(self):
        return iter(())


class _Fluxo:
    def __init__(self, rotas, registro, url, headers):
        self._rotas, self._registro, self._url, self._headers = rotas, registro, url, headers

    def __enter__(self):
        self._registro.append((self._url, dict(self._headers)))
        destino = self._rotas.get(self._url)
        if destino is None:
            return _Resposta(200, httpx.Headers({}))
        return _Resposta(302, httpx.Headers({"location": destino}))

    def __exit__(self, *a):
        return False


class _Cliente:
    def __init__(self, rotas, registro):
        self._rotas, self._registro = rotas, registro

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def stream(self, metodo, url, headers=None):
        return _Fluxo(self._rotas, self._registro, url, headers or {})


@pytest.fixture
def rede_falsa(monkeypatch):
    """`f(rotas) -> registro` — troca DNS e cliente pinado; devolve a lista de (url, cabeçalhos) enviados."""

    def _f(rotas: dict[str, str]):
        registro: list[tuple[str, dict[str, str]]] = []
        monkeypatch.setattr(socket, "getaddrinfo", _gai)
        monkeypatch.setattr(s, "cliente_pinado", lambda validada, **_: _Cliente(rotas, registro))
        return registro

    return _f


@pytest.fixture
def conexao_credenciada(sessao_a):
    """Cria uma conexão de A com credencial e apaga no fim, mesmo se a asserção falhar."""
    criadas = []

    def _criar(sufixo, url=URL_A):
        r = sessao_a.post("/api/conexoes", json={
            "tipo": "http", "nome": f"{PREFIXO_TESTE}-conexao-salto-{sufixo}", "url": url, "credencial": SEGREDO,
        })
        assert r.status_code == 201, r.text
        criadas.append(r.json()["id"])
        return r.json()["id"]

    yield _criar
    for cid in criadas:
        sessao_a.delete(f"/api/conexoes/{cid}")


def test_testar_manda_a_credencial_so_para_a_origem_cadastrada(sessao_a, conexao_credenciada, rede_falsa):
    registro = rede_falsa({})
    cid = conexao_credenciada("origem")
    r = sessao_a.post(f"/api/conexoes/{cid}/testar")
    assert r.status_code == 200, r.text
    assert [u for u, _ in registro] == [URL_A]
    assert registro[0][1].get("Authorization") == f"Bearer {SEGREDO}"


def test_testar_nao_leva_a_credencial_no_redirecionamento_para_outro_host(
    sessao_a, conexao_credenciada, rede_falsa, caplog,
):
    registro = rede_falsa({URL_A: "http://host-b.teste/coleta"})
    cid = conexao_credenciada("outro-host")
    with caplog.at_level("DEBUG"):
        r = sessao_a.post(f"/api/conexoes/{cid}/testar")
    assert r.status_code == 200, r.text
    assert [u for u, _ in registro] == [URL_A, "http://host-b.teste/coleta"]
    assert "Authorization" not in registro[1][1]
    # varredura por texto: o segredo não aparece nos cabeçalhos do salto, na resposta da API nem no log
    assert SEGREDO not in repr(registro[1][1])
    assert SEGREDO not in r.text
    assert SEGREDO not in json.dumps(r.json())
    for reg in caplog.records:
        assert SEGREDO not in reg.getMessage()
        assert SEGREDO not in json.dumps(reg.__dict__, default=str)


def test_testar_nao_leva_a_credencial_quando_o_esquema_cai_para_http(sessao_a, conexao_credenciada, rede_falsa):
    """`https` -> `http` no mesmo host também é outra origem (divergência deliberada de requests/httpx)."""
    url_https = "https://host-a.teste/servico"
    registro = rede_falsa({url_https: "http://host-a.teste/servico"})
    cid = conexao_credenciada("esquema", url=url_https)
    r = sessao_a.post(f"/api/conexoes/{cid}/testar")
    assert r.status_code == 200, r.text
    assert "Authorization" not in registro[1][1]


def test_testar_mantem_a_credencial_em_redirecionamento_da_mesma_origem(sessao_a, conexao_credenciada, rede_falsa):
    registro = rede_falsa({URL_A: "/servico/v2"})
    cid = conexao_credenciada("mesma-origem")
    r = sessao_a.post(f"/api/conexoes/{cid}/testar")
    assert r.status_code == 200, r.text
    assert [u for u, _ in registro] == [URL_A, "http://host-a.teste/servico/v2"]
    assert registro[1][1].get("Authorization") == f"Bearer {SEGREDO}"


@pytest.mark.xfail(strict=True, reason="furo fechado: a rota testar nao vaza o Bearer da casa no salto")
def test_regressao_rota_testar_vaza_a_credencial_para_outro_host(sessao_a, conexao_credenciada, rede_falsa):
    registro = rede_falsa({URL_A: "http://host-b.teste/coleta"})
    cid = conexao_credenciada("regressao")
    sessao_a.post(f"/api/conexoes/{cid}/testar")
    assert registro[1][1].get("Authorization") == f"Bearer {SEGREDO}"
