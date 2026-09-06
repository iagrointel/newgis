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

`PERMITIDAS` é uma exceção NOMEADA, nunca um jeito de calar o teste: cada entrada aqui é uma FK que já existia
achada por esta varredura e pertence a OUTRO item (não fechado, não é a rede) — listada no handoff, não
consertada nesta trilha. Uma FK nova nesta lista sem dono é bug de quem editou o teste, não do produto."""

import pytest

# (tabela_filha, coluna_da_fk) -> item responsável. Achadas na mesma varredura, fora do escopo de L4-01-a;
# ver handoffs/T3/L4-01-a-CONSERTO.md secão "fora do escopo".
PERMITIDAS: dict[tuple[str, str], str] = {
    # varredura de 06/09 (turno 3, item L4-01-a-pacote-de-ativos): mesma classe de falha do achado A1
    # (a FK não confere que o alvo é do mesmo tenant_id), mas em tabelas de OUTROS itens — nenhuma é
    # `plat.rede_*`. Listadas em handoffs/T3/L4-01-a-CONSERTO.md § "fora do escopo"; não consertadas
    # aqui. A maioria aponta para `plat.usuario`/`plat.item`/`plat.pasta` (o dono/criador de um
    # registro) e nasceu antes deste item — cada dono de tabela decide se compõe a FK por tenant_id
    # ou por gatilho.
    ("agenda", "usuario_id"): "fora do escopo de L4-01-a",
    ("arquivo", "criado_por"): "fora do escopo de L4-01-a",
    ("categoria", "pai_id"): "fora do escopo de L4-01-a",
    ("compartilhamento_link_item", "item_id"): "fora do escopo de L4-01-a",
    ("compartilhamento_link_item", "link_id"): "fora do escopo de L4-01-a",
    ("compartilhamento_link", "criado_por"): "fora do escopo de L4-01-a",
    ("compartilhamento_link", "item_id"): "fora do escopo de L4-01-a",
    ("conexao_saude_historico", "conexao_id"): "fora do escopo de L4-01-a",
    ("conexao", "dono_id"): "fora do escopo de L4-01-a",
    ("convite", "criado_por"): "fora do escopo de L4-01-a",
    ("convite", "papel_id"): "fora do escopo de L4-01-a",
    ("convite", "usuario_criado_id"): "fora do escopo de L4-01-a",
    ("exportacao", "arquivo_item_id"): "fora do escopo de L4-01-a",
    ("exportacao", "item_id"): "fora do escopo de L4-01-a",
    ("exportacao", "usuario_id"): "fora do escopo de L4-01-a",
    ("favorito", "item_id"): "fora do escopo de L4-01-a",
    ("favorito", "usuario_id"): "fora do escopo de L4-01-a",
    ("geocodificacao_linha", "geocodificacao_id"): "fora do escopo de L4-01-a",
    ("geocodificacao", "arquivo_id"): "fora do escopo de L4-01-a",
    ("geocodificacao", "usuario_id"): "fora do escopo de L4-01-a",
    ("grupo_membro", "convidado_por"): "fora do escopo de L4-01-a",
    ("grupo_membro", "grupo_id"): "fora do escopo de L4-01-a",
    ("grupo_membro", "usuario_id"): "fora do escopo de L4-01-a",
    ("grupo", "dono_id"): "fora do escopo de L4-01-a",
    ("importacao", "arquivo_id"): "fora do escopo de L4-01-a",
    ("importacao", "usuario_id"): "fora do escopo de L4-01-a",
    ("item_grupo", "grupo_id"): "fora do escopo de L4-01-a",
    ("item_grupo", "item_id"): "fora do escopo de L4-01-a",
    ("item_relacao", "destino"): "fora do escopo de L4-01-a",
    ("item_relacao", "origem"): "fora do escopo de L4-01-a",
    ("item_versao", "item_id"): "fora do escopo de L4-01-a",
    ("item", "apagado_por"): "fora do escopo de L4-01-a",
    ("item", "criado_por"): "fora do escopo de L4-01-a",
    ("item", "dono_id"): "fora do escopo de L4-01-a",
    ("item", "modificado_por"): "fora do escopo de L4-01-a",
    ("item", "pasta_id"): "fora do escopo de L4-01-a",
    ("job_log", "job_id"): "fora do escopo de L4-01-a",
    ("job", "usuario_id"): "fora do escopo de L4-01-a",
    ("papel_personalizado", "criado_por"): "fora do escopo de L4-01-a",
    ("pasta", "dono_id"): "fora do escopo de L4-01-a",
    ("pasta", "pai_id"): "fora do escopo de L4-01-a",
    ("provedor_ldap", "atualizado_por"): "fora do escopo de L4-01-a",
    ("provedor_ldap", "criado_por"): "fora do escopo de L4-01-a",
    ("raster_colecao", "criado_por"): "fora do escopo de L4-01-a",
    ("raster_item", "colecao"): "fora do escopo de L4-01-a",
    ("raster_item", "criado_por"): "fora do escopo de L4-01-a",
    ("redefinicao_senha", "usuario_id"): "fora do escopo de L4-01-a",
    ("rede", "dono_id"): "fora do escopo de L4-01-a — aponta para usuario, não para outra plat.rede_*",
    ("rede", "importado_por"): "fora do escopo de L4-01-a — aponta para usuario, não para outra plat.rede_*",
    ("sessao", "usuario_id"): "fora do escopo de L4-01-a",
    ("token_servico", "renovado_por"): "fora do escopo de L4-01-a",
    ("token_servico", "usuario_id"): "fora do escopo de L4-01-a",
    ("upload", "arquivo_id"): "fora do escopo de L4-01-a",
    ("upload", "usuario_id"): "fora do escopo de L4-01-a",
    ("usuario", "papel_id"): "fora do escopo de L4-01-a",
}


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
