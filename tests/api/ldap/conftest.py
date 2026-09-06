"""Fixtures do item L0-08-d-ldap: sobe/derruba o diretório de teste (glauth, `tests/ldap_fixture/`) e configura
o provedor do inquilino `demo` pela própria API (`PUT /api/org/ldap`), nunca por SQL direto — é a mesma rota
que um administrador real usaria. Todas as fixtures daqui são `lento` (contêiner Docker; ver `pyproject.toml`),
por isso os testes deste diretório também o são (marcados no módulo de teste, não aqui)."""

import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest

DIR = Path(__file__).resolve().parents[2] / "ldap_fixture"
HOST, PORTA = "127.0.0.1", 3893
BASE_DN = "dc=plataforma-teste,dc=local"
BIND_DN = f"cn=svc-plataforma,ou=gg-servico,{BASE_DN}"
BIND_SENHA = "Servico-ldap-0"
MAPA_GRUPO_PERFIL = {
    "gg-plataforma-admin": "admin",
    "gg-plataforma-editor": "editor",
    "gg-plataforma-leitura": "visualizador",
    # dora.lima (teste de colisão com login local) precisa de um perfil mapeado para o bind chegar até o
    # provisionamento (onde a regra `login_em_uso_local` vive); o grupo dela é distinto de
    # 'gg-plataforma-leitura' de propósito, para nunca contar no "encontrados" do teste de importação
    "gg-plataforma-teste-colisao": "visualizador",
}
USUARIOS = {  # login: senha (glauth.cfg tem os hashes sha256 destas senhas)
    "ana.silva": "Teste-ldap-1",
    "bruno.souza": "Teste-ldap-2",
    "carla.dias": "Teste-ldap-3",
    "dora.lima": "Teste-ldap-4",  # reservada ao teste de colisão com login local; nunca usada em outro teste
}


def _porta_aberta() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex((HOST, PORTA)) == 0


def _protocolo_pronto() -> bool:
    """Não basta a porta aceitar TCP: a primeira conexão por um mapeamento de porta do Docker recém-criado
    às vezes fecha no meio de uma operação real ('session terminated by server', medido nesta máquina —
    conntrack/iptables ainda aquecendo). O sinal de pronto é um bind ANÔNIMO de verdade, não só o handshake."""
    import ldap3

    try:
        s = ldap3.Server(HOST, port=PORTA, connect_timeout=1, get_info=ldap3.NONE)
        c = ldap3.Connection(s, authentication=ldap3.ANONYMOUS, receive_timeout=1, auto_bind=False)
        ok = c.bind()
        c.unbind()
        return ok
    except Exception:  # noqa: BLE001 — qualquer falha aqui só significa "ainda não"
        return False


@pytest.fixture(scope="session")
def servidor_ldap():
    """Sobe o contêiner glauth (`tests/ldap_fixture/subir.sh`); pula a suíte quando Docker não está
    disponível nesta máquina (nunca falha o resto do `make check` por isso)."""
    if shutil.which("docker") is None:
        pytest.skip("docker ausente nesta máquina; sem docker, mock do protocolo seria a alternativa (não construída)")
    subprocess.run(["bash", str(DIR / "subir.sh")], check=True, capture_output=True, text=True)
    limite = time.monotonic() + 10
    while not (_porta_aberta() and _protocolo_pronto()):
        if time.monotonic() > limite:
            pytest.fail("glauth não respondeu (porta + bind anônimo) em 10 s")
        time.sleep(0.2)
    yield {"url": f"ldap://{HOST}:{PORTA}", "base_dn": BASE_DN}
    subprocess.run(["bash", str(DIR / "descer.sh")], check=False, capture_output=True, text=True)


def derrubar_servidor_ldap():
    """Usado pelo teste que prova 'diretório fora do ar não derruba o login local' — chamado DENTRO do
    teste (não como fixture) para poder religar em seguida e não vazar o servidor parado para os outros
    testes da sessão."""
    subprocess.run(["bash", str(DIR / "descer.sh")], check=False, capture_output=True, text=True)


def religar_servidor_ldap():
    subprocess.run(["bash", str(DIR / "subir.sh")], check=True, capture_output=True, text=True)
    limite = time.monotonic() + 10
    while not (_porta_aberta() and _protocolo_pronto()):
        if time.monotonic() > limite:
            pytest.fail("glauth não religou (porta + bind anônimo) em 10 s")
        time.sleep(0.2)


@pytest.fixture(scope="session")
def provedor_ldap_demo(servidor_ldap, sessao_a):
    """Configura o provedor do inquilino `demo` pela API (privilégio `org.integracoes`, admin de `demo`),
    devolve o corpo configurado; desliga no fim (PUT com habilitado=False) — nunca apaga a linha (o próprio
    admin de `demo` pode ter configurado algo antes; a suíte só sobrepõe e restaura ao padrão local no fim)."""
    corpo = {
        "habilitado": True,
        "url": servidor_ldap["url"],
        "base_dn": servidor_ldap["base_dn"],
        "start_tls": False,  # glauth de teste não tem certificado; StartTLS real fica para quem tiver AD real
        "bind_dn": BIND_DN,
        "bind_senha": BIND_SENHA,
        "filtro_usuario": "(cn={login})",
        "atributo_grupos": "memberOf",
        "perfil_padrao": None,
        "mapa_grupo_perfil": MAPA_GRUPO_PERFIL,
    }
    r = sessao_a.put("/api/org/ldap", json=corpo)
    assert r.status_code == 200, r.text
    yield corpo
    sessao_a.put("/api/org/ldap", json={**corpo, "habilitado": False})
    # limpeza: apaga os usuários de origem 'ldap' com os 3 logins sintéticos (nunca outro usuário do inquilino)
    r = sessao_a.get("/api/usuarios?limite=1000")
    for u in r.json().get("itens", []):
        if u["login"] in USUARIOS and u["origem"] == "ldap":
            sessao_a.delete(f"/api/usuarios/{u['id']}")


@pytest.fixture(scope="session", autouse=True)
def limpeza_de_residuos(sessao_a, sessao_b):
    """Sobrescreve, só para este diretório, a fixture homônima (autouse) de `tests/api/conftest.py`: ela
    depende de `sessao_plat` (superadmin com 2FA), a conta MAIS disputada por todas as trilhas ao mesmo
    tempo desta árvore (anti-replay de 30 s do TOTP colide entre sessões concorrentes — medido: duas
    rodadas seguidas erraram aqui por causa disso, nada relacionado a LDAP). Nenhum teste deste diretório
    cria dado com prefixo 'zt' (os logins sintéticos do LDAP têm ponto, ex. 'ana.silva'; `provedor_ldap_demo`
    já limpa os seus próprios usuários no fim), então não há nada para esta função limpar aqui — ela só
    evita puxar `sessao_plat` para dentro da suíte de LDAP."""
    yield
