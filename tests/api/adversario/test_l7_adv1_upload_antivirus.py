"""Adversário de linha L7 operação (parte 1) — item `L7-03-a-antivirus-upload`
(laudo `laco/handoffs/T9/linha-L7-laudo-adversario-1.md`). Três achados independentes, cada um provado
rodando `POST /api/arquivos` de verdade contra a trilha (via `cliente`/`sessao_a`, mesmas fixtures do
arquivo oficial `tests/seguranca/test_upload.py`, que hoje falha em 8 dos 9 testes próprios pela mesma
causa raiz):

1. **ClamAV inexistente no código integrado**: `app/varredura_conteudo.py` (o módulo que atende
   `POST /api/arquivos` hoje) não tem função `endereco_clamd` nem qualquer menção a `clamd` — a alegação
   do ledger ("MotorClamd INSTREAM opcional... fora do ar = recusa") não corresponde a código nenhum em
   `wt/uniao`. `app/settings.py` declara `PLAT_CLAMD` mas nada o lê (achado transversal nº 1 do laudo).
2. **SVG e HTML são banidos por inteiro, nunca sanitizados-e-servidos**: a hipótese do item promete SVG
   "só após sanitização" e anexo `.html` "nunca servido... inline (anexos por subcaminho com CSP
   `sandbox`)" — ou seja, ACEITOS com salvaguarda, não rejeitados. `TIPOS_REAIS_DE_SCRIPT` em
   `varredura_conteudo.py` bane `image/svg+xml`/`text/html` incondicionalmente, e `app/svg_seguro.py`
   (o sanitizador, que existe e é usado pelo teste oficial do item) nunca é chamado pelo caminho de
   upload.
3. **Sem política de tipo por rota**: `POST /api/arquivos?classe=foto_campo` deveria recusar
   `application/octet-stream` ("tipo fora da lista da rota", 415, motor `politica_de_rota`) — hoje aceita
   (201)."""

from __future__ import annotations

import pytest

from app import varredura_conteudo as varredura


def _token(sessao_a, nome):
    return sessao_a.post("/api/tokens", json={"nome": nome, "escopos": ["admin:inquilino"]}).json()


# 18/09/2026: a marca xfail(strict=True) saiu porque o teste PASSA — rodado isolado na trilha `uniao`.
# Consertado em 94a65a46a ("fix(upload): restaura o pipeline único por classe (Politica/MotorClamd)
# perdido na fusão"). As marcas dos testes de SVG e de HTML, mais abaixo, CONTINUAM: aqueles dois
# defeitos ainda existem.
# O texto que vem abaixo (docstring/nome) descreve o achado ORIGINAL, não o estado de hoje.
def test_modulo_de_varredura_conhece_endereco_do_clamd():
    assert hasattr(varredura, "endereco_clamd"), (
        "app.varredura_conteudo não tem endereco_clamd — não há integração com ClamAV no código integrado"
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "app/varredura_conteudo.py bane image/svg+xml incondicionalmente (TIPOS_REAIS_DE_SCRIPT); o "
        "sanitizador app/svg_seguro.py (usado pelo teste oficial do item) nunca é chamado pelo caminho de "
        "upload — SVG é rejeitado (415), não sanitizado-e-servido (201) como a hipótese do item promete. "
        "Item L7-03-a-antivirus-upload."
    ),
)
def test_svg_e_aceito_e_sanitizado_nao_rejeitado(cliente, sessao_a):
    tok = _token(sessao_a, "zt-l7adv1-svg")
    try:
        svg = (
            b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)">'
            b"<script>alert(1)</script></svg>"
        )
        h = {"Authorization": f"Bearer {tok['token']}", "content-type": "image/svg+xml"}
        r = cliente.post("/api/arquivos?classe=anexo", content=svg, headers=h)
        assert r.status_code == 201, r.text
    finally:
        sessao_a.delete(f"/api/tokens/{tok['id']}")


@pytest.mark.xfail(
    strict=True,
    reason=(
        "app/varredura_conteudo.py bane text/html incondicionalmente (TIPOS_REAIS_DE_SCRIPT) — anexo "
        "HTML é rejeitado (415) em vez de aceito e servido como Content-Disposition: attachment num CSP "
        "sandbox, como a hipótese do item promete ('nunca servido... inline'). Item L7-03-a-antivirus-"
        "upload."
    ),
)
def test_anexo_html_e_aceito_para_servir_com_sandbox_nao_rejeitado(cliente, sessao_a):
    tok = _token(sessao_a, "zt-l7adv1-html")
    try:
        html = b"<!DOCTYPE html><html><body><script>document.cookie</script>oi</body></html>"
        h = {"Authorization": f"Bearer {tok['token']}", "content-type": "text/html"}
        r = cliente.post("/api/arquivos?classe=anexo", content=html, headers=h)
        assert r.status_code == 201, r.text
    finally:
        sessao_a.delete(f"/api/tokens/{tok['id']}")


# 18/09/2026: a marca xfail(strict=True) saiu porque o teste PASSA — rodado isolado na trilha `uniao`.
# Mesma causa e mesmo conserto do primeiro teste deste arquivo (94a65a46a): a tabela de tipos
# permitidos por CLASSE de rota passou a existir, então a recusa acontece.
# O texto que vem abaixo (docstring/nome) descreve o achado ORIGINAL, não o estado de hoje.
def test_tipo_fora_da_lista_da_rota_e_recusado(cliente, sessao_a):
    tok = _token(sessao_a, "zt-l7adv1-rota")
    try:
        png_minimo = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f"
            b"\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00"
            b"IEND\xaeB`\x82"
        )
        h = {"Authorization": f"Bearer {tok['token']}", "content-type": "application/octet-stream"}
        r = cliente.post("/api/arquivos?classe=foto_campo", content=png_minimo, headers=h)
        assert r.status_code == 415 and r.json()["detalhe"]["motor"] == "politica_de_rota", r.text
    finally:
        sessao_a.delete(f"/api/tokens/{tok['id']}")
