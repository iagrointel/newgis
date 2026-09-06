"""Regras do documento de mapa que o JSON Schema não expressa (item L2-01-a-documento-mapa; app/mapas/documento.py):
id repetido, grupo inexistente, ciclo de grupo, profundidade acima de 3, favorito órfão, extensão invertida e faixa
de escala invertida. Sem banco e sem HTTP — a mesma função que a rota chama."""

import pytest

from app.erros import ErroAPI
from app.mapas import documento as doc

ULID_A = "01J0000000000000000000000A"
ULID_B = "01J0000000000000000000000B"
ULID_C = "01J0000000000000000000000C"
ULID_D = "01J0000000000000000000000D"
UUID_1 = "11111111-1111-4111-8111-111111111111"
UUID_2 = "22222222-2222-4222-8222-222222222222"


def documento(**corpo) -> dict:
    return {"esquema_versao": 1, "corpo": corpo}


def camada(id_local: str, ref: str = UUID_1, **extra) -> dict:
    return {"id": id_local, "ref": ref, **extra}


def regras(dados) -> list[str]:
    return [e["regra"] for e in doc.erros_de_coerencia(dados)]


def test_documento_minimo_e_coerente():
    assert doc.erros_de_coerencia(documento()) == []
    assert doc.erros_de_coerencia({"esquema_versao": 1, "corpo": {}}) == []


def test_id_de_camada_repetido():
    d = documento(camadas=[camada(ULID_A), camada(ULID_A, UUID_2)])
    assert regras(d) == ["id_repetido"]


def test_id_de_grupo_repetido():
    d = documento(grupos=[{"id": ULID_A, "titulo": "um"}, {"id": ULID_A, "titulo": "dois"}])
    assert "id_repetido" in regras(d)


def test_camada_em_grupo_inexistente():
    d = documento(camadas=[camada(ULID_A, grupo=ULID_B)])
    assert regras(d) == ["grupo_inexistente"]


def test_grupo_com_pai_inexistente():
    d = documento(grupos=[{"id": ULID_A, "titulo": "um", "pai": ULID_D}])
    assert "grupo_inexistente" in regras(d)


def test_tres_niveis_de_grupo_passam_e_quatro_nao():
    tres = documento(
        grupos=[
            {"id": ULID_A, "titulo": "1"},
            {"id": ULID_B, "titulo": "2", "pai": ULID_A},
            {"id": ULID_C, "titulo": "3", "pai": ULID_B},
        ]
    )
    assert doc.erros_de_coerencia(tres) == []
    quatro = documento(
        grupos=[
            {"id": ULID_A, "titulo": "1"},
            {"id": ULID_B, "titulo": "2", "pai": ULID_A},
            {"id": ULID_C, "titulo": "3", "pai": ULID_B},
            {"id": ULID_D, "titulo": "4", "pai": ULID_C},
        ]
    )
    assert "grupo_profundo" in regras(quatro)


def test_ciclo_de_grupo_nao_trava_e_e_acusado():
    d = documento(
        grupos=[
            {"id": ULID_A, "titulo": "1", "pai": ULID_B},
            {"id": ULID_B, "titulo": "2", "pai": ULID_A},
        ]
    )
    saida = regras(d)
    assert "grupo_ciclo" in saida


def test_favorito_apontando_para_camada_fora_do_documento():
    d = documento(
        camadas=[camada(ULID_A)],
        favoritos=[{"nome": "casa", "extensao": [-47, -24, -46, -23], "camadas_visiveis": [ULID_B]}],
    )
    assert regras(d) == ["camada_inexistente"]


def test_extensao_invertida_no_documento_e_no_favorito():
    d = documento(extensao_inicial=[-46, -23, -47, -24])
    assert regras(d) == ["extensao_invertida", "extensao_invertida"]
    f = documento(favoritos=[{"nome": "x", "extensao": [-46, -23, -47, -22]}])
    assert regras(f) == ["extensao_invertida"]


def test_faixa_de_escala_invertida():
    d = documento(camadas=[camada(ULID_A, escala_min=50000, escala_max=1000)])
    assert regras(d) == ["escala_invertida"]
    ok = documento(camadas=[camada(ULID_A, escala_min=1000, escala_max=50000)])
    assert doc.erros_de_coerencia(ok) == []


def test_validar_coerencia_levanta_422_com_o_caminho():
    with pytest.raises(ErroAPI) as e:
        doc.validar_coerencia(documento(camadas=[camada(ULID_A, grupo=ULID_B)]))
    assert e.value.status_code == 422
    assert e.value.erro == "documento_incoerente"
    assert e.value.detalhe[0]["campo"] == "corpo.camadas.0.grupo"


def test_referencias_lidas_na_ordem_do_documento():
    d = documento(
        mapa_base={"ref": UUID_2},
        camadas=[camada(ULID_A, estilo={"ref": UUID_2}), camada(ULID_B, UUID_2, popup={"embutido": {}})],
    )
    campos = [c for c, _u, _a in doc.referencias(d)]
    assert campos == [
        "corpo.mapa_base.ref",
        "corpo.camadas.0.ref",
        "corpo.camadas.0.estilo.ref",
        "corpo.camadas.1.ref",
    ]


def test_contrato_de_tiles_nao_promete_servico_que_nao_existe():
    vetor = doc._tiles_da_camada({"id": "0f0f0f0f-0f0f-4f0f-8f0f-0f0f0f0f0f0f", "tipo": "camada_vetorial", "dados": {}})
    assert vetor["pronto"] is False and vetor["padrao"].startswith("/tiles/{token}/c_0f0f0f0f0f0f4f0f")
    raster = doc._tiles_da_camada({"id": "0f0f0f0f-0f0f-4f0f-8f0f-0f0f0f0f0f0f", "tipo": "raster", "dados": {}})
    assert raster["pronto"] is False and raster["servico"] == "titiler"
    externo = doc._tiles_da_camada(
        {"id": "0f0f0f0f-0f0f-4f0f-8f0f-0f0f0f0f0f0f", "tipo": "conexao", "dados": {"protocolo": "wms", "url": "https://x/y"}}
    )
    assert externo["pronto"] is True and externo["url"] == "https://x/y"
