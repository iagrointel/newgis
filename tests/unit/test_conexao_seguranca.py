"""Refutação do item L6-02-a-modelo-conexao-e-seguranca: "adversário usa host público que redireciona para
127.0.0.1:8150 e host cujo DNS muda entre a validação e o uso (rebinding)". O portão do item pede exatamente
os 8 casos abaixo (docstring de app/conexao/seguranca.py) mais a URL pública normal aceita e testável.

Os testes de rede real (URL pública, servidor local simulando um "host público" que redireciona para IP
interno) exigem que a máquina tenha saída à internet — o mesmo pressuposto de `tests/api/test_acervo.py` e de
toda fonte do acervo testada por HTTP nesta casa; marcados `lento` para não travar `make teste` sem rede."""

import http.server
import socket
import threading

import pytest

from app import limites
from app.conexao import seguranca as s

# a URL pública é um endpoint de dado aberto federal (IBGE), nunca nome de cliente/parceiro (regra P7)
URL_PUBLICA_REAL = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/35"


# --------------------------------------------------------------------- 1-5, 7: validação sem rede (IP/esquema/URL)
@pytest.mark.parametrize(
    "url,motivo_esperado",
    [
        ("http://127.0.0.1:8150/", "loopback"),  # caso 1 do portão: 127.0.0.1
        ("http://127.0.0.1/", "loopback"),
        ("http://localhost/", "loopback"),  # DNS local resolve para loopback (caso 5)
        ("http://169.254.169.254/latest/meta-data/", "link_local"),  # caso 1: metadado de nuvem
        ("http://10.0.0.5/", "privado"),  # caso 1: 10.0.0.0/8
        ("http://10.255.255.255/", "privado"),
        ("http://172.16.0.1/", "privado"),
        ("http://172.31.255.255/", "privado"),
        ("http://192.168.1.1/", "privado"),
        ("http://100.64.0.1/", "privado"),  # CGNAT (RFC 6598) — gap conhecido de ipaddress.is_private
        ("http://[::1]/", "loopback"),
        ("http://[fc00::1]/", "privado"),
        ("http://0.0.0.0/", "nao_especificado"),
        ("http://224.0.0.1/", "multicast"),
    ],
)
def test_ip_privado_e_recusado(url, motivo_esperado):
    with pytest.raises(s.ErroURLInsegura) as exc:
        s.validar_url(url)
    assert exc.value.motivo.startswith("ip_bloqueado:" + motivo_esperado)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",  # esquema fora da allowlist
        "ftp://servicodados.ibge.gov.br/",
        "gopher://127.0.0.1:8150/",
    ],
)
def test_esquema_fora_de_http_https_e_recusado(url):
    with pytest.raises(s.ErroURLInsegura) as exc:
        s.validar_url(url)
    assert exc.value.motivo == "esquema_nao_permitido"


def test_userinfo_na_url_e_recusado():
    """caso do portão: userinfo na URL — mesmo com host público de verdade, a presença de user:pass@ já
    recusa antes de qualquer DNS."""
    with pytest.raises(s.ErroURLInsegura) as exc:
        s.validar_url("http://usuario:senha@servicodados.ibge.gov.br/")
    assert exc.value.motivo == "userinfo_na_url"


def test_host_ausente_e_recusado():
    with pytest.raises(s.ErroURLInsegura) as exc:
        s.validar_url("http:///caminho-sem-host")
    assert exc.value.motivo == "host_ausente"


def test_porta_interna_sozinha_nao_e_o_criterio_o_ip_e():
    """caso do portão ("porta interna 8150"): a MESMA porta num host público de verdade é aceita — o que
    bloqueia é sempre o IP, nunca o número da porta."""
    with pytest.raises(s.ErroURLInsegura):
        s.validar_url("http://127.0.0.1:8150/")
    v = s.validar_url("https://servicodados.ibge.gov.br:443/api/v1/localidades/estados/35")
    assert v.porta == 443


def test_dns_que_resolve_para_interno_e_recusado(monkeypatch):
    """caso 5 do portão: host cujo DNS aponta para IP interno (sem precisar de rede real: mocka getaddrinfo)."""

    def _fake_getaddrinfo(host, port, *a, **kw):
        assert host == "interno.exemplo.teste"
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("10.20.30.40", port))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)
    with pytest.raises(s.ErroURLInsegura) as exc:
        s.validar_url("http://interno.exemplo.teste/")
    assert exc.value.motivo == "ip_bloqueado:privado:10.20.30.40"


