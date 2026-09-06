#!/usr/bin/env python3
"""Sincronizador de `plat.acervo_camada` (item L6-01-a-registro; migração 027; ADR ver
laco/decomposicao/L3L6_CONCEITO.md B1/B2/B5). Roda como `postgres` (mesma identidade de `db/migrar.sh`),
com o `psycopg2` do sistema (dpkg python3-psycopg2, sem venv) — nunca como `plat_app`, que só LÊ esta tabela.

    sudo -u postgres python3 scripts/acervo_sync.py [--banco iagro_sat] [--limite N]

O que faz, em ordem:
  1. Lista candidatas: tabela CANÔNICA (`acervo.objeto.canonico`), tipo 'fonte', no servidor e banco desta
     máquina, com coluna de geometria em `geometry_columns` (uma linha por tabela; se houver mais de uma
     coluna de geometria, fica a primeira em ordem alfabética preferindo 'geom'/'geometry').
  2. Para cada candidata: conta com `COUNT(*)` exato sob `statement_timeout` de 25 s (mesmo padrão do
     `contagem2.py` da casa) — timeout NUNCA vira zero, vira `linhas_exatas = NULL` e o motivo fica registrado
     (metodologia §7.31: ausência de dado nunca é medição). Nenhum nome de tabela é digitado em código: a
     regra abaixo ("tabela fantasma") é dinâmica (estimativa > 0 e contagem exata = 0), não uma lista de
     exceção — é o que a refutação do item cobra.
  3. Monta a lista branca de colunas: todas as colunas de `information_schema.columns` MENOS a própria
     geometria (fica em `coluna_geom`) MENOS o que casar (nome EXATO, case-insensitive) com `_COLUNA_NEGADA`
     — checagem GROSSA, só pelo NOME da coluna. Isto é rede de segurança provisória; a checagem fina por
     CONTEÚDO (regex de CPF/CNPJ em amostra) é o item L6-01-f, que ainda não existe — nenhuma camada deste
     sincronizador é exposta à tela antes de o L6-01-f rodar em cima dela (ver docs/adr/0012).
  4. Estado: 'bloqueada' se a contagem não concluiu OU se é tabela fantasma (estimativa > 0, exata = 0);
     'pendente_de_licenca' se `acervo.fonte.licenca` está vazia (regra D17, mesmo critério de `plat.acervo_ficha`
     na migração 021); senão 'exposta'.
  5. UPSERT em `plat.acervo_camada` por `acervo_camada_id = '<fonte_id>/<schema>.<tabela>'` (decisão B2);
     remove do registro quem não é mais candidata (a tabela sumiu ou perdeu a geometria) — só quando a
     rodada encontrou pelo menos 1 candidata (nunca esvazia por bug de conexão).
  6. Grava 1 linha em `plat.acervo_camada_execucao` com os números da rodada e a duração.

Prazo duro de 270 s (item pede "≤ 5 min" — folga para o INSERT final e o commit): ao estourar, as candidatas
que sobrarem entram como 'bloqueada'/'nao_processada_no_prazo' em vez de travar o processo — erro nunca é
sucesso, mas também nunca é uma trava sem fim.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import UTC, datetime

import psycopg2
import psycopg2.errors
import psycopg2.extras

TIMEOUT_CONTAGEM_MS = 25_000
PRAZO_TOTAL_S = 270.0  # folga de 30 s sob o portão de 5 min

# rede de segurança GROSSA por nome de coluna (case-insensitive, casamento EXATO — nunca substring, para não
# confundir "nom_tema"/"nom_munic" com identificador de pessoa); a varredura fina por conteúdo é L6-01-f.
_COLUNA_NEGADA = {
    "cpf", "cnpj", "nome", "nome_completo", "nome_pessoa", "nome_titular", "nome_proprietario",
    "nome_socio", "nome_responsavel", "nome_paciente", "nome_mae", "nome_pai", "razao_social_pf",
    "email", "e_mail", "telefone", "celular", "fone", "rg", "identidade", "passaporte",
    "pis", "nis", "nit", "cns", "titular_cpf", "titular_nome", "proprietario_cpf", "endereco_residencial",
}

SQL_CANDIDATAS = """
SELECT DISTINCT ON (o.schema_nome, o.tabela)
       o.fonte_id, o.servidor, o.banco, o.schema_nome, o.tabela, o.linhas_est,
       g.f_geometry_column AS coluna_geom, g.srid, g.type AS tipo_geom
