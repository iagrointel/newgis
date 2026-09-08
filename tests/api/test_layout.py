"""Item L2-12-b-layouts-elementos-exportacao — portão contra um `uvicorn app.main:app` REAL (o quadro de mapa é
desenhado por chromium de verdade navegando por HTTP até /render/layout-mapa; nada disso passa pelo TestClient).

Cláusulas provadas aqui:
* Export Web Map Task recebe o Web_Map_as_JSON de um mapa nosso e devolve PDF; Get Layout Templates Info lista os
  modelos;
* layout A3 paisagem com mapa + legenda + escala + norte + grade + título em PDF, conferido: ESCALA MEDIDA COM RÉGUA
  — dois pontos vermelhos a 1.000 m um do outro numa camada de prova, achados no PDF rasterizado pelo pdftoppm; a
  distância em mm entre eles × a escala pedida tem de dar 1.000 m a ≤ 1 %; legenda com a mesma cor do estilo
  (pixel do quadradinho); grade UTM com rótulos lidos no texto do PDF; título selecionável (pdftotext);
* `POST /api/layouts/exportar` cria o job `layout.exportar`; validação nomeada; prévia PNG; rota de estilo por token.
Números vão para tests/medidas/L2-12-b-layouts-elementos-exportacao.json com a carga da máquina ao lado.
Depende de PLAT_DSN (trilha) e, para a régua, do Martin em PLAT_MARTIN_URL; sem eles, SALTA com a razão."""

from __future__ import annotations

import importlib.util
import json
import math
import os
import re
import secrets
import shutil
import subprocess
import time
from pathlib import Path

import httpx
import pytest

from tests.e2e.apoio import credenciais
from tests.render_apoio import derrubar_servidor, porta_livre, subir_servidor

pytestmark = pytest.mark.lento
RAIZ = Path(__file__).resolve().parents[2]
MEDIDAS = RAIZ / "tests" / "medidas" / "L2-12-b-layouts-elementos-exportacao.json"
ITEM = "L2-12-b-layouts-elementos-exportacao"
LAT = -23.46
LON0 = -46.53
DIST_M = 1000.0
ESCALA = 20000
DPI = 150


