"""Ajuste por mínimos quadrados (item L4-parcelas-03-ajuste-e-qualidade).

Portão, cláusula por cláusula:
  b) "ajuste por mínimos quadrados em malha sintética de 20 parcelas com 3 pontos de controle:
     resíduos <= tolerância e coordenadas reproduzem a solução analítica (teste)" ->
     test_malha_20_parcelas_3_controles_reproduz_solucao_analitica;
  c) "'analisar' não altera geometria, 'aplicar' altera e grava versão" ->
     test_analisar_nao_escreve_checksum + test_aplicar_move_e_grava_versao;
  d) "analyzeByLSA/applyLSA da fachada mapeados" -> test_fachada_analyze_* e apply (HTTP);
  refutação: "adversário adiciona medida grosseiramente errada (1 m em 100) e confere que o
  resíduo a destaca e que o ajuste sem ela converge" -> test_medida_grosseira_*.

A malha sintética: 4x5 lotes de 100 x 20 m (20 parcelas, 30 nós, 49 linhas, 98 observações).
As POSIÇÕES iniciais dos nós carregam desvio determinístico de até 3 cm (o que uma malha
medida parece); as MEDIDAS COGO (rumo + distância) são calculadas EXATAS sobre as coordenadas
verdadeiras — a solução analítica. 3 nós são controle (categoria 'controle', datum).

Banco: suíte conecta como o app da TRILHA; inquilino demo; GUC local à transação; a fixture
desfaz tudo (padrão test_modelo).
"""

import math

import psycopg2
import pytest

from app.erros import ErroAPI
from app.parcelas import ajuste, modelo


# desvio determinístico da posição inicial: até 3 cm, sem aleatório (a rodada é reproduzível)
def _desvio(i: int, j: int, k: int) -> float:
    return (((i * 7 + j * 11 + k * 13) % 13) - 6) / 200.0


def _malha(cur, tid, *, nx=4, ny=5, largura=100.0, fundo=20.0, registro_id=None):
    """Malha sintética. Nós com POSIÇÃO inicial desviada; linhas com medida EXATA das
    coordenadas verdadeiras; parcelas com o anel verdadeiro (o estado do banco é 'malha medida
    com erro de posição, observações consistentes'). Devolve ids e a verdade."""
    verdade = {}
    nos = {}
    for j in range(ny + 1):
        for i in range(nx + 1):
            x, y = i * largura, j * fundo
            controle = (i, j) in ((0, 0), (nx, 0), (0, ny))
            xi = x + 0.0 if controle else x + _desvio(i, j, 1)
            yi = y + 0.0 if controle else y + _desvio(i, j, 2)
            p = modelo.criar_ponto(cur, tid, x=xi, y=yi,
                                   categoria="controle" if controle else "apoio",
                                   nome=f"N{i}-{j}")
            nos[(i, j)] = str(p["id"])
            verdade[str(p["id"])] = (x, y)
    linhas = {}
    for j in range(ny + 1):
        for i in range(nx):
            a, b = nos[(i, j)], nos[(i + 1, j)]
            linhas[("h", i, j)] = (a, b) if a <= b else (b, a)
    for j in range(ny):
        for i in range(nx + 1):
            a, b = nos[(i, j)], nos[(i, j + 1)]
            linhas[("v", i, j)] = (a, b) if a <= b else (b, a)
    id_linha = {}
    for chave, (a, b) in linhas.items():
        (xa, ya), (xb, yb) = verdade[a], verdade[b]
        rumo = math.degrees(math.atan2(xb - xa, yb - ya)) % 360.0
        dist = math.hypot(xb - xa, yb - ya)
        id_linha[chave] = str(modelo.criar_linha(
            cur, tid, de_ponto_id=a, para_ponto_id=b, rumo_graus=rumo, distancia_m=dist,
            tipo_cogo="reta", registro_id=registro_id)["id"])
    parcelas = []
    for j in range(ny):
        for i in range(nx):
            anel_nos = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
            anel = [verdade[nos[n]] for n in anel_nos]
            borda = [("h", i, j), ("v", i + 1, j), ("h", i, j + 1), ("v", i, j)]
            p = modelo.criar_parcela(cur, tid, tipo="lote", codigo=f"AJ-{i}-{j}",
                                     registro_id=registro_id, anel=anel,
                                     linha_ids=[id_linha[c] for c in borda])
            parcelas.append(str(p["id"]))
    return {"nos": nos, "verdade": verdade, "linhas": id_linha, "parcelas": parcelas}


