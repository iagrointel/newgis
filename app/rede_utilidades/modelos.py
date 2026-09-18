"""Modelos de entrada e saída das rotas de rede de utilidades. O PACOTE em si não passa por pydantic: entra e
sai como bytes, validado pelo esquema JSON (`app/rede_utilidades/esquema.py`), porque a mensagem de erro
precisa apontar a linha do arquivo que a pessoa enviou."""

from typing import Any  # (entrega 10/09) faltava para o bloco recuperado abaixo

from pydantic import (
    BaseModel,
    ConfigDict,  # (entrega 10/09) faltava para o bloco recuperado abaixo
    Field,
)

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
    regras_ativas: bool
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
        default=None,
        pattern="^(conectado|subrede|lacos|caminho_curto|isolados|montante|jusante|isolamento)$")
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
    # isolamento (L4-02-c): categorias de rede cujos dispositivos podem ser abertos (vazio = o padrão do
    # motor, proteção e manobra), se a resposta traz também o que fica sem energia ALÉM dos dispositivos, e
    # se a barreira de condição ("dispositivo sem estado declarado não é ponto de corte") vale. A categoria
    # que representa a fonte é a mesma `categoria_controlador` de `isolados`.
    categorias_isolamento: list[str] = Field(default_factory=list, max_length=20)
    incluir_isolados: bool = False
    ignorar_inoperante: bool = True


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


# --- EPANET .inp (item L4-05-d-epanet-inp) -------------------------------------------------------------

class EpanetImportacao(BaseModel):
    id: str
    rede_id: str
    estado: str
    nome_arquivo: str | None
    crs_epsg: int | None
    arquivo_sha256: str
    arquivo_bytes_tamanho: int
    job_id: str | None
    contagens: dict | None
    avisos: list | None
    erro: str | None
    criado_em: str
    atualizado_em: str


class EpanetImportacaoAceita(BaseModel):
    importacao_id: str
    job_id: str


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


# --- diagrama de rede (item L4-04-d-diagrama-esquematico) -----------------------------------------------

class DiagramaEntrada(BaseModel):
    """Pedido de geração de diagrama. `origem` é validada em `diagrama._elementos_da_origem`, não aqui: as
    três formas (subrede, traçado, seleção) têm campos diferentes, e a mensagem de erro precisa dizer qual
    subrede/feição não existe NESTA rede — coisa que pydantic não sabe."""

    nome: str = Field(min_length=1, max_length=200)
    origem: dict = Field(default_factory=dict)
    modelo: str = Field(default="basico", min_length=1, max_length=60)
    layout: str | None = Field(default=None, max_length=40)


class DiagramaLayoutEntrada(BaseModel):
    layout: str = Field(min_length=1, max_length=40)


class DiagramaModeloEntrada(BaseModel):
    """Modelo (template) de diagrama do inquilino: as regras de construção e o layout padrão. As regras são
    validadas em `diagrama._validar_regras` contra o vocabulário fechado do módulo."""

    nome: str = Field(min_length=1, max_length=200)
    regras: list[dict] = Field(default_factory=list, max_length=20)
    layout: str = Field(min_length=1, max_length=40)


# ---------------------------------------------------------------------------------------------
# (entrega 10/09) União das definições que outros ramos acrescentaram a este mesmo arquivo e que a
# fusão descartou ao ficar com um lado só. Ordem preservada do ramo de origem.


# de wt/il402fresul
class CamadaDoTracadoEntrada(TracadoEntrada):
    """O mesmo pedido de traçado mais o TÍTULO da camada que vai guardar o resultado. Herda de
    `TracadoEntrada` de propósito: salvar como camada é traçar e guardar, nunca um pedido diferente."""
    titulo: str = Field(min_length=1, max_length=250)


# de wt/il405egasee — EpanetImportacao e EpanetImportacaoAceita já existem mais acima neste arquivo
# (item L4-05-d-epanet-inp, mesmos campos); a fusão de 11/09 removeu a repetição, não as classes.


