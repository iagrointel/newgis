"""Mapeamento de campos de uma fonte de fluxo (item L2-14-a-ingestao-de-fluxos): caminho JSON → coluna, tipo,
fuso horário, campo de id de rastro, campo de tempo e geometria (lon/lat, WKT ou GeoJSON).

Duas funções públicas:

  `validar(mapeamento)`     → mapeamento normalizado + `esquema_destino` (lista de {nome, tipo}) GERADO daqui.
  `aplicar(mapa, registro)` → `Evento` normalizado, ou `ErroEvento` com o motivo (nunca exceção crua).

O "esquema de destino gerado" é a lista de campos com tipo declarado; os valores já convertidos vão em
`plat.fluxo_evento.atributos` (jsonb). Uma tabela com colunas tipadas POR FONTE exigiria DDL em tempo de
execução a partir de dado do inquilino — ver o ADR do item para por que isso foi recusado.

Tempo: o valor convertido é sempre UTC. Um texto SEM deslocamento é interpretado no fuso declarado em
`campo_tempo.fuso` (nome IANA, `zoneinfo` da biblioteca padrão); um texto COM deslocamento ignora o fuso
declarado (o dado já diz onde está). Épocas (`epoch_s`, `epoch_ms`) são UTC por definição.
"""

from __future__ import annotations

import datetime
import math
import re
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app import limites

TIPOS_CAMPO = ("texto", "inteiro", "numero", "booleano", "data")
TIPOS_TEMPO = ("iso", "epoch_s", "epoch_ms", "texto")
MODOS_GEOMETRIA = ("nenhum", "lonlat", "wkt", "geojson")
NOME_COLUNA = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
CAMINHO = re.compile(r"^[A-Za-z0-9_. \[\]-]{1,200}$")
_PARTE_INDICE = re.compile(r"^(.*?)\[(\d+)\]$")
UTC = datetime.UTC


class ErroMapeamento(ValueError):
    def __init__(self, motivo: str, detalhe: str = ""):
        super().__init__(detalhe or motivo)
        self.motivo = motivo
        self.detalhe = detalhe or motivo


@dataclass(frozen=True)
class Evento:
    rastro_id: str | None
    tempo_evento: datetime.datetime
    lon: float | None
    lat: float | None
    wkt: str | None
    atributos: dict


@dataclass(frozen=True)
class ErroEvento:
    motivo: str
    detalhe: str = ""


@dataclass(frozen=True)
class Campo:
    caminho: str
    coluna: str
    tipo: str
    fuso: str | None = None


@dataclass(frozen=True)
class Mapa:
    campo_tempo: dict
    campo_rastro: str | None
    geometria: dict
    campos: tuple[Campo, ...] = field(default_factory=tuple)


# ------------------------------------------------------------------ leitura por caminho
def ler_caminho(registro, caminho: str):
    """`a.b[0].c` sobre dicionários e listas aninhados. Caminho ausente devolve None — nunca levanta."""
    atual = registro
    for parte in caminho.split("."):
        nome, indices = parte, []
        while True:
            m = _PARTE_INDICE.match(nome)
            if m is None:
                break
            nome = m.group(1)
            indices.insert(0, int(m.group(2)))
        if nome:
            if not isinstance(atual, dict):
                return None
            atual = atual.get(nome)
        for i in indices:
            if not isinstance(atual, (list, tuple)) or i >= len(atual):
                return None
            atual = atual[i]
        if atual is None:
            return None
    return atual


# ------------------------------------------------------------------ validação
def _fuso(nome: str | None) -> ZoneInfo | None:
    if not nome:
        return None
    try:
        return ZoneInfo(nome)
    except (ZoneInfoNotFoundError, ValueError, KeyError) as e:
        raise ErroMapeamento("fuso_desconhecido", f"fuso horário desconhecido: {nome}") from e


def _caminho_ok(caminho, onde: str) -> str:
    if not isinstance(caminho, str) or not CAMINHO.match(caminho):
        raise ErroMapeamento("caminho_invalido", f"caminho inválido em {onde}")
    return caminho