def _contexto(con, tenant_id):
    with con.cursor() as cur:
        cur.execute("SET search_path = plat, public")
        cur.execute(
            "SELECT set_config('plat.tenant_id', %s, true), set_config('plat.usuario_id', %s, true), "
            "set_config('plat.login', %s, true)", (str(tenant_id), "0", "teste"))


@pytest.fixture
def malha(conexao_plat_app, _ids):
    con = conexao_plat_app
    tid = _ids["demo"]
    _contexto(con, tid)
    with con.cursor() as cur:
        origem = modelo.criar_registro(cur, tid, codigo="AJ-001", tipo="loteamento")
        m = _malha(cur, tid, registro_id=str(origem["id"]))
    return {"con": con, "tid": tid, "malha": m}


def test_malha_20_parcelas_3_controles_reproduz_solucao_analitica(malha):
    """Portão (b): 20 parcelas, 3 controles; resíduos <= tolerância e as coordenadas ajustadas
    voltam para as verdadeiras (a solução analítica da malha sem erro de medida)."""
    con, m = malha["con"], malha["malha"]
    assert len(m["parcelas"]) == 20
    with con.cursor() as cur:
        r = ajuste.analisar(cur, malha["tid"], parcela_ids=m["parcelas"])
    assert r["convergiu"] is True
    assert r["observacoes"] == 98 and r["incognitas"] == 54
    assert r["redundancia"] == 44
    movidos = [p for p in r["pontos"] if not p["fixo"]]
    assert len(movidos) == 27
    for p in movidos:
        vx, vy = m["verdade"][p["id"]]
        assert p["x"] == pytest.approx(vx, abs=0.001), p
        assert p["y"] == pytest.approx(vy, abs=0.001), p
        # o deslocamento é o desvio inicial determinístico (até ~4,2 cm), não resíduo
        assert p["deslocamento_m"] <= 0.05
    for ln in r["linhas"]:
        assert abs(ln["residuo_distancia_m"]) <= 0.02  # sigma da categoria 'medido'
        assert ln["normalizado"] <= 3.0
    assert r["suspeitas"] == []
    # com a tolerância FINA o solver refina até o limite numérico e o sigma zero vai a ~0:
    # as observações são exatas, então a solução analítica é recuperada de verdade
    with con.cursor() as cur:
        r2 = ajuste.analisar(cur, malha["tid"], parcela_ids=m["parcelas"], tolerancia_m=0.001)
    assert r2["convergiu"] is True
    assert r2["sigma_zero"] <= 0.01
    for p in [p for p in r2["pontos"] if not p["fixo"]]:
        vx, vy = m["verdade"][p["id"]]
        assert p["x"] == pytest.approx(vx, abs=1e-4), p
        assert p["y"] == pytest.approx(vy, abs=1e-4), p
    for ln in r2["linhas"]:
        assert ln["normalizado"] <= 0.5


