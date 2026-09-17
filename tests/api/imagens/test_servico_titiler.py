"""Portão do item L1-02-a (serviço TiTiler por inquilino), cláusula por cláusula, e a refutação.

O que se mede aqui, em processo, contra a aplicação `app.imagens.servico_titiler`:
  - `/svc/<token>/raster/<item>/info` e `/tiles/WebMercatorQuad/{z}/{x}/{y}.png` respondem para um
    item do inquilino do token, sobre um COG de verdade (o mesmo apoio do L1-02-tiles-token);
  - nenhum parâmetro de consulta vira endereço de leitura: `?url=`, `file:///etc/passwd`,
    `s3://outro-balde/` e `http://169.254.169.254/` devolvem 400, inclusive quando vêm por
    `expression`, `colormap`, `assets` ou por parâmetro que o TiTiler nem conhece;
  - item de OUTRO inquilino devolve 403 (nunca 404, nunca imagem);
  - uma única grade (`WebMercatorQuad`) e o tamanho/tempo do documento de capacidades com uma grade;
  - `Server-Timing` e `X-Robots-Tag: noindex` em toda resposta;
  - toda rota montada aparece no OpenAPI publicado (rota não documentada = refutação do item).

O que NÃO cabe aqui: `systemctl is-active plat-titiler`. Ativar unidade é ato de instalação em
produção, fora do alcance de uma trilha; o que se verifica é o arquivo de unidade entregue em
`deploy/plat-titiler.service` (aceito pelo `systemd-analyze verify`) e o passo do `install.sh` que o
instala. A cláusula fica registrada como pendente na medida do item.
"""

from __future__ import annotations

import json
import os
import shutil
import statistics
import subprocess
import time
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
ITEM = "L1-02-a-servico-titiler-por-inquilino"
Z, X, Y = 12, 1503, 2230  # ladrilho que cobre o raster sintético de teste (Brasília)
GRADE = "WebMercatorQuad"

# endereços que o adversário do item tenta empurrar por parâmetro de consulta
ENDERECOS = (
    "file:///etc/passwd",
    "s3://outro-balde/segredo.tif",
    "http://169.254.169.254/latest/meta-data/iam/security-credentials/",
    "/vsicurl/http://169.254.169.254/x.tif",
    "https://exemplo.invalido/a.tif",
)
# todo parâmetro que a fábrica do TiTiler publica e que carrega texto livre, mais o `url` do original
PARAMETROS = ("url", "expression", "colormap", "colormap_name", "assets", "bidx", "algorithm",
              "rescale", "nodata", "unscale", "resampling", "src_path", "dataset", "input")


def _cliente():
    from fastapi.testclient import TestClient

    from app.imagens.servico_titiler import app

    return TestClient(app, base_url="http://testserver")


@pytest.fixture(scope="module")
def raster_demo(tenant_id_a):
    """Um COG de verdade (4 bandas, 16 bits) no balde do inquilino A, com item STAC e espelho."""
    from tests.api.imagens.apoio_raster import semear_raster

    return semear_raster(tenant_id_a, "demo")


@pytest.fixture(scope="module")
def raster_demo_b(tenant_id_b):
    """O mesmo, no inquilino B: é o item que o token de A tem de NÃO conseguir ler."""
    from tests.api.imagens.apoio_raster import semear_raster

    return semear_raster(tenant_id_b, "demo2")


@pytest.fixture(scope="module")
def token_a(sessao_a):
    r = sessao_a.post("/api/tokens", json={"nome": "zt-titiler-a", "escopos": ["tiles:ler"]})
    assert r.status_code == 201, r.text
    dados = r.json()
    yield dados
    sessao_a.delete(f"/api/tokens/{dados['id']}")


def _base(token: str, item: str) -> str:
    return f"/svc/{token}/raster/{item}"


