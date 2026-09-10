"""Malha de parcelas (item L4-parcelas-01-modelo-de-parcelas).

Portão, cláusula por cláusula:
  a) "DDL plat.parcela_* (registro, parcela por tipo, linha, ponto, conexão) com RLS e
     versionamento" -> as seis tabelas existem na migração; RLS provada no teste cruzado de
     inquilino; versionamento = linhagem por registro (criada_por/retirada_por + visões
     atual/histórico), testada em test_retirada_* e test_ficha_*;
  b) "importar lotes derivados do SIG de teste interno (dado aberto) como parcelas do tipo
     'lote' com registro sintético" -> test_import_* (malha sintética com linha partilhada) e
     test_import_real_sig (a origem de verdade, lida por COPY de só leitura, dentro da
     transação que a fixture desfaz);
  c) "criar registro, criar parcela por linhas COGO (e2e)" -> test_e2e_registro_e_parcela_por_cogo
  d) "retirar parcela por novo registro e ver histórico (linhagem) na ficha" -> test_retirada_*
     e test_ficha_mostra_linhagem_nos_dois_sentidos
  e) "nenhuma matrícula real, nenhum nome" -> vocabulário fechado de tipo e de tipo de registro
     (recusa fora dele); o import não carrega campo de pessoa (o SELECT da origem só lê
     empreendimento_id, código e geometria — scripts/importar_lotes_sig.py)
  f) "paridade contra parcel fabric schema/records/parcel types escrita" -> test_paridade_escrita
Refutação: "adversário cria duas parcelas ativas do mesmo tipo sobrepostas e confere que a
validação aponta" -> test_sobreposicao_*; "retira parcela e confere que ela some do 'atual' e
fica no 'histórico' com o registro" -> test_retirada_sai_do_atual_e_fica_no_historico.

Banco: suíte conecta como o app da TRILHA (conexao_plat_app); inquilinos demo/demo2 vêm de
plat.auth_login (padrão tests/api/test_rls.py); GUC local à transação; fixture desfaz tudo.
"""

import math
from pathlib import Path

import pytest

from app.erros import ErroAPI
from app.parcelas import cogo, importar, modelo, validacao

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


# ------------------------------------------------------------------ COGO puro (sem banco)


def test_arco_chega_no_ponto_analitico():
    """Quarto de círculo: rumo norte, curva à direita com raio 10, arco pi*10/2 -> chega em
    (10, 10). O rumo é tangente; a chegada é o ponto real do arco."""
    r = cogo.caminhar((0.0, 0.0), [(0.0, math.pi * 10 / 2, 10.0)])
    assert r["vertices"][-1][0] == pytest.approx(10.0, abs=1e-9)
    assert r["vertices"][-1][1] == pytest.approx(10.0, abs=1e-9)
    assert r["perimetro_m"] == pytest.approx(math.pi * 10 / 2, rel=1e-9)


def test_arco_com_raio_negativo_curva_a_esquerda():
    r = cogo.caminhar((0.0, 0.0), [(0.0, math.pi * 10 / 2, -10.0)])
    assert r["vertices"][-1][0] == pytest.approx(-10.0, abs=1e-9)
    assert r["vertices"][-1][1] == pytest.approx(10.0, abs=1e-9)


def test_reto_fecha_exato_e_sem_fechamento():
    r = cogo.caminhar((0.0, 0.0), [(90, 100), (180, 50), (270, 100), (0, 50)])
    assert r["fechamento_m"] == pytest.approx(0.0, abs=1e-9)
    assert r["razao"] is None
    assert r["perimetro_m"] == pytest.approx(300.0)


def test_trajeto_aberto_declara_o_erro():
    r = cogo.caminhar((0.0, 0.0), [(90, 100), (180, 50), (270, 100), (180, 50)])
    assert r["fechamento_m"] == pytest.approx(100.0, abs=1e-9)
    assert r["razao"] == pytest.approx(3.0)


def test_trajeto_vazio_e_recusado():
    with pytest.raises(ErroAPI) as e:
        cogo.caminhar((0.0, 0.0), [])
    assert e.value.status_code == 422


# ------------------------------------------------------------------ e2e COGO no banco (portão c)


