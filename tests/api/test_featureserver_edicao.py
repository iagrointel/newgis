"""Portão do item L2-04-d: escrita compatível com o protocolo Esri sobre a porta única de escrita
(`/rest/services/{item}/FeatureServer/0/applyEdits` e vizinhas).

A camada de teste é criada direto no banco pela mesma `FabricaCamada` do item L2-03-a (a carga por
ingestão não é o que este arquivo testa), e todo pedido passa pela aplicação inteira — nenhuma função é
chamada por dentro.
"""

from __future__ import annotations

import base64
import hashlib
import json
import uuid

import pytest

from tests.api.conftest import com_token
from tests.api.test_edicao_transacional import FabricaCamada, _admin_usuario_id
from tests.api.test_rls import contexto, ids_por_slug

# PNG 1x1 válido (o servidor confere o cabeçalho do conteúdo, não só o content-type declarado)
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@pytest.fixture
def fabrica(conexao_plat_app):
    f = FabricaCamada(conexao_plat_app)
    yield f
    f.limpar()


def _camada(fabrica, conexao_plat_app, slug="demo"):
    ids = ids_por_slug(conexao_plat_app)
    admin_id = _admin_usuario_id(conexao_plat_app, slug)
    item_id, dados = fabrica.criar(
        slug, ids[slug], admin_id,
        campos=[{"nome": "nome", "tipo": "text"}, {"nome": "area", "tipo": "double precision"}],
        geometria="Point",
    )
    return {"id": item_id, "dados": dados, "tenant_id": ids[slug], "admin_id": admin_id}


@pytest.fixture
def camada(fabrica, conexao_plat_app):
    return _camada(fabrica, conexao_plat_app)


@pytest.fixture
def camada_b(fabrica, conexao_plat_app):
    return _camada(fabrica, conexao_plat_app, "demo2")


def base(camada):
    return f"/rest/services/{camada['id']}/FeatureServer/0"


def feicao(nome, x=-46.5, y=-23.5, area=1.0):
    return {"attributes": {"nome": nome, "area": area}, "geometry": {"x": x, "y": y}}


def conta(fabrica, camada):
    return len(fabrica.linhas(camada["dados"]["schema"], camada["dados"]["tabela"],
                              camada["tenant_id"], camada["admin_id"]))


def semear(sessao, camada, quantos, prefixo="p"):
    r = sessao.post(f"{base(camada)}/applyEdits",
                    json={"adds": [feicao(f"{prefixo}{i}", -46.5 + i / 1000) for i in range(quantos)]})
    assert r.status_code == 200, r.text
    return r.json()["addResults"]


# ---------------------------------------------------------------- cláusula 1: 10 adds / 5 updates / 3 deletes
def test_apply_edits_devolve_os_tres_vetores(sessao_a, camada, fabrica):
    adicionados = semear(sessao_a, camada, 10)
    assert len(adicionados) == 10 and all(r["success"] for r in adicionados)
    assert all(isinstance(r["objectId"], int) and uuid.UUID(r["globalId"]) for r in adicionados)

    corpo = {
        "adds": [],
        "updates": [
            {"attributes": {"OBJECTID": r["objectId"], "nome": f"editado-{i}"}}
            for i, r in enumerate(adicionados[:5])
        ],
        "deletes": [r["objectId"] for r in adicionados[5:8]],
        "returnEditMoment": True,
    }
    r = sessao_a.post(f"{base(camada)}/applyEdits", json=corpo)
    assert r.status_code == 200, r.text
    saida = r.json()
    assert len(saida["addResults"]) == 0
    assert len(saida["updateResults"]) == 5 and all(x["success"] for x in saida["updateResults"])
    assert len(saida["deleteResults"]) == 3 and all(x["success"] for x in saida["deleteResults"])
    # editMoment em milissegundos desde a época (13 dígitos hoje, e sempre depois de 2020)
    assert saida["editMoment"] > 1_577_836_800_000, saida["editMoment"]
    assert conta(fabrica, camada) == 7

    linhas = fabrica.linhas(camada["dados"]["schema"], camada["dados"]["tabela"],
                            camada["tenant_id"], camada["admin_id"])
    assert sum(1 for linha in linhas if linha["nome"].startswith("editado-")) == 5


