"""Modelos de entrada e saída das rotas de rede de utilidades. O PACOTE em si não passa por pydantic: entra e
sai como bytes, validado pelo esquema JSON (`app/rede_utilidades/esquema.py`), porque a mensagem de erro
precisa apontar a linha do arquivo que a pessoa enviou."""

from pydantic import BaseModel, Field

from app.rede_utilidades.esquema import DISCIPLINAS


class RedeEntrada(BaseModel):
    nome: str = Field(min_length=1, max_length=200)
    disciplina: str = Field(pattern="^(" + "|".join(DISCIPLINAS) + ")$")
    descricao: str | None = Field(default=None, max_length=2000)
    # cláusula 1 do portão L4-01-b: tolerância de coincidência é parâmetro DA REDE, não da instalação.
    tolerancia_m: float = Field(default=0.05, gt=0, le=10)


class Rede(BaseModel):
    id: str
    nome: str
    disciplina: str
    descricao: str | None
    tolerancia_m: float
    pacote: dict | None
    contagens: dict
    dono: dict
    criado_em: str
    atualizado_em: str


class RedePagina(BaseModel):
    total: int
    itens: list[Rede]


class PacoteInstalado(BaseModel):
    codigo: str
    nome: str
    versao: str
    disciplina: str
    descricao: str | None = None
    fonte: str | None = None
    bytes: int
    sha256: str
    contagens: dict


class PacoteInstaladoLista(BaseModel):
    total: int
    itens: list[PacoteInstalado]


class ImportacaoResultado(BaseModel):
    rede_id: str
    codigo: str
    versao: str
    esquema_versao: int
    sha256: str
    bytes: int
    contagens: dict


# --- topologia derivada (item L4-01-b-topologia-derivada) -------------------------------------------------

class FeicaoPontoEntrada(BaseModel):
    tipo_codigo: int = Field(ge=1, le=32767)
    grupo: str = Field(min_length=1, max_length=63)
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    fase_bitmask: int | None = Field(default=None, ge=0, le=7)
    atributos: dict = Field(default_factory=dict)


class FeicaoLinhaEntrada(BaseModel):
    tipo_codigo: int = Field(ge=1, le=32767)
    grupo: str = Field(min_length=1, max_length=63)
    coordenadas: list[tuple[float, float]] = Field(min_length=2, max_length=2000)
    fase_bitmask: int | None = Field(default=None, ge=0, le=7)
    atributos: dict = Field(default_factory=dict)


class Feicao(BaseModel):
    id: str
    tipo_id: str
    fase_bitmask: int | None
    atributos: dict
    criado_em: str


class TopologiaResumo(BaseModel):
    rede_id: str
    tolerancia_m: float
    nos: int
    arestas: int
    nos_orfaos: int
    arestas_sem_no: int
    duracao_ms: int
    construido_em: str


class TopoNo(BaseModel):
    id: str
    papel: str
    tipo_id: str | None
    origem_id: str | None
    terminal_num: int | None
    grau: int
    lon: float
    lat: float


# --- traçado (item L4-02-a-conectado-e-subrede) -------------------------------------------------------

class PontoTracado(BaseModel):
    """Um ponto de partida ou barreira: por feição (`feicao_id` + `terminal`, obrigatório quando a feição tem
    mais de um terminal) OU por coordenada (`lon`/`lat`, com `tolerancia_m` própria ou a da rede)."""
    feicao_id: str | None = None
    terminal: int | None = Field(default=None, ge=1, le=8)
    lon: float | None = Field(default=None, ge=-180, le=180)
    lat: float | None = Field(default=None, ge=-90, le=90)
    tolerancia_m: float | None = Field(default=None, gt=0, le=1000)


class TracadoEntrada(BaseModel):
    """`tipo=montante|jusante` (item L4-18) exige `pontos_partida` e anda pela direção de fluxo declarada em
    atributo; `tipo=conectado|subrede` (item L4-02-a) exige `pontos_partida`; `tipo=caminho_curto` (item L4-02-d)
    exige um único ponto em `pontos_partida` (a origem) e `destino`; `tipo=lacos` e `tipo=isolados` não
    exigem `pontos_partida` (operam sobre a rede inteira) — a validação por tipo é feita na rota, não aqui,
    porque cada tipo tem uma exigência diferente sobre a MESMA lista."""
    tipo: str | None = Field(
        default=None, pattern="^(conectado|subrede|lacos|caminho_curto|isolados|montante|jusante)$")
    # item L4-02-e: quando vem `config_id`, o TIPO e todo o resto do pedido saem da configuração salva
    # (`plat.rede_config_tracado`) e só os pontos de partida e as barreiras pontuais continuam vindo daqui.
    config_id: str | None = Field(default=None, min_length=36, max_length=36)
    pontos_partida: list[PontoTracado] = Field(default_factory=list, max_length=50)
    destino: PontoTracado | None = None
    barreiras: list[PontoTracado] = Field(default_factory=list, max_length=200)
    # caminho_curto (L4-02-d): atributo de custo (None = comprimento geodésico) e k alternativas (pgr_ksp).
    atributo_custo: str | None = Field(default=None, max_length=63)
    k: int = Field(default=1, ge=1, le=10)
    # isolados (L4-02-d): categoria de rede que representa o "controlador" (padrão 'fonte').
    categoria_controlador: str = Field(default="fonte", min_length=1, max_length=63)
    # montante/jusante (L4-02-b): de onde vem o SENTIDO. 'auto' = do controlador de subrede quando a rede tem
    # controlador com nó na topologia, do atributo `direcao_fluxo` quando não tem; 'controlador' e 'atributo'
    # impõem um dos dois. Ignorado pelos demais tipos de traçado.
    origem_direcao: str = Field(default="auto", pattern="^(auto|controlador|atributo)$")


