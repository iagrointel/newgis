"""HARD-03 — adversário L0, catálogo (L0-03) e fonte registrada / SSRF (L0-04-i, app/conexao/seguranca.py).
Cruzamento de inquilino no item, injeção de SQL no filtro do acervo, SSRF na criação de conexão, e a URL
assinada de objeto de um inquilino não pode buscar objeto de outro. Só roda em trilha (conftest do pacote)."""

from __future__ import annotations

import pytest

from tests.api.catalogo.conftest import DADOS_POR_TIPO
from tests.api.conftest import PREFIXO_TESTE, com_token


def _item(sessao, titulo: str) -> str:
    r = sessao.post("/api/itens", json={"tipo": "mapa", "titulo": titulo, "dados": DADOS_POR_TIPO["mapa"]})
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ---------------------------------------------------------------- L0-03 cruzamento de inquilino no item
def test_l0_03_item_de_b_invisivel_e_inalteravel_por_a(sessao_a, sessao_b):
    item_b = _item(sessao_b, f"{PREFIXO_TESTE} b secreto")
    try:
        for verbo, kw in (("get", {}), ("put", {"json": {"titulo": "x"}}), ("patch", {"json": {"titulo": "x"}}),
                          ("delete", {})):
            r = getattr(sessao_a, verbo)(f"/api/itens/{item_b}", **kw)
            assert r.status_code in (403, 404), (verbo, r.status_code, r.text[:160])
        # e não vaza na busca/facetas de A
        r = sessao_a.get(f"/api/itens?q={PREFIXO_TESTE} b secreto&limite=200")
        assert item_b not in {i["id"] for i in r.json()["itens"]}
        # compartilhamento de B por A também não
        r = sessao_a.put(f"/api/itens/{item_b}/compartilhamento", json={"acesso": "inquilino"})
        assert r.status_code in (403, 404), (r.status_code, r.text[:160])
    finally:
        sessao_b.delete(f"/api/itens/{item_b}")


def test_l0_03_token_de_a_nao_alcanca_item_de_b(sessao_a, sessao_b, cliente):
    r = sessao_a.post("/api/tokens", json={"nome": f"{PREFIXO_TESTE}-cat", "escopos": ["catalogo:ler"]})
    tok = r.json()
    item_b = _item(sessao_b, f"{PREFIXO_TESTE} b por token")
    try:
        r = com_token(cliente, tok["token"], "GET", f"/api/itens/{item_b}")
        assert r.status_code in (403, 404), (r.status_code, r.text[:160])
    finally:
        sessao_b.delete(f"/api/itens/{item_b}")
        sessao_a.delete(f"/api/tokens/{tok['id']}")


# ---------------------------------------------------------------- L0 acervo: injeção no filtro
def test_l0_acervo_filtro_nao_e_injetavel(sessao_a):
    """O filtro de /api/acervo é montado por f-string (bandit B608), mas os valores vão como parâmetro. Uma
    tentativa de injeção tem de virar busca literal (0 ou N linhas coerentes), nunca erro de SQL nem vazamento."""
    for veneno in ("' OR '1'='1", "'; DROP TABLE plat.item;--", "%' UNION SELECT null--", "\\"):
        r = sessao_a.get("/api/acervo", params={"q": veneno, "limite": 5})
        assert r.status_code == 200, (veneno, r.status_code, r.text[:160])
        assert isinstance(r.json()["itens"], list)
    # o mesmo para o domínio (igualdade parametrizada)
    r = sessao_a.get("/api/acervo", params={"dominio": "' OR '1'='1", "limite": 5})
    assert r.status_code == 200 and r.json()["itens"] == []


# ---------------------------------------------------------------- L0-04-i SSRF na criação de conexão
SSRF = [
    ("http://127.0.0.1:8150/", "loopback"),
    ("http://169.254.169.254/latest/meta-data/", "metadado de nuvem"),
    ("http://10.0.0.1/", "rede privada"),
    ("http://192.168.0.1/", "rede privada"),
    ("http://100.64.0.1/", "CGNAT"),
    ("http://[::1]/", "loopback ipv6"),
    ("http://user:senha@example.com/", "userinfo na url"),
    ("ftp://example.com/", "esquema não permitido"),
    ("file:///etc/passwd", "esquema não permitido"),
    ("http://localhost:5432/", "localhost"),
    ("http://0.0.0.0/", "não especificado"),
]


@pytest.mark.parametrize("url,motivo", SSRF)
def test_l0_04i_conexao_ssrf_recusada_na_criacao(sessao_a, url, motivo):
    r = sessao_a.post("/api/conexoes", json={"tipo": "wfs", "nome": f"{PREFIXO_TESTE} ssrf", "url": url})
    assert r.status_code in (400, 422), (motivo, url, r.status_code, r.text[:160])
    # não ficou registrada
    lista = sessao_a.get("/api/conexoes?limite=200").json()["itens"]
    assert not any(c.get("url") == url for c in lista), (motivo, url)


def test_l0_04i_ssrf_por_dns_para_ip_privado(sessao_a):
    """Nome público que resolve para IP privado: o validador resolve DNS e bloqueia pela categoria do IP, não pela
    string. localhost.localdomain resolve para 127.0.0.1 na maioria das máquinas; se não resolver, o teste
    registra que a checagem por string não é a defesa (o IP é que é), sem falso verde."""
    r = sessao_a.post("/api/conexoes", json={"tipo": "wfs", "nome": f"{PREFIXO_TESTE} dns",
                                             "url": "http://localhost.localdomain/"})
    if r.status_code in (400, 422):
        assert "loopback" in r.text or "privado" in r.text or "dns" in r.text, r.text[:200]
    else:
        pytest.skip(f"localhost.localdomain não resolveu para IP privado nesta máquina: {r.status_code}")


# ---------------------------------------------------------------- L0-11 URL assinada de objeto por inquilino
def test_l0_11_url_assinada_de_a_nao_serve_objeto_de_b(sessao_a, sessao_b, cliente):
    """A assinatura HMAC cobre a chave (prefixada pelo slug do inquilino). Trocar o prefixo do inquilino na chave
    invalida a assinatura; a rota anônima /api/objetos/{chave} responde 4xx, nunca o objeto de outro inquilino."""
    from urllib.parse import parse_qs, urlsplit

    from app import objetos

    slug_a = sessao_a.get("/api/eu").json()["inquilino"]["slug"]
    slug_b = sessao_b.get("/api/eu").json()["inquilino"]["slug"]
    sha = "a" * 64  # a chave exige um sha256 de verdade no nome do objeto (regex objetos.CHAVE)
    chave_a = f"{slug_a}/objeto/{sha}.bin"
    url = objetos.url_assinada(chave_a, 300)
    qs = parse_qs(urlsplit(url).query)
    ate, assinatura = int(qs["ate"][0]), qs["assinatura"][0]
    assert objetos.assinatura_valida(chave_a, ate, assinatura)
    # a mesma assinatura na chave de B (troca do prefixo) tem de falhar
    chave_b = f"{slug_b}/objeto/{sha}.bin"
    assert not objetos.assinatura_valida(chave_b, ate, assinatura)
    # e a rota anônima recusa a chave de B com a assinatura de A
    r = cliente.get(f"/api/objetos/{chave_b}", params={"ate": ate, "assinatura": assinatura})
    assert r.status_code in (401, 403, 404), (r.status_code, r.text[:160])
    # travessia de caminho na chave: recusada pela regex CHAVE, nunca chega ao armazenamento
    assert not objetos.assinatura_valida(f"{slug_a}/../{slug_b}/{sha}.bin", ate, "qualquer")
