"""Ataque adversarial ao grupo G1 (identidade, sessão, segundo fator, senha, token de serviço, LDAP).

Escrito pelo ADVERSÁRIO INDEPENDENTE do turno 3, contra os itens L0-02-a/b/c/d/e/f/g e L0-08-d.
Regra do papel: aqui NÃO se conserta nada. Cada achado vira um teste com `xfail(strict=True)` que afirma
o comportamento CORRETO — enquanto o defeito existir o teste dá xfail (suíte verde); no dia em que alguém
consertar, o teste passa, o `strict` transforma o XPASS em FALHA e obriga a remover a marca. É a prova
de conserto.

Testes sem marca são MEDIÇÕES ou confirmações do que aguentou o ataque.
"""

import secrets
import subprocess
import time
from pathlib import Path

import pytest

from app.auth import totp
from tests.api.conftest import PREFIXO_TESTE, arquivo_openapi, entrar, novo_cliente

RAIZ = Path(__file__).resolve().parents[2]


def _rotas_vivas() -> set[tuple[str, str]]:
    from app.main import app

    spec = app.openapi()
    return {(m.upper(), c) for c, ms in spec["paths"].items() for m in ms}


def _rotas_do_arquivo() -> set[tuple[str, str]]:
    spec = arquivo_openapi()
    return {(m.upper(), c) for c, ms in spec["paths"].items() for m in ms}


def _config_do_demo(con, patch_sql: str) -> None:
    """Escreve em plat.tenant como plat_app: sem o contexto de RLS o UPDATE casa 0 linhas em silêncio."""
    from tests.api.test_rls import contexto, ids_por_slug

    con.rollback()
    ids = ids_por_slug(con)
    contexto(con, ids["demo"])
    with con.cursor() as cur:
        cur.execute(patch_sql)
        assert cur.rowcount == 1, f"UPDATE casou {cur.rowcount} linhas (contexto de RLS errado)"
    con.commit()


# ====================================================================== suposições transversais

@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G1-T1: docs/openapi.json é um retrato PARADO; o app vivo tem 196 rotas e o arquivo 168. "
    "Toda a cobertura do L0-02-e (test_cruzado, test_privilegios_declarados, test_eventos) é medida contra o "
    "arquivo, e `make check` não roda `make openapi` nem compara os dois. 28 rotas vivas nunca foram varridas.",
)
def test_t1_openapi_do_arquivo_reflete_o_app_vivo():
    vivas, arquivo = _rotas_vivas(), _rotas_do_arquivo()
    assert sorted(vivas - arquivo) == [], "rotas vivas fora de docs/openapi.json"
    assert sorted(arquivo - vivas) == [], "rotas em docs/openapi.json que já não existem"


@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G1-T2: as migrações 046/047 dão GRANT EXECUTE ao plat_app sem o REVOKE ... FROM PUBLIC que "
    "as migrações 003/006/024 usam; 6 funções SECURITY DEFINER do schema plat ficaram executáveis por PUBLIC "
    "(convite_aceitar, convite_resolver, redefinicao_solicitar, redefinicao_resolver, redefinicao_contexto, "
    "uploads_expirar_candidatos). Cláusula literal do portão do L0-02-e.",
)
def test_t2_nenhuma_security_definer_executavel_por_public(conexao_plat_app):
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            """SELECT p.proname FROM pg_proc p
               WHERE p.pronamespace = 'plat'::regnamespace AND p.prosecdef
                 AND (p.proacl IS NULL OR EXISTS (SELECT 1 FROM aclexplode(p.proacl) a WHERE a.grantee = 0))
               ORDER BY 1"""
        )
        assert [r["proname"] for r in cur.fetchall()] == []


