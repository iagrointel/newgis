"""Testes de domínio dos consumidores e endereços da rede (item L4-20-consumidores-e-enderecos) sobre
rede SINTÉTICA no segundo inquilino de demonstração (demo2) — o primeiro (demo) recebe a carga real da
cooperativa em tests/api/rede/test_consumidores.py, e os dois nunca se tocam (RLS por inquilino).

A rede sintética (perto de Guarulhos, métrica via ST_Transform 31983):

    circuito C1:  n1 --A-- n2 --B-- n3 --D-- n5     E fecha malha n3-n4; F é degenerado (n6-n6);
                         |            |             T1@n2=4 UC, T2@n3=2, T3@n4=5, T4@n5=7,
                         C n4 -------E              T5 a 50 m (fora da tolerância de 10 m) = 100 UC.
    circuito C2:  p0 --H-- p1 com deriva de baixa tensão G (para a camada de endereços).

Árvore de C1 a partir da raiz n2 (maior grau): jusante(A)=0, jusante(B)=2+7=9, jusante(C)=5,
jusante(D)=7; E e F ficam fora (NULL) e entram em trechos_em_malha. Em C2, jusante(H)=0 (raiz p0,
nada a jusante)."""

import pytest

from app import limites
from app.rede import consumidores

N1 = (-46.50000, -23.40000)
N2 = (-46.49990, -23.40000)
N3 = (-46.49980, -23.40000)
N4 = (-46.49990, -23.39990)
N5 = (-46.49970, -23.40000)
N6 = (-46.50000, -23.39980)
P0 = (-46.51000, -23.41000)  # fragmento do circuito C2, a mais de 1 km de C1
P1 = (-46.50980, -23.41000)


def _wkt(p1, p2) -> str:
    return f"LINESTRING({p1[0]} {p1[1]},{p2[0]} {p2[1]})"


@pytest.fixture
def cur_demo2(conexao_plat_app):
    """Cursor do inquilino demo2 com transação revertida no fim (o fixture-mãe faz rollback)."""
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT tenant_id::text AS id FROM plat.auth_login('demo2', 'admin')")
        tid = cur.fetchone()["id"]
        cur.execute("SELECT set_config('plat.tenant_id', %s, false)", (tid,))
        cur.execute(
            "DELETE FROM plat.rede_uc_consumo WHERE tenant_id = plat.tenant_atual();"
            "DELETE FROM plat.rede_uc WHERE tenant_id = plat.tenant_atual();"
            "DELETE FROM plat.rede_trafo WHERE tenant_id = plat.tenant_atual();"
            "DELETE FROM plat.rede_trecho WHERE tenant_id = plat.tenant_atual();"
            "DELETE FROM plat.rede_endereco_sem_rede WHERE tenant_id = plat.tenant_atual();"
            "DELETE FROM plat.rede_endereco WHERE tenant_id = plat.tenant_atual();"
        )
        yield cur
    conexao_plat_app.rollback()


def _trecho(cur, codigo: str, ctmt: str, nivel: str, p1, p2) -> None:
    cur.execute(
        "INSERT INTO plat.rede_trecho (tenant_id, nivel, codigo, ctmt, comprimento_m, geometria)"
        " VALUES (plat.tenant_atual(), %s, %s, %s, 0, ST_GeomFromText(%s, 4674))"
        " ON CONFLICT (tenant_id, nivel, codigo) DO NOTHING",
        (nivel, codigo, ctmt, _wkt(p1, p2)),
    )


def _trafo(cur, codigo: str, ctmt: str, ponto) -> None:
    cur.execute(
        "INSERT INTO plat.rede_trafo (tenant_id, codigo, ctmt, geometria)"
        " VALUES (plat.tenant_atual(), %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4674))"
        " ON CONFLICT (tenant_id, codigo) DO NOTHING",
        (codigo, ctmt, ponto[0], ponto[1]),
    )


def _ucs(cur, trafo: str, n: int) -> None:
    for i in range(n):
        cur.execute(
            "INSERT INTO plat.rede_uc (tenant_id, codigo, ctmt, uni_tr_mt)"
            " VALUES (plat.tenant_atual(), %s, 'C1', %s) ON CONFLICT (tenant_id, codigo) DO NOTHING",
            (f"zt-l4-20-{trafo}-{i}", trafo),
        )


