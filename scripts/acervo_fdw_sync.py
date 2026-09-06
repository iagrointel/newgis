#!/usr/bin/env python3
"""Sincronizador de camadas REMOTAS do acervo via postgres_fdw só-leitura (item L6-01-j-multi-servidor;
migração 20260906T2108_acervo_remoto_fdw; ADR docs/adr/20260906T2108-acervo-remoto-via-fdw.md).
Roda como `postgres` (mesma identidade de `db/migrar.sh` e de `scripts/acervo_sync.py`), com o
`psycopg2` do sistema — nunca como `plat_app`, que só LÊ o registro e as foreign tables.

    sudo -u postgres python3 scripts/acervo_fdw_sync.py [--banco iagro_sat] [--schema plat]
        [--servidor-remoto NOME]... [--segredos /etc/plat/segredos] [--limite N]

O que faz, em ordem:
  1. Lê os servidores ativos de `<schema>.acervo_servidor` (host/porta/banco + papel de LEITURA remoto
     + `segredo_ref`, nome do arquivo de senha no diretório de segredos — a senha nunca está no banco).
  2. Garante, por servidor: `CREATE/ALTER SERVER fdw_<schema>_<servidor>` (postgres_fdw, com
     `connect_timeout`, para que servidor fora do ar falhe em segundos e nunca pendure a rodada),
     `USER MAPPING` para o postgres E para o papel da aplicação (`<schema>_app`) com a senha lida do
     cofre (a API lê as foreign tables como `<schema>_app`, papel que no remoto é SÓ-LEITURA),
     `GRANT USAGE ON FOREIGN SERVER` para o papel da aplicação.
  3. Candidatas: `acervo.objeto` (canônicas, tipo 'fonte', daquele servidor/banco — origem
     'registro_acervo') UNIÃO `<schema>.acervo_servidor_tabela` (declaradas manualmente — origem
     'manual'; é também como a base de teste monta a fixture sem poluir `acervo.objeto`).
  4. Por (servidor, schema remoto): `IMPORT FOREIGN SCHEMA <schema> LIMIT TO (...)` para o schema
     espelho local `<schema_plat>_rm_<servidor>_<schema_remoto>` — o ESPELHO é de definição, nunca de
     dado: nenhuma linha é copiada (regra D21, disco a 98 %). Tabela importada sem coluna de geometria
     não é camada: fica de fora do registro (avisada no log).
  5. Por tabela: `COUNT(*)` exato ATRAVÉS da foreign table, sob `statement_timeout` de 25 s (mesmo
     padrão de `acervo_sync.py`/`contagem2.py`), com a latência MEDIDA gravada em `fdw_latencia_ms`
     (o portão pede tempo medido; número nunca digitado). SRID/tipo da geometria lidos do typmod da
     foreign table (`postgis_typmod_srid/type`), nunca assumidos. Lista branca de colunas pela MESMA
     rede grossa de nomes de `acervo_sync.py` (`_COLUNA_NEGADA`, importada — as duas listas nunca
     divergem). Estado: 'pendente_de_licenca' se `acervo.fonte.licenca` vazia (regra D17), 'exposta'
     senão; contagem não concluída = 'bloqueada', nunca zero.
  6. FALHA DE REDE (servidor não responde, IMPORT ou COUNT estouram por conexão): a camada vira
     `modo_acesso = 'indisponivel'` com `aviso` explicando — NUNCA é apagada e NUNCA vira "0 feições":
     `linhas_exatas` conserva a última contagem conhecida. É o que a refutação do item cobra ("adversário
     derruba a rede da fixture e confere que a camada não aparece como '0 feições'").
  7. Poda (SÓ quando o servidor respondeu nesta rodada — nunca poda às cegas): remove do registro e
     do espelho o que deixou de ser candidata daquele servidor. Linha LOCAL nunca é tocada por este
     script (servidor da linha ≠ este), e uma candidata remota que colide com uma linha 'local' já
     registrada é pulada — o local é a canônica, a remota é a cópia (verbo do item: nunca copiar).
  8. Grava 1 linha em `<schema>.acervo_fdw_execucao` com os números da rodada.

Prazo duro de 270 s por rodada (mesmo padrão de `acervo_sync.py`): ao estourar, o que faltar fica
INTOCADO para a próxima rodada (nunca marcado às cegas), porque connect_timeout de 10 s por servidor
já limita o estrago de um servidor morto.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import psycopg2
import psycopg2.errors
import psycopg2.extras

sys.path.insert(0, str(Path(__file__).resolve().parent))
from acervo_sync import _COLUNA_NEGADA, _log  # noqa: E402 — mesma rede grossa de nomes, mesma saída

TIMEOUT_CONTAGEM_MS = 25_000
CONNECT_TIMEOUT_S = 10
PRAZO_TOTAL_S = 270.0
SEGREDOS_PADRAO = "/etc/plat/segredos"

SQL_CANDIDATAS_REGISTRO = """
SELECT fonte_id, schema_nome, tabela
FROM acervo.objeto
WHERE servidor = %(servidor)s AND banco = %(banco)s AND canonico AND tipo = 'fonte'
  AND fonte_id IS NOT NULL
