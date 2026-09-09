"""Camada 'lacunas e sobreposições' (item L4-parcelas-03-ajuste-e-qualidade).

Portão, cláusula por cláusula:
  a) "camada 'lacunas e sobreposições' gerada para os 8.638 lotes de exemplo (contagem
     conferida com ST_Overlaps/ST_Difference independente)" ->
     test_camada_qualidade_corpo_real_de_exemplo. O 8.638 do portão é o número DE ENTÃO: a
     origem cresceu, o corpus real de hoje tem outro total (medido em 11473 no item 01) — o
     teste mede o número de HOJE, grava na medida e a diferença fica declarada, não escondida.
     A conferência independente usa PREDICADOS DIFERENTES dos da implementação: sobreposição
     decomposta pelas relações DE-9IM (ST_Overlaps/ST_Contains/ST_Equals — não o par
     ST_Intersects + ST_Intersection da implementação) e lacuna decidida por ST_Difference
     contra a união das parcelas DO REGISTRO (a implementação decide por cobertura do ponto
     sobre a superfície; o escopo é o mesmo: dentro de cada registro).
  regra de atributo (hipótese do item): área calculada x declarada e fechamento ->
     test_malha_pequena_...; a regra aponta, não altera dado.
  fachada: POST /api/parcelas/qualidade -> test_qualidade_http.

Malha pequena determinística: 8 lotes 10x10 em anel (a célula central fica SEM dono = lacuna
de 100 m²), um par de quadrados de 20 m com 17 m de transpasse (interseção de 340 m²), duas
quadras sobrepostas entre si e uma delas sobre um lote (para provar que o filtro de tipo
filtra), um lote com área declarada errada e um com erro de fechamento. Banco: inquilino demo,
GUC local à transação, fixture desfaz (padrão da suíte).
"""

import csv
import io
import subprocess

import pytest

from app.erros import ErroAPI
from app.parcelas import modelo, qualidade


def _contexto(con, tenant_id):
    with con.cursor() as cur:
        cur.execute("SET search_path = plat, public")
        cur.execute(
            "SELECT set_config('plat.tenant_id', %s, true), set_config('plat.usuario_id', %s, true), "
            "set_config('plat.login', %s, true)", (str(tenant_id), "0", "teste"))


def _anel_lote(cur, tid, registro_id, codigo, x0, y0, lado=10.0, **kwargs):
    cantos = [(x0, y0), (x0 + lado, y0), (x0 + lado, y0 + lado), (x0, y0 + lado)]
    return modelo.criar_parcela(cur, tid, tipo=kwargs.pop("tipo", "lote"), codigo=codigo,
                                registro_id=registro_id, anel=cantos, **kwargs)


def _malha_pequena(cur, tid):
    """12 lotes + 1 quadra: anel 3x3 sem o centro (lacuna), par sobreposto, quadra sobre lote,
    área declarada errada, fechamento errado. Devolve os códigos."""
    origem = modelo.criar_registro(cur, tid, codigo="QL-LTM", tipo="loteamento")
    reg = str(origem["id"])
    codigos = []
    # anel 3x3 SEM a célula do centro (1,1): o miolo fechado pelas bordas dos 8 vira lacuna
    for j in range(3):
        for i in range(3):
            if (i, j) == (1, 1):
                continue
            codigos.append(f"QL-A{i}{j}")
            _anel_lote(cur, tid, reg, f"QL-A{i}{j}", i * 10.0, j * 10.0)
    # par sobreposto longe do anel: interseção de 17 x 20 = 340 m2
    _anel_lote(cur, tid, reg, "QL-R1", 100.0, 0.0, lado=20.0)
    _anel_lote(cur, tid, reg, "QL-R2", 103.0, 0.0, lado=20.0)
    codigos += ["QL-R1", "QL-R2"]
    # regras de atributo: área declarada absurda e fechamento acima do teto (0,10 m)
    _anel_lote(cur, tid, reg, "QL-DECL", 0.0, 50.0, area_declarada_m2=999999.0)
    _anel_lote(cur, tid, reg, "QL-FECH", 20.0, 50.0, erro_fechamento_m=0.5)
    codigos += ["QL-DECL", "QL-FECH"]
    # duas quadras sobrepostas entre si (o par de sobreposição é SEMPRE do mesmo tipo) e uma
    # quadra sobre o lote QL-DECL — que NÃO é par: a comparação é dentro do tipo
    _anel_lote(cur, tid, reg, "QL-Q0", 0.0, 50.0, lado=15.0, tipo="quadra")
    _anel_lote(cur, tid, reg, "QL-Q1", 5.0, 50.0, lado=15.0, tipo="quadra")
    return reg


