"""Redação de segredos em rota e linhas de log (ADR 0002 seções 5.2 e 9.1)."""

from app.auth.redigir import REDIGIDO, linha_redigida, query_redigida, rota_redigida


def test_parametros_secretos_da_query_sao_redigidos():
    q = query_redigida("token=plat_abc&pagina=2&senha=x&codigo=123456&desafio=deadbeef&Token=z")
    assert "plat_abc" not in q and "123456" not in q and "deadbeef" not in q
    assert q.count(REDIGIDO.replace("<", "%3C").replace(">", "%3E")) == 5
    assert "pagina=2" in q


def test_rota_redigida_corta_em_500():
    r = rota_redigida("/api/eu", "token=" + "a" * 700)
    assert len(r) <= 500 and "aaaa" not in r
    assert rota_redigida("/api/eu", "") == "/api/eu"


def test_linha_redige_cookie_authorization_e_token():
    linha = (
        "GET /api/eu Cookie: plat_sessao="
        + "0" * 64
        + "; Authorization: Bearer plat_"
        + "b" * 43
        + " token=plat_"
        + "c" * 43
    )
    r = linha_redigida(linha)
    assert "0" * 64 not in r and "b" * 43 not in r and "c" * 43 not in r
    assert r.count(REDIGIDO) >= 2  # o valor do cabeçalho vai até o fim da linha, levando o token junto
