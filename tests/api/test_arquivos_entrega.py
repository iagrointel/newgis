"""Entrega segura do conteúdo enviado por cliente (item L7-03-b-antivirus-anexos, 2ª metade; docs/SEGURANCA.md
§8.6): `GET /api/arquivos/{sha256}` devolvia o byte com o MESMO `Content-Type` que o remetente escolhera e sem
`Content-Disposition` — medido pelo adversário independente (handoff T3, achado 23, cadeia), um arquivo enviado
como `text/html` voltava renderizando como HTML na própria origem da aplicação. Estes testes provam pela API
real que isso acabou, sem mexer no que a rota já fazia (o conteúdo devolvido continua idêntico ao enviado)."""

import hashlib
import os

ITEM = "L7-03-b-antivirus-anexos"


def test_conteudo_declarado_como_html_volta_como_anexo_generico(cliente, sessao_a):
    """O caso do achado 23: o remetente declara `text/html` num conteúdo que a varredura aceita (binário
    genérico). A resposta não pode voltar com `text/html`, tem de vir como anexo, com nosniff, e os bytes têm
    de ser exatamente os mesmos."""
    tok = sessao_a.post("/api/tokens", json={"nome": "zt-entrega-a", "escopos": ["admin:inquilino"]}).json()
    try:
        h = {"Authorization": f"Bearer {tok['token']}", "content-type": "text/html"}
        conteudo = os.urandom(2048)
        r = cliente.post("/api/arquivos?classe=zt_entrega", content=conteudo, headers=h)
        assert r.status_code == 201, r.text
        sha = r.json()["sha256"]
        assert sha == hashlib.sha256(conteudo).hexdigest()

        g = cliente.get(f"/api/arquivos/{sha}?classe=zt_entrega", headers={"Authorization": h["Authorization"]})
        assert g.status_code == 200
        assert g.content == conteudo  # a entrega continua fiel ao byte enviado
        assert g.headers["content-type"].split(";")[0] == "application/octet-stream"
        assert g.headers["content-disposition"].startswith("attachment;")
        assert g.headers["x-content-type-options"] == "nosniff"

        cliente.delete(f"/api/arquivos/{sha}?classe=zt_entrega", headers={"Authorization": h["Authorization"]})
    finally:
        sessao_a.delete(f"/api/tokens/{tok['id']}")


def test_tipo_do_vocabulario_e_preservado_mas_ainda_vem_como_anexo(cliente, sessao_a):
    """O outro lado: `application/pdf` está no vocabulário da instalação (`app/objetos.EXTENSOES`), então o tipo
    é preservado — o que muda para todo mundo é o `Content-Disposition: attachment` e o nome saneado."""
    tok = sessao_a.post("/api/tokens", json={"nome": "zt-entrega-b", "escopos": ["admin:inquilino"]}).json()
    try:
        h = {"Authorization": f"Bearer {tok['token']}", "content-type": "application/pdf"}
        conteudo = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
        r = cliente.post("/api/arquivos?classe=zt_entrega", content=conteudo, headers=h)
        assert r.status_code == 201, r.text
        sha = r.json()["sha256"]
        g = cliente.get(f"/api/arquivos/{sha}?classe=zt_entrega", headers={"Authorization": h["Authorization"]})
        assert g.status_code == 200 and g.content == conteudo
        assert g.headers["content-type"].split(";")[0] == "application/pdf"
        assert 'filename="zt_entrega-' in g.headers["content-disposition"]
        assert g.headers["content-disposition"].endswith(".pdf")
        cliente.delete(f"/api/arquivos/{sha}?classe=zt_entrega", headers={"Authorization": h["Authorization"]})
    finally:
        sessao_a.delete(f"/api/tokens/{tok['id']}")


def test_polyglot_pela_api_recebe_415_e_nao_chega_a_existir(cliente, sessao_a):
    """A refutação do adversário, agora fim a fim: GIF válido com `<script>` colado depois é recusado na borda
    (415 `conteudo_recusado`), e o sha256 desse conteúdo não existe no inquilino depois da tentativa."""
    gif = (
        b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,"
        b"\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
    ) + b"<script>alert(document.cookie)</script>"
    tok = sessao_a.post("/api/tokens", json={"nome": "zt-entrega-c", "escopos": ["admin:inquilino"]}).json()
    try:
        h = {"Authorization": f"Bearer {tok['token']}", "content-type": "image/gif"}
        r = cliente.post("/api/arquivos?classe=zt_entrega", content=gif, headers=h)
        assert r.status_code == 415, r.text
        assert r.json()["erro"] == "conteudo_recusado"
        sha = hashlib.sha256(gif).hexdigest()
        g = cliente.get(f"/api/arquivos/{sha}?classe=zt_entrega", headers={"Authorization": h["Authorization"]})
        assert g.status_code == 404
    finally:
        sessao_a.delete(f"/api/tokens/{tok['id']}")