# ------------------------------------------------- cláusula: /info e o ladrilho respondem para o item
def test_info_responde_para_item_do_inquilino(token_a, raster_demo):
    c = _cliente()
    r = c.get(_base(token_a["token"], raster_demo["item_id"]) + "/info")
    assert r.status_code == 200, r.text[:400]
    corpo = r.json()
    assert corpo["band_metadata"] and corpo["count"] == 4
    assert len(corpo["bounds"]) == 4
    # nenhum campo da resposta pode revelar o caminho interno do objeto no armazenamento
    assert "vsis3" not in json.dumps(corpo)


def test_ladrilho_webmercatorquad_devolve_png(token_a, raster_demo):
    c = _cliente()
    url = _base(token_a["token"], raster_demo["item_id"]) + f"/tiles/{GRADE}/{Z}/{X}/{Y}.png"
    r = c.get(url)
    assert r.status_code == 200, r.text[:400]
    assert r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_toda_resposta_traz_server_timing_e_noindex(token_a, raster_demo):
    c = _cliente()
    base = _base(token_a["token"], raster_demo["item_id"])
    for url in (base + "/info", base + f"/tiles/{GRADE}/{Z}/{X}/{Y}.png", "/healthz"):
        r = c.get(url)
        assert "Server-Timing" in r.headers, url
        assert "dur=" in r.headers["Server-Timing"], url
        assert r.headers["X-Robots-Tag"].startswith("noindex"), url


# ------------------------------------------------------------- cláusula: nada de endereço do cliente
@pytest.mark.parametrize("parametro", PARAMETROS)
@pytest.mark.parametrize("endereco", ENDERECOS)
def test_endereco_em_qualquer_parametro_devolve_400(token_a, raster_demo, parametro, endereco):
    """A refutação do item: SSRF por todos os parâmetros do OpenAPI do TiTiler, um a um."""
    c = _cliente()
    url = _base(token_a["token"], raster_demo["item_id"]) + f"/tiles/{GRADE}/{Z}/{X}/{Y}.png"
    r = c.get(url, params={parametro: endereco})
    assert r.status_code == 400, (parametro, endereco, r.status_code, r.text[:200])
    assert r.json()["erro"] == "endereco_nao_aceito"


def test_url_vazia_tambem_e_recusada_pelo_nome_do_parametro(token_a, raster_demo):
    """`?url=` sem valor não pode passar: o que se recusa é o parâmetro existir, não o valor casar."""
    c = _cliente()
    url = _base(token_a["token"], raster_demo["item_id"]) + "/info"
    r = c.get(url, params={"url": ""})
    assert r.status_code == 400 and r.json()["erro"] == "endereco_nao_aceito"


def test_item_com_travessia_de_caminho_devolve_400(token_a):
    c = _cliente()
    for ruim in ("..", "..%2f..%2fetc%2fpasswd", "a/../b"):
        r = c.get(f"/svc/{token_a['token']}/raster/{ruim}/info")
        assert r.status_code in (400, 404), (ruim, r.status_code)
        if r.status_code == 400:
            assert r.json()["erro"] == "item_invalido"


# --------------------------------------------------------- cláusula: item de outro inquilino = 403
def test_item_de_outro_inquilino_devolve_403(token_a, raster_demo_b):
    c = _cliente()
    base = _base(token_a["token"], raster_demo_b["item_id"])
    for url in (base + "/info", base + f"/tiles/{GRADE}/{Z}/{X}/{Y}.png"):
        r = c.get(url)
        assert r.status_code == 403, (url, r.status_code, r.text[:200])
        assert r.json()["erro"] == "item_indisponivel"
        assert r.headers.get("content-type", "").startswith("application/json")


def test_token_invalido_tambem_para_em_403(raster_demo):
    c = _cliente()
    r = c.get(_base("plat_naoexisteestetoken0000000000", raster_demo["item_id"]) + "/info")
    assert r.status_code == 403, r.text[:200]


# ------------------------------------------------------------------ cláusula: uma só grade e OpenAPI
def test_so_existe_a_grade_webmercatorquad(token_a, raster_demo):
    from app.imagens.servico_titiler import GRADES

    assert list(GRADES.list()) == [GRADE]
    c = _cliente()
    url = _base(token_a["token"], raster_demo["item_id"]) + f"/tiles/WorldCRS84Quad/{Z}/{X}/{Y}.png"
    r = c.get(url)
    assert r.status_code in (404, 422), (r.status_code, r.text[:200])


