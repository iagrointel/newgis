"""Adversário de linha L7 operação (parte 1) — item `L7-03-e-cabecalhos-csp-tls`
(laudo `laco/handoffs/T9/linha-L7-laudo-adversario-1.md`).

`app/auth/middleware.py` já documenta a decisão "Cache-Control com UMA origem só: a aplicação. O nginx
não acrescenta o dele nas rotas proxiadas" — mas essa decisão só foi aplicada ao Cache-Control. Na
instalação pública (`https://sistema.iagrointel.com`), o nginx TAMBÉM define (via `add_header`)
`Referrer-Policy`, `Permissions-Policy`, `Strict-Transport-Security`, `X-Content-Type-Options` e
`X-Frame-Options`, e o `add_header` do nginx ACRESCENTA em vez de substituir o cabeçalho que a aplicação
já mandou. Resultado medido (executando `tests/api/test_cabecalhos.py`, arquivo oficial do item, contra a
instalação pública): `Referrer-Policy` chega duplicado com o MESMO valor duas vezes, e `Permissions-Policy`
chega com dois valores DIFERENTES na mesma resposta (a lista longa da aplicação e uma lista curta do
nginx) — o oposto de "cabeçalhos completos e testados por rota" com uma fonte de verdade.

Este teste é mais restrito e não precisa de rede: sobe o app local e confere que, pelo menos do lado da
aplicação, cada cabeçalho de segurança nomeado no portão aparece EXATAMENTE UMA VEZ (`Message.headers` do
Starlette permite múltiplos valores pelo mesmo nome; `get_list` mostra quantos há) — o defeito real só
aparece quando o nginx real está na frente, mas a garantia "uma origem só" tem de valer mesmo assim como
contrato da aplicação, e a duplicação observada em produção prova que HOJE ninguém testa isso fim-a-fim.

xfail(strict=True): a asserção de rede real (contra `https://sistema.iagrointel.com`) é o teste que prova
o defeito; ela é pulada quando o domínio não resolve (mesma regra do arquivo oficial do item) — nesse caso
o xfail correspondente também é pulado (skip tem prioridade sobre xfail no pytest), o que é esperado."""

from __future__ import annotations

import socket
from urllib.parse import urlparse

import httpx
import pytest

BASE_URL = "https://sistema.iagrointel.com"


def _resolve(url: str) -> bool:
    host = urlparse(url).hostname or ""
    try:
        socket.gethostbyname(host)
        return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def http():
    if not _resolve(BASE_URL):
        pytest.skip(f"{BASE_URL} não resolve nesta máquina")
    with httpx.Client(base_url=BASE_URL, timeout=10, follow_redirects=False) as c:
        yield c


@pytest.mark.parametrize("cabecalho", ["referrer-policy", "permissions-policy", "strict-transport-security"])
@pytest.mark.xfail(
    strict=True,
    reason=(
        "o nginx da instalação pública usa add_header para Referrer-Policy/Permissions-Policy/HSTS (entre "
        "outros), que ACRESCENTA ao cabeçalho que a aplicação já mandou em vez de substituir — a decisão "
        "'Cache-Control com UMA origem só' (app/auth/middleware.py) só foi aplicada ao Cache-Control. "
        "Medido: Referrer-Policy chega duplicado com o MESMO valor, Permissions-Policy chega com DOIS "
        "valores DIFERENTES na mesma resposta. Item L7-03-e-cabecalhos-csp-tls."
    ),
)
def test_cabecalho_de_seguranca_aparece_uma_unica_vez(http, cabecalho):
    r = http.get("/")
    assert r.status_code == 200
    valores = r.headers.get_list(cabecalho)
    assert len(valores) == 1, (cabecalho, valores)
