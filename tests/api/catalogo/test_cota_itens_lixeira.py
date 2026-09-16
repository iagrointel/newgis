"""Refutação do item L0-07-c-cotas-uso ("apaga item para liberar cota antes do expurgo — a lixeira conta na
cota"), aplicada a cota_itens: a RLS de leitura de plat.item esconde item apagado por padrão (migrações
017/018, `apagado_em IS NULL OR current_setting('plat.lixeira') = 'on'`). Um `count(*)` cru na checagem de
cota_itens (app/catalogo/rotas_itens.py, app/acervo/rotas.py, app/conexao/rotas.py) contava só os VIVOS —
apagar um item "liberava" uma vaga na cota antes do expurgo físico de verdade. Corrigido com
app/cotas.py::contar_itens_com_lixeira (liga a GUC antes de contar); este teste prova a diferença direto no
banco, com o mesmo mecanismo que as três rotas agora chamam."""

from app import cotas
from tests.api.catalogo.conftest import titulo_zt
from tests.api.test_rls import contexto, ids_por_slug


def test_item_apagado_ainda_conta_na_cota_ate_o_expurgo(sessao_a, itens_a, conexao_plat_app):
    """Medido por linha (`WHERE id = <o item criado aqui>`), nunca pelo total do inquilino: a trilha `uniao` é
    compartilhada por vários worktrees ao mesmo tempo, todos criando/apagando item no MESMO inquilino `demo`
    (achado 16/09 do laço f2fixcatalogo — a versão antiga comparava `count(*) FROM plat.item WHERE tenant_id
    = demo` antes/depois e caía sempre que outro worktree tocava o inquilino no meio dos dois SELECTs; a conta
    por id prova exatamente a mesma coisa — count cru esconde o apagado, contar_itens_com_lixeira não —
    sem depender de mais ninguém ficar quieto)."""
    ids_map = ids_por_slug(conexao_plat_app)
    tenant_id = ids_map["demo"]
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT usuario_id FROM plat.auth_login('demo', 'admin')")
        adm = cur.fetchone()["usuario_id"]

    it = itens_a.criar("mapa", titulo=titulo_zt("cota-itens-lixeira"))

    contexto(conexao_plat_app, tenant_id, usuario_id=adm, login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM plat.item WHERE id = %s::uuid", (it["id"],))
        antes = cur.fetchone()["n"]
    # commit fecha a transação: set_config(..., true) dentro de contar_itens_com_lixeira é LOCAL a ela (senão
    # a GUC ligada aqui "vazaria" para a próxima medição e mascararia exatamente o que este teste prova).
    conexao_plat_app.commit()
    assert antes == 1, "controle: o item recém-criado tem de aparecer no count() cru"

    assert sessao_a.delete(f"/api/itens/{it['id']}").status_code == 204

    contexto(conexao_plat_app, tenant_id, usuario_id=adm, login="admin")
    with conexao_plat_app.cursor() as cur:
        # count(*) CRU (o que as três rotas faziam antes da correção): esconde o item recém-apagado — é
        # exatamente a brecha da refutação, reproduzida aqui como controle negativo. Filtrado por id, não
        # pelo total do inquilino: outro worktree criando/apagando item no MESMO `demo` não interfere.
        cur.execute("SELECT count(*) AS n FROM plat.item WHERE id = %s::uuid", (it["id"],))
        cru_depois = cur.fetchone()["n"]
    conexao_plat_app.commit()

    contexto(conexao_plat_app, tenant_id, usuario_id=adm, login="admin")
    with conexao_plat_app.cursor() as cur:
        # a função corrigida (a que as rotas usam agora) soma pelo INQUILINO inteiro (é o que a cota mede) —
        # aqui só confere que o item apagado passa a contar TAMBÉM sob a GUC, com a mesma consulta por id.
        cur.execute("SELECT set_config('plat.lixeira', 'on', true)")
        cur.execute("SELECT count(*) AS n FROM plat.item WHERE id = %s::uuid", (it["id"],))
        corrigido_depois = cur.fetchone()["n"]
        # smoke real da função de produção (não só a mecânica reproduzida acima): o total do inquilino tem de
        # incluir pelo menos este item ainda não expurgado — cota nunca é menor que 1 aqui, mesmo com outro
        # worktree mexendo no resto do inquilino ao mesmo tempo.
        corrigido_tenant = cotas.contar_itens_com_lixeira(cur, tenant_id)
    conexao_plat_app.commit()

    assert cru_depois == 0, "controle: o count() cru tem de perder o item apagado (é a brecha antiga)"
    assert corrigido_depois == 1, (
        "contar_itens_com_lixeira (mesma GUC) tem de manter o item na cota até o expurgo físico — sem isso, "
        "apagar libera vaga sem liberar nada de verdade"
    )
    assert corrigido_tenant >= 1, "cotas.contar_itens_com_lixeira tem de contar o item apagado no total do inquilino"
