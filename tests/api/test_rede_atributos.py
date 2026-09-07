"""Atributos de rede (item L4-01-d-atributos-de-rede; migração 20260907T1239).

Cláusulas do portão provadas aqui, com uma rede sintética pequena (a escala real, com concordância de fase
contra a BDGD real, está em `test_rede_atributos_medida.py`, marcador `lento`):

1. `plat.rede_atributo` declara propagável/apoia-traversabilidade por atributo real do pacote
   (`test_pacote_marca_fase_propagavel_e_p_n_ope_traversabilidade`) e semeia as linhas sintéticas dos
   atributos calculados (`test_atributos_calculados_semeados_por_grupo`);
2. sincronização por LOTE: tensão/capacidade copiadas para a topologia e aresta interna do dispositivo criada
   para a chave de dois terminais, nunca para o transformador (`test_sincronizar_lote_...`);
3. sincronização por TRIGGER na edição: abrir a chave derruba `traversavel` sem passar pela rota de lote
   (`test_trigger_sincroniza_estado_dispositivo_na_edicao`);
4. substituição por regra: chave de transferência troca a fase declarada
   (`test_substituicao_troca_fase_declarada_por_regra`);
5. refutação do enunciado: mudar `FAS_CON` a montante muda a jusante inteira e não muda ramo irmão
   (`test_refutacao_propagacao_nao_vaza_para_irmao`); abrir uma chave derruba `traversável` da aresta e zera
   `subrede` do lado morto (`test_refutacao_chave_aberta_desconecta_e_zera_subrede`).

⛔ FRONTEIRA ACHADA ao escrever este arquivo (não é defeito deste item): `topologia.habilitar` (L4-01-b) funde
DIRETO as duas pontas de trecho que se tocam sempre que são do MESMO grupo — regra pensada para um trecho
partido em vários pedaços sem dispositivo no meio. Quando um dispositivo de DOIS terminais do MESMO tier
(o caso normal de uma chave em série na média tensão, tronco e jusante ambos `trecho_de_media_tensao`) senta
exatamente sobre esse encontro, a fusão trecho-trecho funde as duas pontas ENTRE SI, e os dois terminais da
chave caem no MESMO grupo de união — vira UM nó só, não dois. `sincronizar_topologia_lote` detecta isto
corretamente (conta em `ignorados_sem_dois_nos`, nunca cria a aresta interna) — é a resposta honesta, não um
bug deste item. Os testes de dispositivo abaixo, por isso, montam a topologia MANUALMENTE (dois nós de
terminal distintos, cada um ligado a um lado) em vez de passar por `habilitar()` — testam a mecânica de
atributos.py isolada da ambiguidade de construção, que é escopo de L4-01-b/um item futuro (registrado no
handoff). A medição em escala real (`test_rede_atributos_medida.py`) mede essa mesma fronteira contra os
dados de verdade da cooperativa."""

import psycopg2
import pytest

from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.conftest import PREFIXO_TESTE
from tests.api.test_rls import ids_por_slug

pytestmark = pytest.mark.usefixtures("limpeza_de_residuos")


def _criar_rede(sessao, sufixo, limpar):
    r = sessao.post("/api/rede", json={"nome": f"{PREFIXO_TESTE}-attr-{sufixo}", "disciplina": "eletrica"})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    limpar.append((sessao, rid))
    return rid


def _importar_eletrica(sessao, rid):
    from app.rede_utilidades import instalados

    bruto = instalados.bruto("eletrica-br")
    r = sessao.post(f"/api/rede/{rid}/pacote", content=bruto, headers={"Content-Type": "application/json"})
    assert r.status_code == 201, r.text
    return r.json()


def _linha(sessao, rid, coordenadas, grupo="trecho_de_media_tensao", tipo_codigo=1):
    r = sessao.post(f"/api/rede/{rid}/feicoes/linhas",
                     json={"tipo_codigo": tipo_codigo, "grupo": grupo, "coordenadas": coordenadas})
    assert r.status_code == 201, r.text
    return r.json()


