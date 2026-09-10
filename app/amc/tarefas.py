"""Tipos de job do motor AMC (registrados pelo decorador @tarefa do L0-05; importados em app/jobs/tipos.py).
`amc.gerar_unidades`: gera a grade de um conjunto (app/amc/unidades.gerar_grade) — item L3-01-b.
`amc.smaa`: SMAA-2 simplificado (item L3-02-c) — aceitabilidade por posição, vetor central de pesos e fator de
confiança; roda como job pela mesma razão do `amc.robustez_pesos` (A8) e reusa o sorteio dele.
`amc.robustez_pesos`: Monte Carlo de sensibilidade ao peso (item L3-02-a; A8 do laco/decomposicao/L3L6_CONCEITO.md:
extração como job, combinação síncrona, ROBUSTEZ COMO JOB porque N sorteios em milhares de unidades passa
do orçamento de uma requisição síncrona). A tarefa só sorteia peso e chama `app.amc.combinacao.combinar`
(item L3-01-e) N vezes — não reimplementa a combinação."""

import time
import uuid

from pydantic import BaseModel, Field, field_validator

from app.amc import robustez, smaa, unidades
from app.jobs.registro import FalhaDefinitiva, tarefa

MAX_UNIDADES = 20_000
MAX_FATORES = 60
MAX_SORTEIOS = 5_000


class GerarUnidadesParametros(BaseModel):
    conjunto_id: uuid.UUID


@tarefa(
    nome="amc.gerar_unidades",
    descricao="Gera a grade (hexagonal/quadrada) de um conjunto de unidades de análise no CRS de trabalho, recortada à "
              "área de estudo, com área geodésica por célula",
    parametros=GerarUnidadesParametros,
    pesado=False,
    memoria_mb=768,          # o trabalho pesado é no Postgres (faixas de ≤ 100 mil células); o filho só orquestra
    timeout_s=1800,
    tentativas=2,
    chave=lambda p: f"amc_unidades:{p.get('conjunto_id')}",
    perfil_minimo="editor",
)
def amc_gerar_unidades(ctx, conjunto_id: uuid.UUID) -> dict:
    cid = str(conjunto_id)
    try:
        ficha = unidades.gerar_grade(ctx, cid)
    except unidades.ErroValidacao as e:
        with ctx.db() as cur:
            cur.execute("UPDATE plat.amc_conjunto_unidade SET estado = 'falhou', erro = %s WHERE id = %s",
                        (e.mensagem, cid))
        raise FalhaDefinitiva(e.mensagem) from e
    if ficha.get("recusado"):
        # `gerar_grade` já limpou as unidades e marcou o conjunto como 'falhou' com o motivo; aqui o JOB também
        # falha, para o operador não ver "concluído" sobre um conjunto que foi recusado (achado 4 do adversário).
        raise FalhaDefinitiva(ficha["motivo_recusa"])
    return {"conjunto_id": cid, "n_unidades": ficha["n_unidades"], "tempo_geracao_s": ficha["tempo_geracao_s"],
            "srid_trabalho": ficha["srid_trabalho"]}


class RobustezParametros(BaseModel):
    fatores: list[list[float | None]] = Field(
        ..., min_length=1, max_length=MAX_UNIDADES,
        description="matriz unidade × fator já extraída (escala 0-100, None/ausente = sem dado)",
    )
    pesos_base: list[float] = Field(
        ..., min_length=1, max_length=MAX_FATORES,
        description="peso escolhido pelo usuário, um por fator, na mesma ordem de ids_fatores",
    )
    ids_fatores: list[str] = Field(..., min_length=1, max_length=MAX_FATORES)
    n_sorteios: int = Field(1000, ge=1, le=MAX_SORTEIOS)
    metodo: str = Field("dirichlet", description="dirichlet (simplex) ou faixa (± k% por fator)")
    concentracao: float | None = Field(None, gt=0)
    k_percentual: float = Field(0.3, gt=0, lt=10)
    k_top: int | None = Field(None, ge=1)
    decil_superior: float = Field(0.9, gt=0, lt=1)
    combinador: str = Field("soma_ponderada")
    politica_ausente: str = Field("excluir")
    fracao_vetada: list[float] | None = Field(None, max_length=MAX_UNIDADES)
    semente: int = Field(..., description="semente do gerador; mesma semente reproduz o resultado bit a bit")

    @field_validator("fatores")
    @classmethod
    def _fatores_retangular(cls, v):
        if v and len({len(linha) for linha in v}) != 1:
            raise ValueError("todas as linhas da matriz de fatores precisam ter o mesmo número de colunas")
        return v


