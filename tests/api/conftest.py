"""Fixtures de identidade para tests/api (ADR 0002 seção 16): um cliente HTTP por identidade (cookie separado),
sessões dos admins de demo/demo2 (tests/credenciais.txt), superadmin de `plataforma` (2FA obrigatório: o segredo
TOTP fica em tests/credenciais_totp.txt, modo 600, fora do git; o install.sh reseta o 2FA do admin semeado e apaga
o arquivo), usuários temporários com limpeza. A suíte roda com PLAT_AMBIENTE=dev no ambiente do processo (ADR 0002
seção 16.4): validade_dias=0 e PLAT_TESTE_* só valem em dev."""

import os
import secrets
import time
from pathlib import Path

import pytest

os.environ.setdefault("PLAT_AMBIENTE", "dev")

ROOT = Path(__file__).resolve().parents[2]
# item L7-31: PLAT_CREDENCIAIS_ARQUIVO aponta para tests/credenciais_homolog.txt quando a suíte roda contra
# o schema de homologação (db/homolog_bootstrap.sh semeia os admins lá; nunca os mesmos de produção) — mesmo
# padrão de PLAT_OPENAPI_ARQUIVO logo abaixo.
CREDENCIAIS = Path(os.environ.get("PLAT_CREDENCIAIS_ARQUIVO") or (ROOT / "tests" / "credenciais.txt"))
CREDENCIAIS_TOTP = ROOT / "tests" / "credenciais_totp.txt"
PREFIXO_TESTE = "zt"  # logins/nomes criados pela suíte começam assim (limpeza por prefixo)


def arquivo_openapi() -> dict:
    """docs/openapi.json comitado (o que o teste cruzado e os de declaração leem). PLAT_OPENAPI_ARQUIVO aponta para
    outra cópia quando a árvore de trabalho é compartilhada e outra trilha regera o arquivo no meio da rodada."""
    import json

    caminho = Path(os.environ.get("PLAT_OPENAPI_ARQUIVO") or (ROOT / "docs" / "openapi.json"))
    return json.loads(caminho.read_text(encoding="utf-8"))


def credenciais() -> dict[str, tuple[str, str]]:
    """{slug: (login, senha)} de tests/credenciais.txt (semeado pelo install.sh)."""
    saida = {}
    if CREDENCIAIS.exists():
        for linha in CREDENCIAIS.read_text(encoding="utf-8").splitlines():
            partes = linha.split()
            if len(partes) >= 3:
                saida[partes[0]] = (partes[1], " ".join(partes[2:]))
    return saida


def totp_guardado(slug: str) -> str | None:
    if CREDENCIAIS_TOTP.exists():
        for linha in CREDENCIAIS_TOTP.read_text(encoding="utf-8").splitlines():
            partes = linha.split()
            if len(partes) == 3 and partes[0] == slug:
                return partes[2]
    return None


def totp_guardar(slug: str, login: str, segredo: str) -> None:
    existentes = CREDENCIAIS_TOTP.read_text(encoding="utf-8").splitlines() if CREDENCIAIS_TOTP.exists() else []
    linhas = [li for li in existentes if not li.startswith(slug + " ")]
    linhas.append(f"{slug} {login} {segredo}")
    CREDENCIAIS_TOTP.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    CREDENCIAIS_TOTP.chmod(0o600)


def novo_cliente():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app, base_url="http://testserver")


def entrar(cliente, slug: str, login: str, senha: str, segredo_totp: str | None = None):
    """Login completo (com 2FA quando exigido e o segredo é conhecido). Devolve a resposta final."""
    from app.auth import totp

    r = cliente.post("/api/login", json={"inquilino": slug, "login": login, "senha": senha})
    if r.status_code == 200 and r.json().get("exige_2fa"):
        assert segredo_totp, f"{slug}/{login} exige 2FA e o segredo não é conhecido (install.sh reseta o 2FA)"
        r2 = cliente.post("/api/login/2fa", json={"desafio": r.json()["desafio"], "codigo": totp.codigo(segredo_totp)})
        if r2.status_code == 401 and r2.json().get("erro") == "codigo_invalido":
            # anti-replay: o código deste passo de 30 s já foi usado por uma rodada anterior da suíte; espera o próximo
            time.sleep(totp.PASSO_S - (time.time() % totp.PASSO_S) + 0.5)
            r = cliente.post("/api/login", json={"inquilino": slug, "login": login, "senha": senha})
            corpo = {"desafio": r.json()["desafio"], "codigo": totp.codigo(segredo_totp)}
            r2 = cliente.post("/api/login/2fa", json=corpo)
        r = r2
    return r


