"""Modelos pydantic das rotas de identidade: corpos de entrada e `response_model` de saída (o OpenAPI comitado
carrega o esquema; o teste cruzado lê o arquivo). Nomes em português (ADR 0001 seção 12)."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app import limites

PERFIL = Field(pattern="^(admin|editor|visualizador|campo)$")


class Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Saida(BaseModel):
    model_config = ConfigDict(extra="allow")


# ---- entradas
class LoginEntrada(Modelo):
    inquilino: str = Field(min_length=1, max_length=40)
    login: str = Field(min_length=1, max_length=128)
    senha: str = Field(min_length=1, max_length=4096)


class Login2FAEntrada(Modelo):
    desafio: str = Field(min_length=1, max_length=128)
    codigo: str | None = Field(default=None, max_length=16)
    codigo_recuperacao: str | None = Field(default=None, max_length=16)


class SenhaEntrada(Modelo):
    atual: str = Field(max_length=4096)
    nova: str = Field(max_length=4096)


class CodigoEntrada(Modelo):
    codigo: str = Field(max_length=16)


class SenhaCodigoEntrada(Modelo):
    senha: str = Field(max_length=4096)
    codigo: str = Field(max_length=16)


class SenhaSoEntrada(Modelo):
    senha: str = Field(max_length=4096)


class PapelEntrada(Modelo):
    nome: str = Field(min_length=1, max_length=limites.PAPEL_NOME_MAX)
    descricao: str | None = Field(default=None, max_length=limites.PAPEL_DESCRICAO_MAX)
    privilegios: list[str] = Field(min_length=1, max_length=64)


class UsuarioCriar(Modelo):
    login: str = Field(min_length=1, max_length=128, pattern=r"^[a-z0-9][a-z0-9._@-]*$")
    nome: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=254)
    perfil: str = PERFIL
    papel_id: int | None = None


class UsuarioEditar(Modelo):
    nome: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=254)
    perfil: str | None = Field(default=None, pattern="^(admin|editor|visualizador|campo)$")
    papel_id: int | None = None
    ativo: bool | None = None


class LoteEntrada(Modelo):
    ids: list[int] = Field(min_length=1, max_length=limites.LOTE_MAX * 10)
    acao: str = Field(pattern="^(perfil|papel|desabilitar|reabilitar)$")
    perfil: str | None = Field(default=None, pattern="^(admin|editor|visualizador|campo)$")
    papel_id: int | None = None


class GrupoCriar(Modelo):
    nome: str = Field(min_length=1, max_length=limites.GRUPO_NOME_MAX)
    resumo: str | None = Field(default=None, max_length=limites.GRUPO_RESUMO_MAX)
    tags: list[str] = Field(default_factory=list, max_length=limites.GRUPO_TAGS_MAX)
    visibilidade: str = Field(default="membros", pattern="^(membros|inquilino)$")
    entrada: str = Field(default="convite", pattern="^(convite|pedido|livre)$")
    contribuicao: str = Field(default="todos", pattern="^(todos|dono_gerentes)$")
    atualizacao_compartilhada: bool = False
    administrativo: bool = False
    protegido: bool = False


class GrupoEditar(Modelo):
    nome: str | None = Field(default=None, min_length=1, max_length=limites.GRUPO_NOME_MAX)
    resumo: str | None = Field(default=None, max_length=limites.GRUPO_RESUMO_MAX)
    tags: list[str] | None = Field(default=None, max_length=limites.GRUPO_TAGS_MAX)
    visibilidade: str | None = Field(default=None, pattern="^(membros|inquilino)$")
    entrada: str | None = Field(default=None, pattern="^(convite|pedido|livre)$")
    contribuicao: str | None = Field(default=None, pattern="^(todos|dono_gerentes)$")
    atualizacao_compartilhada: bool | None = None
    administrativo: bool | None = None
    protegido: bool | None = None
    dono_id: int | None = None


class ConviteEntrada(Modelo):
    usuario_id: int
    papel: str = Field(default="membro", pattern="^(gerente|membro)$")


class PapelMembroEntrada(Modelo):
    papel: str = Field(pattern="^(gerente|membro)$")


class TokenCriar(Modelo):
    nome: str = Field(min_length=1, max_length=128)
    escopos: list[str] = Field(min_length=1, max_length=32)
    restricao: dict[str, list[str]] | None = None
    validade_dias: int | None = Field(default=None, ge=0, le=100_000)


class InquilinoCriar(Modelo):
    slug: str = Field(min_length=2, max_length=39)
    nome: str = Field(min_length=1, max_length=200)
    config: dict[str, Any] | None = None
    admin_login: str = Field(min_length=1, max_length=128, pattern=r"^[a-z0-9][a-z0-9._@-]*$")
    admin_nome: str = Field(min_length=1, max_length=200)


# ---- saídas
class Ok(Saida):
    ok: bool = True


class Usuario(Saida):
    id: int
    login: str
    nome: str
    perfil: str
    papel: dict | None = None
    ativo: bool
    origem: str
    ultimo_login: str | None = None
    criado_em: str | None = None
    email: str | None = None
    superadmin: bool | None = None
    totp_ativo: bool | None = None
    trocar_senha: bool | None = None
    bloqueado_ate: str | None = None
    ultimo_ip: str | None = None
    codigos_recuperacao_restantes: int | None = None


class Eu(Usuario):
    privilegios: list[str]
    inquilino: dict
    pendencias: list[str]
    sessao: dict | None = None
    token: dict | None = None
    idioma_preferido: str
    unidades: str
    formato_data: str
    visibilidade_perfil: str
    foto_url: str | None = None


class LoginSaida(Saida):
    ok: bool
    usuario: Eu | None = None
    exige_2fa: bool | None = None
    desafio: str | None = None
    recuperacao_disponivel: bool | None = None


class Provedores(Saida):
    inquilino: dict
    provedores: list[dict]
    login_local: bool


class Sessao(Saida):
    id: str
    criado_em: str | None
    ultimo_uso: str | None
    expira_em: str | None
    ip: str | None
    agente: str | None
    atual: bool


class Iniciar2FA(Saida):
    segredo: str
    uri: str
    qr_svg: str


class CodigosRecuperacao(Saida):
    codigos_recuperacao: list[str]


class Convite(Saida):
    grupo: dict
    papel: str
    convidado_por: dict | None
    criado_em: str | None


class Privilegio(Saida):
    nome: str
    grupo: str
    descricao: str
    administrativo: bool


class Papel(Saida):
    id: int
    nome: str
    descricao: str | None
    perfil_minimo: str
    privilegios: list[str]
    usuarios: int
    criado_em: str | None = None


class Papeis(Saida):
    perfis: list[dict]
    personalizados: list[Papel]


class Pagina(Saida):
    total: int
    itens: list[Any]


class UsuarioCriado(Saida):
    usuario: Usuario
    senha_temporaria: str


class SenhaTemporaria(Saida):
    senha_temporaria: str


class LoteSaida(Saida):
    alterados: int
    recusados: list[dict]


class Grupo(Saida):
    id: str
    nome: str
    resumo: str | None
    tags: list[str]
    visibilidade: str
    entrada: str
    contribuicao: str
    atualizacao_compartilhada: bool
    administrativo: bool
    protegido: bool
    dono: dict
    membros: int
    meu_papel: str | None
    meu_estado: str | None
    criado_em: str | None = None


class Membro(Saida):
    usuario: dict
    papel: str
    estado: str
    criado_em: str | None


class Estado(Saida):
    estado: str


class Token(Saida):
    id: int
    nome: str
    prefixo: str
    escopos: list[str]
    restricao: dict
    criado_em: str | None
    expira_em: str | None
    revogado_em: str | None
    ultimo_uso: str | None
    ultimo_ip: str | None
    usos: int = 0
    dono: dict
    renovado_por: int | None
    acessos_30d: int | None = None
    ultimo_status: int | None = None


class TokenCriado(Saida):
    token: str
    id: int
    prefixo: str
    escopos: list[str]
    expira_em: str | None
    antigo_expira_em: str | None = None


class Inquilino(Saida):
    id: int
    slug: str
    nome: str
    ativo: bool
    usuarios: int
    criado_em: str | None
    ultimo_acesso: str | None


class InquilinoCriado(Saida):
    id: int
    slug: str
    admin: dict
    senha_temporaria: str