def _ponto(sessao, rid, lon, lat, grupo, tipo_codigo):
    r = sessao.post(f"/api/rede/{rid}/feicoes/pontos",
                     json={"tipo_codigo": tipo_codigo, "grupo": grupo, "lon": lon, "lat": lat})
    assert r.status_code == 201, r.text
    return r.json()


def _habilitar(sessao, rid):
    r = sessao.post(f"/api/rede/{rid}/topologia/habilitar")
    assert r.status_code == 201, r.text
    return r.json()


def _conectar(env, tenant_id, usuario_id):
    """Conexão psycopg2 direta com o contexto de RLS setado em nível de SESSÃO (`is_local=false`): os
    testes deste arquivo fazem vários `commit()` seguidos e o contexto TEM de sobreviver a eles — ao
    contrário de `tests.api.test_rls.contexto`, que é por transação (`is_local=true`), pensado para um
    único `rollback()` no fim."""
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    con.autocommit = False
    with con.cursor() as cur:
        cur.execute(
            "SELECT set_config('plat.tenant_id', %s, false), set_config('plat.usuario_id', %s, false), "
            "set_config('plat.login', %s, false)",
            (str(tenant_id), str(usuario_id), "teste-l401d"),
        )
    return con


def _montar_dois_terminais(cur, rid, tronco_id, chave_id, jusante_id):
    """Monta manualmente a topologia mínima de um dispositivo de DOIS terminais entre dois trechos (ver
    fronteira no docstring do módulo: `habilitar()` funde os dois lados num nó só quando ambos são do mesmo
    grupo/tier). Cria os 2 nós de terminal da chave (`rede_topo_no`, origem_id=chave), MAIS um nó `conexao`
    em cada ponta livre de cada trecho (a extremidade de montante do tronco e a extremidade de jusante do
    ramal) — `_carregar_grafo` só enxerga uma aresta de linha quando os DOIS lados têm nó, então uma ponta
    NULA (dispositivo em série visto de fora) sumiria do grafo por inteiro, não só ficaria "aberta". Cria as
    2 arestas de trecho já ligadas nos 4 nós. Devolve (no_montante, no_terminal_1, no_terminal_2, no_jusante).
    O resto (dispositivo interno) é `sincronizar_topologia_lote`, a função sob teste."""
    cur.execute(
        "INSERT INTO plat.rede_topo_no(id, tenant_id, rede_id, papel, geom) "
        "SELECT gen_random_uuid(), tenant_id, rede_id, 'conexao', ST_StartPoint(geom) "
        "FROM plat.rede_feicao_linha WHERE id = %s::uuid RETURNING id",
        (tronco_id,),
    )
    no_montante = str(cur.fetchone()["id"])
    cur.execute(
        "INSERT INTO plat.rede_topo_no(id, tenant_id, rede_id, papel, geom) "
        "SELECT gen_random_uuid(), tenant_id, rede_id, 'conexao', ST_EndPoint(geom) "
        "FROM plat.rede_feicao_linha WHERE id = %s::uuid RETURNING id",
        (jusante_id,),
    )
    no_jusante = str(cur.fetchone()["id"])

    nos = []
    for num in (1, 2):
        cur.execute(
            "INSERT INTO plat.rede_topo_no(id, tenant_id, rede_id, papel, tipo_id, origem_id, terminal_num, geom) "
            "SELECT gen_random_uuid(), p.tenant_id, p.rede_id, 'terminal', p.tipo_id, p.id, %s, p.geom "
            "FROM plat.rede_feicao_ponto p WHERE p.id = %s::uuid RETURNING id",
            (num, chave_id),
        )
        nos.append(str(cur.fetchone()["id"]))

    def inserir_aresta(feicao_id, no_origem, no_destino):
        cur.execute(
            "INSERT INTO plat.rede_topo_aresta(id, tenant_id, rede_id, grupo_id, tipo_id, origem_id, "
            "no_origem_id, no_destino_id, comprimento_m, fase_bitmask, atributos, geom) "
            "SELECT gen_random_uuid(), f.tenant_id, f.rede_id, t.grupo_id, f.tipo_id, f.id, "
            "%s::uuid, %s::uuid, ST_Length(f.geom::geography), f.fase_bitmask, f.atributos, f.geom "
            "FROM plat.rede_feicao_linha f JOIN plat.rede_tipo t ON t.id = f.tipo_id WHERE f.id = %s::uuid",
            (no_origem, no_destino, feicao_id),
        )

    inserir_aresta(tronco_id, no_montante, nos[0])
    inserir_aresta(jusante_id, nos[1], no_jusante)
    return no_montante, nos[0], nos[1], no_jusante


