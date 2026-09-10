"""Conectores PMTiles/XYZ/TileJSON (item L6-02-g-pmtiles-xyz-tilejson; ADR 0012; family de
`app/conexao/rotas.py`). Dois protocolos de `plat.conexao.tipo` sem metadado padronizado sondável
(`app/conexao/proveniencia.py` já documenta isso para `pmtiles`): zoom mínimo/máximo e atribuição vêm SEMPRE do
que o usuário declara no `config` ao criar a conexão — nunca um valor sondado, nunca um padrão inventado (a
mesma regra "procedência errada é pior que nenhuma" do resto da casa).

Duas checagens deste módulo:

  1. `validar_config` — `config` de uma conexão `pmtiles`/`xyz` tem de trazer `atribuicao` (texto não vazio,
     vira `creditos` do item publicado — o mais perto de "legenda" que a plataforma tem hoje) e `zoom_min`/
     `zoom_max` (inteiros, 0 <= zoom_min <= zoom_max <= CONEXAO_TILE_ZOOM_MAX). `xyz` também exige `formato`
     ("raster" ou "vetor" — a hipótese do item cobre os dois) e que a URL declare literalmente os três
     marcadores `{z}`, `{x}`, `{y}` (case-sensitive, como todo servidor XYZ/TileJSON do mercado).

  2. `verificar_range_pmtiles` — antes de aceitar uma conexão `pmtiles`, pede `Range: bytes=0-<N-1>` (N =
     `CONEXAO_PMTILES_RANGE_BYTES`) pelo MESMO caminho seguro contra SSRF do resto da casa
     (`app.conexao.seguranca.buscar_seguro`, nunca um cliente HTTP à parte) e exige `206 Partial Content` —
     PMTiles inteiro é um único arquivo (pode ter dezenas de GB, como o próprio demo público usado nos testes)
     e o formato só funciona porque o cliente lê o cabeçalho e o índice por Range; um servidor que devolve
     `200` (corpo inteiro) para um pedido com `Range` está dizendo, na prática, "não suporto Range" — mesmo
     que a conexão em si responda — e tem de ser recusado ANTES de a conexão ficar gravada, com o motivo
     nomeado (refutação do item: "adversário fornece servidor que responde 200 a Range: tem de ser recusado").
"""

from __future__ import annotations

from dataclasses import dataclass

from app import limites
from app.conexao import seguranca

_MARCADORES_XYZ = ("{z}", "{x}", "{y}")
_FORMATOS_XYZ = ("raster", "vetor")


class ErroConfigTiles(ValueError):
    def __init__(self, codigo: str, campo: str, mensagem: str):
        self.codigo = codigo
        self.campo = campo
        super().__init__(mensagem)


@dataclass(frozen=True)
class ResultadoRange:
    ok: bool
    motivo: str
    status: int | None


def _zoom_ok(config: dict) -> tuple[int, int]:
    zmin, zmax = config.get("zoom_min"), config.get("zoom_max")
    if not isinstance(zmin, int) or isinstance(zmin, bool):
        raise ErroConfigTiles("zoom_min_invalido", "zoom_min", "config.zoom_min é obrigatório e tem de ser inteiro")
    if not isinstance(zmax, int) or isinstance(zmax, bool):
        raise ErroConfigTiles("zoom_max_invalido", "zoom_max", "config.zoom_max é obrigatório e tem de ser inteiro")
    if not (0 <= zmin <= zmax <= limites.CONEXAO_TILE_ZOOM_MAX):
        raise ErroConfigTiles(
            "zoom_fora_da_faixa", "zoom_min/zoom_max",
            f"zoom_min/zoom_max têm de satisfazer 0 <= zoom_min <= zoom_max <= {limites.CONEXAO_TILE_ZOOM_MAX}",
        )
    return zmin, zmax


def _atribuicao_ok(config: dict) -> str:
    atribuicao = config.get("atribuicao")
    if not isinstance(atribuicao, str) or not atribuicao.strip():
        raise ErroConfigTiles(
            "atribuicao_obrigatoria", "atribuicao",
            "config.atribuicao é obrigatório (texto não vazio) — vira o crédito exibido na legenda da camada",
        )
    atribuicao = " ".join(atribuicao.split())
    if len(atribuicao) > limites.CONEXAO_ATRIBUICAO_MAX:
        raise ErroConfigTiles(
            "atribuicao_longa_demais", "atribuicao",
            f"config.atribuicao passa de {limites.CONEXAO_ATRIBUICAO_MAX} caracteres",
        )
    return atribuicao


