"""`GET /api/qr.svg` (item L5-01-d, widget compartilhar): QR gerado localmente, SVG sem script, texto limitado,
autenticação obrigatória."""

from app import limites


def test_qr_svg_local_sem_script(sessao_a):
    r = sessao_a.get("/api/qr.svg", params={"texto": "https://exemplo.invalido/app?item=1"})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("image/svg+xml")
    assert r.text.lstrip().startswith("<?xml") or r.text.lstrip().startswith("<svg")
    assert "<script" not in r.text and "http://" not in r.text.replace("http://www.w3.org", "")


def test_qr_exige_autenticacao_e_limita_o_texto(cliente, sessao_a):
    assert cliente.get("/api/qr.svg", params={"texto": "x"}).status_code == 401
    assert sessao_a.get("/api/qr.svg", params={"texto": "x" * (limites.QR_TEXTO_MAX + 1)}).status_code == 422
    assert sessao_a.get("/api/qr.svg").status_code == 422
