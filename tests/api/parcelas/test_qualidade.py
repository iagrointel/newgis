"""Camada de qualidade da malha: lacunas e sobreposições (item L4-parcelas-03-ajuste-e-qualidade).

Portão, cláusula por cláusula:
  a) "camada 'lacunas e sobreposições' gerada para os 8.638 lotes de exemplo (contagem
     conferida com ST_Overlaps/ST_Difference independente)" ->
     test_qualidade_lotes_de_exemplo_com_recontagem_independente: a malha de exemplo (lotes
     derivados do SIG de teste interno, o mesmo corpus do item 01 — hoje são mais que os
     8.638 de quando a cláusula foi escrita) entra por import, a camada roda sobre ela e a
     contagem é conferida por caminho INDEPENDENTE no SQL: pares por ST_Overlaps (o par
     recursivo da doc, sem o caminho de ST_Intersection da implementação) e faces de lacuna
     por ST_Difference contra a união das parcelas (área residual, não ponto sobre a
     superfície). Malha de exemplo sem defeito fecha em zero e zero;
     test_qualidade_aponta_defeito_sintetico_delta: sobre o MESMO inquilino com defeito
     PLANTADO (par sobreposto de propósito + anel com buraco), camada e recontagem
     independente contam o MESMO par e a MESMA lacuna;
  atributo: "regras de atributo de parcela (área calculada x declarada, fechamento)" ->
     test_regras_de_atributo_area_e_fechamento.
Refutação do item (adversário): a recontagem independente É o adversário do número da camada.

Banco: suíte conecta como o app da TRILHA (conexao_plat_app); inquilinos demo/demo2 vêm de
plat.auth_login; GUC local à transação; fixture desfaz tudo. O import do corpus de exemplo é
o mesmo caminho de leitura do teste do item 01 (COPY de só leitura como postgres).
"""

import pytest

from app.parcelas import qualidade, modelo, validacao
from app.parcelas.importar import importar_lotes
from tests.api.parcelas.test_modelo import importar_lotes_sig_origem

# ------------------------------------------------------------------ helpers (padrão test_rls)


def _contexto(con, tenant_id, login="teste"):
    with con.cursor() as cur:
        cur.execute("SET search_path = plat, public")
        cur.execute(
            "SELECT set_config('plat.tenant_id', %s, true), set_config('plat.usuario_id', %s, true), "
            "set_config('plat.login', %s, true)",
            (str(tenant_id), "0", login),
        )


@pytest.fixture
def _ids(conexao_plat_app):
    ids = {}
    with conexao_plat_app.cursor() as cur:
        for slug in ("demo", "demo2"):
            cur.execute("SELECT tenant_id FROM plat.auth_login(%s, 'admin')", (slug,))
            r = cur.fetchone()
            assert r is not None, f"admin de {slug} não semeado na trilha"
            ids[slug] = r["tenant_id"]
    return ids


# ------------------------------------------------------------------ recontagem independente


def _recontagem_independente(cur, tid, tipo=None, tolerancia_m2=validacao.TOLERANCIA_M2):
    """O caminho que NÃO é o da implementação: sobreposições por ST_Overlaps (predicado da
    referência, sem interseção explícita na contagem) e lacunas por ST_Difference (área da
    face que sobra fora da união das parcelas, sem ponto sobre a superfície)."""
    cur.execute(
        "SELECT count(*) AS n FROM plat.parcela a JOIN plat.parcela b"
        "  ON a.tenant_id = b.tenant_id AND a.tipo = b.tipo AND a.id < b.id"
        " WHERE a.tenant_id = %s AND a.ativa AND b.ativa"
        "   AND ST_Overlaps(a.geom, b.geom)"
        "   AND ST_Area(ST_Intersection(a.geom, b.geom)) > %s",
        (tid, tolerancia_m2),
    )
    sobreposicoes = int(cur.fetchone()["n"])
    cur.execute(
        "WITH faces AS ("
        "  SELECT (ST_Dump(ST_Polygonize(b.g))).geom AS g FROM ("
        "    SELECT ST_UnaryUnion(ST_Collect(ST_Boundary(p.geom))) AS g FROM plat.parcela p"
        "     WHERE p.tenant_id = %s AND p.ativa"
        "  ) b"
        "), uniao AS ("
        "  SELECT ST_UnaryUnion(ST_Collect(geom)) AS g FROM plat.parcela"
        "   WHERE tenant_id = %s AND ativa"
        ")"
        "SELECT count(*) AS n FROM faces, uniao"
        " WHERE ST_Area(ST_Difference(faces.g, uniao.g)) > %s",
        (tid, tid, tolerancia_m2),
    )
    lacunas = int(cur.fetchone()["n"])
    return {"sobreposicoes": sobreposicoes, "lacunas": lacunas}


