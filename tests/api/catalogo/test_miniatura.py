"""Miniaturas (L0-03-g; ADR 0004 seção 11): JPEG → PNG 600×400 (dimensões lidas de volta), ETag/304; 11 MB 413;
SVG 415; PNG de 20.000×20.000 declarado no cabeçalho → 422 sem decodificar (RSS < +100 MB); EXIF descartado;
POST de quem não edita → 403/404; DELETE limpa; job catalogo.miniatura de camada semeada ≤ 30 s (medida
miniatura_job_s); tipo sem gerador 409; adaptador de objetos grava/lê/apaga e a URL assinada expira."""

import base64
import io
import resource
import struct
import time
import zlib

import pytest
from PIL import Image

from tests.api.catalogo.conftest import esperar_job, titulo_zt
from tests.api.test_rls import contexto, ids_por_slug

ITEM = "L0-03-catalogo"


def _b64(dados: bytes) -> str:
    return base64.b64encode(dados).decode()


def _jpeg(largura=900, altura=500, exif=False) -> bytes:
    im = Image.new("RGB", (largura, altura), (200, 30, 30))
    buf = io.BytesIO()
    if exif:
        ex = Image.Exif()
        ex[0x010E] = "<script>alert(1)</script>"  # ImageDescription
        im.save(buf, format="JPEG", exif=ex.tobytes())
    else:
        im.save(buf, format="JPEG")
    return buf.getvalue()


def _png_bomba(largura=20_000, altura=20_000) -> bytes:
    """PNG válido no cabeçalho (IHDR declara 20.000 × 20.000) com IDAT mínimo: Pillow lê o tamanho sem decodificar."""

    def chunk(tipo: bytes, dados: bytes) -> bytes:
        return struct.pack(">I", len(dados)) + tipo + dados + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", largura, altura, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00" * 10)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def test_envio_normaliza_e_entrega_com_etag(sessao_a, itens_a):
    it = itens_a.criar("mapa")
    iid = it["id"]
    assert sessao_a.get(f"/api/itens/{iid}/miniatura").status_code == 204
    r = sessao_a.post(f"/api/itens/{iid}/miniatura", json={"conteudo": _b64(_jpeg(exif=True))})
    assert r.status_code == 200, r.text
    sha = r.json()["sha256"]
    r = sessao_a.get(f"/api/itens/{iid}/miniatura")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png" and r.headers["etag"] == f'"{sha}"'
    im = Image.open(io.BytesIO(r.content))
    assert im.size == (600, 400) and im.format == "PNG"
    assert not im.info.get("exif") and "script" not in r.content.decode("latin-1")
    assert sessao_a.get(f"/api/itens/{iid}/miniatura", headers={"If-None-Match": f'"{sha}"'}).status_code == 304
    j = sessao_a.get(f"/api/itens/{iid}").json()
    assert j["miniatura"] == f"/api/itens/{iid}/miniatura" and j["miniatura_sha256"] == sha and j["versao_atual"] == 1
    assert j["pontuacao"] == it["pontuacao"] + 1
    assert sessao_a.delete(f"/api/itens/{iid}/miniatura").status_code == 204
    assert sessao_a.get(f"/api/itens/{iid}/miniatura").status_code == 204


def test_recusas_de_tamanho_formato_e_bomba(sessao_a, itens_a):
    it = itens_a.criar("mapa")
    iid = it["id"]
    r = sessao_a.post(
        f"/api/itens/{iid}/miniatura", json={"conteudo": _b64(b"<svg xmlns='http://www.w3.org/2000/svg'/>")}
    )
    assert r.status_code == 415 and r.json()["erro"] == "formato_nao_aceito"
    grande = _b64(b"\xff\xd8" + b"\x00" * (11 * 1024 * 1024))
    r = sessao_a.post(f"/api/itens/{iid}/miniatura", json={"conteudo": grande})
    assert r.status_code in (413, 422), r.status_code
    if r.status_code == 422:
        assert r.json()["erro"] == "validacao"  # o próprio modelo corta acima do máximo em base64
    antes = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    r = sessao_a.post(f"/api/itens/{iid}/miniatura", json={"conteudo": _b64(_png_bomba())})
    depois = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    assert r.status_code == 422 and r.json()["erro"] == "imagem_grande", r.text
    assert r.json()["detalhe"]["maximo_px"] == 25_000_000
    assert (depois - antes) / 1024 < 100, "a bomba não pode alocar (RSS + MB)"
    r = sessao_a.post(f"/api/itens/{iid}/miniatura", json={"conteudo": "não é base64!"})
    assert r.status_code == 422