# ---------------------------------------------------------------- cláusula 2: rollbackOnFailure
def test_rollback_on_failure_nao_deixa_nada(sessao_a, camada, fabrica):
    semear(sessao_a, camada, 2)
    antes = conta(fabrica, camada)
    corpo = {
        "adds": [feicao("novo-1"), feicao("novo-2")],
        "deletes": [999_999_999],  # objectId inexistente = a única falha do lote
        "rollbackOnFailure": True,
    }
    r = sessao_a.post(f"{base(camada)}/applyEdits", json=corpo)
    assert r.status_code == 200, r.text
    saida = r.json()
    assert [x["success"] for x in saida["addResults"]] == [True, True]
    assert saida["deleteResults"][0]["success"] is False
    assert saida["deleteResults"][0]["error"]["code"] == 404
    assert saida.get("rolledBack") is True, saida
    assert conta(fabrica, camada) == antes, "rollbackOnFailure=true não pode deixar nada gravado"


def test_sem_rollback_a_parte_boa_fica(sessao_a, camada, fabrica):
    antes = conta(fabrica, camada)
    r = sessao_a.post(f"{base(camada)}/applyEdits", json={
        "adds": [feicao("fica")], "deletes": [999_999_999], "rollbackOnFailure": False,
    })
    assert r.status_code == 200, r.text
    assert r.json()["addResults"][0]["success"] is True
    assert conta(fabrica, camada) == antes + 1


# ---------------------------------------------------------------- cláusula 3: useGlobalIds
def test_use_global_ids_atualiza_por_globalid(sessao_a, camada, fabrica):
    [criado] = semear(sessao_a, camada, 1, "g")
    r = sessao_a.post(f"{base(camada)}/applyEdits", json={
        "useGlobalIds": True,
        "updates": [{"attributes": {"globalId": criado["globalId"], "nome": "por-globalid"}}],
    })
    assert r.status_code == 200, r.text
    resultado = r.json()["updateResults"][0]
    assert resultado["success"] is True and resultado["globalId"] == criado["globalId"]
    linhas = fabrica.linhas(camada["dados"]["schema"], camada["dados"]["tabela"],
                            camada["tenant_id"], camada["admin_id"])
    assert [linha["nome"] for linha in linhas] == ["por-globalid"]


def test_use_global_ids_com_id_desconhecido_e_404_na_posicao(sessao_a, camada):
    r = sessao_a.post(f"{base(camada)}/applyEdits", json={
        "useGlobalIds": True,
        "updates": [{"attributes": {"globalId": str(uuid.uuid4()), "nome": "x"}}],
        "rollbackOnFailure": False,
    })
    assert r.status_code == 200, r.text
    assert r.json()["updateResults"][0]["error"]["code"] == 404


# ---------------------------------------------------------------- cláusula 4: anexo multipart e leitura de volta
def test_add_attachment_multipart_e_leitura_com_sha256_igual(sessao_a, camada):
    [criado] = semear(sessao_a, camada, 1, "anx")
    oid = criado["objectId"]
    r = sessao_a.post(f"{base(camada)}/{oid}/addAttachment",
                      files={"attachment": ("ponto.png", PNG_1X1, "image/png")})
    assert r.status_code == 200, r.text
    resultado = r.json()["addAttachmentResult"]
    assert resultado["success"] is True
    numero = resultado["objectId"]

    r = sessao_a.get(f"{base(camada)}/{oid}/attachments")
    assert r.status_code == 200, r.text
    infos = r.json()["attachmentInfos"]
    assert len(infos) == 1 and infos[0]["id"] == numero and infos[0]["size"] == len(PNG_1X1)
    assert infos[0]["contentType"] == "image/png" and infos[0]["name"] == "ponto.png"

    r = sessao_a.get(f"{base(camada)}/{oid}/attachments/{numero}")
    assert r.status_code == 200, r.text
    assert hashlib.sha256(r.content).hexdigest() == hashlib.sha256(PNG_1X1).hexdigest()

    r = sessao_a.get(f"{base(camada)}/queryAttachments", params={"objectIds": str(oid)})
    assert r.status_code == 200, r.text
    grupos = r.json()["attachmentGroups"]
    assert grupos[0]["parentObjectId"] == oid and len(grupos[0]["attachmentInfos"]) == 1

    r = sessao_a.post(f"{base(camada)}/{oid}/deleteAttachments", json={"attachmentIds": str(numero)})
    assert r.status_code == 200, r.text
    assert r.json()["deleteAttachmentResults"][0]["success"] is True
    assert sessao_a.get(f"{base(camada)}/{oid}/attachments").json()["attachmentInfos"] == []