"""

SQL_UPSERT_FDW = """
INSERT INTO {schema}.acervo_camada
  (acervo_camada_id, fonte_id, servidor, banco, schema_nome, tabela, coluna_geom, srid, tipo_geom,
   colunas_expostas, colunas_bloqueadas, linhas_exatas, linhas_contadas_em, linhas_estimadas,
   sha256, comando_reexecucao, estado, motivo_bloqueio, sincronizado_em,
   modo_acesso, fdw_tabela, aviso, fdw_verificado_em, fdw_latencia_ms)
VALUES (%(id)s, %(fonte_id)s, %(servidor)s, %(banco)s, %(schema_nome)s, %(tabela)s, %(coluna_geom)s,
        %(srid)s, %(tipo_geom)s, %(colunas_expostas)s, %(colunas_bloqueadas)s, %(linhas_exatas)s,
        %(linhas_contadas_em)s, NULL, %(sha256)s, %(comando_reexecucao)s, %(estado)s,
        %(motivo_bloqueio)s, now(),
        %(modo_acesso)s, %(fdw_tabela)s, %(aviso)s, now(), %(fdw_latencia_ms)s)
ON CONFLICT (acervo_camada_id) DO UPDATE SET
  fonte_id = EXCLUDED.fonte_id, servidor = EXCLUDED.servidor, banco = EXCLUDED.banco,
  schema_nome = EXCLUDED.schema_nome, tabela = EXCLUDED.tabela, coluna_geom = EXCLUDED.coluna_geom,
  srid = EXCLUDED.srid, tipo_geom = EXCLUDED.tipo_geom, colunas_expostas = EXCLUDED.colunas_expostas,
  colunas_bloqueadas = EXCLUDED.colunas_bloqueadas, linhas_exatas = EXCLUDED.linhas_exatas,
  linhas_contadas_em = EXCLUDED.linhas_contadas_em,
  sha256 = EXCLUDED.sha256, comando_reexecucao = EXCLUDED.comando_reexecucao, estado = EXCLUDED.estado,
  motivo_bloqueio = EXCLUDED.motivo_bloqueio, sincronizado_em = now(),
  modo_acesso = EXCLUDED.modo_acesso, fdw_tabela = EXCLUDED.fdw_tabela, aviso = EXCLUDED.aviso,
  fdw_verificado_em = now(), fdw_latencia_ms = EXCLUDED.fdw_latencia_ms
"""

# falha de rede NUNCA reescreve linhas_exatas/estado: só vira aviso + indisponivel (a camada continua
# existindo com a última contagem conhecida — "falha de rede vira aviso, não camada vazia")
SQL_MARCAR_INDISPONIVEL = """
UPDATE {schema}.acervo_camada
   SET modo_acesso = 'indisponivel', aviso = %(aviso)s, fdw_verificado_em = now(), sincronizado_em = now()
 WHERE acervo_camada_id = %(id)s
"""

SQL_INSERIR_INDISPONIVEL = """
INSERT INTO {schema}.acervo_camada
  (acervo_camada_id, fonte_id, servidor, banco, schema_nome, tabela, coluna_geom, srid, tipo_geom,
   colunas_expostas, colunas_bloqueadas, linhas_exatas, linhas_contadas_em, linhas_estimadas,
   sha256, comando_reexecucao, estado, motivo_bloqueio, sincronizado_em,
   modo_acesso, fdw_tabela, aviso, fdw_verificado_em, fdw_latencia_ms)
