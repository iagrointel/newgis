"""E2E do item L2-02-d-rotulos: cada cláusula literal do portão vira um teste, sobre o MapLibre
vendorizado real (o mesmo `web/vendor/maplibre-gl-4.7.1.js` da tela de mapa) e sobre um Martin de
verdade (binário `/usr/local/bin/martin`, item L2-01-b) servindo glifos — não um mock de fonte.

O Martin de glifos roda numa porta PRÓPRIA desta suíte (nunca a produção `plat-martin` :8151, nem
o config dela — ver `laco/handoffs/.../L2-02-d-rotulos.md`), com as fontes abertas Noto Sans / Open
Sans (pacotes `fonts-noto-core`/`fonts-open-sans`, instalados nesta máquina pelo gerente do turno;
ambas licença Apache/SIL, compatíveis com redistribuição pelo Martin — item L2-02-e faz a
instalação definitiva com o glifário completo e a licença documentada no catálogo; aqui só o
suficiente para provar o mecanismo de rótulo)."""

import json
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest
from PIL import Image

RAIZ = Path(__file__).resolve().parents[2]
HARNESS = (Path(__file__).parent / "apoio_estilo" / "harness_rotulos.html").resolve()
CAPTURAS = Path(__file__).parent / "capturas"
CAPTURAS.mkdir(exist_ok=True)
MEDIDAS = RAIZ / "tests" / "medidas" / "L2-02-d-rotulos.json"
FONTES_DIR = Path("/home/dev/plataforma/laco/var/fontes_martin")
MARTIN_BIN = shutil.which("martin") or "/usr/local/bin/martin"


def _porta_livre() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def martin_glifos():
    """Martin real, só com `--font`, numa porta descartável desta suíte. Sem banco: fontes são o
    único recurso publicado — não colide com o `plat-martin` de produção (porta e config distintos,
    processo próprio, morto no fim do módulo)."""
    if not Path(MARTIN_BIN).exists():
        pytest.skip("binário martin não encontrado nesta máquina")
    if not (FONTES_DIR / "NotoSans-Regular.ttf").exists():
        pytest.skip(
            f"fontes de teste ausentes em {FONTES_DIR} (rode: cp .../NotoSans-Regular.ttf .../OpenSans-Regular.ttf ali)"
        )
    porta = _porta_livre()
    proc = subprocess.Popen(
        [MARTIN_BIN, "--font", str(FONTES_DIR), "--listen-addresses", f"127.0.0.1:{porta}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        for _ in range(50):
            try:
                with socket.create_connection(("127.0.0.1", porta), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.1)
        else:
            saida = proc.stdout.read() if proc.stdout else ""
            proc.kill()
            pytest.fail(f"martin de teste não subiu na porta {porta}: {saida}")
        yield f"http://127.0.0.1:{porta}"
    finally:
        proc.kill()
        proc.wait(timeout=5)


def _grava_medida(chave: str, valor, unidade: str, comando: str):
    doc = (
        json.loads(MEDIDAS.read_text(encoding="utf-8"))
        if MEDIDAS.exists()
        else {"item": "L2-02-d-rotulos", "medidas": {}}
    )
    doc.setdefault("medidas", {})[chave] = {"valor": valor, "unidade": unidade, "comando": comando}
    MEDIDAS.write_text(json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _renderiza(page, cfg: dict) -> None:
    # viewport EXPLÍCITO do mesmo tamanho do <div id="mapa"> do arnês (800x600): sem isto, o
    # viewport padrão do navegador (maior que o mapa) faz `page.screenshot()` capturar a página
    # inteira, e a posição do rótulo na captura deixa de bater com o centro geométrico do mapa —
    # foi o que quebrou a amostragem de pixel da cláusula de prioridade/colisão na 1ª rodada.
    page.set_viewport_size({"width": 800, "height": 600})
    erros_console = []
    page.on("console", lambda m: erros_console.append(m.text) if m.type == "error" else None)
    page.add_init_script(script=f"window.ROTULO_TESTE = {json.dumps(cfg)};")
    page.goto(f"file://{HARNESS}")
    page.wait_for_selector("body[data-pronto='1']", timeout=20000)
    erro = page.get_attribute("body", "data-erro")
    assert erro is None, f"MapLibre reportou erro: {erro}"
    assert erros_console == [], f"erro de console: {erros_console}"


def _glyphs_url(base: str) -> str:
    return base + "/font/{fontstack}/{range}"


# ---------------------------------------------------------------------------------------------
# rótulo por campo
# ---------------------------------------------------------------------------------------------


def test_rotulo_por_campo(page, martin_glifos):
    feicoes = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"nome": "Fazenda Alfa"},
                "geometry": {"type": "Point", "coordinates": [-46.9, -22.9]},
            },
            {
                "type": "Feature",
                "properties": {"nome": "Fazenda Beta"},
                "geometry": {"type": "Point", "coordinates": [-46.85, -22.88]},
            },
        ],
    }
    cfg = {
        "style": {
            "version": 8,
            "glyphs": _glyphs_url(martin_glifos),
            "sources": {"camada": {"type": "geojson", "data": feicoes}},
            "layers": [
                {
                    "id": "rotulo",
                    "type": "symbol",
                    "source": "camada",
                    "layout": {"text-field": ["get", "nome"], "text-font": ["Noto Sans Regular"], "text-size": 14},
                    "paint": {"text-color": "#10161a"},
                }
            ],
        },
        "zoom": 10,
    }
    _renderiza(page, cfg)
    destino = CAPTURAS / "rotulo_campo.png"
    page.screenshot(path=str(destino))
    assert destino.stat().st_size > 5000
    _grava_medida("rotulo_por_campo", "ok", "bool", "pytest tests/e2e/test_rotulos_render.py::test_rotulo_por_campo")


