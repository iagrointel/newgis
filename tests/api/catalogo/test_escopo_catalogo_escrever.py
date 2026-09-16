"""Item de seguimento de L0-04-a/L0-11 (achado do adversário, mesma causa raiz): as escritas de `/api/itens`
caíam no padrão `admin:inquilino` de `autenticado()` quando `escopo_token` não era passado, embora a operação
seja "criar/editar/apagar o PRÓPRIO item" (RLS `plat.pode_editar` / privilégio `conteudo.criar`, nunca
administração do inquilino). Um editor comum (perfil `editor`, sem `admin:inquilino`) não conseguia emitir
nenhum token para essas rotas. Prova: `POST /api/itens` exige token `conteudo:criar`; as demais escritas
(PUT/PATCH/DELETE/lote/mover/versão/relações) exigem `catalogo:escrever`; visualizador sem `conteudo.criar`
continua sem conseguir criar; RLS entre inquilinos continua recusando."""

from tests.api.catalogo.conftest import titulo_zt
from tests.api.conftest import com_token, novo_cliente


def test_editor_comum_cria_por_token_conteudo_criar(usuarios_a):
    """Antes: token `catalogo:ler` (ou nenhum escopo dedicado) -> 403 escopo_insuficiente em POST /api/itens,
    porque o padrão de `autenticado()` sem `escopo_token` explícito é `admin:inquilino`. Depois: token
    `conteudo:criar` de um editor comum cria o item (201)."""
    c_ed, _, _ = usuarios_a.sessao("editor")
    r_tok = c_ed.post("/api/tokens", json={"nome": f"{titulo_zt('tok-criar')}", "escopos": ["conteudo:criar"]})
    assert r_tok.status_code == 201, r_tok.text
    tok = r_tok.json()["token"]
    tok_id = r_tok.json()["id"]
    cliente = novo_cliente()
    try:
        corpo = {"tipo": "mapa", "titulo": titulo_zt("por-token"), "dados": {"esquema_versao": 1, "corpo": {}}}
        r = com_token(cliente, tok, "POST", "/api/itens", json=corpo)
        assert r.status_code == 201, r.text
        iid = r.json()["id"]

        # com token só catalogo:ler (sem conteudo:criar), a mesma criação é recusada
        r_tok_ler = c_ed.post("/api/tokens", json={"nome": titulo_zt("tok-ler"), "escopos": ["catalogo:ler"]})
        assert r_tok_ler.status_code == 201, r_tok_ler.text
        try:
            r_neg = com_token(
                novo_cliente(), r_tok_ler.json()["token"], "POST", "/api/itens",
                json={**corpo, "titulo": titulo_zt("recusado")},
            )
            assert r_neg.status_code == 403 and r_neg.json()["erro"] == "escopo_insuficiente"
            assert r_neg.json()["detalhe"]["exigido"] == "conteudo:criar"
        finally:
            c_ed.delete(f"/api/tokens/{r_tok_ler.json()['id']}")

        c_ed.delete(f"/api/itens/{iid}")
    finally:
        c_ed.delete(f"/api/tokens/{tok_id}")


def test_visualizador_nao_ganha_token_conteudo_criar(usuarios_a):
    """Simetria: perfil `visualizador` não tem `conteudo.criar` (só editor/admin) — continua sem conseguir se
    emitir um token para criar item; o teto virou por PRIVILÉGIO, não abriu geral."""
    c_vis, _, _ = usuarios_a.sessao("visualizador")
    r = c_vis.post("/api/tokens", json={"nome": titulo_zt("vis-criar"), "escopos": ["conteudo:criar"]})
    assert r.status_code == 422 and r.json()["erro"] == "escopo_fora_do_teto"


