"""Laudo adversário do grupo G5 (turno 3). O teste afirma o comportamento SEGURO e está
`xfail(strict=True)`: hoje FALHA (é o achado); quando alguém consertar vira XPASS e o strict derruba a
suíte, sinalizando "remova o xfail, a guarda agora é real".

ACHADO G5-1 (segurança real, item L6-02-a-modelo-conexao-e-seguranca): `app.conexao.seguranca.buscar_seguro`
reenvia o cabeçalho `Authorization` (a credencial decifrada da conexão, usada por
`POST /api/conexoes/{id}/testar` em `app/conexao/rotas.py` e pelo job `conexoes.saude_verificar` em
`app/conexao/tarefas.py`) em TODO salto de redirecionamento, inclusive para um HOST DE OUTRA ORIGEM
escolhido pelo servidor de destino. `requests`/`httpx` retiram `Authorization` ao mudar de host; aqui o
laço de redirect repassa `headers=cabecalhos or {}` incondicionalmente. Um host público configurado (ou um
open-redirect nele) que responda 302 para fora exfiltra o Bearer da casa.

Reproduzir (não precisa de rede nem de banco — só do import do módulo):
  cd /home/dev/plataforma/enterprise
  export PLAT_SECRET=$(python3 -c "import secrets;print(secrets.token_hex(32))")
  venv/bin/pytest /home/dev/plataforma/wt/adv5/tests/adversario/test_g5_adversario.py -q -o addopts=""
"""
import socket

import httpx
import pytest

from app.conexao import seguranca as s

# dois hostnames PÚBLICOS distintos -> dois IPs públicos distintos (ambos passam na validação de SSRF)
_MAPA = {"host-a.teste": "8.8.8.8", "host-b.teste": "9.9.9.9"}


def _gai(host, port, *a, **kw):
    ip = _MAPA.get(host)
    if ip is None:
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (host, port))]
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, port))]


class _RespFake:
    def __init__(self, status, headers):
        self.status_code = status
        self.headers = headers

    def iter_bytes(self):
        return iter(())


class _StreamFake:
    def __init__(self, registro, url, headers):
        self._registro, self._url, self._headers = registro, url, headers

    def __enter__(self):
        host = httpx.URL(self._url).host
        self._registro.append((host, self._headers.get("Authorization")))
        if host == "host-a.teste":
            return _RespFake(302, httpx.Headers({"location": "http://host-b.teste/"}))
        return _RespFake(200, httpx.Headers({}))

    def __exit__(self, *a):
        return False


class _ClienteFake:
    def __init__(self, registro):
        self._registro = registro

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def stream(self, metodo, url, headers=None):
        return _StreamFake(self._registro, url, headers or {})


@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G5-1: buscar_seguro reenvia Authorization em redirect para outro HOST; correto é "
    "retirar a credencial ao mudar de origem (esquema+host+porta), como fazem requests/httpx.",
)
def test_credencial_nao_vaza_em_redirect_cross_host(monkeypatch):
    registro: list[tuple[str, str | None]] = []
    monkeypatch.setattr(socket, "getaddrinfo", _gai)
    monkeypatch.setattr(s, "cliente_pinado", lambda validada, **kw: _ClienteFake(registro))

    s.buscar_seguro("http://host-a.teste/", cabecalhos={"Authorization": "Bearer CREDENCIAL-DA-CASA"})

    vazou = [h for h, a in registro if h == "host-b.teste" and a == "Bearer CREDENCIAL-DA-CASA"]
    assert not vazou, f"credencial vazou para outro host no redirect: {registro!r}"