# ---------------------------------------------------------------------------------------------
# rótulo por expressão com formatação '1.234,5 ha' (não compilável -> coluna do servidor)
# ---------------------------------------------------------------------------------------------


def test_rotulo_por_expressao_com_formatacao_cai_para_coluna_do_servidor(page, martin_glifos):
    from app.estilos.rotulos_servidor import nome_coluna_servidor, pre_calcular

    # a expressão que o construtor gravaria é "Concatenar(TextoNumero($area_ha, 1), ' ha')"; o
    # sufixo " ha" concatena no MapLibre (compilador.py::_rotulo_layer, bloco `unidade`), então o
    # que cai para o servidor é só a parte não compilável (ver comentário abaixo).
    props_reais = [{"area_ha": 1234.5}, {"area_ha": 88.0}]
    coluna = nome_coluna_servidor("TextoNumero($area_ha, 1)")
    # o que a ingestão/tile faria de verdade: pré-calcular a expressão SEM o sufixo (o sufixo " ha"
    # concatena no MapLibre — ver app/estilos/compilador.py::_rotulo_layer, bloco `unidade`).
    valores = pre_calcular("TextoNumero($area_ha, 1)", props_reais)
    assert valores[0] == "1.234,5"  # a formatação que dá nome à cláusula do portão

    feicoes = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {coluna: valores[0]},
                "geometry": {"type": "Point", "coordinates": [-46.9, -22.9]},
            },
            {
                "type": "Feature",
                "properties": {coluna: valores[1]},
                "geometry": {"type": "Point", "coordinates": [-46.85, -22.88]},
            },
        ],
    }
    cfg = {
        "style": {
            "version": 8,
            "glyphs": _glyphs_url(martin_glifos),
            "sources": {"camada": {"type": "geojson", "data": feicoes}},
            "layers": [
                {
                    "id": "rotulo",
                    "type": "symbol",
                    "source": "camada",
                    "layout": {
                        "text-field": ["concat", ["to-string", ["get", coluna]], " ha"],
                        "text-font": ["Noto Sans Regular"],
                        "text-size": 14,
                    },
                    "paint": {"text-color": "#10161a"},
                }
            ],
        },
        "zoom": 10,
    }
    _renderiza(page, cfg)
    destino = CAPTURAS / "rotulo_expressao_servidor.png"
    page.screenshot(path=str(destino))
    assert destino.stat().st_size > 5000
    _grava_medida(
        "rotulo_expressao_nao_compilavel_texto_servidor",
        valores[0] + " ha",
        "texto",
        "app.estilos.rotulos_servidor.pre_calcular('TextoNumero($area_ha, 1)', [{'area_ha': 1234.5}])",
    )


# ---------------------------------------------------------------------------------------------
# rótulo por classe (2 classes com filtros) com captura
# ---------------------------------------------------------------------------------------------