@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G1-T3: o commit master 90ab545 não importa. app/main.py referencia app/auth/rotas_convites.py, "
    "rotas_redefinicao.py, modelos_convite.py, modelos_redefinicao.py, app/correio/, app/uploads/ e "
    "app/migracoes.py, que nunca foram comitados. Um checkout limpo do repositório não sobe a API, logo nenhum "
    "portão deste grupo é reproduzível a partir do repositório.",
)
def test_t3_todo_modulo_importado_esta_versionado():
    versionados = set(
        subprocess.run(
            ["git", "ls-files"], cwd=RAIZ, capture_output=True, text=True, check=True
        ).stdout.splitlines()
    )
    import app.main

    faltando = []
    for nome, modulo in list(vars(__import__("sys")).get("modules", {}).items()):
        arquivo = getattr(modulo, "__file__", None) or ""
        if not nome.startswith("app.") and nome != "app":
            continue
        if not arquivo.startswith(str(RAIZ)):
            continue
        rel = str(Path(arquivo).relative_to(RAIZ))
        if rel not in versionados:
            faltando.append(rel)
    assert app.main is not None
    assert sorted(faltando) == [], "módulos importados pela aplicação que não estão no git"


# ====================================================================== L0-02-a login e sessão

def test_a_medidas_de_login_e_sessao(medida, cred):
    """Medição do adversário (não é refutação): custo de login e das defesas que aguentaram."""
    import statistics

    tempos = []
    for _ in range(20):
        c = novo_cliente()
        ini = time.perf_counter()
        r = c.post("/api/login", json={"inquilino": "demo", "login": cred["demo"][0], "senha": cred["demo"][1]})
        tempos.append((time.perf_counter() - ini) * 1000)
        assert r.status_code == 200
    mediana = statistics.median(tempos)
    medida("L0-02-a")("adversario_latencia_login_ms", round(mediana, 1), "ms",
                      "mediana de 20 POST /api/login com senha certa pelo TestClient (pbkdf2 600k incluído)")
    assert mediana < 400, mediana


def test_a_cookie_apos_logout_alterado_e_de_outro_inquilino(cred, usuarios_a):
    c, u, senha = usuarios_a.sessao()
    cookie = c.cookies.get("plat_sessao")
    assert c.post("/api/logout").status_code == 204
    reuso = novo_cliente()
    reuso.cookies.set("plat_sessao", cookie)
    assert reuso.get("/api/eu").status_code == 401  # reuso após logout
    c2 = novo_cliente()
    assert entrar(c2, "demo", u["login"], senha).status_code == 200
    bom = c2.cookies.get("plat_sessao")
    alterado = ("a" if bom[0] != "a" else "b") + bom[1:]
    c3 = novo_cliente()
    c3.cookies.set("plat_sessao", alterado)
    assert c3.get("/api/eu").status_code == 401  # 1 caractere trocado
    assert c2.get("/api/usuarios", headers={"X-Plat-Inquilino": "demo2"}).status_code == 403  # cookie de A em B


@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G1-a1: plat.sessoes_expurgar() apaga por `ultimo_uso < now() - interval '24 hours'` FIXO, "
    "enquanto a sessão passa a devolver 401 pela política do inquilino (12 h por padrão, 1 h no mínimo "
    "configurável). Medido: sessão com ultimo_uso de 13 h devolve 401 e o periódico devolve 0 e a linha "
    "continua na tabela; só some com 25 h. A cláusula do portão é 'devolve 401 E a linha é apagada pelo "
    "periódico'.",
)
def test_a1_sessao_ociosa_alem_da_politica_some_no_periodico(usuarios_a, conexao_plat_app):
    import hashlib

    c, _u, _s = usuarios_a.sessao()
    h = hashlib.sha256(c.cookies.get("plat_sessao").encode()).hexdigest()
    with conexao_plat_app.cursor() as cur:
        cur.execute("SET LOCAL ROLE NONE")
    con = conexao_plat_app
    con.rollback()
    with con.cursor() as cur:
        cur.execute("UPDATE plat.sessao SET ultimo_uso = now() - interval '13 hours' WHERE token_hash = %s", (h,))
    con.commit()
    assert c.get("/api/eu").status_code == 401
    with con.cursor() as cur:
        cur.execute("SELECT plat.sessoes_expurgar() AS n")
        cur.fetchone()
        cur.execute("SELECT count(*) AS n FROM plat.sessao WHERE token_hash = %s", (h,))
        restantes = cur.fetchone()["n"]
    con.rollback()
    assert restantes == 0, "a sessão ociosa continua na tabela depois do periódico"


# ====================================================================== L0-02-b política de senha e bloqueio

