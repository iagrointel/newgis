"""Fluxos de edição da malha de parcelas (item L4-parcelas-02-fluxos-cogo).

Portão, cláusula por cláusula:
  b) "traverse de 6 lados com erro de fechamento calculado e exibido (teste com poligonal
     conhecida: erro = valor esperado ± 1 mm)" -> test_traverse_6_lados_erro_conhecido;
  c) "dividir lote em 2 por área igual devolve áreas iguais ± 0,01 m²" ->
     test_dividir_area_igual_desvio_maximo (e as outras opções de divide em
     test_dividir_proporcional_largura_e_diagonal);
  d) "unir mantém linhas externas e apaga a interna" -> test_unir_mantem_externas_e_apaga_interna
     (na casa "apaga" é RETIRADA — registro + ativa=false; a casa nunca dá DELETE, paridade §11);
  e) "build a partir de linhas de DXF importado (dado aberto) gera N parcelas fechadas
     (contagem)" -> test_build_a_partir_de_dxf_real (planta de teste da casa, corpus aberto de
     projeto — fixture tests/api/parcelas/dados/planta_baixa_A01.dxf) e
     test_build_dxf_sintetico_gera_tres_faces;
  f) "fachada REST ParcelFabricServer mapeada com forma da doc" -> tests/api/parcelas/
     test_fachada.py (HTTP, inquilino temporário); a paridade operação por operação está em
     docs/PARIDADE_PARCELAS.md §11;
  g) "paridade escrita" -> test_paridade_secao_11_e_12.
Refutação: "adversário divide parcela com linha que não cruza e confere recusa" ->
  test_dividir_por_linha_que_nao_cruza_e_recusada; "traverse que não fecha por 5 m e confere
  que o sistema mostra o erro e não fecha em silêncio" -> test_traverse_que_nao_fecha_mostra_o_erro.

Banco: suíte conecta como o app da TRILHA (conexao_plat_app); inquilinos demo/demo2 vêm de
plat.auth_login (padrão tests/api/test_rls.py); GUC local à transação; fixture desfaz tudo.
"""

import math
from pathlib import Path

import pytest

from app import limites
from app.erros import ErroAPI
from app.parcelas import cogo, dxf, fluxos, modelo

RAIZ = Path(__file__).resolve().parents[3]


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


def _quadro_com_linhas(cur, tid, codigo, x0=0.0, y0=0.0, lado=100.0):
    """Lote quadrado com os 4 pontos e as 4 linhas de limite criados e associados — é o que
    unir/recortar precisam para mostrar o destino das linhas. A quadra nasce por um registro
    de ORIGEM próprio (loteamento), distinto do registro que cada teste passa à operação: a
    casa recusa retirada pelo mesmo registro que criou (parcela_check2 do item 01)."""
    origem = modelo.criar_registro(cur, tid, codigo=codigo + "-LTM", tipo="loteamento")
    cantos = [(x0, y0), (x0 + lado, y0), (x0 + lado, y0 + lado), (x0, y0 + lado)]
    pontos = [modelo.criar_ponto(cur, tid, x=x, y=y) for x, y in cantos]
    linhas = [modelo.criar_linha(cur, tid, de_ponto_id=pontos[i]["id"],
                                 para_ponto_id=pontos[(i + 1) % 4]["id"]) for i in range(4)]
    parcela = modelo.criar_parcela(cur, tid, tipo="lote", codigo=codigo, registro_id=origem["id"],
                                   anel=cantos, linha_ids=[str(ln["id"]) for ln in linhas])
    return parcela, linhas


def _ativa(cur, tid, parcela_id) -> bool:
    cur.execute("SELECT ativa FROM plat.parcela WHERE id = %s::uuid AND tenant_id = %s",
                (str(parcela_id), tid))
    return bool(cur.fetchone()["ativa"])


# ------------------------------------------------------------------ traverse COGO (portão b + refutação)


TRAJETO_6_LADOS = [(0, 100), (90, 100), (180, 50), (180, 50), (270, 99), (0, 1)]
# (0,0) -> (0,100) -> (100,100) -> (100,50) -> (100,0) -> (1,0) -> (1,1): fecha a 1 mm de
# (1,1), erro = raiz de 2, perímetro 400, razão 400/raiz de 2.