# ------------------------------------------------------------------ portão a (malha de exemplo)


def test_qualidade_lotes_de_exemplo_com_recontagem_independente(conexao_plat_app, _ids, medida):
    """A malha de exemplo inteira (o corpus aberto da casa; 8.638 lotes quando a cláusula foi
    escrita) entra por import e a camada roda sobre ela: a contagem da camada TEM de bater com
    a recontagem independente, e uma malha derivada íntegra fecha em zero e zero."""
    con = conexao_plat_app
    tid = _ids["demo"]
    _contexto(con, tid)
    lotes = importar_lotes_sig_origem()
    assert len(lotes) >= 8638, "o corpus de exemplo encolheu abaixo do número da cláusula"
    with con.cursor() as cur:
        resumo = importar_lotes(cur, tid, lotes)
        camada = qualidade.camada_qualidade(cur, tenant_id=tid)
        independente = _recontagem_independente(cur, tid)
    assert camada["lotes_avaliados"] == resumo["parcelas"] == len(lotes)
    assert camada["sobreposicoes"]["total"] == independente["sobreposicoes"]
    assert camada["lacunas"]["total"] == independente["lacunas"]
    assert camada["lacunas"]["truncado"] == (camada["lacunas"]["total"] > len(camada["lacunas"]["faces"]))
    medida("L4-parcelas-03-ajuste-e-qualidade")("lotes_exemplo_camada_qualidade", len(lotes),
                                                "lotes",
                                                "pytest tests/api/parcelas/test_qualidade.py::"
                                                "test_qualidade_lotes_de_exemplo_com_recontagem_"
                                                "independente PLAT_GRAVAR_MEDIDAS=1")
    medida("L4-parcelas-03-ajuste-e-qualidade")("sobreposicoes_exemplo",
                                                camada["sobreposicoes"]["total"], "pares", "idem")
    medida("L4-parcelas-03-ajuste-e-qualidade")("lacunas_exemplo", camada["lacunas"]["total"],
                                                "faces", "idem")