@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G1-b1: a hipótese do item diz 'mínimo 10 caracteres com pelo menos uma letra e um número' "
    "(regra herdada do SIG de teste interno). O produto entrega mínimo 8: limites.AUTH_PADROES['senha_min'] = "
    "(8, 8, 64) e Politica.senha_min = 8. Medido: PUT /api/eu/senha com 'Abcdefg1' (8 caracteres) devolve 204.",
)
def test_b1_senha_de_oito_caracteres_e_recusada(usuarios_a):
    c, _u, senha = usuarios_a.sessao()
    r = c.put("/api/eu/senha", json={"atual": senha, "nova": "Abcdefg1"})
    assert r.status_code == 422, f"senha de 8 caracteres aceita: {r.status_code}"


@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G1-b2: a expiração de senha (config.auth.senha_expira_dias) só é avaliada no caminho de senha; "
    "app/auth/rotas_login.py::login_2fa chama _abrir_sessao(..., senha_alterada_em=None), logo quem tem segundo "
    "fator ligado NUNCA recebe a pendência trocar_senha. Medido com senha_expira_dias=30 e senha de 60 dias: "
    "usuário sem 2FA -> pendencias ['trocar_senha']; usuário com 2FA -> pendencias []. A conta mais forte fica "
    "com a política mais fraca.",
)
def test_b2_expiracao_de_senha_vale_tambem_para_quem_tem_2fa(usuarios_a, conexao_plat_app, cred):
    from tests.api.conftest import ligar_2fa

    c, u, senha = usuarios_a.sessao()
    segredo, _ = ligar_2fa(c)
    con = conexao_plat_app
    _config_do_demo(con, "UPDATE plat.tenant SET config = coalesce(config, '{}'::jsonb) || "
                         "'{\"auth\":{\"senha_expira_dias\":30}}'::jsonb WHERE slug = 'demo'")
    from tests.api.test_rls import contexto, ids_por_slug

    con.rollback()
    contexto(con, ids_por_slug(con)["demo"])
    with con.cursor() as cur:
        cur.execute("UPDATE plat.usuario SET senha_alterada_em = now() - interval '60 days' WHERE id = %s", (u["id"],))
        assert cur.rowcount == 1
    con.commit()
    try:
        novo = novo_cliente()
        r = entrar(novo, "demo", u["login"], senha, segredo)
        assert r.status_code == 200, r.text
        assert "trocar_senha" in r.json()["usuario"]["pendencias"], r.json()["usuario"]["pendencias"]
    finally:
        _config_do_demo(con, "UPDATE plat.tenant SET config = config - 'auth' WHERE slug = 'demo'")


def test_b_bloqueio_por_usuario_nao_nega_o_inquilino(cred):
    """Refutação literal do item: 1.000 senhas em 3 min contra um usuário e contra vários logins do MESMO
    inquilino não podem derrubar o inquilino. Aqui a medição é do CUSTO e da vazão; o veredito é NÃO REFUTADO."""
    anon = novo_cliente()
    ini = time.perf_counter()
    tentativas = 0
    for _ in range(30):
        login = "zz" + secrets.token_hex(4)
        for j in range(3):  # 3 < 5: nunca chega ao bloqueio, logo o ataque nunca se auto-limita
            r = anon.post("/api/login", json={"inquilino": "demo", "login": login, "senha": f"Errada-{j}-abc"})
            assert r.status_code == 401
            tentativas += 1
    dt = time.perf_counter() - ini
    c = novo_cliente()
    assert c.post(
        "/api/login", json={"inquilino": "demo", "login": cred["demo"][0], "senha": cred["demo"][1]}
    ).status_code == 200, "o admin do inquilino deixou de entrar durante o ataque"
    assert tentativas / dt > 0  # a medida é o que importa; ver o laudo


# ====================================================================== L0-02-c segundo fator

