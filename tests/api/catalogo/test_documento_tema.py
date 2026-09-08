"""`corpo.tema` em documento de construtor (item L5-10-temas-marca): app e painel ganham a chave OPCIONAL
`tema` no esquema v3 — referência ({"id"} de padrão ou "inquilino") ou definição ({"definicao"} com tokens
validados por formato). A recusa de formato é 422 `tema_invalido` (validador da casa, DEPOIS do JSON Schema);
as formas que nem id nem definicao são, ou os dois juntos, caem no próprio `oneOf` do esquema (422
`dados_invalidos`). Documento gravado em v2 é lido como v3 pela cadeia de migração SEM gravar de volta."""

import json

import pytest

from tests.api.test_rls import contexto, ids_por_slug

# serial: nada aqui muda o inquilino; os casos são criação de item zt* — segue o padrão do catálogo
pytestmark = pytest.mark.serial


def _tema_valido() -> dict:
    """Mesma forma de tests/api/test_org_tema.py (tema mínimo completo, sem aviso de contraste)."""
    return {
        "claro": {
            "cores": {
                "fundo": "#eef1f0", "superficie": "#ffffff", "texto": "#12181a",
                "texto_suave": "#4d5b57", "acento": "#8f4f10", "texto_sobre_acento": "#fff6ec",
                "borda": "#ccd4d1", "sucesso": "#2f7a4c", "erro": "#a83c2e",
            },
            "espacamento": {"grande": "33px"},
        },
    }


def _criar_app(sessao_a, itens_a, corpo_extra: dict):
    corpo = {"nos": [], "ligacoes": []}
    corpo.update(corpo_extra)
    return itens_a.criar("app", dados={"tipo": "app", "esquema_versao": 3, "corpo": corpo})


def test_documento_aceita_tema_por_id_e_por_definicao(sessao_a, itens_a):
    it = _criar_app(sessao_a, itens_a, {"tema": {"id": "prado"}})
    lido = sessao_a.get(f"/api/itens/{it['id']}").json()
    assert lido["dados"]["corpo"]["tema"] == {"id": "prado"}
    definicao = _tema_valido()
    r = sessao_a.put(
        f"/api/itens/{it['id']}",
        json={"dados": {"tipo": "app", "esquema_versao": 3,
                        "corpo": {"nos": [], "ligacoes": [], "tema": {"definicao": definicao}}}},
    )
    assert r.status_code == 200, r.text
    lido = sessao_a.get(f"/api/itens/{it['id']}").json()
    assert lido["dados"]["corpo"]["tema"] == {"definicao": definicao}
    assert lido["versao_atual"] == 2


def test_documento_recusa_tema_invalido(sessao_a, itens_a):
    # recusados pelo validador da casa (422 tema_invalido, DEPOIS do JSON Schema):
    for tema, erro in (
        ({"id": "fantasma"}, "tema_invalido"),  # id que não é padrão nem "inquilino"
        ({"definicao": {"claro": {"cores": {"fundo": "url(javascript:alert(1))"}}}}, "tema_invalido"),
        ({"definicao": {}}, "tema_invalido"),  # nem claro nem escuro
        # recusados antes, pelo JSON Schema do tipo (422 dados_invalidos):
        ({}, "dados_invalidos"),  # sem id nem definicao
        ({"id": "prado", "definicao": {}}, "dados_invalidos"),  # os dois juntos (oneOf)
    ):
        r = sessao_a.post(
            "/api/itens",
            json={"tipo": "app", "titulo": "zt tema ruim",
                  "dados": {"tipo": "app", "esquema_versao": 3,
                            "corpo": {"nos": [], "ligacoes": [], "tema": tema}}},
        )
        assert r.status_code == 422 and r.json()["erro"] == erro, (tema, r.text)


def test_documento_painel_tambem_aceita_tema(sessao_a, itens_a):
    corpo = {"nos": [], "ligacoes": [], "tema": {"id": "inquilino"}}
    it = itens_a.criar("painel", dados={"tipo": "painel", "esquema_versao": 3, "corpo": corpo})
    lido = sessao_a.get(f"/api/itens/{it['id']}").json()
    assert lido["dados"]["corpo"]["tema"] == {"id": "inquilino"}


def test_documento_antigo_v2_e_lido_como_v3_sem_regravar(sessao_a, itens_a, conexao_plat_app):
    """A migração de LEITURA (documento._MIGRACOES) sobe v2→v3 sem tocar o banco; o corpo sem tema continua
    sem tema (documento sem tema renderiza com o padrão)."""
    it = itens_a.criar("app", dados={"tipo": "app", "esquema_versao": 2, "corpo": {"nos": [], "ligacoes": []}})
    iid = it["id"]
    # simula dado legado direto no banco, fora da API
    ids = ids_por_slug(conexao_plat_app)
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT usuario_id FROM plat.auth_login('demo', 'admin')")
        adm = cur.fetchone()["usuario_id"]
    contexto(conexao_plat_app, ids["demo"], usuario_id=adm, login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "UPDATE plat.item SET dados = %s::jsonb WHERE id = %s::uuid",
            (json.dumps({"tipo": "app", "esquema_versao": 2, "corpo": {"nos": [], "ligacoes": []}}), iid),
        )
    conexao_plat_app.commit()

    r = sessao_a.get(f"/api/itens/{iid}")
    assert r.status_code == 200
    dados = r.json()["dados"]
    assert dados["esquema_versao"] == 3
    assert "tema" not in dados["corpo"]

    contexto(conexao_plat_app, ids["demo"], usuario_id=adm, login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT dados FROM plat.item WHERE id = %s::uuid", (iid,))
        assert cur.fetchone()["dados"]["esquema_versao"] == 2  # nunca gravou de volta