class ElementoTracado(BaseModel):
    feicao_id: str
    tipo_id: str | None
    grupo: str | None
    tipo_chave: str | None
    tipo_nome: str | None
    terminal: int | None


class TracadoResultado(BaseModel):
    tipo: str
    elementos: list[ElementoTracado]
    contagem: int
    nos_alcancados: int
    geometria: dict | None
    duracao_ms: int


class TopoArestaModelo(BaseModel):
    id: str
    grupo_id: str
    tipo_id: str | None
    origem_id: str
    no_origem_id: str | None
    no_destino_id: str | None
    comprimento_m: float
    fase_bitmask: int | None
    atributos: dict


# --- rede simples (item L4-18-rede-simples-trace-network) ---------------------------------------------

class AtributoRede(BaseModel):
    """Atributo DE REDE: um campo da camada de origem que o inquilino declara como parte do modelo de rede
    (é o que o traçado pode usar como custo em `caminho_curto`). Declarar é o que separa um campo qualquer
    da camada de um atributo de rede."""
    nome: str = Field(min_length=1, max_length=63)
    tipo_dado: str = Field(default="texto", pattern="^(texto|inteiro|real|data|booleano)$")
    de: str = Field(default="linha", pattern="^(linha|ponto)$")


class RedeSimplesEntrada(BaseModel):
    """Criação de uma rede simples a partir de duas camadas do inquilino. `camada_ponto_id` é opcional: uma
    rede simples pode ser só de trechos (hidrografia sem camada de nó, por exemplo). `campo_direcao` é o
    NOME do campo da camada de linhas que carrega a direção de fluxo, e `mapa_direcao` traduz os valores
    desse campo (em minúsculas, sem espaço nas pontas) para o vocabulário fechado
    digitalizada/contra/indeterminada; sem `campo_direcao`, toda a rede é lida como digitalizada."""
    nome: str = Field(min_length=1, max_length=200)
    disciplina: str = Field(pattern="^(" + "|".join(DISCIPLINAS) + ")$")
    descricao: str | None = Field(default=None, max_length=2000)
    tolerancia_m: float = Field(default=0.05, gt=0, le=10)
    camada_linha_id: str = Field(min_length=36, max_length=36)
    camada_ponto_id: str | None = Field(default=None, min_length=36, max_length=36)
    campo_direcao: str | None = Field(default=None, min_length=1, max_length=63)
    mapa_direcao: dict[str, str] = Field(default_factory=dict)
    atributos_rede: list[AtributoRede] = Field(default_factory=list, max_length=50)


# --- controlador de subrede e tiers (item L4-04-a-controladores-e-tiers) --------------------------------

class ControladorEntrada(BaseModel):
    """Marca o terminal de um dispositivo como controlador de uma subrede. `terminal` é obrigatório quando o
    tipo de ativo declara mais de um terminal no pacote. `nome` é o nome DO CONTROLADOR (único dentro do
    tier); sem ele, vale o nome da subrede."""
    feicao_id: str = Field(min_length=36, max_length=36)
    terminal: int | None = Field(default=None, ge=1, le=8)
    subrede: str = Field(min_length=1, max_length=200)
    tier: str = Field(min_length=1, max_length=63)
    papel: str = Field(default="fonte", pattern="^(fonte|sumidouro)$")
    nome: str | None = Field(default=None, min_length=1, max_length=200)


class Controlador(BaseModel):
    id: str
    nome: str
    papel: str
    origem: str
    subrede_id: str
    subrede: str
    tier: str
    tier_nome: str
    tier_tipo: str
    tier_ordem: int
    feicao_id: str | None
    terminal: int | None
    tipo_id: str | None
    grupo: str | None
    tipo_chave: str | None
    tipo_nome: str | None
    no_id: str | None
    lon: float
    lat: float


class PropagadoresEntrada(BaseModel):
    """Atributos que um tier propaga do controlador para os elementos da subrede (item L4-04-b). Lista vazia
    é legítima: significa "este tier não propaga nada"."""

    propagadores: list[str] = Field(default_factory=list, max_length=20)


# --- configuração de traçado (item L4-02-e-configuracoes-de-tracado) ------------------------------------

class ConfigTracadoEntrada(BaseModel):
    """O documento salvo que preenche o pedido de traçado. `config` é validado contra o catálogo DA REDE em
    `config_tracado.validar_documento` (atributo, categoria, grupo, tipo, operador, função e tipo de
    resultado), e não por pydantic: a mensagem de erro precisa dizer qual atributo a rede não tem."""

    codigo: str = Field(min_length=1, max_length=63, pattern="^[a-z0-9][a-z0-9_-]{0,62}$")
    nome: str = Field(min_length=1, max_length=200)
    descricao: str | None = Field(default=None, max_length=2000)
    tipo: str = Field(pattern="^(conectado|subrede|montante|jusante)$")
    config: dict = Field(default_factory=dict)
    compartilhada: bool = True


class ConfigTracado(BaseModel):
    id: str
    rede_id: str
    codigo: str
    nome: str
    descricao: str | None
    tipo: str
    config: dict
    origem: str
    compartilhada: bool
    dono_id: int | None
    criado_em: str
    atualizado_em: str


class ConfigTracadoPagina(BaseModel):
    total: int
    itens: list[ConfigTracado]
