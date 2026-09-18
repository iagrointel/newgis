"""A varredura cruzada A→B de toda a API (`tests/api/test_cruzado.py` + `tests/api/cruzado_casos.py`) é
montada a partir de `docs/openapi.json` — um ARQUIVO COMITADO. Ela cobre 100 % do que esse arquivo lista, e
é assim que se declara a cobertura. Mas o que está em produção é o que a APLICAÇÃO serve, e os dois se
separam sozinhos: basta uma rota nova entrar sem que o arquivo seja regerado. A rota nasce fora da varredura
e ninguém é avisado, porque a conta de 100 % continua fechando contra o arquivo velho.

Medido em 18/09/2026, no achado do item L4-23: a aplicação servia 958 rotas e o arquivo listava 914 — 51
rotas servidas e invisíveis para a varredura cruzada, 22 delas de escrita (4 DELETE, 2 PATCH, 15 POST,
1 PUT), entre elas `DELETE /api/webhooks/{id}`, `DELETE /api/modelos3d/{id}`,
`DELETE /api/amc/presets/{id}` e `DELETE /api/camadas/{id}/feicoes/{globalid}/anexos/{anexo_id}`.

É a mesma armadilha que o item L0-02-tenant-auth já tinha registrado e que o teste de isolamento da rede já
evitava lendo o OpenAPI em processo. Este arquivo fecha a porta para o resto da API: a diferença entre o que
se serve e o que se varre passa a ser uma falha com os nomes das rotas, não um silêncio.

Ele NÃO afirma que as rotas fora da lista vazam — afirma que ninguém mediu. É gargalo de cobertura, e é
assim que tem de ser lido.
"""

import pytest

from tests.api.conftest import arquivo_openapi

LACUNA_ABERTA = pytest.mark.xfail(
    reason="18/09/2026: LACUNA MEDIDA, ainda aberta — 51 rotas servidas fora da varredura cruzada "
    "(22 de escrita, 29 de leitura) e 7 casos para rota que já não existe. Fechar exige regerar "
    "docs/openapi.json E escrever o caso de cada rota em tests/api/cruzado_casos.py, que é trabalho "
    "de outro item. `strict=True`: no dia em que fechar, o XPASS obriga a tirar esta marca.",
    strict=True,
)

METODOS_DE_ESCRITA = ("POST", "PUT", "PATCH", "DELETE")


def _rotas_servidas() -> set[tuple[str, str]]:
    """O que a aplicação serve agora, em processo — a verdade sobre a superfície exposta."""
    from app.main import app

    esquema = app.openapi()
    return {(metodo.upper(), caminho) for caminho, ops in esquema["paths"].items() for metodo in ops}


def _rotas_do_arquivo() -> set[tuple[str, str]]:
    """O que `docs/openapi.json` lista — a fonte de onde a varredura cruzada tira os casos."""
    spec = arquivo_openapi()
    return {(metodo.upper(), caminho) for caminho, ops in spec["paths"].items() for metodo in ops}


def _fora_da_varredura() -> list[tuple[str, str]]:
    return sorted(_rotas_servidas() - _rotas_do_arquivo())


@LACUNA_ABERTA
def test_nenhuma_rota_de_escrita_servida_fica_fora_da_varredura_cruzada(medida):
    """Rota de escrita que a aplicação serve e a varredura cruzada não conhece: a autorização entre
    inquilinos dela nunca foi exercida por teste nenhum."""
    fora = _fora_da_varredura()
    escrita = [r for r in fora if r[0] in METODOS_DE_ESCRITA]
    medida("L4-23-isolamento-por-inquilino-na-rede")(
        "rotas_servidas_fora_da_varredura_cruzada", len(fora), "rotas",
        "diferenca entre as rotas que app.main.app serve em processo e as que docs/openapi.json lista, "
        "que e a fonte dos casos de tests/api/test_cruzado.py")
    assert not escrita, (
        f"{len(escrita)} rota(s) de escrita servidas e fora da varredura cruzada A→B — a autorização entre "
        f"inquilinos delas não foi exercida por teste nenhum. Regerar docs/openapi.json E escrever o caso "
        f"de cada uma em tests/api/cruzado_casos.py:\n  " + "\n  ".join(f"{m} {c}" for m, c in escrita))


@LACUNA_ABERTA
def test_nenhuma_rota_de_leitura_servida_fica_fora_da_varredura_cruzada():
    """Mesma conta para as rotas de leitura. Vazamento de leitura é vazamento igual — é por leitura que se
    lê o dado do vizinho."""
    fora = [r for r in _fora_da_varredura() if r[0] not in METODOS_DE_ESCRITA]
    assert not fora, (
        f"{len(fora)} rota(s) de leitura servidas e fora da varredura cruzada A→B:\n  "
        + "\n  ".join(f"{m} {c}" for m, c in fora))


@LACUNA_ABERTA
def test_a_varredura_nao_lista_rota_que_ja_nao_existe():
    """O contrário também conta: caso escrito para rota que saiu do produto dá cobertura de mentira."""
    sobrando = sorted(_rotas_do_arquivo() - _rotas_servidas())
    assert not sobrando, (
        f"{len(sobrando)} rota(s) em docs/openapi.json que a aplicação já não serve (a varredura as conta "
        f"como cobertas):\n  " + "\n  ".join(f"{m} {c}" for m, c in sobrando))
