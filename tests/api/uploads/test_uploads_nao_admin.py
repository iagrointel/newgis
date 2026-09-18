"""Upload retomável COMPLETO com token de quem não é admin do inquilino (item L0-04-a-upload-arquivo).

Razão de existir: o bloqueio do item era exatamente este — o adversário independente do turno T3
(`handoffs/T3/L0-04-a-ADVERSARIO.md`) mostrou que nenhum usuário fora do perfil admin conseguia usar o
upload, porque a tela pedia um token com escopo `admin:inquilino`, e esse escopo só é emitido para admin.
O conserto abriu o escopo `conteudo:criar`. `tests/api/uploads/test_uploads.py::test_editor_comum_sobe_
arquivo_pelo_proprio_token` prova a emissão do token e um arquivo de 1 KiB (uma parte só). Falta o que o
portão pede de verdade e que só existia com token de ADMIN: o fluxo RETOMÁVEL inteiro — várias partes,
parte fora de ordem, parte reenviada, sha256 do objeto igual ao local — com o token do EDITOR.

Par negativo na mesma rodada (regra: recusa sem par positivo não prova nada): o mesmo fluxo com um perfil
sem `conteudo.criar` não sai do lugar, e o editor continua sem alcançar `admin:inquilino`.
"""

from __future__ import annotations

import hashlib

import pytest

from tests.api.conftest import PREFIXO_TESTE
from tests.api.uploads.test_uploads import Uploader, _csv_de

ITEM = "L0-04-a-upload-arquivo"
ESCOPO = "conteudo:criar"


def _uploader_com_escopo(cliente, escopo: str = ESCOPO) -> Uploader:
    r = cliente.post("/api/tokens", json={"nome": f"{PREFIXO_TESTE}-nao-admin", "escopos": [escopo]})
    assert r.status_code == 201, r.text
    up = Uploader(cliente)
    up._tok = r.json()["token"]
    up._tok_id = r.json()["id"]
    return up


@pytest.fixture
def editor_upload(usuarios_a):
    """Editor comum (privilégio `conteudo.criar`, nunca `admin:inquilino`) com token de upload próprio."""
    cliente, usuario, _ = usuarios_a.sessao("editor")
    up = _uploader_com_escopo(cliente)
    yield up, cliente, usuario
    up.liberar_token()
    for iid in up.arquivos:
        try:
            cliente.delete(f"/api/itens/{iid}")
        except Exception:  # noqa: BLE001 — limpeza best-effort
            pass
    for upid in up.uploads:
        try:
            up.cliente().delete(f"/api/uploads/{upid}", headers=up.cabecalho())
        except Exception:  # noqa: BLE001
            pass


def test_editor_completa_o_retomavel_inteiro_com_o_proprio_token(editor_upload, medida):
    """Cláusula do portão com o token que o adversário provou não existir: várias partes, a última antes da
    primeira (fora de ordem), a parte 1 reenviada (retomada) e sha256 do objeto igual ao sha256 local."""
    up, cliente, _ = editor_upload
    tamanho = 40 * 1024 * 1024  # 40 MiB -> 3 partes de 16 MiB
    dados = _csv_de(tamanho)
    sha_local = hashlib.sha256(dados).hexdigest()

    corpo = up.iniciar(f"{PREFIXO_TESTE}-editor-retomavel.csv", dados, "csv").json()
    upload_id, parte_bytes = corpo["id"], corpo["parte_bytes"]
    assert corpo["partes"] == 3, corpo

    c = up.cliente()
    pedacos = [dados[i : i + parte_bytes] for i in range(0, tamanho, parte_bytes)]
    # fora de ordem: 3, 1, 2 — e depois a 1 outra vez (a retomada que dá nome ao mecanismo)
    for n in (3, 1, 2):
        r = c.put(f"/api/uploads/{upload_id}/partes/{n}", content=pedacos[n - 1], headers=up.cabecalho())
        assert r.status_code == 200, r.text
    assert r.json()["recebidas"] == 3 and r.json()["faltam"] == []
    r_reenvio = c.put(f"/api/uploads/{upload_id}/partes/1", content=pedacos[0], headers=up.cabecalho())
    assert r_reenvio.status_code == 200, r_reenvio.text
    assert r_reenvio.json()["recebidas"] == 3 and r_reenvio.json()["faltam"] == []

    final = up.concluir(upload_id, sha256=sha_local).json()
    assert final["sha256"] == sha_local, "o arquivo montado pelo servidor não é o que o editor enviou"
    assert final["bytes"] == tamanho

    # o item nasceu para o editor e ele o enxerga pela própria sessão (o upload serviu para alguma coisa)
    ficha = cliente.get(f"/api/itens/{final['arquivo_id']}")
    assert ficha.status_code == 200, ficha.text

    medida(ITEM)(
        "partes_retomavel_token_nao_admin",
        {"bytes": tamanho, "partes": corpo["partes"], "escopo": ESCOPO, "perfil": "editor"},
        "partes (fora de ordem + 1 reenviada)",
        "pytest tests/api/uploads/test_uploads_nao_admin.py"
        "::test_editor_completa_o_retomavel_inteiro_com_o_proprio_token -q",
    )


def test_editor_continua_sem_alcancar_admin_inquilino(editor_upload):
    """O conserto abriu `conteudo:criar`, não o teto: o editor não emite token de administração."""
    _, cliente, _ = editor_upload
    r = cliente.post("/api/tokens", json={"nome": f"{PREFIXO_TESTE}-editor-adm", "escopos": ["admin:inquilino"]})
    assert r.status_code == 422 and r.json()["erro"] == "escopo_fora_do_teto", r.text


def test_perfil_sem_conteudo_criar_nao_inicia_upload_nenhum(usuarios_a):
    """Par negativo: quem não pode criar conteúdo não consegue nem o token, nem o início do upload com um
    token de leitura — o portão abriu para o editor, não para todo mundo."""
    cliente, _, _ = usuarios_a.sessao("visualizador")
    r = cliente.post("/api/tokens", json={"nome": f"{PREFIXO_TESTE}-vis-retomavel", "escopos": [ESCOPO]})
    assert r.status_code == 422 and r.json()["erro"] == "escopo_fora_do_teto", r.text

    up = _uploader_com_escopo(cliente, "catalogo:ler")
    try:
        dados = _csv_de(1024)
        up.iniciar(f"{PREFIXO_TESTE}-vis.csv", dados, "csv", esperado=403)
    finally:
        up.liberar_token()


def test_parte_do_editor_nao_e_alcancavel_por_outro_usuario(editor_upload, usuarios_a):
    """Isolamento entre usuários do MESMO inquilino dentro do fluxo não-admin, com par positivo: o dono do
    upload fecha o mesmo upload que o estranho não conseguiu tocar."""
    up, _, _ = editor_upload
    dados = _csv_de(1024)
    upload_id = up.iniciar(f"{PREFIXO_TESTE}-editor-isolado.csv", dados, "csv").json()["id"]

    outro_cliente, _, _ = usuarios_a.sessao("editor")
    up_outro = _uploader_com_escopo(outro_cliente)
    try:
        r = up_outro.cliente().put(
            f"/api/uploads/{upload_id}/partes/1", content=dados, headers=up_outro.cabecalho()
        )
        assert r.status_code == 404, r.text
    finally:
        up_outro.liberar_token()

    for r_parte in up.enviar_partes(upload_id, dados, 16 * 1024 * 1024):
        assert r_parte.status_code == 200, r_parte.text
    assert up.concluir(upload_id, sha256=hashlib.sha256(dados).hexdigest()).status_code == 202
