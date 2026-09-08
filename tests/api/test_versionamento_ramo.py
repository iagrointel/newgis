"""Portão do item L2-13-a-versoes-ramo-reconciliar: versionamento por ramo, reconciliação, resolução de
conflito e publicação (post), pela aplicação inteira — nenhuma função é chamada por dentro.

A camada de teste é criada pela mesma `FabricaCamada` do item L2-03-a (a carga por ingestão não é o que
este arquivo testa) e depois marcada como versionada pela rota da plataforma.
"""

from __future__ import annotations

import os
import time
import uuid

import psycopg2.errors
import pytest

from tests.api.test_edicao_transacional import FabricaCamada, _admin_usuario_id
from tests.api.test_rls import contexto, ids_por_slug

SRID = 4674


@pytest.fixture
def fabrica(conexao_plat_app):
    f = FabricaCamada(conexao_plat_app)
    yield f
    f.limpar()


def _criar_camada(fabrica, *args, **kwargs):
    """`plat.camada_schema_garantir` ainda faz `GRANT USAGE ON SCHEMA` sem serialização nesta árvore
    (o trinco de aconselhamento está no ramo `wt/conc`, na fila de junção, e não em master): com várias
    trilhas construindo ao mesmo tempo na mesma máquina, o GRANT colide com `tuple concurrently
    updated`. Repetir a criação aqui evita que esta suíte meça a obra do vizinho; some sozinho quando
    aquele ramo entrar."""
    ultimo = None
    for tentativa in range(12):
        try:
            return fabrica.criar(*args, **kwargs)
        except psycopg2.errors.InternalError as e:  # noqa: PERF203
            if "concurrently updated" not in str(e):
                raise
            ultimo = e
            fabrica.con.rollback()
            time.sleep(0.4 * (tentativa + 1))
    raise ultimo


@pytest.fixture
def camada(fabrica, conexao_plat_app, sessao_a):
    ids = ids_por_slug(conexao_plat_app)
    admin_id = _admin_usuario_id(conexao_plat_app, "demo")
    item_id, dados = _criar_camada(
        fabrica, "demo", ids["demo"], admin_id,
        campos=[{"nome": "nome", "tipo": "text"}, {"nome": "area", "tipo": "double precision"}],
        geometria="Point",
    )
    r = sessao_a.post(f"/api/camadas/{item_id}/versionar", json={})
    assert r.status_code == 200, r.text
    assert r.json()["habilitado"] is True
    return {"id": item_id, "dados": dados, "tenant_id": ids["demo"], "admin_id": admin_id}


# ---------------------------------------------------------------- apoio
def _semear(sessao, camada_id, quantos=10):
    corpo = {
        "adicionar": [
            {"atributos": {"nome": f"p{i}", "area": float(i)},
             "geometria": {"type": "Point", "coordinates": [-46.5 + i / 1000, -23.5]}}
            for i in range(quantos)
        ]
    }
    r = sessao.post(f"/api/camadas/{camada_id}/edicoes", json=corpo)
    assert r.status_code == 200, r.text
    saida = r.json()["adicionar"]
    assert all(x["sucesso"] for x in saida), saida
    return saida


def _criar_ramo(sessao, camada_id, nome, acesso="protegido"):
    r = sessao.post(f"/api/camadas/{camada_id}/versoes", json={"nome": nome, "acesso": acesso})
    assert r.status_code == 201, r.text
    return r.json()


def _conta(sessao, camada_id, versao=None, momento=None):
    url = f"/rest/services/{camada_id}/FeatureServer/0/query?where=1%3D1&returnCountOnly=true&f=json"
    if versao:
        url += f"&gdbVersion={versao}"
    if momento:
        url += f"&historicMoment={momento}"
    r = sessao.get(url)
    assert r.status_code == 200, r.text
    return r.json()["count"]