def _gravar(nome: str, valor, unidade: str, como: str) -> None:
    dados = json.loads(MEDIDAS.read_text(encoding="utf-8")) if MEDIDAS.exists() else {"item": ITEM, "medidas": {}}
    carga = os.getloadavg()[0]
    livre = None
    try:
        for linha in Path("/proc/meminfo").read_text().splitlines():
            if linha.startswith("MemAvailable"):
                livre = round(int(linha.split()[1]) / 1024 / 1024, 1)
    except OSError:
        pass
    dados["medidas"][nome] = {
        "valor": valor,
        "unidade": unidade,
        "como": como,
        "carga_1min": round(carga, 2),
        "ram_livre_gb": livre,
        "medido_em": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    MEDIDAS.parent.mkdir(parents=True, exist_ok=True)
    MEDIDAS.write_text(json.dumps(dados, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


@pytest.fixture(scope="module")
def servidor():
    if not os.environ.get("PLAT_DSN"):
        pytest.skip("sem PLAT_DSN no ambiente (rode com o .env da trilha carregado)")
    porta = porta_livre()
    os.environ["PLAT_RENDER_BASE_URL"] = f"http://127.0.0.1:{porta}"
    proc, base_url = subir_servidor(porta)
    yield base_url
    derrubar_servidor(proc)


@pytest.fixture(scope="module")
def sessao(servidor):
    creds = credenciais()
    if "demo" not in creds:
        pytest.skip("sem credencial do inquilino demo")
    login, senha = creds["demo"]
    cli = httpx.Client(base_url=servidor, timeout=180)
    r = cli.post("/api/login", json={"inquilino": "demo", "login": login, "senha": senha})
    assert r.status_code == 200 and r.json().get("ok") is True, r.text
    yield cli
    cli.post("/api/logout", json={})
    cli.close()


def _script_demo():
    caminho = RAIZ / "scripts" / "selecao_demo_camadas.py"
    spec = importlib.util.spec_from_file_location("selecao_demo_camadas", caminho)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def camada_prova(servidor):
    """Camada hospedada com DOIS pontos vermelhos a 1.000 m um do outro na latitude LAT (a régua do portão)."""
    import psycopg2
    import psycopg2.extras

    mod = _script_demo()
    dlon = DIST_M / (111320.0 * math.cos(math.radians(LAT)))
    p1, p2 = (LON0, LAT), (LON0 + dlon, LAT)
    tabela = "c_" + secrets.token_hex(8)
    con = psycopg2.connect(os.environ["PLAT_DSN"])
    try:
        with con.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            adm = mod._contexto(cur, "demo")
            cur.execute(
                f'CREATE TABLE "d_demo"."{tabela}" (fid bigserial PRIMARY KEY, nome text, geom geometry(Point, 4326))'
            )
            cur.execute(
                f'INSERT INTO "d_demo"."{tabela}" (nome, geom) VALUES '
                f"('oeste', ST_SetSRID(ST_MakePoint(%s, %s), 4326)), ('leste', ST_SetSRID(ST_MakePoint(%s, %s), 4326))",
                (p1[0], p1[1], p2[0], p2[1]),
            )
            cur.execute(f'CREATE INDEX ON "d_demo"."{tabela}" USING gist(geom)')
            saida = mod._publicar(
                cur, adm, "layout-regua (L2-12-b, sintética)", tabela, "Point", [{"nome": "nome", "tipo": "text"}]
            )
            cur.execute(
                "UPDATE plat.item SET dados = dados || %s::jsonb WHERE id = %s::uuid",
                (json.dumps({"simbologia": {"tipo": "simples", "cor": "#ff0000", "tamanho": 9}}), saida["item"]),
            )
        con.commit()
        yield {"item": saida["item"], "tabela": tabela, "p1": p1, "p2": p2}
    finally:
        try:
            with con.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                mod._contexto(cur, "demo")
                cur.execute("DELETE FROM plat.item WHERE id = %s::uuid", (saida["item"],))
                cur.execute(f'DROP TABLE IF EXISTS "d_demo"."{tabela}" CASCADE')
            con.commit()
        finally:
            con.close()


def _martin_no_ar() -> bool:
    url = (os.environ.get("PLAT_MARTIN_URL") or "http://127.0.0.1:8151").rstrip("/")
    try:
        return httpx.get(f"{url}/catalog", timeout=5).status_code == 200
    except httpx.HTTPError:
        return False


# ---------------------------------------------------------------- modelos, validação, prévia, job
def test_modelos_validacao_nomeada_e_previa_png(sessao):
    r = sessao.get("/api/layouts/modelos")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert {m["id"] for m in corpo["padrao"]} >= {"a4-retrato-simples", "a4-paisagem-legenda", "a3-paisagem-completo"}
    assert corpo["dimensoes_mm"]["A3"] == [297.0, 420.0] and corpo["dpi"] == {"min": 72, "max": 300}
    r = sessao.get("/api/layouts/modelos/a3-paisagem-completo")
    assert r.status_code == 200 and r.json()["papel"] == "A3"
    r = sessao.post("/api/layouts/validar", json={"layout": {"papel": "A9", "elementos": []}})
    assert r.status_code == 422 and r.json()["erro"] == "layout_invalido" and r.json()["detalhe"]["campo"] == "papel"
    modelo = sessao.get("/api/layouts/modelos/a4-paisagem-legenda").json()
    modelo["nome"] = "prévia"
    r = sessao.post(
        "/api/layouts/previa",
        json={
            "layout": modelo,
            "mapa": {"titulo": "Prévia", "camadas": [], "extensao": [-46.6, -23.5, -46.4, -23.4]},
            "dpi": 36,
        },
    )
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/png"), r.text[:300]
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
    relatorio = json.loads(r.headers["x-layout-relatorio"])
    assert relatorio["papel"] == "A4" and "mapa" in relatorio["escala"]


def test_exportar_cria_job_layout_exportar(sessao):
    modelo = sessao.get("/api/layouts/modelos/a4-retrato-simples").json()
    r = sessao.post(
        "/api/layouts/exportar",
        json={
            "layout": modelo,
            "mapa": {"titulo": "Job", "camadas": [], "extensao": [-46.6, -23.5, -46.4, -23.4]},
            "formato": "pdf",
            "dpi": 96,
        },
    )
    assert r.status_code == 201, r.text
    job = r.json()["job"]
    assert job["tipo"] == "layout.exportar" and job["estado"] in ("pendente", "rodando")
    r = sessao.get(f"/api/jobs/{job['id']}")
    assert r.status_code == 200 and r.json()["parametros"]["formato"] == "pdf"
    sessao.post(f"/api/jobs/{job['id']}/cancelar", json={})


def test_estilo_por_token_interno(servidor, sessao, camada_prova):
    from app.layout import estilo_render

    r = httpx.get(f"{servidor}/api/render/layout/estilo", params={"token": "x.y.z.w"}, timeout=30)
    assert r.status_code == 401
    eu = sessao.get("/api/eu").json()
    payload = {
        "t": eu["inquilino"]["id"],
        "u": eu["id"],
        "b": "osm-guarulhos",
        "c": [{"camada_id": camada_prova["item"], "opacidade": 1.0, "visivel": True}],
    }
    tok = estilo_render.gerar_token(payload)
    r = httpx.get(f"{servidor}/api/render/layout/estilo", params={"token": tok}, timeout=30)
    assert r.status_code == 200, r.text
    est = r.json()
    fonte = f"plat-{camada_prova['item']}"
    assert fonte in est["fontes"] and "token=" in est["fontes"][fonte]["tiles"][0]
    assert any(c.get("source") == fonte for c in est["camadas"])
    assert any(c.get("paint", {}).get("circle-color") == "#ff0000" for c in est["camadas"])


# ---------------------------------------------------------------- Esri e régua
def test_get_layout_templates_info(sessao):
    r = sessao.get("/rest/services/Impressao/GPServer/Get Layout Templates Info Task/execute", params={"f": "json"})
    assert r.status_code == 200, r.text
    lista = r.json()["results"][0]["value"]
    assert len(lista) >= 3 and all("layoutTemplate" in m and "pageSize" in m for m in lista)
    a3 = next(m for m in lista if m["layoutTemplate"] == "a3-paisagem-completo")
    assert a3["pageSize"] == [16.54, 11.69] and a3["layoutOptions"]["hasLegend"] is True
    r = sessao.get("/rest/services/Impressao/GPServer", params={"f": "json"})
    assert r.status_code == 200 and "Export Web Map Task" in r.json()["tasks"]


@pytest.mark.skipif(shutil.which("pdftoppm") is None or shutil.which("pdftotext") is None, reason="poppler ausente")
def test_export_web_map_pdf_escala_com_regua_legenda_grade_e_texto(servidor, sessao, camada_prova, tmp_path):
    if not _martin_no_ar():
        pytest.skip("Martin fora do ar em PLAT_MARTIN_URL: sem tiles não há pontos para medir")
    from PIL import Image

    p1, p2 = camada_prova["p1"], camada_prova["p2"]
    centro = ((p1[0] + p2[0]) / 2, LAT)
    meia = 0.03
    web_map = {
        "mapOptions": {
            "extent": {
                "xmin": centro[0] - meia,
                "ymin": LAT - meia,
                "xmax": centro[0] + meia,
                "ymax": LAT + meia,
                "spatialReference": {"wkid": 4326},
            },
            "scale": ESCALA,
        },
        "operationalLayers": [
            {
                "id": "regua",
                "title": "layout-regua",
                "opacity": 1,
                "visibility": True,
                "url": f"{servidor}/tiles/d_demo/t_{camada_prova['tabela'][2:]}/{{z}}/{{x}}/{{y}}",
            },
            {
                "id": "externa",
                "title": "Living Atlas de exemplo",
                "layerType": "ArcGISTiledMapServiceLayer",
                "url": "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer",
            },
        ],
        "baseMap": {"title": "Topographic", "baseMapLayers": [{"url": "https://exemplo.invalido/basemap"}]},
        "exportOptions": {"dpi": DPI, "outputSize": [1000, 800]},
        "layoutOptions": {
            "titleText": "Prova de impressao do plat",
            "authorText": "Testador",
            "copyrightText": "dado sintético",
            "scaleBarOptions": {"metricUnit": "esriMeters"},
        },
    }
    inicio = time.perf_counter()
    r = sessao.post(
        "/rest/services/Impressao/GPServer/Export Web Map Task/execute",
        data={
            "f": "json",
            "Format": "PDF",
            "Layout_Template": "a3-paisagem-completo",
            "Web_Map_as_JSON": json.dumps(web_map),
        },
    )
    ms = round((time.perf_counter() - inicio) * 1000)
    assert r.status_code == 200, r.text[:500]
    corpo = r.json()
    assert "error" not in corpo, corpo
    url = corpo["results"][0]["value"]["url"]
    avisos = [m["description"] for m in corpo.get("messages", [])]
    assert any("Living Atlas" in a and "fora" in a for a in avisos), (
        avisos
    )  # camada externa: declarada fora, nunca copiada
    assert any("baseMap" in a for a in avisos)
    pdf = sessao.get(url)
    assert pdf.status_code == 200 and pdf.content[:5] == b"%PDF-", pdf.status_code
    arq = tmp_path / "impressao.pdf"
    arq.write_bytes(pdf.content)
    _gravar(
        "export_web_map_task_ms",
        ms,
        "ms",
        f"POST execute A3 {DPI} DPI com 1 camada nossa + motor de render, servidor uvicorn real",
    )

    # texto selecionável e grade UTM lida do PDF
    texto = subprocess.run(["pdftotext", str(arq), "-"], capture_output=True, text=True, timeout=60).stdout
    assert "Prova de impressao do plat" in texto
    assert "Testador" in texto and "dado sintético" in texto
    assert f"Escala 1:{ESCALA:,}".replace(",", ".") in texto
    rotulos_e = re.findall(r"\b(\d{6}) E\b", texto)
    rotulos_n = re.findall(r"\b(\d{7}) N\b", texto)
    assert len(rotulos_e) >= 2 and len(rotulos_n) >= 2, texto[:600]
    # os rótulos são coordenadas UTM verossímeis do fuso 23S para este centro
    from pyproj import Transformer

    tr = Transformer.from_crs("EPSG:4326", "EPSG:32723", always_xy=True)
    e_c, n_c = tr.transform(*centro)
    assert all(abs(int(v) - e_c) < 10000 for v in rotulos_e) and all(abs(int(v) - n_c) < 10000 for v in rotulos_n)

    # régua: pdftoppm no DPI da exportação; dois grupos de pixels vermelhos = os dois pontos da camada
    subprocess.run(
        ["pdftoppm", "-png", "-r", str(DPI), "-singlefile", str(arq), str(tmp_path / "pagina")], check=True, timeout=120
    )
    img = Image.open(tmp_path / "pagina.png").convert("RGB")
    w, h = img.size
    px = img.load()
    vermelhos = []
    for y in range(0, h, 1):
        for x in range(0, w, 1):
            r_, g_, b_ = px[x, y]
            if r_ > 170 and g_ < 90 and b_ < 90:
                vermelhos.append((x, y))
    assert len(vermelhos) >= 20, f"poucos pixels vermelhos ({len(vermelhos)}): os pontos não apareceram no quadro"
    # a legenda tem um quadradinho vermelho: separa pelo quadro (x até ~315 mm) e por metade esquerda/direita
    mm_por_px = 25.4 / DPI
    no_quadro = [(x, y) for x, y in vermelhos if 15 < x * mm_por_px < 315 and 28 < y * mm_por_px < 268]
    assert len(no_quadro) >= 20, "os pontos não estão dentro do quadro"
    xs = sorted(x for x, _ in no_quadro)
    corte = (xs[0] + xs[-1]) / 2
    esq = [(x, y) for x, y in no_quadro if x < corte]
    dir_ = [(x, y) for x, y in no_quadro if x >= corte]
    assert esq and dir_, "só um ponto encontrado"
    cx1 = sum(x for x, _ in esq) / len(esq)
    cx2 = sum(x for x, _ in dir_) / len(dir_)
    cy1 = sum(y for _, y in esq) / len(esq)
    cy2 = sum(y for _, y in dir_) / len(dir_)
    dist_px = math.hypot(cx2 - cx1, cy2 - cy1)
    dist_mm = dist_px * mm_por_px
    escala_medida = DIST_M * 1000.0 / dist_mm
    erro = abs(escala_medida - ESCALA) / ESCALA
    _gravar(
        "escala_medida_regua",
        round(escala_medida, 1),
        "1:N",
        f"{dist_mm:.2f} mm entre dois pontos a {DIST_M:.0f} m no PDF a {DPI} DPI (pdftoppm)",
    )
    _gravar("escala_erro_relativo", round(erro * 100, 3), "%", "|medida − pedida| / pedida; portão ≤ 1 %")
    assert erro <= 0.01, f"escala medida 1:{escala_medida:.0f} contra 1:{ESCALA} pedida ({erro * 100:.2f} %)"
    # legenda: o quadradinho da classe única tem a cor do estilo (#ff0000) — amostra no centro do quadradinho
    # (legenda em x=325, y=28 mm; título ocupa 7 mm; quadradinho em (x, y+1) com 6 × 3 mm)
    sx, sy = int((325 + 3) / mm_por_px), int((28 + 7 + 1 + 1.5) / mm_por_px)
    amostra = px[sx, sy]
    assert amostra[0] > 200 and amostra[1] < 80 and amostra[2] < 80, f"cor da legenda {amostra} != vermelho do estilo"
    _gravar(
        "legenda_cor_amostrada",
        list(amostra),
        "rgb",
        "pixel do quadradinho da legenda no PDF rasterizado vs #ff0000 do estilo",
    )
