"""Documento de cena (item L2-09-b-cena-extrusao-slides): o esquema JSON do tipo `cena` e as regras que
o esquema não expressa (app/cena/documento.py).

O esquema é lido do ARQUIVO da migração (db/migracoes/20260908T0601_cena_esquema.sql) e validado com o
mesmo Draft 2020-12 que a aplicação usa em app/catalogo/tipos.py — assim o teste roda sem banco e ainda
assim confere o esquema que vai para o banco, não uma cópia."""

import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from app.cena import documento as cena
from app.erros import ErroAPI

RAIZ = Path(__file__).resolve().parents[2]
MIGRACAO = RAIZ / "db" / "migracoes" / "20260908T0601_cena_esquema.sql"
ULID_A = "01J8ZK3M9Q7V2X5B8N4T6R1C0D"
ULID_B = "01J8ZK3M9Q7V2X5B8N4T6R1C0E"
UUID_A = "11111111-2222-3333-4444-555555555555"


@pytest.fixture(scope="module")
def validador() -> Draft202012Validator:
    texto = MIGRACAO.read_text(encoding="utf-8")
    corpo = texto.split("$esq$")
    assert len(corpo) == 3, "a migração precisa ter o esquema entre dois marcadores $esq$"
    esquema = json.loads(corpo[1])
    Draft202012Validator.check_schema(esquema)
    return Draft202012Validator(esquema, format_checker=Draft202012Validator.FORMAT_CHECKER)


def _cena_valida() -> dict:
    return {
        "esquema_versao": 1,
        "corpo": {
            "camera": {"centro": [-46.59, -23.49], "zoom": 15.5, "inclinacao": 60, "rotacao": 20},
            "terreno": {"ligado": True, "url": "/tiles/terreno/{z}/{x}/{y}.png", "codificacao": "terrain-rgb",
                        "tamanho_tile": 256, "zoom_maximo": 14, "exagero": 1.5},
            "iluminacao": {"modo": "data_hora", "instante": "2026-06-21T12:00:00-03:00", "intensidade": 0.35},
            "atmosfera": {"ceu": True, "nevoa": {"ligada": True, "inicio": 0.7, "fim": 1}},
            "camadas": [{
                "id": ULID_A, "camada_id": UUID_A, "titulo": "edificações", "visivel": True,
                "desenho": "extrusao", "opacidade": 0.95,
                "cor_por_campo": {"campo": "altura_m", "paradas": [{"valor": 0, "cor": "#e8ded0"},
                                                                   {"valor": 60, "cor": "#7c3f18"}]},
                "extrusao": {"campo_altura": "altura_m", "base_fixa": 0, "escala": 1},
            }],
            "slides": [{"id": ULID_B, "nome": "vista da praça", "camera": {"centro": [-46.59, -23.49], "zoom": 16},
                        "camadas_visiveis": [ULID_A], "instante": "2026-12-21T09:00:00-03:00"}],
        },
    }


# ---------------------------------------------------------------- esquema do tipo
def test_documento_completo_passa_no_esquema(validador):
    assert list(validador.iter_errors(_cena_valida())) == []


def test_corpo_vazio_continua_valido(validador):
    """O tipo existia com envelope vazio antes deste item: todo documento gravado tem de continuar
    válido depois da migração, senão a migração precisaria de conversão na leitura."""
    assert list(validador.iter_errors({"esquema_versao": 1, "corpo": {}})) == []


@pytest.mark.parametrize("caminho,valor", [
    ("inclinacao", 100),          # o MapLibre não passa de 85°
    ("rotacao", -10),
    ("zoom", 40),
])
def test_camera_fora_da_faixa_reprova(validador, caminho, valor):
    d = _cena_valida()
    d["corpo"]["camera"][caminho] = valor
    assert list(validador.iter_errors(d)), f"{caminho}={valor} deveria reprovar"


