"""Fachada REST da malha de parcelas (item L4-parcelas-02-fluxos-cogo, portão f): as sete
operações do ParcelFabricServer na forma da documentação Esri, por HTTP, com inquilino
TEMPORÁRIO (zt-inq-*): o seed é commitado (a fachada roda em outra transação; mesma
precedência de tests/api/test_arquivos.py) e a limpeza é total — o inquilino inteiro é apagado
no fim, os inquilinos de demonstração nunca são tocados.

A varredura cruzada de rotas (401/403/404 por RLS em cada rota nova) é cláusula do registro
TRIPLO e vive em tests/api/cruzado_casos.py; aqui está o e2e por operação + a prova de que o
admin de OUTRO inquilino não alcança a parcela (404).
"""

import secrets
from pathlib import Path

import pytest

from app.parcelas import dxf, modelo
from tests.api.conftest import novo_cliente

RAIZ = Path(__file__).resolve().parents[3]
FABRICA = "/api/parcelas/fabrica"
DXF_SINTETICO = "\n".join([
    "0", "SECTION", "2", "ENTITIES",
    # dois retângulos adjacentes com LINE (compartilham a divisa x=10)
    "0", "LINE", "8", "LOT", "10", "0.0", "20", "0.0", "11", "10.0", "21", "0.0",
    "0", "LINE", "8", "LOT", "10", "10.0", "20", "0.0", "11", "10.0", "21", "10.0",
    "0", "LINE", "8", "LOT", "10", "10.0", "20", "10.0", "11", "0.0", "21", "10.0",
    "0", "LINE", "8", "LOT", "10", "0.0", "20", "10.0", "11", "0.0", "21", "0.0",
    "0", "LINE", "8", "LOT", "10", "10.0", "20", "0.0", "11", "20.0", "21", "0.0",
    "0", "LINE", "8", "LOT", "10", "20.0", "20", "0.0", "11", "20.0", "21", "10.0",
    "0", "LINE", "8", "LOT", "10", "20.0", "20", "10.0", "11", "10.0", "21", "10.0",
    # um terceiro retângulo, afastado, com LWPOLYLINE fechada
    "0", "LWPOLYLINE", "8", "LOT", "70", "1", "90", "4",
    "10", "50.0", "20", "50.0", "10", "60.0", "20", "50.0", "10", "60.0", "20", "60.0",
    "10", "50.0", "20", "60.0",
    "0", "ENDSEC",
]) + "\n"


def _contexto(con, tenant_id):
    with con.cursor() as cur:
        cur.execute("SET search_path = plat, public")
        cur.execute(
            "SELECT set_config('plat.tenant_id', %s, true), set_config('plat.usuario_id', %s, true), "
            "set_config('plat.login', %s, true)", (str(tenant_id), "0", "teste"),
        )


@pytest.fixture
def fabrica(conexao_plat_app, inquilino_temporario):
    """Inquilino temporário com registro + quadro de 100 m semeado e COMMITADO."""
    inq = inquilino_temporario
    con = conexao_plat_app
    with con.cursor() as cur:
        cur.execute("SELECT tenant_id FROM plat.auth_login(%s, 'admin')", (inq.slug,))
        tid = cur.fetchone()["tenant_id"]
    _contexto(con, tid)
    with con.cursor() as cur:
        reg = modelo.criar_registro(cur, tid, codigo="FB-001", tipo="desmembramento")
        # o quadro nasce por um registro DE ORIGEM (loteamento) distinto do registro da
        # operação: a casa recusa retirada pelo mesmo registro que criou (parcela_check2)
        origem = modelo.criar_registro(cur, tid, codigo="FB-LTM", tipo="loteamento")
        cantos = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
        pontos = [modelo.criar_ponto(cur, tid, x=x, y=y) for x, y in cantos]
        linhas = [modelo.criar_linha(cur, tid, de_ponto_id=pontos[i]["id"],
                                     para_ponto_id=pontos[(i + 1) % 4]["id"]) for i in range(4)]
        parcela = modelo.criar_parcela(cur, tid, tipo="lote", codigo="FB-L1",
                                       registro_id=origem["id"], anel=cantos,
                                       linha_ids=[str(ln["id"]) for ln in linhas])
        reg2 = modelo.criar_registro(cur, tid, codigo="FB-002", tipo="aprovacao")
        segs = dxf.ler(DXF_SINTETICO)
        dxf.importar(cur, tid, segmentos=segs, registro_id=reg2["id"])
    con.commit()
    return {"inq": inq, "con": con, "tid": tid, "reg": str(reg["id"]), "reg2": str(reg2["id"]),
            "parcela": str(parcela["id"])}