def test_analisar_nao_escreve_checksum(malha):
    """Portão (c), primeiro lado + refutação: 'analisar' não escreve NADA — checksum das
    coordenadas (e da precisão) igual antes e depois, dentro da MESMA transação aberta."""
    con, m = malha["con"], malha["malha"]
    _contexto(con, malha["tid"])

    def checksum(cur) -> str:
        cur.execute(
            "SELECT md5(string_agg(ST_X(geom)::text || ',' || ST_Y(geom)::text || ',' || "
            "COALESCE(precisao_xy_m::text,'-'), '|' ORDER BY id)) AS h FROM plat.parcela_ponto "
            "WHERE tenant_id = %s", (malha["tid"],))
        return cur.fetchone()["h"]

    with con.cursor() as cur:
        antes = checksum(cur)
        ajuste.analisar(cur, malha["tid"], parcela_ids=m["parcelas"])
        depois = checksum(cur)
    assert antes == depois


def test_aplicar_move_e_grava_versao(malha):
    """Portão (c), segundo lado: 'aplicar' move os pontos no banco (geometria de linha e de
    parcela volta a fechar) e grava a versão em plat.parcela_ajuste."""
    con, m, tid = malha["con"], malha["malha"], malha["tid"]
    _contexto(con, tid)
    with con.cursor() as cur:
        # tolerância zero: move todo ponto com deslocamento > 0. Os 27 pontos livres se movem:
        # até o nó que NASCE exato pela fórmula determinística (desvio inicial 0,0) é puxado
        # pela rede (7,7e-05 m) — é isso que um ajuste de rede faz, e a regra da doc é
        # estritamente maior que a tolerância
        r = ajuste.aplicar(cur, tid, parcela_ids=m["parcelas"], tolerancia_movimento_m=0.0)
        assert len(r["movidos"]) == 27
        assert r["relatorio"]["convergiu"] is True
        # as posições no banco agora são a verdade (solução analítica)
        for pid, (vx, vy) in m["verdade"].items():
            cur.execute("SELECT ST_X(geom) AS x, ST_Y(geom) AS y FROM plat.parcela_ponto "
                        "WHERE id = %s::uuid", (pid,))
            pos = cur.fetchone()
            assert float(pos["x"]) == pytest.approx(vx, abs=0.002)
            assert float(pos["y"]) == pytest.approx(vy, abs=0.002)
        # a linha continua sendo os dois pontos (invariante do modelo)
        for lid in m["linhas"].values():
            cur.execute(
                "SELECT count(*) AS n FROM plat.parcela_linha l "
                "JOIN plat.parcela_ponto a ON a.id = l.de_ponto_id "
                "JOIN plat.parcela_ponto b ON b.id = l.para_ponto_id "
                "WHERE l.id = %s::uuid AND NOT ST_Equals(l.geom, ST_MakeLine(a.geom, b.geom))", (lid,))
            assert cur.fetchone()["n"] == 0
        # a versão ficou gravada (append-only) com o relatório integral
        cur.execute("SELECT sigma_zero, analise FROM plat.parcela_ajuste WHERE id = %s::uuid",
                    (r["id"],))
        v = cur.fetchone()
        assert v is not None and v["analise"]["pontos"]  # o relatório integral está lá
        # a área da parcela voltou ao retângulo exato
        cur.execute("SELECT area_calculada_m2 FROM plat.parcela WHERE id = %s::uuid",
                    (m["parcelas"][0],))
        assert float(cur.fetchone()["area_calculada_m2"]) == pytest.approx(2000.0, abs=0.01)


