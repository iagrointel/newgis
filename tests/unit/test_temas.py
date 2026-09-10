"""Unitário do módulo de temas (item L5-10-temas-marca): validação estrita por FORMATO (refutação do
item: `url(javascript:...)` e `expression()` nunca passam), a cadeia de resolução
documento -> inquilino -> padrão, os nomes de CSS custom properties e o cálculo de contraste — o portão
pede que o teste automatizado calcule os 10 pares de texto (WCAG 1.4.3) de cada tema padrão.

Sem banco e sem FastAPI: app/temas.py é puro de propósito, o MESMO validador serve PUT /api/org/tema,
corpo.tema de documento e os 6 padrões servidos por GET /api/temas."""

import pytest

from app import temas
from app.erros import ErroAPI


def _tema_completo():
    """Um tema válido com os dois modos e as 9 cores (base para os testes de contraste e de resolução)."""
    return {
        "claro": {
            "cores": {
                "fundo": "#f4f5f7", "superficie": "#ffffff", "texto": "#1c2430",
                "texto_suave": "#4e5d6e", "acento": "#0b5cad", "texto_sobre_acento": "#ffffff",
                "borda": "#c9d1d9", "sucesso": "#1a6b3c", "erro": "#a12622",
            },
            "tipografia": {"familia_texto": "IBM Plex Sans"},
            "raio": {"pequeno": "2px", "medio": "4px", "grande": "8px"},
            "espacamento": {"pequeno": "4px", "medio": "12px", "grande": "24px"},
            "sombra": {"nivel_1": {"x": 0, "y": 1, "desfoque": 3, "cor": "#1c243055"}},
        },
        "escuro": {
            "cores": {
                "fundo": "#10151c", "superficie": "#1a222d", "texto": "#e8edf3",
                "texto_suave": "#a9b6c4", "acento": "#58a9ea", "texto_sobre_acento": "#0b1622",
                "borda": "#33404f", "sucesso": "#58c98a", "erro": "#e77370",
            },
        },
    }


# ---------------------------------------------------------------- refutação: injeção recusada por formato

@pytest.mark.parametrize(
    "cor",
    [
        "url(javascript:alert(1))",           # a injeção que a refutação do item manda tentar
        "expression(alert(1))",
        "javascript:alert(1)",
        "red",
        "#zzzzzz",
        "#12345",
        "linear-gradient(#fff, #000)",
        "url(https://exemplo/imagen.png)",
        "",
    ],
)
def test_cor_fora_do_formato_e_recusada(cor):
    with pytest.raises(ErroAPI) as e:
        temas.validar_tema({"claro": {"cores": {"fundo": cor}}})
    assert e.value.status_code == 422 and e.value.erro == "tema_invalido"


@pytest.mark.parametrize(
    "fonte",
    ["Comic Sans MS", "url(javascript:alert(1))", "expression(alert(1))", "IBM Plex Sans'; DROP TABLE x;--", ""],
)
def test_fonte_fora_da_lista_e_recusada(fonte):
    with pytest.raises(ErroAPI) as e:
        temas.validar_tema({"claro": {"tipografia": {"familia_texto": fonte}}})
    assert e.value.status_code == 422 and e.value.erro == "tema_invalido"


@pytest.mark.parametrize("medida", ["12", "10pt", "1em2", "-4px", "grande", "url(javascript:alert(1))"])
def test_medida_fora_do_formato_e_recusada(medida):
    with pytest.raises(ErroAPI) as e:
        temas.validar_tema({"claro": {"raio": {"pequeno": medida}}})
    assert e.value.status_code == 422 and e.value.erro == "tema_invalido"


def test_token_desconhecido_e_modo_ausente_sao_recusados():
    with pytest.raises(ErroAPI):
        temas.validar_tema({"claro": {"cores": {"cor_que_nao_existe": "#123456"}}})
    with pytest.raises(ErroAPI):
        temas.validar_tema({"verde": {"cores": {}}})
    with pytest.raises(ErroAPI):  # nem claro nem escuro
        temas.validar_tema({})


def test_sombra_com_campo_errado_ou_deslocamento_absurdo_e_recusada():
    with pytest.raises(ErroAPI):
        temas.validar_tema({"claro": {"sombra": {"nivel_1": {"x": 0, "y": 1, "cor": "#000000"}}}})
    with pytest.raises(ErroAPI):  # |deslocamento| acima do teto de 100
        temas.validar_tema({"claro": {"sombra": {"nivel_2": {"x": 0, "y": 900, "desfoque": 0, "cor": "#000000"}}}})


def test_tema_valido_passa_e_normaliza():
    # chave de token é exata (strict: chave errada é recusa, não correção); VALOR de cor é normalizado
    saida = temas.validar_tema({"claro": {"cores": {"acento": "#0B5CAD"}, "raio": {"pequeno": "2px"}}})
    assert saida["claro"]["cores"]["acento"] == "#0b5cad"
    assert saida["claro"]["raio"]["pequeno"] == "2px"


# ---------------------------------------------------------------- referência em corpo.tema de documento

def test_referencia_de_documento_aceita_id_padrao_e_inquilino():
    temas.validar_referencia_de_documento({"id": "prado"})
    temas.validar_referencia_de_documento({"id": "inquilino"})
    temas.validar_referencia_de_documento({"definicao": {"claro": {"cores": {"fundo": "#ffffff"}}}})


