"""Notificações internas do item L0-03-k no eixo INQUILINO.

`tests/api/catalogo/test_notificacoes.py` já prova o eixo USUÁRIO (a notificação de outro usuário do
MESMO inquilino é invisível e inalcançável por id, cláusula literal do portão "RLS por usuario_id").
Falta o eixo que a política `p_notificacao_propria` também carrega e que nenhum teste exercia: o
predicado `tenant_id = plat.tenant_atual()`. Aqui: criar, listar, marcar lida, e a notificação do
inquilino A invisível e inalcançável para o inquilino B — sempre com o PAR POSITIVO na mesma rodada
(o dono legítimo vê, marca e apaga a mesma linha), senão um código que recusasse tudo passaria igual.

Criação pela função `plat.notificar` (a mesma que as rotas e o worker chamam), porque não existe rota
pública de criação de notificação — é sempre efeito de outra ação.
"""

import uuid

import pytest

from tests.api.test_rls import contexto, ids_por_slug

ITEM = "L0-03-k-favoritos-notificacoes"


def _notificar(con, tenant_id, usuario_id, chave, titulo="zt notificacao de inquilino"):
    """Escreve uma notificação pela função da casa e devolve o id (commit: a API lê noutra conexão)."""
    contexto(con, tenant_id, usuario_id, "admin")
    try:
        with con.cursor() as cur:
            cur.execute(
                "SELECT plat.notificar(%s, %s, 'grupos/convite', %s, %s, NULL, NULL, NULL, NULL, 60) AS id",
                (tenant_id, usuario_id, titulo, chave),
            )
            novo = cur.fetchone()["id"]
        con.commit()
    except Exception:
        con.rollback()
        raise
    assert novo is not None, "plat.notificar devolveu NULL (chave repetida ou teto por minuto)"
    return str(novo)


def _ids_listados(sessao):
    return [n["id"] for n in sessao.get("/api/notificacoes?limite=100").json()["itens"]]


@pytest.fixture
def par_de_inquilinos(sessao_a, sessao_b, conexao_plat_app):
    """Uma notificação para o admin de A e outra para o admin de B, apagadas no fim pelos donos."""
    ids = ids_por_slug(conexao_plat_app)
    admin_a = sessao_a.get("/api/eu").json()["id"]
    admin_b = sessao_b.get("/api/eu").json()["id"]
    marca = uuid.uuid4().hex
    n_a = _notificar(conexao_plat_app, ids["demo"], admin_a, f"zt/a/{marca}")
    n_b = _notificar(conexao_plat_app, ids["demo2"], admin_b, f"zt/b/{marca}")
    yield {"a": n_a, "b": n_b, "tenant_a": ids["demo"], "tenant_b": ids["demo2"],
           "admin_a": admin_a, "admin_b": admin_b, "marca": marca}
    sessao_a.delete(f"/api/notificacoes/{n_a}")
    sessao_b.delete(f"/api/notificacoes/{n_b}")


def test_o_dono_ve_lista_e_marca_lida_a_propria_notificacao(sessao_a, par_de_inquilinos):
    """PAR POSITIVO das recusas abaixo: o inquilino legítimo enxerga, conta e marca lida a MESMA linha."""
    n_a = par_de_inquilinos["a"]
    assert n_a in _ids_listados(sessao_a)
    antes = sessao_a.get("/api/notificacoes/contagem").json()["nao_lidas"]
    assert antes >= 1
    r = sessao_a.post("/api/notificacoes/lidas", json={"ids": [n_a]})
    assert r.status_code == 200, r.text
    assert r.json()["marcadas"] == 1
    assert r.json()["nao_lidas"] == antes - 1
    lida = [n for n in sessao_a.get("/api/notificacoes?limite=100").json()["itens"] if n["id"] == n_a][0]
    assert lida["lida_em"] is not None


def test_notificacao_de_a_nao_aparece_na_lista_de_b_e_vice_versa(sessao_a, sessao_b, par_de_inquilinos):
    de_a, de_b = par_de_inquilinos["a"], par_de_inquilinos["b"]
    lista_a, lista_b = _ids_listados(sessao_a), _ids_listados(sessao_b)
    assert de_a in lista_a and de_a not in lista_b, "B enxergou notificação do inquilino A"
    assert de_b in lista_b and de_b not in lista_a, "A enxergou notificação do inquilino B"