def test_update_attachment_mantem_o_mesmo_identificador(sessao_a, camada):
    [criado] = semear(sessao_a, camada, 1, "upd")
    oid = criado["objectId"]
    r = sessao_a.post(f"{base(camada)}/{oid}/addAttachment",
                      files={"attachment": ("a.png", PNG_1X1, "image/png")})
    numero = r.json()["addAttachmentResult"]["objectId"]
    outro = PNG_1X1 + b"\x00" * 8  # bytes diferentes, mesmo cabeçalho PNG
    r = sessao_a.post(f"{base(camada)}/{oid}/updateAttachment",
                      data={"attachmentId": str(numero)},
                      files={"attachment": ("b.png", outro, "image/png")})
    assert r.status_code == 200, r.text
    assert r.json()["updateAttachmentResult"]["objectId"] == numero
    lido = sessao_a.get(f"{base(camada)}/{oid}/attachments/{numero}")
    assert hashlib.sha256(lido.content).hexdigest() == hashlib.sha256(outro).hexdigest()


def test_upload_em_dois_tempos_e_anexo_por_upload_id(sessao_a, camada):
    [criado] = semear(sessao_a, camada, 1, "up2")
    r = sessao_a.post(f"/rest/services/{camada['id']}/FeatureServer/uploads/upload",
                      files={"file": ("grande.png", PNG_1X1, "image/png")})
    assert r.status_code == 200, r.text
    assert r.json()["success"] is True
    upload_id = r.json()["item"]["itemID"]

    r = sessao_a.post(f"{base(camada)}/applyEdits", json={
        "attachments": {"adds": [{"globalId": str(uuid.uuid4()), "parentGlobalId": criado["globalId"],
                                  "uploadId": upload_id, "name": "grande.png", "contentType": "image/png"}]},
    })
    assert r.status_code == 200, r.text
    assert r.json()["attachments"]["addResults"][0]["success"] is True, r.text
    infos = sessao_a.get(f"{base(camada)}/{criado['objectId']}/attachments").json()["attachmentInfos"]
    assert len(infos) == 1 and infos[0]["size"] == len(PNG_1X1)


def test_anexo_base64_dentro_do_apply_edits(sessao_a, camada):
    [criado] = semear(sessao_a, camada, 1, "b64")
    r = sessao_a.post(f"{base(camada)}/applyEdits", json={
        "attachments": {"adds": [{"parentGlobalId": criado["globalId"], "name": "em-linha.png",
                                  "contentType": "image/png",
                                  "data": base64.b64encode(PNG_1X1).decode("ascii")}]},
    })
    assert r.status_code == 200, r.text
    assert r.json()["attachments"]["addResults"][0]["success"] is True, r.text


# ---------------------------------------------------------------- cláusula 5: deleteFeatures por where
def test_delete_features_por_where(sessao_a, camada, fabrica):
    semear(sessao_a, camada, 4, "w")
    r = sessao_a.post(f"{base(camada)}/deleteFeatures", json={"where": "nome = 'w1' OR nome = 'w2'"})
    assert r.status_code == 200, r.text
    assert len(r.json()["deleteResults"]) == 2 and all(x["success"] for x in r.json()["deleteResults"])
    linhas = fabrica.linhas(camada["dados"]["schema"], camada["dados"]["tabela"],
                            camada["tenant_id"], camada["admin_id"])
    assert sorted(linha["nome"] for linha in linhas) == ["w0", "w3"]


def test_delete_features_where_malicioso_e_400(sessao_a, camada, fabrica):
    semear(sessao_a, camada, 2, "sql")
    r = sessao_a.post(f"{base(camada)}/deleteFeatures", json={"where": "1=1; DROP TABLE plat.item"})
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == 400
    assert conta(fabrica, camada) == 2


def test_add_e_update_features_separados(sessao_a, camada):
    r = sessao_a.post(f"{base(camada)}/addFeatures", json={"features": [feicao("af1"), feicao("af2")]})
    assert r.status_code == 200 and len(r.json()["addResults"]) == 2, r.text
    oid = r.json()["addResults"][0]["objectId"]
    r = sessao_a.post(f"{base(camada)}/updateFeatures",
                      json={"features": [{"attributes": {"OBJECTID": oid, "nome": "af1-editada"}}]})
    assert r.status_code == 200 and r.json()["updateResults"][0]["success"] is True, r.text