def test_medida_grosseira_1_em_100_destacada_e_sem_ela_converge(malha):
    """Refutação: +1 m numa linha de 100 m; o resíduo a DESTACA — é a cabeça da lista, com o
    maior normalizado de longe — e o ajuste SEM ela converge com todo resíduo dentro do sigma."""
    con, m, tid = malha["con"], malha["malha"], malha["tid"]
    _contexto(con, tid)
    alvo = m["linhas"][("h", 2, 2)]  # linha de 100 m no miolo da malha
    with con.cursor() as cur:
        cur.execute("UPDATE plat.parcela_linha SET distancia_m = distancia_m + 1.0 "
                    "WHERE id = %s::uuid", (alvo,))
        r = ajuste.analisar(cur, tid, parcela_ids=m["parcelas"])
    assert r["suspeitas"] and r["suspeitas"][0] == alvo  # a medida grosseira é suspeita nº 1
    assert r["maior_residuo"]["linha_id"] == alvo
    assert r["maior_residuo"]["normalizado"] > 3.0
    # domina a lista: o segundo lugar fica muito atrás (o erro é DELA, não da vizinhança)
    assert r["linhas"][0]["normalizado"] > 3.0 * r["linhas"][1]["normalizado"]
    assert abs(r["maior_residuo"]["residuo_distancia_m"]) > 0.3  # o erro aparece, não se dilui
    # sem a medida grosseira: converge limpo
    with con.cursor() as cur:
        r2 = ajuste.analisar(cur, tid, parcela_ids=m["parcelas"], sem_linhas=[alvo])
    assert r2["convergiu"] is True
    assert r2["suspeitas"] == []
    assert r2["linhas_excluidas"] == [alvo]
    assert all(ln["normalizado"] <= 3.0 for ln in r2["linhas"])
    for p in [p for p in r2["pontos"] if not p["fixo"]]:
        vx, vy = m["verdade"][p["id"]]
        assert p["x"] == pytest.approx(vx, abs=0.001)
        assert p["y"] == pytest.approx(vy, abs=0.001)


def test_rede_sem_redundancia_e_recusada(conexao_plat_app, _ids):
    """Uma parcela isolada sem NENHUM controle: 8 observações, 8 incógnitas — nada sobra para
    avaliar resíduo, a análise recusa (422) com o erro próprio."""
    con = conexao_plat_app
    tid = _ids["demo"]
    _contexto(con, tid)
    with con.cursor() as cur:
        origem = modelo.criar_registro(cur, tid, codigo="AJ-002", tipo="loteamento")
        cantos = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        pontos = [modelo.criar_ponto(cur, tid, x=x, y=y) for x, y in cantos]  # nenhum controle
        linhas = [modelo.criar_linha(cur, tid, de_ponto_id=pontos[i]["id"],
                                     para_ponto_id=pontos[(i + 1) % 4]["id"],
                                     rumo_graus=90.0 * i, distancia_m=10.0,
                                     tipo_cogo="reta") for i in range(4)]
        p = modelo.criar_parcela(cur, tid, tipo="lote", codigo="AJ-SOLTA",
                                 registro_id=origem["id"], anel=cantos,
                                 linha_ids=[str(ln["id"]) for ln in linhas])
        with pytest.raises(ErroAPI) as e:
            ajuste.analisar(cur, tid, parcela_ids=[str(p["id"])])
        assert e.value.erro == "rede_sem_redundancia"


def test_categoria_fora_do_vocabulario_e_recusada_pelo_banco(conexao_plat_app, _ids):
    con = conexao_plat_app
    tid = _ids["demo"]
    _contexto(con, tid)
    with con.cursor() as cur:
        a = modelo.criar_ponto(cur, tid, x=0.0, y=0.0)
        b = modelo.criar_ponto(cur, tid, x=10.0, y=0.0)
        with pytest.raises(psycopg2.errors.CheckViolation):
            modelo.criar_linha(cur, tid, de_ponto_id=a["id"], para_ponto_id=b["id"],
                               rumo_graus=90.0, distancia_m=10.0, categoria="olhometro")


# ------------------------------------------------------------------ fachada por HTTP


@pytest.fixture
def malha_http(conexao_plat_app, inquilino_temporario):
    """Malha 2x2 (12 linhas, 24 observações, 3 controles) semeada e COMMITADA num inquilino
    temporário: a fachada roda em transação própria (mesma precedência de test_fachada)."""
    inq = inquilino_temporario
    con = conexao_plat_app
    with con.cursor() as cur:
        cur.execute("SELECT tenant_id FROM plat.auth_login(%s, 'admin')", (inq.slug,))
        tid = cur.fetchone()["tenant_id"]
    _contexto(con, tid)
    with con.cursor() as cur:
        origem = modelo.criar_registro(cur, tid, codigo="AJH-LTM", tipo="loteamento")
        m = _malha(cur, tid, nx=2, ny=2, registro_id=str(origem["id"]))
    con.commit()
    return {"inq": inq, "con": con, "tid": tid, "parcelas": m["parcelas"]}