def test_rotulo_por_classes_com_filtro(page, martin_glifos):
    from app.estilos import compilador

    pc = {
        "tipo": "unico",
        "geometria": "ponto",
        "campo": None,
        "campos": ["classe_uso"],
        "simbolo": {"cor": "#336699"},
        "rotulos": {
            "visivel": True,
            "classes": [
                {
                    "nome": "lavoura",
                    "texto": {"campo": "classe_uso"},
                    "cor": "#1d6f42",
                    "filtro": {"campo": "classe_uso", "operador": "==", "valor": "lavoura"},
                },
                {
                    "nome": "pastagem",
                    "texto": {"campo": "classe_uso"},
                    "cor": "#a15c00",
                    "filtro": {"campo": "classe_uso", "operador": "==", "valor": "pastagem"},
                },
            ],
        },
    }
    doc_estilo = compilador.compilar(pc)
    feicoes = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"classe_uso": "lavoura"},
                "geometry": {"type": "Point", "coordinates": [-46.95, -22.9]},
            },
            {
                "type": "Feature",
                "properties": {"classe_uso": "pastagem"},
                "geometry": {"type": "Point", "coordinates": [-46.85, -22.88]},
            },
        ],
    }
    assert doc_estilo["glyphs"] == compilador.GLYPHS_PADRAO  # o documento GRAVADO usa a convenção fixa
    layers = [{**la, "source": "camada"} for la in doc_estilo["layers"]]
    # o `glyphs` do documento real aponta para o Martin de produção (rota /fontes/plat/...); aqui
    # trocamos só pelo Martin de teste desta suíte (mesmo formato de rota, host diferente) — é o
    # único ajuste feito no documento, o resto (layers, filtros, cores) é o que compilador.compilar
    # devolveu de verdade.
    cfg = {
        "style": {
            "version": 8,
            "glyphs": martin_glifos + "/font/{fontstack}/{range}",
            "sources": {"camada": {"type": "geojson", "data": feicoes}},
            "layers": layers,
        },
        "zoom": 10,
    }
    layers_rotulo = [la for la in layers if la["type"] == "symbol"]
    assert len(layers_rotulo) == 2, "duas classes com filtro -> dois layers symbol"
    _renderiza(page, cfg)
    destino = CAPTURAS / "rotulo_classes.png"
    page.screenshot(path=str(destino))
    assert destino.stat().st_size > 5000
    _grava_medida(
        "rotulo_2_classes_com_filtro_layers",
        len(layers_rotulo),
        "layers de rótulo",
        "compilador.compilar(pc) com 2 classes filtradas",
    )


# ---------------------------------------------------------------------------------------------
# rótulo de linha segue a linha (captura em z14)
# ---------------------------------------------------------------------------------------------


def test_rotulo_de_linha_segue_a_linha_em_z14(page, martin_glifos):
    from app.estilos import compilador

    pc = {
        "tipo": "unico",
        "geometria": "linha",
        "campo": None,
        "campos": ["nome"],
        "simbolo": {"cor": "#555555"},
        "rotulos": {
            "visivel": True,
            "classes": [{"texto": {"campo": "nome"}, "ao_longo_da_linha": True, "repetir_px": 180, "tamanho": 13}],
        },
    }
    doc_estilo = compilador.compilar(pc)
    rotulo_layer = [la for la in doc_estilo["layers"] if la["type"] == "symbol"][0]
    assert (
        rotulo_layer["layout"]["symbol-placement"] == "line"
    )  # prova mecânica: MapLibre vai desenhar seguindo a linha

    feicoes = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"nome": "Estrada Vicinal do Bosque"},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[-46.98, -22.94], [-46.90, -22.90], [-46.83, -22.87]],
                },
            }
        ],
    }
    layers = [{**la, "source": "camada"} for la in doc_estilo["layers"]]
    cfg = {
        "style": {
            "version": 8,
            "glyphs": martin_glifos + "/font/{fontstack}/{range}",
            "sources": {"camada": {"type": "geojson", "data": feicoes}},
            "layers": layers,
        },
        "center": [-46.90, -22.90],
        "zoom": 14,
    }
    _renderiza(page, cfg)
    destino = CAPTURAS / "rotulo_linha_z14.png"
    page.screenshot(path=str(destino))
    assert destino.stat().st_size > 5000
    _grava_medida(
        "rotulo_linha_symbol_placement", "line", "texto", "compilador.compilar com geometria linha + ao_longo_da_linha"
    )