@pytest.mark.parametrize(
    "referencia",
    [
        {"id": "fantasma"},                       # id que não é padrão nem inquilino
        {"id": "prado", "definicao": {"claro": {}}},  # os dois juntos
        {},                                       # nem id nem definicao
        "prado",                                  # nem objeto é
        {"definicao": {"claro": {"cores": {"fundo": "url(javascript:alert(1))"}}}},
    ],
)
def test_referencia_de_documento_recusa_o_invalido(referencia):
    with pytest.raises(ErroAPI) as e:
        temas.validar_referencia_de_documento(referencia)
    assert e.value.status_code == 422 and e.value.erro == "tema_invalido"


# ---------------------------------------------------------------- cadeia de resolução

def test_cadeia_documento_definicao_vence_todo_o_resto():
    definicao = {"claro": {"cores": {"fundo": "#123456"}}}
    tokens, origem = temas.resolver({"definicao": definicao}, {"cores": {"fundo": "#654321"}})
    assert origem == "documento" and tokens is definicao


def test_cadeia_documento_por_id_vence_inquilino():
    tokens, origem = temas.resolver({"id": "prado"}, {"claro": {}})
    assert origem == "documento" and tokens is temas.TEMAS_PADRAO["prado"]["tokens"]


def test_cadeia_documento_pedindo_inquilino_cai_para_o_inquilino_e_depois_para_o_padrao():
    inquilino = {"claro": {"cores": {"fundo": "#abcdef"}}}
    tokens, origem = temas.resolver({"id": "inquilino"}, inquilino)
    assert origem == "inquilino" and tokens is inquilino
    tokens, origem = temas.resolver({"id": "inquilino"}, None)
    assert origem == "padrao" and tokens is temas.TEMAS_PADRAO[temas.ID_PADRAO]["tokens"]


def test_cadeia_sem_nada_e_o_padrao():
    tokens, origem = temas.resolver(None, None)
    assert origem == "padrao" and tokens is temas.TEMAS_PADRAO[temas.ID_PADRAO]["tokens"]
    # id desconhecido num documento velho: não pode derrubar a renderização — cai na cadeia
    tokens, origem = temas.resolver({"id": "sumido"}, None)
    assert origem == "padrao"


# ---------------------------------------------------------------- contraste (WCAG 1.4.3)

def test_contraste_de_valores_conhecidos():
    assert round(temas.contraste("#000000", "#ffffff"), 2) == 21.0
    assert temas.contraste("#ffffff", "#ffffff") == 1.0  # a mesma cor não tem contraste nenhum


def test_os_seis_temas_padroes_sao_avaliados_em_10_pares_sem_aviso():
    """Cláusula do portão: o teste automatizado calcula o contraste dos 10 pares de texto — aqui para os
    6 temas padrão (paridade StoryMaps/Web AppBuilder), que precisam nascer sem aviso nenhum."""
    assert len(temas.TEMAS_PADRAO) == 6
    for id_tema, entrada in temas.TEMAS_PADRAO.items():
        assert set(entrada["tokens"]) == {"claro", "escuro"}, id_tema
        for modo, tokens in entrada["tokens"].items():
            pares = temas.avaliar_modo(tokens)
            assert len(pares) == 10, (id_tema, modo, len(pares))
            reprovados = [p for p in pares if not p["ok"]]
            assert reprovados == [], (id_tema, modo, reprovados)


def test_tema_abaixo_do_minimo_vira_aviso_com_par_e_razao():
    tema = {"claro": {"cores": {k: v for k, v in _tema_completo()["claro"]["cores"].items()}}}
    tema["claro"]["cores"]["texto"] = "#8a8a8a"  # cinza médio sobre fundo claro não chega a 4,5:1
    avisos = temas.avisos_do_tema(tema)
    pares = {a["par"] for a in avisos}
    assert "texto/fundo" in pares and "texto/superficie" in pares
    for a in avisos:
        assert a["razao"] < 4.5 and a["minimo"] == 4.5 and a["modo"] == "claro"


def test_tema_parcial_avalia_somente_os_pares_computaveis():
    tema = {"claro": {"cores": {"acento": "#0b5cad", "texto_sobre_acento": "#ffffff"}}}
    pares = temas.avaliar_modo(tema["claro"])
    assert [p["par"] for p in pares] == ["texto_sobre_acento/acento"]
    assert temas.avisos_do_tema(tema) == []


# ---------------------------------------------------------------- CSS custom properties

def test_css_variaveis_usa_os_nomes_da_regra_da_casa():
    saida = temas.css_variaveis(_tema_completo()["claro"])
    assert saida["--t-texto-suave"] == "#4e5d6e"
    assert saida["--t-familia-texto"] == "IBM Plex Sans"
    assert saida["--t-raio-pequeno"] == "2px"
    assert saida["--t-espacamento-grande"] == "24px"
    assert saida["--t-sombra-nivel-1"] == "0px 1px 3px #1c243055"


def test_seis_temas_padroes_com_nome_e_tokens_sao_o_vocabulario_da_casa():
    esperados = {"padrao", "lamina", "mare", "prado", "terra", "alto_contraste"}
    assert set(temas.TEMAS_PADRAO) == esperados
    for entrada in temas.TEMAS_PADRAO.values():
        assert isinstance(entrada["nome"], str) and entrada["nome"]