def test_editor_comum_edita_apaga_proprio_item_por_token_catalogo_escrever(usuarios_a):
    """Antes: token sem `admin:inquilino` -> 403 escopo_insuficiente em PUT/PATCH/DELETE, mover, lote e
    versão/relações — só perfil admin conseguia emitir esse escopo. Depois: token `catalogo:escrever` do
    próprio dono do item basta (RLS `pode_editar` continua sendo quem manda por baixo)."""
    c_ed, _, _ = usuarios_a.sessao("editor")
    r_item = c_ed.post(
        # tipo "conexao": sem extrator de relações (app/catalogo/relacoes.py EXTRATORES), então
        # PUT .../relacoes não recusa com 409 relacoes_pelo_tipo
        "/api/itens",
        json={"tipo": "conexao", "titulo": titulo_zt("escrever"),
              "dados": {"protocolo": "wms", "url": "https://exemplo.gov.br/wms"}},
    )
    assert r_item.status_code == 201, r_item.text
    iid = r_item.json()["id"]

    r_tok = c_ed.post("/api/tokens", json={"nome": titulo_zt("tok-escrever"), "escopos": ["catalogo:escrever"]})
    assert r_tok.status_code == 201, r_tok.text
    tok, tok_id = r_tok.json()["token"], r_tok.json()["id"]
    cliente = novo_cliente()
    try:
        r_put = com_token(cliente, tok, "PUT", f"/api/itens/{iid}", json={"titulo": titulo_zt("editado")})
        assert r_put.status_code == 200, r_put.text
        r_patch = com_token(cliente, tok, "PATCH", f"/api/itens/{iid}", json={"resumo": "novo resumo"})
        assert r_patch.status_code == 200, r_patch.text
        r_mover = com_token(cliente, tok, "POST", f"/api/itens/{iid}/mover", json={"pasta_id": None})
        assert r_mover.status_code == 200, r_mover.text
        r_lote = com_token(cliente, tok, "POST", "/api/itens/lote", json={"ids": [iid], "acao": "proteger"})
        assert r_lote.status_code == 200 and r_lote.json()["feitos"] == 1, r_lote.text
        r_desproteger = com_token(cliente, tok, "POST", "/api/itens/lote", json={"ids": [iid], "acao": "desproteger"})
        assert r_desproteger.status_code == 200, r_desproteger.text
        r_rel = com_token(cliente, tok, "PUT", f"/api/itens/{iid}/relacoes", json={"relacoes": []})
        assert r_rel.status_code == 200, r_rel.text
        r_pub = com_token(cliente, tok, "POST", f"/api/itens/{iid}/versoes/1/publicar")
        assert r_pub.status_code == 200, r_pub.text
        r_del = com_token(cliente, tok, "DELETE", f"/api/itens/{iid}")
        assert r_del.status_code == 204, r_del.text

        # o mesmo token (catalogo:escrever) não vira admin:inquilino por tabela
        r_neg = c_ed.post("/api/tokens", json={"nome": titulo_zt("nega-admin"), "escopos": ["admin:inquilino"]})
        assert r_neg.status_code == 422 and r_neg.json()["erro"] == "escopo_fora_do_teto"
    finally:
        c_ed.delete(f"/api/tokens/{tok_id}")


def test_editor_comum_valida_e_salva_metadado_por_token_catalogo_escrever(usuarios_a):
    """Achado 15/09 (wt/f2-tiposjob, commit 3b1894b1c): `POST /api/itens/{id}/metadado/validar` e
    `PUT /api/itens/{id}/metadado` nasceram com `autenticado()` sem `escopo_token` (padrão `admin:inquilino`),
    mesma causa raiz de 542dce33d/8c58f8cba — um editor comum não conseguia emitir token para o próprio
    editor de metadado da tela. Depois: `catalogo:escrever` (mesmo escopo das outras escritas de item)
    basta para as duas rotas."""
    c_ed, _, _ = usuarios_a.sessao("editor")
    r_item = c_ed.post(
        "/api/itens",
        json={"tipo": "mapa", "titulo": titulo_zt("metadado"), "dados": {"esquema_versao": 1, "corpo": {}}},
    )
    assert r_item.status_code == 201, r_item.text
    iid = r_item.json()["id"]

    r_tok = c_ed.post("/api/tokens", json={"nome": titulo_zt("tok-metadado"), "escopos": ["catalogo:escrever"]})
    assert r_tok.status_code == 201, r_tok.text
    tok, tok_id = r_tok.json()["token"], r_tok.json()["id"]
    cliente = novo_cliente()
    try:
        r_validar = com_token(cliente, tok, "POST", f"/api/itens/{iid}/metadado/validar", json={})
        assert r_validar.status_code == 200, r_validar.text
        r_salvar = com_token(cliente, tok, "PUT", f"/api/itens/{iid}/metadado", json={})
        assert r_salvar.status_code == 200, r_salvar.text
    finally:
        c_ed.delete(f"/api/tokens/{tok_id}")
        c_ed.delete(f"/api/itens/{iid}")