def test_e2e_registro_e_parcela_por_cogo(conexao_plat_app, _ids):
    con = conexao_plat_app
    tid = _ids["demo"]
    _contexto(con, tid)
    with con.cursor() as cur:
        reg = modelo.criar_registro(cur, tid, codigo="DOC-2026-001", tipo="desmembramento",
                                    data_registro="2026-09-08")
        p0 = modelo.criar_ponto(cur, tid, x=1000.0, y=2000.0, nome="V-0", precisao_xy_m=0.02,
                                fixo=True, registro_id=reg["id"])
        parcela = cogo.criar_parcela_cogo(
            cur, tid, registro_id=reg["id"], ponto_inicial_id=p0["id"], codigo="Q1-L01",
            tipo="lote", trajeto=[(90, 100), (180, 50), (270, 100), (0, 50)],
            precisao_xy_m=0.02, precisao_rumo_s=30, precisao_dist_cm=5, area_declarada_m2=5000.0,
        )
        assert parcela["area_calculada_m2"] == pytest.approx(5000.0, abs=1e-6)
        assert float(parcela["erro_fechamento_m"]) == pytest.approx(0.0, abs=1e-9)
        assert parcela["erro_fechamento_razao"] is None
        assert float(parcela["area_declarada_m2"]) == 5000.0
        cur.execute("SELECT count(*) AS n FROM plat.parcela_ponto WHERE tenant_id = %s", (tid,))
        assert cur.fetchone()["n"] == 4  # o ponto inicial é reusado; 3 vértices novos
        cur.execute(
            "SELECT count(*) AS n, count(*) FILTER (WHERE tipo_cogo = 'reta') AS retas "
            "FROM plat.parcela_linha WHERE tenant_id = %s", (tid,))
        r = cur.fetchone()
        assert r["n"] == 4 and r["retas"] == 4
        cur.execute(
            "SELECT count(*) AS n FROM plat.parcela_linha_parcela WHERE parcela_id = %s::uuid",
            (str(parcela["id"]),))
        assert cur.fetchone()["n"] == 4
        cur.execute("SELECT codigo FROM plat.v_parcela_atual WHERE tenant_id = %s", (tid,))
        assert [r["codigo"] for r in cur.fetchall()] == ["Q1-L01"]


# ------------------------------------------------------------------ import (portão b)


def _malha_sintetica():
    return [
        {"empreendimento_id": 1, "codigo": "Q1-L1", "wkt": "POLYGON((0 0,100 0,100 100,0 100,0 0))"},
        {"empreendimento_id": 1, "codigo": "Q1-L2", "wkt": "POLYGON((100 0,200 0,200 100,100 100,100 0))"},
        {"empreendimento_id": 2, "codigo": "Q1-L1", "wkt": "POLYGON((0 0,100 0,100 100,0 100,0 0))"},
    ]


def test_import_cria_lote_com_registro_sintetico_e_linha_partilhada(conexao_plat_app, _ids):
    con = conexao_plat_app
    tid = _ids["demo"]
    _contexto(con, tid)
    with con.cursor() as cur:
        resumo = importar.importar_lotes(cur, tid, _malha_sintetica())
        assert resumo["registros"] == 2  # um registro sintético por empreendimento
        assert resumo["parcelas"] == 3
        assert resumo["pontos"] == 6    # 4 do primeiro + 2 novos do segundo; o terceiro reusa tudo
        assert resumo["linhas"] == 7    # 4 + 3 (a divisa comum é UMA linha)
        assert resumo["associacoes"] == 12
        assert resumo["linhas_partilhadas"] == 4  # as 4 divisas do lote 3 reusam as do lote 1
        cur.execute(
            "SELECT tipo, origem, codigo FROM plat.parcela_registro WHERE tenant_id = %s "
            "ORDER BY codigo", (tid,))
        regs = cur.fetchall()
        assert all(r["origem"] == "sintetico" and r["tipo"] == "loteamento" for r in regs)
        cur.execute(
            "SELECT precisao_xy_m FROM plat.parcela_ponto WHERE tenant_id = %s LIMIT 1", (tid,))
        p = cur.fetchone()
        assert p["precisao_xy_m"] is None  # precisão derivada NÃO é inventada
        cur.execute("SELECT atributos->>'origem' AS marca FROM plat.parcela WHERE tenant_id = %s",
                    (tid,))
        assert all(r["marca"] == "sig_lote_derivado" for r in cur.fetchall())