def test_openapi_cobre_toda_rota_montada(token_a):
    """Refutação: rota montada e não documentada é rota que ninguém revisa."""
    c = _cliente()
    spec = c.get("/openapi.json").json()
    documentadas = set(spec["paths"])
    from app.imagens.servico_titiler import app as alvo

    montadas = set()
    for rota in alvo.routes:
        caminho = getattr(rota, "path", None)
        if caminho:
            montadas.add(caminho)
        for interna in getattr(getattr(rota, "original_router", None), "routes", ()):
            montadas.add("/svc/{token}/raster/{item}" + interna.path)
    faltando = {rota for rota in montadas if rota not in documentadas} - {"/openapi.json", "/healthz"}
    assert not faltando, faltando


def test_nenhuma_rota_publica_aceita_parametro_url(token_a):
    """O `url` do TiTiler original não pode reaparecer no contrato publicado."""
    c = _cliente()
    spec = c.get("/openapi.json").json()
    for caminho, metodos in spec["paths"].items():
        for metodo, corpo in metodos.items():
            nomes = {p.get("name") for p in corpo.get("parameters", [])}
            assert "url" not in nomes, (metodo, caminho)


# --------------------------------------------------------------------- cláusula: unidade e instalação
def test_unidade_systemd_existe_e_e_aceita():
    unidade = RAIZ / "deploy" / "plat-titiler.service"
    texto = unidade.read_text(encoding="utf-8")
    assert "app.imagens.servico_titiler:app" in texto
    assert "--workers 4" in texto and "--host 127.0.0.1" in texto
    assert "PYTHONNOUSERSITE=1" in texto
    # segredo nunca em Environment=/argv: só por LoadCredential=
    assert "LoadCredential=PLAT_DSN" in texto
    assert "PLAT_SECRET=" not in texto
    instalador = (RAIZ / "install.sh").read_text(encoding="utf-8")
    assert "plat-titiler.service" in instalador and "PORTA_TITILER" in instalador


@pytest.mark.skipif(shutil.which("systemd-analyze") is None, reason="systemd-analyze ausente")
def test_unidade_passa_no_systemd_analyze(tmp_path):
    origem = (RAIZ / "deploy" / "plat-titiler.service").read_text(encoding="utf-8")
    concreto = (origem.replace("APP_DIR", str(RAIZ)).replace("APP_USER", "dev")
                .replace("PORTA_TITILER", "8152"))
    destino = tmp_path / "plat-titiler.service"
    destino.write_text(concreto, encoding="utf-8")
    saida = subprocess.run(["systemd-analyze", "verify", str(destino)], capture_output=True, text=True)
    # LoadCredential= aponta para /etc/plat/segredos (só existe na máquina instalada): o verificador
    # reclama do caminho ausente, não da sintaxe. Reprova só o que for erro de sintaxe/diretiva.
    ruins = [linha for linha in saida.stderr.splitlines()
             if linha.strip() and "segredos" not in linha and "Unit is bound to inactive" not in linha]
    assert not ruins, saida.stderr[-1500:]


def test_saude_do_plat_api_sonda_o_titiler():
    """Cláusula 'ligado ao /saude do plat-api': o serviço entra na lista de sondas por
    PLAT_TITILER_URL, e o `/healthz` deste processo é o alvo dessa sonda."""
    from app.settings import settings

    assert "titiler" in settings.servicos()
    c = _cliente()
    r = c.get("/healthz")
    assert r.status_code == 200 and r.json()["estado"] == "ok" and r.json()["grade"] == GRADE


# ----------------------------------------------------------------------------- cláusula: as medidas
def _percentil(valores: list[float], p: float) -> float:
    ordenado = sorted(valores)
    posicao = min(len(ordenado) - 1, max(0, round(p * (len(ordenado) - 1))))
    return ordenado[posicao]