# ---------------------------------------------------------------------------------------------
# prioridade: classe A vence B em colisão (dois pontos sobrepostos) — refutação/portão
# ---------------------------------------------------------------------------------------------


def test_prioridade_classe_a_vence_b_em_colisao(page, martin_glifos):
    """Classe A (`prioridade: 1`, mais importante) e classe B (`prioridade: 2`) no MESMO
    `plat_construtor.rotulos`, exatamente como um editor gravaria. Medido de verdade no MapLibre-GL
    real ANTES de escrever este teste: `symbol-sort-key` só ordena feições DENTRO de um layer —
    quem decide a colisão ENTRE classes/layers diferentes é a ORDEM do array `layers` (o que vem
    depois vence); é por isso que `_rotulos_layers` (app/estilos/compilador.py) reordena as classes
    por prioridade em vez de só gravar o sort-key. Aqui a prova é ponta a ponta: dois pontos no
    MESMO lugar, o documento exatamente como `compilador.compilar` devolve, contagem de pixel na
    captura real."""
    from app.estilos import compilador

    pc = {
        "tipo": "unico",
        "geometria": "ponto",
        "campo": None,
        "campos": ["classe"],
        "simbolo": {"cor": "#333333"},
        "rotulos": {
            "visivel": True,
            "classes": [
                {
                    "nome": "A",
                    "texto": {"expressao": "'AAAAAAAAAA'"},
                    "cor": "#000000",
                    "tamanho": 22,
                    "prioridade": 1,
                    "filtro": {"campo": "classe", "operador": "==", "valor": "A"},
                },
                {
                    "nome": "B",
                    "texto": {"expressao": "'BBBBBBBBBB'"},
                    "cor": "#ff0000",
                    "tamanho": 22,
                    "prioridade": 2,
                    "filtro": {"campo": "classe", "operador": "==", "valor": "B"},
                },
            ],
        },
    }
    doc_estilo = compilador.compilar(pc)
    rotulos = [la for la in doc_estilo["layers"] if la["type"] == "symbol"]
    assert rotulos[-1]["filter"][2] == "A", "prioridade 1 (mais importante) tem de ficar por último na lista de layers"

    feicoes = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"classe": "A"},
                "geometry": {"type": "Point", "coordinates": [-46.9, -22.9]},
            },
            {
                "type": "Feature",
                "properties": {"classe": "B"},
                "geometry": {"type": "Point", "coordinates": [-46.9, -22.9]},
            },
        ],
    }
    layers = [{**la, "source": "camada"} for la in doc_estilo["layers"] if la["type"] == "symbol"]
    cfg = {
        "style": {
            "version": 8,
            "glyphs": martin_glifos + "/font/{fontstack}/{range}",
            "sources": {"camada": {"type": "geojson", "data": feicoes}},
            "layers": layers,
        },
        "zoom": 14,
    }
    _renderiza(page, cfg)
    destino = CAPTURAS / "rotulo_prioridade_colisao.png"
    page.screenshot(path=str(destino))
    im = Image.open(destino).convert("RGB")

    # varre a faixa central da imagem (onde o texto cai, já que os dois pontos são o mesmo lugar,
    # centralizado no mapa) contando pixels pretos (texto de A) vs vermelhos (texto de B, só
    # apareceria se B tivesse vencido a colisão).
    largura, altura = im.size
    pretos = vermelhos = 0
    y0, y1 = altura // 2 - 30, altura // 2 + 30
    for y in range(y0, y1):
        for x in range(largura // 2 - 150, largura // 2 + 150):
            r, g, b = im.getpixel((x, y))
            if r < 60 and g < 60 and b < 60:
                pretos += 1
            elif r > 180 and g < 80 and b < 80:
                vermelhos += 1
    assert pretos > 0, "o texto de A (preto) precisa aparecer na captura"
    assert pretos > vermelhos, f"A devia vencer a colisão: pretos={pretos} vermelhos={vermelhos}"
    _grava_medida(
        "prioridade_colisao_pixels_pretos_vs_vermelhos",
        f"{pretos} x {vermelhos}",
        "pixels",
        "amostragem de pixel na captura rotulo_prioridade_colisao.png (Pillow)",
    )


# ---------------------------------------------------------------------------------------------
# faixa de escala respeitada
# ---------------------------------------------------------------------------------------------


def test_faixa_de_escala_respeitada(page, martin_glifos):
    from app.estilos import compilador

    # escala_max pequena -> só some quando MUITO afastado; aqui construímos uma faixa que INCLUI o
    # zoom 10 (visível) e EXCLUI o zoom 3 (o minzoom nativo calculado fica entre os dois).
    pc = {
        "tipo": "unico",
        "geometria": "ponto",
        "campo": None,
        "campos": ["nome"],
        "simbolo": {"cor": "#333333"},
        "rotulos": {"visivel": True, "classes": [{"texto": {"campo": "nome"}, "escala_max": 5_000_000}]},
    }
    doc_estilo = compilador.compilar(pc)
    rotulo = [la for la in doc_estilo["layers"] if la["type"] == "symbol"][0]
    id_rotulo = rotulo["id"]
    minzoom_nativo = rotulo["minzoom"]
    assert 0 < minzoom_nativo < 20

    feicoes = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"nome": "Ponto Teste"},
                "geometry": {"type": "Point", "coordinates": [-46.9, -22.9]},
            },
        ],
    }
    layers = [{**la, "source": "camada"} for la in doc_estilo["layers"]]
    base_style = {
        "version": 8,
        "glyphs": martin_glifos + "/font/{fontstack}/{range}",
        "sources": {"camada": {"type": "geojson", "data": feicoes}},
        "layers": layers,
    }

    zoom_visivel = min(19, minzoom_nativo + 3)
    zoom_invisivel = max(0, minzoom_nativo - 3)

    _renderiza(page, {"style": base_style, "center": [-46.9, -22.9], "zoom": zoom_visivel})
    visiveis_dentro = page.evaluate(
        f"() => window.mapaRotulo.queryRenderedFeatures({{layers: ['{id_rotulo}']}}).length"
    )

    _renderiza(page, {"style": base_style, "center": [-46.9, -22.9], "zoom": zoom_invisivel})
    visiveis_fora = page.evaluate(f"() => window.mapaRotulo.queryRenderedFeatures({{layers: ['{id_rotulo}']}}).length")

    assert visiveis_dentro > 0, "dentro da faixa de escala o rótulo tem de aparecer"
    assert visiveis_fora == 0, "fora da faixa de escala (mais longe que escala_max) o rótulo tem de sumir"
    _grava_medida(
        "faixa_de_escala_minzoom_nativo",
        round(minzoom_nativo, 3),
        "zoom",
        "compilador.compilar com rotulos.classes[0].escala_max=5000000",
    )


