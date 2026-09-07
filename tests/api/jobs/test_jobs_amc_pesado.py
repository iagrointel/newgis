"""REFUTAÇÃO do item L3-16-desempenho-escala: duas execuções do motor multicritério lançadas ao mesmo tempo,
com DOIS processos de worker livres, e a segunda espera a primeira terminar — 1 job pesado por vez na máquina.

Por que aqui e não em tests/api/amc: as fixtures de worker em subprocesso (`iniciar_worker`) vivem neste
diretório. O teste usa worker próprio, em porta própria, encerrado pelo identificador de processo no fim —
nunca a unidade `plat-worker` do sistema.

O par de execuções tem `execucao_id` DIFERENTE de propósito: `amc.recombinar` declara
`chave = amc_recombinar:<execucao_id>`, e a serialização por chave já é provada em test_jobs_fila.py. Se as
duas execuções fossem a mesma, o teste passaria pelo motivo errado — provaria a chave, não o `pesado=True`.
"""

import json
import os
import time
import uuid

import pytest

from app import db as banco
from tests.api.jobs.conftest import criar_job, esperar
from tests.api.test_rls import ids_por_slug

PORTA_WORKER = 8301          # porta desta trilha (>= 8300), fora da faixa da unidade do sistema
UNIDADES = 20_000            # rows suficientes para o job durar o bastante para a sobreposição ser visível
FATORES = ("fator_a", "fator_b", "fator_c")


class ContextoDeTeste:
    """O que a montagem usa do ContextoJob: db()."""

    def __init__(self, tenant_id: int):
        self._ctx = banco.Contexto(tenant_id, 0, "teste")

    def db(self):
        return banco.db(self._ctx)


def _definicao() -> dict:
    return {
        "esquema": "amc_modelo.v1",
        "nome": "escala de teste interno",
        "combinador": {"tipo": "soma_ponderada_normalizada"},
        "fatores": [
            {"id": f, "nome": f, "criterio": "maior é melhor", "fonte": "sintética", "unidade": "un",
             "direcao": "maior_melhor", "base": "engenharia",
             "camada": {"tipo": "item", "id": str(uuid.UUID(int=i + 1))},
             "extrator": {"tipo": "raster_media"},
             "transformacao": {"tipo": "linear", "minimo": 0, "maximo": 100},
             "peso": 1.0}
            for i, f in enumerate(FATORES)
        ],
    }


def _montar_execucao(ctx, tenant_id: int) -> str:
    """Cria modelo, versão, conjunto e execução com `UNIDADES × len(FATORES)` linhas de fator bruto.
    Devolve o id da execução. Tudo com prefixo de teste e sem nome de cliente."""
    from psycopg2.extras import execute_values

    definicao = _definicao()
    versao_hash = uuid.uuid4().hex + uuid.uuid4().hex   # 64 hexadecimais, como o CHECK da migração 045 exige
    with ctx.db() as cur:
        cur.execute(
            "INSERT INTO plat.amc_modelo(tenant_id, nome, versao_hash) VALUES (%s, %s, %s) RETURNING id",
            (tenant_id, f"zt-escala {versao_hash[:8]}", versao_hash),
        )
        modelo_id = cur.fetchone()["id"]
        cur.execute(
            "INSERT INTO plat.amc_modelo_versao(modelo_id, tenant_id, versao_hash, numero, definicao) "
            "VALUES (%s, %s, %s, 1, %s)",
            (modelo_id, tenant_id, versao_hash, json.dumps(definicao)),
        )
        cur.execute(
            "INSERT INTO plat.amc_conjunto_unidade(tenant_id, nome, tipo, srid_trabalho, estado, n_unidades) "
            "VALUES (%s, %s, 'feicoes', 31982, 'pronto', %s) RETURNING id",
            (tenant_id, f"zt-escala conj {versao_hash[:8]}", UNIDADES),
        )
        conjunto_id = cur.fetchone()["id"]
        cur.execute(
            "INSERT INTO plat.amc_execucao(tenant_id, modelo_id, versao_hash, conjunto_id, pesos, camadas, "
            "motor_versao, semente) VALUES (%s, %s, %s, %s, %s, %s, 'amc/0.1+teste', 1) RETURNING id",
            (tenant_id, modelo_id, versao_hash, conjunto_id,
             json.dumps({f: 1.0 for f in FATORES}), json.dumps([])),
        )
        execucao_id = str(cur.fetchone()["id"])
        linhas = [(execucao_id, tenant_id, f"u{i:07d}", f, float((i * 7 + j * 13) % 101), 1.0)
                  for i in range(UNIDADES) for j, f in enumerate(FATORES)]
        execute_values(
            cur,
            "INSERT INTO plat.amc_fator_bruto(execucao_id, tenant_id, unidade_id, fator, valor, cobertura) "
            "VALUES %s", linhas, template="(%s::uuid, %s, %s, %s, %s, %s)", page_size=5000,
        )
    return execucao_id


@pytest.fixture
def tenant_demo(conexao_plat_app):
    return ids_por_slug(conexao_plat_app)["demo"]


@pytest.mark.lento
def test_duas_recombinacoes_simultaneas_a_segunda_espera_na_fila(cliente_demo, iniciar_worker, tenant_demo):
    ctx = ContextoDeTeste(tenant_demo)
    execucoes = [_montar_execucao(ctx, tenant_demo) for _ in range(2)]
    iniciar_worker(f"teste-amc-{os.getpid()}", processos=2, porta=PORTA_WORKER)

    t0 = time.monotonic()
    jobs = [criar_job(cliente_demo, "amc.recombinar", {"execucao_id": eid}) for eid in execucoes]
    fim = [esperar(cliente_demo, j["id"], timeout=300) for j in jobs]

    assert all(j["estado"] == "concluido" for j in fim), [(j["estado"], j["erro"]) for j in fim]
    assert all(j["pesado"] for j in fim), "amc.recombinar tem de nascer pesado"
    primeiro, segundo = sorted(fim, key=lambda j: j["iniciado_em"])
    assert segundo["iniciado_em"] >= primeiro["terminado_em"], (
        "as duas recombinações rodaram ao mesmo tempo: o 'um pesado por vez' não segurou\n"
        f"{json.dumps({'primeiro': primeiro, 'segundo': segundo}, default=str)[:800]}"
    )
    assert time.monotonic() - t0 < 300

    # e o trabalho foi feito de verdade: uma linha de resultado por unidade, na escala, em cada execução
    with ctx.db() as cur:
        for eid in execucoes:
            cur.execute(
                "SELECT count(*) AS n, min(favorabilidade) AS mn, max(favorabilidade) AS mx "
                "FROM plat.amc_resultado WHERE execucao_id = %s::uuid", (eid,)
            )
            r = cur.fetchone()
            assert r["n"] == UNIDADES, (eid, r["n"])
            assert 0.0 <= float(r["mn"]) <= float(r["mx"]) <= 100.0, r
