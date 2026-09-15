"""Item de seguimento de L0-04-a/L0-11 (achado do adversário, mesma causa raiz): `DELETE /api/exportacoes/{id}`
(cancelar a que roda / apagar o arquivo da que já terminou) exigia token `admin:inquilino` — só perfil admin
conseguia emitir esse escopo (`app/auth/rotas_tokens.py`) — embora a operação seja "cancelar/apagar a PRÓPRIA
exportação" (`_carregar` já recusa com 404 quem não é dono, nem tem `jobs.gerir_todos`) e `conteudo.exportar`
(o mesmo privilégio que já cobre `POST /api/exportacoes`) seja de perfil editor/admin, não só admin.

⚠ achado à parte, NÃO deste item: `POST /api/exportacoes` está QUEBRADO nesta wt/uniao para QUALQUER usuário
(inclusive admin) -- `app/jobs/tipos.py` (o agregador "importa cada módulo de tipos, o registro é preenchido
na importação") nunca importa `app.exportacao.tipos_job`, então o job `exportacao.gerar` nunca se registra e
`servico.criar(..., "exportacao.gerar", ...)` recusa com 422 tipo_desconhecido -- MEDIDO na HEAD de wt/uniao
(8129ca163), não é staleness deste branch. Fora do escopo deste item (não é ocorrência de `admin:inquilino`,
é um import que falta em outro módulo) -- reportado ao gerente, não corrigido aqui. Por isso a linha
`plat.exportacao` do teste é inserida DIRETO por SQL (`_inserir_exportacao_pendente`), no mesmo contexto de
RLS que a API usaria -- o que se prova aqui é o ESCOPO do DELETE, não o pipeline de geração do arquivo."""

import psycopg2

from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.catalogo.conftest import DADOS_POR_TIPO, titulo_zt
from tests.api.conftest import com_token, novo_cliente


