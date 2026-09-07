"""Item L7-03-e — o que se prova lendo ARQUIVO, não resposta:

1. `web/` não tem <script> em linha sem nonce nem tratador de evento em atributo (`onclick=`, `onerror=`…),
   que é o que uma CSP com `script-src 'self' 'nonce-…'` recusa em silêncio: a página abriria em branco.
2. `deploy/nginx.conf` declara o conjunto inteiro em cada `location` de `/static/` (lá o nginx é a origem do
   corpo) e NÃO repete nas rotas proxiadas o que a aplicação já declara (add_header acrescenta: sairiam dois).
3. `deploy/nginx_tls.conf` está no perfil intermediate da Mozilla, com stapling, e o install.sh o instala.
"""

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
WEB = RAIZ / "web"
# vendor: biblioteca de terceiros servida do disco, verificada por sha256 em web/vendor/VERSOES.txt; ela não é
# documento HTML da casa e não entra em nenhuma página por <script> em linha.
PAGINAS = sorted(p for p in WEB.rglob("*.html") if "vendor" not in p.parts)
ATRIBUTO_DE_EVENTO = re.compile(r"\son[a-z]+\s*=", re.IGNORECASE)
SCRIPT_ABERTURA = re.compile(r"<script([^>]*)>", re.IGNORECASE)
CABECALHOS_ESTATICO = (
    "Content-Security-Policy",
    "Permissions-Policy",
    "Cross-Origin-Opener-Policy",
    "Cross-Origin-Resource-Policy",
    "Referrer-Policy",
    "X-Content-Type-Options",
    "Strict-Transport-Security",
    "X-Robots-Tag",
    "Cache-Control",
)
# estes a APLICAÇÃO declara (app/cabecalhos.py); repetidos numa location proxiada sairiam em dobro
SO_DA_APLICACAO = ("Content-Security-Policy", "Referrer-Policy", "X-Content-Type-Options", "X-Frame-Options")


def test_ha_pagina_para_examinar():
    assert len(PAGINAS) >= 15, [p.name for p in PAGINAS]


@pytest.mark.parametrize("pagina", PAGINAS, ids=lambda p: str(p.relative_to(WEB)))
def test_pagina_sem_script_em_linha_sem_nonce(pagina):
    texto = pagina.read_text(encoding="utf-8")
    for atributos in SCRIPT_ABERTURA.findall(texto):
        tem_src = "src=" in atributos.lower()
        tem_nonce = "nonce=" in atributos.lower()
        assert tem_src or tem_nonce, (pagina.name, atributos)


@pytest.mark.parametrize("pagina", PAGINAS, ids=lambda p: str(p.relative_to(WEB)))
def test_pagina_sem_tratador_de_evento_em_atributo(pagina):
    achados = ATRIBUTO_DE_EVENTO.findall(pagina.read_text(encoding="utf-8"))
    assert not achados, (pagina.name, achados)


def _blocos_location(texto: str) -> list[tuple[str, str]]:
    """(cabeçalho do location, corpo até a chave que o fecha). O arquivo não tem location aninhado."""
    saida = []
    for casa in re.finditer(r"^\s*location\s+([^{]+)\{", texto, re.MULTILINE):
        fim = texto.index("\n    }", casa.end())
        saida.append((casa.group(1).strip(), texto[casa.end():fim]))
    return saida


@pytest.fixture(scope="module")
def nginx_conf() -> str:
    return (RAIZ / "deploy" / "nginx.conf").read_text(encoding="utf-8")


def test_locations_de_estatico_declaram_o_conjunto_inteiro(nginx_conf):
    estaticos = [(c, b) for c, b in _blocos_location(nginx_conf) if "static" in c]
    assert len(estaticos) == 2, [c for c, _ in estaticos]
    for cabeca, corpo in estaticos:
        faltam = [h for h in CABECALHOS_ESTATICO if f"add_header {h} " not in corpo]
        assert not faltam, (cabeca, faltam)


def test_rotas_proxiadas_nao_repetem_o_que_a_aplicacao_declara(nginx_conf):
    for cabeca, corpo in _blocos_location(nginx_conf):
        if "proxy_pass" not in corpo:
            continue
        repetidos = [h for h in SO_DA_APLICACAO if f"add_header {h} " in corpo]
        assert not repetidos, (cabeca, repetidos)
        assert "add_header Strict-Transport-Security " in corpo, cabeca


@pytest.fixture(scope="module")
def tls_conf() -> str:
    return (RAIZ / "deploy" / "nginx_tls.conf").read_text(encoding="utf-8")


def test_perfil_tls_intermediate(tls_conf):
    protocolos = re.search(r"^ssl_protocols ([^;]+);", tls_conf, re.MULTILINE)[1].split()
    assert protocolos == ["TLSv1.2", "TLSv1.3"], protocolos
    cifras = re.search(r"^ssl_ciphers ([^;]+);", tls_conf, re.MULTILINE)[1].split(":")
    assert cifras and all(c.startswith("ECDHE-") for c in cifras), cifras
    assert all(("GCM" in c) or ("CHACHA20" in c) for c in cifras), cifras
    assert "ssl_prefer_server_ciphers off;" in tls_conf
    assert "ssl_session_tickets off;" in tls_conf


def test_stapling_ligado_e_verificado(tls_conf):
    assert "ssl_stapling on;" in tls_conf
    assert "ssl_stapling_verify on;" in tls_conf
    assert "ssl_trusted_certificate " in tls_conf
    assert re.search(r"^resolver ", tls_conf, re.MULTILINE), "stapling sem resolvedor não busca a resposta OCSP"


def test_instalador_escreve_o_perfil_tls_e_liga_http2():
    instalador = (RAIZ / "install.sh").read_text(encoding="utf-8")
    assert "deploy/nginx_tls.conf" in instalador
    assert "/etc/nginx/conf.d/plat_tls.conf" in instalador
    # nginx 1.24 (Ubuntu 24.04): HTTP/2 é opção do `listen`, não a diretiva `http2 on;` do 1.25.1+
    assert "http2" in instalador