def test_import_real_sig_casa(conexao_plat_app, _ids, medida):
    """A origem de verdade: lotes derivados do SIG de teste interno (dado aberto), lidos por
    COPY de SÓ LEITURA como postgres e importados dentro da transação que a fixture desfaz. É
    este teste que mede o número citável do portão (a origem cresce desde que o item foi
    escrito — o número de hoje vale, o do portão era o de então)."""
    con = conexao_plat_app
    tid = _ids["demo"]
    _contexto(con, tid)
    lotes = importar_lotes_sig_origem()
    assert len(lotes) > 0, "origem sem lotes: sigcorp.lote vazia nesta máquina"
    with con.cursor() as cur:
        resumo = importar.importar_lotes(cur, tid, lotes)
        assert resumo["parcelas"] == len(lotes)
        assert resumo["registros"] >= 1
        assert resumo["linhas_partilhadas"] > 0, "malha derivada devia ter divisas compartilhadas"
        cur.execute("SELECT count(*) AS n FROM plat.parcela WHERE tenant_id = %s AND tipo = 'lote'",
                    (tid,))
        assert cur.fetchone()["n"] == len(lotes)
        cur.execute("SELECT count(*) AS n FROM plat.parcela WHERE tenant_id = %s AND NOT ativa", (tid,))
        assert cur.fetchone()["n"] == 0
    medida("L4-parcelas-01-modelo-de-parcelas")("import_real_parcelas", resumo["parcelas"],
                                                "parcelas",
                                                "pytest tests/api/parcelas/test_modelo.py::"
                                                "test_import_real_sig_casa PLAT_GRAVAR_MEDIDAS=1")
    medida("L4-parcelas-01-modelo-de-parcelas")("import_real_linhas_partilhadas",
                                                resumo["linhas_partilhadas"], "linhas",
                                                "idem")


def importar_lotes_sig_origem() -> list[dict]:
    """A leitura da origem do teste: o mesmo caminho do script (COPY como postgres, só
    leitura, sem nome e sem matrícula na projeção)."""
    import csv
    import io
    import subprocess

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


# ------------------------------------------------------------------ retirada e linhagem (portão d + refutação 2)


def _lote_criado(cur, tid, codigo, registro_id, dx=0.0, tipo="lote"):
    return modelo.criar_parcela(
        cur, tid, tipo=tipo, codigo=codigo, registro_id=registro_id,
        anel=[(10 + dx, 10), (30 + dx, 10), (30 + dx, 30), (10 + dx, 30)],
    )


def _lote_com_linhas(cur, tid, codigo, registro_id, dx=0.0):
    """Lote com as 4 linhas de limite CRIADAS e associadas (o que a retirada usa para
    demonstrar que linha exclusiva sai junto e linha partilhada fica)."""
    cantos = [(10 + dx, 10), (30 + dx, 10), (30 + dx, 30), (10 + dx, 30)]
    pontos = [modelo.criar_ponto(cur, tid, x=x, y=y) for x, y in cantos]
    linhas = [modelo.criar_linha(cur, tid, de_ponto_id=pontos[i]["id"],
                                 para_ponto_id=pontos[(i + 1) % 4]["id"]) for i in range(4)]
    return modelo.criar_parcela(
        cur, tid, tipo="lote", codigo=codigo, registro_id=registro_id,
        anel=cantos, linha_ids=[ln["id"] for ln in linhas],
    )


def test_retirada_sai_do_atual_e_fica_no_historico(conexao_plat_app, _ids):
    con = conexao_plat_app
    tid = _ids["demo"]
    _contexto(con, tid)
    with con.cursor() as cur:
        reg1 = modelo.criar_registro(cur, tid, codigo="R-001", tipo="loteamento")
        parcela = _lote_com_linhas(cur, tid, "L-100", reg1["id"])
        reg2 = modelo.criar_registro(cur, tid, codigo="R-002", tipo="remembramento")
        retirada = modelo.retirar_parcela(cur, tid, parcela_id=parcela["id"], registro_id=reg2["id"])
        assert retirada["codigo"] == "L-100"
        cur.execute("SELECT count(*) AS n FROM plat.v_parcela_atual WHERE tenant_id = %s", (tid,))
        assert cur.fetchone()["n"] == 0  # sumiu do 'atual'
        cur.execute(
            "SELECT codigo, retirada_por_codigo, retirada_por_tipo FROM plat.v_parcela_historico "
            "WHERE tenant_id = %s", (tid,))
        h = cur.fetchone()
        assert h["codigo"] == "L-100" and h["retirada_por_codigo"] == "R-002"
        assert h["retirada_por_tipo"] == "remembramento"
        # as 4 linhas exclusivas da parcela são retiradas junto; nada é apagado
        cur.execute("SELECT count(*) AS n FROM plat.parcela_linha WHERE tenant_id = %s AND ativa", (tid,))
        assert cur.fetchone()["n"] == 0
        cur.execute("SELECT count(*) AS n FROM plat.parcela_linha WHERE tenant_id = %s", (tid,))
        assert cur.fetchone()["n"] == 4
        cur.execute("SELECT count(*) AS n FROM plat.parcela_ponto WHERE tenant_id = %s", (tid,))
        assert cur.fetchone()["n"] == 4  # ponto é acervo, fica
        with pytest.raises(ErroAPI):
            modelo.retirar_parcela(cur, tid, parcela_id=parcela["id"], registro_id=reg2["id"])