@pytest.fixture
def rede_sintetica(cur_demo2):
    for codigo, p1, p2 in (
        ("zt-A", N1, N2),
        ("zt-B", N2, N3),
        ("zt-C", N2, N4),
        ("zt-D", N3, N5),
        ("zt-E", N3, N4),
        ("zt-F", N6, N6),
        ("zt-H", P0, P1),
    ):
        _trecho(cur_demo2, codigo, "C2" if codigo == "zt-H" else "C1", "mt", p1, p2)
    # baixa tensão pendurada no meio de H (para os endereços com rede no portão)
    _trecho(cur_demo2, "zt-G", "C2", "bt", (P0[0] + 0.0001, P0[1]), (P0[0] + 0.0001, P0[1] - 0.0002))
    for codigo, ponto in (("zt-T1", N2), ("zt-T2", N3), ("zt-T3", N4), ("zt-T4", N5),
                          ("zt-T5", (N5[0] + 0.0005, N5[1]))):
        _trafo(cur_demo2, codigo, "C1", ponto)
    for trafo, n in (("zt-T1", 4), ("zt-T2", 2), ("zt-T3", 5), ("zt-T4", 7), ("zt-T5", 100)):
        _ucs(cur_demo2, trafo, n)
    return cur_demo2


def test_jusante_radial_malha_e_degenerado(rede_sintetica):
    resumo = consumidores.calcular_jusante(rede_sintetica)
    assert resumo["trechos"] == 7 and resumo["ctmts"] == 2
    assert resumo["trechos_calculados"] == 5 and resumo["trechos_em_malha"] == 2
    assert resumo["ucs"] == 18  # as 100 do T5 fora da tolerância não entram
    rede_sintetica.execute(
        "SELECT codigo, clientes_jusante FROM plat.rede_trecho"
        " WHERE tenant_id = plat.tenant_atual() AND nivel = 'mt'"
    )
    valores = {r["codigo"]: r["clientes_jusante"] for r in rede_sintetica.fetchall()}
    assert valores["zt-A"] == 0  # n1 não tem transformador: zero é calculado, não nulo
    assert valores["zt-B"] == 9  # T2 no n3 (2) + T4 no n5 (7)
    assert valores["zt-C"] == 5  # T3 no n4
    assert valores["zt-D"] == 7  # T4 no n5
    assert valores["zt-E"] is None  # malha: fora da árvore
    assert valores["zt-F"] is None  # degenerado: fora da árvore
    assert valores["zt-H"] == 0  # raiz p0, nada a jusante


def test_jusante_segunda_rodada_idempotente(rede_sintetica):
    consumidores.calcular_jusante(rede_sintetica)
    consumidores.calcular_jusante(rede_sintetica)
    rede_sintetica.execute(
        "SELECT count(*) AS n FROM plat.rede_trecho"
        " WHERE tenant_id = plat.tenant_atual() AND nivel = 'mt' AND clientes_jusante IS NOT NULL"
    )
    assert rede_sintetica.fetchone()["n"] == 5


def _endereco(cur, endereco_id: int, ponto) -> None:
    cur.execute(
        "INSERT INTO plat.rede_endereco (tenant_id, fonte, endereco_id, geometria)"
        " VALUES (plat.tenant_atual(), 'censo', %s, ST_SetSRID(ST_MakePoint(%s, %s), 4674))"
        " ON CONFLICT (tenant_id, fonte, endereco_id) DO NOTHING",
        (endereco_id, ponto[0], ponto[1]),
    )


