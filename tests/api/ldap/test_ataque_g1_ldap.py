"""Ataque adversarial ao item L0-08-d-ldap (turno 3). Usa o diretório de teste do próprio item
(tests/ldap_fixture, glauth em contêiner), por isso vive neste diretório: as fixtures `servidor_ldap` e
`provedor_ldap_demo` são de tests/api/ldap/conftest.py. Nada é consertado aqui."""

import time

import pytest

from tests.api.conftest import novo_cliente

pytestmark = pytest.mark.lento


def test_injecao_de_filtro_senha_vazia_e_curinga(servidor_ldap, provedor_ldap_demo):
    """Refutação literal: injeção de filtro ('*)(uid=*'), bind anônimo. As duas aguentaram."""
    for tentativa in ("*", "*)(uid=*", "ana.silva)(|(uid=*", "\\2a"):  # "ana.silva*" é o achado G1-l3
        r = novo_cliente().post(
            "/api/login/ldap", json={"inquilino": "demo", "login": tentativa, "senha": "Teste-ldap-1"}
        )
        assert r.status_code in (401, 422, 423), (tentativa, r.status_code, r.text[:200])
    r = novo_cliente().post("/api/login/ldap", json={"inquilino": "demo", "login": "ana.silva", "senha": ""})
    assert r.status_code in (401, 422), r.text


def test_mede_binds_por_minuto_contra_logins_diferentes(servidor_ldap, provedor_ldap_demo):
    """Refutação literal: '1.000 binds/min'. O contador de força bruta é por (inquilino, login); contra logins
    DIFERENTES ele nunca dispara. Aqui só se MEDE a vazão — o veredito está no laudo."""
    cliente = novo_cliente()
    ini = time.perf_counter()
    n = 0
    for i in range(60):
        r = cliente.post(
            "/api/login/ldap", json={"inquilino": "demo", "login": f"inexistente{i}", "senha": "SenhaErrada-1"}
        )
        assert r.status_code in (401, 423, 503), r.status_code
        n += 1
    dt = time.perf_counter() - ini
    assert n / dt > 0
    print(f"\nbinds/s medidos contra logins diferentes: {n / dt:.1f} ({int(60 * n / dt)}/min)")


@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G1-l3 (o mais grave do grupo): plat.ldap_provisionar é chamado com o LOGIN CRU digitado pelo "
    "cliente, não com o atributo canônico da entrada encontrada no diretório (o cn/dn já está em `achado`). No "
    "diretório de teste do próprio item (glauth), 'ana.silva*' encontra a entrada de ana.silva, o bind com a "
    "senha dela funciona e nasce um usuário LOCAL de login 'ana.silva*' amarrado ao DN de ana.silva. A partir "
    "daí o login CANÔNICO 'ana.silva' recebe 409 conflito/ux_usuario_sujeito_externo, para sempre: uma "
    "requisição não autenticada tira do ar a conta legítima e ainda devolve o nome da restrição do banco numa "
    "rota pública.",
)
def test_l3_login_cru_nao_vira_identidade_local(servidor_ldap, provedor_ldap_demo, conexao_plat_app):
    from tests.api.test_rls import contexto, ids_por_slug

    con = conexao_plat_app
    con.rollback()
    contexto(con, ids_por_slug(con)["demo"])
    with con.cursor() as cur:
        cur.execute("DELETE FROM plat.usuario WHERE origem = 'ldap' AND login LIKE 'ana.silva%'")
    con.commit()
    try:
        r = novo_cliente().post(
            "/api/login/ldap", json={"inquilino": "demo", "login": "ana.silva*", "senha": "Teste-ldap-1"}
        )
        if r.status_code == 200:
            assert r.json()["usuario"]["login"] == "ana.silva", (
                "o usuário local nasceu com o texto cru do cliente, não com o atributo do diretório: "
                f"{r.json()['usuario']['login']!r}"
            )
        canonico = novo_cliente().post(
            "/api/login/ldap", json={"inquilino": "demo", "login": "ana.silva", "senha": "Teste-ldap-1"}
        )
        assert canonico.status_code == 200, (
            f"o login canônico ficou trancado: {canonico.status_code} {canonico.text[:200]}"
        )
    finally:
        con.rollback()
        contexto(con, ids_por_slug(con)["demo"])
        with con.cursor() as cur:
            cur.execute("DELETE FROM plat.usuario WHERE origem = 'ldap' AND login LIKE 'ana.silva%'")
        con.commit()


@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G1-l1: o limite por IP do nginx (10 r/min) está só em `location = /api/login` e "
    "`location = /api/login/2fa`, casamento EXATO; /api/login/ldap cai no `location /` e não tem limite na "
    "borda. O único freio é o contador EM MEMÓRIA de app/auth/ldap.py, por (inquilino, login) e por PROCESSO "
    "(a unidade sobe --workers 2). Medido nesta máquina: 172 binds/s contra logins diferentes, sem nenhum "
    "bloqueio — a refutação do item fala em 1.000 binds/min.",
)
def test_l1_login_ldap_tem_limite_por_ip_na_borda():
    from pathlib import Path

    conf = Path("/etc/nginx/sites-enabled/plat.iagrointel.com")
    if not conf.exists():
        pytest.skip("nginx do ambiente não disponível")
    texto = conf.read_text(encoding="utf-8", errors="replace")
    assert "location = /api/login/ldap" in texto or "location ~ ^/api/login" in texto


@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G1-l2: a hipótese do item cita StartTLS/LDAPS, mas o diretório de teste (glauth) sobe com "
    "[ldaps] enabled = false e sem certificado, e tests/api/ldap/conftest.py fixa start_tls: False. Nenhum "
    "teste exercita o caminho TLS: o portão foi fechado só sobre LDAP em claro.",
)
def test_l2_o_caminho_tls_do_ldap_e_exercitado():
    from pathlib import Path

    conf = (Path(__file__).resolve().parent / "conftest.py").read_text(encoding="utf-8")
    assert '"start_tls": True' in conf or "start_tls=True" in conf


@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G1-l4: o diretório de teste trata a fuga RFC 4515 como curinga — a busca (cn=ana.silva\\2a) "
    "devolve a entrada de ana.silva, igual a (cn=ana.silva*). Ou seja, o escape do login (a defesa que o item "
    "declara contra injeção de filtro) NUNCA é exercitado: o que barra '*)(uid=*' é a regra 'exatamente 1 "
    "resultado', não o escape. A prova de resistência a injeção do item é nula neste servidor.",
)
def test_l4_o_escape_do_filtro_e_de_fato_exercitado(servidor_ldap, provedor_ldap_demo):
    import ldap3

    from tests.api.ldap.conftest import BASE_DN, BIND_DN, BIND_SENHA, HOST, PORTA

    s = ldap3.Server(HOST, port=PORTA, get_info=ldap3.NONE)
    c = ldap3.Connection(s, user=BIND_DN, password=BIND_SENHA, auto_bind=True)
    try:
        c.search(BASE_DN, "(cn=ana.silva\\2a)", attributes=["cn"])
        assert list(c.entries) == [], "o diretório de teste casa a fuga \\2a como curinga"
    finally:
        c.unbind()