def _feicoes(sessao, camada_id, versao=None, momento=None):
    url = f"/rest/services/{camada_id}/FeatureServer/0/query?where=1%3D1&outFields=*&f=json"
    if versao:
        url += f"&gdbVersion={versao}"
    if momento:
        url += f"&historicMoment={momento}"
    r = sessao.get(url)
    assert r.status_code == 200, r.text
    return {f["attributes"]["nome"]: f for f in r.json()["features"]}


def _editar_no_ramo(sessao, camada_id, versao_nome, atualizar=(), adicionar=(), apagar=()):
    corpo = {"versao": versao_nome, "atualizar": list(atualizar), "adicionar": list(adicionar),
             "apagar": list(apagar)}
    r = sessao.post(f"/api/camadas/{camada_id}/edicoes", json=corpo)
    assert r.status_code == 200, r.text
    return r.json()


def _padrao_por_globalid(sessao, camada_id, globalid):
    r = sessao.get(f"/api/camadas/{camada_id}/feicoes/{globalid}")
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- cláusula 1: conflitos exatos
def _cenario(sessao_a, sessao_outro, camada):
    """10 feições semeadas no padrão; ramo com 5 edições de atributo e 5 de geometria; outro usuário
    edita o PADRÃO em 3 delas (uma de cada tipo mais uma). Devolve o material para as asserções."""
    semeadas = _semear(sessao_a, camada["id"])
    ramo = _criar_ramo(sessao_a, camada["id"], "zt-trabalho")

    atualizar = []
    for i, f in enumerate(semeadas[:5]):
        atualizar.append({"id": f["id"], "versao": f["versao"], "atributos": {"nome": f"ramo-{i}"}})
    for i, f in enumerate(semeadas[5:], start=5):
        atualizar.append({
            "id": f["id"], "versao": f["versao"],
            "geometria": {"type": "Point", "coordinates": [-45.0 + i / 1000, -22.0]},
        })
    saida = _editar_no_ramo(sessao_a, camada["id"], ramo["nome"], atualizar=atualizar)
    assert [x["sucesso"] for x in saida["atualizar"]] == [True] * 10, saida

    # o outro usuário mexe no PADRÃO em três feições: duas de atributo (0 e 1) e uma de geometria (7)
    tocadas = [semeadas[0], semeadas[1], semeadas[7]]
    corpo = {"atualizar": [
        {"id": tocadas[0]["id"], "versao": tocadas[0]["versao"], "atributos": {"nome": "padrao-0"}},
        {"id": tocadas[1]["id"], "versao": tocadas[1]["versao"], "atributos": {"area": 999.0}},
        {"id": tocadas[2]["id"], "versao": tocadas[2]["versao"],
         "geometria": {"type": "Point", "coordinates": [-40.0, -20.0]}},
    ]}
    r = sessao_outro.post(f"/api/camadas/{camada['id']}/edicoes", json=corpo)
    assert r.status_code == 200, r.text
    assert all(x["sucesso"] for x in r.json()["atualizar"]), r.text
    return semeadas, ramo, tocadas


@pytest.fixture
def outro_editor(usuarios_a):
    cliente, usuario, _senha = usuarios_a.sessao(perfil="editor")
    return cliente, usuario


