"""Uma tabela só de subrede (item L4-04-c-unificar-subrede; ADR 20260908T0152).

Antes havia duas tabelas para o mesmo conceito: `plat.rede_subrede` (a subrede DERIVADA do controlador,
item L4-04-a) e `plat.rede_subrede_bdgd` (a hierarquia que o ARQUIVO declara, item L4-01-c). Aqui está a
prova de que agora é uma tabela só, com a coluna `origem` separando as duas leituras, e de que a
reconciliação entre elas é medida em vez de suposta.

Cláusulas do portão provadas aqui:
1. uma tabela só — `test_a_tabela_antiga_nao_existe_mais`, `test_as_duas_origens_na_mesma_tabela`,
   `test_no_e_aresta_apontam_para_a_tabela_unificada`;
2. a importação continua populando controladores e passa a declarar e reconciliar —
   `test_importar_declara_a_hierarquia_e_reconcilia`;
3. reconciliação medida — `test_importar_declara_a_hierarquia_e_reconcilia` (rede sintética; a medida na
   cooperativa de teste está em `test_rede_subrede_unificada_medida.py`, marcada `lento`);
4. a migração leva os dados da tabela antiga — a conferência está em
   `tests/dados/verifica_migracao_subrede_unificada.sql` (roda como postgres, em transação desfeita);
   aqui fica o que sobra dela no schema: a tabela antiga sumiu e as chaves estrangeiras foram repontadas.

Refutação (papel adversário), provada aqui:
- `test_ctmt_sem_disjuntor_reconcilia_pelo_no_de_cabeca`: o alimentador que o arquivo declara mas cujo
  equipamento de saída não está no arquivo NÃO vira subrede órfã — ele reconcilia com a subrede derivada
  cujo controlador nasceu no nó de cabeça;
- `test_forma_da_linha_depende_da_origem` e `test_nivel_invertido_continua_recusado`: a tabela única não
  afrouxou regra nenhuma — linha declarada com tier, linha derivada com nível e nível fora de ordem
  continuam recusados pelo banco, não pela aplicação.
"""

import pytest

from tests.api.test_rede_controladores import (
    CTMT_COM_EQUIPAMENTO,
    CTMT_SEM_EQUIPAMENTO,
    SUB,
    _criar_rede,
    _habilitar,
    _linha,
    _ponto,
    limpar_redes,  # noqa: F401 — fixture reusada
)
from tests.api.test_rls import contexto, ids_por_slug

# arquivo de medida separado do da cooperativa (`L4-04-c-unificar-subrede.json`, escrito pelo teste
# `lento`): um é rede sintética, o outro é dado real, e misturar os dois num arquivo só apaga a diferença
ITEM = "L4-04-c-unificar-subrede-sintetica"
TRAFO = "TR1"


def _rede_com_trafo_no_alimentador(sessao, rid, lon0=31.0, lat0=11.0):
    """A mesma rede de teste do item L4-04-a, com uma diferença que o portão deste item exige: o
    transformador carrega o `ctmt` do arquivo. Sem esse campo a hierarquia declarada não tem como pendurar
    o nível 3 no nível 2 — e o que este item promete é medir a reconciliação, não fabricar o pai."""
    d = 0.001
    a, b, c = (lon0, lat0), (lon0 + d, lat0), (lon0 + 2 * d, lat0)
    bt = (lon0 + 2 * d, lat0 + d)
    a2, b2 = (lon0, lat0 + 10 * d), (lon0 + d, lat0 + 10 * d)
    at1 = {"ctmt": CTMT_COM_EQUIPAMENTO, "sub": SUB}
    at2 = {"ctmt": CTMT_SEM_EQUIPAMENTO, "sub": SUB}
    disjuntor = _ponto(sessao, rid, *a, "chave_de_media_tensao", 4, atributos=at1)
    _linha(sessao, rid, [list(a), list(b)], "trecho_de_media_tensao", atributos={**at1, "cod_id": "MT1"})
    _linha(sessao, rid, [list(b), list(c)], "trecho_de_media_tensao", atributos={**at1, "cod_id": "MT2"})
    trafo = _ponto(sessao, rid, *c, "transformador_de_distribuicao", 1,
                   atributos={"cod_id": TRAFO, "ctmt": CTMT_COM_EQUIPAMENTO})
    _linha(sessao, rid, [list(c), list(bt)], "trecho_de_baixa_tensao", atributos={"cod_id": "BT1"})
    _linha(sessao, rid, [list(a2), list(b2)], "trecho_de_media_tensao", atributos={**at2, "cod_id": "MT3"})
    _habilitar(sessao, rid)
    return {"disjuntor": disjuntor, "trafo": trafo}


@pytest.fixture
def rede_importada(sessao_a, limpar_redes):  # noqa: F811 — a fixture vem do módulo irmão
    rid = _criar_rede(sessao_a, "unifica", limpar_redes)
    rede = _rede_com_trafo_no_alimentador(sessao_a, rid)
    r = sessao_a.post(f"/api/rede/{rid}/controladores/importar")
    assert r.status_code == 200, r.text
    return rid, rede, r.json()


