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
    tipo: str = Field(pattern="^(conectado|subrede)$")
    pontos_partida: list[PontoTracado] = Field(min_length=1, max_length=50)
    barreiras: list[PontoTracado] = Field(default_factory=list, max_length=200)


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