def test_qualidade_aponta_defeito_sintetico_delta(conexao_plat_app, _ids):
    """O mesmo acordo com defeito PLANTADO: um par sobreposto de propósito (ST_Overlaps
    verdadeiro, 200 m²) e uma parcela com buraco (a face do buraco não é coberta por
    ninguém). Camada e recontagem independente contam O MESMO, e os pares apontados são os
    plantados."""
    con = conexao_plat_app
    tid = _ids["demo"]
    _contexto(con, tid)
    with con.cursor() as cur:
        reg = modelo.criar_registro(cur, tid, codigo="QLD-001", tipo="loteamento")
        modelo.criar_parcela(cur, tid, tipo="lote", codigo="QLD-A", registro_id=reg["id"],
                             anel=[(0, 0), (20, 0), (20, 20), (0, 20)])
        modelo.criar_parcela(cur, tid, tipo="lote", codigo="QLD-B", registro_id=reg["id"],
                             anel=[(10, 0), (30, 0), (30, 20), (10, 20)])  # 200 m² de A
        modelo.criar_parcela(
            cur, tid, tipo="lote", codigo="QLD-C", registro_id=reg["id"],
            wkt="POLYGON((200 200,300 200,300 300,200 300,200 200),"
                "(240 240,240 260,260 260,260 240,240 240))",
        )
        camada = qualidade.camada_qualidade(cur, tenant_id=tid)
        independente = _recontagem_independente(cur, tid)
        assert camada["sobreposicoes"]["total"] == 1 == independente["sobreposicoes"]
        assert camada["lacunas"]["total"] == 1 == independente["lacunas"]
        par = camada["sobreposicoes"]["pares"][0]
        assert {par["a"], par["b"]} == {"QLD-A", "QLD-B"}
        assert par["area_m2"] == pytest.approx(200.0, abs=1e-6)
        lacuna = camada["lacunas"]["faces"][0]
        assert lacuna["area_m2"] == pytest.approx(400.0, abs=1e-6)  # 20 m x 20 m de buraco
        # recorte por tipo: a camada de 'gleba' não vê o defeito dos lotes
        camada_gleba = qualidade.camada_qualidade(cur, tenant_id=tid, tipo="gleba")
        assert camada_gleba["lotes_avaliados"] == 0
        assert camada_gleba["sobreposicoes"]["total"] == 0


# ------------------------------------------------------------------ regras de atributo


def test_regras_de_atributo_area_e_fechamento(conexao_plat_app, _ids):
    """Área calculada x declarada fora da tolerância entra na regra de atributo; fechamento
    ruim (erro_fechamento_m acima do teto da casa, 10 cm) entra; parcela sã não entra."""
    con = conexao_plat_app
    tid = _ids["demo"]
    _contexto(con, tid)
    with con.cursor() as cur:
        reg = modelo.criar_registro(cur, tid, codigo="QLD-002", tipo="escritura")
        boa = modelo.criar_parcela(cur, tid, tipo="lote", codigo="QLD-BOA", registro_id=reg["id"],
                                   anel=[(0, 0), (20, 0), (20, 20), (0, 20)],
                                   area_declarada_m2=400.0)
        mentirosa = modelo.criar_parcela(
            cur, tid, tipo="lote", codigo="QLD-AREA", registro_id=reg["id"],
            anel=[(50, 0), (70, 0), (70, 20), (50, 20)],  # 400 m² de verdade
            area_declarada_m2=900.0,  # escritura diz 900
        )
        aberta = modelo.criar_parcela(
            cur, tid, tipo="lote", codigo="QLD-ABERTA", registro_id=reg["id"],
            anel=[(100, 0), (120, 0), (120, 20), (100, 20)],
            area_declarada_m2=400.0,
            erro_fechamento_m=1.20, erro_fechamento_razao=120.0,  # traverse que erra 1,2 m
        )
        camada = qualidade.camada_qualidade(cur, tenant_id=tid)
        area_regra = camada["atributos"]["area_declarada_vs_calculada"]
        fechamento = camada["atributos"]["fechamento"]
        assert area_regra["total"] == 1
        assert area_regra["desvio_maximo_m2"] == pytest.approx(500.0, abs=1e-6)
        assert fechamento["total"] == 1
        assert fechamento["erro_maximo_m"] == pytest.approx(1.20, abs=1e-9)
        # a boa não está em nenhuma regra: 400 calculado contra 400 declarado fecha
        assert camada["lotes_avaliados"] == 3
        assert boa["erro_fechamento_m"] is None and aberta["erro_fechamento_razao"] > 100


# ------------------------------------------------------------------ recusas de entrada


def test_qualidade_recusa_tipo_fora_do_vocabulario(conexao_plat_app, _ids):
    from app.erros import ErroAPI
    con = conexao_plat_app
    tid = _ids["demo"]
    _contexto(con, tid)
    with con.cursor() as cur, pytest.raises(ErroAPI) as e:
        qualidade.camada_qualidade(cur, tenant_id=tid, tipo="matricula")
    assert e.value.status_code == 422