def ligar_2fa(cliente) -> tuple[str, list[str]]:
    """Liga o 2FA da sessão do cliente; devolve (segredo, códigos de recuperação)."""
    from app.auth import totp

    r = cliente.post("/api/eu/2fa/iniciar", json={})
    assert r.status_code == 200, r.text
    segredo = r.json()["segredo"]
    r = cliente.post("/api/eu/2fa/confirmar", json={"codigo": totp.codigo(segredo)})
    assert r.status_code == 200, r.text
    return segredo, r.json()["codigos_recuperacao"]


@pytest.fixture(scope="session")
def cred(env):
    c = credenciais()
    for slug in ("demo", "demo2", "plataforma"):
        if slug not in c:
            pytest.skip(f"tests/credenciais.txt sem a linha de {slug} (rode sudo bash install.sh)")
    return c


def _sessao_admin(cred, slug):
    login, senha = cred[slug]
    c = novo_cliente()
    r = entrar(c, slug, login, senha)
    assert r.status_code == 200 and r.json()["ok"] is True, (slug, r.status_code, r.text)
    return c


@pytest.fixture(scope="session")
def sessao_a(cred):
    """Admin do inquilino demo (A)."""
    return _sessao_admin(cred, "demo")


@pytest.fixture(scope="session")
def sessao_b(cred):
    """Admin do inquilino demo2 (B)."""
    return _sessao_admin(cred, "demo2")


@pytest.fixture(scope="session")
def sessao_plat(cred):
    """Superadmin (inquilino plataforma). 2FA obrigatório: liga na primeira vez e guarda o segredo fora do git."""
    login, senha = cred["plataforma"]
    c = novo_cliente()
    r = entrar(c, "plataforma", login, senha, totp_guardado("plataforma"))
    assert r.status_code == 200 and r.json()["ok"] is True, (r.status_code, r.text)
    if "configurar_2fa" in r.json()["usuario"]["pendencias"]:
        segredo, _ = ligar_2fa(c)
        totp_guardar("plataforma", login, segredo)
    return c


@pytest.fixture(scope="session")
def ids(sessao_a, sessao_b, sessao_plat):
    """ids dos admins e dos inquilinos (via /api/eu; o tenant_id vem de test_rls.ids_por_slug quando precisa)."""
    a = sessao_a.get("/api/eu").json()
    b = sessao_b.get("/api/eu").json()
    p = sessao_plat.get("/api/eu").json()
    return {"a": a, "b": b, "plat": p}


class Usuarios:
    """Cria usuários temporários num inquilino (pela sessão do admin) e apaga no fim da sessão de testes."""

    def __init__(self, admin):
        self.admin = admin
        self.criados: list[int] = []

    def criar(self, perfil="editor", papel_id=None, email=None, login=None, nome=None) -> tuple[dict, str]:
        login = login or f"{PREFIXO_TESTE}{secrets.token_hex(4)}"
        r = self.admin.post(
            "/api/usuarios",
            json={
                "login": login,
                "nome": nome or f"Teste {login}",
                "perfil": perfil,
                "papel_id": papel_id,
                "email": email,
            },
        )
        assert r.status_code == 201, r.text
        u = r.json()["usuario"]
        self.criados.append(u["id"])
        return u, r.json()["senha_temporaria"]

    def sessao(self, perfil="editor", **kw):
        """Usuário novo já com senha definitiva e sessão aberta: (cliente, usuario, senha)."""
        u, temporaria = self.criar(perfil, **kw)
        c = novo_cliente()
        slug = self.admin.get("/api/eu").json()["inquilino"]["slug"]
        r = entrar(c, slug, u["login"], temporaria)
        assert r.status_code == 200 and r.json()["usuario"]["pendencias"] == ["trocar_senha"], r.text
        senha = "Senha-definitiva-1" + secrets.token_hex(3)  # dígito fixo: hex só com letras reprovaria
        r = c.put("/api/eu/senha", json={"atual": temporaria, "nova": senha})
        assert r.status_code == 204, r.text
        return c, u, senha

    def limpar(self):
        for uid in reversed(self.criados):
            # usuário com grupos: transfere/apaga é do teste; aqui só se tenta o caminho simples
            self.admin.delete(f"/api/usuarios/{uid}")
        self.criados.clear()