@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G1-c1: com config.auth.exigir_2fa ligado, a pendência 'configurar_2fa' fecha as rotas que "
    "passam por app.auth.sessao.autenticado(), mas as 7 rotas /rest/services/Geocodificador/GeocodeServer/* "
    "autenticam por app/geocodificador/rotas_esri.py::_autenticar, que chama resolver() direto e nunca olha "
    "pendências (nem CSRF sob cookie, nem X-Plat-Inquilino). Medido: /api/usuarios -> 403 pendencia e "
    "/rest/services/Geocodificador/GeocodeServer/suggest?text=rua -> 200 para o MESMO usuário sem 2FA. "
    "Cláusula do portão: 'usuário sem 2FA cai na tela de configuração antes de qualquer rota'.",
)
def test_c1_pendencia_de_2fa_fecha_tambem_o_geocodeserver(sessao_plat):
    slug = f"{PREFIXO_TESTE}-inq-{secrets.token_hex(3)}"
    r = sessao_plat.post(
        "/api/plataforma/inquilinos",
        json={"slug": slug, "nome": f"Inquilino de teste {slug}", "admin_login": "admin",
              "admin_nome": "Administrador de teste", "config": {"auth": {"exigir_2fa": True}}},
    )
    assert r.status_code == 201, r.text
    tid, temporaria = r.json()["id"], r.json()["senha_temporaria"]
    try:
        c = novo_cliente()
        assert entrar(c, slug, "admin", temporaria).status_code == 200
        nova = "Senha-adversario-1" + secrets.token_hex(3)
        assert c.put("/api/eu/senha", json={"atual": temporaria, "nova": nova}).status_code == 204
        assert c.get("/api/eu").json()["pendencias"] == ["configurar_2fa"]
        assert c.get("/api/usuarios").status_code == 403  # a rota normal fecha, como o portão manda
        for rota in ("/rest/services/Geocodificador/GeocodeServer/suggest?text=rua",
                     "/rest/services/Geocodificador/GeocodeServer/findAddressCandidates?SingleLine=rua"):
            assert c.get(rota).status_code == 403, f"{rota} respondeu com pendência de 2FA aberta"
    finally:
        sessao_plat.delete(f"/api/plataforma/inquilinos/{tid}")


def test_c_forca_bruta_replay_e_relogio(usuarios_a, sessao_a):
    """O que aguentou: 5 códigos errados bloqueiam (423), código de passo futuro (+5 min) é recusado."""
    from tests.api.conftest import ligar_2fa

    c, u, senha = usuarios_a.sessao()
    segredo, _ = ligar_2fa(c)
    r = novo_cliente().post("/api/login", json={"inquilino": "demo", "login": u["login"], "senha": senha})
    desafio = r.json()["desafio"]
    codigos = []
    for i in range(6):
        rr = novo_cliente().post("/api/login/2fa", json={"desafio": desafio, "codigo": "%06d" % i})
        codigos.append(rr.status_code)
        if rr.status_code == 423:
            break
    assert codigos[:5] == [401] * 5 and codigos[5] == 423, codigos
    assert sessao_a.post(f"/api/usuarios/{u['id']}/desbloquear").status_code == 204
    r = novo_cliente().post("/api/login", json={"inquilino": "demo", "login": u["login"], "senha": senha})
    futuro = totp.codigo(segredo, passo=totp.passo_atual() + 10)
    assert novo_cliente().post(
        "/api/login/2fa", json={"desafio": r.json()["desafio"], "codigo": futuro}
    ).status_code == 401
    sessao_a.post(f"/api/usuarios/{u['id']}/desbloquear")


# ====================================================================== L0-02-d token de serviço

@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G1-d1: o portão pede 'prefixo de 8 caracteres na lista'; app/auth/rotas_tokens.py::_inserir "
    "grava prefixo = valor[:12], ou seja 'plat_' + 7 caracteres do próprio segredo. Medido: len(prefixo) = 12.",
)
def test_d1_prefixo_do_token_tem_oito_caracteres(sessao_a):
    r = sessao_a.post("/api/tokens", json={"nome": f"{PREFIXO_TESTE}-adv-prefixo", "escopos": ["catalogo:ler"]})
    assert r.status_code == 201, r.text
    try:
        assert len(r.json()["prefixo"]) == 8, r.json()["prefixo"]
    finally:
        sessao_a.delete(f"/api/tokens/{r.json()['id']}")