def test_fachada_analyze_by_lsa_nao_escreve(malha_http):
    inq = malha_http["inq"]
    corpo = {"parcelFeatures": [{"id": pid, "layerId": "parcela"} for pid in malha_http["parcelas"]],
             "analysisType": "WEIGHTED_LEAST_SQUARES", "convergenceTolerance": 0.05}
    r = inq.admin.post("/api/parcelas/fabrica/analyzeByLSA", json=corpo)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["success"] is True and j["exceededTransferLimit"] is False
    assert j["resumo"]["convergiu"] is True and j["resumo"]["suspeitas"] == []
    assert j["resumo"]["observacoes"] == 24 and j["resumo"]["redundancia"] == 12
    assert len(j["pontos"]) == 9 and len(j["linhas"]) == 12
    # a análise não escreveu: as coordenadas no banco continuam as DESVIADAS
    con = malha_http["con"]
    _contexto(con, malha_http["tid"])
    with con.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM plat.parcela_ponto WHERE tenant_id = %s "
                    "AND precisao_xy_m IS NOT NULL", (malha_http["tid"],))
        assert cur.fetchone()["n"] == 0  # nada de precisão a posteriori gravada por análise
        cur.execute("SELECT count(*) AS n FROM plat.parcela_ajuste WHERE tenant_id = %s",
                    (malha_http["tid"],))
        assert cur.fetchone()["n"] == 0  # e nenhuma versão


def test_fachada_apply_lsa_grava_versao(malha_http):
    inq = malha_http["inq"]
    corpo = {"parcelFeatures": [{"id": pid, "layerId": "parcela"} for pid in malha_http["parcelas"]],
             "movementTolerance": 0.005, "updateAttributes": True}
    r = inq.admin.post("/api/parcelas/fabrica/applyLSA", json=corpo)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["success"] is True
    updates = j["serviceEdits"][0]["editedFeatures"]["updates"]
    assert len(updates) == 6  # os 6 nós de apoio da malha 2x2 (3 controles ficam)
    assert all(u["deslocamentoM"] > 0.005 for u in updates)
    assert j["ajuste"]["id"] and j["ajuste"]["redundancia"] == 12
    con = malha_http["con"]
    _contexto(con, malha_http["tid"])
    with con.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM plat.parcela_ajuste WHERE tenant_id = %s",
                    (malha_http["tid"],))
        assert cur.fetchone()["n"] == 1  # a versão gravada
        cur.execute("SELECT count(*) AS n FROM plat.parcela_ponto WHERE tenant_id = %s "
                    "AND categoria = 'apoio' AND precisao_xy_m IS NOT NULL", (malha_http["tid"],))
        assert cur.fetchone()["n"] == 6  # updateAttributes: precisão a posteriori por ponto


def test_fachada_consistency_check_nao_move_nada(malha_http):
    inq = malha_http["inq"]
    corpo = {"parcelFeatures": [{"id": pid, "layerId": "parcela"} for pid in malha_http["parcelas"]],
             "analysisType": "CONSISTENCY_CHECK"}
    r = inq.admin.post("/api/parcelas/fabrica/analyzeByLSA", json=corpo)
    assert r.status_code == 200, r.text
    assert r.json()["resumo"]["convergiu"] is True
    con = malha_http["con"]
    _contexto(con, malha_http["tid"])
    with con.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM plat.parcela_ajuste WHERE tenant_id = %s",
                    (malha_http["tid"],))
        assert cur.fetchone()["n"] == 0
