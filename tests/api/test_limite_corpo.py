"""Limite de corpo por requisição (item L0-12; app/limite_corpo.py; docs/CONTRATO_API.md seção "Limites").
Sem sessão: a rejeição acontece na camada ASGI, antes de qualquer autenticação — por isso os testes abaixo
não usam `sessao_a`/`sessao_b` (fixtures de tests/api/conftest.py), só `novo_cliente()`."""

import json

import pytest

from app import limites
from tests.api.conftest import novo_cliente

MAXIMO = limites.CORPO_MAX_PADRAO_BYTES


@pytest.fixture
def cliente():
    return novo_cliente()


def _confere_corpo_413(resposta):
    assert resposta.status_code == 413
    j = resposta.json()
    assert j["erro"] == "corpo_grande"
    assert isinstance(j["mensagem"], str) and j["mensagem"]
    assert "req_id" in j and len(j["req_id"]) == 16
    # o mesmo contrato de erro do resto da API (app/erros.py): erro, mensagem, req_id; detalhe é opcional
    assert set(j) <= {"erro", "mensagem", "detalhe", "req_id"}
    return j


def test_content_length_acima_do_limite_e_413_no_formato_padrao(cliente):
    """Caminho feliz do portão do item: corpo grande demais -> 413 no formato de erro {erro, mensagem, req_id}."""
    corpo = b"x" * (MAXIMO + 1)
    r = cliente.post("/api/itens", content=corpo, headers={"content-type": "application/octet-stream"})
    _confere_corpo_413(r)


def test_content_length_no_limite_exato_nao_e_413(cliente):
    """MAXIMO bytes é o teto, não o gatilho — só o que passa dele rejeita (evita off-by-one)."""
    corpo = b"x" * MAXIMO
    r = cliente.post("/api/itens", content=corpo, headers={"content-type": "application/octet-stream"})
    assert r.status_code != 413, r.text


def test_corpo_sem_content_length_tambem_e_limitado(cliente):
    """Refutação do item: um adversário que omita Content-Length (chunked) para escapar do teto declarado não
    consegue — os bytes são contados conforme chegam pelo ASGI `receive()` (app/limite_corpo.py), não só o
    cabeçalho. httpx envia um corpo vindo de gerador em Transfer-Encoding: chunked, sem Content-Length."""

    def gerador():
        enviado = 0
        pedaco = b"y" * (1024 * 1024)
        while enviado < MAXIMO + len(pedaco):
            yield pedaco
            enviado += len(pedaco)

    r = cliente.post("/api/itens", content=gerador())
    assert "content-length" not in {k.lower() for k in r.request.headers}
    _confere_corpo_413(r)


def test_corpo_pequeno_segue_o_fluxo_normal_da_rota(cliente):
    """O middleware não pode quebrar o caminho feliz: corpo pequeno chega à rota normalmente (401 sem sessão,
    não 413) — a contraprova de que o limite não vira uma negação de serviço disfarçada."""
    r = cliente.post("/api/itens", json={"tipo": "mapa", "titulo": "teste"})
    assert r.status_code == 401
    assert r.json()["erro"] == "nao_autenticado"


def test_limite_nao_se_aplica_fora_do_prefixo_de_api(cliente):
    """Página HTML (/entrar) e estático não levam limite de corpo — só /api,/svc,/ogc,/tiles (app/limite_corpo.py:
    PREFIXOS_COM_LIMITE). GET não tem corpo, então o teste é sobre o caminho de decisão (`limite_para`), não sobre
    enviar bytes de verdade a uma rota de página."""
    from app.limite_corpo import limite_para

    assert limite_para("/entrar") is None
    assert limite_para("/") is None
    assert limite_para("/api/itens") == MAXIMO


def test_content_length_mentiroso_tambem_e_pego_pela_contagem(cliente):
    """Content-Length pequeno declarado, corpo real grande enviado depois: a contagem por bytes recebidos (não
    só o cabeçalho) pega a mentira. httpx recalcula Content-Length a partir do `content=` de verdade, então aqui
    a única forma de simular é falsificar o cabeçalho manualmente via `headers=`."""
    corpo = b"z" * (MAXIMO + 1)
    r = cliente.post(
        "/api/itens",
        content=corpo,
        headers={"content-type": "application/octet-stream", "content-length": "10"},
    )
    _confere_corpo_413(r)


def test_docs_limites_md_cita_o_mesmo_numero_do_codigo():
    """"documento vivo == código": docs/LIMITES.md (gerado por docs/gerar_limites.py) tem de citar o valor
    exato de limites.CORPO_MAX_PADRAO_BYTES, não um número reescrito à mão que pode ficar velho."""
    md = (limites.__file__.rsplit("/", 2)[0] + "/docs/LIMITES.md")
    texto = open(md, encoding="utf-8").read()
    assert f"`{limites.CORPO_MAX_PADRAO_BYTES!r}`" in texto
    assert json.dumps(limites.CORPO_MAX_PADRAO_BYTES) in texto  # legível também fora de crase, para o cronista