def test_linha_partilhada_sobrevive_a_retirada_de_um_dos_lados(conexao_plat_app, _ids):
    con = conexao_plat_app
    tid = _ids["demo"]
    _contexto(con, tid)
    with con.cursor() as cur:
        modelo.criar_registro(cur, tid, codigo="RS-001", tipo="loteamento")
        resumo = importar.importar_lotes(cur, tid, _malha_sintetica()[:2])
        cur.execute(
            "SELECT count(*) AS n FROM plat.parcela_linha WHERE tenant_id = %s AND ativa", (tid,))
        ativas_antes = cur.fetchone()["n"]
        assert ativas_antes == resumo["linhas"]
        reg2 = modelo.criar_registro(cur, tid, codigo="RS-002", tipo="desmembramento")
        cur.execute("SELECT id, codigo FROM plat.parcela WHERE tenant_id = %s ORDER BY codigo", (tid,))
        primeira = cur.fetchone()
        modelo.retirar_parcela(cur, tid, parcela_id=primeira["id"], registro_id=reg2["id"])
        cur.execute(
            "SELECT count(*) AS n FROM plat.parcela_linha WHERE tenant_id = %s AND ativa", (tid,))
        # das 7 linhas, as 3 exclusivas do lote retirado saem; a partilhada e as 3 do
        # sobrevivente continuam
        assert cur.fetchone()["n"] == 4


def test_ficha_mostra_linhagem_nos_dois_sentidos(conexao_plat_app, _ids):
    con = conexao_plat_app
    tid = _ids["demo"]
    _contexto(con, tid)
    with con.cursor() as cur:
        reg1 = modelo.criar_registro(cur, tid, codigo="F-001", tipo="loteamento")
        antiga = _lote_criado(cur, tid, "L-A", reg1["id"])
        reg2 = modelo.criar_registro(cur, tid, codigo="F-002", tipo="desmembramento")
        modelo.retirar_parcela(cur, tid, parcela_id=antiga["id"], registro_id=reg2["id"])
        nova = modelo.criar_parcela(
            cur, tid, tipo="lote", codigo="L-A-1", registro_id=reg2["id"],
            anel=[(10, 10), (20, 10), (20, 30), (10, 30)],
        )
        ficha_nova = modelo.ficha(cur, tid, nova["id"])
        assert ficha_nova["ativa"] is True
        assert ficha_nova["criada_por"]["codigo"] == "F-002"
        assert [p["codigo"] for p in ficha_nova["predecessoras"]] == ["L-A"]  # quem o registro F-002 retirou
        ficha_antiga = modelo.ficha(cur, tid, antiga["id"])
        assert ficha_antiga["ativa"] is False
        assert ficha_antiga["retirada_por"]["codigo"] == "F-002"
        assert [s["codigo"] for s in ficha_antiga["sucessoras"]] == ["L-A-1"]  # quem F-002 criou


# ------------------------------------------------------------------ validação (refutação 1)