def test_traverse_6_lados_erro_conhecido(conexao_plat_app, _ids):
    """Portão b: a poligonal conhecida fecha com erro RAIZ DE 2 m (± 1 mm), calculado E
    devolvido na criação e gravado na parcela — o erro é exibido, nunca escondido."""
    r = cogo.caminhar((0.0, 0.0), TRAJETO_6_LADOS)
    assert r["fechamento_m"] == pytest.approx(math.sqrt(2), abs=0.001)  # ± 1 mm
    assert r["perimetro_m"] == pytest.approx(400.0, abs=1e-9)
    assert r["razao"] == pytest.approx(400.0 / math.sqrt(2), abs=0.01)
    con = conexao_plat_app
    tid = _ids["demo"]
    _contexto(con, tid)
    with con.cursor() as cur:
        reg = modelo.criar_registro(cur, tid, codigo="TR-001", tipo="outro")
        p0 = modelo.criar_ponto(cur, tid, x=0.0, y=0.0, nome="V-0", fixo=True, registro_id=reg["id"])
        parcela = cogo.criar_parcela_cogo(
            cur, tid, registro_id=reg["id"], ponto_inicial_id=p0["id"], codigo="P-TR-1",
            tipo="lote", trajeto=TRAJETO_6_LADOS,
        )
        # exibido: vem na resposta da criação E fica na linha da parcela
        assert float(parcela["erro_fechamento_m"]) == pytest.approx(math.sqrt(2), abs=0.001)
        assert float(parcela["erro_fechamento_razao"]) == pytest.approx(400.0 / math.sqrt(2), abs=0.01)
        cur.execute("SELECT erro_fechamento_m, erro_fechamento_razao FROM plat.parcela "
                    "WHERE id = %s::uuid", (str(parcela["id"]),))
        linha = cur.fetchone()
        assert float(linha["erro_fechamento_m"]) == pytest.approx(math.sqrt(2), abs=0.001)
        assert float(linha["erro_fechamento_razao"]) == pytest.approx(400.0 / math.sqrt(2), abs=0.01)


def test_traverse_que_nao_fecha_mostra_o_erro(conexao_plat_app, _ids):
    """Refutação: traverse que erra 5 m NÃO fecha em silêncio — a parcela nasce com o erro de
    5,000 m e a razão 405/5 = 81 declarados na ficha, e a geometria não é esticada para fechar."""
    trajeto = [(0, 100), (90, 100), (180, 50), (180, 50), (270, 100), (90, 5)]
    r = cogo.caminhar((0.0, 0.0), trajeto)
    assert r["fechamento_m"] == pytest.approx(5.0, abs=0.001)  # ± 1 mm
    assert r["razao"] == pytest.approx(81.0, abs=0.001)
    con = conexao_plat_app
    tid = _ids["demo"]
    _contexto(con, tid)
    with con.cursor() as cur:
        reg = modelo.criar_registro(cur, tid, codigo="TR-002", tipo="outro")
        p0 = modelo.criar_ponto(cur, tid, x=0.0, y=0.0, nome="V-0", fixo=True, registro_id=reg["id"])
        parcela = cogo.criar_parcela_cogo(
            cur, tid, registro_id=reg["id"], ponto_inicial_id=p0["id"], codigo="P-TR-2",
            tipo="lote", trajeto=trajeto,
        )
        assert float(parcela["erro_fechamento_m"]) == pytest.approx(5.0, abs=0.001)
        assert float(parcela["erro_fechamento_razao"]) == pytest.approx(81.0, abs=0.001)
        # o anel guarda a chegada real perto de (5,0) E o início em (0,0): nada foi esticado
        # nem encaixado para fechar bonito (a asserção varre os vértices — o ponto em que o
        # anel começa no ST_Boundary é escolha do PostGIS, e o 270° deixa ruído de 1e-14)
        cur.execute(
            "SELECT ST_NumPoints(ST_Boundary(geom)) AS n, "
            "ST_AsText((ST_DumpPoints(ST_Boundary(geom))).geom) AS p "
            "FROM plat.parcela WHERE id = %s::uuid",
            (str(parcela["id"]),),
        )
        linhas = cur.fetchall()
        n = linhas[0]["n"]
        pontos = []
        for ln in linhas:
            x_txt, y_txt = ln["p"][len("POINT("):-1].split()
            pontos.append((float(x_txt), float(y_txt)))
        assert n == 8  # 7 vértices distintos (6 do trajeto + a chegada real) + o fechamento
        assert any(pytest.approx((5.0, 0.0), abs=1e-6) == p for p in pontos)
        assert any(pytest.approx((0.0, 0.0), abs=1e-6) == p for p in pontos)
        # a aresta de fechamento (do chegada de volta ao início) não finge ser medida
        cur.execute(
            "SELECT count(*) AS n FROM plat.parcela_linha l JOIN plat.parcela_linha_parcela a "
            "ON a.linha_id = l.id WHERE a.parcela_id = %s::uuid AND l.rumo_graus IS NULL "
            "AND l.distancia_m IS NULL",
            (str(parcela["id"]),),
        )
        assert cur.fetchone()["n"] == 1
        ficha = modelo.ficha(cur, tid, parcela["id"])
        assert ficha["ativa"] is True  # quem decide se o erro é aceitável é quem criou


# ------------------------------------------------------------------ dividir (portão c + refutação a)


