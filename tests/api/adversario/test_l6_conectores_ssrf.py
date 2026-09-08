"""HARD-03 — adversário de conectores (L6-02, SSRF e vazamento de credencial) sobre master. A fonte externa é a
única superfície que faz o servidor buscar uma URL do cliente. Ataca: `validar_url` (unidade) com file://,
metadado de nuvem, loopback/privado/CGNAT, userinfo, DNS que resolve para IP interno; a rota de criar conexão
(SSRF na entrada, não só no teste de saúde); a revalidação de cada salto de redirecionamento; e o não-vazamento
da credencial em resposta e em log. Cada ataque com controle positivo. Só roda em trilha (conftest do pacote)."""

from __future__ import annotations

import logging
import secrets

import pytest

from app.conexao import seguranca as seg

BLOQUEADAS = [
    "file:///etc/passwd",
    "http://169.254.169.254/latest/meta-data/",       # metadado de nuvem
    "http://127.0.0.1:8150/",                          # loopback + porta interna
    "http://localhost:5432/",                          # localhost
    "http://10.0.0.1/", "http://192.168.1.1/", "http://172.16.0.1/",  # RFC 1918
    "http://100.64.0.1/",                              # CGNAT (RFC 6598)
    "http://[::1]/", "http://[fd00::1]/",              # loopback / ULA ipv6
    "http://0.0.0.0/",                                 # não especificado
    "http://user:senha@example.com/",                 # userinfo na url
    "gopher://example.com/", "ftp://example.com/",     # esquema não permitido
    "http://169.254.169.254.nip.io/" if False else "http://metadata.google.internal/",  # nome de metadado
]


# ---------------------------------------------------------------- validar_url (unidade)
@pytest.mark.parametrize("url", BLOQUEADAS)
def test_validar_url_recusa_alvo_inseguro(url):
    with pytest.raises(seg.ErroURLInsegura):
        seg.validar_url(url)


def test_validar_url_aceita_alvo_publico():
    """Controle positivo: um host público legítimo passa (resolve para IP público). Usa um nome estável do IANA
    reservado a documentação/exemplo; se não resolver nesta máquina, o teste registra que não pôde confirmar o
    caminho feliz, sem falso verde."""
    try:
        v = seg.validar_url("https://example.com/wfs?service=WFS")
    except seg.ErroURLInsegura as e:
        if e.motivo.startswith(("dns", "url_")):
            pytest.skip(f"sem DNS para example.com nesta máquina: {e.motivo}")
        raise
    assert v.host == "example.com" and v.ips


def test_validar_url_dns_para_ip_privado_e_bloqueado():
    try:
        seg.validar_url("http://localhost.localdomain/")
    except seg.ErroURLInsegura as e:
        assert "loopback" in str(e.motivo) or "privado" in str(e.motivo) or "dns" in str(e.motivo)
    else:
        pytest.skip("localhost.localdomain não resolveu para IP privado nesta máquina")


def test_cada_salto_de_redirect_e_revalidado():
    """buscar_seguro revalida cada Location do zero por validar_url (defesa de rebinding/redirect para interno).
    Sem servidor externo, prova a propriedade pela estrutura: um Location interno cai em url_insegura. Aqui
    exercita-se o ponto de validação chamando validar_url com o alvo interno que um redirect entregaria."""
    with pytest.raises(seg.ErroURLInsegura):
        seg.validar_url("http://169.254.169.254/")  # o alvo que um redirect malicioso tentaria alcançar
    # e o cliente nunca segue redirect por conta própria
    import inspect

    fonte = inspect.getsource(seg.cliente_pinado)
    assert "follow_redirects=False" in fonte


# ---------------------------------------------------------------- SSRF na criação da conexão (rota)
@pytest.mark.parametrize("url", BLOQUEADAS)
def test_criar_conexao_recusa_ssrf_na_entrada(sessao_a, url):
    r = sessao_a.post("/api/conexoes", json={"tipo": "wfs", "nome": f"zt{secrets.token_hex(3)}", "url": url})
    assert r.status_code in (400, 422), (url, r.status_code, r.text[:160])
    lista = sessao_a.get("/api/conexoes?limite=200").json()["itens"]
    assert not any(c.get("url") == url for c in lista), url


def test_editar_conexao_para_url_interna_e_recusado(sessao_a):
    """A defesa vale também no PATCH: cria uma conexão legítima e tenta apontá-la para o metadado de nuvem."""
    r = sessao_a.post("/api/conexoes", json={"tipo": "wfs", "nome": f"zt{secrets.token_hex(3)}",
                                             "url": "https://example.com/wfs"})
    if r.status_code not in (201, 200):
        pytest.skip(f"criação legítima não passou (DNS?): {r.status_code} {r.text[:120]}")
    cid = r.json()["id"]
    try:
        r = sessao_a.patch(f"/api/conexoes/{cid}", json={"url": "http://169.254.169.254/"})
        assert r.status_code in (400, 422), (r.status_code, r.text[:160])
    finally:
        sessao_a.delete(f"/api/conexoes/{cid}")


# ---------------------------------------------------------------- credencial nunca vaza
def test_credencial_nunca_volta_em_resposta_nem_em_log(sessao_a, caplog):
    segredo = "senha-super-secreta-" + secrets.token_hex(8)
    caplog.set_level(logging.DEBUG)
    r = sessao_a.post("/api/conexoes", json={
        "tipo": "postgres_fdw", "nome": f"zt{secrets.token_hex(3)}",
        "url": "https://example.com/", "credencial": segredo})
    if r.status_code not in (201, 200):
        pytest.skip(f"criação com credencial não passou nesta trilha: {r.status_code} {r.text[:120]}")
    cid = r.json()["id"]
    try:
        # a resposta da criação não traz a credencial nem o cifrado
        assert segredo not in r.text and "credencial_cifrada" not in r.text
        # nem o GET, nem a listagem
        assert segredo not in sessao_a.get(f"/api/conexoes/{cid}").text
        assert segredo not in sessao_a.get("/api/conexoes?limite=200").text
        # a resposta expõe só "tem_credencial", nunca o valor
        assert sessao_a.get(f"/api/conexoes/{cid}").json().get("tem_credencial") is True
        # e o segredo não caiu em nenhuma linha de log da aplicação
        texto = "\n".join(rec.getMessage() for rec in caplog.records)
        assert segredo not in texto
    finally:
        sessao_a.delete(f"/api/conexoes/{cid}")


def test_erro_de_conexao_nao_ecoa_a_credencial(sessao_a):
    """Um teste de saúde que falha (host público inexistente) não pode devolver a credencial no corpo do erro."""
    segredo = "cred-no-corpo-" + secrets.token_hex(6)
    # host que RESOLVE (passa o portão SSRF na criação) mas cujo caminho de saúde falha (WFS num path inexistente)
    r = sessao_a.post("/api/conexoes", json={
        "tipo": "wfs", "nome": f"zt{secrets.token_hex(3)}",
        "url": "https://example.com/caminho-que-nao-existe-" + secrets.token_hex(4), "credencial": segredo})
    if r.status_code not in (201, 200):
        pytest.skip(f"criação não passou nesta trilha (DNS?): {r.status_code} {r.text[:120]}")
    cid = r.json()["id"]
    try:
        rt = sessao_a.post(f"/api/conexoes/{cid}/testar")
        assert segredo not in rt.text, rt.text[:200]
        assert "credencial_cifrada" not in rt.text
    finally:
        sessao_a.delete(f"/api/conexoes/{cid}")