# ---------------------------------------------------------------- cláusula 6: token só-leitura = 403 Esri
def test_token_so_leitura_recebe_403_com_corpo_esri(sessao_a, cliente, camada):
    r = sessao_a.post("/api/tokens", json={"nome": "zt-l204d-ler", "escopos": ["camada:ler"]})
    assert r.status_code == 201, r.text
    tok = r.json()
    try:
        resposta = com_token(cliente, tok["token"], "POST", f"{base(camada)}/applyEdits",
                             json={"adds": [feicao("nao-entra")]})
        # a decisão do ADR: código HTTP REAL (não o 200 da Esri) E corpo no formato dela
        assert resposta.status_code == 403, resposta.text
        corpo = resposta.json()
        assert set(corpo) == {"error"}, corpo
        assert corpo["error"]["code"] == 403
        assert isinstance(corpo["error"]["message"], str) and corpo["error"]["message"]
        assert isinstance(corpo["error"]["details"], list)
    finally:
        sessao_a.delete(f"/api/tokens/{tok['id']}")


def test_token_de_edicao_escreve_pelo_mesmo_caminho(sessao_a, cliente, camada, fabrica):
    r = sessao_a.post("/api/tokens", json={"nome": "zt-l204d-editar", "escopos": ["camada:editar"]})
    assert r.status_code == 201, r.text
    tok = r.json()
    try:
        resposta = com_token(cliente, tok["token"], "POST", f"{base(camada)}/applyEdits",
                             json={"adds": [feicao("por-token")]})
        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["addResults"][0]["success"] is True
        # token também na querystring, que é como o cliente Esri costuma se ligar
        resposta = cliente.post(f"{base(camada)}/applyEdits?token={tok['token']}",
                                json={"adds": [feicao("por-querystring")]})
        assert resposta.status_code == 200, resposta.text
    finally:
        sessao_a.delete(f"/api/tokens/{tok['id']}")


# ---------------------------------------------------------------- cláusula 7: histórico com origem
def test_historico_registra_origem_featureserver(sessao_a, camada, conexao_plat_app):
    [criado] = semear(sessao_a, camada, 1, "hist")
    sessao_a.post(f"/api/camadas/{camada['id']}/edicoes",
                  json={"atualizar": [{"id": criado["globalId"], "versao": 1,
                                       "atributos": {"nome": "pela-api-da-casa"}}]})
    contexto(conexao_plat_app, camada["tenant_id"], usuario_id=camada["admin_id"], login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "SELECT operacao, origem FROM plat.feicao_historico WHERE globalid = %s::uuid ORDER BY id",
            (criado["globalId"],),
        )
        linhas = cur.fetchall()
    assert [(linha["operacao"], linha["origem"]) for linha in linhas] == [
        ("inserir", "featureserver"), ("atualizar", "api")
    ], linhas


# ---------------------------------------------------------------- calculate (sqlExpression -> L2-03-f)
def test_calculate_por_expressao_e_por_valor(sessao_a, camada, fabrica):
    semear(sessao_a, camada, 3, "calc")
    r = sessao_a.post(f"{base(camada)}/calculate", json={
        "where": "nome = 'calc1'",
        "calcExpression": [{"field": "area", "sqlExpression": "area * 3 + 1"},
                           {"field": "nome", "value": "recalculada"}],
    })
    assert r.status_code == 200, r.text
    assert r.json() == {"success": True, "updatedFeatureCount": 1}
    linhas = fabrica.linhas(camada["dados"]["schema"], camada["dados"]["tabela"],
                            camada["tenant_id"], camada["admin_id"])
    alvo = [linha for linha in linhas if linha["nome"] == "recalculada"]
    assert len(alvo) == 1 and alvo[0]["area"] == 4.0, linhas


def test_calculate_com_nome_desconhecido_e_400(sessao_a, camada):
    semear(sessao_a, camada, 1, "cx")
    r = sessao_a.post(f"{base(camada)}/calculate", json={
        "where": "1=1", "calcExpression": [{"field": "area", "sqlExpression": "pg_sleep(10)"}],
    })
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == 400


# ---------------------------------------------------------------- applyEdits do SERVIÇO
def test_apply_edits_do_servico(sessao_a, camada, fabrica):
    r = sessao_a.post(f"/rest/services/{camada['id']}/FeatureServer/applyEdits",
                      json={"edits": [{"id": 0, "adds": [feicao("svc1"), feicao("svc2")]}]})
    assert r.status_code == 200, r.text
    saida = r.json()
    assert isinstance(saida, list) and saida[0]["id"] == 0
    assert len(saida[0]["addResults"]) == 2 and all(x["success"] for x in saida[0]["addResults"])
    assert conta(fabrica, camada) == 2


def test_apply_edits_do_servico_com_camada_inexistente(sessao_a, camada):
    r = sessao_a.post(f"/rest/services/{camada['id']}/FeatureServer/applyEdits",
                      json={"edits": [{"id": 7, "adds": []}]})
    assert r.status_code == 404 and r.json()["error"]["code"] == 404, r.text