# --- cláusula 1: uma tabela só ---------------------------------------------------------------------------

def test_a_tabela_antiga_nao_existe_mais(conexao_plat_app):
    con = conexao_plat_app
    with con.cursor() as cur:
        cur.execute("SELECT to_regclass('plat.rede_subrede_bdgd') AS antiga, "
                    "to_regclass('plat.rede_subrede') AS unica")
        r = cur.fetchone()
    assert r["antiga"] is None, "a tabela da importação foi absorvida: não pode mais existir"
    assert r["unica"] is not None


def test_no_e_aresta_apontam_para_a_tabela_unificada(conexao_plat_app):
    """As referências que existiam para a tabela antiga passaram a apontar a unificada — é isso que deixa a
    migração preservar os `id` em vez de reescrever `rede_no`/`rede_aresta` linha a linha."""
    con = conexao_plat_app
    with con.cursor() as cur:
        cur.execute(
            "SELECT c.conrelid::regclass::text AS tabela, c.confrelid::regclass::text AS alvo "
            "FROM pg_constraint c JOIN pg_attribute a "
            "  ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey) AND a.attname = 'subrede_id' "
            "WHERE c.contype = 'f' AND c.conrelid IN "
            "  ('plat.rede_no'::regclass, 'plat.rede_aresta'::regclass)"
        )
        alvos = {r["tabela"].split(".")[-1]: r["alvo"].split(".")[-1] for r in cur.fetchall()}
    assert alvos == {"rede_no": "rede_subrede", "rede_aresta": "rede_subrede"}, alvos


def test_as_duas_origens_na_mesma_tabela(rede_importada, conexao_plat_app):
    rid, _rede, _contagem = rede_importada
    con = conexao_plat_app
    with con.cursor() as cur:
        cur.execute(
            "SELECT origem, count(*) AS n, count(tier_id) AS com_tier, count(nivel) AS com_nivel, "
            "       array_agg(DISTINCT estado ORDER BY estado) AS estados "
            "FROM plat.rede_subrede WHERE rede_id = %s::uuid GROUP BY origem ORDER BY origem",
            (rid,),
        )
        por_origem = {r["origem"]: dict(r) for r in cur.fetchall()}
    assert set(por_origem) == {"bdgd", "controlador"}, por_origem
    derivada, declarada = por_origem["controlador"], por_origem["bdgd"]
    # 2 alimentadores + 1 transformador viraram subrede derivada
    assert derivada["n"] == 3 and derivada["com_tier"] == 3 and derivada["com_nivel"] == 0
    assert set(derivada["estados"]) <= {"limpa", "suja"}
    # 1 subestação + 2 alimentadores + 1 transformador declarados pelo arquivo
    assert declarada["n"] == 4 and declarada["com_tier"] == 0 and declarada["com_nivel"] == 4
    assert declarada["estados"] == ["declarada"]


# --- cláusula 2 e 3: a importação declara e reconcilia ---------------------------------------------------

def test_importar_declara_a_hierarquia_e_reconcilia(rede_importada, medida):
    rid, rede, contagem = rede_importada
    # o que já fazia continua igual (item L4-04-a)
    assert contagem["alimentadores_por_dispositivo"] == 1
    assert contagem["alimentadores_por_no_de_cabeca"] == 1
    assert contagem["transformadores_marcados"] == 1

    declarado = contagem["declarado"]
    assert declarado["subestacoes"] == 1 and declarado["alimentadores"] == 2
    assert declarado["transformadores"] == 1, declarado

    rec = contagem["reconciliacao"]
    assert rec["alimentadores"]["declaradas"] == 2
    assert rec["alimentadores"]["com_equivalente"] == 2
    assert rec["alimentadores"]["taxa"] == 1.0, rec
    assert rec["transformadores"]["com_equivalente"] == 1, rec

    assert rede["trafo"]["id"]
    gravar = medida(ITEM)
    comando = "bash laco/roda_teste.sh tests/api/test_rede_subrede_unificada.py"
    gravar("alimentadores_declarados_pelo_arquivo", rec["alimentadores"]["declaradas"], "alimentadores",
           comando + " (rede sintética de 2 alimentadores; a medida na cooperativa de teste está em "
                     "test_rede_subrede_unificada_medida.py)")
    gravar("alimentadores_reconciliados", rec["alimentadores"]["com_equivalente"], "alimentadores", comando)
    gravar("taxa_de_reconciliacao_sintetica", rec["alimentadores"]["taxa"],
           "razão sobre os alimentadores declarados", comando)