def test_gerar_classifica_e_e_idempotente(rede_sintetica):
    """e1 a 5 m da média sem baixa por perto = candidato_ligacao; e2 a ~300 m = cadastro_faltante;
    e3 sem média a 700 m e e4 com baixa a 50 m não entram."""
    _endereco(rede_sintetica, 92001, (N2[0] - 0.00005, N2[1] - 0.000045))  # ~5 m do trecho A
    _endereco(rede_sintetica, 92002, (N2[0] + 0.00294, N2[1]))  # ~300 m do trecho A
    _endereco(rede_sintetica, 92003, (N2[0] - 0.00784, N2[1]))  # ~800 m: fora do raio da média
    _endereco(rede_sintetica, 92004, (P0[0] + 0.0001, P0[1] + 0.00045))  # ~50 m do bt zt-G e do mt zt-H
    resumo = consumidores.gerar_enderecos_sem_rede(rede_sintetica, 700.0, 135.0)
    assert resumo["enderecos"] == 4 and resumo["total"] == 2
    assert resumo["candidato_ligacao"] == 1 and resumo["cadastro_faltante"] == 1
    rede_sintetica.execute(
        "SELECT endereco_id, dist_rede_m, situacao FROM plat.rede_endereco_sem_rede"
        " WHERE tenant_id = plat.tenant_atual() ORDER BY dist_rede_m"
    )
    linhas = rede_sintetica.fetchall()
    assert [(r["endereco_id"], r["situacao"]) for r in linhas] == [
        (92001, "candidato_ligacao"),
        (92002, "cadastro_faltante"),
    ]
    assert 2.0 <= linhas[0]["dist_rede_m"] <= 10.0 and 250.0 <= linhas[1]["dist_rede_m"] <= 350.0
    de_novo = consumidores.gerar_enderecos_sem_rede(rede_sintetica, 700.0, 135.0)
    assert de_novo == resumo  # recomeço: apaga e regenera o mesmo conjunto


def _uma_uc(cur, uni_tr_mt: str) -> str:
    cur.execute(
        "SELECT id::text AS id FROM plat.rede_uc"
        " WHERE tenant_id = plat.tenant_atual() AND uni_tr_mt = %s ORDER BY codigo LIMIT 1",
        (uni_tr_mt,),
    )
    return cur.fetchone()["id"]


def test_ficha_uc_so_agregado_e_sem_campo_identificavel(rede_sintetica):
    # 4 UC no zt-T1: abaixo do mínimo de agregação -> ene_kwh nulo com motivo
    for i in range(4):
        rede_sintetica.execute(
            "INSERT INTO plat.rede_uc_consumo (uc_id, tenant_id, ano, ene_kwh)"
            " SELECT id, tenant_id, 2024, %s FROM plat.rede_uc"
            " WHERE tenant_id = plat.tenant_atual() AND uni_tr_mt = 'zt-T1' AND codigo = %s",
            (100.0 * i, f"zt-l4-20-zt-T1-{i}"),
        )
    ficha = consumidores.ficha_uc(rede_sintetica, _uma_uc(rede_sintetica, "zt-T1"))
    assert ficha["uni_tr_mt"] == "zt-T1" and ficha["ctmt"] == "C1"
    assert ficha["consumo"]["ene_kwh"] is None and ficha["consumo"]["ucs"] == 4
    assert "motivo" in ficha["consumo"] and str(limites.REDE_AGREGACAO_MIN_UCS) in ficha["consumo"]["motivo"]
    # nenhuma chave da ficha é identificável (varredura exata de chave; consumo só em agregado)
    proibidas = {"nome", "cpf", "cnpj", "telefone", "email", "endereco", "identidade"}
    chaves = set(ficha) | set(ficha["consumo"])
    assert not (chaves & proibidas), chaves & proibidas


def test_ficha_uc_agregado_acima_do_minimo(rede_sintetica):
    # o zt-T3 tem 5 UC (== mínimo): consumo agregado sai numérico
    for i, uc in enumerate(("zt-l4-20-zt-T3-0", "zt-l4-20-zt-T3-1", "zt-l4-20-zt-T3-2",
                            "zt-l4-20-zt-T3-3", "zt-l4-20-zt-T3-4")):
        rede_sintetica.execute(
            "INSERT INTO plat.rede_uc_consumo (uc_id, tenant_id, ano, ene_kwh)"
            " SELECT id, tenant_id, 2024, %s FROM plat.rede_uc"
            " WHERE tenant_id = plat.tenant_atual() AND uni_tr_mt = 'zt-T3' AND codigo = %s",
            (10.0 + i, uc),
        )
    ficha = consumidores.ficha_uc(rede_sintetica, _uma_uc(rede_sintetica, "zt-T3"))
    assert ficha["consumo"]["ucs"] == 5
    assert ficha["consumo"]["ene_kwh"] == pytest.approx(sum(10.0 + i for i in range(5)), abs=0.01)
    assert ficha["consumo"]["motivo"] is None and ficha["consumo"]["ano"] == 2024


def test_ficha_uc_inexistente(rede_sintetica):
    assert consumidores.ficha_uc(rede_sintetica, "00000000-0000-0000-0000-000000000000") is None
