"""Item L0-04-k: `GET /api/importacoes/formatos` responde a lista de formatos aceitos, e não mais o 404
`importacao_inexistente` de `GET /api/importacoes/{id}` (que estava declarada antes e engolia o caminho).
Chamada com sessão comum, sem privilégio nenhum: a rota exige apenas estar autenticado (`x-auth: S/T`,
`x-privilegio: proprio`, como as vizinhas), e devolve a tabela de formatos aceitos, igual para todos.
Sem autenticação nenhuma ela responde 401 — o que também prova que ela não é mais a rota `{id}` disfarçada."""

from app.ingestao.formatos import FORMATOS
from tests.api.conftest import novo_cliente


def test_formatos_responde_200_com_a_lista(sessao_a):
    r = sessao_a.get("/api/importacoes/formatos")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert isinstance(corpo, list) and corpo
    assert {f["tipo"] for f in corpo} == set(FORMATOS)
    for f in corpo:
        assert f["extensoes"] and f["rotulo"]


def test_formatos_nao_cai_no_404_de_importacao_inexistente(sessao_a):
    """Encoberta, a rota respondia 404 `importacao_inexistente`: o segmento `formatos` era lido como o `{id}`
    da rota vizinha. Este é o erro exato que o item conserta."""
    r = sessao_a.get("/api/importacoes/formatos")
    assert r.status_code == 200, r.text
    assert "importacao_inexistente" not in r.text


def test_formatos_sem_autenticacao_e_401(sessao_a):
    """Só estar autenticado basta (nenhum privilégio); anônimo, não."""
    assert novo_cliente().get("/api/importacoes/formatos").status_code == 401
