"""Adversário de linha L7 operação (parte 1) — item `L7-03-e-cabecalhos-csp-tls`
(laudo `laco/handoffs/T9/linha-L7-laudo-adversario-1.md`).

RFC 9116 exige que `/.well-known/security.txt` traga um campo `Contact` com valor utilizável
(`mailto:`/`https://`/`tel:`) — é o único campo obrigatório do documento. O `security.txt` servido por
esta aplicação tem o CAMPO (a linha `Contact: ` existe), mas com o VALOR vazio — o que é, na prática, a
mesma coisa que não ter contato nenhum para quem reporta uma vulnerabilidade.

xfail(strict=True): quando o campo `Contact` ganhar um valor de verdade, este teste passa."""

from __future__ import annotations

import pytest

from tests.api.conftest import novo_cliente


@pytest.fixture(scope="module")
def local():
    return novo_cliente()


@pytest.mark.xfail(
    strict=True,
    reason=(
        "/.well-known/security.txt tem o campo Contact presente mas VAZIO ('Contact: '), violando a RFC "
        "9116 (Contact é o único campo obrigatório e precisa de um valor mailto:/https:/tel:). Item "
        "L7-03-e-cabecalhos-csp-tls."
    ),
)
def test_security_txt_tem_contact_com_valor(local):
    r = local.get("/.well-known/security.txt")
    assert r.status_code == 200
    campos = dict(li.split(": ", 1) for li in r.text.splitlines() if ": " in li)
    assert campos.get("Contact", "").strip(), campos