# de wt/il405egasee
class ConferenciaEscoamento(BaseModel):
    """Resposta da conferência de escoamento por gravidade. `alterou_a_rede` é sempre falso: a conferência
    nomeia a divergência e nunca inverte o trecho."""

    total: int
    sob_pressao: int
    conferidos: int
    conformes: int
    com_testemunha_nas_estruturas: int
    percentual_concordancia: float | None
    alterou_a_rede: bool
    problemas: list[dict]


# de wt/il405egasee
class ConferenciaPressao(BaseModel):
    controladores: int
    controladores_conformes: int
    transicoes_sem_regulador: int
    tolerancia_m: float
    tiers: list[dict]
    alterou_a_rede: bool
    problemas: list[dict]


# de wt/il405egasee
class TeksiImportacaoResultado(BaseModel):
    rede_id: str
    sha256: str
    bytes: int
    contagens: dict
    gravadas: dict
    recusadas: list[dict]
    avisos: list[dict]


# de wt/il403dareas
MAX_POR_LOTE = 1000  # teto declarado de operações de cada tipo num applyEdits


# de wt/il403dareas
class FeicaoAdicionar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grupo: str = Field(min_length=1, max_length=62)
    tipo: int = Field(ge=1, le=32767)
    geometria: dict[str, Any] | None = None  # GeoJSON da geometria (Point/LineString, WGS84)
    atributos: dict[str, Any] = Field(default_factory=dict)
    terminal_inicio: str | None = Field(default=None, min_length=1, max_length=62)
    terminal_fim: str | None = Field(default=None, min_length=1, max_length=62)


# de wt/il403dareas
class FeicaoAtualizar(BaseModel):
    """Grupo e tipo NÃO mudam (mudança de classe é apagar + adicionar); só geometria, atributos e os
    terminais declarados nas pontas."""
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=36, max_length=36)
    geometria: dict[str, Any] | None = None
    atributos: dict[str, Any] | None = None
    terminal_inicio: str | None = Field(default=None, min_length=1, max_length=62)
    terminal_fim: str | None = Field(default=None, min_length=1, max_length=62)


# de wt/il403dareas
class AssociacaoAdicionar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: str = Field(pattern="^(contencao|estrutura)$")
    de: str = Field(min_length=36, max_length=36)
    para: str = Field(min_length=36, max_length=36)


# de wt/il403dareas
class AssociacoesLote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adicionar: list[AssociacaoAdicionar] = Field(default_factory=list, max_length=MAX_POR_LOTE)
    apagar: list[str] = Field(default_factory=list, max_length=MAX_POR_LOTE)


# de wt/il403dareas
class ApplyEditsEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adicionar: list[FeicaoAdicionar] = Field(default_factory=list, max_length=MAX_POR_LOTE)
    atualizar: list[FeicaoAtualizar] = Field(default_factory=list, max_length=MAX_POR_LOTE)
    apagar: list[str] = Field(default_factory=list, max_length=MAX_POR_LOTE)
    associacoes: AssociacoesLote = Field(default_factory=AssociacoesLote)


# de wt/il403dareas
class AtivacaoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ativa: bool


# de wt/il403dareas
class ApplyEditsResultado(BaseModel):
    rede_id: str
    regras_ativas: bool
    adicionadas: list[str]
    atualizadas: int
    apagadas: int
    associacoes_adicionadas: int
    associacoes_apagadas: int
    conexoes: int  # conexões derivadas novas (jj + je) gravadas neste lote
    area_sujas_criadas: int = 0  # item L4-03-d-areas-sujas-e-validacao: 1 por feição tocada com geometria


# de wt/il403dareas
class ValidacaoResultado(BaseModel):
    rede_id: str
    regras_ativas: bool
    conexoes_avaliadas: int
    associacoes_avaliadas: int
    total_erros: int
    erros: list[dict]  # cada erro traz codigo, mensagem e a lista de feições envolvidas


