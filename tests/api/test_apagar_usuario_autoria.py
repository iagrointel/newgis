"""Trava do item F2-FKSTALE: `criado_por`/`apagado_por`/`modificado_por` de `plat.item` (e `criado_por` de
`plat.arquivo`) são AUTORIA — rastro histórico de quem agiu — nunca POSSE. `_itens_do_dono` (app/auth/
rotas_usuarios.py) já barra a exclusão de quem é DONO (`dono_id`, política escrita em
016_catalogo_apagar_usuario.sql); este teste prova o outro lado, que o bug original apagava: um usuário que só
CRIOU um item (não é mais o dono, por transferência) tem de poder ser apagado, e o item sobrevive com
`criado_por = NULL` em vez de travar num `em_uso` genérico. Medido antes do conserto (migração
20260915T2349_fk_autoria_ator_fora_do_inquilino.sql): `arquivo.criado_por` não tinha `ON DELETE SET NULL`
nenhum, e travava até a limpeza de usuários `zt*` do `laco/trilha_ambiente.sh`."""

import secrets

from tests.api.conftest import PREFIXO_TESTE
from tests.api.test_rls import contexto, ids_por_slug


def test_apagar_usuario_com_item_criado_mas_nao_dono_mantem_item_com_criado_por_nulo(
    sessao_a, usuarios_a, conexao_plat_app
):
    admin_id = sessao_a.get("/api/eu").json()["id"]  # sem depender de `ids` (sessao_plat): menos contenção
    autor_c, autor_u, _ = usuarios_a.sessao("editor")
    r = autor_c.post(
        "/api/itens",
        json={
            "tipo": "mapa",
            "titulo": f"{PREFIXO_TESTE}-autoria-{secrets.token_hex(2)}",
            "dados": {"esquema_versao": 1, "corpo": {}},
        },
    )
    assert r.status_code == 201, r.text
    item = r.json()
    assert item["dono"]["id"] == autor_u["id"]
    assert item["criado_por"]["id"] == autor_u["id"]

    # transfere a posse para o admin (fora da API de transferência: aqui só a mecânica de dono_id importa,
    # não o plano dela) — depois disso o autor não é mais dono, só quem criou.
    tenant_id = ids_por_slug(conexao_plat_app)["demo"]
    contexto(conexao_plat_app, tenant_id, usuario_id=admin_id, login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT set_config('plat.transferencia', 'on', true)")
        cur.execute("UPDATE plat.item SET dono_id = %s WHERE id = %s::uuid", (admin_id, item["id"]))
    conexao_plat_app.commit()

    # sem itens dos quais é DONO, apagar o autor não esbarra em possui_itens (isso já era coberto por
    # test_usuarios.py::test_apagar_com_2_itens_do_catalogo_recusa_listando_os_2 do lado oposto)
    r = sessao_a.delete(f"/api/usuarios/{autor_u['id']}")
    assert r.status_code == 204, r.text
    usuarios_a.criados.remove(autor_u["id"])

    r = sessao_a.get(f"/api/itens/{item['id']}")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["dono"]["id"] == admin_id, "o item continua existindo, com o dono que já tinha antes da exclusão"
    assert j["criado_por"] is None, "criado_por é autoria (histórico): vira NULL, nunca trava a exclusão do ator"

    itens_a_apagar_no_fim = sessao_a.delete(f"/api/itens/{item['id']}")
    assert itens_a_apagar_no_fim.status_code == 204


def test_apagar_usuario_com_arquivo_criado_nao_trava_na_fk(sessao_a, usuarios_a, conexao_plat_app):
    """`plat.arquivo` não tem "dono", só `criado_por` — puramente autoria. Antes do conserto, a FK
    `arquivo_tenant_criado_por_fkey` não tinha `ON DELETE SET NULL` nenhum (nem simples, nem composto): apagar
    o usuário estourava em_uso citando essa constraint, mesmo sem nenhuma checagem de app avisando por quê."""
    admin_id = sessao_a.get("/api/eu").json()["id"]
    autor_c, autor_u, _ = usuarios_a.sessao("editor")
    tenant_id = ids_por_slug(conexao_plat_app)["demo"]
    contexto(conexao_plat_app, tenant_id, usuario_id=autor_u["id"], login=autor_u["login"])
    sha = secrets.token_hex(32)
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "INSERT INTO plat.arquivo(tenant_id, classe, sha256, bytes, content_type, chave, criado_por) "
            "VALUES (%s, 'objeto', %s, 10, 'application/octet-stream', %s, %s) RETURNING id",
            (tenant_id, sha, f"zt/objeto/{sha}.bin", autor_u["id"]),
        )
        arquivo_id = cur.fetchone()["id"]
    conexao_plat_app.commit()

    r = sessao_a.delete(f"/api/usuarios/{autor_u['id']}")
    assert r.status_code == 204, r.text
    usuarios_a.criados.remove(autor_u["id"])

    contexto(conexao_plat_app, tenant_id, usuario_id=admin_id, login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT criado_por FROM plat.arquivo WHERE id = %s", (arquivo_id,))
        assert cur.fetchone()["criado_por"] is None
        cur.execute("DELETE FROM plat.arquivo WHERE id = %s", (arquivo_id,))
    conexao_plat_app.commit()