def test_malha_pequena_lacuna_sobreposicao_e_regras_de_atributo(conexao_plat_app, _ids):
    """Camada na malha determinística: 1 lacuna (célula central de 100 m2), 1 sobreposição de
    lote (340 m2), e as duas regras de atributo apontando — e a CONFERÊNCIA INDEPENDENTE
    (relações DE-9IM na sobreposição, ST_Difference na lacuna) bate com a camada."""
    con = conexao_plat_app
    tid = _ids["demo"]
    _contexto(con, tid)
    with con.cursor() as cur:
        _malha_pequena(cur, tid)
        camada = qualidade.camada_qualidade(cur, tenant_id=tid, tipo="lote")

    assert camada["lotes_avaliados"] == 12
    # sobreposição: 1 par de lotes, 340 m2; a quadra sobre QL-DECL não entra (filtro de tipo)
    assert camada["sobreposicoes"]["total"] == 1
    assert {camada["sobreposicoes"]["pares"][0]["a"], camada["sobreposicoes"]["pares"][0]["b"]} \
        == {"QL-R1", "QL-R2"}
    assert camada["sobreposicoes"]["area_m2"] == pytest.approx(340.0, abs=0.001)
    assert camada["sobreposicoes"]["truncado"] is False
    # sem filtro de tipo: entra o par das quadras (10 x 10 = 100 m2) e o dos lotes; a quadra
    # sobre o LOTE não é par (a comparação é dentro do tipo) — 14 lotes avaliados
    tudo = qualidade.camada_qualidade(con.cursor(), tenant_id=tid)
    assert tudo["sobreposicoes"]["total"] == 2
    assert tudo["lotes_avaliados"] == 14
    # lacuna: a célula central, 100 m2, centrada em (15, 15)
    assert camada["lacunas"]["total"] == 1
    assert camada["lacunas"]["area_m2"] == pytest.approx(100.0, abs=0.001)
    assert camada["lacunas"]["faces"][0]["centroide"].startswith("POINT(15 15)")
    # regras de atributo: 1 área declarada fora e 1 fechamento acima do teto
    assert camada["atributos"]["area_declarada_vs_calculada"]["total"] == 1
    assert camada["atributos"]["area_declarada_vs_calculada"]["desvio_maximo_m2"] \
        == pytest.approx(999899.0, abs=0.01)
    assert camada["atributos"]["fechamento"]["total"] == 1
    assert camada["atributos"]["fechamento"]["erro_maximo_m"] == pytest.approx(0.5)

    # ---- conferência INDEPENDENTE (predicados diferentes dos da implementação): a semântica
    # "interseção de área significativa" é decomposta pelas relações DE-9IM — sobreposição
    # parcial (ST_Overlaps), contenção dos dois lados (ST_Contains) e igualdade (ST_Equals) —
    # sem usar o ST_Intersects da implementação. (ST_Overlaps SOLO está ERRADO como conferência:
    # ele é FALSO quando uma parcela contém a outra, e conta lascas sem o teto de área)
    with con.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM plat.parcela a JOIN plat.parcela b"
            "  ON a.tenant_id = b.tenant_id AND a.id < b.id AND a.tipo = b.tipo"
            " AND a.ativa AND b.ativa AND a.geom && b.geom"
            " WHERE a.tenant_id = %s AND a.tipo = 'lote'"
            " AND ST_Area(ST_Intersection(a.geom, b.geom)) > 0.01"
            " AND (ST_Overlaps(a.geom, b.geom) OR ST_Contains(a.geom, b.geom)"
            "   OR ST_Contains(b.geom, a.geom) OR ST_Equals(a.geom, b.geom))", (tid,))
        assert cur.fetchone()["n"] == camada["sobreposicoes"]["total"]
        cur.execute(
            "WITH borda AS ("
            "  SELECT ST_UnaryUnion(ST_Collect(ST_Boundary(p.geom))) AS g FROM plat.parcela p"
            "   WHERE p.tenant_id = %s AND p.ativa AND p.tipo = 'lote'),"
            "faces AS (SELECT (ST_Dump(ST_Polygonize(borda.g))).geom AS g FROM borda),"
            "uniao AS (SELECT ST_UnaryUnion(ST_Collect(p.geom)) AS g FROM plat.parcela p"
            "   WHERE p.tenant_id = %s AND p.ativa AND p.tipo = 'lote')"
            "SELECT count(*) AS total, COALESCE(sum(ST_Area(f.g)), 0) AS area_m2"
            " FROM faces f CROSS JOIN uniao u"
            " WHERE ST_Area(f.g) > 0.01 AND ST_Area(ST_Difference(f.g, u.g)) > 0.01",
            (tid, tid))
        r = cur.fetchone()
    assert r["total"] == camada["lacunas"]["total"]
    assert float(r["area_m2"]) == pytest.approx(camada["lacunas"]["area_m2"], abs=0.001)


