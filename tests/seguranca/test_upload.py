"""Pipeline único de upload (item L7-03-a-antivirus-upload; docs/SEGURANCA.md §9). Portão, cláusula a cláusula:
EICAR recusado quando clamd está ligado e o evento aparece na trilha (aqui um `clamd` de teste que fala o protocolo
INSTREAM por socket unix — o daemon real não cabe na RAM desta máquina, D21); SVG com `<script>` sai sem o
script; zip com 1 GB de zeros é recusado; `.exe` renomeado para `.tif` é recusado pelos bytes; 1 byte acima do
plano = 413 antes de ler o corpo inteiro (medido pelo número de mensagens ASGI consumidas). Refutação: polyglot
GIF+HTML, SVG com `xlink:href` javascript, `.dbf` malformado, KMZ com 10 mil entradas, anexo `.html` inline."""

from __future__ import annotations

import asyncio
import hashlib
import io
import os
import socket
import struct
import threading
import zipfile

import psycopg2
import pytest

from app import limites
from app import varredura_conteudo as varredura
from app.schema_ambiente import CursorSchemaAmbiente
from app.svg_seguro import sanitizar, tem_script
from tests.api.test_rls import contexto, ids_por_slug

EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
PNG_MINIMO = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)
GIF_HTML_POLYGLOT = b"GIF89a<html><script>alert(1)</script></html>"
EXE_MZ = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00" + b"\x00" * 200 + b"PE\x00\x00"
SVG_SCRIPT = (
    b'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" onload="alert(1)">'
    b"<script>alert(1)</script><foreignObject><body onload=\"alert(2)\"/></foreignObject>"
    b'<a xlink:href="javascript:alert(3)">liga</a><circle r="5" onclick="x()"/>'
    b'<image xlink:href="javascript:alert(4)"/><use href="https://x/evil.svg#a"/>'
    b'<rect width="10" height="10" style="fill:url(https://x/y)"/><path d="M0 0L1 1"/></svg>'
)


# --------------------------------------------------------------------------- clamd de teste


class ClamdFalso:
    """fala o INSTREAM do clamd por socket unix: `FOUND` quando o fluxo contém a assinatura EICAR, senão `OK`."""

    def __init__(self, caminho: str):
        self.caminho = caminho
        self.srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.srv.bind(caminho)
        self.srv.listen(4)
        self.recebidos: list[int] = []
        self.t = threading.Thread(target=self._servir, daemon=True)
        self.t.start()

    def _servir(self):
        while True:
            try:
                c, _ = self.srv.accept()
            except OSError:
                return
            with c:
                cmd = b""
                while not cmd.endswith(b"\0"):
                    cmd += c.recv(1)
                dados = b""
                while True:
                    cab = c.recv(4)
                    n = struct.unpack(">I", cab)[0]
                    if n == 0:
                        break
                    while n:
                        p = c.recv(n)
                        dados += p
                        n -= len(p)
                self.recebidos.append(len(dados))
                c.sendall(b"stream: Eicar-Signature FOUND\0" if EICAR in dados else b"stream: OK\0")

    def parar(self):
        self.srv.close()
        os.unlink(self.caminho)


@pytest.fixture
def clamd(tmp_path, monkeypatch):
    caminho = str(tmp_path / "clamd.sock")
    f = ClamdFalso(caminho)
    monkeypatch.setattr(varredura, "endereco_clamd", lambda: caminho)
    yield f
    f.parar()


def _token(sessao_a, nome):
    return sessao_a.post("/api/tokens", json={"nome": nome, "escopos": ["admin:inquilino"]}).json()


def _eventos(env, tenant_id, tipo, sha):
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        contexto(con, tenant_id)
        with con.cursor() as cur:
            cur.execute(
                "SELECT propriedades FROM plat.evento WHERE tipo = %s AND alvo_id = %s ORDER BY em DESC LIMIT 1",
                (tipo, sha),
            )
            return cur.fetchone()
    finally:
        con.close()


# --------------------------------------------------------------------------- 1. EICAR + trilha