def test_dividir_area_igual_desvio_maximo(conexao_plat_app, _ids):
    """Portão c: dividir lote de 10.000 m² em 2 por área igual devolve duas partes com áreas
    iguais dentro de ± 0,01 m²; a original sai do atual e as partes entram."""
    con = conexao_plat_app
    tid = _ids["demo"]
    _contexto(con, tid)
    with con.cursor() as cur:
        reg = modelo.criar_registro(cur, tid, codigo="DV-001", tipo="desmembramento")
        pai, _ = _quadro_com_linhas(cur, tid, "QL-1")
        partes = fluxos.dividir(cur, tid, parcela_id=pai["id"], registro_id=reg["id"],
                                rumo_graus=90, opcao="EqualArea", numero_de_partes=2)
        assert len(partes) == 2
        areas = [float(p["area_calculada_m2"]) for p in partes]
        for a in areas:
            assert a == pytest.approx(5000.0, abs=0.01)  # a tolerância do portão
        assert abs(areas[0] - areas[1]) <= 0.01
        for p in partes:
            assert float(p["area_declarada_m2"]) == pytest.approx(5000.0, abs=0.01)
            assert p["atributos"]["fluxo"] == "divide"
        assert _ativa(cur, tid, pai["id"]) is False
        cur.execute("SELECT codigo FROM plat.v_parcela_atual WHERE tenant_id = %s ORDER BY codigo", (tid,))
        assert [r["codigo"] for r in cur.fetchall()] == ["QL-1-01", "QL-1-02"]


def test_dividir_proporcional_largura_e_diagonal(conexao_plat_app, _ids):
    """As outras duas divideOption da doc + rumo diagonal: ProportionalArea em 4 partes iguais,
    EqualWidth em faixas de 30 m (a sobra vira a última parte) e corte a 45 graus com metade da
    área cada (o varredor precisa projetar os QUATRO cantos da caixa, não dois)."""
    con = conexao_plat_app
    tid = _ids["demo"]
    _contexto(con, tid)
    with con.cursor() as cur:
        reg = modelo.criar_registro(cur, tid, codigo="DV-002", tipo="desmembramento")
        pai, _ = _quadro_com_linhas(cur, tid, "QP-1")
        partes = fluxos.dividir(cur, tid, parcela_id=pai["id"], registro_id=reg["id"],
                                rumo_graus=0, opcao="ProportionalArea", numero_de_partes=4)
        assert len(partes) == 4
        for p in partes:
            assert float(p["area_calculada_m2"]) == pytest.approx(2500.0, abs=0.01)

    _contexto(con, tid)
    with con.cursor() as cur:
        reg2 = modelo.criar_registro(cur, tid, codigo="DV-003", tipo="desmembramento")
        pai, _ = _quadro_com_linhas(cur, tid, "QW-1")
        partes = fluxos.dividir(cur, tid, parcela_id=pai["id"], registro_id=reg2["id"],
                                rumo_graus=90, opcao="EqualWidth", parte_area_ou_largura=30.0)
        areas = sorted(float(p["area_calculada_m2"]) for p in partes)
        assert len(partes) == 4
        assert areas == pytest.approx([1000.0, 3000.0, 3000.0, 3000.0], abs=0.01)

    _contexto(con, tid)
    with con.cursor() as cur:
        reg3 = modelo.criar_registro(cur, tid, codigo="DV-004", tipo="desmembramento")
        pai, _ = _quadro_com_linhas(cur, tid, "QD-1")
        partes = fluxos.dividir(cur, tid, parcela_id=pai["id"], registro_id=reg3["id"],
                                rumo_graus=45, opcao="EqualArea", numero_de_partes=2)
        areas = [float(p["area_calculada_m2"]) for p in partes]
        for a in areas:
            assert a == pytest.approx(5000.0, abs=0.01)
        assert abs(areas[0] - areas[1]) <= 0.01


def test_dividir_por_linha_e_recusa(conexao_plat_app, _ids):
    """Divisão por linha de corte (a forma extra da casa) + a REFUTAÇÃO: linha que não cruza é
    recusada com 422 linha_nao_cruza e a parcela fica inteira, ativa, sem partes criadas."""
    con = conexao_plat_app
    tid = _ids["demo"]
    _contexto(con, tid)
    with con.cursor() as cur:
        reg = modelo.criar_registro(cur, tid, codigo="DL-001", tipo="desmembramento")
        pai, _ = _quadro_com_linhas(cur, tid, "QLN-1")
        partes = fluxos.dividir_por_linha(cur, tid, parcela_id=pai["id"], registro_id=reg["id"],
                                          linha=[(50.0, -10.0), (50.0, 110.0)])
        assert len(partes) == 2
        for p in partes:
            assert float(p["area_calculada_m2"]) == pytest.approx(5000.0, abs=0.01)
        assert [p["codigo"] for p in partes] == ["QLN-1-A", "QLN-1-B"]

    _contexto(con, tid)
    with con.cursor() as cur:
        reg2 = modelo.criar_registro(cur, tid, codigo="DL-002", tipo="desmembramento")
        pai2, _ = _quadro_com_linhas(cur, tid, "QLN-2", y0=100000.0)
        with pytest.raises(ErroAPI) as e:
            fluxos.dividir_por_linha(cur, tid, parcela_id=pai2["id"], registro_id=reg2["id"],
                                     linha=[(50.0, 100150.0), (150.0, 100150.0)])
        assert e.value.status_code == 422 and e.value.erro == "linha_nao_cruza"
        assert _ativa(cur, tid, pai2["id"]) is True  # a parcela fica inteira
        cur.execute("SELECT count(*) AS n FROM plat.parcela WHERE tenant_id = %s AND codigo LIKE 'QLN-2-%%'",
                    (tid,))
        assert cur.fetchone()["n"] == 0  # nenhuma parte foi criada
        with pytest.raises(ErroAPI) as e3:
            fluxos.dividir_por_linha(cur, tid, parcela_id=pai2["id"], registro_id=reg2["id"],
                                     linha=[(0.0, 100000.0), (50.0, 100050.0), (100.0, 100000.0)])
        assert e3.value.status_code == 422  # corte de 3 pontos: fora (a casa só corta reto)