def test_qualidade_recusa_tipo_e_tolerancia_invalidos(conexao_plat_app, _ids):
    con = conexao_plat_app
    tid = _ids["demo"]
    _contexto(con, tid)
    with con.cursor() as cur:
        with pytest.raises(ErroAPI) as e:
            qualidade.camada_qualidade(cur, tenant_id=tid, tipo="chacara")
        assert e.value.erro == "tipo_invalido"
        with pytest.raises(ErroAPI) as e:
            qualidade.camada_qualidade(cur, tenant_id=tid, tolerancia_m2=0.0)
        assert e.value.erro == "valor_invalido"


# ------------------------------------------------------------------ corpo real de exemplo (portão a)


def _lotes_de_exemplo() -> list[dict]:
    """O mesmo caminho de origem do teste do item 01 (tests/api/parcelas/test_modelo.py):
    COPY de SÓ LEITURA como postgres, sem nome e sem matrícula na projeção."""
    sql = ("COPY (SELECT empreendimento_id, codigo, ST_AsText(geom) FROM sigcorp.lote "
           "ORDER BY id) TO STDOUT WITH (FORMAT csv)")
    fluxo = subprocess.run(
        ["sudo", "-u", "postgres", "psql", "-d", "iagro_sat", "-X", "-q", "-v", "ON_ERROR_STOP=1",
         "-c", sql],
        check=True, capture_output=True, text=True,
    ).stdout
    return [
        {"empreendimento_id": int(r[0]), "codigo": r[1], "wkt": r[2]}
        for r in csv.reader(io.StringIO(fluxo))
        if r and r[0]
    ]