def test_importar_de_novo_nao_duplica_a_hierarquia_declarada(rede_importada, sessao_a):
    rid, _rede, _c = rede_importada
    segunda = sessao_a.post(f"/api/rede/{rid}/controladores/importar")
    assert segunda.status_code == 200, segunda.text
    corpo = segunda.json()
    assert corpo["declarado"]["subestacoes"] == 0 and corpo["declarado"]["alimentadores"] == 0
    assert corpo["declarado"]["ja_declaradas"] == 4, corpo["declarado"]
    assert corpo["reconciliacao"]["alimentadores"]["declaradas"] == 2
    assert corpo["reconciliacao"]["alimentadores"]["taxa"] == 1.0


# --- refutação -------------------------------------------------------------------------------------------

def test_ctmt_sem_disjuntor_reconcilia_pelo_no_de_cabeca(rede_importada, sessao_a, conexao_plat_app):
    """Refutação do portão: o alimentador que o arquivo declara mas cujo equipamento de saída NÃO está no
    arquivo tem de acabar com controlador no nó de cabeça e reconciliado — nunca subrede órfã."""
    rid, _rede, _c = rede_importada
    con = conexao_plat_app
    with con.cursor() as cur:
        cur.execute(
            "SELECT d.codigo_externo, d.equivalente_id, c.nome AS derivada, c.origem AS origem_derivada "
            "FROM plat.rede_subrede d LEFT JOIN plat.rede_subrede c ON c.id = d.equivalente_id "
            "WHERE d.rede_id = %s::uuid AND d.origem = 'bdgd' AND d.codigo_externo = %s",
            (rid, CTMT_SEM_EQUIPAMENTO),
        )
        r = cur.fetchone()
    assert r is not None, "o alimentador sem equipamento tem de estar declarado"
    assert r["equivalente_id"] is not None, "declarada sem equivalente = subrede órfã, o que a refutação proíbe"
    assert r["derivada"] == CTMT_SEM_EQUIPAMENTO and r["origem_derivada"] == "controlador"

    controladores = sessao_a.get(f"/api/rede/{rid}/controladores").json()["itens"]
    sem = [c for c in controladores if c["nome"] == CTMT_SEM_EQUIPAMENTO][0]
    assert sem["origem"] == "no_de_cabeca" and sem["no_id"], sem


# --- a tabela única não afrouxou regra -------------------------------------------------------------------

def test_forma_da_linha_depende_da_origem(conexao_plat_app):
    con = conexao_plat_app
    ids = ids_por_slug(con)
    tenant_id = ids["demo"]
    with con.cursor() as cur:
        contexto(con, tenant_id)
        cur.execute("SELECT id FROM plat.rede LIMIT 1")
        linha = cur.fetchone()
        if linha is None:
            pytest.skip("o inquilino demo não tem rede nenhuma nesta base")
        rede_id = linha["id"]
        with pytest.raises(Exception, match="rede_subrede_forma_da_origem"):
            cur.execute(
                "INSERT INTO plat.rede_subrede (tenant_id, rede_id, origem, estado, nome) "
                "VALUES (%s, %s::uuid, 'bdgd', 'declarada', 'zt-sem-nivel')",
                (tenant_id, rede_id),
            )
    con.rollback()
    with con.cursor() as cur:
        contexto(con, tenant_id)
        with pytest.raises(Exception, match="rede_subrede_forma_da_origem"):
            cur.execute(
                "INSERT INTO plat.rede_subrede (tenant_id, rede_id, origem, estado, nome, nivel, "
                "codigo_externo) VALUES (%s, %s::uuid, 'controlador', 'suja', 'zt-com-nivel', 1, 'zt')",
                (tenant_id, rede_id),
            )
    con.rollback()


def test_nivel_invertido_continua_recusado(conexao_plat_app):
    """A regra de nível estrito do item L4-01-c sobreviveu à unificação, com o MESMO nome de exceção."""
    con = conexao_plat_app
    ids = ids_por_slug(con)
    tenant_id = ids["demo"]
    with con.cursor() as cur:
        contexto(con, tenant_id)
        cur.execute("SELECT id FROM plat.rede LIMIT 1")
        linha = cur.fetchone()
        if linha is None:
            pytest.skip("o inquilino demo não tem rede nenhuma nesta base")
        rede_id = linha["id"]
        cur.execute(
            "INSERT INTO plat.rede_subrede (tenant_id, rede_id, origem, estado, nivel, codigo_externo, "
            "nome) VALUES (%s, %s::uuid, 'bdgd', 'declarada', 1, 'zt-u1', 'zt-u1') RETURNING id",
            (tenant_id, rede_id),
        )
        nivel1 = cur.fetchone()["id"]
        with pytest.raises(Exception, match="subrede_nivel_invertido"):
            cur.execute(
                "INSERT INTO plat.rede_subrede (tenant_id, rede_id, origem, estado, nivel, "
                "codigo_externo, nome, pai_id) "
                "VALUES (%s, %s::uuid, 'bdgd', 'declarada', 3, 'zt-u3', 'zt-u3', %s::uuid)",
                (tenant_id, rede_id, nivel1),
            )
    con.rollback()