def test_dns_nao_resolve_vira_erro_nomeado_nunca_silencio(monkeypatch):
    def _fake_getaddrinfo(*a, **kw):
        raise socket.gaierror("nao resolve")

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)
    with pytest.raises(s.ErroURLInsegura) as exc:
        s.validar_url("http://nao-existe.exemplo.teste/")
    assert exc.value.motivo == "dns_falhou"


# --------------------------------------------------------------------- 6: redirecionamento revalidado (com rede real)
@pytest.mark.lento
def test_url_publica_normal_e_aceita_e_testavel():
    """portão: 'URL pública normal aceita e testável'."""
    v = s.validar_url(URL_PUBLICA_REAL)
    assert v.esquema == "https"
    assert v.ips  # resolveu a algum IP público de verdade
    resultado = s.buscar_seguro(URL_PUBLICA_REAL)
    assert resultado.ok is True
    assert resultado.status == 200
    assert resultado.saltos == 0


@pytest.mark.lento
def test_redirecionamento_para_ip_interno_e_recusado_no_salto():
    """caso 6 do portão: host PÚBLICO de verdade (bind no IP público real desta máquina — nunca loopback,
    senão o hop 0 já recusaria e o teste provaria só o caso 1 de novo) que responde 302 para
    169.254.169.254 (metadado de nuvem). `buscar_seguro` tem de aceitar o hop 0 e recusar só no hop 1."""
    ip_publico = _ip_publico_desta_maquina()
    if ip_publico is None:
        pytest.skip("máquina sem IP público roteável (sem interface global IPv4)")

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(302)
            self.send_header("Location", "http://169.254.169.254/latest/meta-data/")
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer((ip_publico, 0), Handler)
    porta = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        resultado = s.buscar_seguro(f"http://{ip_publico}:{porta}/")
    finally:
        srv.shutdown()
        t.join(timeout=2)

    assert resultado.ok is False
    assert resultado.saltos == 1  # aceitou o hop 0 (host público real) e recusou só o Location
    assert resultado.mensagem == "url_insegura:ip_bloqueado:link_local:169.254.169.254"


@pytest.mark.lento
def test_conexao_pinada_no_ip_ja_validado_nao_resolve_dns_de_novo(monkeypatch):
    """caso 8 (DNS rebinding): depois de `validar_url` resolver o host, uma segunda chamada a
    `socket.getaddrinfo` para O MESMO host, no momento de conectar, teria de nunca acontecer — prova
    isso derrubando `getaddrinfo` global e checando que a busca ainda funciona (a conexão real usa o IP
    já pinado, não uma nova resolução)."""
    v = s.validar_url(URL_PUBLICA_REAL)

    chamadas = []
    original = socket.getaddrinfo

    def _contando(host, *a, **kw):
        chamadas.append(host)
        return original(host, *a, **kw)

    monkeypatch.setattr(socket, "getaddrinfo", _contando)
    with s.cliente_pinado(v, timeout_conectar=3.0, timeout_ler=6.0) as cliente:
        r = cliente.get(URL_PUBLICA_REAL)
        assert r.status_code == 200
    # a única resolução de DNS observada durante a conexão pinada é a da THREAD do backend, para o IP
    # literal (nunca para o hostname original) — o hostname não aparece de novo
    assert v.host not in chamadas


@pytest.mark.lento
def test_redirecionamento_em_loop_para_no_limite_de_saltos():
    """host público real (nunca loopback) que redireciona para si mesmo indefinidamente: `buscar_seguro`
    tem de desistir em `CONEXAO_REDIRECT_MAX` saltos, nunca entrar em loop infinito."""
    ip_publico = _ip_publico_desta_maquina()
    if ip_publico is None:
        pytest.skip("máquina sem IP público roteável (sem interface global IPv4)")

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            n = int(self.path.strip("/") or "0")
            self.send_response(302)
            self.send_header("Location", f"http://{ip_publico}:{self.server.server_port}/{n + 1}")
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer((ip_publico, 0), Handler)
    porta = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        resultado = s.buscar_seguro(f"http://{ip_publico}:{porta}/0")
    finally:
        srv.shutdown()
        t.join(timeout=2)

    assert resultado.ok is False
    assert resultado.mensagem == "redirecionamentos_demais"
    assert resultado.saltos == limites.CONEXAO_REDIRECT_MAX


def _ip_publico_desta_maquina() -> str | None:
    import ipaddress
    import subprocess

    try:
        saida = subprocess.run(
            ["ip", "-4", "-o", "addr", "show", "scope", "global"], capture_output=True, text=True, timeout=3
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for linha in saida.splitlines():
        partes = linha.split()
        if len(partes) < 4:
            continue
        ip = partes[3].split("/")[0]
        try:
            if ipaddress.ip_address(ip).is_global:
                return ip
        except ValueError:
            continue
    return None