@pytest.fixture(scope="session")
def usuarios_a(sessao_a):
    u = Usuarios(sessao_a)
    yield u
    u.limpar()


@pytest.fixture(scope="session")
def usuarios_b(sessao_b):
    u = Usuarios(sessao_b)
    yield u
    u.limpar()


@pytest.fixture(scope="session")
def token_a(sessao_a):
    """Token admin:inquilino do admin de A (o que o teste cruzado usa)."""
    r = sessao_a.post("/api/tokens", json={"nome": f"{PREFIXO_TESTE}-cruzado", "escopos": ["admin:inquilino"]})
    assert r.status_code == 201, r.text
    tok = r.json()
    yield tok
    sessao_a.delete(f"/api/tokens/{tok['id']}")


class InquilinoTemporario:
    """Inquilino zt-inq-* criado pelo superadmin, com o admin já logado e com senha definitiva; apagado no fim
    (DELETE /api/plataforma/inquilinos/{id}): o teste nunca depende de estado limpo dos inquilinos de demonstração."""

    def __init__(self, sessao_plat, config=None):
        self.slug = f"{PREFIXO_TESTE}-inq-{secrets.token_hex(3)}"
        r = sessao_plat.post(
            "/api/plataforma/inquilinos",
            json={
                "slug": self.slug,
                "nome": f"Inquilino de teste {self.slug}",
                "admin_login": "admin",
                "admin_nome": "Administrador de teste",
                "config": config or {},
            },
        )
        assert r.status_code == 201, r.text
        self.id = r.json()["id"]
        self.admin_id = r.json()["admin"]["id"]
        temporaria = r.json()["senha_temporaria"]
        self.admin = novo_cliente()
        assert entrar(self.admin, self.slug, "admin", temporaria).status_code == 200
        self.senha = "Senha-do-admin-1" + secrets.token_hex(3)
        assert self.admin.put("/api/eu/senha", json={"atual": temporaria, "nova": self.senha}).status_code == 204
        self._plat = sessao_plat

    def apagar(self):
        self._plat.delete(f"/api/plataforma/inquilinos/{self.id}")


@pytest.fixture
def inquilino_temporario(sessao_plat):
    inq = InquilinoTemporario(sessao_plat)
    yield inq
    inq.apagar()


@pytest.fixture(scope="session", autouse=True)
def limpeza_de_residuos(sessao_a, sessao_b, sessao_plat):
    """No fim da sessão de testes: revoga tokens, apaga grupos, papéis e usuários zt-* dos inquilinos de demonstração
    e apaga inquilinos zt-inq-* (o que uma rodada abortada deixou; o install.sh em dev faz o mesmo)."""
    yield
    for s in (sessao_a, sessao_b):
        for t in s.get("/api/tokens?todos=1").json():
            if t["nome"].startswith(PREFIXO_TESTE) and t["revogado_em"] is None:
                s.delete(f"/api/tokens/{t['id']}")
        for g in s.get(f"/api/grupos?q={PREFIXO_TESTE}&limite=200").json()["itens"]:
            s.delete(f"/api/grupos/{g['id']}")
        for u in s.get(f"/api/usuarios?q={PREFIXO_TESTE}&limite=200").json()["itens"]:
            if u["login"].startswith(PREFIXO_TESTE):
                s.delete(f"/api/usuarios/{u['id']}")
        for p in s.get("/api/papeis").json()["personalizados"]:
            if p["nome"].startswith(PREFIXO_TESTE):
                s.delete(f"/api/papeis/{p['id']}")
    for t in sessao_plat.get("/api/plataforma/inquilinos").json():
        if t["slug"].startswith(f"{PREFIXO_TESTE}-inq-"):
            sessao_plat.delete(f"/api/plataforma/inquilinos/{t['id']}")


def com_token(cliente, token: str, metodo: str, url: str, **kw):
    return cliente.request(metodo, url, headers={"Authorization": f"Bearer {token}", **kw.pop("headers", {})}, **kw)
