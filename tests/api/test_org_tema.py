"""API dos temas de marca (item L5-10-temas-marca): GET /api/temas serve os 6 padrões (com nome, tokens e
avisos de contraste) e o tema do inquilino quando existir, para qualquer membro autenticado (a marca é vista
por todo o inquilino); PUT /api/org/tema grava/remove o tema do inquilino com o MESMO privilégio de sessão
do PUT /api/org (`org.configurar`), validação estrita 422 `tema_invalido` nomeando o token (a refutação do
item injeta `url(javascript:...)`/`expression()` e precisa ser recusada por FORMATO, antes do banco); tema
com contraste abaixo de 4,5:1 é ACEITO mas volta com `avisos`. O `corpo.tema` de documento (app/painel) tem
suíte própria em tests/api/catalogo/test_documento_tema.py; o isolamento entre inquilinos fica na varredura
cruzada (casos GET /api/temas e PUT /api/org/tema em cruzado_casos.py)."""

import pytest

from app import temas

# serial: grava e remove o tema do INQUILINO demo inteiro (config do tenant) — roda com -n 0
pytestmark = pytest.mark.serial


@pytest.fixture(autouse=True)
def tema_do_inquilino_zerado(sessao_a):
    """Limpa o tema do inquilino ANTES e DEPOIS de cada teste: nenhum teste herda a marca de outro e uma
    falha no meio não deixa tema residual na configuração do inquilino de demonstração."""
    sessao_a.put("/api/org/tema", json={"tema": None})
    yield
    sessao_a.put("/api/org/tema", json={"tema": None})


def _tema_valido() -> dict:
    """Tema mínimo completo (as 9 cores do claro), sem aviso de contraste nenhum (conferido com
    temas.avaliar_modo)."""
    return {
        "claro": {
            "cores": {
                "fundo": "#eef1f0", "superficie": "#ffffff", "texto": "#12181a",
                "texto_suave": "#4d5b57", "acento": "#8f4f10", "texto_sobre_acento": "#fff6ec",
                "borda": "#ccd4d1", "sucesso": "#2f7a4c", "erro": "#a83c2e",
            },
            "espacamento": {"grande": "33px"},
        },
    }


def _tema_sem_contraste() -> dict:
    tema = _tema_valido()
    tema["claro"]["cores"]["texto"] = "#8a8a8a"  # sobre #eef1f0 fica abaixo de 4,5:1
    return tema


def test_get_devolve_seis_padroes_com_avisos_vazios_e_inquilino_nulo(sessao_a):
    r = sessao_a.get("/api/temas")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert set(corpo["padroes"]) == {"padrao", "lamina", "mare", "prado", "terra", "alto_contraste"}
    for id_tema, entrada in corpo["padroes"].items():
        assert entrada["nome"], id_tema
        assert set(entrada["tema"]) == {"claro", "escuro"}, id_tema
        assert entrada["avisos"] == [], (id_tema, entrada["avisos"])
    # estado de partida: sem tema de inquilino (testes anteriores limpam no fim)
    assert corpo["inquilino"] is None


def test_get_exige_sessao_e_abre_para_editor(cliente, sessao_a, usuarios_a):
    assert cliente.get("/api/temas").status_code == 401
    c_ed, _, _ = usuarios_a.sessao("editor")
    r = c_ed.get("/api/temas")
    assert r.status_code == 200  # a marca é vista por todo membro; só GRAVAR exige org.configurar


def test_put_grava_e_le_de_volta_o_mesmo_tema_e_registra_evento(sessao_a):
    tema = _tema_valido()
    r = sessao_a.put("/api/org/tema", json={"tema": tema})
    assert r.status_code == 200, r.text
    assert r.json()["tema"] == tema
    assert r.json()["avisos"] == []
    lido = sessao_a.get("/api/temas").json()
    assert lido["inquilino"] is not None
    assert lido["inquilino"]["tema"] == tema
    # remove no fim: o inquilino volta ao estado de partida para os testes seguintes
    assert sessao_a.put("/api/org/tema", json={"tema": None}).status_code == 200
    assert sessao_a.get("/api/temas").json()["inquilino"] is None


def test_put_exige_org_configurar(sessao_a, usuarios_a):
    c_ed, _, _ = usuarios_a.sessao("editor")
    r = c_ed.put("/api/org/tema", json={"tema": _tema_valido()})
    assert r.status_code == 403 and r.json()["erro"] == "sem_privilegio"
    assert sessao_a.get("/api/temas").json()["inquilino"] is None


@pytest.mark.parametrize(
    "injecao, campo",
    [
        ({"claro": {"cores": {"fundo": "url(javascript:alert(1))"}}}, "claro.cores.fundo"),
        ({"claro": {"tipografia": {"familia_texto": "expression(alert(1))"}}}, "claro.tipografia.familia_texto"),
        ({"claro": {"raio": {"pequeno": "url(javascript:alert(1))"}}}, "claro.raio.pequeno"),
        (
            {"claro": {"sombra": {"nivel_1": {"x": 0, "y": 0, "desfoque": 0, "cor": "javascript:alert(1)"}}}},
            "claro.sombra.nivel_1.cor",
        ),
    ],
)
def test_put_recusa_injecao_por_formato_e_nao_altera_o_inquilino(sessao_a, injecao, campo):
    r = sessao_a.put("/api/org/tema", json={"tema": injecao})
    # recusa por FORMATO nomeando o token exato que falhou (nunca grava nada)
    assert r.status_code == 422 and r.json()["erro"] == "tema_invalido", r.text
    assert campo in str(r.json()), r.text
    assert sessao_a.get("/api/temas").json()["inquilino"] is None


def test_put_com_contraste_baixo_e_aceito_mas_volta_com_aviso(sessao_a):
    r = sessao_a.put("/api/org/tema", json={"tema": _tema_sem_contraste()})
    assert r.status_code == 200, r.text
    avisos = r.json()["avisos"]
    pares = {(a["modo"], a["par"]) for a in avisos}
    assert ("claro", "texto/fundo") in pares and ("claro", "texto/superficie") in pares
    for a in avisos:
        assert a["razao"] < a["minimo"] == 4.5
    # o aviso viaja junto no GET (quem consome o tema enxerga o mesmo aviso)
    lido = sessao_a.get("/api/temas").json()
    assert lido["inquilino"]["avisos"] == avisos
    assert sessao_a.put("/api/org/tema", json={"tema": None}).status_code == 200


def test_put_sem_chave_tema_e_recusado(sessao_a):
    # remover por acidente (PUT vazio) não pode apagar a marca do inquilino: a chave é obrigatória
    r = sessao_a.put("/api/org/tema", json={})
    assert r.status_code == 422, r.text


def test_vocabulario_do_modulo_e_o_que_a_api_serve(sessao_a):
    """Paridade: o que app/temas.TEMAS_PADRAO declara é byte a byte o que o GET serve (o front-end resolve a
    cadeia com ESTA resposta — nada de tema conhecido só pelo servidor)."""
    r = sessao_a.get("/api/temas").json()
    assert set(r["padroes"]) == set(temas.TEMAS_PADRAO)
    for id_tema, entrada in temas.TEMAS_PADRAO.items():
        assert r["padroes"][id_tema]["tema"] == entrada["tokens"]