def test_dividir_recusa_argumento_fora_do_contrato(conexao_plat_app, _ids):
    con = conexao_plat_app
    tid = _ids["demo"]
    _contexto(con, tid)
    with con.cursor() as cur:
        reg = modelo.criar_registro(cur, tid, codigo="DV-009", tipo="desmembramento")
        pai, _ = _quadro_com_linhas(cur, tid, "QX-1")
        with pytest.raises(ErroAPI):
            fluxos.dividir(cur, tid, parcela_id=pai["id"], registro_id=reg["id"], rumo_graus=90,
                           opcao="EqualWidth", numero_de_partes=2)  # EqualWidth sem largura
        with pytest.raises(ErroAPI):
            fluxos.dividir(cur, tid, parcela_id=pai["id"], registro_id=reg["id"], rumo_graus=90,
                           opcao="ProportionalArea", numero_de_partes=2, parte_area_ou_largura=5.0)
        with pytest.raises(ErroAPI) as e:
            fluxos.dividir(cur, tid, parcela_id=pai["id"], registro_id=reg["id"], rumo_graus=90,
                           opcao="EqualArea", numero_de_partes=limites.PARCELA_DIVIDE_PARTES_MAX + 1)
        assert e.value.status_code == 422 and e.value.erro == "regras_demais"
        with pytest.raises(ErroAPI) as e2:
            fluxos.dividir(cur, tid, parcela_id=pai["id"], registro_id=reg["id"], rumo_graus=90,
                           opcao="RepartirAoMeio", numero_de_partes=2)
        assert e2.value.status_code == 422 and e2.value.erro == "tipo_invalido"
        with pytest.raises(ErroAPI) as e3:
            fluxos.dividir(cur, tid, parcela_id=pai["id"], registro_id=reg["id"], rumo_graus=360,
                           opcao="EqualArea", numero_de_partes=2)
        assert e3.value.status_code == 422


# ------------------------------------------------------------------ unir (portão d)


def test_unir_mantem_externas_e_apaga_interna(conexao_plat_app, _ids):
    """Portão d: a união de dois lotes contíguos mantém as 6 linhas externas ATIVAS e associadas
    à parcela unida; a divisa interna é APAGADA na semântica da doc e RETIRADA na da casa
    (ativa=false com o registro — nunca DELETE, paridade §11)."""
    con = conexao_plat_app
    tid = _ids["demo"]
    _contexto(con, tid)
    with con.cursor() as cur:
        reg = modelo.criar_registro(cur, tid, codigo="UN-001", tipo="remembramento")
        a, linhas_a = _quadro_com_linhas(cur, tid, "QU-1", x0=0.0)
        b, linhas_b = _quadro_com_linhas(cur, tid, "QU-2", x0=100.0)
        cur.execute(
            "SELECT id FROM plat.parcela_linha WHERE tenant_id = %s "
            "AND ST_Equals(geom, ST_GeomFromText('LINESTRING(100 0, 100 100)', %s))",
            (tid, fluxos.SRID),
        )
        divisa = cur.fetchone()
        assert divisa is not None, "a divisa interna devia existir como linha"
        divisa_id = str(divisa["id"])

        unida = fluxos.unir(cur, tid, parcela_ids=[a["id"], b["id"]], registro_id=reg["id"],
                            codigo="QU-UNIDA")
        assert float(unida["area_calculada_m2"]) == pytest.approx(20000.0, abs=0.01)
        assert unida["atributos"]["fluxo"] == "merge"
        assert sorted(unida["atributos"]["origens"]) == sorted([str(a["id"]), str(b["id"])])
        assert _ativa(cur, tid, a["id"]) is False and _ativa(cur, tid, b["id"]) is False
        assert _ativa(cur, tid, unida["id"]) is True

        # a divisa interna: retirada (ativa=false, com o registro), nunca apagada
        cur.execute("SELECT ativa, retirada_por_registro FROM plat.parcela_linha "
                    "WHERE id = %s::uuid AND tenant_id = %s", (divisa_id, tid))
        ln = cur.fetchone()
        assert ln["ativa"] is False
        assert str(ln["retirada_por_registro"]) == str(reg["id"])

        # as 6 externas: ativas e associadas à unida
        cur.execute(
            "SELECT count(*) AS n, count(*) FILTER (WHERE l.ativa) AS ativas "
            "FROM plat.parcela_linha l JOIN plat.parcela_linha_parcela u ON u.linha_id = l.id "
            "WHERE u.parcela_id = %s::uuid AND l.tenant_id = %s",
            (str(unida["id"]), tid),
        )
        r = cur.fetchone()
        assert r["n"] == 6 and r["ativas"] == 6
        # e a divisa interna NÃO pertence à unida
        cur.execute("SELECT count(*) AS n FROM plat.parcela_linha_parcela "
                    "WHERE parcela_id = %s::uuid AND linha_id = %s::uuid", (str(unida["id"]), divisa_id))
        assert cur.fetchone()["n"] == 0