# de wt/il403dareas
class AtivacaoResultado(BaseModel):
    rede_id: str
    regras_ativas: bool


# de wt/il403dareas
class ImportacaoRegrasResultado(BaseModel):
    rede_id: str
    total: int
    sha256: str
    bytes: int


# --- áreas sujas e validação incremental (item L4-03-d-areas-sujas-e-validacao) -----------------------------


# de wt/il403dareas
class ValidacaoExtensaoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    extensao: dict[str, Any] | None = None  # GeoJSON de polígono; None = todas as áreas sujas ativas ("tudo")


# de wt/il403dareas
class ValidacaoExtensaoResultado(BaseModel):
    rede_id: str
    versao_edicao: int
    areas_processadas: int
    areas_ativas_restantes: int
    feicoes_em_escopo: int
    feicoes_total: int
    total_erros: int
    erros: list[dict]
    tempo_ms: float
    carga_1min: float
    ram_livre_gb: float
    medido_em: str


# de wt/il403dareas
class ModoTracadoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    modo: str = Field(pattern="^(avisar|bloquear)$")


# de wt/il403dareas
class ModoTracadoResultado(BaseModel):
    rede_id: str
    modo: str


# de wt/il403dareas — na fusão de 11/09 este resultado se chamava TracadoResultado e colidiu com o
# TracadoResultado do traçado de rede (item L4-02-a), de campos diferentes; o nome novo desempata os dois.
class TracadoAreaSujaResultado(BaseModel):
    rede_id: str
    cruza_area_suja: bool
    bloqueado: bool
    modo: str
    area_suja: dict | None = None


# de wt/il406dcateg
class CategoriasEntrada(BaseModel):
    categorias: list[str] = Field(min_length=0, max_length=64)


# de wt/il406dcateg
class RestricoesEntrada(BaseModel):
    restricoes: list[str] = Field(min_length=0, max_length=8)


# de wt/il406dcateg
class FeicaoEntrada(BaseModel):
    tipo_id: str
    codigo: str = Field(min_length=1, max_length=120)
    controlador_ativo: bool = False


# de wt/il406dcateg
class LigacaoEntrada(BaseModel):
    para_feicao_id: str


# de wt/il405gosmpo
class MunicipioGeoJson(BaseModel):
    """Polígono do recorte territorial em GeoJSON (EPSG:4326). Aceita Geometry, Feature ou
    FeatureCollection tal como vem da fonte (ex.: malha municipal do IBGE) — os campos extras
    (`geometry`, `features`, `properties`) passam intactos para o conector, que decide a forma."""

    model_config = ConfigDict(extra="allow")

    type: str = Field(min_length=1, max_length=40)


# de wt/il405gosmpo
class ImportacaoOsmEntrada(BaseModel):
    caminho: str = Field(min_length=1, max_length=2000)
    municipio: MunicipioGeoJson
    nome_municipio: str = Field(min_length=1, max_length=200)


# de wt/il405gosmpo
class ImportacaoOsmResultado(BaseModel):
    rede_id: str
    licenca: str
    aviso: str
    contagens: dict
    trechos_gerados: int
    fixacoes: int
    fora_do_limite: dict
    desvios: dict
    duracao_ms: int
    conferido: bool
    importacao_id: str | None


# de wt/il405gosmpo
class ImportacaoFicha(BaseModel):
    id: str
    fonte: str
    caminho: str
    distribuidora: str | None
    municipio: str | None
    sha256: str
    licenca: str | None
    aviso: str | None
    estado: str
    contagens: dict | None
    desvios: dict | None
    erro: str | None
    criado_em: str
    concluido_em: str | None


# de wt/il405gosmpo
class ImportacaoFichaLista(BaseModel):
    total: int
    itens: list[ImportacaoFicha]