VALUES (%(id)s, %(fonte_id)s, %(servidor)s, %(banco)s, %(schema_nome)s, %(tabela)s, %(coluna_geom)s,
        0, 'GEOMETRY', '{}', '{}', NULL, NULL, NULL, NULL, NULL, 'bloqueada', 'servidor_indisponivel',
        now(), 'indisponivel', NULL, %(aviso)s, now(), NULL)
ON CONFLICT (acervo_camada_id) DO UPDATE SET
  modo_acesso = 'indisponivel', aviso = EXCLUDED.aviso, fdw_verificado_em = now(),
  sincronizado_em = now()
"""


def _ident(conn, nome: str) -> str:
    return psycopg2.extensions.quote_ident(nome, conn)


def _san(nome: str) -> str:
    """Slug seguro para nomear SERVER/schema espelho a partir de nome de servidor/schema remoto."""
    s = re.sub(r"[^a-z0-9_]+", "_", nome.lower()).strip("_")
    return s or "x"


def _nome_curto(prefixo: str, *partes: str, limite: int = 63) -> str:
    """Nome de objeto Postgres ≤ 63 bytes: corta com sufixo de hash quando passa (nunca colide)."""
    nome = "_".join([prefixo, *partes])
    if len(nome.encode()) <= limite:
        return nome
    h = hashlib.sha256(nome.encode()).hexdigest()[:10]
    base = nome[: limite - 11].rstrip("_")
    return f"{base}_{h}"


def _senha_do_cofre(diretorio: Path, segredo_ref: str) -> str | None:
    """Lê a senha do papel de leitura no arquivo do cofre. `segredo_ref` já vem validado pelo CHECK da
    tabela (sem '/' e sem '..'), mas a defesa é repetida aqui: uma linha gravada por fora da tabela
    (restauração, cópia) não pode apontar para fora do diretório de segredos."""
    alvo = (diretorio / segredo_ref).resolve()
    if not str(alvo).startswith(str(diretorio.resolve()) + os.sep):
        _log(f"segredo_ref fora do cofre recusado: {segredo_ref!r}")
        return None
    try:
        return alvo.read_text(encoding="utf-8").strip()
    except OSError as e:
        _log(f"segredo {segredo_ref!r} ilegível: {e}")
        return None


def _garantir_servidor_fdw(conn, schema_plat: str, srv: dict, senha: str, papel_app: str) -> str:
    """CREATE/ALTER idempotente do SERVER postgres_fdw + USER MAPPING (postgres e papel da aplicação) +
    GRANT USAGE. `connect_timeout` fica SEMPRE gravado no servidor: é o que faz uma queda de rede virar
    erro em segundos (e aviso na camada), nunca uma rodada pendurada. Devolve o nome do SERVER."""
    nome_srv = _nome_curto("fdw", _san(schema_plat), _san(srv["servidor"]))
    with conn.cursor() as cur:
        cur.execute(
            "SELECT srvoptions FROM pg_foreign_server WHERE srvname = %s",
            (nome_srv,),
        )
        existe = cur.fetchone() is not None
        # os VALORES de host/banco/usuário vão entre aspas simples com escape de aspa (são valores de
        # opção do FDW, nunca identificadores — quote_ident seria errado aqui)
        def v(x) -> str:
            return "'" + str(x).replace("'", "''") + "'"

        pares = (
            f"host {v(srv['host'])}, port {v(srv['porta'])}, dbname {v(srv['banco'])}, "
            f"connect_timeout {v(CONNECT_TIMEOUT_S)}"
        )
        if not existe:
            cur.execute(
                f"CREATE SERVER {_ident(conn, nome_srv)} FOREIGN DATA WRAPPER postgres_fdw "
                f"OPTIONS ({pares})"
            )
        else:
            cur.execute(
                f"ALTER SERVER {_ident(conn, nome_srv)} OPTIONS "
                f"(SET host {v(srv['host'])}, SET port {v(srv['porta'])}, SET dbname {v(srv['banco'])}, "
                f"SET connect_timeout {v(CONNECT_TIMEOUT_S)})"
            )
        for papel in ("CURRENT_USER", _ident(conn, papel_app)):
            cur.execute(
                f"CREATE USER MAPPING IF NOT EXISTS FOR {papel} SERVER {_ident(conn, nome_srv)} "
                f"OPTIONS (user {v(srv['fdw_usuario'])}, password {v(senha)})"
            )
            cur.execute(
                f"ALTER USER MAPPING FOR {papel} SERVER {_ident(conn, nome_srv)} "
                f"OPTIONS (SET user {v(srv['fdw_usuario'])}, SET password {v(senha)})"
            )
        cur.execute(f"GRANT USAGE ON FOREIGN SERVER {_ident(conn, nome_srv)} TO {_ident(conn, papel_app)}")
    conn.commit()
    return nome_srv


def _candidatas(conn, schema_plat: str, srv: dict) -> list[dict]:
    """acervo.objeto (canônicas daquele servidor) + declaradas manualmente. Nenhum nome digitado em
    código: o universo vem sempre do registro."""
    with conn.cursor() as cur:
        cur.execute(SQL_CANDIDATAS_REGISTRO, {"servidor": srv["servidor"], "banco": srv["banco"]})
        linhas = [dict(r, origem="registro_acervo") for r in cur.fetchall()]
        cur.execute(
            f"SELECT fonte_id, schema_nome, tabela FROM {_ident(conn, schema_plat)}.acervo_servidor_tabela "
            "WHERE servidor = %s",
            (srv["servidor"],),
        )
        linhas += [dict(r, origem="manual") for r in cur.fetchall()]
    return linhas


def _geom_da_foreign(conn, espelho: str, tabela: str) -> tuple[str, int, str] | None:
    """(coluna_geom, srid, tipo_geom) da foreign table, pelo typmod — nunca assumido. None = não é camada."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT a.attname AS coluna, "
            "       postgis_typmod_srid(a.atttypmod) AS srid, postgis_typmod_type(a.atttypmod) AS tipo "
            "FROM pg_attribute a "
            "JOIN pg_class c ON c.oid = a.attrelid AND c.relkind = 'f' "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "JOIN pg_type t ON t.oid = a.atttypid "
            "WHERE n.nspname = %s AND c.relname = %s AND t.typname = 'geometry' AND a.attnum > 0 "
            "ORDER BY (lower(a.attname) NOT IN ('geom', 'geometry')), a.attname LIMIT 1",
            (espelho, tabela),
        )
        r = cur.fetchone()
    if r is None:
        return None
    return r["coluna"], r["srid"] or 0, (r["tipo"] or "GEOMETRY").upper()


