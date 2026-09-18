"""Modelos pydantic de `plat.conexao` (item L6-02-a-modelo-conexao-e-seguranca). `credencial` é ENTRADA
apenas — nenhum modelo de SAÍDA carrega a credencial, cifrada ou não; `ConexaoSaida.tem_credencial` diz só se
existe, nunca o valor."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app import limites


class Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Saida(BaseModel):
    model_config = ConfigDict(extra="allow")


class ConexaoEntrada(Modelo):
    tipo: str = Field(pattern="^(" + "|".join(limites.CONEXAO_TIPOS) + ")$")
    nome: str = Field(min_length=1, max_length=limites.CONEXAO_NOME_MAX)
    url: str = Field(min_length=1, max_length=limites.CONEXAO_URL_MAX)
    modo: str = Field(default="referenciada", pattern="^(" + "|".join(limites.CONEXAO_MODOS) + ")$")
    config: dict[str, Any] = Field(default_factory=dict)
    credencial: str | None = Field(default=None, max_length=4096)


class ConexaoEditar(Modelo):
    nome: str | None = Field(default=None, min_length=1, max_length=limites.CONEXAO_NOME_MAX)
    url: str | None = Field(default=None, min_length=1, max_length=limites.CONEXAO_URL_MAX)
    modo: str | None = Field(default=None, pattern="^(" + "|".join(limites.CONEXAO_MODOS) + ")$")
    config: dict[str, Any] | None = None
    credencial: str | None = Field(default=None, max_length=4096)
    remover_credencial: bool = False


class Dono(Saida):
    id: int
    login: str
    nome: str | None = None


class ConexaoCartao(Saida):
    id: str
    tipo: str
    modo: str
    nome: str
    url: str
    saude: str
    saude_verificada_em: str | None = None
    # estado agregado (item L6-02-l-saude; plat.v_conexao_saude): "nunca_testada" | "ok" | "degradado" | "fora" —
    # "fora" é a última verificação falhando; "degradado" é a última passando mas alguma das últimas 5 falhando;
    # "ok" é as últimas 5 (ou menos, sem 5 ainda) passando. Nunca dois estados ao mesmo tempo (ver 036).
    estado_saude: str = "nunca_testada"
    disponibilidade_30d_pct: float | None = None
    disponibilidade_30d_total: int = 0


class Conexao(ConexaoCartao):
    config: dict[str, Any]
    tem_credencial: bool
    saude_mensagem: str | None = None
    saude_latencia_ms: int | None = None
    dono: Dono
    criado_em: str
    atualizado_em: str


class ConexaoPagina(Saida):
    total: int
    itens: list[ConexaoCartao]


class ConexaoTeste(Saida):
    ok: bool
    status: int | None = None
    mensagem: str
    latencia_ms: int
    saude: str
    saude_verificada_em: str


class SaudeHistoricoItem(Saida):
    verificada_em: str
    ok: bool
    status: int | None = None
    mensagem: str | None = None
    latencia_ms: int | None = None


class SaudeHistoricoPagina(Saida):
    itens: list[SaudeHistoricoItem]


class PublicarCamadaEntrada(Modelo):
    titulo: str | None = Field(default=None, min_length=1, max_length=250)


# --------------------------------------------------------------- arquivo por URL (item L6-02-h)
class ArquivoUrlEntrada(Modelo):
    """Configuração da conexão como fonte de ARQUIVO por URL. `intervalo_s` só é usado quando `agendado`;
    os limites vêm de `app/limites.py` (mínimo 15 min, o mesmo mínimo do agendador do L0-05)."""

    intervalo_s: int = Field(
        default=limites.CONEXAO_ARQUIVO_INTERVALO_PADRAO_S,
        ge=limites.CONEXAO_ARQUIVO_INTERVALO_MIN_S, le=limites.CONEXAO_ARQUIVO_INTERVALO_MAX_S,
    )
    agendado: bool = False


class ArquivoUrlEstado(Saida):
    conexao_id: str
    formato: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    sha256: str | None = None
    bytes: int | None = None
    item_id: str | None = None
    importacao_id: str | None = None
    intervalo_s: int
    agendado: bool
    proximo_em: str | None = None
    ultimo_em: str | None = None
    ultimo_resultado: str | None = None
    ultimo_detalhe: str | None = None
    sincronizacoes: int
    recargas: int


# --- item L6-02-conectores-vivos: descoberta de camada (`app/conexao/descoberta.py`) e proxy de tile/imagem

class CamadaExterna(Saida):
    nome: str
    titulo: str | None = None
    crs: list[str] = Field(default_factory=list)
    extensao: dict[str, Any] | None = None
    descoberta_em: str


class CamadasPagina(Saida):
    total: int
    itens: list[CamadaExterna]


class DescobrirResultado(Saida):
    ok: bool
    mensagem: str
    url_sondada: str | None = None
    total: int
    itens: list[CamadaExterna]


# --- conector de feição externa (item L6-02-c-wfs-ogcapi): WFS 2.0 e OGC API - Features no modo REFERENCIADO.
# A cópia (modo copiado) não tem rota própria: é o job `conexao.copiar_vetor` por `POST /api/jobs`, como toda
# tarefa pesada da plataforma.


class ColecaoSaida(Saida):
    nome: str
    titulo: str | None = None
    crs_nativo: str | None = None       # verbatim do serviço ("urn:ogc:def:crs:EPSG::4674"); None = não declarou
    srid_nativo: int | None = None
    srid_entregue: int
    extent_4326: list[float] | None = None
    formatos: list[str] = []


class ColecoesPagina(Saida):
    total: int
    itens: list[ColecaoSaida]
    do_cache: bool = False


class CampoSaida(Saida):
    nome: str            # já normalizado (o mesmo normalizador da ingestão de arquivo)
    origem: str          # nome como o serviço o chama
    tipo: str            # tipo de coluna PostgreSQL a que ele corresponde
    tipo_declarado: str  # o que o serviço declarou, verbatim
    origem_do_tipo: str  # describefeaturetype | queryables | amostra (inferido, nunca declarado)


class CamposSaida(Saida):
    colecao: str
    itens: list[CampoSaida]
    do_cache: bool = False


class FeicoesSaida(Saida):
    """GeoJSON + o que a paginação apurou. `numero_matched` é o total DECLARADO pelo serviço (pode ser None:
    nem todo serviço declara) e `numberReturned` é o que veio nesta resposta — os dois juntos, nunca um só."""

    # título único no OpenAPI: colidia com app.regras.modelos.FeicoesSaida e impedia a geração do SDK
    model_config = ConfigDict(title="FeicoesSaidaConexao")

    type: str = "FeatureCollection"
    features: list[dict]
    numberReturned: int  # noqa: N815 — nome do padrão OGC API - Features, não do repositório
    numberMatched: int | None = None  # noqa: N815
    colecao: str
    srid_entregue: int
    do_cache: bool = False
    avisos: list[str] = []