@pytest.mark.skipif(os.environ.get("PLAT_GRAVAR_MEDIDAS") != "1", reason="medida só na gravação")
def test_medida_40_ladrilhos_frio_e_quente(token_a, raster_demo, medida):
    """40 ladrilhos frios (distintos, cada um abre o COG e lê faixas novas) e 40 quentes (o mesmo
    ladrilho, com o cabeçalho do COG e as faixas já em memória do processo). Referência da prova do
    conceito L1: 36-56 ms em processo. Grava a carga da máquina ao lado do número."""
    c = _cliente()
    base = _base(token_a["token"], raster_demo["item_id"])
    # 40 ladrilhos distintos dentro da cobertura: z=15 dá uma grade 8x8 sobre o raster de 20 km
    zq = 15
    x0, y0 = X * 2 ** (zq - Z), Y * 2 ** (zq - Z)
    alvos = [(x0 + i % 8, y0 + i // 8) for i in range(40)]

    frios = []
    for x, y in alvos:
        inicio = time.perf_counter()
        r = c.get(base + f"/tiles/{GRADE}/{zq}/{x}/{y}.png")
        frios.append((time.perf_counter() - inicio) * 1000)
        assert r.status_code in (200, 204), (x, y, r.status_code, r.text[:200])

    quentes = []
    url_quente = base + f"/tiles/{GRADE}/{Z}/{X}/{Y}.png"
    c.get(url_quente)  # aquece
    for _ in range(40):
        inicio = time.perf_counter()
        r = c.get(url_quente)
        quentes.append((time.perf_counter() - inicio) * 1000)
        assert r.status_code == 200

    carga = os.getloadavg()[0]
    livre_gb = round(int(subprocess.run(["awk", "/MemAvailable/ {print $2}", "/proc/meminfo"],
                                        capture_output=True, text=True).stdout or 0) / 1048576, 1)
    gravar = medida(ITEM)
    comum = f" (40 ladrilhos, TestClient em processo; carga_1min={carga:.2f}; ram_livre_gb={livre_gb})"
    gravar("ladrilho_frio_mediana_ms", round(statistics.median(frios), 1), "ms",
           "pytest tests/api/imagens/test_servico_titiler.py::test_medida_40_ladrilhos_frio_e_quente" + comum)
    gravar("ladrilho_frio_p90_ms", round(_percentil(frios, 0.90), 1), "ms", "idem" + comum)
    gravar("ladrilho_quente_mediana_ms", round(statistics.median(quentes), 1), "ms", "idem" + comum)
    gravar("ladrilho_quente_p90_ms", round(_percentil(quentes, 0.90), 1), "ms", "idem" + comum)
    gravar("carga_1min", round(carga, 2), "media de 1 min", "os.getloadavg()[0] no instante da medida")
    gravar("ram_livre_gb", livre_gb, "GB", "MemAvailable de /proc/meminfo no instante da medida")


@pytest.mark.skipif(os.environ.get("PLAT_GRAVAR_MEDIDAS") != "1", reason="medida só na gravação")
def test_medida_capacidades_com_uma_grade(token_a, raster_demo, medida):
    """O tamanho e o tempo do documento de capacidades com UMA grade — é o número que sustenta a
    decisão C4 (o TiTiler com as 12 grades do morecantile publica um documento muito maior)."""
    c = _cliente()
    url = _base(token_a["token"], raster_demo["item_id"]) + f"/{GRADE}/tilejson.json"
    inicio = time.perf_counter()
    r = c.get(url)
    ms = (time.perf_counter() - inicio) * 1000
    assert r.status_code == 200, r.text[:300]
    gravar = medida(ITEM)
    gravar("tilejson_uma_grade_bytes", len(r.content), "bytes", f"GET {url}")
    gravar("tilejson_uma_grade_ms", round(ms, 1), "ms", f"GET {url} (TestClient em processo)")
    gravar("grades_publicadas", 1, "grades",
           "app.imagens.servico_titiler.GRADES.list() == ['WebMercatorQuad']")
