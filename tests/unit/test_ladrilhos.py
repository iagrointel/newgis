"""Item L6-02-g-pmtiles-xyz-tilejson: `config` obrigatório de pmtiles/xyz (atribuição + zoom, marcadores
{z}{x}{y} para xyz), verificação de `Range`/206 antes de aceitar uma conexão pmtiles, e o TileJSON montado do
que a conexão já guarda. Refutação do item: "adversário fornece servidor que responde 200 a Range (ignora o
cabeçalho): tem de ser recusado" — provada com um servidor local de verdade bindado no IP público desta
máquina (nunca loopback: `buscar_seguro` bloqueia loopback antes mesmo de chegar ao Range), o mesmo padrão de
`tests/unit/test_conexao_seguranca.py`.

O teste de 206 de verdade usa um arquivo PMTiles público real (Tigris/protomaps, `accept-ranges: bytes`
conferido por HTTP em 07/09/2026 — `curl -D- -H "Range: bytes=0-1023"` devolveu 206/Content-Range); marcado
`lento` (rede real), como todo teste desta casa que sai para a internet."""

import http.server
import threading

import pytest

from app.conexao import ladrilhos as l

URL_PMTILES_PUBLICA = "https://demo-bucket.protomaps.com/v4.pmtiles"  # accept-ranges: bytes, 206 conferido


# --------------------------------------------------------------------- validar_config (sem rede)
def _config(**over):
    base = {"atribuicao": "  Protomaps  ", "zoom_min": 0, "zoom_max": 14}
    base.update(over)
    return base


def test_tipo_fora_de_pmtiles_xyz_nao_mexe_no_config():
    config = {"qualquer": "coisa"}
    assert l.validar_config("wms", "https://x/", config) is config


def test_pmtiles_aceita_config_completo_e_normaliza_espacos():
    normalizado = l.validar_config("pmtiles", "https://x/a.pmtiles", _config(atribuicao="  A   B  "))
    assert normalizado["atribuicao"] == "A B"
    assert normalizado["zoom_min"] == 0
    assert normalizado["zoom_max"] == 14


@pytest.mark.parametrize(
    "campo,valor,codigo",
    [
        ("atribuicao", "", "atribuicao_obrigatoria"),
        ("atribuicao", "   ", "atribuicao_obrigatoria"),
        ("atribuicao", "x" * 501, "atribuicao_longa_demais"),
        ("zoom_min", "0", "zoom_min_invalido"),
        ("zoom_min", None, "zoom_min_invalido"),
        ("zoom_max", 1.5, "zoom_max_invalido"),
    ],
)
def test_pmtiles_recusa_config_incompleto(campo, valor, codigo):
    with pytest.raises(l.ErroConfigTiles) as exc:
        l.validar_config("pmtiles", "https://x/a.pmtiles", _config(**{campo: valor}))
    assert exc.value.codigo == codigo


def test_pmtiles_recusa_zoom_invertido():
    with pytest.raises(l.ErroConfigTiles) as exc:
        l.validar_config("pmtiles", "https://x/a.pmtiles", _config(zoom_min=10, zoom_max=5))
    assert exc.value.codigo == "zoom_fora_da_faixa"


def test_pmtiles_recusa_zoom_acima_do_teto():
    from app import limites

    with pytest.raises(l.ErroConfigTiles) as exc:
        l.validar_config("pmtiles", "https://x/a.pmtiles", _config(zoom_max=limites.CONEXAO_TILE_ZOOM_MAX + 1))
    assert exc.value.codigo == "zoom_fora_da_faixa"


def test_xyz_exige_formato_e_marcadores_na_url():
    with pytest.raises(l.ErroConfigTiles) as exc:
        l.validar_config("xyz", "https://x/{z}/{x}/{y}.png", _config())  # sem formato
    assert exc.value.codigo == "formato_invalido"

    with pytest.raises(l.ErroConfigTiles) as exc:
        l.validar_config("xyz", "https://x/tiles.png", _config(formato="raster"))  # sem marcadores
    assert exc.value.codigo == "url_sem_marcadores_xyz"


def test_xyz_aceita_com_marcadores_e_formato():
    normalizado = l.validar_config("xyz", "https://x/{z}/{x}/{y}.pbf", _config(formato="vetor"))
    assert normalizado["formato"] == "vetor"


# --------------------------------------------------------------------- tilejson (sem rede)
def test_tilejson_monta_do_que_a_conexao_ja_guarda():
    conexao = {
        "nome": "camada de teste", "url": "https://x/{z}/{x}/{y}.pbf",
        "config": {"atribuicao": "Fonte X", "zoom_min": 2, "zoom_max": 16, "formato": "vetor"},
    }
    doc = l.tilejson(conexao)
    assert doc["tilejson"] == "3.0.0"
    assert doc["attribution"] == "Fonte X"
    assert doc["minzoom"] == 2 and doc["maxzoom"] == 16
    assert doc["tiles"] == ["https://x/{z}/{x}/{y}.pbf"]
    assert doc["format"] == "vetor"


# --------------------------------------------------------------------- verificar_range_pmtiles (rede real)
@pytest.mark.lento
def test_range_pmtiles_publico_confirma_206():
    resultado = l.verificar_range_pmtiles(URL_PMTILES_PUBLICA)
    assert resultado.ok is True, resultado.motivo
    assert resultado.status == 206


@pytest.mark.lento
def test_adversario_devolve_200_ignorando_range_e_recusado():
    """a refutação exigida pelo item: servidor público de verdade (bind no IP público desta máquina, nunca
    loopback — `buscar_seguro` já recusaria loopback antes de olhar o Range) que responde 200 ao pedido com
    `Range`, corpo inteiro. `verificar_range_pmtiles` tem de recusar mesmo a conexão tendo respondido."""
    ip_publico = _ip_publico_desta_maquina()
    if ip_publico is None:
        pytest.skip("máquina sem IP público roteável (sem interface global IPv4)")

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            # ignora o cabeçalho Range de propósito: devolve 200 e o corpo inteiro, como o adversário do item
            corpo = b"0" * 2048
            self.send_response(200)
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer((ip_publico, 0), Handler)
    porta = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        resultado = l.verificar_range_pmtiles(f"http://{ip_publico}:{porta}/fingido.pmtiles")
    finally:
        srv.shutdown()
        t.join(timeout=2)

    assert resultado.ok is False
    assert resultado.status == 200
    assert resultado.motivo == "servidor_ignora_range_devolveu_200"


def _ip_publico_desta_maquina() -> str | None:
    import ipaddress
    import subprocess

    try:
        saida = subprocess.run(
            ["ip", "-4", "-o", "addr", "show", "scope", "global"], capture_output=True, text=True, timeout=3
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for linha in saida.splitlines():
        partes = linha.split()
        if len(partes) < 4:
            continue
        ip = partes[3].split("/")[0]
        try:
            if ipaddress.ip_address(ip).is_global:
                return ip
        except ValueError:
            continue
    return None