def test_sobreposicao_mesmo_tipo_aponta(conexao_plat_app, _ids, medida):
    con = conexao_plat_app
    tid = _ids["demo"]
    _contexto(con, tid)
    with con.cursor() as cur:
        reg = modelo.criar_registro(cur, tid, codigo="S-001", tipo="loteamento")
        _lote_criado(cur, tid, "L-1", reg["id"], dx=0.0)
        _lote_criado(cur, tid, "L-2", reg["id"], dx=10.0)  # sobreposto de propósito
        _lote_criado(cur, tid, "G-1", reg["id"], dx=5.0, tipo="gleba")  # valida só contra gleba
        modelo.criar_parcela(cur, tid, tipo="gleba", codigo="G-1b", registro_id=reg["id"],
                             anel=[(15, 10), (35, 10), (35, 30), (15, 30)])
        r = validacao.sobreposicoes(cur, tenant_id=tid)
        pares_lote = [p for p in r["pares"] if p["tipo"] == "lote"]
        pares_gleba = [p for p in r["pares"] if p["tipo"] == "gleba"]
        assert r["total"] == 2 and not r["truncado"]
        assert len(pares_lote) == 1
        assert {pares_lote[0]["a"], pares_lote[0]["b"]} == {"L-1", "L-2"}
        assert pares_lote[0]["area_m2"] == pytest.approx(200.0)  # 10 m × 20 m
        # G-1 (x de 15 a 35) e G-1b são idênticos: um par de gleba; cruzar com lote não aponta
        assert len(pares_gleba) == 1
        assert {pares_gleba[0]["a"], pares_gleba[0]["b"]} == {"G-1", "G-1b"}
        assert pares_gleba[0]["area_m2"] == pytest.approx(400.0)  # 20 m × 20 m
        # retirada tira o par: só o 'atual' se valida
        reg2 = modelo.criar_registro(cur, tid, codigo="S-002", tipo="remembramento")
        cur.execute("SELECT id FROM plat.parcela WHERE tenant_id = %s AND codigo = 'L-2'", (tid,))
        modelo.retirar_parcela(cur, tid, parcela_id=cur.fetchone()["id"], registro_id=reg2["id"])
        r2 = validacao.sobreposicoes(cur, tenant_id=tid)
        assert all({"L-1", "L-2"} != {p["a"], p["b"]} for p in r2["pares"])
        assert r2["total"] == 1  # sobra o par de glebas
    medida("L4-parcelas-01-modelo-de-parcelas")("sobreposicao_area_m2", 200.0, "m2",
                                                "pytest tests/api/parcelas/test_modelo.py::"
                                                "test_sobreposicao_mesmo_tipo_aponta "
                                                "PLAT_GRAVAR_MEDIDAS=1")


def test_sobreposicao_de_tipo_diferente_nao_aponta(conexao_plat_app, _ids):
    con = conexao_plat_app
    tid = _ids["demo"]
    _contexto(con, tid)
    with con.cursor() as cur:
        reg = modelo.criar_registro(cur, tid, codigo="S-010", tipo="loteamento")
        modelo.criar_parcela(cur, tid, tipo="lote", codigo="X-1", registro_id=reg["id"],
                             anel=[(0, 0), (10, 0), (10, 10), (0, 10)])
        modelo.criar_parcela(cur, tid, tipo="servidao", codigo="S-1", registro_id=reg["id"],
                             anel=[(0, 0), (10, 0), (10, 10), (0, 10)])
        r = validacao.sobreposicoes(cur, tenant_id=tid)
        assert r["total"] == 0


# ------------------------------------------------------------------ vocabulário fechado + RLS (portões a e e)


def test_vocabulario_fechado_recusa_fora_do_vocabulario(conexao_plat_app, _ids):
    con = conexao_plat_app
    tid = _ids["demo"]
    _contexto(con, tid)
    with con.cursor() as cur:
        reg = modelo.criar_registro(cur, tid, codigo="V-001", tipo="escritura")
        with pytest.raises(ErroAPI) as e:
            modelo.criar_parcela(cur, tid, tipo="matricula", codigo="M-1", registro_id=reg["id"],
                                 anel=[(0, 0), (1, 0), (1, 1)])
        assert e.value.status_code == 422
        with pytest.raises(ErroAPI) as e2:
            modelo.criar_registro(cur, tid, codigo="V-002", tipo="planta_avaliada")
        assert e2.value.status_code == 422


def test_rls_inquilino_b_nao_ve_parcela_de_a(conexao_plat_app, _ids):
    con = conexao_plat_app
    with con.cursor() as cur:
        _contexto(con, _ids["demo"])
        reg = modelo.criar_registro(cur, _ids["demo"], codigo="RLS-001", tipo="loteamento")
        _lote_criado(cur, _ids["demo"], "L-RSS", reg["id"])
    _contexto(con, _ids["demo2"])
    with con.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM plat.parcela")
        assert cur.fetchone()["n"] == 0
        cur.execute("SELECT count(*) AS n FROM plat.v_parcela_historico")
        assert cur.fetchone()["n"] == 0
        cur.execute("SELECT count(*) AS n FROM plat.parcela_linha")
        assert cur.fetchone()["n"] == 0
        cur.execute("SELECT count(*) AS n FROM plat.parcela_registro")
        assert cur.fetchone()["n"] == 0


# ------------------------------------------------------------------ paridade escrita (portão f)


def test_paridade_escrita():
    doc = Path(__file__).resolve().parents[3] / "docs" / "PARIDADE_PARCELAS.md"
    assert doc.exists(), "docs/PARIDADE_PARCELAS.md não existe"
    texto = doc.read_text(encoding="utf-8")
    for termo in ("Records", "Retired By Record", "parcel type", "COGO", "lineage"):
        assert termo in texto, f"paridade sem '{termo}'"