def test_reconciliar_lista_exatamente_os_tres_conflitos(sessao_a, outro_editor, camada):
    sessao_outro, _u = outro_editor
    semeadas, ramo, tocadas = _cenario(sessao_a, sessao_outro, camada)

    r = sessao_a.post(f"/api/camadas/{camada['id']}/versoes/{ramo['nome']}/reconciliar", json={})
    assert r.status_code == 200, r.text
    saida = r.json()
    assert saida["pendentes"] == 3, saida
    conflitos = {c["globalid"]: c for c in saida["conflitos"]}
    assert set(conflitos) == {t["id"] for t in tocadas}, conflitos

    # campos certos: a feição 0 mudou `nome` dos dois lados, com os três valores nomeados
    c0 = conflitos[tocadas[0]["id"]]
    assert c0["tipo"] == "atualizar-atualizar"
    assert c0["detalhe"]["atributos"]["nome"] == {
        "base": "p0", "ramo": "ramo-0", "padrao": "padrao-0", "mudou_no_ramo": True, "mudou_no_padrao": True
    }
    assert c0["detalhe"]["geometria"]["mudou_no_ramo"] is False
    assert c0["detalhe"]["geometria"]["mudou_no_padrao"] is False

    # a feição 1: o ramo mexeu em `nome`, o padrão em `area`
    c1 = conflitos[tocadas[1]["id"]]["detalhe"]["atributos"]
    assert c1["nome"]["mudou_no_ramo"] is True and c1["nome"]["mudou_no_padrao"] is False
    assert c1["area"]["mudou_no_padrao"] is True and c1["area"]["mudou_no_ramo"] is False
    assert c1["area"]["padrao"] == 999.0 and c1["area"]["base"] == 1.0

    # a feição 7: geometria dos dois lados
    g7 = conflitos[tocadas[2]["id"]]["detalhe"]["geometria"]
    assert g7["mudou_no_ramo"] is True and g7["mudou_no_padrao"] is True
    assert conflitos[tocadas[2]["id"]]["detalhe"]["atributos"] == {}

    # nenhuma das outras sete entrou na lista
    assert len(saida["conflitos"]) == 3


# ---------------------------------------------------------------- cláusula 2: resolver e publicar
def test_resolver_dois_ramo_um_manual_e_publicar(sessao_a, outro_editor, camada):
    sessao_outro, _u = outro_editor
    semeadas, ramo, tocadas = _cenario(sessao_a, sessao_outro, camada)
    base = f"/api/camadas/{camada['id']}/versoes/{ramo['nome']}"
    assert sessao_a.post(f"{base}/reconciliar", json={}).json()["pendentes"] == 3

    # publicar com conflito pendente é recusado
    r = sessao_a.post(f"{base}/publicar", json={})
    assert r.status_code == 409 and r.json()["erro"] == "conflitos_pendentes", r.text

    for t in tocadas[:2]:
        r = sessao_a.post(f"{base}/conflitos/{t['id']}/resolver", json={"decisao": "ramo"})
        assert r.status_code == 200, r.text
    r = sessao_a.post(
        f"{base}/conflitos/{tocadas[2]['id']}/resolver",
        json={"decisao": "manual", "atributos": {"nome": "decidido-a-mao", "area": 7.0},
              "geometria": {"type": "Point", "coordinates": [-44.0, -21.0]}},
    )
    assert r.status_code == 200, r.text

    r = sessao_a.post(f"{base}/publicar", json={})
    assert r.status_code == 200, r.text
    assert r.json()["atualizada"] == 10, r.json()

    # padrão campo a campo
    padrao = _feicoes(sessao_a, camada["id"])
    assert len(padrao) == 10
    # os 5 de atributo do ramo venceram (inclusive os dois resolvidos como "ramo vence")
    for i in range(5):
        assert f"ramo-{i}" in padrao, sorted(padrao)
    # a feição 1 mantém a `area` do ramo (que era a de base, 1.0): "ramo vence" descarta os 999 do padrão
    assert padrao["ramo-1"]["attributes"]["area"] == 1.0
    # a feição 7 ficou com o que a resolução manual escolheu
    assert "decidido-a-mao" in padrao
    manual = padrao["decidido-a-mao"]["attributes"]
    assert manual["area"] == 7.0
    p7 = _padrao_por_globalid(sessao_a, camada["id"], tocadas[2]["id"])
    assert [round(c, 6) for c in p7["geometria"]["coordinates"]] == [-44.0, -21.0]
    # as feições 5,6,8,9 ficaram com a geometria movida pelo ramo
    p5 = _padrao_por_globalid(sessao_a, camada["id"], semeadas[5]["id"])
    assert round(p5["geometria"]["coordinates"][1], 6) == -22.0

    # ramo fechado
    r = sessao_a.get(f"/api/camadas/{camada['id']}/versoes/{ramo['nome']}")
    assert r.status_code == 200 and r.json()["estado"] == "publicada", r.text