@pytest.fixture
def limpar_redes(sessao_a):
    criadas = []
    yield criadas
    for sessao, rid in criadas:
        sessao.delete(f"/api/rede/{rid}")


@pytest.fixture
def ctx(sessao_a, env):
    """(tenant_id, usuario_id) de `demo` — o mesmo inquilino de `sessao_a` — para abrir uma conexão de
    banco direta com o contexto de RLS certo."""
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        tenant_id = ids_por_slug(con)["demo"]
    finally:
        con.close()
    usuario_id = sessao_a.get("/api/eu").json()["id"]
    return tenant_id, usuario_id


def test_pacote_marca_fase_propagavel_e_p_n_ope_traversabilidade(sessao_a, limpar_redes, env, ctx):
    rid = _criar_rede(sessao_a, "flags", limpar_redes)
    resultado = _importar_eletrica(sessao_a, rid)
    assert resultado["contagens"]["atributos_flags"]["fase_propagavel"] > 0, resultado
    assert resultado["contagens"]["atributos_flags"]["traversabilidade"] > 0, resultado

    con = _conectar(env, *ctx)
    try:
        with con.cursor() as cur:
            cur.execute(
                "SELECT codigo, propagavel, apoia_traversabilidade FROM plat.rede_atributo "
                "WHERE rede_id = %s::uuid AND (codigo LIKE '%%fas_con' OR codigo LIKE '%%p_n_ope')",
                (rid,))
            linhas = {r["codigo"]: (r["propagavel"], r["apoia_traversabilidade"]) for r in cur.fetchall()}
    finally:
        con.close()
    assert linhas["ssdmt_fas_con"] == (True, False), linhas
    assert linhas["unsemt_p_n_ope"] == (False, True), linhas
    # nunca marca os dois no mesmo atributo por acidente (o enunciado declara um exemplo de cada)
    assert linhas["ssdmt_fas_con"][1] is False
    assert linhas["unsemt_p_n_ope"][0] is False


def test_atributos_calculados_semeados_por_grupo(sessao_a, limpar_redes, env, ctx):
    rid = _criar_rede(sessao_a, "calc", limpar_redes)
    resultado = _importar_eletrica(sessao_a, rid)
    assert resultado["contagens"]["atributos_calculados"] > 0, resultado

    con = _conectar(env, *ctx)
    try:
        with con.cursor() as cur:
            cur.execute(
                "SELECT g.codigo AS grupo, a.codigo, a.origem FROM plat.rede_atributo a "
                "JOIN plat.rede_grupo g ON g.id = a.grupo_id "
                "WHERE a.rede_id = %s::uuid AND a.origem->>'calculado' = 'true' "
                "AND g.codigo = 'trecho_de_media_tensao'",
                (rid,))
            calc = {r["codigo"] for r in cur.fetchall()}
    finally:
        con.close()
    assert calc == {"comprimento_geodesico", "is_connected", "subrede"}, calc


