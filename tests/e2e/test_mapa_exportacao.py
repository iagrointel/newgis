"""Portão do item L2-01-l-exportacao-do-mapa, cláusula "exportar O MAPA": o ARQUIVO gerado é conferido,
não a lista de formatos nem o diálogo.

O que o tronco já tem medido em outro lugar (não se repete aqui): a exportação de FEIÇÕES da seleção
nos 12 formatos, o PNG com legenda e atribuição e o botão Exportar estão em
`tests/e2e/test_exportar_mapa.py`; a impressão PNG/PDF do canvas está em
`tests/e2e/test_mapa_web.py::test_impressao_png_e_pdf_com_escala_e_norte`; o diálogo do painel Layout
(prévia, gravar, enfileirar) está em `tests/e2e/test_l212b_layout_dialogo.py`.

O que faltava e este arquivo mede, pela tela: a saída POR LAYOUT é um arquivo com a GEOMETRIA pedida e
com o CONTEÚDO pedido dentro.

  * PNG por layout: a prévia sai no tamanho em pixels que o papel e o DPI escolhidos determinam
    (A4 retrato a 96 dpi = 794 x 1123 px, com 2 px de folga de arredondamento), e o título digitado
    aparece como TINTA — o par é a mesma prévia sem o título, que tem de dar bytes diferentes; sem esse
    par, uma folha em branco do tamanho certo passaria;
  * PDF por layout: o job é disparado pela tela e, quando há worker nesta trilha, o arquivo baixado é
    aberto por um leitor independente (`pdftoppm` do Poppler) e tem de ter 1 página com desenho e o
    título no texto (`pdftotext`). Sem worker o teste diz isso e SALTA essa metade — nunca a finge;
  * recusa com par positivo: layout com elemento fora do papel não gera arquivo (422 nomeado), e o
    mesmo layout corrigido gera.

Como rodar contra uma trilha (nunca contra plat.iagrointel.com, que é produção):

    set -a; source /home/dev/plataforma/laco/var/trilha/<trilha>.env; set +a
    venv/bin/python -m uvicorn tests.e2e.frente_estatica:app --port <porta>
    venv/bin/python -m app.jobs.worker &     # opcional: sem ele a metade do PDF salta
    venv/bin/pytest tests/e2e/test_mapa_exportacao.py -m lento --base-url http://127.0.0.1:<porta>
"""

from __future__ import annotations

import io
import subprocess
import time

import pytest
from PIL import Image

