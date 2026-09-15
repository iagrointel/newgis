"""Item de seguimento de L0-04-a/L0-11 (achado do adversário, mesma causa raiz): as rotas de fila/roteiro/
visita/foto de `app/campo/rotas.py` (`router`, prefixo `/api/campo`) caíam no padrão `admin:inquilino` de
`autenticado()` quando `escopo_token` não era passado — embora o vocabulário já tivesse `campo:usar` (usado
por `router_pwa` desde a origem) e o perfil `campo` (quem de fato coleta em campo) nunca seja admin do
inquilino: o próprio operador de campo não conseguia emitir um token para o próprio trabalho, e ficava
preso à sessão do navegador (inviável na coleta OFFLINE que é a razão de ser do módulo). Prova: token
`campo:usar` agora basta para leitura E escrita (a escrita continua exigindo `campo.coletar`, privilégio
que perfil `campo`/`editor`/`admin` têm); visualizador (sem `campo.coletar`) lê mas não escreve; RLS entre
inquilinos continua recusando com o mesmo token.

A fila é criada com `globalids=[]` (camada de apoio SEM tabela física real): `app/campo/servico.py::
fila_criar` só toca a tabela física quando há globalid a validar (achado nesta trilha: o papel de banco da
base de teste não tem CREATE em `d_demo` — `_criar_camada_pontos`/`tests/api/test_campo.py::
test_fluxo_completo`, SEM NENHUMA relação com este item, falha com o mesmo `permission denied for schema
d_demo`; ambiente, não código). O que se prova aqui é o ESCOPO do token, não o pipeline de globalid."""

from tests.api.catalogo.conftest import DADOS_POR_TIPO, titulo_zt
from tests.api.conftest import com_token, novo_cliente


def _criar_camada_leve(sessao) -> str:
    """Item `camada_vetorial` compartilhado com o inquilino inteiro (`acesso: inquilino`): sem isso, o item
    nasce privado do admin que o criou e o perfil `campo`/`visualizador` (que não é dono) toma 404
    item_inexistente por RLS antes mesmo de chegar à fila -- o que mascararia a prova do escopo com um
    problema de VISIBILIDADE, não de token."""
    r = sessao.post("/api/itens", json={
        "tipo": "camada_vetorial", "titulo": titulo_zt("campo-leve"),
        "dados": DADOS_POR_TIPO["camada_vetorial"],
    })
    assert r.status_code == 201, r.text
    iid = r.json()["id"]
    r_comp = sessao.put(f"/api/itens/{iid}/compartilhamento", json={"acesso": "inquilino"})
    assert r_comp.status_code == 200, r_comp.text
    return iid


def test_perfil_campo_le_e_escreve_por_token_campo_usar(sessao_a, usuarios_a):
    """Antes: sem `escopo_token` explícito nas rotas, um token não-admin recebia 403 escopo_insuficiente
    (faltava `admin:inquilino`) para QUALQUER rota de `/api/campo/filas*` — inclusive leitura. Depois: um
    token `campo:usar` do perfil `campo` (nunca admin) basta para o ciclo inteiro."""
    camada_id = _criar_camada_leve(sessao_a)
    try:
        c_campo, _, _ = usuarios_a.sessao("campo")
        r_tok = c_campo.post("/api/tokens", json={"nome": titulo_zt("tok-campo"), "escopos": ["campo:usar"]})
        assert r_tok.status_code == 201, r_tok.text
        tok, tok_id = r_tok.json()["token"], r_tok.json()["id"]
        cliente = novo_cliente()
        try:
            # leitura
            r_listar = com_token(cliente, tok, "GET", "/api/campo/filas")
            assert r_listar.status_code == 200, r_listar.text

            # escrita: criar fila (sem alvo -- só prova o escopo/privilégio, não o pipeline de globalid)
            r_fila = com_token(cliente, tok, "POST", "/api/campo/filas", json={
                "titulo": "fila do perfil campo", "camada_id": camada_id,
            })
            assert r_fila.status_code == 201, r_fila.text
            fila_id = r_fila.json()["id"]

            r_ver = com_token(cliente, tok, "GET", f"/api/campo/filas/{fila_id}")
            assert r_ver.status_code == 200 and r_ver.json()["alvos"] == [], r_ver.text

            r_geojson = com_token(cliente, tok, "GET", f"/api/campo/filas/{fila_id}/alvos.geojson")
            assert r_geojson.status_code == 200, r_geojson.text

            # o mesmo token continua sem admin:inquilino
            r_neg = c_campo.post("/api/tokens", json={"nome": titulo_zt("nega"), "escopos": ["admin:inquilino"]})
            assert r_neg.status_code == 422 and r_neg.json()["erro"] == "escopo_fora_do_teto"
        finally:
            c_campo.delete(f"/api/tokens/{tok_id}")
    finally:
        sessao_a.delete(f"/api/itens/{camada_id}")


def test_visualizador_le_mas_nao_escreve_em_campo(sessao_a, usuarios_a):
    """`campo:usar` não tem teto por privilégio na emissão (qualquer perfil pode pedir o escopo) — quem trava
    a ESCRITA é `campo.coletar` dentro da própria rota. Perfil `visualizador` não tem `campo.coletar`: lê,
    mas toma 403 sem_privilegio ao tentar criar fila (o escopo cobre, o privilégio não)."""
    camada_id = _criar_camada_leve(sessao_a)
    try:
        c_vis, _, _ = usuarios_a.sessao("visualizador")
        r_tok = c_vis.post("/api/tokens", json={"nome": titulo_zt("tok-vis"), "escopos": ["campo:usar"]})
        assert r_tok.status_code == 201, r_tok.text
        tok, tok_id = r_tok.json()["token"], r_tok.json()["id"]
        cliente = novo_cliente()
        try:
            assert com_token(cliente, tok, "GET", "/api/campo/filas").status_code == 200
            r = com_token(cliente, tok, "POST", "/api/campo/filas", json={
                "titulo": "fila proibida", "camada_id": camada_id,
            })
            assert r.status_code == 403 and r.json()["erro"] == "sem_privilegio", r.text
            assert r.json()["detalhe"]["exigido"] == "campo.coletar"
        finally:
            c_vis.delete(f"/api/tokens/{tok_id}")
    finally:
        sessao_a.delete(f"/api/itens/{camada_id}")


def test_token_campo_usar_de_outro_inquilino_nao_ve_fila_de_a(sessao_a, sessao_b, usuarios_b):
    """RLS cruzada intacta com token (a mesma que `test_inquilino_b_nao_ve_fila_de_a` prova com sessão)."""
    camada_id = _criar_camada_leve(sessao_a)
    try:
        r_fila = sessao_a.post("/api/campo/filas", json={"titulo": "fila RLS de A", "camada_id": camada_id})
        assert r_fila.status_code == 201, r_fila.text
        fila_id = r_fila.json()["id"]

        c_campo_b, _, _ = usuarios_b.sessao("campo")
        r_tok_b = c_campo_b.post("/api/tokens", json={"nome": titulo_zt("tok-b"), "escopos": ["campo:usar"]})
        assert r_tok_b.status_code == 201, r_tok_b.text
        tok_b_id = r_tok_b.json()["id"]
        try:
            r = com_token(novo_cliente(), r_tok_b.json()["token"], "GET", f"/api/campo/filas/{fila_id}")
            assert r.status_code == 404, r.text
        finally:
            c_campo_b.delete(f"/api/tokens/{tok_b_id}")
    finally:
        sessao_a.delete(f"/api/itens/{camada_id}")
