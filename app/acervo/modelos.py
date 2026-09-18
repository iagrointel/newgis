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

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,  # (entrega 10/09) faltava para o bloco recuperado abaixo
)

from app import limites  # (entrega 10/09) faltava para o bloco recuperado abaixo


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
    # item L6-01-h: aviso de frescor agregado das camadas EXPOSTAS da fonte (plat.v_acervo_fonte_frescor).
    # Fonte sem camada exposta fica com camadas_expostas = 0 e verificacao_vencida = false — "não se aplica",
    # nunca "em dia" (a tela distingue os dois pelo número de camadas).
    verificacao_vencida: bool = False
    motivo_vencida: str | None = None
    camadas_expostas: int = 0
    camadas_vencidas: int = 0
    verificada_em: str | None = None
    endpoints_mortos: int = 0
    # item L6-01-c: tipo da licença CURADA (vocabulário fechado do L6-01-g, plat.acervo_licenca). É ele que
    # aciona o aviso de atribuição obrigatória (ODbL/CC-BY-SA) na tela. NUNCA é inferido do texto livre de
    # `licenca`: medido, o texto livre de fontes como `aneel` diz "licença não declarada" mesmo quando a
    # curadoria por HTTP achou ODbL de verdade. Sem curadoria, fica None — "não curada", nunca um padrão.
    licenca_curada_tipo: str | None = None


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


class AcervoCamadaNaFicha(Saida):
    """Uma camada EXPOSTA da fonte, como a ficha a mostra (itens L6-01-c e L6-01-j-multi-servidor).
    `origem` é o texto que a tela escreve: camada lida por FDW de outro servidor da casa sai como
    "servidor remoto (<nome>)", por extenso — nunca um código que o leitor tenha de decifrar."""

    acervo_camada_id: str
    servidor: str
    schema_nome: str
    tabela: str
    estado: str
    modo_acesso: str
    origem: str
    linhas_exatas: int | None = None
    fdw_tabela: str | None = None
    aviso: str | None = None


class AcervoMeuMapaCamada(Saida):
    """Camada do acervo já adicionada pelo inquilino (legenda do mapa, item L6-01-c). `licenca_curada_tipo`
    é o valor CONGELADO no item no dia em que foi adicionado, não o de hoje: a legenda mostra a licença sob
    a qual a camada entrou no mapa."""

    item_id: str
    # opcional de proposito: item de protocolo `acervo` sem `fonte_id` nos parametros e um item MALFORMADO,
    # e a legenda tem de mostra-lo assim (com o campo vazio) em vez de sumir com ele ou derrubar a rota com
    # um 500 de validacao. Some-lo seria esconder o defeito de quem precisa conserta-lo.
    fonte_id: str | None = None
    titulo: str
    licenca_curada_tipo: str | None = None
    licenca: str | None = None
    dominio: str | None = None
    adicionado_em: str | None = None


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
    # item L6-01-j: as camadas EXPOSTAS da fonte, com o servidor de onde cada uma é lida
    camadas: list[AcervoCamadaNaFicha] = []


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


# ---------------------------------------------------------------- frescor (item L6-01-h-frescor-verificacao)
class AcervoCamadaFrescor(Saida):
    """Uma camada do registro com o estado de verificação. `linhas_exatas` é NULL quando a contagem não coube
    no prazo de 25 s — a tela escreve "não contado no prazo", nunca zero, e `reltuples` não aparece aqui."""

    acervo_camada_id: str
    fonte_id: str
    schema_nome: str
    tabela: str
    estado: str
    fonte_nome: str | None = None
    fonte_dominio: str | None = None
    fonte_licenca: str | None = None
    fonte_frescor: str | None = None
    proxima_verificacao: str | None = None
    verificada_em: str | None = None
    contagem_estado: str | None = None
    linhas_exatas: int | None = None
    linhas_anteriores: int | None = None
    variacao_pct: float | None = None
    mudanca_relevante: bool | None = None
    hash_estado: str | None = None
    endpoints_testados: int = 0
    endpoints_mortos: int = 0
    endpoint_morto: bool = False
    prazo_da_fonte_vencido: bool = False
    nunca_verificada: bool = True
    verificacao_antiga: bool = False
    verificacao_vencida: bool = False
    motivo_vencida: str | None = None


class AcervoCamadaFrescorPagina(Saida):
    total: int
    vencidas: int
    itens: list[AcervoCamadaFrescor]


class AcervoVerificacao(Saida):
    verificada_em: str
    contagem_estado: str
    linhas_exatas: int | None = None
    linhas_anteriores: int | None = None
    variacao_pct: float | None = None
    mudanca_relevante: bool = False
    hash_estado: str
    hash_valor: str | None = None
    duracao_ms: int = 0
    execucao_id: int | None = None


class AcervoVerificacaoHistorico(Saida):
    camada: AcervoCamadaFrescor
    total: int
    verificacoes: list[AcervoVerificacao]


class AcervoMudanca(Saida):
    acervo_camada_id: str
    fonte_id: str
    schema_nome: str
    tabela: str
    verificada_em: str
    linhas_anteriores: int | None = None
    linhas_exatas: int | None = None
    variacao_pct: float | None = None
    execucao_id: int | None = None


class AcervoMudancaPagina(Saida):
    total: int
    limiar_pct: float
    itens: list[AcervoMudanca]


class AcervoExecucao(Saida):
    id: int
    iniciada_em: str
    concluida_em: str | None = None
    duracao_ms: int | None = None
    camadas_expostas: int = 0
    camadas_verificadas: int = 0
    camadas_nao_contadas: int = 0
    endpoints_testados: int = 0
    endpoints_responderam: int = 0
    mudancas: int = 0