@tarefa(
    nome="amc.robustez_pesos",
    descricao="Monte Carlo de sensibilidade ao peso: N recombinações baratas do fator já extraído, "
               "resumidas por unidade (mínimo/média/máximo/desvio, frequência no top-k e no decil superior)",
    parametros=RobustezParametros,
    pesado=True,
    memoria_mb=512,
    timeout_s=120,
    tentativas=1,
    chave=None,
    perfil_minimo="editor",
)
def amc_robustez_pesos(
    ctx,
    fatores: list[list[float | None]],
    pesos_base: list[float],
    ids_fatores: list[str],
    semente: int,
    n_sorteios: int = 1000,
    metodo: str = "dirichlet",
    concentracao: float | None = None,
    k_percentual: float = 0.3,
    k_top: int | None = None,
    decil_superior: float = 0.9,
    combinador: str = "soma_ponderada",
    politica_ausente: str = "excluir",
    fracao_vetada: list[float] | None = None,
) -> dict:
    n_unidades = len(fatores)
    n_fatores = len(fatores[0]) if fatores else 0
    ctx.log("INFO", f"robustez: {n_sorteios} sorteios em {n_unidades} unidades × {n_fatores} fatores "
                     f"(método={metodo}, semente={semente})")
    try:
        inicio = time.monotonic()
        r = robustez.simular_robustez(
            fatores, pesos_base, n=n_sorteios, metodo=metodo, concentracao=concentracao,
            k_percentual=k_percentual, k_top=k_top, decil_superior=decil_superior, combinador=combinador,
            politica_ausente=politica_ausente, fracao_vetada=fracao_vetada, ids_fatores=ids_fatores,
            semente=semente, progresso=lambda pct: ctx.progresso(pct, f"{pct} % dos sorteios"),
        )
    except robustez.ErroRobustez as e:
        raise FalhaDefinitiva(e.mensagem) from e
    duracao_total = time.monotonic() - inicio
    ctx.log("INFO", f"robustez concluída em {duracao_total:.3f} s (cálculo puro: {r.tempo_s:.3f} s)")
    saida = r.como_dicionario()
    saida["duracao_job_s"] = duracao_total
    return saida


class SmaaParametros(RobustezParametros):
    """Mesmos parâmetros do sorteio de peso, mais o recorte da tabela de aceitabilidade. `k_top`,
    `decil_superior` e `n_sorteios` do sorteio de robustez continuam valendo: o SMAA usa `posicoes`
    (quantas posições do ranking a tabela conta) e `topo` (quantas unidades a tabela mostra)."""

    posicoes: int = Field(smaa.POSICOES_PADRAO, ge=1, le=1000)
    topo: int = Field(smaa.TOPO_PADRAO, ge=1, le=1000)


@tarefa(
    nome="amc.smaa",
    descricao="SMAA-2 simplificado: índice de aceitabilidade por posição, vetor central de pesos e fator de "
              "confiança por unidade; responde que pesos precisariam ser verdade para a unidade ganhar",
    parametros=SmaaParametros,
    pesado=True,
    memoria_mb=512,
    timeout_s=300,
    tentativas=1,
    chave=None,
    perfil_minimo="editor",
)
def amc_smaa(
    ctx,
    fatores: list[list[float | None]],
    pesos_base: list[float],
    ids_fatores: list[str],
    semente: int,
    n_sorteios: int = 1000,
    metodo: str = "dirichlet",
    concentracao: float | None = None,
    k_percentual: float = 0.3,
    k_top: int | None = None,
    decil_superior: float = 0.9,
    combinador: str = "soma_ponderada",
    politica_ausente: str = "excluir",
    fracao_vetada: list[float] | None = None,
    posicoes: int = smaa.POSICOES_PADRAO,
    topo: int = smaa.TOPO_PADRAO,
) -> dict:
    n_unidades = len(fatores)
    n_fatores = len(fatores[0]) if fatores else 0
    ctx.log("INFO", f"smaa: {n_sorteios} sorteios em {n_unidades} unidades × {n_fatores} fatores "
                     f"(método={metodo}, semente={semente}, posições={posicoes}, topo={topo})")
    try:
        inicio = time.monotonic()
        r = smaa.simular_smaa(
            fatores, pesos_base, n=n_sorteios, metodo=metodo, concentracao=concentracao,
            k_percentual=k_percentual, combinador=combinador, politica_ausente=politica_ausente,
            fracao_vetada=fracao_vetada, ids_fatores=ids_fatores, posicoes=posicoes, topo=topo,
            semente=semente, progresso=lambda pct: ctx.progresso(pct, f"{pct} % dos sorteios"),
        )
    except smaa.ErroSmaa as e:
        raise FalhaDefinitiva(e.mensagem) from e
    duracao_total = time.monotonic() - inicio
    ctx.log("INFO", f"smaa concluído em {duracao_total:.3f} s (cálculo puro: {r.tempo_s:.3f} s)")
    saida = r.como_dicionario()
    saida["duracao_job_s"] = duracao_total
    return saida
