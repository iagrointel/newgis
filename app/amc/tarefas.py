"""Tipos de job do motor AMC (registrados pelo decorador @tarefa do L0-05; importados em app/jobs/tipos.py).
`amc.gerar_unidades`: gera a grade de um conjunto (app/amc/unidades.gerar_grade) — a extração de fatores (L3-01-c)
e a robustez (L3-02) virão como tipos próprios aqui."""

import uuid

from pydantic import BaseModel

from app.amc import unidades
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