def _colunas_da_foreign(conn, espelho: str, tabela: str, coluna_geom: str) -> tuple[list[str], list[str]]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position",
            (espelho, tabela),
        )
        todas = [r["column_name"] for r in cur.fetchall()]
    expostas = [c for c in todas if c != coluna_geom and c.lower() not in _COLUNA_NEGADA]
    bloqueadas = [c for c in todas if c != coluna_geom and c.lower() in _COLUNA_NEGADA]
    return expostas, bloqueadas


def _contar_via_fdw(conn, espelho: str, tabela: str) -> tuple[int | None, int | None, str | None]:
    """COUNT(*) ATRAVÉS da foreign table (a leitura cruza a rede pelo FDW, não por conexão direta),
    sob statement_timeout de 25 s. Devolve (linhas, latencia_ms, erro): erro None no sucesso; 'timeout'
    quando a contagem não conclui; a mensagem curta do erro de conexão quando a rede cai."""
    ident = f"{_ident(conn, espelho)}.{_ident(conn, tabela)}"
    inicio = time.monotonic()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SET LOCAL statement_timeout = {TIMEOUT_CONTAGEM_MS}")
            cur.execute(f"SELECT count(*) AS n FROM {ident}")  # noqa: S608 — identificadores citados
            n = cur.fetchone()["n"]
        conn.commit()
        return n, int((time.monotonic() - inicio) * 1000), None
    except psycopg2.errors.QueryCanceled:
        conn.rollback()
        return None, int((time.monotonic() - inicio) * 1000), "timeout"
    except psycopg2.Error as e:
        conn.rollback()
        msg = (e.diag.message_primary or str(e)).strip().splitlines()[0][:300]
        return None, int((time.monotonic() - inicio) * 1000), msg


def _marcar_indisponivel(cur, schema_plat: str, camada_id: str, cand: dict, banco: str, aviso: str) -> None:
    """Falha de rede: a camada NUNCA some e NUNCA zera — conserva a última contagem e ganha o aviso.
    Se ainda não existia, nasce 'bloqueada'/'servidor_indisponivel' com linhas_exatas NULL (ausência de
    dado nunca é medição)."""
    cur.execute(
        SQL_MARCAR_INDISPONIVEL.format(schema=_ident(cur.connection, schema_plat)),
        {"id": camada_id, "aviso": aviso},
    )
    if cur.rowcount == 0:
        cur.execute(
            SQL_INSERIR_INDISPONIVEL.format(schema=_ident(cur.connection, schema_plat)),
            {
                "id": camada_id, "fonte_id": cand["fonte_id"], "servidor": cand["servidor"],
                "banco": banco, "schema_nome": cand["schema_nome"], "tabela": cand["tabela"],
                "coluna_geom": "geom", "aviso": aviso,
            },
        )