def test_visualizador_com_token_catalogo_escrever_nao_salva_metadado_de_item_alheio(usuarios_a):
    """Simetria da anterior: `catalogo:escrever` não tem teto por privilégio no ato de emitir o token (ao
    contrário de `conteudo:criar`) — um visualizador CONSEGUE se emitir o token. Quem barra é a RLS
    `pode_editar` dentro da rota (`exigir_edicao`, 403 `sem_edicao_no_item`), a mesma trava de
    PUT/PATCH/DELETE. Item só de posse (sem compartilhar) dá 404 (RLS de leitura, `test_niveis_e_grupo`
    já cobre isso) — para separar "não lê" de "lê mas não edita" o item é compartilhado por GRUPO com o
    visualizador (mesma receita de tests/api/catalogo/test_compartilhamento.py), que fica com
    `pode_editar=False` e ainda assim vê o item."""
    c_ed, _, _ = usuarios_a.sessao("editor")
    c_vis, u_vis, _ = usuarios_a.sessao("visualizador")
    r_item = c_ed.post(
        "/api/itens",
        json={"tipo": "mapa", "titulo": titulo_zt("metadado-alheio"), "dados": {"esquema_versao": 1, "corpo": {}}},
    )
    assert r_item.status_code == 201, r_item.text
    iid = r_item.json()["id"]
    try:
        r_grupo = c_ed.post("/api/grupos", json={"nome": titulo_zt("grupo-metadado"), "entrada": "convite"})
        assert r_grupo.status_code == 201, r_grupo.text
        gid = r_grupo.json()["id"]
        try:
            r_membro = c_ed.post(f"/api/grupos/{gid}/membros", json={"usuario_id": u_vis["id"]})
            assert r_membro.status_code == 201, r_membro.text
            assert c_vis.post(f"/api/grupos/{gid}/aceitar").status_code == 200
            r_comp = c_ed.put(f"/api/itens/{iid}/compartilhamento", json={"grupos": [gid]})
            assert r_comp.status_code == 200, r_comp.text
            r_ver = c_vis.get(f"/api/itens/{iid}")
            assert r_ver.status_code == 200 and r_ver.json()["pode_editar"] is False, r_ver.text

            r_tok = c_vis.post(
                "/api/tokens", json={"nome": titulo_zt("tok-vis"), "escopos": ["catalogo:escrever"]}
            )
            assert r_tok.status_code == 201, r_tok.text
            tok, tok_id = r_tok.json()["token"], r_tok.json()["id"]
            cliente = novo_cliente()
            try:
                r_salvar = com_token(cliente, tok, "PUT", f"/api/itens/{iid}/metadado", json={})
                assert r_salvar.status_code == 403 and r_salvar.json()["erro"] == "sem_edicao_no_item", (
                    r_salvar.text
                )
                r_validar = com_token(cliente, tok, "POST", f"/api/itens/{iid}/metadado/validar", json={})
                assert r_validar.status_code == 200, r_validar.text
            finally:
                c_vis.delete(f"/api/tokens/{tok_id}")
        finally:
            c_ed.delete(f"/api/grupos/{gid}")
    finally:
        c_ed.delete(f"/api/itens/{iid}")


def test_token_catalogo_escrever_de_outro_inquilino_nao_edita_item_de_a(sessao_a, sessao_b, itens_a):
    """RLS cruzada intacta: um token `catalogo:escrever` do inquilino B não edita item do inquilino A (a rota
    responde como se o item não existisse, igual à sessão -- RLS não distingue sessão de token)."""
    it = itens_a.criar("mapa")
    r_tok_b = sessao_b.post("/api/tokens", json={"nome": titulo_zt("tok-b-escrever"), "escopos": ["catalogo:escrever"]})
    assert r_tok_b.status_code == 201, r_tok_b.text
    tok_id = r_tok_b.json()["id"]
    try:
        r = com_token(
            novo_cliente(), r_tok_b.json()["token"], "PUT", f"/api/itens/{it['id']}", json={"titulo": "invasao"}
        )
        assert r.status_code == 404, r.text
    finally:
        sessao_b.delete(f"/api/tokens/{tok_id}")