def test_unir_recusa_descontinua_e_limite(conexao_plat_app, _ids):
    con = conexao_plat_app
    tid = _ids["demo"]
    _contexto(con, tid)
    with con.cursor() as cur:
        reg = modelo.criar_registro(cur, tid, codigo="UN-009", tipo="remembramento")
        a, _ = _quadro_com_linhas(cur, tid, "QI-1", x0=0.0)
        b, _ = _quadro_com_linhas(cur, tid, "QI-2", x0=1000.0)
        with pytest.raises(ErroAPI) as e:
            fluxos.unir(cur, tid, parcela_ids=[a["id"], b["id"]], registro_id=reg["id"])
        assert e.value.status_code == 422  # união descontínua não é polígono único
        with pytest.raises(ErroAPI) as e2:
            fluxos.unir(cur, tid, parcela_ids=[a["id"]], registro_id=reg["id"])
        assert e2.value.status_code == 422


# ------------------------------------------------------------------ recortar


def test_recortar_tres_opcoes(conexao_plat_app, _ids):
    con = conexao_plat_app
    tid = _ids["demo"]
    wkt_metade_leste = "POLYGON((50 0, 150 0, 150 100, 50 100, 50 0))"
    _contexto(con, tid)
    with con.cursor() as cur:
        reg = modelo.criar_registro(cur, tid, codigo="CL-001", tipo="desmembramento")
        pai, _ = _quadro_com_linhas(cur, tid, "QC-1")
        r = fluxos.recortar(cur, tid, parcela_id=pai["id"], registro_id=reg["id"],
                            opcao="PreserveArea", geometria_wkt=wkt_metade_leste)
        # PreserveArea: a interseção vira parcela nova e o PAI CONTINUA (mesma identidade) com o resto
        assert len(r["adds"]) == 1
        assert float(r["adds"][0]["area_calculada_m2"]) == pytest.approx(5000.0, abs=0.01)
        assert r["atualizado"] is not None
        assert str(r["atualizado"]["id"]) == str(pai["id"])
        assert float(r["atualizado"]["area_calculada_m2"]) == pytest.approx(5000.0, abs=0.01)
        assert _ativa(cur, tid, pai["id"]) is True

    _contexto(con, tid)
    with con.cursor() as cur:
        reg2 = modelo.criar_registro(cur, tid, codigo="CL-002", tipo="desmembramento")
        pai2, _ = _quadro_com_linhas(cur, tid, "QC-2", y0=100000.0)
        geo2 = "POLYGON((50 100000, 150 100000, 150 100100, 50 100100, 50 100000))"
        r2 = fluxos.recortar(cur, tid, parcela_id=pai2["id"], registro_id=reg2["id"],
                             opcao="DiscardArea", geometria_wkt=geo2)
        assert r2["adds"] == []  # a área de recorte é descartada
        assert float(r2["atualizado"]["area_calculada_m2"]) == pytest.approx(5000.0, abs=0.01)

    _contexto(con, tid)
    with con.cursor() as cur:
        reg3 = modelo.criar_registro(cur, tid, codigo="CL-003", tipo="desmembramento")
        pai3, _ = _quadro_com_linhas(cur, tid, "QC-3", y0=200000.0)
        geo3 = "POLYGON((50 200000, 150 200000, 150 200100, 50 200100, 50 200000))"
        r3 = fluxos.recortar(cur, tid, parcela_id=pai3["id"], registro_id=reg3["id"],
                             opcao="PreserveBothAreasSplit", geometria_wkt=geo3)
        assert _ativa(cur, tid, pai3["id"]) is False  # o pai sai
        assert len(r3["adds"]) == 2
        areas = sorted(float(p["area_calculada_m2"]) for p in r3["adds"])
        assert areas == pytest.approx([5000.0, 5000.0], abs=0.01)
        assert [p["codigo"] for p in r3["adds"]] == ["QC-3-R", "QC-3-S"]

    _contexto(con, tid)
    with con.cursor() as cur:
        reg4 = modelo.criar_registro(cur, tid, codigo="CL-004", tipo="desmembramento")
        pai4, _ = _quadro_com_linhas(cur, tid, "QC-4", y0=300000.0)
        geo4 = "POLYGON((-50 300000, 150 300000, 150 300100, -50 300100, -50 300000))"
        r4 = fluxos.recortar(cur, tid, parcela_id=pai4["id"], registro_id=reg4["id"],
                             opcao="PreserveArea", geometria_wkt=geo4)
        assert r4["atualizado"] is None  # sem resto: o recorte consumiu a parcela
        assert _ativa(cur, tid, pai4["id"]) is False


