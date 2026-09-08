"""Rotas /api/amc/presets (item L3-01-h-presets): CRUD por API, aplicação SÍNCRONA sem job, export e
import em JSON, e as travas de acesso — o portão do item pede "preset de outro inquilino inacessível
(teste cruzado)", provado aqui com a sessão de B e na varredura A→B (casos em cruzado_casos.py).
Refutação do item: adversário importa preset com fator que o modelo não tem → recusa com a lista do
que falta. Os pesos são escolha do usuário, nunca medida da casa (AVISO_PESOS acompanha o resultado).
"""

import secrets

import pytest

from app.amc.combinacao import AVISO_PESOS
from tests.api.conftest import PREFIXO_TESTE

CONTEUDO = {"fatores": ["acesso_rodoviario", "custo_terreno"],
            "pesos": {"acesso_rodoviario": 5.0, "custo_terreno": 2.0}}
MATRIZ = {"ids_fatores": ["acesso_rodoviario", "custo_terreno"],
          "fatores": [[80.0, 40.0], [70.0, 20.0], [None, 50.0]]}


def _criar(sessao, sufixo, escopo="usuario", conteudo=None):
    return sessao.post("/api/amc/presets", json={
        "nome": f"{PREFIXO_TESTE}-preset-{sufixo}", "descricao": "preset de teste",
        "escopo": escopo, "conteudo": conteudo or CONTEUDO,
    })


@pytest.fixture
def limpar_presets(sessao_a):
    criados = []
    yield criados
    for pid in criados:
        sessao_a.delete(f"/api/amc/presets/{pid}")


# ------------------------------------------------------------------ CRUD


def test_criar_ver_listar_fluxo_basico(sessao_a, limpar_presets):
    r = _criar(sessao_a, "basico")
    assert r.status_code == 201, r.text
    preset = r.json()
    limpar_presets.append(preset["id"])
    assert preset["nome"] == f"{PREFIXO_TESTE}-preset-basico"
    assert preset["escopo"] == "usuario"
    assert preset["integrado"] is False
    assert preset["conteudo"]["pesos"] == CONTEUDO["pesos"]
    assert preset["dono_login"]

    r_ver = sessao_a.get(f"/api/amc/presets/{preset['id']}")
    assert r_ver.status_code == 200
    assert r_ver.json()["conteudo"] == preset["conteudo"]

    r_lista = sessao_a.get("/api/amc/presets")
    assert r_lista.status_code == 200
    ids = {i["id"] for i in r_lista.json()["itens"]}
    assert preset["id"] in ids
    # os integrados saem SEMPRE na listagem, o 'pesos iguais' inclusive (contrato do item)
    nomes = {i["nome"] for i in r_lista.json()["itens"]}
    assert "pesos iguais" in nomes and "logística: galpão" in nomes


def test_criar_com_nome_repetido_no_mesmo_escopo_e_409(sessao_a, limpar_presets):
    r1 = _criar(sessao_a, "unico")
    assert r1.status_code == 201, r1.text
    limpar_presets.append(r1.json()["id"])
    r2 = _criar(sessao_a, "unico")
    assert r2.status_code == 409
    assert r2.json()["erro"] == "nome_existente"


def test_editar_e_apagar_pelo_dono(sessao_a, limpar_presets):
    pid = _criar(sessao_a, "editar").json()["id"]
    limpar_presets.append(pid)
    r = sessao_a.patch(f"/api/amc/presets/{pid}",
                       json={"descricao": "atualizada",
                             "conteudo": {"pesos_iguais": True, "combinador": "soma_ponderada",
                                          "politica_ausente": "excluir"}})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["descricao"] == "atualizada"
    assert corpo["conteudo"]["pesos_iguais"] is True
    assert corpo["conteudo"]["fatores"] == []
    assert corpo["atualizado_em"] >= corpo["criado_em"]

    r_del = sessao_a.delete(f"/api/amc/presets/{pid}")
    assert r_del.status_code == 204
    limpar_presets.remove(pid)
    assert sessao_a.get(f"/api/amc/presets/{pid}").status_code == 404


