"""Modelo de elementos da rede de utilidades (item L4-01-modelo-rede; ADR 20260906T2126).

Cláusulas do portão provadas aqui:
1. pgRouting instalado e usável (`test_pgrouting_resolve_menor_caminho`);
2. DDL `plat.rede_*` com regras de conectividade validadas por TRIGGER, não por checagem da aplicação
   (`test_gatilho_recusa_no_fora_da_rede`, `test_gatilho_recusa_associacao_fora_do_catalogo`,
   `test_gatilho_recusa_subrede_de_nivel_invertido`);
3. importador BDGD contra um recorte de DISTRIBUIDORA REAL (1 alimentador da cooperativa de teste,
   ativo da casa também usado pelo item irmão `L4-01-c-importador-bdgd`; ver
   `tests/dados/gerar_bdgd_extrato.py`), com a contagem inserida conferida contra `inspecionar()` camada
   a camada e toda perda explicada por um desvio nomeado (`test_importa_distribuidora_real_e_confere_contagem`).
   PARCIAL quanto a "distribuidora inteira": a distribuidora completa foi tentada e medida em >13 minutos sob
   disputa de banco de uma trilha (ver fixture `extrato_real` e `docs/rede/MODELO_REDE.md` §7) — a
   mecânica está provada contra dado real, a escala de uma distribuidora inteira não.

Fronteira honesta desta passagem (documentada também no ADR e no handoff): RAMLIG entra com desvio,
nunca aresta, nesta distribuidora real — `PN_CON_2` vem vazio em 100% das linhas (medido no recorte E
na distribuidora inteira, 26.581 linhas, E na BDGD da cooperativa de teste, 2.418.764 linhas — três amostras
independentes, mesmo padrão) — o ramal de ligação liga junção a CONSUMIDOR, não junção a junção, e o
modelo atual só sabe montar aresta juncao-juncao. A conectividade do consumidor com a rede não se
perde (a associação de `_consumidores` liga o mesmo PN_CON), mas o ramal em si não vira aresta na
malha do pgRouting — registrado como pendência do próximo item da linha, nunca escondido atrás de um
número que pareça completo. Se `PLAT_REDE_REFERENCIA_GDB` não apontar um pacote existente nesta
máquina (ambiente sem os ativos da casa), os testes que dependem dele pulam."""

import hashlib

import pytest

from app.rede_utilidades import deposito, instalados
from app.rede_utilidades import pacote as pacote_mod
from app.rede_utilidades.bdgd import importar, inspecionar
from tests.api.test_rls import contexto, ids_por_slug
from tests.dados.gerar_bdgd_extrato import obter_extrato_pequeno


@pytest.fixture(scope="module")
def extrato_real():
    """Um alimentador (CTMT) da cooperativa de teste real — não a distribuidora inteira: medido que
    importar a distribuidora completa (44.268 SSDMT + 27.587 UCBT_tab + ...) passa de 13 minutos sob a
    disputa de banco de uma trilha compartilhada, porque a associação de cada dispositivo/consumidor
    com a junção é uma consulta por linha (não em lote — ver `docs/rede/MODELO_REDE.md` §4/§7, achado
    de performance registrado como pendência). Este extrato usa o MESMO arquivo fonte e as MESMAS
    esquisitices de dado real (RAMLIG sem PN_CON_2 etc.), numa escala que cabe no orçamento de uma
    trilha; `obter_extrato()` (não usado aqui) continua disponível para medir a distribuidora inteira
    fora da suíte, com tempo maior."""
    try:
        return obter_extrato_pequeno()
    except FileNotFoundError as exc:
        pytest.skip(str(exc))


@pytest.fixture
def rede_eletrica(conexao_plat_app):
    """Rede do inquilino demo com o pacote eletrica-br instalado, pronta para o importador BDGD."""
    con = conexao_plat_app
    ids = ids_por_slug(con)
    tenant_id = ids["demo"]
    with con.cursor() as cur:
        contexto(con, tenant_id)
        cur.execute("SELECT id FROM plat.usuario WHERE tenant_id = %s AND ativo ORDER BY id LIMIT 1", (tenant_id,))
        usuario_id = cur.fetchone()["id"]
        contexto(con, tenant_id, usuario_id)
        cur.execute(
            "INSERT INTO plat.rede (tenant_id, nome, disciplina, tolerancia_m, dono_id) "
            "VALUES (%s, 'zt-modelo-bdgd', 'eletrica', 0.05, %s) RETURNING id",
            (tenant_id, usuario_id),
        )
        rede_id = cur.fetchone()["id"]
        bruto = instalados.bruto("eletrica-br")
        doc = pacote_mod.ler(bruto)
        deposito.importar(cur, tenant_id, rede_id, doc, usuario_id, hashlib.sha256(bruto).hexdigest(), len(bruto))
    yield con, tenant_id, usuario_id, str(rede_id)