def _quadro_novo(fabrica, codigo, x0):
    """Segundo quadro semeado e commitado (para merge/clip por HTTP sem colidir com o primeiro)."""
    con = fabrica["con"]
    tid = fabrica["tid"]
    _contexto(con, tid)
    with con.cursor() as cur:
        origem = modelo.criar_registro(cur, tid, codigo=codigo + "-LTM", tipo="loteamento")
        cantos = [(x0, 0.0), (x0 + 100.0, 0.0), (x0 + 100.0, 100.0), (x0, 100.0)]
        pontos = [modelo.criar_ponto(cur, tid, x=x, y=y) for x, y in cantos]
        linhas = [modelo.criar_linha(cur, tid, de_ponto_id=pontos[i]["id"],
                                     para_ponto_id=pontos[(i + 1) % 4]["id"]) for i in range(4)]
        p = modelo.criar_parcela(cur, tid, tipo="lote", codigo=codigo, registro_id=origem["id"],
                                 anel=cantos, linha_ids=[str(ln["id"]) for ln in linhas])
    con.commit()
    return str(p["id"])


def test_divide_http_area_igual(fabrica):
    inq = fabrica["inq"]
    r = inq.admin.post(f"{FABRICA}/divide", json={
        "divideParcelGuid": fabrica["parcela"], "record": fabrica["reg"],
        "divideOption": "EqualArea", "divideNumberOfParts": 2, "divideLineBearing": 90,
    })
    assert r.status_code == 200, r.text
    j = r.json()
    # forma da doc: moment + exceededTransferLimit + success + serviceEdits[{id, editedFeatures}]
    assert j["success"] is True and j["exceededTransferLimit"] is False
    assert j["moment"] and j["moment"].endswith("Z")
    assert j["serviceEdits"][0]["id"] == "Parcela"
    adds = j["serviceEdits"][0]["editedFeatures"]["adds"]
    assert len(adds) == 2
    for a in adds:
        assert a["areaCalculadaM2"] == pytest.approx(5000.0, abs=0.01)
    con = fabrica["con"]
    _contexto(con, fabrica["tid"])
    with con.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM plat.parcela WHERE tenant_id = %s AND ativa "
                    "AND codigo LIKE 'FB-L1-%%'", (fabrica["tid"],))
        assert cur.fetchone()["n"] == 2
        cur.execute("SELECT ativa FROM plat.parcela WHERE id = %s::uuid", (fabrica["parcela"],))
        assert cur.fetchone()["ativa"] is False


def test_divide_http_por_linha_e_recusa(fabrica):
    inq = fabrica["inq"]
    r = inq.admin.post(f"{FABRICA}/divide", json={
        "divideParcelGuid": fabrica["parcela"], "record": fabrica["reg"],
        "linha": [[50.0, -10.0], [50.0, 110.0]],
    })
    assert r.status_code == 200, r.text
    adds = r.json()["serviceEdits"][0]["editedFeatures"]["adds"]
    assert [a["codigo"] for a in adds] == ["FB-L1-A", "FB-L1-B"]

    outro = _quadro_novo(fabrica, "FB-L2", x0=100000.0)
    r2 = inq.admin.post(f"{FABRICA}/divide", json={
        "divideParcelGuid": outro, "record": fabrica["reg"],
        "linha": [[50.0, 100150.0], [150.0, 100150.0]],
    })
    assert r2.status_code == 422
    assert r2.json()["erro"] == "linha_nao_cruza"
    con = fabrica["con"]
    _contexto(con, fabrica["tid"])
    with con.cursor() as cur:
        cur.execute("SELECT ativa FROM plat.parcela WHERE id = %s::uuid", (outro,))
        assert cur.fetchone()["ativa"] is True


