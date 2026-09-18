"""Adversário de linha L7 operação (parte 1) — hipótese transversal nº 2 do laudo
(`laco/handoffs/T9/linha-L7-laudo-adversario-1.md`): `app/consulta/rotas_query.py::_autenticar` tem hoje a
assinatura `(request, item_id)` — só sessão OU token, escopo fixo `"camada:ler"` — mas
`app/consulta/rotas_edicao_esri.py` (1 chamada) e `app/consulta/rotas_sync_esri.py` +
`app/versionamento/rotas_esri.py` (16 chamadas) importam a MESMA função e chamam
`_autenticar(request, item_id, escopo)` com 3 argumentos.

Isso derruba, ao mesmo tempo, a cláusula "tokens com escopo" de `L7-03-seguranca` (o escopo
`camada:editar` nunca é conferido porque a chamada crasha antes de chegar em `esc.exigir_escopo`) e faz
`test_conjunto_de_seguranca_em_toda_rota_do_openapi` (item `L7-03-e`) falhar em ~19 rotas porque a
resposta nunca termina de forma controlada.

Reproduzido também fora do processo de teste, direto na trilha `uniao` (porta 8192, sem tocar schema
`plat`):

    curl -s -o /dev/null -w '%{http_code}\\n' \\
      'http://127.0.0.1:8192/rest/services/1/FeatureServer/1/queryAttachments?attachmentIds=1'
    # 500

xfail(strict=True): quando alguém uniformizar a assinatura de `_autenticar` (aceitar e usar o 3º
argumento, ou remover o 3º argumento dos chamadores), a rota volta a responder 4xx/2xx em vez de 500 e
este teste passa "de verdade" — sinal para apagar o xfail."""

from __future__ import annotations

import inspect

import pytest

from app.consulta import rotas_query
from tests.api.conftest import novo_cliente


@pytest.fixture(scope="module")
def local():
    return novo_cliente()


# 18/09/2026: a marca xfail(strict=True) saiu porque o teste PASSA — rodado isolado na trilha `uniao`.
# A assinatura hoje é `_autenticar(request, item_id, escopo=ESCOPO)` em app/consulta/rotas_query.py:39
# — os três argumentos que rotas_edicao_esri.py e rotas_sync_esri.py já passavam. Some com isso a
# causa dos 500 de queryAttachments e de applyEdits que estes três testes descreviam.
# O texto que vem abaixo (docstring/nome) descreve o achado ORIGINAL, não o estado de hoje.
def test_assinatura_de_autenticar_bate_com_quem_chama_com_escopo():
    """`rotas_query._autenticar` tem de aceitar o 3º parâmetro (escopo) que
    `rotas_edicao_esri`/`rotas_sync_esri` já passam — hoje não aceita."""
    parametros = inspect.signature(rotas_query._autenticar).parameters
    assert len(parametros) >= 3, (
        "app/consulta/rotas_query.py::_autenticar só aceita "
        f"{list(parametros)} (2 argumentos), mas app/consulta/rotas_edicao_esri.py e "
        "app/consulta/rotas_sync_esri.py chamam _autenticar(request, item_id, escopo) com 3 — toda rota "
        "de escrita/anexo/replicação do protocolo Esri crasha com TypeError antes de conferir o escopo."
    )


# 18/09/2026: a marca xfail(strict=True) saiu porque o teste PASSA — rodado isolado na trilha `uniao`.
# A assinatura hoje é `_autenticar(request, item_id, escopo=ESCOPO)` em app/consulta/rotas_query.py:39
# — os três argumentos que rotas_edicao_esri.py e rotas_sync_esri.py já passavam. Some com isso a
# causa dos 500 de queryAttachments e de applyEdits que estes três testes descreviam.
# O texto que vem abaixo (docstring/nome) descreve o achado ORIGINAL, não o estado de hoje.
def test_query_attachments_nunca_e_500(local):
    r = local.get("/rest/services/1/FeatureServer/1/queryAttachments?attachmentIds=1")
    assert r.status_code != 500, (r.status_code, r.text[:300])


# 18/09/2026: a marca xfail(strict=True) saiu porque o teste PASSA — rodado isolado na trilha `uniao`.
# A assinatura hoje é `_autenticar(request, item_id, escopo=ESCOPO)` em app/consulta/rotas_query.py:39
# — os três argumentos que rotas_edicao_esri.py e rotas_sync_esri.py já passavam. Some com isso a
# causa dos 500 de queryAttachments e de applyEdits que estes três testes descreviam.
# O texto que vem abaixo (docstring/nome) descreve o achado ORIGINAL, não o estado de hoje.
def test_apply_edits_nunca_e_500(local):
    r = local.post("/rest/services/1/FeatureServer/1/applyEdits", data={"f": "json"})
    assert r.status_code != 500, (r.status_code, r.text[:300])