# ---------------------------------------------------------------- refutação combinada (o que o adversário manda)
def test_objectid_de_outro_inquilino_nao_entra(sessao_a, camada, camada_b, fabrica):
    """A camada do inquilino B existe, mas o pedido é feito na sessão de A contra o ITEM de B: a RLS de
    `plat.item` faz o item sumir (404), nunca escreve na tabela do outro."""
    r = sessao_a.post(f"{base(camada_b)}/applyEdits", json={"adds": [feicao("invasao")]})
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == 404
    assert conta(fabrica, camada_b) == 0


def test_globalid_repetido_no_mesmo_lote(sessao_a, camada, fabrica):
    [criado] = semear(sessao_a, camada, 1, "rep")
    corpo = {
        "useGlobalIds": True,
        "updates": [
            {"attributes": {"globalId": criado["globalId"], "nome": "primeira"}},
            {"attributes": {"globalId": criado["globalId"], "nome": "segunda"}},
        ],
    }
    r = sessao_a.post(f"{base(camada)}/applyEdits", json=corpo)
    assert r.status_code == 200, r.text
    # a segunda referência ao MESMO globalId carrega a versão lida antes da primeira escrita: a
    # concorrência otimista do L2-03-a a recusa, e com rollbackOnFailure (padrão) nada é gravado
    assert r.json()["updateResults"][1]["success"] is False, r.text
    assert r.json().get("rolledBack") is True
    linhas = fabrica.linhas(camada["dados"]["schema"], camada["dados"]["tabela"],
                            camada["tenant_id"], camada["admin_id"])
    assert [linha["nome"] for linha in linhas] == ["rep0"]


def test_geometria_em_metros_sem_spatial_reference_e_recusada(sessao_a, camada, fabrica):
    """UTM/Web Mercator mandados sem `spatialReference`: a camada é geográfica (4674), e coordenada fora
    de [-180,180]/[-90,90] não é grau em hipótese nenhuma — a validação do L2-03-a pega."""
    r = sessao_a.post(f"{base(camada)}/applyEdits", json={
        "adds": [{"attributes": {"nome": "em-metros"}, "geometry": {"x": 333_000.0, "y": 7_400_000.0}}],
        "rollbackOnFailure": False,
    })
    assert r.status_code == 200, r.text
    resultado = r.json()["addResults"][0]
    assert resultado["success"] is False, r.text
    assert "geometria_fora_do_crs" in resultado["error"]["description"], resultado
    assert conta(fabrica, camada) == 0


def test_spatial_reference_declarada_e_reprojetada(sessao_a, camada, fabrica):
    r = sessao_a.post(f"{base(camada)}/applyEdits", json={
        "adds": [{"attributes": {"nome": "web-mercator"},
                  "geometry": {"x": -5_176_000.0, "y": -2_690_000.0, "spatialReference": {"wkid": 3857}}}],
    })
    assert r.status_code == 200, r.text
    assert r.json()["addResults"][0]["success"] is True, r.text
    assert conta(fabrica, camada) == 1


def test_lote_de_cinco_mil_adds_e_recusado_inteiro(sessao_a, camada, fabrica):
    corpo = {"adds": [feicao(f"massa{i}", -46.5 + i / 100_000) for i in range(5000)]}
    r = sessao_a.post(f"{base(camada)}/applyEdits", json=corpo)
    assert r.status_code == 400, r.text[:300]
    assert r.json()["error"]["code"] == 400
    assert conta(fabrica, camada) == 0


def test_campo_inexistente_nao_vira_coluna(sessao_a, camada, fabrica):
    r = sessao_a.post(f"{base(camada)}/applyEdits", json={
        "adds": [{"attributes": {"nome": "ok", "coluna_inventada": 1}, "geometry": {"x": -46.5, "y": -23.5}}],
        "rollbackOnFailure": False,
    })
    assert r.status_code == 200, r.text
    assert r.json()["addResults"][0]["success"] is False
    assert conta(fabrica, camada) == 0


def test_forma_de_formulario_do_cliente_esri(sessao_a, camada):
    """Cliente Esri manda `application/x-www-form-urlencoded` com os vetores em JSON de texto."""
    r = sessao_a.post(f"{base(camada)}/applyEdits",
                      data={"adds": json.dumps([feicao("por-formulario")]), "f": "json"})
    assert r.status_code == 200, r.text
    assert r.json()["addResults"][0]["success"] is True