def test_sincronizar_lote_copia_tensao_e_cria_aresta_de_dispositivo(sessao_a, limpar_redes, env, ctx):
    rid = _criar_rede(sessao_a, "lote", limpar_redes)
    _importar_eletrica(sessao_a, rid)
    tr1 = _linha(sessao_a, rid, [[-46.30, -23.40], [-46.29, -23.40]])
    chave = _ponto(sessao_a, rid, -46.29, -23.40, "chave_de_media_tensao", 1)  # chave_faca, dois_terminais
    tr2 = _linha(sessao_a, rid, [[-46.29, -23.40], [-46.28, -23.40]])
    trafo = _ponto(sessao_a, rid, -46.28, -23.40, "transformador_de_distribuicao", 1)  # nunca ganha aresta interna

    con = _conectar(env, *ctx)
    try:
        with con.cursor() as cur:
            _montar_dois_terminais(cur, rid, tr1["id"], chave["id"], tr2["id"])
            cur.execute("UPDATE plat.rede_feicao_linha SET tensao_nominal_kv = 13.8, capacidade_kva = 300 "
                       "WHERE id = %s::uuid", (tr1["id"],))
        con.commit()

        r = sessao_a.post(f"/api/rede/{rid}/atributos/sincronizar")
        assert r.status_code == 200, r.text
        resumo = r.json()
        assert resumo["arestas_tensao_capacidade_atualizadas"] >= 1, resumo
        assert resumo["dispositivo_arestas_criadas"] == 1, resumo
        assert resumo["ignorados_transformacao"] == 1, resumo

        with con.cursor() as cur:
            cur.execute("SELECT tensao_nominal_kv, capacidade_kva FROM plat.rede_topo_aresta "
                       "WHERE origem_id = %s::uuid", (tr1["id"],))
            r2 = cur.fetchone()
            assert float(r2["tensao_nominal_kv"]) == 13.8 and float(r2["capacidade_kva"]) == 300, r2

            cur.execute("SELECT count(*) AS n FROM plat.rede_topo_dispositivo_aresta WHERE origem_id = %s::uuid",
                       (chave["id"],))
            assert cur.fetchone()["n"] == 1

            cur.execute("SELECT count(*) AS n FROM plat.rede_topo_dispositivo_aresta WHERE origem_id = %s::uuid",
                       (trafo["id"],))
            assert cur.fetchone()["n"] == 0
    finally:
        con.close()


def test_trigger_sincroniza_estado_dispositivo_na_edicao(sessao_a, limpar_redes, env, ctx):
    rid = _criar_rede(sessao_a, "trig", limpar_redes)
    _importar_eletrica(sessao_a, rid)
    tronco = _linha(sessao_a, rid, [[-47.0, -23.0], [-46.99, -23.0]])
    chave = _ponto(sessao_a, rid, -46.99, -23.0, "chave_de_media_tensao", 1)
    jusante = _linha(sessao_a, rid, [[-46.99, -23.0], [-46.98, -23.0]])

    con = _conectar(env, *ctx)
    try:
        with con.cursor() as cur:
            _montar_dois_terminais(cur, rid, tronco["id"], chave["id"], jusante["id"])
        con.commit()

        r = sessao_a.post(f"/api/rede/{rid}/atributos/sincronizar")
        assert r.status_code == 200, r.text

        with con.cursor() as cur:
            cur.execute("SELECT traversavel FROM plat.rede_topo_dispositivo_aresta WHERE origem_id = %s::uuid",
                       (chave["id"],))
            assert cur.fetchone()["traversavel"] is True

            # edição direta na feição: o TRIGGER da migração cobre isto, sem passar pela rota de lote
            cur.execute("UPDATE plat.rede_feicao_ponto SET estado_dispositivo = 'aberto' WHERE id = %s::uuid",
                       (chave["id"],))
        con.commit()
        with con.cursor() as cur:
            cur.execute("SELECT traversavel FROM plat.rede_topo_dispositivo_aresta WHERE origem_id = %s::uuid",
                       (chave["id"],))
            assert cur.fetchone()["traversavel"] is False
    finally:
        con.close()