# ---------------------------------------------------------------- cláusula 3: não vaza nos dois sentidos
def test_leitura_no_ramo_nao_vaza_para_o_padrao_nem_o_contrario(sessao_a, camada):
    semeadas = _semear(sessao_a, camada["id"])
    ramo = _criar_ramo(sessao_a, camada["id"], "zt-isolado")

    _editar_no_ramo(
        sessao_a, camada["id"], ramo["nome"],
        adicionar=[{"atributos": {"nome": "so-no-ramo", "area": 1.0},
                    "geometria": {"type": "Point", "coordinates": [-46.0, -23.0]}},
                   {"atributos": {"nome": "so-no-ramo-2", "area": 2.0},
                    "geometria": {"type": "Point", "coordinates": [-46.1, -23.1]}}],
        apagar=[{"id": semeadas[9]["id"]}],
        atualizar=[{"id": semeadas[0]["id"], "versao": semeadas[0]["versao"],
                    "atributos": {"nome": "mudado-no-ramo"}}],
    )
    # padrão: 10, sem nada do ramo
    padrao = _feicoes(sessao_a, camada["id"])
    assert _conta(sessao_a, camada["id"]) == 10
    assert "so-no-ramo" not in padrao and "mudado-no-ramo" not in padrao and "p0" in padrao and "p9" in padrao
    # ramo: 10 + 2 - 1 = 11, com as mudanças dele
    no_ramo = _feicoes(sessao_a, camada["id"], versao=ramo["nome"])
    assert _conta(sessao_a, camada["id"], versao=ramo["nome"]) == 11
    assert "so-no-ramo" in no_ramo and "so-no-ramo-2" in no_ramo
    assert "mudado-no-ramo" in no_ramo and "p0" not in no_ramo and "p9" not in no_ramo

    # e o contrário: uma edição feita no PADRÃO depois do ramo não aparece no ramo
    r = sessao_a.post(
        f"/api/camadas/{camada['id']}/edicoes",
        json={"atualizar": [{"id": semeadas[3]["id"], "versao": semeadas[3]["versao"],
                             "atributos": {"nome": "so-no-padrao"}}]},
    )
    assert r.status_code == 200, r.text
    assert "so-no-padrao" in _feicoes(sessao_a, camada["id"])
    depois = _feicoes(sessao_a, camada["id"], versao=ramo["nome"])
    assert "so-no-padrao" not in depois and "p3" in depois

    # depois de reconciliar (sem conflito: o ramo não tocou a feição 3) o ramo passa a ver o padrão
    r = sessao_a.post(f"/api/camadas/{camada['id']}/versoes/{ramo['nome']}/reconciliar", json={})
    assert r.status_code == 200 and r.json()["pendentes"] == 0, r.text
    assert "so-no-padrao" in _feicoes(sessao_a, camada["id"], versao=ramo["nome"])


# ---------------------------------------------------------------- cláusula 4: historicMoment
def test_historic_moment_devolve_o_estado_anterior(sessao_a, camada):
    semeadas = _semear(sessao_a, camada["id"], quantos=3)
    time.sleep(0.05)
    antes_ms = int(time.time() * 1000)
    time.sleep(0.05)
    r = sessao_a.post(
        f"/api/camadas/{camada['id']}/edicoes",
        json={
            "atualizar": [{"id": semeadas[0]["id"], "versao": semeadas[0]["versao"],
                           "atributos": {"nome": "depois"},
                           "geometria": {"type": "Point", "coordinates": [-30.0, -10.0]}}],
            "apagar": [{"id": semeadas[2]["id"]}],
        },
    )
    assert r.status_code == 200, r.text

    agora = _feicoes(sessao_a, camada["id"])
    assert set(agora) == {"depois", "p1"}
    assert _conta(sessao_a, camada["id"]) == 2

    antes = _feicoes(sessao_a, camada["id"], momento=antes_ms)
    assert set(antes) == {"p0", "p1", "p2"}, sorted(antes)
    assert _conta(sessao_a, camada["id"], momento=antes_ms) == 3
    # a geometria também volta ao que era (a feição 0 estava perto de -46,5 / -23,5)
    assert round(antes["p0"]["geometry"]["x"], 3) == -46.5
    # e a apagada volta inteira, com os atributos que tinha
    assert antes["p2"]["attributes"]["area"] == 2.0