# ------------------------------------------------------------------ build + sementes (portão e)


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


def test_dxf_leitor_sintetico():
    segs = dxf.ler(DXF_SINTETICO)
    assert len(segs) == 11  # 7 de LINE + 4 da polilinha fechada (fecha o 4º segmento sozinha)
    assert all(s["camada"] == "LOT" for s in segs)
    with pytest.raises(ErroAPI) as e:
        dxf.ler("0\nSECTION\n2\nHEADER\n9\n$ACADVER\n1\nAC1027\n0\nENDSEC\n")
    assert e.value.status_code == 422  # sem ENTITIES não é dado
    with pytest.raises(ErroAPI) as e2:
        dxf.ler("0\nSECTION\n2\nENTITIES\n0\nENDSEC\n")
    assert e2.value.status_code == 422  # seção vazia: sem linha aproveitável


def test_build_dxf_sintetico_gera_tres_faces(conexao_plat_app, _ids):
    """Portão e (contagem determinística): as linhas do DXF sintético fecham exatamente 3
    faces; o build gera 3 parcelas e um segundo build gera ZERO (as linhas já têm parcela)."""
    con = conexao_plat_app
    tid = _ids["demo"]
    _contexto(con, tid)
    with con.cursor() as cur:
        reg = modelo.criar_registro(cur, tid, codigo="DX-001", tipo="outro")
        segs = dxf.ler(DXF_SINTETICO)
        imp = dxf.importar(cur, tid, segmentos=segs, registro_id=reg["id"])
        assert imp["linhas"] == 11 and imp["pontos"] == 10
        criadas = fluxos.construir(cur, tid, registro_id=reg["id"])
        assert len(criadas) == 3  # a contagem do portão
        assert all(p["atributos"]["fluxo"] == "build" for p in criadas)
        areas = sorted(float(p["area_calculada_m2"]) for p in criadas)
        assert areas == pytest.approx([100.0, 100.0, 100.0], abs=0.01)
        de_novo = fluxos.construir(cur, tid, registro_id=reg["id"])
        assert de_novo == []  # linhas livres: nenhum sobrou


def test_build_a_partir_de_dxf_real(conexao_plat_app, _ids, medida):
    """Portão e com o dado aberto de verdade: a planta de teste da casa (corpus aberto de
    projeto, fixture dados/planta_baixa_A01.dxf). 557 segmentos entram; o build fecha as faces
    que o desenho deixa fechadas — a contagem exata é MEDIDA e citável (não fixada no teste,
    que uma versão de PostGIS pode mover); o recorte SEMÂNTICO é a camada LOT, uma poligonal
    fechada única, que vira exatamente 1 lote com a área da poligonal (fórmula do calcador)."""
    con = conexao_plat_app
    tid = _ids["demo"]
    _contexto(con, tid)
    caminho = RAIZ / "tests" / "api" / "parcelas" / "dados" / "planta_baixa_A01.dxf"
    with con.cursor() as cur:
        reg = modelo.criar_registro(cur, tid, codigo="DX-002", tipo="outro")
        segs = dxf.ler_arquivo(caminho)
        assert len(segs) == 557
        imp = dxf.importar(cur, tid, segmentos=segs, registro_id=reg["id"])
        assert imp["linhas"] == 557
        criadas = fluxos.construir(cur, tid, registro_id=reg["id"])
        assert len(criadas) >= 1, "o desenho da planta devia deixar ao menos uma face fechada"
    medida("L4-parcelas-02-fluxos-cogo")("dxf_real_segmentos", len(segs), "segmentos",
                                         "pytest tests/api/parcelas/test_fluxos.py::"
                                         "test_build_a_partir_de_dxf_real PLAT_GRAVAR_MEDIDAS=1")
    medida("L4-parcelas-02-fluxos-cogo")("dxf_real_faces_build", len(criadas), "parcelas", "idem")

    # a camada LOT do desenho é um retângulo fechado: recorte semântico de exatamente 1 lote
    _contexto(con, tid)
    with con.cursor() as cur:
        reg2 = modelo.criar_registro(cur, tid, codigo="DX-003", tipo="outro")
        lote = dxf.importar(cur, tid, segmentos=[s for s in segs if s["camada"] == "LOT"],
                            registro_id=reg2["id"])
        assert lote["linhas"] == 4
        criado_lote = fluxos.construir(cur, tid, registro_id=reg2["id"])
        assert len(criado_lote) == 1  # a contagem semântica: a camada LOT fecha 1 lote
        assert float(criado_lote[0]["area_calculada_m2"]) == pytest.approx(
            _area_do_anel([s for s in segs if s["camada"] == "LOT"]), abs=0.01)
    medida("L4-parcelas-02-fluxos-cogo")("dxf_real_lote_area_m2",
                                         float(criado_lote[0]["area_calculada_m2"]), "m2", "idem")