def test_campo_desconhecido_e_cor_invalida_reprovam(validador):
    d = _cena_valida()
    d["corpo"]["camadas"][0]["altura"] = 30  # nome errado: a altura mora em extrusao.campo_altura
    assert list(validador.iter_errors(d))
    d = _cena_valida()
    d["corpo"]["camadas"][0]["cor_por_campo"]["paradas"][0]["cor"] = "vermelho"
    assert list(validador.iter_errors(d))


def test_id_fora_do_formato_ulid_reprova(validador):
    d = _cena_valida()
    d["corpo"]["slides"][0]["id"] = "vista-1"
    assert list(validador.iter_errors(d))


def test_nome_de_campo_com_aspas_reprova(validador):
    """`campo` entra em expressão do MapLibre; o padrão do esquema só deixa passar identificador."""
    d = _cena_valida()
    d["corpo"]["camadas"][0]["extrusao"]["campo_altura"] = 'altura"; drop'
    assert list(validador.iter_errors(d))


# ---------------------------------------------------------------- regras do documento inteiro
def test_documento_valido_nao_gera_erro():
    assert cena.erros_de("cena", _cena_valida()) == []
    cena.validar("cena", _cena_valida())


def test_outro_tipo_nao_e_tocado():
    assert cena.erros_de("mapa", {"corpo": {"camadas": ["nada disso"]}}) == []


def test_id_de_camada_repetido():
    d = _cena_valida()
    d["corpo"]["camadas"].append({**d["corpo"]["camadas"][0]})
    erros = cena.erros_de("cena", d)
    assert [e["regra"] for e in erros] == ["id_duplicado"]


def test_slide_que_cita_camada_inexistente():
    d = _cena_valida()
    d["corpo"]["slides"][0]["camadas_visiveis"] = [ULID_B]
    erros = cena.erros_de("cena", d)
    assert [e["regra"] for e in erros] == ["camada_inexistente"]
    assert erros[0]["campo"] == "corpo.slides.0.camadas_visiveis.0"


def test_extrusao_sem_altura_nenhuma():
    d = _cena_valida()
    d["corpo"]["camadas"][0]["extrusao"] = {"escala": 1}
    erros = cena.erros_de("cena", d)
    assert [e["regra"] for e in erros] == ["extrusao_sem_altura"]


def test_altura_fixa_dispensa_o_campo():
    d = _cena_valida()
    d["corpo"]["camadas"][0]["extrusao"] = {"altura_fixa": 12}
    assert cena.erros_de("cena", d) == []


def test_base_acima_do_topo():
    d = _cena_valida()
    d["corpo"]["camadas"][0]["extrusao"] = {"altura_fixa": 10, "base_fixa": 20}
    assert [e["regra"] for e in cena.erros_de("cena", d)] == ["base_acima_do_topo"]


def test_camada_de_icone_nao_exige_altura():
    d = _cena_valida()
    d["corpo"]["camadas"][0] = {"id": ULID_A, "camada_id": UUID_A, "desenho": "icone", "icone": {"tamanho": 5}}
    d["corpo"]["slides"][0]["camadas_visiveis"] = [ULID_A]
    assert cena.erros_de("cena", d) == []


def test_validar_levanta_422_com_a_lista_de_campos():
    d = _cena_valida()
    d["corpo"]["camadas"][0]["extrusao"] = {}
    with pytest.raises(ErroAPI) as e:
        cena.validar("cena", d)
    assert e.value.status_code == 422
    assert e.value.erro == "cena_invalida"
    assert e.value.detalhe[0]["campo"] == "corpo.camadas.0.extrusao"


def test_a_migracao_nao_usa_numero_sequencial_nem_toca_tabela():
    texto = MIGRACAO.read_text(encoding="utf-8")
    assert re.match(r"^\d{8}T\d{4}", MIGRACAO.name), "nome de migração é carimbo de tempo (ADR 0014)"
    assert "CREATE TABLE" not in texto.upper(), "a cena reusa plat.item; nenhuma tabela nova"