def sincronizar(dsn_kwargs: dict, schema_plat: str, segredos: Path, so_servidores: list[str] | None,
                limite: int | None = None) -> dict:
    inicio = time.monotonic()
    inicio_iso = datetime.now(UTC)
    papel_app = f"{schema_plat}_app"
    conn = psycopg2.connect(cursor_factory=psycopg2.extras.RealDictCursor, **dsn_kwargs)
    conn.autocommit = False
    stats = {"servidores_ok": 0, "servidores_fora": 0, "tabelas_fdw": 0, "indisponiveis": 0,
             "puladas": 0, "sem_geometria": 0, "estourou_prazo": False}
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS postgres_fdw")
            cur.execute(
                f"SELECT servidor, host, porta, banco, fdw_usuario, segredo_ref "
                f"FROM {_ident(conn, schema_plat)}.acervo_servidor WHERE ativo ORDER BY servidor"
            )
            servidores = cur.fetchall()
        conn.commit()
        if so_servidores:
            servidores = [s for s in servidores if s["servidor"] in so_servidores]

        processadas = 0
        for srv in servidores:
            if time.monotonic() - inicio > PRAZO_TOTAL_S:
                stats["estourou_prazo"] = True
                _log("prazo duro de 270 s estourado; servidores restantes ficam para a próxima rodada")
                break
            nome = srv["servidor"]
            senha = _senha_do_cofre(segredos, srv["segredo_ref"])
            if senha is None:
                aviso = f"segredo '{srv['segredo_ref']}' ausente ou ilegível no cofre da instalação"
                _log(f"{nome}: {aviso}")
                with conn.cursor() as cur:
                    for cand in _candidatas(conn, schema_plat, srv):
                        _marcar_indisponivel(
                            cur, schema_plat, f"{cand['fonte_id']}/{cand['schema_nome']}.{cand['tabela']}",
                            dict(cand, servidor=nome), srv["banco"], aviso)
                        stats["indisponiveis"] += 1
                conn.commit()
                stats["servidores_fora"] += 1
                continue

            candidatas = _candidatas(conn, schema_plat, srv)
            if limite:
                candidatas = candidatas[:limite]
            if not candidatas:
                _log(f"{nome}: nenhuma candidata (registro nem declaração manual)")
                stats["servidores_ok"] += 1
                continue

            nome_srv = _garantir_servidor_fdw(conn, schema_plat, srv, senha, papel_app)
            servidor_vivo = False

            # agrupa por schema remoto: um IMPORT FOREIGN SCHEMA ... LIMIT TO por grupo
            por_schema: dict[str, list[dict]] = {}
            for cand in candidatas:
                por_schema.setdefault(cand["schema_nome"], []).append(cand)

            for schema_remoto, grupo in por_schema.items():
                if time.monotonic() - inicio > PRAZO_TOTAL_S:
                    stats["estourou_prazo"] = True
                    break
                espelho = _nome_curto(f"{_san(schema_plat)}_rm", _san(nome), _san(schema_remoto))
                tabelas_sql = ", ".join(_ident(conn, c["tabela"]) for c in grupo)
                try:
                    with conn.cursor() as cur:
                        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {_ident(conn, espelho)}")
                        cur.execute(
                            f"IMPORT FOREIGN SCHEMA {_ident(conn, schema_remoto)} LIMIT TO ({tabelas_sql}) "
                            f"FROM SERVER {_ident(conn, nome_srv)} INTO {_ident(conn, espelho)}"
                        )
                        cur.execute(
                            f"GRANT USAGE ON SCHEMA {_ident(conn, espelho)} TO {_ident(conn, papel_app)}"
                        )
                    conn.commit()
                    servidor_vivo = True
                except psycopg2.Error as e:
                    conn.rollback()
                    msg = (e.diag.message_primary or str(e)).strip().splitlines()[0][:300]
                    aviso = f"servidor remoto '{nome}' não respondeu ({msg})"
                    _log(f"{nome}.{schema_remoto}: IMPORT falhou: {msg}")
                    with conn.cursor() as cur:
                        for cand in grupo:
                            _marcar_indisponivel(
                                cur, schema_plat,
                                f"{cand['fonte_id']}/{cand['schema_nome']}.{cand['tabela']}",
                                dict(cand, servidor=nome), srv["banco"], aviso)
                            stats["indisponiveis"] += 1
                            processadas += 1
                    conn.commit()
                    continue

                for cand in grupo:
                    if time.monotonic() - inicio > PRAZO_TOTAL_S:
                        stats["estourou_prazo"] = True
                        break
                    camada_id = f"{cand['fonte_id']}/{cand['schema_nome']}.{cand['tabela']}"
                    with conn.cursor() as cur:
                        # local é a canônica: remota que colide com linha 'local' já registrada é cópia
                        cur.execute(
                            f"SELECT modo_acesso FROM {_ident(conn, schema_plat)}.acervo_camada "
                            "WHERE acervo_camada_id = %s",
                            (camada_id,),
                        )
                        existente = cur.fetchone()
                    if existente and existente["modo_acesso"] == "local":
                        _log(f"{camada_id}: já registrada como local; remota é cópia, pulada")
                        stats["puladas"] += 1
                        processadas += 1
                        continue

                    geom = _geom_da_foreign(conn, espelho, cand["tabela"])
                    if geom is None:
                        _log(f"{camada_id}: sem coluna de geometria no espelho; não é camada, fora do registro")
                        stats["sem_geometria"] += 1
                        processadas += 1
                        continue
                    coluna_geom, srid, tipo_geom = geom
                    expostas, bloqueadas = _colunas_da_foreign(conn, espelho, cand["tabela"], coluna_geom)
                    n_exato, latencia_ms, erro = _contar_via_fdw(conn, espelho, cand["tabela"])

                    with conn.cursor() as cur:
                        if erro and erro != "timeout":
                            # conexão caiu no meio da rodada: aviso, nunca zero, e o resto do servidor
                            # é tratado do mesmo jeito (não se insiste em rede morta)
                            aviso = f"servidor remoto '{nome}' não respondeu ({erro})"
                            _marcar_indisponivel(cur, schema_plat, camada_id,
                                                 dict(cand, servidor=nome), srv["banco"], aviso)
                            stats["indisponiveis"] += 1
                            processadas += 1
                            conn.commit()
                            servidor_vivo = False
                            _log(f"{camada_id}: rede caiu durante a contagem ({erro}); demais do "
                                 f"servidor marcadas indisponíveis")
                            with conn.cursor() as cur2:
                                for resto in grupo[grupo.index(cand) + 1:]:
                                    _marcar_indisponivel(
                                        cur2, schema_plat,
                                        f"{resto['fonte_id']}/{resto['schema_nome']}.{resto['tabela']}",
                                        dict(resto, servidor=nome), srv["banco"], aviso)
                                    stats["indisponiveis"] += 1
                                    processadas += 1
                            conn.commit()
                            break

                        cur.execute("SELECT licenca, sha256, sha256_cmd FROM acervo.fonte WHERE fonte_id = %s",
                                    (cand["fonte_id"],))
                        fonte = cur.fetchone()
                        licenca = (fonte or {}).get("licenca") if fonte else None
                        tem_licenca = bool(licenca and licenca.strip())

                        if erro == "timeout":
                            estado, motivo = "bloqueada", "contagem_nao_concluida_em_25s"
                        elif not tem_licenca:
                            estado, motivo = "pendente_de_licenca", None
                        else:
                            estado, motivo = "exposta", None

                        cur.execute(
                            SQL_UPSERT_FDW.format(schema=_ident(conn, schema_plat)),
                            {
                                "id": camada_id, "fonte_id": cand["fonte_id"], "servidor": nome,
                                "banco": srv["banco"], "schema_nome": cand["schema_nome"],
                                "tabela": cand["tabela"], "coluna_geom": coluna_geom, "srid": srid,
                                "tipo_geom": tipo_geom, "colunas_expostas": expostas,
                                "colunas_bloqueadas": bloqueadas, "linhas_exatas": n_exato,
                                "linhas_contadas_em": datetime.now(UTC).date() if n_exato is not None else None,
                                "sha256": (fonte or {}).get("sha256"),
                                "comando_reexecucao": (fonte or {}).get("sha256_cmd"),
                                "estado": estado, "motivo_bloqueio": motivo,
                                "modo_acesso": "fdw", "fdw_tabela": f"{espelho}.{cand['tabela']}",
                                "aviso": None, "fdw_latencia_ms": latencia_ms,
                            },
                        )
                        cur.execute(
                            f"GRANT SELECT ON {_ident(conn, espelho)}.{_ident(conn, cand['tabela'])} "
                            f"TO {_ident(conn, papel_app)}"
                        )
                    conn.commit()
                    stats["tabelas_fdw"] += 1
                    processadas += 1

            # poda SÓ com o servidor vivo nesta rodada (nunca às cegas): registro e espelho
            if servidor_vivo:
                ids_vivos = [f"{c['fonte_id']}/{c['schema_nome']}.{c['tabela']}" for c in candidatas]
                with conn.cursor() as cur:
                    cur.execute(
                        f"DELETE FROM {_ident(conn, schema_plat)}.acervo_camada "
                        "WHERE servidor = %s AND modo_acesso IN ('fdw', 'indisponivel') "
                        "AND acervo_camada_id <> ALL(%s)",
                        (nome, ids_vivos),
                    )
                    if cur.rowcount:
                        _log(f"{nome}: {cur.rowcount} linha(s) removida(s) do registro (deixaram de ser candidatas)")
                    cur.execute(
                        "SELECT n.nspname AS espelho, c.relname AS tabela "
                        "FROM pg_foreign_table ft "
                        "JOIN pg_class c ON c.oid = ft.ftgrelid "
                        "JOIN pg_namespace n ON n.oid = c.relnamespace "
                        "JOIN pg_foreign_server fs ON fs.oid = ft.ftserver WHERE fs.srvname = %s",
                        (nome_srv,),
                    )
                    esperadas = {
                        (
                            _nome_curto(f"{_san(schema_plat)}_rm", _san(nome), _san(c["schema_nome"])),
                            c["tabela"],
                        )
                        for c in candidatas
                    }
                    for r in cur.fetchall():
                        if (r["espelho"], r["tabela"]) not in esperadas:
                            cur.execute(
                                f"DROP FOREIGN TABLE IF EXISTS "
                                f"{_ident(conn, r['espelho'])}.{_ident(conn, r['tabela'])}"
                            )
                conn.commit()
                stats["servidores_ok"] += 1
            else:
                stats["servidores_fora"] += 1

        fim = time.monotonic()
        duracao_ms = int((fim - inicio) * 1000)
        with conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO {_ident(conn, schema_plat)}.acervo_fdw_execucao "
                "(iniciado_em, concluido_em, duracao_ms, servidores_ok, servidores_fora, tabelas_fdw, "
                " indisponiveis) VALUES (%s, now(), %s, %s, %s, %s, %s)",
                (inicio_iso, duracao_ms, stats["servidores_ok"], stats["servidores_fora"],
                 stats["tabelas_fdw"], stats["indisponiveis"]),
            )
        conn.commit()
        stats["duracao_s"] = round(fim - inicio, 1)
        stats["processadas"] = processadas
        return stats
    finally:
        conn.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--banco", default="iagro_sat")
    ap.add_argument("--schema", default=os.environ.get("PLAT_SCHEMA", "plat"),
                    help="schema do produto nesta instalação (trilha passa plat_t<nome>)")
    ap.add_argument("--servidor-remoto", action="append", default=None,
                    help="processa só este servidor (repetível); sem a opção, todos os ativos")
    ap.add_argument("--segredos", default=os.environ.get("PLAT_FDW_SEGREDOS_DIR", SEGREDOS_PADRAO),
                    help="diretório do cofre de senhas FDW")
    ap.add_argument("--limite", type=int, default=None, help="só N candidatas por servidor (depuração)")
    args = ap.parse_args()

    stats = sincronizar({"dbname": args.banco}, args.schema, Path(args.segredos),
                        args.servidor_remoto, args.limite)
    _log(
        f"servidores_ok={stats['servidores_ok']} servidores_fora={stats['servidores_fora']} "
        f"tabelas_fdw={stats['tabelas_fdw']} indisponiveis={stats['indisponiveis']} "
        f"puladas={stats['puladas']} sem_geometria={stats['sem_geometria']} "
        f"duracao_s={stats['duracao_s']} estourou_prazo={stats['estourou_prazo']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