FROM acervo.objeto o
JOIN geometry_columns g
  ON g.f_table_schema = o.schema_nome AND g.f_table_name = o.tabela
WHERE o.tipo = 'fonte' AND o.canonico AND o.servidor = %(servidor)s AND o.banco = %(banco)s
  AND o.fonte_id IS NOT NULL
ORDER BY o.schema_nome, o.tabela,
         (lower(g.f_geometry_column) NOT IN ('geom', 'geometry')), g.f_geometry_column
"""

SQL_FONTE = "SELECT licenca, sha256, sha256_cmd FROM acervo.fonte WHERE fonte_id = %s"

SQL_UPSERT = """
INSERT INTO plat.acervo_camada
  (acervo_camada_id, fonte_id, servidor, banco, schema_nome, tabela, coluna_geom, srid, tipo_geom,
   colunas_expostas, colunas_bloqueadas, linhas_exatas, linhas_contadas_em, linhas_estimadas,
   sha256, comando_reexecucao, estado, motivo_bloqueio, sincronizado_em)
VALUES (%(id)s, %(fonte_id)s, %(servidor)s, %(banco)s, %(schema_nome)s, %(tabela)s, %(coluna_geom)s,
        %(srid)s, %(tipo_geom)s, %(colunas_expostas)s, %(colunas_bloqueadas)s, %(linhas_exatas)s,
        %(linhas_contadas_em)s, %(linhas_estimadas)s, %(sha256)s, %(comando_reexecucao)s, %(estado)s,
        %(motivo_bloqueio)s, now())
ON CONFLICT (acervo_camada_id) DO UPDATE SET
  fonte_id = EXCLUDED.fonte_id, servidor = EXCLUDED.servidor, banco = EXCLUDED.banco,
  schema_nome = EXCLUDED.schema_nome, tabela = EXCLUDED.tabela, coluna_geom = EXCLUDED.coluna_geom,
  srid = EXCLUDED.srid, tipo_geom = EXCLUDED.tipo_geom, colunas_expostas = EXCLUDED.colunas_expostas,
  colunas_bloqueadas = EXCLUDED.colunas_bloqueadas, linhas_exatas = EXCLUDED.linhas_exatas,
  linhas_contadas_em = EXCLUDED.linhas_contadas_em, linhas_estimadas = EXCLUDED.linhas_estimadas,
  sha256 = EXCLUDED.sha256, comando_reexecucao = EXCLUDED.comando_reexecucao, estado = EXCLUDED.estado,
  motivo_bloqueio = EXCLUDED.motivo_bloqueio, sincronizado_em = now()