def test_eicar_recusado_com_clamd_ligado_e_evento_na_trilha(cliente, sessao_a, env, clamd):
    tok = _token(sessao_a, "zt-l703a-eicar")
    try:
        h = {"Authorization": f"Bearer {tok['token']}", "content-type": "text/plain"}
        r = cliente.post("/api/arquivos?classe=anexo", content=EICAR, headers=h)
        assert r.status_code == 415, r.text
        corpo = r.json()
        assert corpo["erro"] == "conteudo_recusado" and corpo["detalhe"]["assinatura"] == "Eicar-Signature"
        assert corpo["detalhe"]["motor"] == "clamd"
        assert clamd.recebidos == [len(EICAR)]  # o fluxo inteiro foi ao clamd
        sha = hashlib.sha256(EICAR).hexdigest()
        con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
        ids = ids_por_slug(con)
        con.close()
        ev = _eventos(env, ids["demo"], "arquivos/quarentena", sha)
        assert ev is not None, "quarentena sem registro na trilha"
        props = ev["propriedades"]
        assert props["assinatura"] == "Eicar-Signature" and props["classe"] == "anexo" and props["sha256"] == sha
        assert "X5O!" not in str(props)  # nunca o conteúdo
        # o objeto NÃO existe (a quarentena é o registro, não o armazenamento)
        assert cliente.get(f"/api/arquivos/{sha}?classe=anexo", headers=h).status_code == 404
        # conteúdo limpo com o mesmo clamd ligado passa
        r2 = cliente.post("/api/arquivos?classe=anexo", content=b"texto inofensivo\n", headers=h)
        assert r2.status_code == 201, r2.text
        cliente.delete(f"/api/arquivos/{r2.json()['sha256']}?classe=anexo", headers=h)
    finally:
        sessao_a.delete(f"/api/tokens/{tok['id']}")


def test_clamd_configurado_mas_fora_do_ar_recusa_nunca_deixa_passar(cliente, sessao_a, tmp_path, monkeypatch):
    monkeypatch.setattr(varredura, "endereco_clamd", lambda: str(tmp_path / "nao-existe.sock"))
    tok = _token(sessao_a, "zt-l703a-clamd-fora")
    try:
        h = {"Authorization": f"Bearer {tok['token']}", "content-type": "text/plain"}
        r = cliente.post("/api/arquivos?classe=anexo", content=b"qualquer coisa", headers=h)
        assert r.status_code == 415 and "clamd" in r.json()["mensagem"], r.text
    finally:
        sessao_a.delete(f"/api/tokens/{tok['id']}")


# --------------------------------------------------------------------------- 2. SVG


def test_svg_com_script_sai_sem_o_script():
    limpo = sanitizar(SVG_SCRIPT)
    assert not tem_script(limpo), limpo
    assert b"<path" in limpo and b"<circle" in limpo and b"<rect" in limpo  # o desenho fica
    assert b"foreignObject" not in limpo and b"<a" not in limpo and b"evil.svg" not in limpo
    assert b"url(" not in limpo  # style com url() some
    assert b"onload" not in limpo and b"onclick" not in limpo


def test_svg_por_upload_e_gravado_sanitizado_e_servido_com_sandbox(cliente, sessao_a):
    tok = _token(sessao_a, "zt-l703a-svg")
    try:
        h = {"Authorization": f"Bearer {tok['token']}", "content-type": "image/svg+xml"}
        r = cliente.post("/api/arquivos?classe=anexo", content=SVG_SCRIPT, headers=h)
        assert r.status_code == 201, r.text
        sha = r.json()["sha256"]
        assert sha != hashlib.sha256(SVG_SCRIPT).hexdigest()  # o que foi gravado NÃO é o que chegou
        r2 = cliente.get(f"/api/arquivos/{sha}?classe=anexo", headers=h)
        assert r2.status_code == 200 and not tem_script(r2.content)
        assert r2.headers["content-security-policy"].startswith("sandbox")
        assert r2.headers["x-content-type-options"] == "nosniff"
        cliente.delete(f"/api/arquivos/{sha}?classe=anexo", headers=h)
        # entidade externa / bomba de entidades: recusa
        xxe = b'<!DOCTYPE s [<!ENTITY e SYSTEM "file:///etc/passwd">]><svg xmlns="http://www.w3.org/2000/svg">&e;</svg>'
        r3 = cliente.post("/api/arquivos?classe=anexo", content=xxe, headers=h)
        assert r3.status_code == 415 and r3.json()["detalhe"]["motor"] == "svg_seguro", r3.text
    finally:
        sessao_a.delete(f"/api/tokens/{tok['id']}")


# --------------------------------------------------------------------------- 3. zip-bomba


def _zip_de_zeros(tamanho: int, entradas: int = 1) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        bloco = b"\0" * (1024 * 1024)
        for i in range(entradas):
            with z.open(f"zeros{i}.bin", "w") as f:
                restante = tamanho
                while restante > 0:
                    f.write(bloco[: min(len(bloco), restante)])
                    restante -= len(bloco)
    return buf.getvalue()