def test_d_escopo_restricao_revogacao_e_log(sessao_a):
    """O que aguentou no portão do token: escopo, teto de validade, IP, Referer curinga, revogação e log."""
    anon = novo_cliente()

    def hdr(t, **extra):
        return {"Authorization": f"Bearer {t}", **extra}

    r = sessao_a.post("/api/tokens", json={"nome": f"{PREFIXO_TESTE}-adv-cat", "escopos": ["catalogo:ler"]})
    tc = r.json()
    assert anon.post("/api/itens", json={"titulo": "x", "tipo": "app"}, headers=hdr(tc["token"])).status_code == 403
    assert anon.get("/api/itens", headers=hdr(tc["token"])).status_code == 200
    assert sessao_a.post(
        "/api/tokens", json={"nome": f"{PREFIXO_TESTE}-adv-400", "escopos": ["catalogo:ler"], "validade_dias": 400}
    ).status_code == 400
    r = sessao_a.post("/api/tokens", json={"nome": f"{PREFIXO_TESTE}-adv-ip", "escopos": ["catalogo:ler"],
                                          "restricao": {"ip": ["10.0.0.0/8"]}})
    ti = r.json()
    neg = anon.get("/api/itens", headers=hdr(ti["token"]))
    assert neg.status_code == 401 and neg.json()["erro"] == "ip_nao_permitido"
    r = sessao_a.post("/api/tokens", json={"nome": f"{PREFIXO_TESTE}-adv-ref", "escopos": ["catalogo:ler"],
                                          "restricao": {"referer": ["https://*.exemplo.gov.br"]}})
    tr = r.json()
    esperado = {None: 401, "https://a.exemplo.gov.br": 200, "https://a.b.exemplo.gov.br": 200,
                "https://exemplo.gov.br": 401, "https://mal.exemplo.gov.br.evil.com": 401,
                "http://a.exemplo.gov.br": 401}
    for origem, codigo in esperado.items():
        h = hdr(tr["token"], **({"Origin": origem} if origem else {}))
        assert anon.get("/api/itens", headers=h).status_code == codigo, origem
    r = sessao_a.post("/api/tokens", json={"nome": f"{PREFIXO_TESTE}-adv-rev", "escopos": ["catalogo:ler"]})
    tv = r.json()
    assert anon.get("/api/itens", headers=hdr(tv["token"])).status_code == 200
    ini = time.perf_counter()
    sessao_a.delete(f"/api/tokens/{tv['id']}")
    depois = anon.get("/api/itens", headers=hdr(tv["token"]))
    assert time.perf_counter() - ini < 1.0
    assert depois.status_code == 401 and depois.json()["erro"] == "token_revogado"
    assert "revogado em" in depois.json()["mensagem"]
    for lista in (sessao_a.get("/api/tokens?todos=1").json(),):
        assert not any("hash" in chave for chave in lista[0]), lista[0].keys()
    for t in sessao_a.get("/api/tokens?todos=1").json():
        if t["nome"].startswith(f"{PREFIXO_TESTE}-adv") and t["revogado_em"] is None:
            sessao_a.delete(f"/api/tokens/{t['id']}")


def test_d_leitura_por_token_aparece_no_log_com_token_id(sessao_a):
    r = sessao_a.post("/api/tokens", json={"nome": f"{PREFIXO_TESTE}-adv-log", "escopos": ["catalogo:ler"]})
    tok = r.json()
    try:
        anon = novo_cliente()
        assert anon.get("/api/itens", headers={"Authorization": f"Bearer {tok['token']}"}).status_code == 200
        time.sleep(0.5)
        linhas = sessao_a.get(f"/api/tokens/{tok['id']}/log").json()["itens"]
        assert linhas, "nenhuma linha de log_acesso para o token"
        um = linhas[0]
        for campo in ("ip", "rota", "bytes", "status"):
            assert campo in um, (campo, um.keys())
    finally:
        sessao_a.delete(f"/api/tokens/{tok['id']}")


# ====================================================================== L0-02-e varredura cruzada

@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G1-e1: GET /api/uploads/tipos declara x-auth 'S/T' no OpenAPI e responde 200 SEM credencial "
    "nenhuma. Rota nova, fora de docs/openapi.json, logo fora da varredura cruzada e fora do teste de "
    "privilégio declarado.",
)
def test_e1_rota_declarada_com_auth_exige_credencial():
    assert novo_cliente().get("/api/uploads/tipos").status_code == 401


