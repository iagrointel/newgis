"""Tipos de job do motor AMC (registrados pelo decorador @tarefa do L0-05; importados em app/jobs/tipos.py).
`amc.gerar_unidades`: gera a grade de um conjunto (app/amc/unidades.gerar_grade) — item L3-01-b.
`amc.sensibilidade`: índices de Sobol (global) e tornado um-fator-por-vez (local) do mesmo modelo, com N
declarado, intervalo por bootstrap e tempo medido (item L3-02-b) — job pela mesma razão do sorteio: o
custo é N·(g+2) recombinações.
`amc.robustez_pesos`: Monte Carlo de sensibilidade ao peso (item L3-02-a; A8 do laco/decomposicao/L3L6_CONCEITO.md:
extração como job, combinação síncrona, ROBUSTEZ COMO JOB porque N sorteios em milhares de unidades passa
do orçamento de uma requisição síncrona). A tarefa só sorteia peso e chama `app.amc.combinacao.combinar`
(item L3-01-e) N vezes — não reimplementa a combinação."""

import time
import uuid

from pydantic import BaseModel, Field, field_validator

from app.amc import robustez, sensibilidade, unidades
from app.jobs.registro import FalhaDefinitiva, tarefa

MAX_UNIDADES = 20_000
MAX_FATORES = 60
MAX_SORTEIOS = 5_000
MAX_N_SOBOL = 4_096      # N·(g+2) recombinações: com 60 fatores dá 253.952 chamadas, o teto de um job
MAX_BOOTSTRAP = 2_000


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


class SensibilidadeParametros(BaseModel):
    fatores: list[list[float | None]] = Field(
        ..., min_length=1, max_length=MAX_UNIDADES,
        description="matriz unidade × fator já extraída (escala 0-100, None/ausente = sem dado)",
    )
    pesos_base: list[float] = Field(
        ..., min_length=1, max_length=MAX_FATORES,
        description="peso escolhido pelo usuário, um por fator, na mesma ordem de ids_fatores",
    )
    ids_fatores: list[str] = Field(..., min_length=1, max_length=MAX_FATORES)
    modelo: str = Field(..., min_length=1, max_length=200, description="identificação do modelo no relatório")
    versao_modelo: str | None = Field(None, max_length=200)
    n: int = Field(1024, ge=4, le=MAX_N_SOBOL, description="N da amostra de Saltelli; potência de 2")
    semente: int = Field(..., description="semente do gerador; mesma semente reproduz o resultado bit a bit")
    alvo: str = Field("concordancia_topk")
    k_top: int | None = Field(None, ge=1)
    faixa_peso_baixo: float = Field(-0.5, gt=-1.0)
    faixa_peso_alto: float = Field(1.0)
    passos_tornado: int = Field(9, ge=2, le=101)
    combinador: str = Field("soma_ponderada")
    politica_ausente: str = Field("excluir")
    fracao_vetada: list[float] | None = Field(None, max_length=MAX_UNIDADES)
    n_bootstrap: int = Field(100, ge=0, le=MAX_BOOTSTRAP)
    nivel_confianca: float = Field(0.95, gt=0.0, lt=1.0)

    @field_validator("fatores")
    @classmethod
    def _fatores_retangular_sensibilidade(cls, v):
        if v and len({len(linha) for linha in v}) != 1:
            raise ValueError("todas as linhas da matriz de fatores precisam ter o mesmo número de colunas")
        return v

    @field_validator("n")
    @classmethod
    def _n_potencia_de_dois(cls, v):
        if v & (v - 1) != 0:
            raise ValueError("N tem de ser potência de 2; a sequência de Sobol perde o equilíbrio fora disso")
        return v


@tarefa(
    nome="amc.sensibilidade",
    descricao="Sensibilidade do modelo multicritério: índices de Sobol de 1ª ordem e total sobre os pesos "
              "(global, com intervalo por bootstrap) e tornado um-fator-por-vez (local), com N e tempo declarados",
    parametros=SensibilidadeParametros,
    pesado=True,
    memoria_mb=512,
    timeout_s=600,
    tentativas=1,
    chave=None,
    perfil_minimo="editor",
)
def amc_sensibilidade(
    ctx,
    fatores: list[list[float | None]],
    pesos_base: list[float],
    ids_fatores: list[str],
    modelo: str,
    semente: int,
    versao_modelo: str | None = None,
    n: int = 1024,
    alvo: str = "concordancia_topk",
    k_top: int | None = None,
    faixa_peso_baixo: float = -0.5,
    faixa_peso_alto: float = 1.0,
    passos_tornado: int = 9,
    combinador: str = "soma_ponderada",
    politica_ausente: str = "excluir",
    fracao_vetada: list[float] | None = None,
    n_bootstrap: int = 100,
    nivel_confianca: float = 0.95,
) -> dict:
    n_unidades = len(fatores)
    n_fatores = len(fatores[0]) if fatores else 0
    ctx.log("INFO", f"sensibilidade do modelo {modelo}: N={n} sobre {n_fatores} pesos em {n_unidades} unidades "
                     f"(alvo={alvo}, semente={semente})")
    ctx.progresso(5, "amostra de Saltelli")
    try:
        relatorio = sensibilidade.relatorio_sensibilidade(
            fatores, pesos_base, modelo=modelo, versao_modelo=versao_modelo, ids_fatores=ids_fatores,
            n=n, semente=semente, alvo=alvo, k_top=k_top,
            faixa_peso=(faixa_peso_baixo, faixa_peso_alto), passos_tornado=passos_tornado,
            combinador=combinador, politica_ausente=politica_ausente, fracao_vetada=fracao_vetada,
            n_bootstrap=n_bootstrap, nivel_confianca=nivel_confianca,
        )
    except sensibilidade.ErroSensibilidade as e:
        raise FalhaDefinitiva(e.mensagem) from e
    ctx.progresso(100, "relatório pronto")
    ctx.log("INFO", f"sensibilidade concluída em {relatorio['tempo_s']:.3f} s; mandam no resultado: "
                     + (", ".join(relatorio["mandam_no_resultado"]) or "nenhum")
                     + "; irrelevantes: " + (", ".join(relatorio["irrelevantes"]) or "nenhum"))
    return relatorio
