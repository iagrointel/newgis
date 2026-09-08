"""Modelos pydantic do catálogo (entradas com extra=forbid; saídas com extra=allow para o OpenAPI comitado).
Limites vêm de app/limites.py (seção catálogo)."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app import limites

UUID_PADRAO = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"


class Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Saida(BaseModel):
    model_config = ConfigDict(extra="allow")


def _tags(v):
    if v is None:
        return v
    saida = []
    for t in v:
        if not isinstance(t, str):
            raise ValueError("tag precisa ser texto")
        t = " ".join(t.split())
        if not 1 <= len(t) <= limites.TAG_MAX or any(c in t for c in ",\n\r\t"):
            raise ValueError(f"tag entre 1 e {limites.TAG_MAX} caracteres, sem vírgula nem quebra de linha")
        if t not in saida:
            saida.append(t)
    return saida


def _extent(v):
    if v is None:
        return v
    if len(v) != 4:
        raise ValueError("extent exige [xmin, ymin, xmax, ymax]")
    xmin, ymin, xmax, ymax = (float(x) for x in v)
    if not (-180 <= xmin <= 180 and -180 <= xmax <= 180 and -90 <= ymin <= 90 and -90 <= ymax <= 90):
        raise ValueError("extent fora de [-180,180] x [-90,90] (EPSG:4326)")
    if not (xmin < xmax and ymin < ymax):
        raise ValueError("extent exige xmin < xmax e ymin < ymax")
    return [xmin, ymin, xmax, ymax]


# ---- entradas
class ItemEntrada(Modelo):
    tipo: str = Field(min_length=2, max_length=41, pattern=r"^[a-z][a-z0-9_]{1,40}$")
    titulo: str = Field(min_length=1, max_length=limites.ITEM_TITULO_MAX)
    resumo: str | None = Field(default=None, max_length=limites.ITEM_RESUMO_MAX)
    descricao: str | None = Field(default=None, max_length=limites.ITEM_DESCRICAO_MAX)
    tags: list[str] = Field(default_factory=list, max_length=limites.ITEM_TAGS_MAX)
    creditos: str | None = Field(default=None, max_length=limites.ITEM_CREDITOS_MAX)
    termos_de_uso: str | None = Field(default=None, max_length=limites.ITEM_DESCRICAO_MAX)
    pasta_id: str | None = Field(default=None, pattern=UUID_PADRAO)
    extent: list[float] | None = None
    extent_origem: str | None = Field(default=None, pattern="^(dado|usuario|inquilino)$")
    categorias: list[str] = Field(default_factory=list, max_length=limites.ITEM_CATEGORIAS_MAX)
    classificacao: dict[str, Any] | None = None
    url: str | None = Field(default=None, max_length=2048, pattern=r"^https?://")
    origem: str = Field(default="hospedado", pattern="^(hospedado|referenciado)$")
    dados: dict[str, Any] = Field(default_factory=dict)
    id: str | None = Field(default=None, pattern=UUID_PADRAO)  # ADR 0005: a ingestão fornece o uuid

    _t = field_validator("tags")(_tags)
    _e = field_validator("extent")(_extent)


class ItemEditar(Modelo):
    titulo: str | None = Field(default=None, min_length=1, max_length=limites.ITEM_TITULO_MAX)
    resumo: str | None = Field(default=None, max_length=limites.ITEM_RESUMO_MAX)
    descricao: str | None = Field(default=None, max_length=limites.ITEM_DESCRICAO_MAX)
    tags: list[str] | None = Field(default=None, max_length=limites.ITEM_TAGS_MAX)
    creditos: str | None = Field(default=None, max_length=limites.ITEM_CREDITOS_MAX)
    termos_de_uso: str | None = Field(default=None, max_length=limites.ITEM_DESCRICAO_MAX)
    extent: list[float] | None = None
    extent_origem: str | None = Field(default=None, pattern="^(dado|usuario|inquilino)$")
    categorias: list[str] | None = Field(default=None, max_length=limites.ITEM_CATEGORIAS_MAX)
    classificacao: dict[str, Any] | None = None
    url: str | None = Field(default=None, max_length=2048, pattern=r"^https?://")
    origem: str | None = Field(default=None, pattern="^(hospedado|referenciado)$")
    dados: dict[str, Any] | None = None
    protegido: bool | None = None
    status: str | None = Field(default=None, pattern="^(autoritativo|obsoleto|nenhum)$")
    versao_atual: int | None = None  # edição concorrente: se vier diferente do banco = 409 versao_conflito
    # L5-13: versão que o cliente LEU; diferente do banco = mesclagem por nó com a versão atual (409 só se o mesmo
    # nó mudou dos dois lados, com o documento atual e os ids em conflito no detalhe)
    base_versao: int | None = Field(default=None, ge=1)

    _t = field_validator("tags")(_tags)
    _e = field_validator("extent")(_extent)


class MoverEntrada(Modelo):
    pasta_id: str | None = Field(default=None, pattern=UUID_PADRAO)


class LoteEntrada(Modelo):
    ids: list[str] = Field(min_length=1, max_length=limites.LOTE_MAX)
    acao: str = Field(pattern="^(mover|apagar|restaurar|tags|categorias|proteger|desproteger|status|compartilhar)$")
    pasta_id: str | None = Field(default=None, pattern=UUID_PADRAO)
    tags: list[str] | None = Field(default=None, max_length=limites.ITEM_TAGS_MAX)
    de: str | None = Field(default=None, max_length=limites.TAG_MAX)
    para: str | None = Field(default=None, max_length=limites.TAG_MAX)
    categorias: list[str] | None = Field(default=None, max_length=limites.ITEM_CATEGORIAS_MAX)
    status: str | None = Field(default=None, pattern="^(autoritativo|obsoleto|nenhum)$")
    acesso: str | None = Field(default=None, pattern="^(privado|inquilino|publico)$")
    grupos: list[str] | None = Field(default=None, max_length=512)
    cascata: bool = False

    _t = field_validator("tags")(_tags)


class MiniaturaEntrada(Modelo):
    """Imagem em base64 (JSON: o CSRF sob cookie exige application/json; multipart entra com o L0-11)."""

    conteudo: str = Field(min_length=1, max_length=limites.MINIATURA_BYTES_MAX * 4 // 3 + 16)
    nome: str | None = Field(default=None, max_length=255)


class RestaurarVersaoEntrada(Modelo):
    comentario: str | None = Field(default=None, max_length=limites.VERSAO_COMENTARIO_MAX)


class RelacaoEntrada(Modelo):
    destino: str = Field(pattern=UUID_PADRAO)
    tipo: str = Field(min_length=1, max_length=40)
    posicao: int | None = None


class RelacoesEntrada(Modelo):
    relacoes: list[RelacaoEntrada] = Field(max_length=limites.RELACOES_POR_ORIGEM)


class CompartilhamentoEntrada(Modelo):
    acesso: str | None = Field(default=None, pattern="^(privado|inquilino|publico)$")
    grupos: list[str] | None = Field(default=None, max_length=512)
    destaques: list[str] | None = Field(default=None, max_length=24)
    aplicar_a_dependencias: list[str] | None = Field(default=None, max_length=limites.RELACOES_POR_ORIGEM)


class LinkEntrada(Modelo):
    nome: str | None = Field(default=None, max_length=128)
    expira_em: str | None = None
    itens_incluidos: list[str] | None = Field(default=None, max_length=limites.RELACOES_POR_ORIGEM)
    permite_download: bool = False


class TransferenciaEntrada(Modelo):
    ids: list[str] | None = Field(default=None, min_length=1, max_length=limites.LOTE_MAX)
    usuario_origem_id: int | None = None
    novo_dono_id: int
    simular: bool = True
    pastas: str = Field(default="manter", pattern="^(manter|unica)$")
    pasta_unica_nome: str | None = Field(default=None, min_length=1, max_length=limites.PASTA_NOME_MAX)
    adicionar_aos_grupos: bool = False
    forcar_parcial: bool = False


class PastaEntrada(Modelo):
    nome: str = Field(min_length=1, max_length=limites.PASTA_NOME_MAX)
    pai_id: str | None = Field(default=None, pattern=UUID_PADRAO)


class PastaEditar(Modelo):
    nome: str | None = Field(default=None, min_length=1, max_length=limites.PASTA_NOME_MAX)
    pai_id: str | None = Field(default=None, pattern=UUID_PADRAO)
    para_raiz: bool = False


class CategoriaNo(Modelo):
    id: str | None = Field(default=None, pattern=UUID_PADRAO)
    nome: str = Field(min_length=1, max_length=limites.CATEGORIA_NOME_MAX)
    codigo: str | None = Field(default=None, max_length=64)
    filhas: list["CategoriaNo"] = Field(default_factory=list)


class CategoriasEntrada(Modelo):
    arvore: list[CategoriaNo] = Field(max_length=900)


class ImportarCategorias(Modelo):
    modelo: str = Field(pattern="^(iso19115|inspire)$")


class EsvaziarEntrada(Modelo):
    ids: list[str] | None = Field(default=None, max_length=limites.LOTE_MAX)


# ---- saídas
class Item(Saida):
    id: str
    tipo: str
    familia: str
    titulo: str
    tags: list[str]
    dono: dict
    acesso: str
    protegido: bool
    pontuacao: int
    versao_atual: int


class Pagina(Saida):
    total: int
    itens: list[Any]
    proximo_cursor: str | None = None
    aproximado: bool | None = None


class Facetas(Saida):
    tipo: list[dict]
    familia: list[dict]
    tags: list[dict]
    dono: list[dict]
    status: list[dict]
    categoria: list[dict]
    acesso: list[dict]


class TipoItem(Saida):
    nome: str
    familia: str
    rotulo: str
    descricao: str
    esquema: dict
    esquema_versao: int
    icone: str
    modulo_front: str
    abre_em: list[str]
    tem_dado_fisico: bool
    linha_dona: str


class LoteSaida(Saida):
    feitos: int
    recusados: list[dict]


class Miniatura(Saida):
    miniatura: str
    sha256: str


class JobCriado(Saida):
    job_id: str


class Versao(Saida):
    versao: int
    sha256: str
    autor: dict | None
    rotulo: str | None
    comentario: str | None
    compactou: int
    criado_em: str | None


class VersaoCompleta(Versao):
    corpo: dict
    diff: list[dict] | None = None


class UsadoPor(Saida):
    id: str
    oculto: bool = False


class OrdemExclusao(Saida):
    ordem: list[dict]
    ocultos: int


class Compartilhamento(Saida):
    acesso: str
    grupos: list[dict]
    links: list[dict]
    publico_permitido: bool
    dependencias: list[dict]


class Link(Saida):
    id: str
    prefixo: str
    nome: str | None
    criado_em: str | None
    expira_em: str | None
    revogado_em: str | None
    acessos: int
    itens_incluidos: list[str]


class LinkCriado(Link):
    token: str
    url: str


class Compartilhado(Saida):
    item: dict
    itens_incluidos: list[dict]
    permite_download: bool


class Transferencia(Saida):
    plano: list[dict]
    total: int
    com_falha: int
    novo_dono: dict
    executado: bool
    transferidos: int


class Pasta(Saida):
    id: str
    nome: str
    pai_id: str | None
    profundidade: int
    ancestrais: list[str]
    itens_visiveis: int
    dono: dict
    criado_em: str | None


class PastaArvore(Pasta):
    filhas: list[Any] = []


class Categorias(Saida):
    arvore: list[dict]
    total: int
    maximo: int


class ImportadoCategorias(Saida):
    criadas: int
    existentes: int


class ObjetoAssinado(Saida):
    url: str
    expira_em: str