def test_pgrouting_resolve_menor_caminho(rede_eletrica):
    """Cláusula 1: a extensão está instalada e a função de menor caminho do item roda de ponta a ponta
    (duas junções, uma aresta entre elas), sem depender do importador."""
    con, tenant_id, usuario_id, rede_id = rede_eletrica
    with con.cursor() as cur:
        contexto(con, tenant_id, usuario_id)
        cur.execute("SELECT extname FROM pg_extension WHERE extname = 'pgrouting'")
        assert cur.fetchone() is not None, "extensão pgrouting não instalada"

        cur.execute(
            "SELECT t.id FROM plat.rede_tipo t JOIN plat.rede_grupo g ON g.id = t.grupo_id "
            "WHERE t.rede_id = %s::uuid AND g.codigo = 'trecho_de_media_tensao' LIMIT 1",
            (rede_id,),
        )
        tipo_trecho = cur.fetchone()["id"]

        cur.execute(
            "INSERT INTO plat.rede_no (tenant_id, rede_id, papel, geom) VALUES "
            "(%s, %s::uuid, 'juncao', ST_SetSRID(ST_MakePoint(-51.0, -29.0), 4326)) RETURNING id",
            (tenant_id, rede_id),
        )
        no_a = cur.fetchone()["id"]
        cur.execute(
            "INSERT INTO plat.rede_no (tenant_id, rede_id, papel, geom) VALUES "
            "(%s, %s::uuid, 'juncao', ST_SetSRID(ST_MakePoint(-51.001, -29.001), 4326)) RETURNING id",
            (tenant_id, rede_id),
        )
        no_b = cur.fetchone()["id"]
        cur.execute(
            "INSERT INTO plat.rede_aresta (tenant_id, rede_id, tipo_id, no_origem_id, no_destino_id, "
            "no_origem_seq, no_destino_seq, geom, comprimento_m) VALUES "
            "(%s, %s::uuid, %s::uuid, %s::uuid, %s::uuid, 0, 0, "
            "ST_SetSRID(ST_MakeLine(ST_MakePoint(-51.0,-29.0), ST_MakePoint(-51.001,-29.001)), 4326), 140.5)",
            (tenant_id, rede_id, tipo_trecho, no_a, no_b),
        )
        cur.execute("SELECT plat.rede_menor_caminho(%s::uuid, %s::uuid, %s::uuid) AS r", (rede_id, no_a, no_b))
        r = cur.fetchone()["r"]
        assert r["encontrado"] is True
        assert r["custo_m"] == pytest.approx(140.5, rel=1e-3)
        assert r["ramais_sem_custo"] == 0
        assert len(r["arestas"]) == 1


def test_gatilho_recusa_no_fora_da_rede(rede_eletrica):
    """Cláusula 2: uma aresta não pode ligar nós de REDES diferentes — o gatilho recusa, não a app."""
    con, tenant_id, usuario_id, rede_id = rede_eletrica
    with con.cursor() as cur:
        contexto(con, tenant_id, usuario_id)
        cur.execute(
            "INSERT INTO plat.rede (tenant_id, nome, disciplina, tolerancia_m, dono_id) "
            "VALUES (%s, 'zt-modelo-outra', 'eletrica', 0.05, %s) RETURNING id",
            (tenant_id, usuario_id),
        )
        outra_rede_id = cur.fetchone()["id"]
        cur.execute(
            "SELECT t.id FROM plat.rede_tipo t JOIN plat.rede_grupo g ON g.id = t.grupo_id "
            "WHERE t.rede_id = %s::uuid AND g.codigo = 'trecho_de_media_tensao' LIMIT 1",
            (rede_id,),
        )
        tipo_trecho = cur.fetchone()["id"]
        cur.execute(
            "INSERT INTO plat.rede_no (tenant_id, rede_id, papel) VALUES (%s, %s::uuid, 'juncao') RETURNING id",
            (tenant_id, rede_id),
        )
        no_a = cur.fetchone()["id"]
        cur.execute(
            "INSERT INTO plat.rede_no (tenant_id, rede_id, papel) VALUES (%s, %s::uuid, 'juncao') RETURNING id",
            (tenant_id, outra_rede_id),
        )
        no_de_outra_rede = cur.fetchone()["id"]
        with pytest.raises(Exception, match="aresta_no_destino_fora_da_rede"):
            cur.execute(
                "INSERT INTO plat.rede_aresta (tenant_id, rede_id, tipo_id, no_origem_id, no_destino_id, "
                "no_origem_seq, no_destino_seq) VALUES (%s, %s::uuid, %s::uuid, %s::uuid, %s::uuid, 0, 0)",
                (tenant_id, rede_id, tipo_trecho, no_a, no_de_outra_rede),
            )