def test_merge_http_mantem_externas(fabrica):
    vizinho = _quadro_novo(fabrica, "FB-V1", x0=100.0)
    inq = fabrica["inq"]
    r = inq.admin.post(f"{FABRICA}/merge", json={
        "parentParcels": [{"id": fabrica["parcela"], "layerId": "parcela"},
                          {"id": vizinho, "layerId": "parcela"}],
        "record": fabrica["reg"], "targetParcelType": "lote", "codigo": "FB-UNIDA",
    })
    assert r.status_code == 200, r.text
    adds = r.json()["serviceEdits"][0]["editedFeatures"]["adds"]
    assert len(adds) == 1 and adds[0]["codigo"] == "FB-UNIDA"
    assert adds[0]["areaCalculadaM2"] == pytest.approx(20000.0, abs=0.01)
    con = fabrica["con"]
    tid = fabrica["tid"]
    _contexto(con, tid)
    with con.cursor() as cur:
        cur.execute("SELECT id FROM plat.parcela WHERE tenant_id = %s AND codigo = 'FB-UNIDA'", (tid,))
        unida = str(cur.fetchone()["id"])
        cur.execute(
            "SELECT count(*) AS n, count(*) FILTER (WHERE l.ativa) AS ativas "
            "FROM plat.parcela_linha l JOIN plat.parcela_linha_parcela u ON u.linha_id = l.id "
            "WHERE u.parcela_id = %s::uuid", (unida,))
        rr = cur.fetchone()
        # tudo que serve à unida continua ATIVO (as externas + as linhas do DXF que jazem na
        # fronteira da união — a regra do fluxo é associar TODA linha ativa da fronteira); e a
        # divisa interna entre os dois quadros não serve à unida
        assert rr["n"] == rr["ativas"]
        cur.execute(
            "SELECT count(*) AS n FROM plat.parcela_linha_parcela u JOIN plat.parcela_linha l "
            "ON l.id = u.linha_id WHERE u.parcela_id = %s::uuid "
            "AND ST_Equals(l.geom, ST_GeomFromText('LINESTRING(100 0, 100 100)', 31982))", (unida,))
        assert cur.fetchone()["n"] == 0
        cur.execute(
            "SELECT count(*) AS n FROM plat.parcela_linha WHERE tenant_id = %s AND NOT ativa "
            "AND ST_Equals(geom, ST_GeomFromText('LINESTRING(100 0, 100 100)', 31982))", (tid,))
        assert cur.fetchone()["n"] >= 1  # a divisa interna foi retirada (nunca apagada)

    # mergeInto é recusado: a união sempre cria parcela nova (paridade §11)
    r2 = inq.admin.post(f"{FABRICA}/merge", json={
        "parentParcels": [{"id": unida, "layerId": "parcela"}], "record": fabrica["reg"],
        "mergeInto": unida,
    })
    assert r2.status_code == 422


def test_clip_http_preserva_area(fabrica):
    inq = fabrica["inq"]
    r = inq.admin.post(f"{FABRICA}/clip", json={
        "parentParcels": [{"id": fabrica["parcela"], "layerId": "parcela"}],
        "record": fabrica["reg"], "clipOption": "PreserveArea",
        "clippingGeometry": {"type": "Polygon",
                             "coordinates": [[[50.0, -5.0], [150.0, -5.0], [150.0, 50.0],
                                              [50.0, 50.0], [50.0, -5.0]]]},
    })
    assert r.status_code == 200, r.text
    adds = r.json()["serviceEdits"][0]["editedFeatures"]["adds"]
    assert len(adds) == 1 and adds[0]["areaCalculadaM2"] == pytest.approx(2500.0, abs=0.01)
    updates = r.json()["serviceEdits"][0]["editedFeatures"]["updates"]
    assert len(updates) == 1  # o pai continua (mesma feição) com o resto
    assert updates[0]["areaCalculadaM2"] == pytest.approx(7500.0, abs=0.01)


def test_sementes_http_fluxo_completo(fabrica):
    inq = fabrica["inq"]
    r = inq.admin.post(f"{FABRICA}/createSeeds", json={"record": fabrica["reg2"]})
    assert r.status_code == 200, r.text
    assert len(r.json()["serviceEdits"][0]["editedFeatures"]["adds"]) == 3

    # build NÃO cria parcela em face com semente ativa
    r2 = inq.admin.post(f"{FABRICA}/build", json={"record": fabrica["reg2"]})
    assert r2.status_code == 200, r2.text
    assert r2.json()["serviceEdits"][0]["editedFeatures"]["adds"] == []

    r3 = inq.admin.post(f"{FABRICA}/reconstructFromSeeds", json={
        "record": fabrica["reg2"], "extent": {"xmin": -1.0, "ymin": -1.0, "xmax": 70.0, "ymax": 70.0},
    })
    assert r3.status_code == 200, r.text
    assert r3.json()["reconstructedParcelCount"] == 3  # o campo da doc
    adds = r3.json()["serviceEdits"][0]["editedFeatures"]["adds"]
    assert [a["codigo"] for a in adds] == ["S-00001", "S-00002", "S-00003"]

    # build DEPOIS da reconstrução também é zero: as linhas agora têm parcela ativa
    r4 = inq.admin.post(f"{FABRICA}/build", json={"record": fabrica["reg2"]})
    assert r4.status_code == 200
    assert r4.json()["serviceEdits"][0]["editedFeatures"]["adds"] == []