"""


def _log(msg: str) -> None:
    print(f"[acervo_sync] {msg}", file=sys.stderr, flush=True)


def _colunas_da_tabela(cur, schema: str, tabela: str, coluna_geom: str) -> tuple[list[str], list[str]]:
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position",
        (schema, tabela),
    )
    todas = [r["column_name"] for r in cur.fetchall()]
    expostas, bloqueadas = [], []
    for c in todas:
        if c == coluna_geom:
            continue
        if c.lower() in _COLUNA_NEGADA:
            bloqueadas.append(c)
        else:
            expostas.append(c)
    return expostas, bloqueadas


def _contar_exato(conn, schema: str, tabela: str) -> int | None:
    """COUNT(*) sob statement_timeout de 25 s; None = não concluiu (nunca vira 0)."""
    ident = psycopg2.extensions.quote_ident(schema, conn) + "." + psycopg2.extensions.quote_ident(tabela, conn)
    try:
        with conn.cursor() as cur:
            cur.execute(f"SET LOCAL statement_timeout = {TIMEOUT_CONTAGEM_MS}")
            cur.execute(f"SELECT count(*) FROM {ident}")  # noqa: S608 — identificadores citados, sem dado do chamador
            n = cur.fetchone()["count"]
        conn.commit()
        return n
    except (psycopg2.errors.QueryCanceled, psycopg2.errors.UndefinedTable, psycopg2.Error) as e:
        conn.rollback()
        _log(f"contagem não concluída em {schema}.{tabela}: {type(e).__name__}")
        return None


def sincronizar(dsn_kwargs: dict, servidor: str, banco: str, limite: int | None = None) -> dict:
    inicio = time.monotonic()
    inicio_iso = datetime.now(UTC)
    conn = psycopg2.connect(cursor_factory=psycopg2.extras.RealDictCursor, **dsn_kwargs)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(SQL_CANDIDATAS, {"servidor": servidor, "banco": banco})
            candidatas = cur.fetchall()
            cur.execute("SELECT acervo_camada_id, sincronizado_em FROM plat.acervo_camada")
            ultima_sinc = {r["acervo_camada_id"]: r["sincronizado_em"] for r in cur.fetchall()}
        conn.commit()

        # ordem por PROGRESSO, não alfabética: quem nunca sincronizou (ou sincronizou há mais tempo) vai
        # primeiro, para que uma rodada que estoura o prazo (máquina ocupada com outro job pesado da casa —
        # medido 06/09/2026: REFRESH MATERIALIZED VIEW de 3h e COUNT(*) de 18 min concorrentes) processe
        # tabelas DIFERENTES na próxima vez, em vez de sempre travar nas primeiras da ordem alfabética.
        epoca = datetime.min.replace(tzinfo=UTC)
        candidatas = sorted(
            candidatas,
            key=lambda r: ultima_sinc.get(f"{r['fonte_id']}/{r['schema_nome']}.{r['tabela']}", epoca),
        )
        # o universo COMPLETO de ids candidatos (antes do --limite) é o que decide o que é lixo a podar; um
        # --limite (depuração/teste) processa só um pedaço, mas NUNCA pode fazer o resto do registro parecer
        # "sumiu" — só id fora deste conjunto completo é removido (tabela que perdeu geometria/canonicidade de
        # verdade), nunca um id que só não coube nesta rodada limitada.
        todos_os_ids_candidatos = {f"{r['fonte_id']}/{r['schema_nome']}.{r['tabela']}" for r in candidatas}
        if limite:
            candidatas = candidatas[:limite]

        expostas = bloqueadas = pendentes = fantasmas = nao_concluidas = 0
        sincronizados: list[str] = []
        estourou_prazo = False

        with conn.cursor() as cur:
            for row in candidatas:
                acervo_camada_id = f"{row['fonte_id']}/{row['schema_nome']}.{row['tabela']}"

                if time.monotonic() - inicio > PRAZO_TOTAL_S:
                    estourou_prazo = True
                    cur.execute(
                        SQL_UPSERT,
                        {
                            "id": acervo_camada_id, "fonte_id": row["fonte_id"], "servidor": row["servidor"],
                            "banco": row["banco"], "schema_nome": row["schema_nome"], "tabela": row["tabela"],
                            "coluna_geom": row["coluna_geom"], "srid": row["srid"] or 0,
                            "tipo_geom": row["tipo_geom"] or "GEOMETRY", "colunas_expostas": [],
                            "colunas_bloqueadas": [], "linhas_exatas": None, "linhas_contadas_em": None,
                            "linhas_estimadas": row["linhas_est"], "sha256": None, "comando_reexecucao": None,
                            "estado": "bloqueada", "motivo_bloqueio": "nao_processada_no_prazo",
                        },
                    )
                    bloqueadas += 1
                    sincronizados.append(acervo_camada_id)
                    continue

                expostas_cols, bloqueadas_cols = _colunas_da_tabela(
                    cur, row["schema_nome"], row["tabela"], row["coluna_geom"]
                )
                n_exato = _contar_exato(conn, row["schema_nome"], row["tabela"])

                fonte = None
                with conn.cursor() as cur2:
                    cur2.execute(SQL_FONTE, (row["fonte_id"],))
                    fonte = cur2.fetchone()
                licenca = (fonte or {}).get("licenca") if fonte else None
                tem_licenca = bool(licenca and licenca.strip())

                motivo = None
                if n_exato is None:
                    estado, motivo = "bloqueada", "contagem_nao_concluida_em_25s"
                    nao_concluidas += 1
                    bloqueadas += 1
                elif n_exato == 0 and (row["linhas_est"] or 0) > 0:
                    estado, motivo = "bloqueada", "tabela_fantasma_estimativa_sem_dado"
                    fantasmas += 1
                    bloqueadas += 1
                elif not tem_licenca:
                    estado = "pendente_de_licenca"
                    pendentes += 1
                else:
                    estado = "exposta"
                    expostas += 1

                cur.execute(
                    SQL_UPSERT,
                    {
                        "id": acervo_camada_id, "fonte_id": row["fonte_id"], "servidor": row["servidor"],
                        "banco": row["banco"], "schema_nome": row["schema_nome"], "tabela": row["tabela"],
                        "coluna_geom": row["coluna_geom"], "srid": row["srid"] or 0,
                        "tipo_geom": row["tipo_geom"] or "GEOMETRY", "colunas_expostas": expostas_cols,
                        "colunas_bloqueadas": bloqueadas_cols, "linhas_exatas": n_exato,
                        "linhas_contadas_em": datetime.now(UTC).date() if n_exato is not None else None,
                        "linhas_estimadas": row["linhas_est"], "sha256": (fonte or {}).get("sha256"),
                        "comando_reexecucao": (fonte or {}).get("sha256_cmd"), "estado": estado,
                        "motivo_bloqueio": motivo,
                    },
                )
                sincronizados.append(acervo_camada_id)
            conn.commit()

            removidas = 0
            if todos_os_ids_candidatos:
                # item L6-01-j-multi-servidor: a poda é SÓ do servidor LOCAL (o desta rodada). Linhas
                # de servidor remoto (modo_acesso 'fdw'/'indisponivel', escritas por acervo_fdw_sync.py)
                # nunca são candidatas aqui e não podem sumir por isso.
                cur.execute(
                    "DELETE FROM plat.acervo_camada WHERE servidor = %(servidor)s "
                    "AND acervo_camada_id <> ALL(%(ids)s)",
                    {"servidor": servidor, "ids": list(todos_os_ids_candidatos)},
                )
                removidas = cur.rowcount
                conn.commit()

        fim = time.monotonic()
        stats = {
            "candidatas": len(candidatas), "expostas": expostas, "bloqueadas": bloqueadas,
            "pendentes": pendentes, "fantasmas": fantasmas, "nao_concluidas": nao_concluidas,
            "removidas": removidas, "duracao_s": round(fim - inicio, 1), "estourou_prazo": estourou_prazo,
        }
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO plat.acervo_camada_execucao "
                "(iniciado_em, concluido_em, duracao_ms, candidatas, expostas, bloqueadas, pendentes, "
                " fantasmas, nao_concluidas) VALUES (%s, now(), %s, %s, %s, %s, %s, %s, %s)",
                (
                    inicio_iso, int((fim - inicio) * 1000), stats["candidatas"], expostas, bloqueadas,
                    pendentes, fantasmas, nao_concluidas,
                ),
            )
        conn.commit()
        return stats
    finally:
        conn.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--banco", default="iagro_sat")
    ap.add_argument("--servidor", default="vultr", help="acervo.objeto.servidor desta máquina (medido: 'vultr')")
    ap.add_argument("--limite", type=int, default=None, help="só as N primeiras candidatas (depuração/teste)")
    args = ap.parse_args()

    stats = sincronizar({"dbname": args.banco}, args.servidor, args.banco, args.limite)
    _log(
        f"candidatas={stats['candidatas']} expostas={stats['expostas']} bloqueadas={stats['bloqueadas']} "
        f"pendentes_de_licenca={stats['pendentes']} fantasmas={stats['fantasmas']} "
        f"nao_concluidas={stats['nao_concluidas']} removidas={stats['removidas']} "
        f"duracao_s={stats['duracao_s']} estourou_prazo={stats['estourou_prazo']}"
    )
    if stats["duracao_s"] > 300:
        _log("ATENÇÃO: passou de 5 min mesmo com o prazo duro (bug no controle de tempo)")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
