"""Adversário de linha L0 (turno 9) — item `L0-05-d-periodicos`.

ACHADO REAL, já acontecido na trilha `uniao` (não é hipotético): o periódico `jobs.uso_medir` ("medição de
uso por inquilino diária", uma das tarefas citadas na própria hipótese do item) está com
`plat.agenda.ultimo_estado = 'falhou'` para o inquilino `plataforma` desde 2026-09-15, e vai falhar de novo
em toda execução seguinte para qualquer inquilino sem bucket no Garage (o inquilino técnico `plataforma`,
que nunca terá um; ou qualquer inquilino novo antes do primeiro sucesso do conector).

`app/jobs/periodicos.py::jobs_uso_medir` documenta a intenção — "Garage fora do ar NÃO falha o job: o
inquilino é medido sem a coluna bytes_bucket (NULL preserva a medição anterior, migração 20260906T2124)" —
mas `plat.uso_medir(p_tenant, p_dia, p_bytes_bucket)` só faz esse `coalesce` no braço UPDATE do
`ON CONFLICT`:

    INSERT INTO plat.uso_inquilino (..., bytes_bucket, ...) VALUES (..., p_bytes_bucket, ...)
    ON CONFLICT (tenant_id, dia) DO UPDATE SET
        bytes_bucket = coalesce(EXCLUDED.bytes_bucket, u.bytes_bucket), ...

Na PRIMEIRA medição de um inquilino/dia (sem linha anterior de quem herdar), o `INSERT` grava
`p_bytes_bucket` cru — e a coluna `uso_inquilino.bytes_bucket` é `NOT NULL`. Com Garage fora do ar (ou
inquilino sem bucket, `sem_bucket` no retorno de `jobs_uso_medir`) nesse primeiro dia, o `INSERT` estoura
`NotNullViolation`, a exceção sobe sem tratamento dentro do `for tenant_id in tenants` e o job inteiro vira
`falhou` — não só aquele inquilino fica sem medição daquele dia (o que já seria ruim): a EXCEÇÃO NÃO
CAPTURADA para o laço no meio da lista, e nenhum inquilino processado DEPOIS do que não tem bucket é medido
naquele dia. Reproduzido ao vivo (`plat.job_log`, job da agenda `jobs.uso_medir` de 2026-09-15 06:47 UTC,
trilha uniao): `psycopg2.errors.NotNullViolation: null value in column "bytes_bucket"`.

Isto não derruba OUTROS periódicos (a cláusula "periódico que falha não bloqueia os outros" do portão
segue de pé — os demais periódicos da agenda continuam `concluido` no mesmo dia), mas falsifica a hipótese
do próprio item ("medição de uso por inquilino diária 02:00" listada como uma das tarefas) e o comentário
de design que promete resiliência a Garage fora do ar: a resiliência só existe a partir da SEGUNDA medição
bem-sucedida de cada inquilino."""

import datetime

import psycopg2
import pytest

from tests.api.test_rls import contexto, ids_por_slug


# CONSERTADO — remedição de 17/09/2026 contra o master da união (sha b81e2c788): o marcador
# xfail(strict=True) do turno 9 foi retirado porque a asserção passa. plat.uso_medir(tenant, dia, NULL)
# já não estoura NotNullViolation em bytes_bucket na primeira medição do inquilino/dia. O achado do
# adversário fica registrado no laudo do turno 9 e em laco/vivo/remedicao_L0L3_20260917.md.
def test_uso_medir_com_bucket_nulo_sem_linha_anterior_nao_derruba_o_periodico(conexao_plat_app):
    ids = ids_por_slug(conexao_plat_app)
    tenant_id = ids["demo"]
    # dia que nenhuma trilha/turno já mediu (bem no passado; plat.uso_inquilino só ganha linhas do periódico
    # ou dos testes de L0-03-catalogo, sempre com `dia` recente)
    dia = datetime.date(1999, 1, 1)
    contexto(conexao_plat_app, tenant_id, usuario_id=0, login="teste")
    with conexao_plat_app.cursor() as cur:
        cur.execute("DELETE FROM plat.uso_inquilino WHERE tenant_id = %s AND dia = %s", (tenant_id, dia))
    conexao_plat_app.commit()
    try:
        contexto(conexao_plat_app, tenant_id, usuario_id=0, login="teste")
        with conexao_plat_app.cursor() as cur:
            # a mesma chamada que app/jobs/periodicos.py::jobs_uso_medir faz quando o Garage não devolveu
            # bytes_bucket para este inquilino (fora do ar, ou inquilino ainda sem bucket)
            cur.execute("SELECT * FROM plat.uso_medir(%s, %s, NULL)", (tenant_id, dia))
        conexao_plat_app.commit()
    except psycopg2.Error as e:
        conexao_plat_app.rollback()
        pytest.fail(f"plat.uso_medir(tenant, dia_nunca_medido, NULL) estourou: {e}")
    finally:
        contexto(conexao_plat_app, tenant_id, usuario_id=0, login="teste")
        with conexao_plat_app.cursor() as cur:
            cur.execute("DELETE FROM plat.uso_inquilino WHERE tenant_id = %s AND dia = %s", (tenant_id, dia))
        conexao_plat_app.commit()