@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G1-e2: as 7 rotas /rest/services/Geocodificador/GeocodeServer* não declaram x-privilegio no "
    "openapi_extra. test_privilegios_declarados.py existe para reprovar isso, mas lê docs/openapi.json (parado) "
    "e não vê as rotas novas.",
)
def test_e2_toda_rota_viva_declara_privilegio():
    from app.main import app

    spec = app.openapi()
    sem = sorted(
        (m.upper(), c) for c, ms in spec["paths"].items() for m, op in ms.items() if "x-privilegio" not in op
    )
    assert sem == []


@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G1-e3: duas rotas vivas fora da varredura devolvem 500. DELETE /api/convites/{id} com id não "
    "UUID levanta psycopg2 InvalidTextRepresentation (o parâmetro de caminho é str e vai cru para ::uuid); "
    "PUT /api/org/smtp com corpo vazio levanta ForeignKeyViolation porque o tipo de evento 'org/smtp_remover' "
    "não está em plat.evento_tipo. A varredura cruzada do L0-02-e aceita só 401/403/404 e teria pego as duas.",
)
def test_e3_rotas_novas_nao_devolvem_500(sessao_a):
    for metodo, url, corpo in (("DELETE", "/api/convites/nao-e-uuid", None), ("PUT", "/api/org/smtp", {})):
        try:
            r = sessao_a.request(metodo, url, **({"json": corpo} if corpo is not None else {}))
            codigo = r.status_code
        except Exception as e:  # noqa: BLE001 — o TestClient repropaga a exceção do servidor
            codigo = f"500/{type(e).__name__}"
        assert codigo in (400, 401, 403, 404, 409, 415, 422), f"{metodo} {url} -> {codigo}"


def test_e_medida_da_cobertura_real(medida):
    """Mede a cobertura da varredura cruzada contra o app VIVO, não contra o arquivo parado."""
    from tests.api import cruzado_casos as cc

    vivas = _rotas_vivas()
    cobertas = [r for r in vivas if r in cc.CASOS]
    medida("L0-02-e")("adversario_rotas_vivas", len(vivas), "rotas", "len(paths×methods) de app.openapi() vivo")
    medida("L0-02-e")("adversario_rotas_vivas_cobertas", len(cobertas), "rotas",
                      "rotas vivas com caso em tests/api/cruzado_casos.py")
    assert len(vivas) > 0


# ====================================================================== L0-02-f tela de usuários

def test_f_editor_admin_cruzado_e_ultimo_admin(sessao_a, sessao_b, sessao_plat, usuarios_a):
    """Refutação literal do item: editor chamando rota de admin; admin de A criando usuário em B; último
    administrador. Nenhuma passou — veredito NÃO REFUTADO nestas cláusulas."""
    editor, _u, _s = usuarios_a.sessao("editor")
    alvo, _t = usuarios_a.criar("editor")
    novo = {"login": f"{PREFIXO_TESTE}x", "nome": "x", "perfil": "editor"}
    assert editor.post("/api/usuarios", json=novo).status_code == 403
    assert editor.put(f"/api/usuarios/{alvo['id']}", json={"perfil": "admin"}).status_code == 403
    assert editor.post("/api/usuarios/lote", json={"ids": [alvo["id"]], "acao": "desabilitar"}).status_code == 403
    r = sessao_a.post("/api/usuarios", json={"login": f"{PREFIXO_TESTE}y", "nome": "y", "perfil": "editor"},
                      headers={"X-Plat-Inquilino": "demo2"})
    assert r.status_code == 403 and r.json()["erro"] == "so_superadmin"
    eu = sessao_a.get("/api/eu").json()
    r = sessao_a.put(f"/api/usuarios/{eu['id']}", json={"ativo": False})
    assert r.status_code == 409 and r.json()["erro"] == "proprio_usuario"
    lote = {"ids": list(range(1, 102)), "acao": "desabilitar"}
    assert sessao_a.post("/api/usuarios/lote", json=lote).status_code == 422
    slug = f"{PREFIXO_TESTE}-inq-{secrets.token_hex(3)}"
    r = sessao_plat.post("/api/plataforma/inquilinos",
                         json={"slug": slug, "nome": f"Inquilino de teste {slug}", "admin_login": "admin",
                               "admin_nome": "Administrador de teste", "config": {}})
    tid, temporaria = r.json()["id"], r.json()["senha_temporaria"]
    try:
        c1 = novo_cliente()
        assert entrar(c1, slug, "admin", temporaria).status_code == 200
        p1 = "Senha-adversario-1" + secrets.token_hex(3)
        assert c1.put("/api/eu/senha", json={"atual": temporaria, "nova": p1}).status_code == 204
        eu1 = c1.get("/api/eu").json()
        r = c1.put(f"/api/usuarios/{eu1['id']}", json={"perfil": "editor"})
        assert r.status_code == 409 and r.json()["erro"] == "ultimo_admin", r.text
    finally:
        sessao_plat.delete(f"/api/plataforma/inquilinos/{tid}")