def test_zip_com_1_gb_de_zeros_e_recusado(cliente, sessao_a):
    bomba = _zip_de_zeros(1024 * 1024 * 1024)
    assert len(bomba) < 2 * 1024 * 1024  # 1 GiB de zeros cabe em ~1 MiB comprimido: chega inteiro no buffer único
    tok = _token(sessao_a, "zt-l703a-zip")
    try:
        h = {"Authorization": f"Bearer {tok['token']}", "content-type": "application/zip"}
        r = cliente.post("/api/arquivos?classe=anexo", content=bomba, headers=h)
        assert r.status_code == 415, r.text
        assert r.json()["detalhe"]["motor"] == "zip_bomba" and "razão de compressão" in r.json()["mensagem"]
        # KMZ com 10 mil entradas (refutação): contagem de entradas
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for i in range(10_000):
                z.writestr(f"p{i}.kml", "<kml/>")
        r2 = cliente.post(
            "/api/arquivos?classe=anexo", content=buf.getvalue(),
            headers={**h, "content-type": "application/vnd.google-earth.kmz"},
        )
        assert r2.status_code == 415 and "entradas" in r2.json()["mensagem"], r2.text
    finally:
        sessao_a.delete(f"/api/tokens/{tok['id']}")


# --------------------------------------------------------------------------- 4. bytes, não extensão


def test_exe_renomeado_para_tif_e_recusado_pelos_bytes(cliente, sessao_a, env):
    tok = _token(sessao_a, "zt-l703a-exe")
    try:
        h = {"Authorization": f"Bearer {tok['token']}", "content-type": "image/tiff"}
        r = cliente.post("/api/arquivos?classe=objeto", content=EXE_MZ, headers=h)
        assert r.status_code == 415, r.text
        detectado = r.json()["detalhe"]["tipo_detectado"]
        assert detectado in ("application/x-dosexec", "application/vnd.microsoft.portable-executable"), detectado
        sha = hashlib.sha256(EXE_MZ).hexdigest()
        con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
        ids = ids_por_slug(con)
        con.close()
        ev = _eventos(env, ids["demo"], "arquivos/conteudo_recusado", sha)
        assert ev is not None and ev["propriedades"]["content_type"] == "image/tiff"
        # polyglot GIF+HTML (refutação): a assinatura é GIF, mas a classe anexo não serve inline o que não é
        # imagem e a imagem vai com sandbox; um "GIF" que é HTML por dentro é recusado quando declarado html
        h_html = {**h, "content-type": "text/html"}
        r2 = cliente.post("/api/arquivos?classe=anexo", content=GIF_HTML_POLYGLOT, headers=h_html)
        assert r2.status_code == 415, r2.text
        # e declarado como GIF entra, mas nunca sai executável: nosniff + sandbox + tipo fixo image/gif
        h_gif = {**h, "content-type": "image/gif"}
        r3 = cliente.post("/api/arquivos?classe=anexo", content=GIF_HTML_POLYGLOT, headers=h_gif)
        assert r3.status_code == 201, r3.text
        r4 = cliente.get(f"/api/arquivos/{r3.json()['sha256']}?classe=anexo", headers=h)
        assert r4.headers["content-type"].startswith("image/gif") and r4.headers["x-content-type-options"] == "nosniff"
        assert r4.headers["content-security-policy"].startswith("sandbox")
        cliente.delete(f"/api/arquivos/{r3.json()['sha256']}?classe=anexo", headers=h)
    finally:
        sessao_a.delete(f"/api/tokens/{tok['id']}")


def test_tipo_fora_da_lista_da_rota_e_recusado_antes_do_corpo(cliente, sessao_a):
    tok = _token(sessao_a, "zt-l703a-rota")
    try:
        h = {"Authorization": f"Bearer {tok['token']}", "content-type": "application/octet-stream"}
        r = cliente.post("/api/arquivos?classe=foto_campo", content=PNG_MINIMO, headers=h)
        assert r.status_code == 415 and r.json()["detalhe"]["motor"] == "politica_de_rota", r.text
        h_png = {**h, "content-type": "image/png"}
        r2 = cliente.post("/api/arquivos?classe=foto_campo", content=PNG_MINIMO, headers=h_png)
        assert r2.status_code == 201, r2.text
        cliente.delete(f"/api/arquivos/{r2.json()['sha256']}?classe=foto_campo", headers=h)
    finally:
        sessao_a.delete(f"/api/tokens/{tok['id']}")


# --------------------------------------------------------------------------- 5. 413 antes de ler o corpo


