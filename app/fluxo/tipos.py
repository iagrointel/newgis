"""Vocabulário fechado de tipo de fonte de fluxo e validação da `config` de cada tipo (item
L2-14-a-ingestao-de-fluxos). A lista TIPOS é a MESMA do CHECK de `plat.fluxo_fonte` na migração
20260908T1237_fluxo_ingestao.sql — as duas mudam juntas, como já vale para `plat.conexao`/`app.limites`.

Toda URL e todo par host/porta declarados aqui passam pela defesa de SSRF do item L6-02-a
(`app.conexao.seguranca.validar_url`): uma fonte nunca fica registrada apontando para a rede interna,
para o serviço de metadado da nuvem ou para o loopback desta máquina.
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from app import limites
from app.conexao import seguranca

# receptores passivos: o evento CHEGA (o processo plat-fluxo escuta)
TIPOS_RECEPTOR = ("http", "websocket_servidor", "gps_frota", "sensor")
# conectores ativos: o processo plat-fluxo VAI BUSCAR
TIPOS_CONECTOR = ("websocket_cliente", "mqtt", "sondagem", "ais")
TIPOS = tuple(sorted(TIPOS_RECEPTOR + TIPOS_CONECTOR))

# formato do corpo aceito pelo receptor HTTP, por tipo de fonte
FORMATOS_POR_TIPO = {
    "http": ("json", "ndjson", "csv", "geojson"),
    "websocket_servidor": ("json", "ndjson", "geojson"),
    "gps_frota": ("json", "ndjson", "gpx"),
    "sensor": ("json", "ndjson"),
}


class ErroConfig(ValueError):
    """Config de fonte recusada. `motivo` é o código estável que a rota devolve em 422."""

    def __init__(self, motivo: str, detalhe: str = ""):
        super().__init__(detalhe or motivo)
        self.motivo = motivo
        self.detalhe = detalhe or motivo


def _exigir(config: dict, chave: str) -> object:
    if chave not in config or config[chave] in (None, ""):
        raise ErroConfig("config_campo_obrigatorio", f"a config do tipo exige o campo {chave}")
    return config[chave]


def _texto(config: dict, chave: str, maximo: int, *, obrigatorio: bool = True, padrao: str = "") -> str:
    if chave not in config or config[chave] in (None, ""):
        if obrigatorio:
            raise ErroConfig("config_campo_obrigatorio", f"a config do tipo exige o campo {chave}")
        return padrao
    valor = config[chave]
    if not isinstance(valor, str):
        raise ErroConfig("config_tipo_errado", f"{chave} tem de ser texto")
    if len(valor) > maximo:
        raise ErroConfig("config_texto_longo", f"{chave} passa de {maximo} caracteres")
    return valor


def _inteiro(config: dict, chave: str, minimo: int, maximo: int, padrao: int) -> int:
    if chave not in config or config[chave] is None:
        return padrao
    valor = config[chave]
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise ErroConfig("config_tipo_errado", f"{chave} tem de ser inteiro")
    if not minimo <= valor <= maximo:
        raise ErroConfig("config_fora_da_faixa", f"{chave} tem de estar entre {minimo} e {maximo}")
    return valor


def url_websocket_validada(url: str) -> str:
    """`ws://`/`wss://` não existem para `app.conexao.seguranca` (que só conhece http/https). A troca de
    esquema aqui é só para a VALIDAÇÃO — o que a defesa de SSRF precisa é do host, da porta e do IP para
    onde ele resolve, e esses são os mesmos nos dois pares de esquema. A URL devolvida é a original."""
    partes = urlsplit(url)
    equivalente = {"ws": "http", "wss": "https"}.get(partes.scheme)
    if equivalente is None:
        raise ErroConfig("url_insegura", "esquema tem de ser ws:// ou wss://")
    try:
        seguranca.validar_url(urlunsplit((equivalente, partes.netloc, partes.path, partes.query, "")))
    except seguranca.ErroURLInsegura as e:
        raise ErroConfig("url_insegura", f"URL recusada: {e.motivo}") from e
    return url


def _host_porta_validados(host: str, porta: int, *, tls: bool) -> None:
    """MQTT e AIS não falam HTTP, mas o host é um endereço de rede igual: passa pela MESMA validação de
    SSRF (resolução de DNS + faixas privadas/loopback/link-local) que uma URL de conector."""
    esquema = "https" if tls else "http"
    try:
        seguranca.validar_url(f"{esquema}://{host}:{porta}/")
    except seguranca.ErroURLInsegura as e:
        raise ErroConfig("url_insegura", f"endereço recusado: {e.motivo}") from e


def validar_config(tipo: str, config: dict) -> dict:
    """Devolve a config normalizada (só as chaves que o tipo conhece) ou levanta ErroConfig."""
    if tipo not in TIPOS:
        raise ErroConfig("tipo_desconhecido", f"tipo tem de ser um de {', '.join(TIPOS)}")
    if not isinstance(config, dict):
        raise ErroConfig("config_tipo_errado", "config tem de ser objeto")

    if tipo in TIPOS_RECEPTOR:
        # receptor não tem endereço a configurar: o endereço é o do próprio receptor (plat-fluxo).
        formatos = FORMATOS_POR_TIPO[tipo]
        formato = _texto(config, "formato", 20, obrigatorio=False, padrao=formatos[0])
        if formato not in formatos:
            raise ErroConfig("formato_nao_suportado", f"formato de {tipo} tem de ser um de {', '.join(formatos)}")
        return {"formato": formato}

    if tipo == "websocket_cliente":
        url = url_websocket_validada(_texto(config, "url", limites.FLUXO_URL_MAX))
        return {
            "url": url,
            "assinatura": _texto(config, "assinatura", limites.FLUXO_TEXTO_MAX, obrigatorio=False),
            "cabecalho_credencial": _texto(config, "cabecalho_credencial", 100, obrigatorio=False),
        }

    if tipo == "mqtt":
        host = _texto(config, "host", 253)
        porta = _inteiro(config, "porta", 1, 65535, 8883)
        tls = config.get("tls", True)
        if not isinstance(tls, bool):
            raise ErroConfig("config_tipo_errado", "tls tem de ser booleano")
        _host_porta_validados(host, porta, tls=tls)
        topico = _texto(config, "topico", limites.FLUXO_MQTT_TOPICO_MAX)
        return {
            "host": host, "porta": porta, "tls": tls, "topico": topico,
            "qos": _inteiro(config, "qos", 0, 1, 0),
            "cliente_id": _texto(config, "cliente_id", 64, obrigatorio=False),
            "usuario": _texto(config, "usuario", 200, obrigatorio=False),
        }

    if tipo == "sondagem":
        url = str(_exigir(config, "url"))
        try:
            seguranca.validar_url(url)
        except seguranca.ErroURLInsegura as e:
            raise ErroConfig("url_insegura", f"URL recusada: {e.motivo}") from e
        formato = _texto(config, "formato", 20, obrigatorio=False, padrao="json")
        if formato not in ("json", "ndjson", "csv", "geojson", "esri_json"):
            raise ErroConfig("formato_nao_suportado", "formato de sondagem tem de ser json, ndjson, csv, "
                                                      "geojson ou esri_json")
        return {
            "url": url,
            "formato": formato,
            "intervalo_s": _inteiro(config, "intervalo_s", limites.FLUXO_SONDAGEM_INTERVALO_MIN_S,
                                    limites.FLUXO_SONDAGEM_INTERVALO_MAX_S, 60),
            # campo de "última atualização": a sondagem seguinte só aceita registro com valor MAIOR que o
            # da anterior, e é isso que impede a mesma lista ser ingerida de novo a cada rodada
            "campo_atualizacao": _texto(config, "campo_atualizacao", 200, obrigatorio=False),
            "caminho_lista": _texto(config, "caminho_lista", 200, obrigatorio=False),
        }

    # ais
    host = _texto(config, "host", 253)
    porta = _inteiro(config, "porta", 1, 65535, 4001)
    _host_porta_validados(host, porta, tls=False)
    return {"host": host, "porta": porta}