def validar(bruto: dict) -> tuple[Mapa, list[dict]]:
    """Mapeamento cru (o que a rota recebeu) → (Mapa, esquema_destino). Levanta ErroMapeamento."""
    if not isinstance(bruto, dict):
        raise ErroMapeamento("mapeamento_tipo_errado", "mapeamento tem de ser objeto")

    tempo = bruto.get("campo_tempo") or {}
    if not isinstance(tempo, dict):
        raise ErroMapeamento("mapeamento_tipo_errado", "campo_tempo tem de ser objeto")
    tipo_tempo = tempo.get("tipo", "iso")
    if tipo_tempo not in TIPOS_TEMPO:
        raise ErroMapeamento("tempo_tipo_invalido", f"campo_tempo.tipo tem de ser um de {', '.join(TIPOS_TEMPO)}")
    caminho_tempo = tempo.get("caminho")
    if caminho_tempo is not None:
        _caminho_ok(caminho_tempo, "campo_tempo")
    fuso_nome = tempo.get("fuso") or None
    _fuso(fuso_nome)
    formato = tempo.get("formato") or None
    if formato is not None and (not isinstance(formato, str) or len(formato) > 100):
        raise ErroMapeamento("tempo_formato_invalido", "campo_tempo.formato tem de ser texto de até 100 caracteres")
    if tipo_tempo == "texto" and not formato:
        raise ErroMapeamento("tempo_formato_invalido", "campo_tempo.tipo=texto exige campo_tempo.formato")
    campo_tempo = {"caminho": caminho_tempo, "tipo": tipo_tempo, "fuso": fuso_nome, "formato": formato}

    rastro = bruto.get("campo_rastro") or None
    if rastro is not None:
        _caminho_ok(rastro, "campo_rastro")

    geo = bruto.get("geometria") or {"modo": "nenhum"}
    if not isinstance(geo, dict):
        raise ErroMapeamento("mapeamento_tipo_errado", "geometria tem de ser objeto")
    modo = geo.get("modo", "nenhum")
    if modo not in MODOS_GEOMETRIA:
        raise ErroMapeamento("geometria_modo_invalido", f"geometria.modo tem de ser um de {', '.join(MODOS_GEOMETRIA)}")
    if modo == "lonlat":
        geometria = {"modo": modo, "lon": _caminho_ok(geo.get("lon"), "geometria.lon"),
                     "lat": _caminho_ok(geo.get("lat"), "geometria.lat")}
    elif modo in ("wkt", "geojson"):
        geometria = {"modo": modo, "caminho": _caminho_ok(geo.get("caminho"), "geometria.caminho")}
    else:
        geometria = {"modo": "nenhum"}

    campos_brutos = bruto.get("campos") or []
    if not isinstance(campos_brutos, list):
        raise ErroMapeamento("mapeamento_tipo_errado", "campos tem de ser lista")
    if len(campos_brutos) > limites.FLUXO_CAMPOS_MAX:
        raise ErroMapeamento("campos_demais", f"a fonte passa de {limites.FLUXO_CAMPOS_MAX} campos mapeados")
    campos, vistos = [], set()
    for c in campos_brutos:
        if not isinstance(c, dict):
            raise ErroMapeamento("mapeamento_tipo_errado", "cada campo tem de ser objeto")
        caminho = _caminho_ok(c.get("caminho"), "campos[].caminho")
        coluna = c.get("coluna") or caminho.replace(".", "_").replace("[", "_").replace("]", "").lower()
        if not NOME_COLUNA.match(coluna):
            raise ErroMapeamento("coluna_invalida", f"nome de coluna inválido: {coluna}")
        if coluna in vistos:
            raise ErroMapeamento("coluna_repetida", f"coluna repetida no mapeamento: {coluna}")
        vistos.add(coluna)
        tipo = c.get("tipo", "texto")
        if tipo not in TIPOS_CAMPO:
            raise ErroMapeamento("campo_tipo_invalido", f"tipo de campo tem de ser um de {', '.join(TIPOS_CAMPO)}")
        fuso_campo = c.get("fuso") or None
        _fuso(fuso_campo)
        campos.append(Campo(caminho=caminho, coluna=coluna, tipo=tipo, fuso=fuso_campo))

    mapa = Mapa(campo_tempo=campo_tempo, campo_rastro=rastro, geometria=geometria, campos=tuple(campos))
    return mapa, esquema_destino(mapa)