def _criar_camada_exportavel(sessao) -> str:
    r = sessao.post("/api/itens", json={
        "tipo": "camada_vetorial", "titulo": titulo_zt("exportavel"),
        "dados": DADOS_POR_TIPO["camada_vetorial"],
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _inserir_exportacao_pendente(env, cliente, item_id: str, formato: str = "csv") -> str:
    """Insere a linha de `plat.exportacao` DIRETO no banco, no mesmo contexto de RLS (`set_config` local à
    transação, mesmo padrão de `tests/api/test_campo.py::_conexao_com_contexto_demo`) que `POST
    /api/exportacoes` usaria -- contorna o job `exportacao.gerar` não registrado (ver docstring do módulo)
    sem inventar nenhuma regra de acesso nova: é a MESMA policy `p_exportacao_inserir` (`tenant_id =
    plat.tenant_atual()`) que a rota usaria."""
    eu = cliente.get("/api/eu").json()
    usuario_id, slug = eu["id"], eu["inquilino"]["slug"]
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    con.autocommit = False
    try:
        with con.cursor() as cur:
            # plat.auth_login é SECURITY DEFINER (enxerga além do inquilino sem contexto ainda montado, mesmo
            # padrão de tests/api/test_rls.py::ids_por_slug); só o tenant_id importa aqui, o usuario_id do
            # 'admin' é descartado -- o contexto usa o usuario_id de QUEM CRIOU (`cliente`), não o admin.
            cur.execute("SELECT tenant_id FROM plat.auth_login(%s, 'admin')", (slug,))
            tenant_id = cur.fetchone()["tenant_id"]
            cur.execute(
                "SELECT set_config('plat.tenant_id', %s, true), set_config('plat.usuario_id', %s, true), "
                "set_config('plat.login', %s, true)",
                (str(tenant_id), str(usuario_id), "teste-exportacao"),
            )
            cur.execute(
                "INSERT INTO plat.exportacao(tenant_id, usuario_id, item_id, formato) "
                "VALUES (%s, %s, %s::uuid, %s) RETURNING id",
                (tenant_id, usuario_id, item_id, formato),
            )
            exportacao_id = str(cur.fetchone()["id"])
        con.commit()
    finally:
        con.close()
    return exportacao_id


def test_editor_comum_cancela_a_propria_exportacao_por_token_conteudo_exportar(usuarios_a, env):
    """Antes: token sem `admin:inquilino` -> 403 escopo_insuficiente em DELETE /api/exportacoes/{id}. Depois:
    token `conteudo:exportar` do próprio dono basta."""
    c_ed, _, _ = usuarios_a.sessao("editor")
    iid = _criar_camada_exportavel(c_ed)
    try:
        exportacao_id = _inserir_exportacao_pendente(env, c_ed, iid)
        assert c_ed.get(f"/api/exportacoes/{exportacao_id}").json()["estado"] == "pendente"

        r_tok = c_ed.post("/api/tokens", json={"nome": titulo_zt("tok-exportar"), "escopos": ["conteudo:exportar"]})
        assert r_tok.status_code == 201, r_tok.text
        tok, tok_id = r_tok.json()["token"], r_tok.json()["id"]
        cliente = novo_cliente()
        try:
            r_del = com_token(cliente, tok, "DELETE", f"/api/exportacoes/{exportacao_id}")
            assert r_del.status_code == 204, r_del.text
            assert c_ed.get(f"/api/exportacoes/{exportacao_id}").json()["estado"] == "cancelada"

            # o mesmo token não vira admin:inquilino por tabela
            r_neg = c_ed.post("/api/tokens", json={"nome": titulo_zt("nega-admin"), "escopos": ["admin:inquilino"]})
            assert r_neg.status_code == 422 and r_neg.json()["erro"] == "escopo_fora_do_teto"
        finally:
            c_ed.delete(f"/api/tokens/{tok_id}")
    finally:
        c_ed.delete(f"/api/itens/{iid}")


def test_token_catalogo_ler_nao_apaga_exportacao(usuarios_a, env):
    """Escopo errado continua recusado: `catalogo:ler` não cobre `conteudo:exportar`."""
    c_ed, _, _ = usuarios_a.sessao("editor")
    iid = _criar_camada_exportavel(c_ed)
    try:
        exportacao_id = _inserir_exportacao_pendente(env, c_ed, iid)

        r_tok = c_ed.post("/api/tokens", json={"nome": titulo_zt("tok-ler"), "escopos": ["catalogo:ler"]})
        assert r_tok.status_code == 201, r_tok.text
        tok_id = r_tok.json()["id"]
        try:
            r = com_token(novo_cliente(), r_tok.json()["token"], "DELETE", f"/api/exportacoes/{exportacao_id}")
            assert r.status_code == 403 and r.json()["erro"] == "escopo_insuficiente"
            assert r.json()["detalhe"]["exigido"] == "conteudo:exportar"
        finally:
            c_ed.delete(f"/api/tokens/{tok_id}")
        c_ed.delete(f"/api/exportacoes/{exportacao_id}")
    finally:
        c_ed.delete(f"/api/itens/{iid}")


def test_outro_dono_nao_apaga_exportacao_por_token(usuarios_a, env):
    """RLS/dono cruzado intacta: o token `conteudo:exportar` de um SEGUNDO editor (mesmo inquilino) não cancela
    a exportação de quem não é ele (`_carregar` recusa com 404 quem não é dono e não tem `jobs.gerir_todos`)."""
    c_ed, _, _ = usuarios_a.sessao("editor")
    c_outro, _, _ = usuarios_a.sessao("editor")
    iid = _criar_camada_exportavel(c_ed)
    try:
        exportacao_id = _inserir_exportacao_pendente(env, c_ed, iid)

        r_tok = c_outro.post("/api/tokens", json={"nome": titulo_zt("tok-outro"), "escopos": ["conteudo:exportar"]})
        assert r_tok.status_code == 201, r_tok.text
        tok_id = r_tok.json()["id"]
        try:
            r = com_token(novo_cliente(), r_tok.json()["token"], "DELETE", f"/api/exportacoes/{exportacao_id}")
            assert r.status_code == 404, r.text
        finally:
            c_outro.delete(f"/api/tokens/{tok_id}")
        c_ed.delete(f"/api/exportacoes/{exportacao_id}")
    finally:
        c_ed.delete(f"/api/itens/{iid}")
