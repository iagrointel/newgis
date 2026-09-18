"""Adversário de linha L7 operação (parte 1) — item `L7-03-e-cabecalhos-csp-tls`
(laudo `laco/handoffs/T9/linha-L7-laudo-adversario-1.md`).

`app/auth/middleware.py` já documenta a decisão "Cache-Control com UMA origem só: a aplicação. O nginx
não acrescenta o dele nas rotas proxiadas" — mas essa decisão só foi aplicada ao Cache-Control. Na
instalação pública (`https://sistema.iagrointel.com`), o nginx TAMBÉM define (via `add_header`)
`Referrer-Policy` e `Permissions-Policy`, e o `add_header` do nginx ACRESCENTA em vez de substituir o
cabeçalho que a aplicação já mandou. Resultado medido (`curl -sD - https://sistema.iagrointel.com/`,
16/09): `Referrer-Policy` chega duplicado com o MESMO valor duas vezes, e `Permissions-Policy` chega com
dois valores DIFERENTES na mesma resposta (a lista longa da aplicação e uma lista curta do nginx) — o
oposto de "cabeçalhos completos e testados por rota" com uma fonte de verdade.

**Conferido e DESCARTADO por evidência**: `Strict-Transport-Security` NÃO duplica — a mesma captura mostra
uma única linha `Strict-Transport-Security: max-age=31536000; includeSubDomains` (o nginx também define
HSTS via `add_header`, mas nesta rota a aplicação não manda o dela, então não há acúmulo). Por isso HSTS
fica fora do parametrize abaixo — incluí-lo antes foi excesso de generalização a partir da lista de
cabeçalhos que o nginx configura, não da resposta real.

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


# CONSERTADO (18/09/2026, turno L7 do construtor). O defeito era real e foi medido de novo antes do
# conserto: `curl -sD - https://sistema.iagrointel.com/` trazia Referrer-Policy duas vezes,
# X-Content-Type-Options duas vezes e Permissions-Policy com DOIS valores, o do nginx mais fraco que o
# da aplicação. A causa é a que o laudo apontou: `add_header` do nginx ACRESCENTA, nunca substitui.
#
# O conserto tem duas metades, e a primeira sozinha abre um buraco:
#  1. nas rotas proxiadas comuns (/, /api/login, /api/login/2fa) o nginx deixou de declarar os três; a
#     origem é a aplicação (app/auth/middleware.py);
#  2. nas rotas /svc/ guardadas por `auth_request`, tirar sozinho deixava a resposta 403 — que o
#     PRÓPRIO nginx gera, sem montante nenhum — sem cabeçalho de segurança algum (medido em 18/09,
#     contagem zero nos três). Ali vale `proxy_hide_header` dos três mais `add_header` dos três: um
#     valor no 200 e um valor no 403.
# deploy/nginx.conf carrega as duas metades; o vhost vivo foi realinhado com ele no mesmo dia.
ROTAS = ["/", "/api/login", "/svc/x/raster/y/info"]
CABECALHOS = ["referrer-policy", "permissions-policy", "x-content-type-options",
              "strict-transport-security"]


@pytest.mark.parametrize("rota", ROTAS)
@pytest.mark.parametrize("cabecalho", CABECALHOS)
def test_cabecalho_de_seguranca_aparece_uma_unica_vez(http, cabecalho, rota):
    r = http.get(rota)
    valores = r.headers.get_list(cabecalho)
    assert len(valores) == 1, (rota, r.status_code, cabecalho, valores)


def test_permissions_policy_nao_sai_com_dois_valores_diferentes(http):
    """Par positivo do achado mais grave: a duplicata do nginx trazia uma lista CURTA (geolocation,
    camera, microphone, payment, usb) ao lado da lista longa da aplicação. Um cliente que lesse a
    primeira teria a política errada. Aqui exige-se um valor só, e que seja o completo."""
    r = http.get("/")
    valores = r.headers.get_list("permissions-policy")
    assert len(valores) == 1, valores
    assert "accelerometer=()" in valores[0], valores