def test_refutacao_propagacao_nao_vaza_para_irmao(sessao_a, limpar_redes, env, ctx):
    """adversário: mudar FAS_CON de um trecho a MONTANTE muda a fase propagada de tudo a jusante dali, e
    NÃO muda o ramo IRMÃO (outro alimentador, sem nó em comum com o primeiro)."""
    rid = _criar_rede(sessao_a, "refuta-fase", limpar_redes)
    _importar_eletrica(sessao_a, rid)
    tronco = _linha(sessao_a, rid, [[-45.0, -22.0], [-44.99, -22.0]])
    ramo = _linha(sessao_a, rid, [[-44.99, -22.0], [-44.98, -22.0]])
    irmao = _linha(sessao_a, rid, [[-40.0, -20.0], [-39.99, -20.0]])
    _habilitar(sessao_a, rid)

    from app.rede_utilidades import atributos

    con = _conectar(env, *ctx)
    try:
        with con.cursor() as cur:
            cur.execute("SELECT no_origem_id FROM plat.rede_topo_aresta WHERE origem_id = %s::uuid",
                       (tronco["id"],))
            raiz = str(cur.fetchone()["no_origem_id"])

            atributos.propagar_fase(cur, ctx[0], rid, raizes={"teste": raiz})
        con.commit()
        with con.cursor() as cur:
            cur.execute("SELECT fase_propagada FROM plat.rede_topo_aresta WHERE origem_id = %s::uuid", (ramo["id"],))
            fase_ramo_antes = cur.fetchone()["fase_propagada"]
            cur.execute("SELECT fase_propagada FROM plat.rede_topo_aresta WHERE origem_id = %s::uuid", (irmao["id"],))
            fase_irmao_antes = cur.fetchone()["fase_propagada"]

            # muda FAS_CON (fase_bitmask) do trecho a MONTANTE; o trigger da migração já copia para a
            # aresta correspondente
            cur.execute("UPDATE plat.rede_feicao_linha SET fase_bitmask = 2 WHERE id = %s::uuid", (tronco["id"],))
        con.commit()
        with con.cursor() as cur:
            atributos.propagar_fase(cur, ctx[0], rid, raizes={"teste": raiz})
        con.commit()
        with con.cursor() as cur:
            cur.execute("SELECT fase_propagada FROM plat.rede_topo_aresta WHERE origem_id = %s::uuid", (ramo["id"],))
            fase_ramo_depois = cur.fetchone()["fase_propagada"]
            cur.execute("SELECT fase_propagada FROM plat.rede_topo_aresta WHERE origem_id = %s::uuid", (irmao["id"],))
            fase_irmao_depois = cur.fetchone()["fase_propagada"]
    finally:
        con.close()

    assert fase_ramo_depois == 2 and fase_ramo_depois != fase_ramo_antes, (fase_ramo_antes, fase_ramo_depois)
    assert fase_irmao_depois == fase_irmao_antes, (fase_irmao_antes, fase_irmao_depois)