def test_f_desabilitado_perde_a_sessao_em_menos_de_um_segundo(sessao_a, usuarios_a):
    c, u, _s = usuarios_a.sessao("editor")
    assert c.get("/api/eu").status_code == 200
    ini = time.perf_counter()
    assert sessao_a.put(f"/api/usuarios/{u['id']}", json={"ativo": False}).status_code == 200
    r = c.get("/api/eu")
    assert r.status_code == 401 and time.perf_counter() - ini < 1.0


# ====================================================================== L0-02-g perfil do usuário

def test_g_foto_email_e_campos_nao_editaveis(usuarios_a, conexao_plat_app):
    """Refutação literal do item: SVG com script como foto, e-mail fora do domínio, login novo no PUT."""
    import base64

    c, _u, _s = usuarios_a.sessao("editor")
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    r = c.post("/api/eu/foto", json={"conteudo": base64.b64encode(svg).decode()})
    assert r.status_code == 415 and r.json()["erro"] == "formato_nao_aceito", r.text
    grande = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"A" * 1_200_000).decode()
    assert c.post("/api/eu/foto", json={"conteudo": grande}).status_code in (413, 422)
    for campo, valor in (("login", f"{PREFIXO_TESTE}-outro"), ("perfil", "admin"), ("papel_id", 1), ("ativo", True)):
        r = c.put("/api/eu", json={campo: valor})
        assert r.status_code == 400 and r.json()["erro"] == "campo_nao_editavel", (campo, r.text)
    con = conexao_plat_app
    _config_do_demo(con, "UPDATE plat.tenant SET config = coalesce(config, '{}'::jsonb) || "
                         "'{\"auth\":{\"dominios_email\":[\"exemplo.gov.br\"]}}'::jsonb WHERE slug = 'demo'")
    try:
        r = c.put("/api/eu", json={"email": "alguem@outro.com"})
        assert r.status_code == 422 and r.json()["erro"] == "email_dominio", r.text
        assert c.put("/api/eu", json={"email": "alguem@exemplo.gov.br"}).status_code == 200
    finally:
        _config_do_demo(con, "UPDATE plat.tenant SET config = config - 'auth' WHERE slug = 'demo'")


@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G1-g1: visibilidade_perfil (privado/inquilino) é gravada e devolvida em /api/eu, mas nenhum "
    "consumidor a lê: grep por visibilidade_perfil em app/ acha só rotas_eu.py (escrita), comum.py (leitura do "
    "próprio) e modelos.py. Um perfil marcado 'privado' aparece igual na listagem /api/usuarios para qualquer "
    "membro do inquilino. Está na hipótese do item, não no portão literal.",
)
def test_g1_perfil_privado_some_da_listagem_do_inquilino(usuarios_a, sessao_a):
    c, u, _s = usuarios_a.sessao("editor")
    assert c.put("/api/eu", json={"visibilidade_perfil": "privado"}).status_code == 200
    outro, _t = usuarios_a.criar("editor")
    lista = sessao_a.get(f"/api/usuarios?q={u['login']}").json()["itens"]
    visiveis = [x for x in lista if x["id"] == u["id"] and x.get("nome")]
    assert visiveis == [], "usuário com perfil privado continua com o nome exposto na listagem do inquilino"
