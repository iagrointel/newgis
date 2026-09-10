"""Item F5 (laudo do adversário do reescritor de schema,
laco/handoffs/T4/ADVERSARIO-reescritor-schema.md): a trava de aconselhamento "1 pesado por vez"
do worker (`app.jobs.worker.LOCK_PESADO`) usava `hashtext(LOCK_PESADO)` com uma CONSTANTE — o
mesmo número em qualquer ambiente. `pg_try_advisory_lock` é do CLUSTER Postgres inteiro, nunca do
schema, e o valor viaja como PARÂMETRO da consulta (nunca como texto SQL), então
`CursorSchemaAmbiente` (app/schema_ambiente.py) não tem o que reescrever: produção, homologação e
qualquer trilha disputavam a MESMA trava.

Sintoma medido em 07/09: a fila de junção reprovou o mesmo lote em dois testes DIFERENTES rodando
ao mesmo tempo (test_busca.py, depois test_compartilhamento.py) — falha que muda de lugar entre
rodadas é disputa entre ambientes, não defeito de ramo.

Este teste usa duas conexões cruas ao Postgres, uma por AMBIENTE REAL (dois schemas de trilha
distintos, criados por `laco/trilha_ambiente.sh`), chamando a MESMA consulta que
`app.jobs.worker._pegar`/`_soltar_pesado` usam, com a chave lida da função pública do módulo
(`chave_lock_pesado`) — nunca duplica a lógica do worker."""

from pathlib import Path

import psycopg2
import pytest
from dotenv import dotenv_values

from app.jobs.worker import LOCK_PESADO, chave_lock_pesado

VAR_TRILHA = Path("/home/dev/plataforma/laco/var/trilha")


def _env_trilha(nome: str) -> dict[str, str]:
    arq = VAR_TRILHA / f"{nome}.env"
    if not arq.exists():
        pytest.skip(f"trilha {nome!r} não provisionada ({arq} não existe) — "
                    f"rode: bash /home/dev/plataforma/laco/trilha_ambiente.sh {nome} <worktree>")
    valores = dotenv_values(arq)
    dsn, schema = valores.get("PLAT_DSN"), valores.get("PLAT_SCHEMA")
    assert dsn and schema, f"{arq} sem PLAT_DSN/PLAT_SCHEMA"
    return {"dsn": dsn, "schema": schema}


@pytest.fixture(scope="module")
def ambiente_a() -> dict[str, str]:
    """A própria trilha deste item (F5); ver `laco/trilha_ambiente.sh trava <worktree>`."""
    return _env_trilha("trava")


@pytest.fixture(scope="module")
def ambiente_b() -> dict[str, str]:
    """Segunda trilha, SÓ para este teste provar isolamento entre ambientes; apagada no fim
    (regra dura do item: "apague os schemas das trilhas no fim")."""
    return _env_trilha("travb")


def _conectar(dsn: str):
    con = psycopg2.connect(dsn)
    con.autocommit = True
    return con


def _tentar_pesado(con, chave: str) -> bool:
    with con.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(hashtext(%s)) AS ok", (chave,))
        return bool(cur.fetchone()[0])


def _soltar_pesado(con, chave: str) -> None:
    with con.cursor() as cur:
        cur.execute("SELECT pg_advisory_unlock(hashtext(%s))", (chave,))


def test_chave_e_constante_hoje_colide_entre_ambientes(ambiente_a, ambiente_b):
    """Caracteriza o DEFEITO tal como ele está em produção hoje: a chave "crua" (LOCK_PESADO, sem
    o ambiente) é a mesma em qualquer schema — é por isso que dois ambientes reais disputam UMA
    trava só. Este teste passa tanto antes quanto depois do conserto (não testa o conserto; prova
    que o vetor do defeito existe e seria explorado se alguém usasse a chave crua)."""
    con_a = _conectar(ambiente_a["dsn"])
    con_b = _conectar(ambiente_b["dsn"])
    try:
        assert _tentar_pesado(con_a, LOCK_PESADO) is True, "ambiente A não conseguiu nem a própria trava crua"
        # é exatamente isto que reproduz o sintoma de 07/09: com a chave crua, o worker do
        # ambiente B nunca pega o pesado enquanto A segura o dele.
        assert _tentar_pesado(con_b, LOCK_PESADO) is False, (
            "a chave crua deveria colidir entre ambientes (é o defeito); se isto falhar, "
            "o Postgres de teste não é o cluster compartilhado esperado"
        )
    finally:
        _soltar_pesado(con_a, LOCK_PESADO)
        con_a.close()
        con_b.close()


