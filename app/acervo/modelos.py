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

from pydantic import BaseModel, ConfigDict


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