def test_camada_qualidade_corpo_real_de_exemplo(conexao_plat_app, _ids, medida):
    """Portão (a) no corpus real: importa TODOS os lotes de exemplo (o mesmo import do item 01),
    gera a camada e confere a contagem com predicados independentes. O portão citava 8.638
    lotes — número de quando o item foi escrito; a origem cresceu (o item 01 mediu 11.473) e
    é o número de hoje que vale, com os dois declarados na medida."""
    from app.parcelas import importar

    con = conexao_plat_app
    tid = _ids["demo"]
    _contexto(con, tid)
    lotes = _lotes_de_exemplo()
    assert len(lotes) > 0, "origem sem lotes: sigcorp.lote vazia nesta máquina"
    with con.cursor() as cur:
        resumo = importar.importar_lotes(cur, tid, lotes)
        assert resumo["parcelas"] == len(lotes)
        camada = qualidade.camada_qualidade(cur, tenant_id=tid, tipo="lote")
        assert camada["lotes_avaliados"] == len(lotes)

        # conferência independente das SOBREPOSIÇÕES: a interseção significativa é decomposta
        # pelas relações DE-9IM (sobreposição parcial, contenção dos dois lados, igualdade),
        # sem o ST_Intersects da implementação; o && é só pré-filtro de bbox — sem ele o par
        # a x b é varrido cru (65 milhões de pares neste corpus), e foi isso que estourou a
        # memória do Postgres na 1ª rodada
        cur.execute(
            "SELECT count(*) AS n FROM plat.parcela a JOIN plat.parcela b"
            "  ON a.tenant_id = b.tenant_id AND a.id < b.id AND a.tipo = b.tipo"
            " AND a.ativa AND b.ativa AND a.geom && b.geom"
            " WHERE a.tenant_id = %s AND a.tipo = 'lote'"
            " AND ST_Area(ST_Intersection(a.geom, b.geom)) > 0.01"
            " AND (ST_Overlaps(a.geom, b.geom) OR ST_Contains(a.geom, b.geom)"
            "   OR ST_Contains(b.geom, a.geom) OR ST_Equals(a.geom, b.geom))", (tid,))
        sobre_independente = int(cur.fetchone()["n"])
        assert sobre_independente == camada["sobreposicoes"]["total"], (
            "contagem de sobreposição divergiu da conferência independente")

        # conferência independente das LACUNAS: mesmo escopo (faces dentro de cada registro —
        # cada registro é um levantamento), predicado diferente (ST_Difference contra a união
        # das parcelas do registro, não cobertura do ponto sobre a superfície)
        cur.execute(
            "WITH borda AS ("
            "  SELECT p.criada_por_registro AS rid,"
            "         ST_UnaryUnion(ST_Collect(ST_Boundary(p.geom))) AS g"
            "  FROM plat.parcela p"
            "   WHERE p.tenant_id = %s AND p.ativa AND p.criada_por_registro IS NOT NULL"
            "    AND p.tipo = 'lote' GROUP BY 1),"
            "faces AS (SELECT rid, (ST_Dump(ST_Polygonize(ARRAY[g]))).geom AS g FROM borda),"
            "uniao AS (SELECT p.criada_por_registro AS rid,"
            "                 ST_UnaryUnion(ST_Collect(p.geom)) AS g"
            "  FROM plat.parcela p"
            "   WHERE p.tenant_id = %s AND p.ativa AND p.criada_por_registro IS NOT NULL"
            "    AND p.tipo = 'lote' GROUP BY 1)"
            "SELECT count(*) AS total, COALESCE(sum(ST_Area(f.g)), 0) AS area_m2"
            " FROM faces f JOIN uniao u ON u.rid = f.rid"
            " WHERE ST_Area(f.g) > 0.01 AND ST_Area(ST_Difference(f.g, u.g)) > 0.01",
            (tid, tid))
        r = cur.fetchone()
    assert int(r["total"]) == camada["lacunas"]["total"], (
        "contagem de lacuna divergiu da conferência independente")
    assert float(r["area_m2"]) == pytest.approx(camada["lacunas"]["area_m2"], abs=0.5)

    medida("L4-parcelas-03-ajuste-e-qualidade")("lotes_exemplo_avaliados", len(lotes), "parcelas",
                                                "pytest tests/api/parcelas/test_qualidade.py::"
                                                "test_camada_qualidade_corpo_real_de_exemplo "
                                                "PLAT_GRAVAR_MEDIDAS=1")
    medida("L4-parcelas-03-ajuste-e-qualidade")("lotes_exemplo_sobreposicoes",
                                                camada["sobreposicoes"]["total"], "pares",
                                                "idem; conferido com relações DE-9IM independentes")
    medida("L4-parcelas-03-ajuste-e-qualidade")("lotes_exemplo_lacunas", camada["lacunas"]["total"],
                                                "faces",
                                                "idem; conferido com ST_Difference independente")


# ------------------------------------------------------------------ fachada por HTTP


@pytest.fixture
def qualidade_http(conexao_plat_app, inquilino_temporario):
    """A malha pequena semeada e COMMITADA num inquilino temporário: a fachada roda em
    transação própria (mesma precedência de test_fachada)."""
    inq = inquilino_temporario
    con = conexao_plat_app
    with con.cursor() as cur:
        cur.execute("SELECT tenant_id FROM plat.auth_login(%s, 'admin')", (inq.slug,))
        tid = cur.fetchone()["tenant_id"]
    _contexto(con, tid)
    with con.cursor() as cur:
        _malha_pequena(cur, tid)
    con.commit()
    return {"inq": inq, "con": con, "tid": tid}


def test_qualidade_http(qualidade_http):
    """POST /api/parcelas/qualidade devolve a camada na forma do módulo, com o filtro de tipo."""
    r = qualidade_http["inq"].admin.post("/api/parcelas/qualidade", json={"tipo": "lote"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["lotes_avaliados"] == 12
    assert j["sobreposicoes"]["total"] == 1
    assert j["lacunas"]["total"] == 1
    assert j["atributos"]["area_declarada_vs_calculada"]["total"] == 1
    assert j["atributos"]["fechamento"]["total"] == 1
    # tipo fora do vocabulário é recusado na porta
    r = qualidade_http["inq"].admin.post("/api/parcelas/qualidade", json={"tipo": "fazenda"})
    assert r.status_code == 422