def _area_do_anel(segs: list[dict]) -> float:
    """Fórmula do calcador sobre os segmentos da camada LOT (verificação independente do
    ST_Area do banco: o número do teste não depende de quem mede)."""
    cadeia = list(segs)
    anel = [cadeia[0]["pontos"][0], cadeia[0]["pontos"][1]]
    restante = cadeia[1:]
    while restante:
        fim = anel[-1]
        for i, s in enumerate(restante):
            a, b = s["pontos"]
            if math.hypot(a[0] - fim[0], a[1] - fim[1]) < 1e-6:
                anel.append(b)
                restante.pop(i)
                break
            if math.hypot(b[0] - fim[0], b[1] - fim[1]) < 1e-6:
                anel.append(a)
                restante.pop(i)
                break
        else:
            raise AssertionError("os segmentos da camada LOT não formam uma cadeia fechada")
    soma = 0.0
    for i in range(len(anel) - 1):
        (x1, y1), (x2, y2) = anel[i], anel[i + 1]
        soma += x1 * y2 - x2 * y1
    return abs(soma) / 2.0


def test_sementes_fluxo_completo(conexao_plat_app, _ids):
    """createSeeds -> build ignora a face com semente -> reconstructFromSeeds cria a parcela,
    retira a semente e devolve a contagem (o reconstructedParcelCount da doc)."""
    con = conexao_plat_app
    tid = _ids["demo"]
    _contexto(con, tid)
    with con.cursor() as cur:
        reg = modelo.criar_registro(cur, tid, codigo="SD-001", tipo="aprovacao")
        segs = dxf.ler(DXF_SINTETICO)
        dxf.importar(cur, tid, segmentos=segs, registro_id=reg["id"])

        sementes = fluxos.criar_sementes(cur, tid, registro_id=reg["id"])
        assert len(sementes) == 3
        cur.execute("SELECT count(*) AS n FROM plat.parcela_semente WHERE tenant_id = %s AND ativa", (tid,))
        assert cur.fetchone()["n"] == 3

        # build NÃO cria parcela em face com semente ativa
        assert fluxos.construir(cur, tid, registro_id=reg["id"]) == []

        extent = {"xmin": -1.0, "ymin": -1.0, "xmax": 70.0, "ymax": 70.0}
        r = fluxos.reconstruir_de_sementes(cur, tid, registro_id=reg["id"], extent=extent)
        assert r["count"] == 3
        assert [p["codigo"] for p in r["criadas"]] == ["S-00001", "S-00002", "S-00003"]
        cur.execute("SELECT count(*) AS n FROM plat.parcela_semente WHERE tenant_id = %s AND ativa", (tid,))
        assert cur.fetchone()["n"] == 0  # as sementes consumidas foram retiradas
        cur.execute("SELECT count(*) AS n FROM plat.parcela WHERE tenant_id = %s AND ativa", (tid,))
        assert cur.fetchone()["n"] == 3
        # reconstruir de novo: sem semente, nenhuma parcela nova
        r2 = fluxos.reconstruir_de_sementes(cur, tid, registro_id=reg["id"], extent=extent)
        assert r2["count"] == 0
        # sem extent é recusa (a doc exige extent)
        with pytest.raises(ErroAPI) as e:
            fluxos.reconstruir_de_sementes(cur, tid, registro_id=reg["id"], extent=None)
        assert e.value.status_code == 422


# ------------------------------------------------------------------ duplicar, mudar tipo, atribuir