# ---------------------------------------------------------------- refutação: dois ramos, mesma feição
def test_dois_ramos_editam_a_mesma_feicao(sessao_a, camada):
    """Refutação do item-pai adaptada: o segundo ramo a publicar encontra o padrão já mudado pelo
    primeiro, e a publicação dele é recusada até haver decisão."""
    semeadas = _semear(sessao_a, camada["id"], quantos=3)
    r1 = _criar_ramo(sessao_a, camada["id"], "zt-ramo-1", acesso="publico")
    r2 = _criar_ramo(sessao_a, camada["id"], "zt-ramo-2", acesso="publico")
    alvo = semeadas[0]
    for nome_ramo, valor in ((r1["nome"], "de-um"), (r2["nome"], "de-dois")):
        _editar_no_ramo(
            sessao_a, camada["id"], nome_ramo,
            atualizar=[{"id": alvo["id"], "versao": alvo["versao"], "atributos": {"nome": valor}}],
        )
    # cada ramo vê só a sua versão
    assert "de-um" in _feicoes(sessao_a, camada["id"], versao=r1["nome"])
    assert "de-um" not in _feicoes(sessao_a, camada["id"], versao=r2["nome"])

    b1 = f"/api/camadas/{camada['id']}/versoes/{r1['nome']}"
    b2 = f"/api/camadas/{camada['id']}/versoes/{r2['nome']}"
    assert sessao_a.post(f"{b1}/publicar", json={}).status_code == 200
    assert "de-um" in _feicoes(sessao_a, camada["id"])

    r = sessao_a.post(f"{b2}/publicar", json={})
    assert r.status_code == 409 and r.json()["erro"] == "conflitos_pendentes", r.text
    # a recusa já traz a lista (a transação recusada não deixa nada gravado)
    assert r.json()["detalhe"]["pendentes"] == [alvo["id"]], r.text
    # e reconciliar grava a lista para consulta
    assert sessao_a.post(f"{b2}/reconciliar", json={}).json()["pendentes"] == 1
    conflitos = sessao_a.get(f"{b2}/conflitos").json()["conflitos"]
    assert len(conflitos) == 1 and conflitos[0]["globalid"] == alvo["id"]
    assert conflitos[0]["detalhe"]["atributos"]["nome"]["padrao"] == "de-um"

    assert sessao_a.post(f"{b2}/conflitos/{alvo['id']}/resolver", json={"decisao": "ramo"}).status_code == 200
    assert sessao_a.post(f"{b2}/publicar", json={}).status_code == 200
    assert "de-dois" in _feicoes(sessao_a, camada["id"])