def esquema_destino(mapa: Mapa) -> list[dict]:
    """Esquema GERADO do mapeamento: o que quem consome o fluxo (camada, painel, API) pode contar que existe."""
    esquema = [
        {"nome": "rastro_id", "tipo": "texto", "origem": mapa.campo_rastro or ""},
        {"nome": "tempo_evento", "tipo": "data", "origem": mapa.campo_tempo.get("caminho") or ""},
        {"nome": "recebido_em", "tipo": "data", "origem": ""},
    ]
    if mapa.geometria.get("modo") != "nenhum":
        esquema.append({"nome": "geom", "tipo": "geometria", "origem": mapa.geometria.get("modo", "")})
    esquema += [{"nome": c.coluna, "tipo": c.tipo, "origem": c.caminho} for c in mapa.campos]
    return esquema


def de_json(bruto: dict) -> Mapa:
    """Reconstrói o Mapa do jsonb guardado (já validado na escrita)."""
    mapa, _ = validar(bruto or {})
    return mapa


def para_json(mapa: Mapa) -> dict:
    return {
        "campo_tempo": mapa.campo_tempo,
        "campo_rastro": mapa.campo_rastro,
        "geometria": mapa.geometria,
        "campos": [{"caminho": c.caminho, "coluna": c.coluna, "tipo": c.tipo, "fuso": c.fuso} for c in mapa.campos],
    }


# ------------------------------------------------------------------ conversão de valor
def _para_utc(valor: datetime.datetime, fuso_nome: str | None) -> datetime.datetime:
    if valor.tzinfo is None:
        zona = _fuso(fuso_nome) or UTC
        valor = valor.replace(tzinfo=zona)
    return valor.astimezone(UTC)


def converter_tempo(valor, tipo: str, fuso_nome: str | None, formato: str | None) -> datetime.datetime:
    """Levanta ErroMapeamento('tempo_invalido') — quem chama transforma em evento descartado, com contagem."""
    if valor is None:
        raise ErroMapeamento("tempo_invalido", "campo de tempo ausente")
    try:
        if tipo == "epoch_s":
            return datetime.datetime.fromtimestamp(float(valor), UTC)
        if tipo == "epoch_ms":
            return datetime.datetime.fromtimestamp(float(valor) / 1000.0, UTC)
        if tipo == "texto":
            return _para_utc(datetime.datetime.strptime(str(valor), formato or ""), fuso_nome)
        texto = str(valor).strip().replace("Z", "+00:00")
        return _para_utc(datetime.datetime.fromisoformat(texto), fuso_nome)
    except ErroMapeamento:
        raise
    except (TypeError, ValueError, OSError, OverflowError) as e:
        raise ErroMapeamento("tempo_invalido", f"tempo não convertido: {str(valor)[:80]}") from e


def converter_valor(valor, tipo: str, fuso_nome: str | None):
    if valor is None:
        return None
    if tipo == "texto":
        texto = valor if isinstance(valor, str) else str(valor)
        if len(texto) > limites.FLUXO_TEXTO_MAX:
            raise ErroMapeamento("texto_longo", f"valor de texto passa de {limites.FLUXO_TEXTO_MAX} caracteres")
        return texto
    if tipo == "booleano":
        if isinstance(valor, bool):
            return valor
        if isinstance(valor, str) and valor.strip().lower() in ("true", "false", "1", "0", "sim", "nao", "não"):
            return valor.strip().lower() in ("true", "1", "sim")
        if isinstance(valor, (int, float)) and valor in (0, 1):
            return bool(valor)
        raise ErroMapeamento("valor_invalido", "valor booleano inválido")
    if tipo in ("inteiro", "numero"):
        try:
            n = float(valor)
        except (TypeError, ValueError) as e:
            raise ErroMapeamento("valor_invalido", f"valor numérico inválido: {str(valor)[:40]}") from e
        if not math.isfinite(n):
            raise ErroMapeamento("valor_invalido", "número não finito")
        if tipo == "inteiro":
            if abs(n) > limites.FLUXO_INTEIRO_MAX:
                raise ErroMapeamento("valor_invalido", "inteiro fora da faixa")
            return int(n)
        return n
    # data: guardada em milissegundos desde a época (a mesma convenção da linguagem de expressão)
    return int(converter_tempo(valor, "iso" if isinstance(valor, str) else "epoch_ms",
                               fuso_nome, None).timestamp() * 1000)