# ---------------------------------------------------------------------------------------------
# glifos servidos pelo Martin com cache (2º pedido HIT)
# ---------------------------------------------------------------------------------------------


def test_glifos_servidos_pelo_martin_com_cache(martin_glifos):
    import urllib.request

    url = martin_glifos + "/font/Noto%20Sans%20Regular/0-255"
    t0 = time.perf_counter()
    corpo1 = urllib.request.urlopen(url).read()
    t1 = time.perf_counter()
    corpo2 = urllib.request.urlopen(url).read()
    t2 = time.perf_counter()

    ms_fria, ms_cache = (t1 - t0) * 1000, (t2 - t1) * 1000
    assert corpo1 == corpo2, "o 2º pedido tem de devolver exatamente o mesmo PBF (o cache serve o mesmo byte a byte)"
    assert len(corpo1) > 1000, "glifo vazio: pacote de fonte não carregou de verdade"
    assert ms_cache < ms_fria, (
        f"2ª chamada (cache) devia ser mais rápida: fria={ms_fria:.3f} ms cache={ms_cache:.3f} ms"
    )
    _grava_medida(
        "glifos_martin_1a_chamada_ms",
        round(ms_fria, 3),
        "ms",
        "urllib GET /font/Noto Sans Regular/0-255 (Martin de teste desta suíte, 1ª chamada)",
    )
    _grava_medida(
        "glifos_martin_2a_chamada_cache_ms",
        round(ms_cache, 3),
        "ms",
        "idem, 2ª chamada (mesmo processo Martin, cache em memória)",
    )
    _grava_medida("glifos_martin_2a_chamada_e_hit", ms_cache < ms_fria, "bool", "ms_cache < ms_fria acima")