def test_publicar_ramo_cujo_pai_ja_foi_publicado(sessao_a, camada):
    """Refutação: publicar duas vezes o mesmo ramo, e publicar um ramo já fechado."""
    semeadas = _semear(sessao_a, camada["id"], quantos=2)
    ramo = _criar_ramo(sessao_a, camada["id"], "zt-uma-vez")
    _editar_no_ramo(
        sessao_a, camada["id"], ramo["nome"],
        atualizar=[{"id": semeadas[0]["id"], "versao": semeadas[0]["versao"], "atributos": {"nome": "x"}}],
    )
    base = f"/api/camadas/{camada['id']}/versoes/{ramo['nome']}"
    assert sessao_a.post(f"{base}/publicar", json={}).status_code == 200
    r = sessao_a.post(f"{base}/publicar", json={})
    assert r.status_code == 409 and r.json()["erro"] == "versao_fechada", r.text
    r = sessao_a.post(f"{base}/reconciliar", json={})
    assert r.status_code == 409 and r.json()["erro"] == "versao_fechada", r.text
    # e editar dentro de ramo publicado também é recusado
    r = sessao_a.post(
        f"/api/camadas/{camada['id']}/edicoes",
        json={"versao": ramo["nome"], "adicionar": [
            {"atributos": {"nome": "tarde"}, "geometria": {"type": "Point", "coordinates": [-46.0, -23.0]}}]},
    )
    assert r.status_code == 409 and r.json()["erro"] == "versao_fechada", r.text


def test_apagar_ramo_com_edicoes_descarta_tudo(sessao_a, camada):
    """Refutação: apagar ramo com edições não pode encostar no padrão."""
    semeadas = _semear(sessao_a, camada["id"], quantos=3)
    ramo = _criar_ramo(sessao_a, camada["id"], "zt-descartavel")
    _editar_no_ramo(
        sessao_a, camada["id"], ramo["nome"],
        atualizar=[{"id": semeadas[0]["id"], "versao": semeadas[0]["versao"], "atributos": {"nome": "some"}}],
        adicionar=[{"atributos": {"nome": "nasce-e-morre"},
                    "geometria": {"type": "Point", "coordinates": [-46.0, -23.0]}}],
    )
    assert _conta(sessao_a, camada["id"], versao=ramo["nome"]) == 4
    r = sessao_a.delete(f"/api/camadas/{camada['id']}/versoes/{ramo['nome']}")
    assert r.status_code == 200 and r.json()["linhas_descartadas"] == 2, r.text
    padrao = _feicoes(sessao_a, camada["id"])
    assert set(padrao) == {"p0", "p1", "p2"}
    # e o ramo some da listagem e da leitura
    assert [v["nome"] for v in sessao_a.get(f"/api/camadas/{camada['id']}/versoes").json()] == []
    r = sessao_a.get(
        f"/rest/services/{camada['id']}/FeatureServer/0/query"
        f"?where=1%3D1&f=json&gdbVersion={ramo['nome']}"
    )
    assert r.status_code == 404, r.text


def test_ramo_privado_de_outro_usuario_nao_e_legivel(sessao_a, outro_editor, camada):
    """Refutação: ler (e escrever) o ramo privado de outro usuário."""
    sessao_outro, _u = outro_editor
    _semear(sessao_a, camada["id"], quantos=2)
    privado = _criar_ramo(sessao_a, camada["id"], "zt-privado", acesso="privado")
    protegido = _criar_ramo(sessao_a, camada["id"], "zt-protegido", acesso="protegido")

    assert sessao_outro.get(f"/api/camadas/{camada['id']}/versoes/{privado['nome']}").status_code == 404
    assert [v["nome"] for v in sessao_outro.get(f"/api/camadas/{camada['id']}/versoes").json()] == [
        protegido["nome"]
    ]
    r = sessao_outro.get(
        f"/rest/services/{camada['id']}/FeatureServer/0/query"
        f"?where=1%3D1&f=json&gdbVersion={privado['nome']}"
    )
    assert r.status_code == 404, r.text
    r = sessao_outro.post(
        f"/api/camadas/{camada['id']}/edicoes",
        json={"versao": privado["nome"], "adicionar": [
            {"atributos": {"nome": "invasor"}, "geometria": {"type": "Point", "coordinates": [-46.0, -23.0]}}]},
    )
    assert r.status_code == 404, r.text
    # protegido: lê, mas não escreve
    assert sessao_outro.get(f"/api/camadas/{camada['id']}/versoes/{protegido['nome']}").status_code == 200
    r = sessao_outro.post(f"/api/camadas/{camada['id']}/versoes/{protegido['nome']}/reconciliar", json={})
    assert r.status_code == 403 and r.json()["erro"] == "versao_protegida", r.text