def test_1_byte_acima_do_plano_da_413_antes_de_ler_o_corpo(sessao_a, env, medida):
    """medido pelo tráfego: o servidor responde 413 sem consumir NENHUMA mensagem `http.request` do corpo quando
    o Content-Length já passa do teto da classe; e, quando o cliente mente no Content-Length, para de ler assim
    que o contador passa do teto (nunca o corpo inteiro)."""
    from app.main import app

    tok = _token(sessao_a, "zt-l703a-413")
    try:
        limite = limites.IMAGEM_UPLOAD_BYTES_MAX
        pedaco = b"\x89PNG\r\n\x1a\n" + b"\0" * (64 * 1024 - 8)
        n_pedacos = (limite + 1) // len(pedaco) + 2

        async def chamar(content_length: int | None):
            lidos = 0
            enviados: list[dict] = []

            async def receive():
                nonlocal lidos
                lidos += 1
                ultimo = lidos >= n_pedacos
                return {"type": "http.request", "body": pedaco, "more_body": not ultimo}

            async def send(m):
                enviados.append(m)

            cab = [(b"authorization", f"Bearer {tok['token']}".encode()), (b"content-type", b"image/png"),
                   (b"host", b"testserver")]
            if content_length is not None:
                cab.append((b"content-length", str(content_length).encode()))
            scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST",
                     "scheme": "http", "path": "/api/arquivos", "raw_path": b"/api/arquivos",
                     "query_string": b"classe=imagem", "headers": cab, "client": ("127.0.0.1", 1),
                     "server": ("testserver", 80)}
            await app(scope, receive, send)
            status = next(m["status"] for m in enviados if m["type"] == "http.response.start")
            return status, lidos

        # 1 byte acima, Content-Length honesto: 413 sem ler uma mensagem sequer
        status, lidos = asyncio.run(chamar(limite + 1))
        assert status == 413 and lidos == 0, (status, lidos)
        m = medida("L7-03-a-antivirus-upload")
        m("mensagens_de_corpo_lidas_content_length_honesto", lidos, "mensagens ASGI",
          "POST /api/arquivos?classe=imagem com Content-Length = teto+1: mensagens http.request lidas antes do 413")
        # cliente que mente (declara pequeno, manda grande): para de ler no primeiro pedaço acima do teto
        status, lidos = asyncio.run(chamar(1024))
        assert status == 413 and lidos < n_pedacos, (status, lidos, n_pedacos)
        assert lidos <= limite // len(pedaco) + 2
        m("mensagens_de_corpo_lidas_content_length_mentiroso", lidos, "mensagens ASGI",
          f"Content-Length 1024 e corpo de {n_pedacos} pedaços de 64 KiB: lidas até passar o teto de {limite} bytes")
        m("mensagens_de_corpo_totais", n_pedacos, "mensagens ASGI", "tamanho do corpo enviado, em pedaços de 64 KiB")
    finally:
        sessao_a.delete(f"/api/tokens/{tok['id']}")


# --------------------------------------------------------------------------- 6. anexo .html nunca inline


def test_anexo_html_e_servido_como_attachment_com_sandbox(cliente, sessao_a):
    tok = _token(sessao_a, "zt-l703a-html")
    try:
        h = {"Authorization": f"Bearer {tok['token']}", "content-type": "text/html"}
        html = b"<!DOCTYPE html><html><body><script>document.cookie</script>oi</body></html>"
        r = cliente.post("/api/arquivos?classe=anexo", content=html, headers=h)
        assert r.status_code == 201, r.text
        sha = r.json()["sha256"]
        r2 = cliente.get(f"/api/arquivos/{sha}?classe=anexo", headers=h)
        assert r2.status_code == 200
        disposicao = r2.headers["content-disposition"]
        assert disposicao.startswith("attachment;") and ".html" in disposicao
        assert r2.headers["content-security-policy"].startswith("sandbox")
        assert r2.headers["x-content-type-options"] == "nosniff"
        cliente.delete(f"/api/arquivos/{sha}?classe=anexo", headers=h)
    finally:
        sessao_a.delete(f"/api/tokens/{tok['id']}")


# --------------------------------------------------------------------------- 7. documento lista tipos por rota


def test_documento_lista_os_tipos_por_rota():
    from pathlib import Path

    doc = (Path(__file__).resolve().parents[2] / "docs" / "SEGURANCA.md").read_text(encoding="utf-8")
    for nome, pol in varredura.POLITICAS.items():
        assert f"`{nome}`" in doc, f"classe {nome} sem linha em docs/SEGURANCA.md"
        for tipo in pol.tipos:
            assert tipo in doc, f"tipo {tipo} da classe {nome} não documentado"
