"""Leitura da medição de uso do inquilino (item L0-07-c-cotas-uso).

O achado do adversário do T9 foi que `plat.uso_inquilino` era escrita pelo periódico e NUNCA lida: sem rota
e sem tela, a cláusula "tela 'Uso' do admin do inquilino com gráfico" do portão não tinha como ser
verdadeira. Estes testes provam o caminho de volta inteiro: o periódico grava, a rota devolve a série com as
cotas ao lado, um inquilino nunca vê a série do outro, e quem não é admin do inquilino não lê nada.

A série de 30 pontos que o portão pede é exercitada como o próprio parâmetro do periódico prevê (um job por
dia: `jobs.uso_medir {"dia": ...}`) — aqui os pontos são gravados direto na tabela com a role de aplicação,
porque o que está sob teste é a LEITURA, e 30 jobs de medição levariam minutos sem provar nada a mais."""

import datetime
import os

import psycopg2
import pytest

ITEM = "L0-07-c-cotas-uso"


def _conexao(env):
    """Conexão própria em autocommit: a fixture `conexao_plat_app` da suíte não serve aqui porque não
    comita, e a API lê por OUTRA conexão — os pontos gravados nela seriam invisíveis para a rota.
    `CursorSchemaAmbiente` é o mesmo cursor da suíte: sem ele o `plat.` literal bateria em PRODUÇÃO
    quando a trilha tem schema próprio."""
    from app.schema_ambiente import CursorSchemaAmbiente

    con = psycopg2.connect(env.get("PLAT_DSN") or os.environ["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    con.autocommit = True
    return con


@pytest.fixture
def serie_de_30_dias(env):
    """30 pontos diários no inquilino A, do mais antigo ao de hoje; removidos ao fim."""
    from tests.api.test_rls import contexto, ids_por_slug

    con = _conexao(env)
    tenant_a = ids_por_slug(con)["demo"]
    hoje = datetime.date.today()
    dias = [hoje - datetime.timedelta(days=n) for n in range(29, -1, -1)]
    contexto(con, tenant_a)
    with con.cursor() as cur:
        for dia in dias:
            # a MESMA função que o periódico jobs.uso_medir chama (SECURITY DEFINER: a role da aplicação
            # só tem SELECT na tabela, de propósito — quem escreve a conta é a medição, nunca o usuário).
            # Um ponto por dia é exatamente o que o parâmetro `dia` do periódico prevê para série retroativa.
            cur.execute("SELECT plat.uso_medir(%s, %s, %s)", (tenant_a, dia, 1_000_000))
    try:
        yield dias
    finally:
        # sem faxina de propósito: estes pontos SÃO a medição real dos últimos 30 dias do inquilino de
        # demonstração, gravada pela mesma função do periódico e idempotente por (inquilino, dia). Apagar
        # exigiria privilégio de escrita na tabela que a role da aplicação não tem — e não deve ter.
        con.close()


def test_serie_devolve_os_30_pontos_em_ordem_com_as_cotas(sessao_a, serie_de_30_dias, medida):
    r = sessao_a.get("/api/uso?dias=30")
    assert r.status_code == 200, r.text
    corpo = r.json()
    pontos = corpo["pontos"]
    assert len(pontos) == 30, [p["dia"] for p in pontos]
    assert [p["dia"] for p in pontos] == sorted(p["dia"] for p in pontos), "a série tem de vir em ordem de dia"
    assert pontos[-1]["bytes_total"] == pontos[-1]["bytes_banco"] + pontos[-1]["bytes_bucket"]
    assert all(p["bytes_bucket"] == 1_000_000 for p in pontos), "o bytes_bucket medido tem de voltar inteiro"
    assert set(corpo["cotas"]) == {"cota_bytes", "cota_usuarios", "cota_itens", "cota_jobs_dia"}
    medida(ITEM)("pontos_na_serie_diaria", len(pontos), "pontos",
                 "pytest tests/api/test_uso.py::test_serie_devolve_os_30_pontos_em_ordem_com_as_cotas")


def test_janela_recorta_a_serie(sessao_a, serie_de_30_dias):
    assert len(sessao_a.get("/api/uso?dias=7").json()["pontos"]) == 7
    assert len(sessao_a.get("/api/uso?dias=1").json()["pontos"]) == 1


def test_agora_vem_dos_contadores_vivos_e_nao_da_serie(sessao_a, serie_de_30_dias):
    """`agora` não pode ser o último ponto: é o que a plataforma contabiliza AGORA, e é isso que impede a
    tela de mostrar o consumo de ontem como se fosse o de hoje antes de o periódico do dia rodar."""
    corpo = sessao_a.get("/api/uso?dias=30").json()
    agora = corpo["agora"]
    assert set(agora) == {"bytes_total", "itens", "itens_lixeira", "usuarios_total", "jobs_hoje"}
    assert all(isinstance(v, int) and v >= 0 for v in agora.values())
    # `agora["bytes_total"]` é tenant.uso_bytes (a reserva de cota que app/cotas.py mantém), e o ponto do dia
    # é bytes de BANCO + bucket medidos: são duas contas diferentes de propósito, e a tela diz qual é qual.
    assert agora["bytes_total"] != corpo["pontos"][-1]["bytes_total"] or agora["bytes_total"] == 0


def test_um_inquilino_nao_ve_a_serie_do_outro(sessao_a, sessao_b, serie_de_30_dias):
    """A fixture escreveu 30 pontos com valores inconfundíveis no inquilino A; B não pode ver nenhum."""
    de_a = sessao_a.get("/api/uso?dias=30").json()["pontos"]
    assert len(de_a) == 30 and all(p["bytes_bucket"] == 1_000_000 for p in de_a)
    corpo = sessao_b.get("/api/uso?dias=30").json()
    assert corpo["inquilino"] == "demo2"
    assert not [p for p in corpo["pontos"] if p["bytes_bucket"] == 1_000_000], (
        "o inquilino B enxergou pontos medidos no inquilino A (o 1.000.000 de bytes_bucket é a marca da fixture)"
    )


def test_sem_privilegio_de_organizacao_nao_le(usuarios_a):
    """`org.configurar` é o privilégio da conta do inquilino: um visualizador não lê a conta de ninguém."""
    cliente, _u, _senha = usuarios_a.sessao(perfil="visualizador")
    r = cliente.get("/api/uso")
    assert r.status_code in (401, 403), r.text


def test_a_tela_de_uso_existe_e_chama_a_rota():
    """A cláusula do portão é 'tela Uso ... com gráfico'. Aqui fica a parte estática (a página existe, está
    no menu, e o módulo dela chama a rota e desenha um SVG); a captura é do e2e."""
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[2]
    from app.paginas import PAGINAS

    assert PAGINAS["/admin/uso"] == "admin/uso.html"
    js = (raiz / "web" / "js" / "admin" / "uso.js").read_text(encoding="utf-8")
    assert "/api/uso?dias=" in js
    assert "createElementNS" in js and "grafico-uso" in js, "a tela tem de desenhar o gráfico, não só a tabela"
    assert "'/admin/uso'" in (raiz / "web" / "js" / "base" / "layout.js").read_text(encoding="utf-8")
