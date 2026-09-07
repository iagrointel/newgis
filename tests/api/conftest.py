"""Fixtures de identidade para tests/api (ADR 0002 seção 16): um cliente HTTP por identidade (cookie separado),
sessões dos admins de demo/demo2 (tests/credenciais.txt), superadmin de `plataforma` (2FA obrigatório: o segredo
TOTP fica em tests/credenciais_totp.txt, modo 600, fora do git; o install.sh reseta o 2FA do admin semeado e apaga
o arquivo), usuários temporários com limpeza. A suíte roda com PLAT_AMBIENTE=dev no ambiente do processo (ADR 0002
seção 16.4): validade_dias=0 e PLAT_TESTE_* só valem em dev."""

import contextlib
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
# PLAT_CREDENCIAIS_TOTP_ARQUIVO segue o MESMO padrão de PLAT_CREDENCIAIS_ARQUIVO: sem ela, todo ambiente
# (produção, homologação e qualquer trilha) escreve no mesmo tests/credenciais_totp.txt do repositório — o
# segredo TOTP do superadmin de `plataforma` de uma trilha sobrescreve o de outra e o próximo login 401
# com codigo_invalido porque o segredo do arquivo já não é o do banco (achado real, corrida entre trilhas
# concorrentes ligando o 2FA quase ao mesmo tempo). Cada ambiente isolado (schema/base próprios) precisa do
# seu próprio arquivo.
CREDENCIAIS_TOTP = Path(os.environ.get("PLAT_CREDENCIAIS_TOTP_ARQUIVO") or (ROOT / "tests" / "credenciais_totp.txt"))
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


