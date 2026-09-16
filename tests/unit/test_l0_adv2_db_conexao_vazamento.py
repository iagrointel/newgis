"""Adversário de linha L0 (rodada 2, wt/f2-adv-l02) — achado sobre `L0-06-a-dump-logico`, com implicação
transversal (afeta qualquer chamador de `app.db.db()`, não só backup). Laudo completo em
`laco/handoffs/T9/linha-L0-laudo-adversario-2.md`.

Medido AO VIVO nesta trilha: `POST /api/jobs {"tipo": "backup.executar"}` termina em `estado: "falhou"` com
`erro: "ProgrammingError: set_session cannot be used inside a transaction"` (traceback completo em
`app/db.py:74`, dentro de `_preparar`, chamado por `app/jobs/tarefas.py:717::backup_executar`). O portão do
item ("periódico roda e a linha em plat.backup tem sha256 igual ao do arquivo") não pode ser cumprido por um
job que quebra antes de abrir a primeira transação.

A causa é mais grave que um bug isolado do backup: `app.db.db()` só recicla a conexão para o pool
(`p.putconn`) em DOIS lugares — (a) no `finally` do bloco principal, que só é alcançado se `_preparar` teve
ÊXITO (`break` do for-loop antes dele); (b) dentro do `except (psycopg2.OperationalError, psycopg2.InterfaceError)`
do for-loop de tentativas. `psycopg2.ProgrammingError` NÃO é subclasse de nenhuma das duas — é uma exceção
IRMÃ na hierarquia do psycopg2 (`DatabaseError` tem `OperationalError`, `ProgrammingError`, etc. como
filhos independentes). Quando `_preparar` levanta `ProgrammingError` (como aconteceu de verdade com o
backup), a exceção atravessa o for-loop sem cair em nenhum `except` e sem passar pelo `finally` do bloco de
baixo (que nunca chega a ser alcançado) — a conexão obtida por `obter_conexao()` nunca volta ao pool.
Com `PLAT_POOL_MAX=2` (padrão de toda trilha, `laco/trilha_ambiente.sh`), duas ocorrências deste padrão de
erro esgotam o pool inteiro da trilha (PoolError em todo pedido seguinte) — risco de negação de serviço
generalizado a partir de UM job de backup que falha.

CONSERTADO (turno 9, f2fixfdwpool): `app/db.py::db()` ganhou um `except Exception` genérico no for-loop de
tentativas — qualquer exceção não-retentável de `_preparar` (não só a dupla OperationalError/InterfaceError)
agora devolve a conexão ao pool (fechando-a) antes de relançar. Teste deixou de ser xfail."""

from __future__ import annotations

import psycopg2
import pytest


def test_db_devolve_a_conexao_ao_pool_mesmo_quando_preparar_levanta_erro_nao_retentavel(monkeypatch):
    from app import db as db_mod

    p = db_mod.pool()
    em_uso_antes = len(p._used)

    def preparar_com_erro_nao_retentavel(con, ctx, somente_leitura=False):
        # a MESMA exceção medida ao vivo (backup.executar, tests/medidas ou o job real desta trilha)
        raise psycopg2.ProgrammingError("set_session cannot be used inside a transaction")

    monkeypatch.setattr(db_mod, "_preparar", preparar_com_erro_nao_retentavel)
    with pytest.raises(psycopg2.ProgrammingError):
        with db_mod.db():
            pass  # nunca alcançado

    em_uso_depois = len(p._used)
    assert em_uso_depois == em_uso_antes, (
        f"conexão vazou do pool: {em_uso_antes} em uso antes da chamada, {em_uso_depois} depois — "
        "db() não chamou putconn() para a conexão obtida antes de _preparar falhar com ProgrammingError"
    )