from tests.e2e.apoio import CAPTURAS, Tela, sufixo

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "L2-01-l-exportacao-do-mapa"
# A4 retrato a 96 dpi: 210 mm / 25,4 * 96 = 793,7 px; 297 mm = 1122,5 px
A4_96DPI = (794, 1123)
FOLGA_PX = 2


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Numa BASE DE TRILHA o servidor sobe com certificado próprio: a plataforma exige `PLAT_URL_PUBLICA`
    em https (e o CSP manda `upgrade-insecure-requests`, que aborta todo fetch em http). Só o certificado
    é ignorado; nenhuma outra checagem é afrouxada."""
    return {**browser_context_args, "ignore_https_errors": True}


@pytest.fixture
def mapa(page, base_url, credenciais_demo, api_auth):
    if "/api/layouts/previa" not in api_auth:
        pytest.skip("backend sem /api/layouts/previa no OpenAPI da URL de teste")
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url, ITEM)
    tela.entrar(slug, login, senha)
    tela.ir("/mapa")
    page.wait_for_selector("#mapa canvas.maplibregl-canvas", timeout=20000)
    return tela


def _layout_a4(titulo: str, x_titulo: float = 20.0) -> dict:
    return {
        "nome": titulo,
        "papel": "A4",
        "orientacao": "retrato",
        "elementos": [
            {"tipo": "mapa", "id": "mapa", "x": 10, "y": 40, "w": 190, "h": 200,
             "modo": "extensao", "extensao": [-46.75, -23.65, -46.35, -23.35]},
            {"tipo": "titulo", "id": "titulo", "x": x_titulo, "y": 10, "w": 170, "h": 20, "texto": titulo},
        ],
    }


def _previa(tela: Tela, layout: dict, dpi: int = 96):
    return tela.api("POST", "/api/layouts/previa", {"layout": layout, "dpi": dpi})


def test_png_por_layout_sai_no_tamanho_do_papel_e_com_o_titulo_dentro(mapa, page, medida):
    s = sufixo()
    titulo = f"Mapa de portao {s}"

    r = _previa(mapa, _layout_a4(titulo))
    assert r.status == 200, (r.status, r.text()[:300])
    bytes_com_titulo = r.body()
    assert bytes_com_titulo[:4] == b"\x89PNG", bytes_com_titulo[:16]

    with Image.open(io.BytesIO(bytes_com_titulo)) as im:
        largura, altura = im.size
        cores = len(im.convert("RGB").getcolors(maxcolors=4_000_000) or [])
    assert abs(largura - A4_96DPI[0]) <= FOLGA_PX and abs(altura - A4_96DPI[1]) <= FOLGA_PX, (
        f"A4 retrato a 96 dpi deveria dar {A4_96DPI} px, veio {(largura, altura)}"
    )
    assert cores > 2, f"a folha saiu praticamente vazia ({cores} cores distintas)"

    # par: o MESMO layout sem o título tem de dar bytes diferentes (senão o título não virou tinta)
    sem_titulo = _layout_a4(titulo)
    sem_titulo["elementos"] = [e for e in sem_titulo["elementos"] if e["tipo"] != "titulo"]
    r2 = _previa(mapa, sem_titulo)
    assert r2.status == 200, (r2.status, r2.text()[:300])
    assert r2.body() != bytes_com_titulo, "tirar o título do layout não mudou um byte da imagem"

    CAPTURAS.mkdir(parents=True, exist_ok=True)
    destino = CAPTURAS / f"{ITEM}_previa_a4.png"
    destino.write_bytes(bytes_com_titulo)
    gravar = medida(ITEM)
    gravar("previa_layout_a4_96dpi_px", f"{largura}x{altura}", "px",
           "tests/e2e/test_mapa_exportacao.py::test_png_por_layout_sai_no_tamanho_do_papel_e_com_o_titulo_dentro")
    gravar("previa_layout_a4_96dpi_bytes", len(bytes_com_titulo), "bytes", "POST /api/layouts/previa pela tela")
    mapa.verificar()


def test_layout_com_elemento_fora_do_papel_nao_gera_arquivo(mapa):
    """Par positivo/negativo da recusa: fora do papel = 422 nomeado e NENHUM arquivo; dentro = PNG."""
    s = sufixo()
    mapa.esperar_status(422)
    ruim = _previa(mapa, _layout_a4(f"fora {s}", x_titulo=900.0))
    assert ruim.status == 422, (ruim.status, ruim.text()[:300])
    corpo = ruim.json()
    assert "elemento" in (corpo.get("erro", "") + str(corpo.get("detalhe", ""))).lower(), corpo

    bom = _previa(mapa, _layout_a4(f"dentro {s}"))
    assert bom.status == 200 and bom.body()[:4] == b"\x89PNG"


def test_pdf_por_layout_e_um_pdf_de_verdade_com_o_titulo(mapa, page, tmp_path, medida):
    s = sufixo()
    titulo = f"PDF de portao {s}"
    r = mapa.api("POST", "/api/layouts/exportar",
                 {"layout": _layout_a4(titulo), "formato": "pdf", "dpi": 96, "nome": titulo})
    assert r.status == 201, (r.status, r.text()[:300])
    corpo = r.json()
    job_id = corpo["job"]["id"]
    assert corpo["formato"] == "pdf"

    try:
        estado, saida = None, None
        limite = time.monotonic() + 180
        while time.monotonic() < limite:
            job = mapa.api("GET", f"/api/jobs/{job_id}").json()
            estado = job["estado"]
            if estado in ("concluido", "falhou"):
                saida = job.get("resultado") or {}
                break
            time.sleep(3)
        if estado in ("pendente", "rodando", None):
            pytest.skip(f"sem worker nesta trilha: o job de exportação ficou em '{estado}' "
                        f"(rode venv/bin/python -m app.jobs.worker para medir esta metade)")
        assert estado == "concluido", (estado, saida)

        link = saida.get("url") or saida.get("link") or saida.get("arquivo_url")
        assert link, f"job concluído sem endereço do arquivo no resultado: {saida}"
        baixado = mapa.api("GET", link)
        assert baixado.status == 200, baixado.status
        pdf = tmp_path / "layout.pdf"
        pdf.write_bytes(baixado.body())
        assert pdf.read_bytes()[:5] == b"%PDF-", "o arquivo entregue não é PDF"

        proc = subprocess.run(["pdftoppm", "-png", "-r", "60", str(pdf), str(tmp_path / "pagina")],
                              capture_output=True, text=True, timeout=120)
        assert proc.returncode == 0, proc.stderr
        paginas = sorted(tmp_path.glob("pagina*.png"))
        assert len(paginas) == 1, paginas
        with Image.open(paginas[0]) as im:
            cores = len(im.convert("RGB").getcolors(maxcolors=4_000_000) or [])
        assert cores > 2, f"a página do PDF saiu em branco ({cores} cores)"
        texto = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True,
                               timeout=60).stdout
        assert s in texto, texto[:300]

        gravar = medida(ITEM)
        gravar("pdf_por_layout_bytes", pdf.stat().st_size, "bytes",
               "tests/e2e/test_mapa_exportacao.py::test_pdf_por_layout_e_um_pdf_de_verdade_com_o_titulo")
        gravar("pdf_por_layout_paginas", len(paginas), "páginas", "pdftoppm -png -r 60 sobre o PDF gerado")
    finally:
        mapa.api("POST", f"/api/jobs/{job_id}/cancelar")
