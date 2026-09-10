"""Modelos pydantic da integração AGOL (item L2-08-migracao-agol). `senha`/`token` são ENTRADA apenas —
nenhum modelo de SAÍDA carrega a credencial, cifrada ou não; `CredencialSaida.configurado` diz só se existe."""

from pydantic import Field

from app import limites
from app.auth.modelos import Modelo, Saida


class CredencialEntrada(Modelo):
    """PUT /api/agol/credencial (mesmo desenho de `app.conexao.modelos.ConexaoEditar`): `credencial` ausente
    (None) preserva a cifra já guardada, só atualizando portal/usuario/rotulo; `remover_credencial=true` apaga
    a credencial cifrada (e o `tipo`) sem apagar portal/usuario/rotulo. Quando `credencial` é informada,
    `tipo` é obrigatório ('senha', pareada com `usuario`, ou 'token', de longa duração, sem usuário)."""

    portal: str = Field(default="https://www.arcgis.com", min_length=1, max_length=limites.AGOL_PORTAL_MAX)
    usuario: str = Field(default="", max_length=limites.AGOL_USUARIO_MAX)
    tipo: str | None = Field(default=None, pattern="^(senha|token)$")
    credencial: str | None = Field(default=None, max_length=limites.AGOL_CREDENCIAL_MAX)
    remover_credencial: bool = False
    rotulo: str = Field(default="", max_length=limites.AGOL_ROTULO_MAX)


class CredencialSaida(Saida):
    configurado: bool
    portal: str | None = None
    usuario: str | None = None
    tipo: str | None = None  # 'senha' | 'token'
    rotulo: str | None = None


class TesteSaida(Saida):
    ok: bool
    mensagem: str
    organizacao: str | None = None
    usuario_agol: str | None = None
    creditos_disponiveis: float | None = None
    verificado_em: str


class PublicarEntrada(Modelo):
    item_id: str = Field(pattern=r"^[0-9a-fA-F-]{36}$")
    titulo: str | None = Field(default=None, min_length=1, max_length=limites.AGOL_TITULO_MAX)


class PublicacaoSaida(Saida):
    item_id: str
    estado: str  # 'nunca_publicado' | 'pendente' | 'publicando' | 'publicado' | 'erro'
    portal: str | None = None
    agol_geojson_item_id: str | None = None
    agol_servico_item_id: str | None = None
    servico_url: str | None = None
    n_feicoes: int | None = None
    mensagem: str | None = None
    job_id: str | None = None
    publicado_em: str | None = None
    atualizado_em: str | None = None


class PublicacaoJobSaida(Saida):
    job_id: str
    estado: str
    item_id: str


class PublicacoesPagina(Saida):
    itens: list[PublicacaoSaida]