def test_quem_nao_edita_nao_envia(sessao_a, itens_a, editor_a):
    it = itens_a.criar("mapa")
    c, _ = editor_a
    assert c.post(f"/api/itens/{it['id']}/miniatura", json={"conteudo": _b64(_jpeg())}).status_code == 404
    sessao_a.put(f"/api/itens/{it['id']}/compartilhamento", json={"acesso": "inquilino"})
    r = c.post(f"/api/itens/{it['id']}/miniatura", json={"conteudo": _b64(_jpeg())})
    assert r.status_code == 403 and r.json()["erro"] == "sem_edicao_no_item"
    assert c.get(f"/api/itens/{it['id']}/miniatura").status_code == 204


def test_job_de_camada_semeada(sessao_a, itens_a, conexao_plat_app, medida, worker_vivo):
    ids = ids_por_slug(conexao_plat_app)
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT usuario_id FROM plat.auth_login('demo', 'admin')")
        adm = cur.fetchone()["usuario_id"]
    contexto(conexao_plat_app, ids["demo"], usuario_id=adm, login="admin")
    tabela = "zt_mini_" + titulo_zt()[-6:]
    with conexao_plat_app.cursor() as cur:
        cur.execute(f"CREATE TABLE plat_trabalho.{tabela} (id serial PRIMARY KEY, geom geometry(Polygon, 4326))")
        cur.execute(
            f"INSERT INTO plat_trabalho.{tabela}(geom) SELECT "
            "ST_Buffer(ST_SetSRID(ST_MakePoint(-47.9 + g * 0.1, -15.8), 4326), 0.03) "
            "FROM generate_series(1, 30) g"
        )
    conexao_plat_app.commit()
    it = itens_a.criar(
        "camada_vetorial",
        dados={
            "schema": "plat_trabalho",
            "tabela": tabela,
            "geometria": "Polygon",
            "srid": 4326,
            "campos": [{"nome": "id", "tipo": "integer"}],
            "fonte": "hospedada",
        },
    )
    t0 = time.perf_counter()
    r = sessao_a.post(f"/api/itens/{it['id']}/miniatura/gerar")
    assert r.status_code == 202, r.text
    job = esperar_job(sessao_a, r.json()["job_id"], 60)
    dt = time.perf_counter() - t0
    assert job["estado"] == "concluido", job
    medida(ITEM)(
        "miniatura_job_s", round(dt, 2), "s", "POST /api/itens/{id}/miniatura/gerar até job concluido (30 polígonos)"
    )
    assert dt <= 30
    r = sessao_a.get(f"/api/itens/{it['id']}/miniatura")
    assert r.status_code == 200
    im = Image.open(io.BytesIO(r.content)).convert("RGB")
    assert im.size == (600, 400) and im.getpixel((300, 200)) != (245, 246, 248)  # há desenho no centro
    mapa = itens_a.criar("mapa")
    r = sessao_a.post(f"/api/itens/{mapa['id']}/miniatura/gerar")
    assert r.status_code == 409 and r.json()["erro"] == "tipo_sem_gerador"
    with conexao_plat_app.cursor() as cur:
        cur.execute(f"DROP TABLE plat_trabalho.{tabela}")
    conexao_plat_app.commit()


def test_adaptador_de_objetos_e_url_assinada(cliente, tmp_path, monkeypatch):
    from app import objetos

    monkeypatch.setenv("PLAT_DADOS_DIR", str(tmp_path))
    iid = "00000000-0000-0000-0000-000000000001"
    o = objetos.guardar("miniatura", iid, b"abc", "image/png")
    assert o["chave"].startswith(f"miniatura/{iid}/") and o["bytes"] == 3 and objetos.ler(o["chave"]) == b"abc"
    assert objetos.guardar("miniatura", iid, b"abc", "image/png") == o  # mesma chave = mesmo conteúdo, não regrava
    url = objetos.url_assinada(o["chave"], 60)
    assert url.startswith(f"/api/objetos/{o['chave']}?ate=")
    r = cliente.get(url)
    assert r.status_code == 200 and r.content == b"abc" and r.headers["content-type"] == "image/png"
    assert cliente.get(url.replace("assinatura=", "assinatura=0")).status_code == 404
    vencida = objetos.url_assinada(o["chave"], -100)
    assert cliente.get(vencida).status_code == 404
    with pytest.raises(objetos.ChaveInvalida):
        objetos.ler("../../etc/passwd")
    assert cliente.get("/api/objetos/../../etc/passwd?ate=1&assinatura=x").status_code in (404, 422)
    assert objetos.apagar(o["chave"]) is True and objetos.apagar(o["chave"]) is False