def test_criar_recusa_conteudo_invalido_com_codigo_estavel(sessao_a):
    for conteudo, codigo in (
        ({"pesos": {"a": 1.0}}, "fatores_ausentes"),
        ({"fatores": ["a", "a"], "pesos": {"a": 1.0}}, "fator_duplicado"),
        ({"fatores": ["a", "b"], "pesos": {"a": 0.0, "b": 0.0}}, "soma_de_pesos_zero"),
        ({"fatores": ["a"], "pesos": {"b": 1.0}}, "peso_fora_da_lista"),
        ({"fatores": ["a"], "pesos": {"a": 1.0}, "combinador": "媒体"}, "combinador_desconhecido"),
    ):
        r = _criar(sessao_a, "invalido", conteudo=conteudo)
        assert r.status_code == 422, r.text
        assert r.json()["erro"] == codigo


# ------------------------------------------------------------------ aplicar (recalcula sem job)


def test_aplicar_recalcula_na_mesma_resposta_sem_criar_job(sessao_a, limpar_presets):
    pid = _criar(sessao_a, "aplicar").json()["id"]
    limpar_presets.append(pid)
    r = sessao_a.post(f"/api/amc/presets/{pid}/aplicar", json=MATRIZ)
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["preset_id"] == pid
    assert corpo["pesos_iguais"] is False
    fav = corpo["resultado"]["fav"]
    assert fav[0] == pytest.approx((80.0 * 5.0 + 40.0 * 2.0) / 7.0)
    # unidade sem dado no acesso_rodoviario: a nota vem do fator restante ('excluir') e a cobertura
    # registra a lacuna — só unidade SEM dado nenhum é que sai sem nota
    assert fav[2] == pytest.approx(50.0)
    # cobertura PONDERADA: só o custo_terreno (peso 2 de 7) tinha dado nessa unidade
    assert corpo["resultado"]["cobertura"][2] == pytest.approx(2.0 / 7.0)
    assert corpo["resultado"]["aviso_pesos"] == AVISO_PESOS
    # SEM job: a resposta traz o resultado pronto na mesma chamada, sem referência a job nenhum,
    # e a fila do usuário não ganhou trabalho de preset
    assert "job" not in corpo and "job_id" not in corpo
    fila = sessao_a.get("/api/jobs?limite=200").json()
    assert not [j for j in fila["itens"] if "preset" in j["tipo"]]


def test_aplicar_pesos_iguais_sobre_matriz_qualquer(sessao_a):
    r = sessao_a.post("/api/amc/presets/pesos_iguais/aplicar",
                      json={"ids_fatores": ["qualquer_fator_x", "qualquer_fator_y"],
                            "fatores": [[90.0, 30.0]]})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["preset_nome"] == "pesos iguais"
    assert corpo["pesos_iguais"] is True
    assert corpo["resultado"]["fav"] == [pytest.approx(60.0)]


def test_aplicar_recusa_fator_da_matriz_que_o_preset_nao_declara(sessao_a):
    r = sessao_a.post("/api/amc/presets/pesos_iguais/aplicar",
                      json={"ids_fatores": ["a"], "fatores": [[1.0, 2.0]]})
    assert r.status_code == 422
    assert r.json()["erro"] == "matriz_invalida"


def test_aplicar_integrado_galpao_aplica_veto_onde_tem_dado(sessao_a):
    r = sessao_a.post("/api/amc/presets/logistica_galpao/aplicar", json={
        "ids_fatores": ["acesso_rodoviario", "polo_gerador_carga", "proximidade_porto",
                        "custo_terreno", "proximidade_aeroporto", "area_alagada"],
        "fatores": [[80.0, 70.0, 60.0, 50.0, 40.0, 5.0],
                    [80.0, 70.0, 60.0, 50.0, 40.0, None]],
    })
    assert r.status_code == 200, r.text
    res = r.json()["resultado"]
    assert res["fav"][0] == 0.0           # vetada: nota ZERADA por restrição, não por peso
    assert res["vetado"][0] is True
    assert res["vetado"][1] is False      # sem dado no fator de veto: veto não é inventado
    assert res["fav"][1] > 0.0


# ------------------------------------------------------------------ acesso cruzado


def test_preset_de_outro_inquilino_e_inacessivel(sessao_a, sessao_b, limpar_presets):
    pid = _criar(sessao_a, "cruzado").json()["id"]
    limpar_presets.append(pid)
    # a listagem de B nunca traz o preset de A
    lista_b = sessao_b.get("/api/amc/presets").json()
    assert pid not in {i["id"] for i in lista_b["itens"]}
    # e o acesso direto é 404 — para B, o preset de A e o inexistente são a mesma resposta
    for metodo, corpo in (("get", None), ("patch", {"nome": "roubado"}),
                          ("delete", None), ("post", MATRIZ)):
        url = f"/api/amc/presets/{pid}" + ("/aplicar" if metodo == "post" else "")
        r = getattr(sessao_b, metodo)(url, json=corpo) if corpo else getattr(sessao_b, metodo)(url)
        assert r.status_code == 404, (metodo, r.text)
        assert r.json()["erro"] == "preset_inexistente"
    # B não consegue exportar nem apagar: o preset de A fica intacto
    assert sessao_a.get(f"/api/amc/presets/{pid}").status_code == 200


