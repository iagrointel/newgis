"""Tipos de job do motor AMC (registrados pelo decorador @tarefa do L0-05; importados em app/jobs/tipos.py).
`amc.gerar_unidades`: gera a grade de um conjunto (app/amc/unidades.gerar_grade). `amc.recombinar`: refaz a
favorabilidade de uma execução já extraída com outros pesos, em blocos, do lado do servidor (item
L3-16-desempenho-escala) — a robustez (L3-02) virá como tipo próprio aqui."""

import time
import uuid

import numpy as np
from psycopg2.extras import execute_values
from pydantic import BaseModel

from app import limites
from app.amc import escala, unidades
from app.jobs.registro import FalhaDefinitiva, tarefa


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


class RecombinarParametros(BaseModel):
    execucao_id: uuid.UUID
    pesos: dict[str, float] | None = None
    combinador: str = "soma_ponderada"
    politica_ausente: str = "excluir"


def _linear(valores: np.ndarray, t: dict) -> np.ndarray:
    """Valor bruto -> favorabilidade 0-100 pela transformação `linear` do esquema do modelo.

    LIMITE DECLARADO E TEMPORÁRIO deste item: só o tipo `linear`. A biblioteca completa das 16
    transformações é o item L3-01-d-transformacoes, que ainda não está nesta árvore; quando ela entrar,
    esta função sai e `app.amc.transformacoes` toma o lugar (uma linha de troca). Não se duplica aqui o
    que já existe lá: transformação de tipo diferente de `linear` levanta erro nomeado, nunca finge."""
    tipo = (t or {}).get("tipo")
    if tipo != "linear":
        raise FalhaDefinitiva(
            f"transformação {tipo!r} não é aplicada por este job (só 'linear'); a biblioteca completa é o "
            f"item L3-01-d-transformacoes"
        )
    minimo, maximo = float(t["minimo"]), float(t["maximo"])
    if maximo == minimo:
        return np.where(np.isfinite(valores), 50.0, np.nan)
    frac = (valores - minimo) / (maximo - minimo)
    if t.get("direcao", "crescente") == "decrescente":
        frac = 1.0 - frac
    abaixo = float(t["abaixo"]) if t.get("abaixo") is not None else 0.0
    acima = float(t["acima"]) if t.get("acima") is not None else 100.0
    return np.where(frac < 0.0, abaixo, np.where(frac > 1.0, acima, frac * 100.0))


def _blocos_de_fator_bruto(ctx, execucao_id: str, fatores: list[dict], plano: dict):
    """Gera `(ids, matriz 0-100)` lendo `plat.amc_fator_bruto` de `plano['bloco']` em `plano['bloco']`
    unidades, ordenado por `unidade_id`. Nada do conjunto inteiro fica em memória: é esta leitura em
    blocos (com faixa de `unidade_id`, não OFFSET) que faz o pico de RAM não crescer com o total."""
    ordem = {f["id"]: i for i, f in enumerate(fatores)}
    ultimo = ""
    while True:
        ctx.verificar()
        with ctx.db() as cur:
            cur.execute(
                "SELECT unidade_id FROM plat.amc_fator_bruto WHERE execucao_id = %s::uuid AND unidade_id > %s "
                "GROUP BY unidade_id ORDER BY unidade_id LIMIT %s",
                (execucao_id, ultimo, plano["bloco"]),
            )
            ids = [linha["unidade_id"] for linha in cur.fetchall()]
            if not ids:
                return
            cur.execute(
                "SELECT unidade_id, fator, valor FROM plat.amc_fator_bruto WHERE execucao_id = %s::uuid "
                "AND unidade_id >= %s AND unidade_id <= %s ORDER BY unidade_id",
                (execucao_id, ids[0], ids[-1]),
            )
            linhas = cur.fetchall()
        posicao = {uid: i for i, uid in enumerate(ids)}
        bruto = np.full((len(ids), len(fatores)), np.nan, dtype=np.float64)
        for linha in linhas:
            j = ordem.get(linha["fator"])
            if j is None or linha["valor"] is None:
                continue
            bruto[posicao[linha["unidade_id"]], j] = float(linha["valor"])
        matriz = np.empty_like(bruto)
        for j, f in enumerate(fatores):
            matriz[:, j] = _linear(bruto[:, j], f.get("transformacao") or {})
        matriz[~np.isfinite(bruto)] = np.nan  # ausência de dado continua ausência, nunca vira 0 nem 50
        ultimo = ids[-1]
        yield ids, matriz