@contextlib.contextmanager
def trinco(nome: str):
    """Trinco de arquivo entre processos (os workers do pytest-xdist são processos irmãos). Cada `nome` é um
    arquivo próprio em tests/, logo dois trincos diferentes nunca esperam um pelo outro."""
    import fcntl

    with open(Path(__file__).resolve().parents[1] / nome, "w") as arq:
        fcntl.flock(arq, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(arq, fcntl.LOCK_UN)


def entrar(cliente, slug: str, login: str, senha: str, segredo_totp: str | None = None):
    """Login completo (com 2FA quando exigido e o segredo é conhecido). Devolve a resposta final.

    07/09: sob pytest-xdist os workers entram com o MESMO usuário ao mesmo tempo; o banco guarda um
    desafio 2FA por usuário (plat.usuario.desafio_2fa_hash), então o login de um worker apaga o desafio
    do outro (410 desafio_expirado) e os dois disputam o mesmo passo de 30 s do TOTP (anti-replay).
    Só o trecho login -> 2fa é serializado, por trinco de arquivo; o resto da suíte segue em paralelo.
    """
    with trinco(".login.lock"):
        return _entrar(cliente, slug, login, senha, segredo_totp)


def _entrar(cliente, slug: str, login: str, senha: str, segredo_totp: str | None = None):
    from app.auth import totp

    r = cliente.post("/api/login", json={"inquilino": slug, "login": login, "senha": senha})
    if r.status_code == 200 and r.json().get("exige_2fa"):
        assert segredo_totp, f"{slug}/{login} exige 2FA e o segredo não é conhecido (install.sh reseta o 2FA)"
        r2 = cliente.post("/api/login/2fa", json={"desafio": r.json()["desafio"], "codigo": totp.codigo(segredo_totp)})
        # anti-replay (app/auth/totp.py::verificar): o passo de 30 s já gasto por outro worker (ou por uma rodada
        # anterior) devolve codigo_invalido. Espera o passo seguinte e repete — até 3 vezes, porque com 5 workers
        # entrando ao mesmo tempo dois passos seguidos podem estar gastos.
        for _ in range(3):
            if not (r2.status_code == 401 and r2.json().get("erro") == "codigo_invalido"):
                break
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


def _sessao_superadmin(cred):
    login, senha = cred["plataforma"]
    c = novo_cliente()
    # 07/09 (xdist): sem trinco os 5 workers ligam o 2FA do MESMO superadmin quase juntos — cada um grava um
    # segredo por cima do outro no banco e no arquivo, e os que chegam depois recebem 401 codigo_invalido; a
    # sessão da plataforma morre e todo teste que depende dela vira ERROR. Com o trinco, o primeiro worker liga
    # o 2FA e grava o segredo; os seguintes RELEEM o arquivo já dentro do trinco e só entram. Trinco próprio
    # (não o .login.lock), senão `entrar` esperaria por este mesmo processo.
    with trinco(".2fa_plataforma.lock"):
        r = entrar(c, "plataforma", login, senha, totp_guardado("plataforma"))
        assert r.status_code == 200 and r.json()["ok"] is True, (r.status_code, r.text)
        if "configurar_2fa" in r.json()["usuario"]["pendencias"]:
            segredo, _ = ligar_2fa(c)
            totp_guardar("plataforma", login, segredo)
    return c


@pytest.fixture(scope="session")
def sessao_plat(cred):
    """Superadmin (inquilino plataforma). 2FA obrigatório: liga na primeira vez e guarda o segredo fora do git."""
    return _sessao_superadmin(cred)


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


def varrer_residuos(sessao_a, sessao_b, sessao_plat) -> None:
    """Revoga tokens, apaga grupos, papéis e usuários zt-* dos inquilinos de demonstração e apaga inquilinos
    zt-inq-*. É uma VARREDURA POR PREFIXO: apaga o resíduo de qualquer rodada, inclusive o que outro worker
    do pytest-xdist ainda esteja usando — por isso só corre quando não há mais ninguém rodando."""
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


def sob_xdist() -> bool:
    """Verdadeiro dentro de um worker do pytest-xdist (a variável é posta pelo próprio xdist)."""
    return bool(os.environ.get("PYTEST_XDIST_WORKER"))


@pytest.fixture(scope="session", autouse=True)
def limpeza_de_residuos(sessao_a, sessao_b, sessao_plat):
    """No fim da sessão de testes: varre o resíduo zt-* (o que uma rodada abortada deixou; o install.sh em dev faz
    o mesmo).

    07/09: sob pytest-xdist esta varredura NÃO corre aqui. Os workers terminam em instantes diferentes e o
    primeiro a acabar revogava o token `zt-cruzado` e apagava os usuários zt* que os outros ainda estavam
    usando — daí 401 no lugar de 404 em test_plataforma/test_cruzado, sem relação com o que o teste prova.
    Quem varre é o processo CONTROLADOR, em pytest_sessionfinish, depois que todos os workers terminaram."""
    yield
    if sob_xdist():
        return
    varrer_residuos(sessao_a, sessao_b, sessao_plat)


def pytest_sessionfinish(session, exitstatus):
    import sys; print('DEBUG sessionfinish', __file__, os.environ.get('PYTEST_XDIST_WORKER'), getattr(session.config.option,'numprocesses',None), file=sys.stderr)
    """Controlador do pytest-xdist: varre o resíduo zt-* depois que TODOS os workers terminaram (ver
    limpeza_de_residuos). No processo do worker e na rodada serial não faz nada — lá quem varre é a fixture."""
    if sob_xdist() or not getattr(session.config.option, "numprocesses", None):
        return
    if not session.config.pluginmanager.hasplugin("xdist"):
        return
    try:
        c = credenciais()
        if not all(slug in c for slug in ("demo", "demo2", "plataforma")):
            return
        varrer_residuos(_sessao_admin(c, "demo"), _sessao_admin(c, "demo2"), _sessao_superadmin(c))
    except Exception as e:  # noqa: BLE001 - limpeza best-effort: nunca derruba a rodada por causa dela
        print(f"[limpeza] varredura de resíduos zt-* no controlador falhou: {type(e).__name__}: {e}")


def com_token(cliente, token: str, metodo: str, url: str, **kw):
    return cliente.request(metodo, url, headers={"Authorization": f"Bearer {token}", **kw.pop("headers", {})}, **kw)