def test_ambientes_diferentes_nao_disputam_mais_a_mesma_trava(ambiente_a, ambiente_b):
    """VERMELHO antes do conserto: chave_lock_pesado(schema) ainda não existia / ainda devolvia a
    constante, então esta asserção falhava exatamente como a de cima. VERDE depois: a chave por
    ambiente usa o schema de cada trilha (settings.PLAT_SCHEMA em produção), então um worker do
    ambiente B pega o pesado dele mesmo com o de A ainda segurando o dele — as duas filas de
    junção avançam ao mesmo tempo, o sintoma de 07/09 (bisseção culpando ramo inocente) não se
    repete."""
    con_a = _conectar(ambiente_a["dsn"])
    con_b = _conectar(ambiente_b["dsn"])
    chave_a = chave_lock_pesado(ambiente_a["schema"])
    chave_b = chave_lock_pesado(ambiente_b["schema"])
    assert chave_a != chave_b, "a chave por ambiente tem de diferir por schema, senão nada mudou"
    try:
        assert _tentar_pesado(con_a, chave_a) is True
        assert _tentar_pesado(con_b, chave_b) is True, (
            "o ambiente B ficou bloqueado pela trava do ambiente A: a chave ainda não está "
            "amarrada ao ambiente (defeito do item F5 ainda presente)"
        )
    finally:
        _soltar_pesado(con_a, chave_a)
        _soltar_pesado(con_b, chave_b)
        con_a.close()
        con_b.close()


def test_dentro_do_mesmo_ambiente_um_pesado_por_vez_continua_valendo(ambiente_a):
    """A garantia original não pode afrouxar: DUAS sessões do MESMO ambiente ainda disputam a
    MESMA trava — só o cruzamento ENTRE ambientes foi separado."""
    con_1 = _conectar(ambiente_a["dsn"])
    con_2 = _conectar(ambiente_a["dsn"])
    chave = chave_lock_pesado(ambiente_a["schema"])
    try:
        assert _tentar_pesado(con_1, chave) is True
        assert _tentar_pesado(con_2, chave) is False, (
            "duas sessões do MESMO ambiente conseguiram o pesado ao mesmo tempo: "
            "a regra 'um pesado por vez' afrouxou"
        )
        _soltar_pesado(con_1, chave)
        assert _tentar_pesado(con_2, chave) is True, "depois de A soltar, B (mesmo ambiente) devia conseguir"
    finally:
        _soltar_pesado(con_2, chave)
        con_1.close()
        con_2.close()


def test_chave_lock_pesado_usa_schema_do_ambiente_por_padrao(ambiente_a, monkeypatch):
    """Sem argumento, chave_lock_pesado() lê settings.PLAT_SCHEMA — é assim que o worker real
    (que nunca passa o schema explicitamente) fica amarrado ao próprio ambiente. `Settings` é
    dataclass FROZEN (imutável de propósito), por isso troca-se o OBJETO `settings` do módulo
    (via `dataclasses.replace`), nunca um atributo dele."""
    import dataclasses

    from app.jobs import worker as mod_worker

    settings_trocado = dataclasses.replace(mod_worker.settings, PLAT_SCHEMA=ambiente_a["schema"])
    monkeypatch.setattr(mod_worker, "settings", settings_trocado)
    assert chave_lock_pesado() == chave_lock_pesado(ambiente_a["schema"])
    assert chave_lock_pesado() != f"outro_schema:{LOCK_PESADO}"