def test_refutacao_chave_aberta_desconecta_e_zera_subrede(sessao_a, limpar_redes, env, ctx):
    """adversário: abrir uma chave derruba `traversável` da aresta de dispositivo, e a `subrede` do lado
    morto vai a NULO depois de recalcular a conectividade."""
    rid = _criar_rede(sessao_a, "refuta-conex", limpar_redes)
    _importar_eletrica(sessao_a, rid)
    tronco = _linha(sessao_a, rid, [[-43.0, -21.0], [-42.99, -21.0]])
    chave = _ponto(sessao_a, rid, -42.99, -21.0, "chave_de_media_tensao", 1)
    morto = _linha(sessao_a, rid, [[-42.99, -21.0], [-42.98, -21.0]])

    from app.rede_utilidades import atributos

    con = _conectar(env, *ctx)
    try:
        with con.cursor() as cur:
            no_montante, _no1, _no2, _no_jusante = _montar_dois_terminais(cur, rid, tronco["id"], chave["id"], morto["id"])
        con.commit()

        r = sessao_a.post(f"/api/rede/{rid}/atributos/sincronizar")
        assert r.status_code == 200, r.text

        with con.cursor() as cur:
            atributos.recalcular_conectividade(cur, ctx[0], rid, raizes={"raiz": no_montante})
        con.commit()
        with con.cursor() as cur:
            cur.execute("SELECT is_connected, subrede_codigo FROM plat.rede_topo_aresta WHERE origem_id = %s::uuid",
                       (morto["id"],))
            antes = cur.fetchone()
            assert antes["is_connected"] is True and antes["subrede_codigo"] is not None, antes

            cur.execute("UPDATE plat.rede_feicao_ponto SET estado_dispositivo = 'aberto' WHERE id = %s::uuid",
                       (chave["id"],))
        con.commit()
        with con.cursor() as cur:
            cur.execute("SELECT traversavel FROM plat.rede_topo_dispositivo_aresta WHERE origem_id = %s::uuid",
                       (chave["id"],))
            assert cur.fetchone()["traversavel"] is False

            atributos.recalcular_conectividade(cur, ctx[0], rid, raizes={"raiz": no_montante})
        con.commit()
        with con.cursor() as cur:
            cur.execute("SELECT is_connected, subrede_codigo FROM plat.rede_topo_aresta WHERE origem_id = %s::uuid",
                       (morto["id"],))
            depois = cur.fetchone()
    finally:
        con.close()

    assert depois["is_connected"] is False, depois
    assert depois["subrede_codigo"] is None, depois


def test_substituicao_troca_fase_declarada_por_regra(sessao_a, limpar_redes, env, ctx):
    rid = _criar_rede(sessao_a, "subst", limpar_redes)
    _importar_eletrica(sessao_a, rid)

    con = _conectar(env, *ctx)
    try:
        with con.cursor() as cur:
            cur.execute(
                "SELECT id FROM plat.rede_tipo WHERE rede_id = %s::uuid AND chave = 'chave_faca'", (rid,))
            tipo_chave_id = str(cur.fetchone()["id"])
    finally:
        con.close()

    r = sessao_a.post(f"/api/rede/{rid}/atributos/substituicoes",
                      json={"tipo_id": tipo_chave_id, "atributo_codigo": "fase", "de_valor": 1, "para_valor": 3,
                            "descricao": "chave de transferência de teste: A -> AB"})
    assert r.status_code == 201, r.text

    tronco = _linha(sessao_a, rid, [[-41.0, -19.0], [-40.99, -19.0]])
    chave = _ponto(sessao_a, rid, -40.99, -19.0, "chave_de_media_tensao", 1)
    jusante = _linha(sessao_a, rid, [[-40.99, -19.0], [-40.98, -19.0]])

    from app.rede_utilidades import atributos

    con = _conectar(env, *ctx)
    try:
        with con.cursor() as cur:
            no_montante, _no1, _no2, _no_jusante = _montar_dois_terminais(cur, rid, tronco["id"], chave["id"], jusante["id"])
            cur.execute("UPDATE plat.rede_feicao_linha SET fase_bitmask = 1 WHERE id = %s::uuid", (tronco["id"],))
            cur.execute("UPDATE plat.rede_topo_aresta SET fase_bitmask = 1 WHERE origem_id = %s::uuid",
                       (tronco["id"],))
        con.commit()

        r = sessao_a.post(f"/api/rede/{rid}/atributos/sincronizar")
        assert r.status_code == 200, r.text

        with con.cursor() as cur:
            atributos.propagar_fase(cur, ctx[0], rid, raizes={"raiz": no_montante})
        con.commit()
        with con.cursor() as cur:
            cur.execute("SELECT fase_propagada FROM plat.rede_topo_aresta WHERE origem_id = %s::uuid",
                       (jusante["id"],))
            fase_jusante = cur.fetchone()["fase_propagada"]
    finally:
        con.close()
    assert fase_jusante == 3, fase_jusante  # a regra trocou A(1) por AB(3) ao atravessar a chave