@tarefa(
    nome="amc.recombinar",
    descricao="Refaz a favorabilidade de uma execução já extraída com outros pesos, em blocos, no servidor "
              "(unidades demais para o navegador)",
    parametros=RecombinarParametros,
    pesado=True,             # 1 por vez na máquina: a refutação do item L3-16 é justamente esta fila
    memoria_mb=escala.orcamento_mb(),
    timeout_s=limites.AMC_EXTRACAO_TIMEOUT_S,
    tentativas=1,            # recombinação é determinística: se falhou, repetir dá o mesmo erro
    chave=lambda p: f"amc_recombinar:{p.get('execucao_id')}",
    perfil_minimo="editor",
)
def amc_recombinar(ctx, execucao_id: uuid.UUID, pesos: dict | None = None,
                   combinador: str = "soma_ponderada", politica_ausente: str = "excluir") -> dict:
    eid = str(execucao_id)
    t0 = time.perf_counter()
    with ctx.db() as cur:
        cur.execute("SELECT tenant_id, modelo_id, versao_hash, pesos FROM plat.amc_execucao WHERE id = %s::uuid",
                    (eid,))
        exe = cur.fetchone()
        if exe is None:
            raise FalhaDefinitiva(f"execução inexistente: {eid}")
        cur.execute("SELECT definicao FROM plat.amc_modelo_versao WHERE modelo_id = %s AND versao_hash = %s",
                    (exe["modelo_id"], exe["versao_hash"]))
        versao = cur.fetchone()
        if versao is None:
            raise FalhaDefinitiva("versão do modelo desapareceu (nunca deveria: versão é imutável)")
        cur.execute("SELECT count(DISTINCT unidade_id) AS n FROM plat.amc_fator_bruto WHERE execucao_id = %s::uuid",
                    (eid,))
        n_unidades = int(cur.fetchone()["n"])
    fatores = [f for f in (versao["definicao"].get("fatores") or []) if isinstance(f, dict)]
    if not fatores:
        raise FalhaDefinitiva("o modelo não tem nenhum fator")
    if n_unidades == 0:
        raise FalhaDefinitiva("a execução não tem fator bruto extraído; recombinar exige extração antes")
    escolhidos = pesos if pesos is not None else exe["pesos"]
    try:
        plano = escala.plano(n_unidades, len(fatores))
    except escala.ErroEscala as e:
        raise FalhaDefinitiva(e.mensagem) from e
    vetor_pesos = [float(escolhidos.get(f["id"], 0.0)) for f in fatores]
    if sum(vetor_pesos) <= 0:
        raise FalhaDefinitiva("a soma dos pesos escolhidos é zero; não há como normalizar")

    gravadas = 0
    blocos = _blocos_de_fator_bruto(ctx, eid, fatores, plano)
    for k, (ids, resultado) in enumerate(escala.combinar_em_blocos(
            blocos, vetor_pesos, combinador=combinador, politica_ausente=politica_ausente)):
        # A3 do conceito, escrito como CHECK em plat.amc_resultado: unidade vetada NÃO carrega número na
        # escala e o motivo é obrigatório. `combinar` devolve 0.0 na vetada (a nota da conta); aqui ela vira
        # NULL com motivo, que é o contrato do banco. Sem isto o INSERT do bloco inteiro é recusado.
        linhas = []
        for i, uid in enumerate(ids):
            vetado = bool(resultado.vetado[i])
            fav = None if (vetado or not np.isfinite(resultado.fav[i])) else float(resultado.fav[i])
            motivo = resultado.motivo[i] or ("unidade inteiramente coberta por restrição" if vetado else None)
            linhas.append((eid, exe["tenant_id"], uid, fav, vetado, motivo, float(resultado.cobertura[i])))
        with ctx.db() as cur:
            execute_values(
                cur,
                "INSERT INTO plat.amc_resultado(execucao_id, tenant_id, unidade_id, favorabilidade, vetado, "
                "motivo, cobertura) VALUES %s ON CONFLICT (execucao_id, unidade_id) DO UPDATE SET "
                "favorabilidade = EXCLUDED.favorabilidade, vetado = EXCLUDED.vetado, motivo = EXCLUDED.motivo, "
                "cobertura = EXCLUDED.cobertura",
                linhas, template="(%s::uuid, %s, %s, %s, %s, %s, %s)",
            )
        gravadas += len(linhas)
        ctx.progresso(min(99, int(100 * (k + 1) / plano["n_blocos"])), f"bloco {k + 1}/{plano['n_blocos']}")
    ctx.progresso(100, "recombinação concluída")
    return {"execucao_id": eid, "unidades": gravadas, "n_blocos": plano["n_blocos"], "bloco": plano["bloco"],
            "pico_estimado_mb": plano["pico_estimado_mb"], "orcamento_mb": plano["orcamento_mb"],
            "pico_rss_mb": escala.medir_pico_mb(), "tempo_s": round(time.perf_counter() - t0, 3),
            "aviso_pesos": "pesos escolhidos pelo usuário, não medidos"}