def test_duplicar_e_mudar_tipo(conexao_plat_app, _ids):
    con = conexao_plat_app
    tid = _ids["demo"]
    _contexto(con, tid)
    with con.cursor() as cur:
        reg = modelo.criar_registro(cur, tid, codigo="DP-001", tipo="aprovacao")
        pai, _ = _quadro_com_linhas(cur, tid, "QP-10")
        copia = fluxos.duplicar(cur, tid, parcela_id=pai["id"], registro_id=reg["id"], codigo="QP-10-C")
        assert copia["id"] != pai["id"]
        assert float(copia["area_calculada_m2"]) == pytest.approx(10000.0, abs=0.01)
        assert copia["atributos"]["fluxo"] == "duplicar"
        assert copia["atributos"]["origem"] == str(pai["id"])
        mudada = fluxos.mudar_tipo(cur, tid, parcela_id=pai["id"], tipo="gleba")
        assert str(mudada["id"]) == str(pai["id"]) and mudada["tipo"] == "gleba"
        with pytest.raises(ErroAPI):
            fluxos.mudar_tipo(cur, tid, parcela_id=pai["id"], tipo="matricula")


def test_atribuir_a_registro_com_recusa(conexao_plat_app, _ids):
    """assignFeaturesToRecord: CreatedByRecord reatribui a criação; RetiredByRecord RETIRA
    (parcela/linha; ponto só fica inativo — item 01, decisão declarada). Retirar pelo MESMO
    registro que criou é recusado com mensagem legível (a CHECK da tabela proíbe)."""
    con = conexao_plat_app
    tid = _ids["demo"]
    _contexto(con, tid)
    with con.cursor() as cur:
        reg1 = modelo.criar_registro(cur, tid, codigo="AT-001", tipo="aprovacao")
        reg2 = modelo.criar_registro(cur, tid, codigo="AT-002", tipo="desmembramento")
        pai, linhas = _quadro_com_linhas(cur, tid, "QA-1")
        r = fluxos.atribuir_a_registro(cur, tid, pares=[{"id": str(pai["id"]), "layerId": "parcela"}],
                                       registro_id=reg2["id"], escrever="CreatedByRecord")
        assert r["writeAttribute"] == "CreatedByRecord"
        cur.execute("SELECT criada_por_registro FROM plat.parcela WHERE id = %s::uuid", (str(pai["id"]),))
        assert str(cur.fetchone()["criada_por_registro"]) == str(reg2["id"])

        with pytest.raises(ErroAPI) as e:
            fluxos.atribuir_a_registro(cur, tid, pares=[{"id": str(pai["id"]), "layerId": "parcela"}],
                                       registro_id=reg2["id"], escrever="RetiredByRecord")
        assert e.value.status_code == 422  # retirada pelo mesmo registro que criou: proibida

        r2 = fluxos.atribuir_a_registro(
            cur, tid,
            pares=[{"id": str(pai["id"]), "layerId": "parcela"},
                   {"id": str(linhas[0]["id"]), "layerId": "linha"}],
            registro_id=reg1["id"], escrever="RetiredByRecord",
        )
        assert len(r2["feitos"]) == 2
        cur.execute("SELECT ativa FROM plat.parcela WHERE id = %s::uuid", (str(pai["id"]),))
        assert cur.fetchone()["ativa"] is False
        cur.execute("SELECT ativa FROM plat.parcela_linha WHERE id = %s::uuid", (str(linhas[0]["id"]),))
        assert cur.fetchone()["ativa"] is False

        # ponto: RetiredByRecord deixa inativo (ponto não tem retirada por registro)
        p1 = modelo.criar_ponto(cur, tid, x=500.0, y=500.0, registro_id=reg1["id"])
        fluxos.atribuir_a_registro(cur, tid, pares=[{"id": str(p1["id"]), "layerId": "ponto"}],
                                   registro_id=reg2["id"], escrever="RetiredByRecord")
        cur.execute("SELECT ativa, retirada_por_registro IS NULL AS sem_retirada "
                    "FROM plat.parcela_ponto WHERE id = %s::uuid", (str(p1["id"]),))
        pt = cur.fetchone()
        assert pt["ativa"] is False and pt["sem_retirada"] is True

        with pytest.raises(ErroAPI) as e404:
            fluxos.atribuir_a_registro(cur, tid, pares=[{"id": "00000000-0000-0000-0000-000000000000",
                                                         "layerId": "parcela"}],
                                       registro_id=reg2["id"], escrever="CreatedByRecord")
        assert e404.value.status_code == 404
        with pytest.raises(ErroAPI) as e422:
            fluxos.atribuir_a_registro(cur, tid, pares=[{"id": str(pai["id"]), "layerId": "predio"}],
                                       registro_id=reg2["id"])
        assert e422.value.status_code == 422


# ------------------------------------------------------------------ paridade (portão g)


def test_paridade_secao_11_e_12():
    doc = RAIZ / "docs" / "PARIDADE_PARCELAS.md"
    assert doc.exists(), "docs/PARIDADE_PARCELAS.md não existe"
    texto = doc.read_text(encoding="utf-8")
    for termo in ("build", "divide", "merge", "clip", "createSeeds", "reconstructFromSeeds",
                  "assignFeaturesToRecord", "ProportionalArea", "EqualArea", "EqualWidth",
                  "DXF", "LWPOLYLINE", "linha_nao_cruza"):
        assert termo in texto, f"paridade §11/§12 sem '{termo}'"