def test_b_nao_marca_lida_nem_apaga_a_notificacao_de_a(sessao_a, sessao_b, par_de_inquilinos):
    de_a = par_de_inquilinos["a"]
    assert sessao_b.post("/api/notificacoes/lidas", json={"ids": [de_a]}).status_code == 404
    assert sessao_b.delete(f"/api/notificacoes/{de_a}").status_code == 404
    # o par positivo, na mesma rodada: a linha continua lá, não lida, e o dono a apaga
    minha = [n for n in sessao_a.get("/api/notificacoes?limite=100").json()["itens"] if n["id"] == de_a]
    assert minha and minha[0]["lida_em"] is None, "a tentativa de B mexeu na linha de A"
    assert sessao_a.delete(f"/api/notificacoes/{de_a}").status_code == 204
    assert de_a not in _ids_listados(sessao_a)


def test_marcar_todas_de_b_nao_toca_no_que_e_de_a(sessao_a, sessao_b, par_de_inquilinos):
    """`todas: true` não tem id no corpo: se o UPDATE não filtrasse por inquilino, varreria a casa inteira."""
    de_a = par_de_inquilinos["a"]
    assert sessao_b.post("/api/notificacoes/lidas", json={"todas": True}).status_code == 200
    minha = [n for n in sessao_a.get("/api/notificacoes?limite=100").json()["itens"] if n["id"] == de_a][0]
    assert minha["lida_em"] is None, "o 'marcar todas' de B marcou a notificação de A"
    # par positivo: o mesmo 'todas' zera o sino de quem o chamou
    assert sessao_b.get("/api/notificacoes/contagem").json()["nao_lidas"] == 0


def test_notificar_usuario_de_outro_inquilino_e_recusado_na_origem(sessao_a, sessao_b, conexao_plat_app):
    """A guarda da própria função (`notificacao_usuario_fora_do_inquilino`): não dá para escrever no sino
    de alguém de outro inquilino nem passando o par (tenant de A, usuário de B)."""
    import psycopg2

    ids = ids_por_slug(conexao_plat_app)
    admin_b = sessao_b.get("/api/eu").json()["id"]
    contexto(conexao_plat_app, ids["demo"], sessao_a.get("/api/eu").json()["id"], "admin")
    with pytest.raises(psycopg2.errors.RaiseException) as e:
        with conexao_plat_app.cursor() as cur:
            cur.execute(
                "SELECT plat.notificar(%s, %s, 'grupos/convite', 'zt cruzada', %s, NULL, NULL, NULL, NULL, 60)",
                (ids["demo"], admin_b, f"zt/x/{uuid.uuid4().hex}"),
            )
    conexao_plat_app.rollback()
    assert "notificacao_usuario_fora_do_inquilino" in str(e.value)


def test_medida_isolamento_por_inquilino(sessao_a, sessao_b, par_de_inquilinos, medida):
    """A medida do item neste eixo: quantas portas da notificação foram experimentadas de fora do inquilino
    e quantas recusaram — com o par positivo contado do lado do dono, na mesma rodada."""
    de_a = par_de_inquilinos["a"]
    tentativas = {
        "listar": de_a not in _ids_listados(sessao_b),
        "marcar_lida": sessao_b.post("/api/notificacoes/lidas", json={"ids": [de_a]}).status_code == 404,
        "apagar": sessao_b.delete(f"/api/notificacoes/{de_a}").status_code == 404,
        "marcar_todas": sessao_b.post("/api/notificacoes/lidas", json={"todas": True}).status_code == 200,
    }
    dono_ve = de_a in _ids_listados(sessao_a)
    assert all(tentativas.values()) and dono_ve, (tentativas, dono_ve)
    medida(ITEM)(
        "portas_fechadas_para_outro_inquilino",
        {"portas": len(tentativas), "recusadas": sum(1 for v in tentativas.values() if v),
         "dono_continua_vendo": dono_ve},
        "rotas de /api/notificacoes experimentadas por um inquilino que não é o dono",
        "pytest tests/api/test_notificacoes.py -q",
    )
