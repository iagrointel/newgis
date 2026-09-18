"""Configurações novas do item L0-07-a-configuracoes-org (segunda leva, depois da refutação T9): resumo, contato,
contatos administrativos (≥ 1, admin ativo do próprio inquilino), regional (unidades, formato de data e de
número/data), extent do mapa padrão, página inicial em blocos (texto / links / galeria; ≤ 15 blocos, ≤ 8 links
por bloco, URL só https:// ou caminho /), galeria em destaque (grupo existente) e os textos pré-login (banner de
aviso e termo de acesso), que o /entrar lê de GET /api/login/provedores ANTES de qualquer credencial.

O corpo de PUT é sempre o full-replace do `_corpo` de tests/api/test_org.py: cada teste restaura o inquilino
demo no `finally`."""

import base64
import secrets
import uuid

from tests.api.conftest import PREFIXO_TESTE, novo_cliente
from tests.api.test_org import _corpo


def _grupo(sessao) -> str:
    r = sessao.post("/api/grupos", json={"nome": f"{PREFIXO_TESTE}-galeria-{secrets.token_hex(3)}"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_campos_novos_persistem_e_voltam_no_get(sessao_a):
    original = sessao_a.get("/api/org").json()
    gid = _grupo(sessao_a)
    try:
        corpo = _corpo(original)
        corpo.update(
            resumo="inquilino de demonstração do portão",
            contato="contato@demo.test",
            unidades="imperial",
            formato_data="aaaa-mm-dd",
            formato_numero_data="navegador",
            centro=None,
            zoom=None,
            extent=[-46.7, -23.6, -46.5, -23.4],
            pagina_inicial=[
                {"tipo": "texto", "titulo": "boas-vindas", "texto": "texto de abertura do inquilino"},
                {"tipo": "links", "titulo": "atos", "links": [
                    {"rotulo": "prefeitura", "url": "https://prefeitura.example/atos"},
                    {"rotulo": "conteúdo", "url": "/conteudo"},
                ]},
                {"tipo": "galeria", "titulo": "destaques"},
            ],
            galeria_destaque=gid,
            banner_aviso="rede monitorada — <b>acesso restrito</b>",
            termo_acesso="ao entrar você concorda com o termo de uso interno",
        )
        r = sessao_a.put("/api/org", json=corpo)
        assert r.status_code == 200, r.text
        org = sessao_a.get("/api/org").json()  # nova requisição: leitura do banco, não do eco do PUT
        assert org["resumo"] == "inquilino de demonstração do portão"
        assert org["contato"] == "contato@demo.test"
        assert org["regional"] == {"unidades": "imperial", "formato_data": "aaaa-mm-dd",
                                   "formato_numero_data": "navegador"}
        assert org["mapa"]["extent"] == [-46.7, -23.6, -46.5, -23.4]
        assert org["mapa"]["centro"] is None and org["mapa"]["zoom"] is None
        assert org["pagina_inicial"] == corpo["pagina_inicial"]
        assert org["galeria_destaque"] == gid
        assert org["banner_aviso"] == "rede monitorada — <b>acesso restrito</b>"  # cru: saneamento é na renderização
        assert org["termo_acesso"] == "ao entrar você concorda com o termo de uso interno"
    finally:
        assert sessao_a.put("/api/org", json=_corpo(original)).status_code == 200
        sessao_a.delete(f"/api/grupos/{gid}")


def test_contatos_admin_normaliza_dedup_e_recusa_vazio(sessao_a):
    original = sessao_a.get("/api/org").json()
    login_admin = original["contatos_admin"][0]
    try:
        corpo = _corpo(original)
        corpo["contatos_admin"] = [f" {login_admin.upper()} ", login_admin, login_admin]
        r = sessao_a.put("/api/org", json=corpo)
        assert r.status_code == 200, r.text
        assert sessao_a.get("/api/org").json()["contatos_admin"] == [login_admin]

        # refutação do adversário: "define contato administrativo vazio" — nem lista zerada (pydantic)…
        r = sessao_a.put("/api/org", json={**_corpo(original), "contatos_admin": []})
        assert r.status_code == 422 and r.json()["erro"] == "validacao"
        assert any("contatos_admin" in d.get("campo", "") for d in r.json()["detalhe"])
        # …nem lista que ZERA depois do strip (só espaços) — esse passa no esquema e morre na rota
        r = sessao_a.put("/api/org", json={**_corpo(original), "contatos_admin": ["  ", ""]})
        assert r.status_code == 422 and r.json()["erro"] == "validacao"
        assert r.json()["detalhe"]["campo"] == "contatos_admin"
        assert sessao_a.get("/api/org").json()["contatos_admin"] == [login_admin]
    finally:
        sessao_a.put("/api/org", json=_corpo(original))


def test_contatos_admin_recusa_inexistente_e_nao_admin(sessao_a, sessao_b, usuarios_a, usuarios_b):
    original = sessao_a.get("/api/org").json()
    _c_ed, u_ed, _s = usuarios_a.sessao("editor")
    _c_b, u_b, _s_b = usuarios_b.sessao("admin")  # admin de OUTRO inquilino (demo2)
    try:
        for logins in ([f"{PREFIXO_TESTE}-ninguem-{secrets.token_hex(3)}"], [u_ed["login"]]):
            r = sessao_a.put("/api/org", json={**_corpo(original), "contatos_admin": logins})
            assert r.status_code == 422 and r.json()["erro"] == "validacao", r.text
            assert r.json()["detalhe"]["campo"] == "contatos_admin"
            assert r.json()["detalhe"]["logins"] == logins
        # admin de OUTRO inquilino: RLS esconde a linha, sai como "não encontrado" — nunca vaza que existe
        r = sessao_a.put("/api/org", json={**_corpo(original), "contatos_admin": [u_b["login"]]})
        assert r.status_code == 422 and r.json()["detalhe"]["campo"] == "contatos_admin"
        assert r.json()["detalhe"]["logins"] == [u_b["login"]]
    finally:
        sessao_a.put("/api/org", json=_corpo(original))


def test_validacoes_422_blocos(sessao_a):
    base = _corpo(sessao_a.get("/api/org").json())
    texto = {"tipo": "texto", "titulo": "", "texto": "x"}

    r = sessao_a.put("/api/org", json={**base, "pagina_inicial": [texto] * 16})  # ORG_BLOCOS_MAX = 15
    assert r.status_code == 422 and r.json()["erro"] == "validacao"
    assert any("pagina_inicial" in d.get("campo", "") for d in r.json()["detalhe"])

    nove = [{"rotulo": f"l{n}", "url": "https://exemplo.test/"} for n in range(9)]  # ORG_BLOCO_LINKS_MAX = 8
    r = sessao_a.put("/api/org", json={**base, "pagina_inicial": [{"tipo": "links", "titulo": "", "links": nove}]})
    assert r.status_code == 422

    r = sessao_a.put("/api/org", json={**base, "pagina_inicial": [{"tipo": "video", "titulo": ""}]})
    assert r.status_code == 422

    r = sessao_a.put("/api/org", json={**base, "pagina_inicial": [
        {"tipo": "links", "titulo": "", "links": [{"rotulo": "x", "url": "javascript:alert(1)"}]}]})
    assert r.status_code == 422
    assert any("url" in d.get("campo", "") for d in r.json()["detalhe"])

    r = sessao_a.put("/api/org", json={**base, "pagina_inicial": [
        {"tipo": "links", "titulo": "", "links": [{"rotulo": "x", "url": "//externo.test/caminho"}]}]})
    assert r.status_code == 422  # //host é URL de protocolo relativo: fora da lista

    r = sessao_a.put("/api/org", json={**base, "pagina_inicial": [{"tipo": "texto", "titulo": "", "texto": ""}]})
    assert r.status_code == 422

    assert sessao_a.get("/api/org").json()["pagina_inicial"] == base["pagina_inicial"]  # nada grudou


def test_validacoes_422_campos_novos(sessao_a):
    base = _corpo(sessao_a.get("/api/org").json())

    r = sessao_a.put("/api/org", json={**base, "resumo": "x" * 311})  # ORG_RESUMO_MAX = 310
    assert r.status_code == 422

    r = sessao_a.put("/api/org", json={**base, "contato": "nao-e-email"})
    assert r.status_code == 422 and r.json()["detalhe"]["campo"] == "contato"

    r = sessao_a.put("/api/org", json={**base, "banner_aviso": "x" * 501})  # ORG_BANNER_MAX = 500
    assert r.status_code == 422

    r = sessao_a.put("/api/org", json={**base, "termo_acesso": "x" * 4001})  # ORG_TERMO_MAX = 4000
    assert r.status_code == 422

    r = sessao_a.put("/api/org", json={**base, "unidades": "parsecs"})
    assert r.status_code == 422 and r.json()["detalhe"]["campo"] == "unidades"

    r = sessao_a.put("/api/org", json={**base, "formato_data": "dd-mm-aa"})
    assert r.status_code == 422 and r.json()["detalhe"]["campo"] == "formato_data"

    r = sessao_a.put("/api/org", json={**base, "extent": [-46.5, -23.6, -46.7, -23.4]})  # oeste > leste
    assert r.status_code == 422 and r.json()["detalhe"]["campo"] == "extent"

    r = sessao_a.put("/api/org", json={**base, "extent": [-200, 0, 100, 10]})  # fora de lon/lat
    assert r.status_code == 422 and r.json()["detalhe"]["campo"] == "extent"

    r = sessao_a.put("/api/org", json={**base, "galeria_destaque": "nao-e-uuid"})
    assert r.status_code == 422  # validador do modelo: nunca chega ao WHERE uuid do banco (seria 500)

    r = sessao_a.put("/api/org", json={**base, "galeria_destaque": str(uuid.uuid4())})
    assert r.status_code == 422 and r.json()["detalhe"]["campo"] == "galeria_destaque"


def test_banner_e_termo_expostos_no_login_publico(sessao_a):
    original = sessao_a.get("/api/org").json()
    anon = novo_cliente()
    injecao = "aviso <script>alert(1)</script> do inquilino"
    try:
        corpo = _corpo(original)
        corpo.update(banner_aviso=injecao, termo_acesso="termo de acesso interno")
        assert sessao_a.put("/api/org", json=corpo).status_code == 200
        r = anon.get("/api/login/provedores?inquilino=demo")
        assert r.status_code == 200, r.text
        inq = r.json()["inquilino"]
        # o texto vai CRU até o cliente — a defesa é o textContent do /entrar (prova e2e), nunca marcação
        assert inq["banner_aviso"] == injecao
        assert inq["termo_acesso"] == "termo de acesso interno"
    finally:
        sessao_a.put("/api/org", json=_corpo(original))
    r = anon.get("/api/login/provedores?inquilino=demo")
    assert r.status_code == 200 and r.json()["inquilino"]["banner_aviso"] is None


def test_logo_acima_de_1mb_recusado_antes_do_armazenamento(sessao_a):
    """Portão do item: 'logo > 1 MB recusado'. O corte acontece em `_decodificar_base64_logo` ANTES de falar
    com o armazenamento de objetos — por isso a prova não depende do Garage (a instância de trilhas não está
    de pé nesta máquina; o caminho feliz do logo fica em test_org.py, que aqui falha por ambiente, não por
    código)."""
    grande = base64.b64encode(b"\x00" * (1024 * 1024 + 1024)).decode()
    r = sessao_a.post("/api/org/logo", json={"conteudo": grande})
    assert r.status_code in (413, 422), r.status_code  # 413 da rota, ou 422 do max_length do pydantic
    if r.status_code == 413:
        assert r.json()["erro"] == "logo_grande"


def test_config_nova_isolada_entre_inquilinos(sessao_a, sessao_b):
    org_a = sessao_a.get("/api/org").json()
    org_b = sessao_b.get("/api/org").json()
    anon = novo_cliente()
    try:
        corpo_a = _corpo(org_a)
        corpo_a["banner_aviso"] = f"{PREFIXO_TESTE}-banner-a-{secrets.token_hex(3)}"
        assert sessao_a.put("/api/org", json=corpo_a).status_code == 200
        # B não vê a chave nova de A nem no GET autenticado…
        assert sessao_b.get("/api/org").json()["banner_aviso"] == org_b["banner_aviso"]
        # …nem no caminho público pré-login do PRÓPRIO slug
        r = anon.get("/api/login/provedores?inquilino=demo2")
        assert r.status_code == 200 and r.json()["inquilino"]["banner_aviso"] != corpo_a["banner_aviso"]
    finally:
        sessao_a.put("/api/org", json=_corpo(org_a))