class AcervoExecucaoPagina(Saida):
    total: int
    itens: list[AcervoExecucao]


# ---------------------------------------------------------------------------------------------
# (entrega 10/09) União das definições que outros ramos acrescentaram a este mesmo arquivo e que a
# fusão descartou ao ficar com um lado só. Ordem preservada do ramo de origem.


# de wt/cxux18
class AcervoCamadaMapa(Saida):
    """Uma camada do acervo já adicionada ao catálogo do inquilino, como a legenda do mapa precisa dela (item
    L6-01-c-tela-acervo). Os campos vêm do instantâneo gravado em `dados.parametros` na hora de adicionar, não
    de uma nova consulta ao acervo: a legenda mostra a licença sob a qual o dado foi adicionado."""

    item_id: str
    titulo: str
    fonte_id: str
    dominio: str | None = None
    licenca: str | None = None
    licenca_curada_tipo: str | None = None


# de wt/il301gtelam
class AcervoCamadaPublicada(Saida):
    """Uma view de `plat_acervo` (item L6-01-b). `assinada` é deste inquilino: a RLS de
    plat.acervo_assinatura já recorta o LEFT JOIN, então nunca vaza a assinatura de outro."""

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


# de wt/il301gtelam
class AcervoCamadaPagina(Saida):
    total: int
    camadas: list[AcervoCamadaPublicada]


# de wt/il301gtelam
class AcervoFeicoes(Saida):
    """GeoJSON de uma camada publicada. `features` fica vazio quando o filtro não achou nada — nunca quando
    falta assinatura: aí a rota já devolveu 403 antes de consultar."""

    type: str
    camada: str
    total: int
    features: list[dict]


# de wt/cx5l601i
class AcervoArquivo(Saida):
    caminho: str
    nome: str | None = None
    tipo: str                      # raster | vetor
    extensao: str
    bytes: int | None = None
    sha256: str | None = None
    feicoes: int | None = None
    srid: str | None = None
    tipo_geom: str | None = None
    fonte_id: str | None = None
    fonte_nome: str | None = None
    orgao: str | None = None
    dominio: str | None = None
    licenca: str | None = None
    publicavel: bool = False       # D17: sem licença escrita o item nasce privado e não se compartilha
    exposto: bool = False
    item_id: str | None = None
    no_disco: bool | None = None   # o arquivo do registro existe nesta instalação


# de wt/cx5l601i
class AcervoArquivosPagina(Saida):
    total: int
    itens: list[AcervoArquivo]
    raiz_configurada: bool
    rasters: int
    vetores: int


# de wt/cx5l601i
class AcervoExporEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    caminhos: list[str] = Field(min_length=1, max_length=limites.ACERVO_ARQUIVO_LOTE_MAX)
    titulo: str | None = Field(default=None, max_length=200)


# de wt/cx5l601i
class AcervoExporSaida(Saida):
    jobs: list[dict]
    recusados: list[dict]


# de wt/il601eassin
class AcervoAssinaturaEntrada(BaseModel):
    """Corpo OBRIGATÓRIO de POST /api/acervo/camadas/{camada}/assinatura (item L6-01-e). O clique na
    licença chega como `aceite_licenca=true` + o sha256 do texto que estava na tela: o servidor só grava se
    o sha bater com o texto atual da fonte — sha defasado é 409 (a tela relê e mostra o texto novo).
    Default False/"": nunca se aceita sozinho."""

    model_config = ConfigDict(extra="forbid")
    aceite_licenca: bool = False
    licenca_sha256: str = Field(default="", max_length=64)


# de wt/il601eassin
class AcervoAssinaturaSaida(Saida):
    """Resposta do POST de assinatura: o que ficou gravado (quem/quando vivem em plat.acervo_assinatura;
    `assinado_em` volta aqui para a tela mostrar sem nova consulta)."""

    camada: str
    assinada: bool
    licenca_tipo: str | None = None
    licenca_sha256: str | None = None
    assinado_em: str | None = None


# de wt/il601eassin
class AcervoUsoLinha(Saida):
    """Uso de uma camada pelo inquilino no recorte pedido (dia ou mês)."""

    view_nome: str | None = None
    acervo_camada_id: str
    consultas: int
    feicoes: int
    dias: int | None = None  # só no recorte mensal: em quantos dias do mês houve leitura


# de wt/il601eassin
class AcervoUsoDia(Saida):
    dia: str
    total_consultas: int
    total_feicoes: int
    camadas: list[AcervoUsoLinha]


# de wt/il601eassin
class AcervoUsoMensal(Saida):
    """Relatório mensal de uso do acervo pelo inquilino — entrada do item L7-09."""

    ano: int
    mes: int
    total_consultas: int
    total_feicoes: int
    camadas: list[AcervoUsoLinha]


# de wt/il601jmulti
class AcervoCamadaResumo(Saida):
    """Uma linha de `plat.acervo_camada` para a fonte, na ficha (item L6-01-j-multi-servidor). `origem`
    é o texto que a ficha mostra: 'local' quando a tabela vive neste servidor, 'servidor remoto (<nome>)'
    quando é lida por postgres_fdw só-leitura de outra máquina da casa, e 'servidor remoto indisponível
    (<nome>)' quando a última verificação não conseguiu falar com ela — a camada nunca desaparece nem vira
    '0 feições' por queda de rede; `linhas_exatas` conserva a última contagem conhecida e `aviso` explica."""

    servidor: str
    schema_nome: str
    tabela: str
    modo_acesso: str
    origem: str
    linhas_exatas: int | None = None
    aviso: str | None = None
    fdw_verificado_em: str | None = None
    fdw_latencia_ms: int | None = None
