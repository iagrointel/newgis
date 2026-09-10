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