def _geometria(mapa: Mapa, registro) -> tuple[float | None, float | None, str | None]:
    modo = mapa.geometria.get("modo", "nenhum")
    if modo == "nenhum":
        return None, None, None
    if modo == "lonlat":
        lon, lat = ler_caminho(registro, mapa.geometria["lon"]), ler_caminho(registro, mapa.geometria["lat"])
        if lon is None or lat is None:
            return None, None, None
        try:
            lon, lat = float(lon), float(lat)
        except (TypeError, ValueError) as e:
            raise ErroMapeamento("coordenada_invalida", "lon/lat não numéricos") from e
        if not (math.isfinite(lon) and math.isfinite(lat)) or not (-180 <= lon <= 180) or not (-90 <= lat <= 90):
            raise ErroMapeamento("coordenada_fora_da_faixa", f"lon/lat fora da faixa: {lon}, {lat}")
        return lon, lat, None
    valor = ler_caminho(registro, mapa.geometria["caminho"])
    if valor is None:
        return None, None, None
    if modo == "geojson":
        if not isinstance(valor, dict) or valor.get("type") != "Point":
            raise ErroMapeamento("geometria_invalida", "geometria GeoJSON tem de ser Point")
        coords = valor.get("coordinates")
        if not isinstance(coords, (list, tuple)) or len(coords) < 2:
            raise ErroMapeamento("geometria_invalida", "Point sem coordinates")
        return _geometria_lonlat(coords[0], coords[1])
    texto = str(valor).strip()
    if len(texto) > limites.FLUXO_WKT_MAX:
        raise ErroMapeamento("geometria_invalida", f"WKT passa de {limites.FLUXO_WKT_MAX} caracteres")
    m = re.match(r"^POINT\s*\(\s*(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s*\)$", texto, re.IGNORECASE)
    if m is None:
        raise ErroMapeamento("geometria_invalida", "WKT tem de ser POINT(lon lat)")
    return _geometria_lonlat(m.group(1), m.group(2))


def _geometria_lonlat(lon, lat) -> tuple[float, float, None]:
    try:
        lon, lat = float(lon), float(lat)
    except (TypeError, ValueError) as e:
        raise ErroMapeamento("coordenada_invalida", "coordenadas não numéricas") from e
    if not (math.isfinite(lon) and math.isfinite(lat)) or not (-180 <= lon <= 180) or not (-90 <= lat <= 90):
        raise ErroMapeamento("coordenada_fora_da_faixa", f"lon/lat fora da faixa: {lon}, {lat}")
    return lon, lat, None


def aplicar(mapa: Mapa, registro, *, agora: datetime.datetime | None = None) -> Evento | ErroEvento:
    """Registro cru (dicionário já decodificado do corpo) → Evento normalizado, ou ErroEvento com o motivo."""
    if not isinstance(registro, dict):
        return ErroEvento("registro_tipo_errado", "cada evento tem de ser um objeto")
    agora = agora or datetime.datetime.now(UTC)
    try:
        caminho = mapa.campo_tempo.get("caminho")
        if caminho:
            tempo = converter_tempo(ler_caminho(registro, caminho), mapa.campo_tempo["tipo"],
                                    mapa.campo_tempo.get("fuso"), mapa.campo_tempo.get("formato"))
        else:
            tempo = agora  # fonte sem campo de tempo: o tempo do evento é o do recebimento
        adiante = (tempo - agora).total_seconds()
        if adiante > limites.FLUXO_TEMPO_FUTURO_MAX_S:
            return ErroEvento("tempo_no_futuro", f"tempo do evento {adiante:.0f} s à frente do relógio")
        if (agora - tempo).days > limites.FLUXO_TEMPO_PASSADO_MAX_DIAS:
            return ErroEvento("tempo_velho_demais", "tempo do evento fora da janela aceita")

        rastro = None
        if mapa.campo_rastro:
            valor = ler_caminho(registro, mapa.campo_rastro)
            if valor is not None:
                rastro = valor if isinstance(valor, str) else str(valor)
                if len(rastro) > limites.FLUXO_RASTRO_MAX:
                    return ErroEvento("rastro_longo",
                                      f"id de rastro passa de {limites.FLUXO_RASTRO_MAX} caracteres")

        lon, lat, wkt = _geometria(mapa, registro)

        atributos = {}
        for c in mapa.campos:
            atributos[c.coluna] = converter_valor(ler_caminho(registro, c.caminho), c.tipo, c.fuso)
    except ErroMapeamento as e:
        return ErroEvento(e.motivo, e.detalhe)
    return Evento(rastro_id=rastro, tempo_evento=tempo, lon=lon, lat=lat, wkt=wkt, atributos=atributos)