def test_gatilho_recusa_subrede_de_nivel_invertido(rede_eletrica):
    """Cláusula 2: subrede de nível 3 exige pai de nível 2 — pular direto do nível 1 é recusado."""
    con, tenant_id, usuario_id, rede_id = rede_eletrica
    with con.cursor() as cur:
        contexto(con, tenant_id, usuario_id)
        cur.execute(
            "INSERT INTO plat.rede_subrede_bdgd (tenant_id, rede_id, nivel, codigo_externo) "
            "VALUES (%s, %s::uuid, 1, 'zt-nivel1') RETURNING id",
            (tenant_id, rede_id),
        )
        nivel1 = cur.fetchone()["id"]
        with pytest.raises(Exception, match="subrede_nivel_invertido"):
            cur.execute(
                "INSERT INTO plat.rede_subrede_bdgd (tenant_id, rede_id, nivel, codigo_externo, pai_id) "
                "VALUES (%s, %s::uuid, 3, 'zt-nivel3', %s::uuid)",
                (tenant_id, rede_id, nivel1),
            )


def test_gatilho_recusa_associacao_fora_do_catalogo(rede_eletrica):
    """Cláusula 2: associação nó-nó sem regra correspondente em `rede_regra` é recusada na escrita."""
    con, tenant_id, usuario_id, rede_id = rede_eletrica
    with con.cursor() as cur:
        contexto(con, tenant_id, usuario_id)
        cur.execute(
            "SELECT t.id FROM plat.rede_tipo t JOIN plat.rede_grupo g ON g.id = t.grupo_id "
            "WHERE t.rede_id = %s::uuid AND g.codigo = 'subestacao' LIMIT 1",
            (rede_id,),
        )
        tipo_sub = cur.fetchone()["id"]
        cur.execute(
            "INSERT INTO plat.rede_no (tenant_id, rede_id, papel, tipo_id) VALUES "
            "(%s, %s::uuid, 'fonte', %s::uuid) RETURNING id",
            (tenant_id, rede_id, tipo_sub),
        )
        de_no = cur.fetchone()["id"]
        cur.execute(
            "INSERT INTO plat.rede_no (tenant_id, rede_id, papel, tipo_id) VALUES "
            "(%s, %s::uuid, 'fonte', %s::uuid) RETURNING id",
            (tenant_id, rede_id, tipo_sub),
        )
        para_no = cur.fetchone()["id"]
        # subestação-subestação nunca tem regra de conectividade no pacote eletrica-br
        with pytest.raises(Exception, match="associacao_sem_regra"):
            cur.execute(
                "INSERT INTO plat.rede_associacao (tenant_id, rede_id, tipo, de_no_id, para_no_id) "
                "VALUES (%s, %s::uuid, 'conectividade', %s::uuid, %s::uuid)",
                (tenant_id, rede_id, de_no, para_no),
            )