def validar_config(tipo: str, url: str, config: dict) -> dict:
    """Confere `config` de uma conexão `pmtiles`/`xyz` e devolve os campos já normalizados (atribuição com
    espaços colapsados, zoom como inteiros) — quem chama grava exatamente o que voltou daqui, nunca o bruto do
    pedido. Levanta `ErroConfigTiles` (nunca devolve "meio válido"); chamado tanto na criação quanto na edição
    de URL/config (rotas.py), para que uma conexão nunca fique com atribuição/zoom ausente por ter sido só
    editada depois de criada."""
    if tipo not in ("pmtiles", "xyz"):
        return config
    atribuicao = _atribuicao_ok(config)
    zmin, zmax = _zoom_ok(config)
    normalizado = dict(config)
    normalizado["atribuicao"] = atribuicao
    normalizado["zoom_min"] = zmin
    normalizado["zoom_max"] = zmax
    if tipo == "xyz":
        formato = config.get("formato")
        if formato not in _FORMATOS_XYZ:
            raise ErroConfigTiles(
                "formato_invalido", "formato", f"config.formato é obrigatório e tem de ser um de {_FORMATOS_XYZ}"
            )
        faltando = [m for m in _MARCADORES_XYZ if m not in url]
        if faltando:
            raise ErroConfigTiles(
                "url_sem_marcadores_xyz", "url",
                f"a URL de uma conexão xyz precisa dos marcadores {_MARCADORES_XYZ}; faltando: {faltando}",
            )
        normalizado["formato"] = formato
    return normalizado


def verificar_range_pmtiles(url: str) -> ResultadoRange:
    """GET com `Range: bytes=0-<N-1>` pelo caminho seguro contra SSRF; só aceita `206`. Nunca levanta: qualquer
    recusa vira `ResultadoRange(ok=False, ...)` com o motivo nomeado — quem chama (rotas.py) decide o código
    HTTP e a mensagem ao inquilino."""
    n = limites.CONEXAO_PMTILES_RANGE_BYTES
    resultado = seguranca.buscar_seguro(
        url, metodo="GET", timeout_conectar=limites.CONEXAO_CONECTAR_TIMEOUT_S,
        timeout_ler=limites.CONEXAO_LER_TIMEOUT_S, max_bytes=n * 2,
        cabecalhos={"Range": f"bytes=0-{n - 1}"},
    )
    if resultado.status is None:
        return ResultadoRange(ok=False, motivo=f"nao_verificou_range:{resultado.mensagem}", status=None)
    if resultado.status == 206:
        return ResultadoRange(ok=True, motivo="range_206_confirmado", status=206)
    if resultado.status == 200:
        # o caso do adversário do item: o servidor respondeu (nem recusou a conexão), mas ignorou o Range e
        # devolveu o corpo inteiro — para um arquivo PMTiles isto é o mesmo que não suportar o protocolo.
        return ResultadoRange(ok=False, motivo="servidor_ignora_range_devolveu_200", status=200)
    return ResultadoRange(ok=False, motivo=f"range_recusado_http_{resultado.status}", status=resultado.status)


def tilejson(conexao: dict) -> dict:
    """TileJSON 3.0.0 (https://github.com/mapbox/tilejson-spec/tree/master/3.0.0) de uma conexão `xyz` — só
    monta o que a própria conexão já guarda (config.zoom_min/zoom_max/atribuicao/formato), nunca sonda o
    serviço de novo (a checagem de metadado já aconteceu na criação, via `validar_config`)."""
    config = conexao.get("config") or {}
    return {
        "tilejson": "3.0.0",
        "name": conexao.get("nome"),
        "attribution": config.get("atribuicao"),
        "scheme": "xyz",
        "tiles": [conexao["url"]],
        "minzoom": config.get("zoom_min", 0),
        "maxzoom": config.get("zoom_max", limites.CONEXAO_TILE_ZOOM_MAX),
        "format": config.get("formato"),
    }