# ---------------------------------------------------------------- VersionManagementServer
def test_version_management_server_ciclo_completo(sessao_a, camada):
    semeadas = _semear(sessao_a, camada["id"], quantos=3)
    vms = f"/rest/services/{camada['id']}/VersionManagementServer"

    r = sessao_a.get(f"{vms}?f=json")
    assert r.status_code == 200 and r.json()["defaultVersionName"] == "sde.DEFAULT", r.text

    r = sessao_a.post(f"{vms}/create", json={"versionName": "zt-esri", "accessPermission": "public"})
    assert r.status_code == 200, r.text
    info = r.json()["versionInfo"]
    guid = info["versionGuid"]
    assert guid.startswith("{") and guid.endswith("}") and uuid.UUID(guid.strip("{}"))
    assert info["access"] == "public"

    nomes = [v["versionName"] for v in sessao_a.get(f"{vms}/versions").json()["versions"]]
    assert nomes == ["sde.DEFAULT", "zt-esri"], nomes

    # sessões do protocolo (o cliente da Esri as chama antes de reconciliar)
    for passo in ("startReading", "startEditing", "stopEditing", "stopReading"):
        r = sessao_a.post(f"{vms}/{guid}/{passo}", json={"sessionId": "{ABC}"})
        assert r.status_code == 200 and r.json()["success"] is True, (passo, r.text)
        assert r.json()["sessionId"] == "{ABC}"

    # edição no ramo pelo applyEdits com gdbVersion
    r = sessao_a.post(
        f"/rest/services/{camada['id']}/FeatureServer/0/applyEdits",
        json={"gdbVersion": "zt-esri",
              "updates": [{"attributes": {"OBJECTID": semeadas[0]["fid"], "nome": "pelo-esri"}}]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["updateResults"][0]["success"] is True, r.text
    assert "pelo-esri" in _feicoes(sessao_a, camada["id"], versao="zt-esri")
    assert "pelo-esri" not in _feicoes(sessao_a, camada["id"])

    r = sessao_a.post(f"{vms}/{guid}/reconcile", json={})
    assert r.status_code == 200 and r.json()["hasConflicts"] is False, r.text
    assert sessao_a.post(f"{vms}/{guid}/conflicts").json()["conflicts"] == []
    r = sessao_a.post(f"{vms}/{guid}/post", json={})
    assert r.status_code == 200 and r.json()["success"] is True, r.text
    assert "pelo-esri" in _feicoes(sessao_a, camada["id"])


def test_version_management_server_apagar(sessao_a, camada):
    _semear(sessao_a, camada["id"], quantos=1)
    vms = f"/rest/services/{camada['id']}/VersionManagementServer"
    guid = sessao_a.post(f"{vms}/create", json={"versionName": "zt-some"}).json()["versionInfo"]["versionGuid"]
    r = sessao_a.post(f"{vms}/{guid}/delete", json={})
    assert r.status_code == 200 and r.json()["success"] is True, r.text
    assert [v["versionName"] for v in sessao_a.get(f"{vms}/versions").json()["versions"]] == ["sde.DEFAULT"]


# ---------------------------------------------------------------- limite declarado e camada não versionada
def test_teto_de_ramos_declarado(sessao_a, camada):
    r = sessao_a.post(f"/api/camadas/{camada['id']}/versionar", json={"ramos_max": 2})
    assert r.status_code == 200 and r.json()["ramos_max"] == 2, r.text
    _criar_ramo(sessao_a, camada["id"], "zt-a")
    _criar_ramo(sessao_a, camada["id"], "zt-b")
    r = sessao_a.post(f"/api/camadas/{camada['id']}/versoes", json={"nome": "zt-c"})
    assert r.status_code == 409 and r.json()["erro"] == "ramos_demais", r.text
    assert r.json()["detalhe"]["maximo"] == 2


def test_camada_sem_versionamento_recusa_gdbversion(sessao_a, fabrica, conexao_plat_app):
    ids = ids_por_slug(conexao_plat_app)
    admin_id = _admin_usuario_id(conexao_plat_app, "demo")
    item_id, _dados = _criar_camada(
        fabrica, "demo", ids["demo"], admin_id, campos=[{"nome": "nome", "tipo": "text"}], geometria="Point"
    )
    r = sessao_a.get(
        f"/rest/services/{item_id}/FeatureServer/0/query?where=1%3D1&f=json&gdbVersion=qualquer"
    )
    assert r.status_code == 422 and r.json()["erro"] == "gdbversion_fora", r.text
    r = sessao_a.get(f"/api/camadas/{item_id}/versoes")
    assert r.status_code == 409 and r.json()["erro"] == "camada_nao_versionada", r.text
    # SDE.DEFAULT continua aceito em camada não versionada (é o padrão do protocolo)
    r = sessao_a.get(
        f"/rest/services/{item_id}/FeatureServer/0/query"
        "?where=1%3D1&f=json&gdbVersion=SDE.DEFAULT&returnCountOnly=true"
    )
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------- medida de desempenho
@pytest.mark.skipif(
    os.environ.get("PLAT_MEDIR_RECONCILIAR") != "1",
    reason="medida de reconciliação com 10 mil edições: só sob PLAT_MEDIR_RECONCILIAR=1 (leva minutos)",
)
def test_medida_reconciliar_10_mil_edicoes(sessao_a, camada, medida):
    grava = medida("L2-13-a-versoes-ramo-reconciliar")
    total = 10_000
    passo = 500
    semeadas = []
    for inicio in range(0, total, passo):
        corpo = {"adicionar": [
            {"atributos": {"nome": f"p{i}", "area": float(i)},
             "geometria": {"type": "Point", "coordinates": [-46.5 + i / 100000, -23.5]}}
            for i in range(inicio, inicio + passo)
        ]}
        r = sessao_a.post(f"/api/camadas/{camada['id']}/edicoes", json=corpo)
        assert r.status_code == 200, r.text
        semeadas += r.json()["adicionar"]
    ramo = _criar_ramo(sessao_a, camada["id"], "zt-grande")
    for inicio in range(0, total, passo):
        lote = semeadas[inicio:inicio + passo]
        _editar_no_ramo(
            sessao_a, camada["id"], ramo["nome"],
            atualizar=[{"id": f["id"], "versao": f["versao"], "atributos": {"nome": "r"}} for f in lote],
        )
    carga = os.getloadavg()[0]
    disponivel = [li for li in open("/proc/meminfo", encoding="utf-8") if li.startswith("MemAvailable")]
    livre_gb = round(int(disponivel[0].split()[1]) / 1024 / 1024, 2) if disponivel else -1.0
    inicio = time.monotonic()
    r = sessao_a.post(f"/api/camadas/{camada['id']}/versoes/{ramo['nome']}/reconciliar", json={})
    segundos = time.monotonic() - inicio
    assert r.status_code == 200, r.text
    grava(
        "reconciliar_10k_edicoes_s", round(segundos, 2), "segundos",
        "PLAT_MEDIR_RECONCILIAR=1 bash /home/dev/plataforma/laco/roda_teste.sh "
        "tests/api/test_versionamento_ramo.py::test_medida_reconciliar_10_mil_edicoes -q",
    )
    grava("carga_1min", round(carga, 2), "media de carga de 1 min", "uptime")
    grava("ram_livre_gb", livre_gb, "GiB", "free -g")
    grava("edicoes_no_ramo", total, "feições editadas no ramo", "-")