def test_assign_features_to_record_http(fabrica):
    inq = fabrica["inq"]
    r = inq.admin.post(f"{FABRICA}/assignFeaturesToRecord", json={
        "parcelFeatures": [{"id": fabrica["parcela"], "layerId": "parcela"}],
        "record": fabrica["reg2"], "writeAttribute": "RetiredByRecord",
    })
    assert r.status_code == 200, r.text
    assert r.json()["success"] is True
    con = fabrica["con"]
    _contexto(con, fabrica["tid"])
    with con.cursor() as cur:
        cur.execute("SELECT ativa, retirada_por_registro FROM plat.parcela WHERE id = %s::uuid",
                    (fabrica["parcela"],))
        ln = cur.fetchone()
        assert ln["ativa"] is False
        assert str(ln["retirada_por_registro"]) == fabrica["reg2"]


def test_outro_inquilino_nao_alcanca_a_parcela(fabrica, sessao_b):
    """RLS por HTTP: o admin do demo2 chama a fachada com a parcela de OUTRO inquilino e recebe
    404 — o dado do vizinho não existe para ele, nem para dividir."""
    r = sessao_b.post(f"{FABRICA}/divide", json={
        "divideParcelGuid": fabrica["parcela"], "record": fabrica["reg"],
        "divideOption": "EqualArea", "divideNumberOfParts": 2, "divideLineBearing": 90,
    })
    assert r.status_code == 404
    assert r.json()["erro"] == "nao_encontrado"


def test_token_sem_escopo_e_recusado(fabrica, sessao_a):
    """O escopo `parcelas:usar` é o contrato de token da fachada: token com `catalogo:ler` dá
    403 escopo_insuficiente (o escopo é verificado antes de qualquer dado); token com
    `parcelas:usar` PASSA pelo escopo — e a RLS devolve 404, porque o registro semeado é de
    outro inquilino (o token é do demo, o recurso é do temporário)."""
    r_ruim = sessao_a.post("/api/tokens", json={"nome": f"zt-parc02-{secrets.token_hex(3)}",
                                                "escopos": ["catalogo:ler"]})
    assert r_ruim.status_code == 201, r_ruim.text
    r_bom = sessao_a.post("/api/tokens", json={"nome": f"zt-parc02-{secrets.token_hex(3)}",
                                               "escopos": ["parcelas:usar"]})
    assert r_bom.status_code == 201, r_bom.text
    pelado = novo_cliente()  # sem cookie: cookie + Bearer na mesma chamada é 400 autenticacao_ambigua
    try:
        ruim = {"Authorization": f"Bearer {r_ruim.json()['token']}"}
        bom = {"Authorization": f"Bearer {r_bom.json()['token']}"}
        corpo = {"record": fabrica["reg"], "extent": {"xmin": -1.0, "ymin": -1.0,
                                                      "xmax": 70.0, "ymax": 70.0}}
        resp_ruim = pelado.post(f"{FABRICA}/reconstructFromSeeds", json=corpo, headers=ruim)
        assert resp_ruim.status_code == 403
        assert resp_ruim.json()["erro"] == "escopo_insuficiente"
        resp_bom = pelado.post(f"{FABRICA}/reconstructFromSeeds", json=corpo, headers=bom)
        assert resp_bom.status_code == 404  # escopo passou; a RLS segurou o dado alheio
        assert resp_bom.json()["erro"] == "nao_encontrado"
    finally:
        sessao_a.delete(f"/api/tokens/{r_ruim.json()['id']}")
        sessao_a.delete(f"/api/tokens/{r_bom.json()['id']}")
        sessao_a.delete(f"/api/tokens/{r_bom.json()['id']}")


def test_dxf_real_fixture_esta_no_repo():
    """A fixture do dado aberto (planta de teste da casa, corpus aberto de projeto) está no
    repositório e abre: 557 segmentos, camada LOT fechando o terreno."""
    segs = dxf.ler_arquivo(RAIZ / "tests" / "api" / "parcelas" / "dados" / "planta_baixa_A01.dxf")
    assert len(segs) == 557
    lotes = [s for s in segs if s["camada"] == "LOT"]
    assert len(lotes) == 4
