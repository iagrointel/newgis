"""Modelos pydantic da ficha do acervo (item L6-01-a-procedencia-acervo, estendido pelos itens
L6-01-d-ficha-fonte e L6-01-f-lgpd). Saída lê `plat.acervo_ficha` (migração 021) + `plat.acervo_endpoint`
(migração 036) + `plat.acervo_lgpd` (migração 037) — três views/tabelas SECURITY INVOKER que já filtram por
`licenca IS NOT NULL` (regra D17); o modelo só espelha o que elas devolvem, não filtra de novo.

Os 10 campos de procedência da hipótese do item L6-01-d (url, licença, frescor, data_dado, script_gerador,
sha256, método, confiança, limites, próxima_verificação) já existiam em `AcervoFicha` desde o item anterior
(L6-01-a-procedencia-acervo) — conferido por leitura antes de somar código; o que faltava era só
`endpoints`/`endpoints_total`/`endpoints_vivos` (acervo.endpoint, "confirmados e vivos") e `completude_texto`
("x/10" explícito, não só o número cru). `limites` já É "o que este dado não sustenta" em conteúdo real
(exemplos lidos em acervo.fonte.limites: "0 vendidos lidos; só o tempo resolve", "só fluxo, sem estoque
RAIS") — não duplicado sob outro nome para não abrir campo que o adversário possa achar "inventado"."""

from pydantic import BaseModel, ConfigDict, Field


class Saida(BaseModel):
    model_config = ConfigDict(extra="allow")


class AcervoCartao(Saida):
    fonte_id: str
    nome: str
    orgao: str | None = None
    dominio: str
    licenca: str
    frescor: str | None = None
    numero_tabelas: int
    registros_estimados: int
    procedencia_pontuacao: float | None = None
    proxima_verificacao: str | None = None
    risco_pii: bool = False
    risco_pii_motivo: str | None = None


class AcervoEndpoint(Saida):
    url: str
    origem: str | None = None
    http: str | None = None
    content_type: str | None = None
    bytes: int | None = None
    ms: int | None = None
    testado_em: str | None = None
    confirmado: bool | None = None
    vivo: bool


class AcervoFicha(AcervoCartao):
    url: str | None = None
    url_http: str | None = None
    url_conferida_em: str | None = None
    data_dado: str | None = None
    data_acesso: str | None = None
    script_gerador: str | None = None
    sha256: str | None = None
    comando_reexecucao: str | None = None
    metodo: str | None = None
    confianca: str | None = None
    limites: str | None = None
    bytes: int | None = None
    procedencia_campos: int | None = None
    procedencia_campos_possiveis: int | None = None
    atualizado_em: str | None = None
    # item L6-01-d: endpoints testados por HTTP (acervo.endpoint), ordenados vivo-primeiro
    endpoints: list[AcervoEndpoint] = []
    endpoints_total: int = 0
    endpoints_confirmados_vivos: int = 0
    # completude por extenso ("4,5/10"), nunca só o número cru — ausência é "não registrado", nunca 0/10 silencioso
    completude_texto: str | None = None


class AcervoPagina(Saida):
    total: int
    itens: list[AcervoCartao]


class AcervoDominio(Saida):
    dominio: str
    fontes: int


class AcervoAdicionarEntrada(BaseModel):
    """Corpo opcional de POST /api/acervo/{fonte_id}/adicionar (item L6-01-f-lgpd). Fonte marcada em
    `plat.acervo_lgpd.risco_pii` exige `confirma_risco_pii=true` explícito; sem isso a rota recusa com 409
    antes de criar qualquer item. Default false: nunca se confirma sozinho."""

    model_config = ConfigDict(extra="forbid")
    confirma_risco_pii: bool = False


class AcervoCamadaPublicada(Saida):
    """Uma view de `plat_acervo` (item L6-01-b). `assinada` é deste inquilino: a RLS de
    plat.acervo_assinatura já recorta o LEFT JOIN, então nunca vaza a assinatura de outro.
    Item L6-01-e: os campos `licenca_*` são o que a tela mostra e o que o aceite grava — o
    `licenca_sha256` é o que o chamador ecoa no POST de assinatura para provar que clicou no texto que o
    servidor gravou. Todos None quando a fonte não tem licença curada (aí a assinatura é recusada)."""

    view_nome: str
    acervo_camada_id: str
    fonte_id: str
    schema_origem: str
    tabela_origem: str
    coluna_geom: str
    srid: int
    colunas: list[str]
    linhas_exatas: int | None = None
    tipo_geom: str | None = None
    assinada: bool
    licenca_tipo: str | None = None
    licenca_texto: str | None = None
    licenca_url: str | None = None
    licenca_sha256: str | None = None


class AcervoCamadaPagina(Saida):
    total: int
    camadas: list[AcervoCamadaPublicada]


class AcervoFeicoes(Saida):
    """GeoJSON de uma camada publicada. `features` fica vazio quando o filtro não achou nada — nunca quando
    falta assinatura: aí a rota já devolveu 403 antes de consultar."""

    type: str
    camada: str
    total: int
    features: list[dict]


class AcervoAssinaturaEntrada(BaseModel):
    """Corpo OBRIGATÓRIO de POST /api/acervo/camadas/{camada}/assinatura (item L6-01-e). O clique na
    licença chega como `aceite_licenca=true` + o sha256 do texto que estava na tela: o servidor só grava se
    o sha bater com o texto atual da fonte — sha defasado é 409 (a tela relê e mostra o texto novo).
    Default False/"": nunca se aceita sozinho."""

    model_config = ConfigDict(extra="forbid")
    aceite_licenca: bool = False
    licenca_sha256: str = Field(default="", max_length=64)


class AcervoAssinaturaSaida(Saida):
    """Resposta do POST de assinatura: o que ficou gravado (quem/quando vivem em plat.acervo_assinatura;
    `assinado_em` volta aqui para a tela mostrar sem nova consulta)."""

    camada: str
    assinada: bool
    licenca_tipo: str | None = None
    licenca_sha256: str | None = None
    assinado_em: str | None = None


class AcervoUsoLinha(Saida):
    """Uso de uma camada pelo inquilino no recorte pedido (dia ou mês)."""

    view_nome: str | None = None
    acervo_camada_id: str
    consultas: int
    feicoes: int
    dias: int | None = None  # só no recorte mensal: em quantos dias do mês houve leitura


class AcervoUsoDia(Saida):
    dia: str
    total_consultas: int
    total_feicoes: int
    camadas: list[AcervoUsoLinha]


class AcervoUsoMensal(Saida):
    """Relatório mensal de uso do acervo pelo inquilino — entrada do item L7-09."""

    ano: int
    mes: int
    total_consultas: int
    total_feicoes: int
    camadas: list[AcervoUsoLinha]