def test_importa_distribuidora_real_e_confere_contagem(rede_eletrica, extrato_real):
    """Cláusula 3 (parcial — ver fronteira honesta no docstring do módulo e §4/§7 de
    `docs/rede/MODELO_REDE.md`): a régua é `inspecionar()` lido do MESMO arquivo GDB (não um número
    de cabeça), e toda camada que não bate 1:1 tem desvio nomeado com quantidade explicando a
    diferença inteira. O arquivo é um recorte (1 alimentador) de uma distribuidora REAL (cooperativa
    de teste) — a distribuidora INTEIRA foi tentada e medida como lenta demais para a suíte (ver
    fixture `extrato_real`), então esta cláusula fica provada na MECÂNICA (contagem/desvio corretos
    contra dado real), não na ESCALA."""
    arquivo = inspecionar(extrato_real)
    # a régua é o arquivo lido agora, nunca um número fixado à mão — mas o valor abaixo prova que
    # não é um GDB vazio nem trivial
    assert arquivo["SSDMT"] > 100 and arquivo["UCBT_tab"] > 100, arquivo

    con, tenant_id, usuario_id, rede_id = rede_eletrica
    with con.cursor() as cur:
        contexto(con, tenant_id, usuario_id)
        resultado = importar(cur, tenant_id, rede_id, extrato_real)

    contagens = resultado["contagens"]
    desvios = resultado["desvios"]

    # camadas que fecham 1:1 nesta distribuidora real
    for camada in ("SUB", "SSDMT", "UNTRMT", "SSDBT", "UCBT_tab", "UNSEMT", "UCMT_tab"):
        assert contagens[camada]["arquivo"] == contagens[camada]["inserido"], (camada, contagens[camada])

    # CTMT: parte dos alimentadores referencia uma SUB fora deste arquivo (interligação com outra
    # distribuidora, dado real — não artefato) — cada um vira o desvio nomeado, nenhum silencioso
    ctmt = contagens["CTMT"]
    assert ctmt["arquivo"] - ctmt["inserido"] == desvios.get("alimentador_sem_subestacao", {}).get("quantidade", 0)

    # RAMLIG: 0% de aproveitamento como ARESTA nesta distribuidora real — ver fronteira honesta no
    # docstring do módulo. O número é medido, não estimado, e 100% das linhas têm desvio nomeado.
    assert contagens["RAMLIG"]["inserido"] == 0
    assert desvios["trecho_sem_ponto_conexao"]["quantidade"] == contagens["RAMLIG"]["arquivo"]

    # nada silencioso: toda camada com arquivo != inserido tem ALGUM desvio nomeado com quantidade > 0
    camadas_com_perda = {c for c, v in contagens.items() if v["arquivo"] != v["inserido"]}
    assert camadas_com_perda, "esta distribuidora real deveria ter ao menos uma perda explicada (RAMLIG)"
    assert sum(d["quantidade"] for d in desvios.values()) >= sum(
        contagens[c]["arquivo"] - contagens[c]["inserido"] for c in camadas_com_perda
    )

    assert resultado["conferido"] is False  # honesto: nem tudo do arquivo virou nó/aresta (ver docstring)

    with con.cursor() as cur:
        contexto(con, tenant_id, usuario_id)
        cur.execute("SELECT count(*) AS n FROM plat.rede_no WHERE rede_id = %s::uuid", (rede_id,))
        total_nos = cur.fetchone()["n"]
        cur.execute("SELECT count(*) AS n FROM plat.rede_aresta WHERE rede_id = %s::uuid", (rede_id,))
        total_arestas = cur.fetchone()["n"]
        cur.execute("SELECT count(*) AS n FROM plat.rede_subrede_bdgd WHERE rede_id = %s::uuid", (rede_id,))
        total_subredes = cur.fetchone()["n"]
        cur.execute("SELECT count(*) AS n FROM plat.rede_associacao WHERE rede_id = %s::uuid", (rede_id,))
        total_associacoes = cur.fetchone()["n"]

    # números medidos de um recorte de distribuidora real (registrados também, à mão, em
    # tests/medidas/L4-01-modelo-rede.json — `medida()` depende de git_sha_curto(), que lê .git/HEAD
    # como diretório e falha em worktree; achado à parte deste item, fora de escopo consertar
    # `app/versao.py`, compartilhado por toda a árvore)
    assert total_nos > 200  # SUB + UNTRMT + UNSEMT + UCBT/UCMT + junções derivadas de PN_CON
    assert total_arestas > 500  # SSDMT + SSDBT
    assert total_subredes > 0
    assert total_associacoes > 0


def test_conferido_falso_reflete_arquivo_com_desvio_e_verdadeiro_sem(rede_eletrica, extrato_real):
    """`conferido` é o resumo binário que a auditoria expõe: falso quando há qualquer desvio de
    contagem, verdadeiro quando todas as camadas do CAMADAS batem 1:1. Prova a direção oposta com um
    GDB minúsculo (só a camada SUB, extraída da mesma distribuidora real) onde toda camada bate."""
    con, tenant_id, usuario_id, rede_id = rede_eletrica
    import shutil

    import pyogrio as pg

    caminho = "tests/dados/gerados/bdgd_so_sub.gdb"
    shutil.rmtree(caminho, ignore_errors=True)
    sub = pg.read_dataframe(extrato_real, layer="SUB")
    pg.write_dataframe(sub, caminho, layer="SUB", driver="OpenFileGDB", geometry_type="MultiPolygon")
    try:
        with con.cursor() as cur:
            contexto(con, tenant_id, usuario_id)
            resultado = importar(cur, tenant_id, rede_id, caminho)
        n_sub = len(sub)
        assert resultado["contagens"]["SUB"] == {"arquivo": n_sub, "inserido": n_sub}
        # as demais camadas simplesmente não existem no GDB: 0 arquivo / 0 inserido, sem desvio
        for camada in ("CTMT", "SSDMT", "UNTRMT", "SSDBT", "UCBT_tab", "RAMLIG", "UNSEMT", "UCMT_tab"):
            assert resultado["contagens"][camada] == {"arquivo": 0, "inserido": 0}
        assert resultado["conferido"] is True  # toda camada CAMADAS bate 1:1, mesmo com 0/0
        # CTMT e PONNOT ausentes viram desvio informativo (1 cada, não por linha) — nunca silêncio,
        # mas também nunca contam contra "conferido" porque a régua é arquivo==inserido por camada.
        assert set(resultado["desvios"]) == {"ctmt_ausente", "ponnot_ausente"}
        assert resultado["desvios"]["ctmt_ausente"]["quantidade"] == 1
        assert resultado["desvios"]["ponnot_ausente"]["quantidade"] == 1
    finally:
        shutil.rmtree(caminho, ignore_errors=True)