def test_preset_de_escopo_usuario_e_invisivel_ao_colega_do_mesmo_inquilino(sessao_a, usuarios_a):
    admin_pid = _criar(sessao_a, "solo-dono").json()["id"]
    colega, _, _ = usuarios_a.sessao()
    try:
        r = colega.get(f"/api/amc/presets/{admin_pid}")
        assert r.status_code == 404
        assert admin_pid not in {i["id"] for i in colega.get("/api/amc/presets").json()["itens"]}
        # integrado é do inquilino inteiro: o colega VÊ e consegue aplicar
        r_int = colega.post("/api/amc/presets/pesos_iguais/aplicar",
                            json={"ids_fatores": ["f"], "fatores": [[50.0]]})
        assert r_int.status_code == 200
    finally:
        sessao_a.delete(f"/api/amc/presets/{admin_pid}")


def test_presets_integrados_sao_somente_leitura(sessao_a):
    r_patch = sessao_a.patch("/api/amc/presets/pesos_iguais", json={"nome": "meu"})
    assert r_patch.status_code == 403
    assert r_patch.json()["erro"] == "integrado_somente_leitura"
    r_del = sessao_a.delete("/api/amc/presets/logistica_galpao")
    assert r_del.status_code == 403
    # uuid que não existe: 404 estável
    r_nulo = sessao_a.get("/api/amc/presets/00000000-0000-0000-0000-000000000000")
    assert r_nulo.status_code == 404
    r_nao_uuid = sessao_a.get("/api/amc/presets/nao-e-uuid")
    assert r_nao_uuid.status_code == 404


# ------------------------------------------------------------------ exportar / importar


def test_exportar_e_importar_roundtrip_com_a_lista_do_que_falta(sessao_a, limpar_presets):
    pid = _criar(sessao_a, "viagem").json()["id"]
    limpar_presets.append(pid)
    r_exp = sessao_a.get(f"/api/amc/presets/{pid}/exportar")
    assert r_exp.status_code == 200
    documento = r_exp.json()
    assert documento["formato"] == "plat/amc_preset" and documento["versao"] == 1
    # o conteúdo sai NORMALIZADO (padrões preenchidos: combinador, política, gama, vetos, pesos_iguais)
    assert documento["conteudo"]["fatores"] == CONTEUDO["fatores"]
    assert documento["conteudo"]["pesos"] == CONTEUDO["pesos"]
    assert documento["conteudo"]["combinador"] == "soma_ponderada"
    assert documento["conteudo"]["politica_ausente"] == "excluir"

    documento["nome"] = f"{PREFIXO_TESTE}-preset-volta-{secrets.token_hex(3)}"
    r_imp = sessao_a.post("/api/amc/presets/importar", json=documento)
    assert r_imp.status_code == 201, r_imp.text
    importado = r_imp.json()
    limpar_presets.append(importado["id"])
    assert importado["faltando"] == []
    assert sessao_a.get(f"/api/amc/presets/{importado['id']}").status_code == 200

    # a refutação do item: importar com fator que o modelo não tem → recusa COM a lista do que falta
    documento["nome"] = f"{PREFIXO_TESTE}-preset-armadilha-{secrets.token_hex(3)}"
    documento["fatores_modelo"] = ["acesso_rodoviario"]
    r_falta = sessao_a.post("/api/amc/presets/importar", json=documento)
    assert r_falta.status_code == 422
    corpo = r_falta.json()
    assert corpo["erro"] == "fator_fora_do_modelo"
    assert corpo["detalhe"]["faltando"] == ["custo_terreno"]

    # formato desconhecido também é recusado antes de tocar o banco
    r_fmt = sessao_a.post("/api/amc/presets/importar",
                          json={**{k: v for k, v in documento.items() if k != "fatores_modelo"},
                                "formato": "outro/formato"})
    assert r_fmt.status_code == 422
    assert r_fmt.json()["erro"] == "formato_desconhecido"
