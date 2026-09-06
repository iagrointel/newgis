"""A TRAVA do achado A1 (item L4-01-a-pacote-de-ativos, adversário do turno 3, `handoffs/T3/
ataque-L4-portal-ADVERSARIO.md`): uma chave estrangeira simples (só por `id`) entre duas tabelas que TÊM
`tenant_id` não é filtrada pela RLS. `plat_app`, autenticado no inquilino B, consegue pendurar uma linha SUA
apontando para o `id` de uma linha de OUTRO inquilino — a FK só confere que o id existe em algum lugar da
tabela, nunca que é do mesmo tenant_id da linha que está sendo gravada; isso também vira um oráculo de
existência (uuid alheio é aceito, uuid inventado é recusado).

Este teste varre `pg_constraint` do schema inteiro (não só as 10 tabelas de `plat.rede_*`) e reprova toda FK
cujas duas tabelas tenham `tenant_id` mas cujas colunas da FK não incluam `tenant_id` — a migração
`20260906T1815_rede_fk_por_inquilino.sql` trocou as 10 da rede por FK composta `(tenant_id, id)`; qualquer
tabela nova do produto que repita o padrão simples cai aqui.

`PERMITIDAS` é uma exceção NOMEADA, nunca um jeito de calar o teste: só entra aqui uma FK que já foi
avaliada e é LEGÍTIMA sem ser composta (ex.: alvo é dicionário global sem inquilino — caso que nem chega a
este dict, porque a varredura já exige `tenant_id` dos dois lados). Uma FK nova nesta lista sem justificativa
escrita é bug de quem editou o teste, não do produto.

Item FK-CLASSE-CONSERTO (turno 3, 06/09/2026, `handoffs/T3/FK-CLASSE-CONSERTO.md`) consertou as 44 das 55
achadas nesta varredura que já existiam no schema `master` (migração `20260906T1847_fk_por_inquilino_classe.sql`,
mesmo padrão da `20260906T1815_rede_fk_por_inquilino.sql`). As outras 11 (`exportacao`×3, `geocodificacao`/
`geocodificacao_linha`×3, `raster_item`/`raster_colecao`×3, `rede.dono_id`/`rede.importado_por`×2) pertencem a
tabelas que AINDA NÃO EXISTEM em `master` — vêm de trilhas em voo (garage/valida/stac) não mescladas. Não
entraram como exceção permanente de propósito: quando aquela trilha mesclar, esta trava vai acusar a mesma
classe de falha e quem mesclar aplica o MESMO padrão (`UNIQUE (tenant_id, id)` no alvo + FK composta) —
listar como "fora do escopo" para sempre deixaria a dívida crescer sem prazo."""

import pytest

# (tabela_filha, coluna_da_fk) -> justificativa. Vazio: nenhuma FK simples entre tabelas com tenant_id
# ficou sem conserto neste schema (ver histórico acima — as 11 que faltam são de tabelas que não existem
# em `master`, não exceções). Uma entrada nova aqui exige justificativa escrita, não apaga achado.
PERMITIDAS: dict[tuple[str, str], str] = {}


def _fks_simples_entre_tabelas_com_tenant(cur) -> list[dict]:
    cur.execute(
        """
        SELECT
          nc.nspname AS schema_filha, tc.relname AS tabela_filha, con.conname AS nome,
          tf.relname AS tabela_alvo,
          (SELECT array_agg(a.attname ORDER BY a.attnum)
             FROM pg_attribute a WHERE a.attrelid = tc.oid AND a.attnum = ANY(con.conkey)) AS colunas_filha,
          EXISTS (SELECT 1 FROM pg_attribute x
                    WHERE x.attrelid = tc.oid AND x.attname = 'tenant_id' AND NOT x.attisdropped) AS filha_tem_tenant,
          EXISTS (SELECT 1 FROM pg_attribute y
                    WHERE y.attrelid = tf.oid AND y.attname = 'tenant_id' AND NOT y.attisdropped) AS alvo_tem_tenant
        FROM pg_constraint con
        JOIN pg_class tc ON tc.oid = con.conrelid
        JOIN pg_namespace nc ON nc.oid = tc.relnamespace
        JOIN pg_class tf ON tf.oid = con.confrelid
        WHERE con.contype = 'f' AND nc.nspname = 'plat'
        ORDER BY tc.relname, con.conname
        """
    )
    achados = []
    for r in cur.fetchall():
        if not (r["filha_tem_tenant"] and r["alvo_tem_tenant"]):
            continue
        colunas = list(r["colunas_filha"] or [])
        if "tenant_id" in colunas:
            continue  # já é composta (ou o próprio tenant_id é a FK, caso trivial)
        achados.append({
            "tabela_filha": r["tabela_filha"], "colunas_filha": colunas,
            "tabela_alvo": r["tabela_alvo"], "constraint": r["nome"],
        })
    return achados


def test_toda_fk_entre_tabelas_com_tenant_id_e_composta_por_inquilino(conexao_plat_app):
    with conexao_plat_app.cursor() as cur:
        achados = _fks_simples_entre_tabelas_com_tenant(cur)
    nao_permitidos = [
        a for a in achados
        if (a["tabela_filha"], a["colunas_filha"][0] if a["colunas_filha"] else "") not in PERMITIDAS
    ]
    assert nao_permitidos == [], (
        "FK simples entre tabelas com tenant_id (a RLS não filtra isto — vazamento tipo A1 do L4-01-a): "
        f"{nao_permitidos}"
    )


REDE = ("rede_dominio", "rede_tier", "rede_categoria", "rede_terminal_config", "rede_grupo", "rede_tipo",
        "rede_tipo_categoria", "rede_atributo", "rede_regra")


@pytest.mark.parametrize("tabela", REDE)
def test_as_dez_tabelas_da_rede_nao_tem_mais_fk_simples(conexao_plat_app, tabela):
    """As 10 tabelas do achado A1, uma por uma: nenhuma FK saindo delas pode ter ficado simples."""
    with conexao_plat_app.cursor() as cur:
        achados = _fks_simples_entre_tabelas_com_tenant(cur)
    assert [a for a in achados if a["tabela_filha"] == tabela] == []
