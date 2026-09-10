"""Tipos de job do backup lógico por inquilino (item L0-06-backup-status; porta
`/home/dev/fgr/sig/pipeline/backup.sh`/`restore_test.sh` para o multi-inquilino do PLAT — ver o desenho
completo em `app/backup/__init__.py`).

`backup.executar` — pg_dump -Fc (comprimido) do schema `d_<slug>` do PRÓPRIO inquilino do job, sha256,
tamanho e tempo em `plat.backup`, sobe ao bucket do PRÓPRIO inquilino no Garage (`app/objetos.py`, mesmo
caminho de `app/imagens/ingestao.py`). Recusa (FalhaDefinitiva, arquivo apagado, sem subir nada) acima do
teto de `limites.BACKUP_DUMP_BYTES_MAX` — disco a 99% nesta máquina, o código nunca presume schema pequeno.

`backup.ensaio_restauracao` — baixa o dump mais recente do inquilino, confere o sha256 contra o registrado,
restaura num schema temporário `plat_ensaio_<hex>` NA MESMA base (o Postgres é compartilhado com sistemas
de cliente: sem banco novo, sem reinício), compara COUNT(*) de cada tabela contra a produção, grava o
veredito em `plat.backup_drill` e DERRUBA o schema temporário sempre — inclusive quando a restauração ou a
contagem falham no meio do caminho (bloco `finally`)."""

from __future__ import annotations

import json
import re
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from app import limites, objetos
from app.backup import nucleo
from app.jobs.registro import FalhaDefinitiva, tarefa
from app.settings import settings

_IDENT_SQL = re.compile(r"^[a-z][a-z0-9_]*$")


def _banco_nome() -> str:
    return urlparse(settings.PLAT_DSN).path.lstrip("/")


def _slug_e_esquema(ctx) -> tuple[str, str]:
    with ctx.db() as cur:
        cur.execute("SELECT slug FROM plat.tenant WHERE id = %s", (ctx.tenant_id,))
        r = cur.fetchone()
    if r is None:
        raise FalhaDefinitiva("backup: inquilino inexistente no contexto do job")
    slug = r["slug"]
    esquema = f"d_{slug}"
    if not _IDENT_SQL.match(esquema):
        raise FalhaDefinitiva(f"backup: nome de schema fora do padrão esperado ({esquema!r})")
    return slug, esquema


def _contar_tabelas(cur, esquema: str) -> int:
    cur.execute("SELECT count(*) AS n FROM pg_tables WHERE schemaname = %s", (esquema,))
    return int(cur.fetchone()["n"])


def _notificar_falha(ctx, motivo: str, detalhe: dict) -> None:
    """Falha de backup/ensaio NUNCA é silêncio: log ERRO do job + evento auditável no inquilino (o item
    L0-06 pede notificação ao superadmin; o canal de e-mail (`correio.enviar`, L0-07-d) fica para um turno
    que já mexa em SMTP — aqui o evento é o registro permanente e verificável que fica na tela /admin/log e
    em /admin/backup, e é o que os testes conferem)."""
    ctx.log("ERRO", f"backup: {motivo}")
    try:
        with ctx.db() as cur:
            cur.execute(
                "SELECT plat.evento_registrar('backup/falha', 'backup', NULL, %s::jsonb, NULL, NULL)",
                (json.dumps({"motivo": motivo, **detalhe}, default=str),),
            )
    except Exception as e:  # a falha do job em si já é o alarme principal; isto nunca pode mascará-la
        ctx.log("ERRO", f"backup: falha também ao registrar o evento de notificação: {e}")


# ---------------------------------------------------------------- backup.executar
class ExecutarParametros(BaseModel):
    origem: str = Field("manual", max_length=40)


@tarefa(
    nome="backup.executar",
    descricao="Backup: pg_dump -Fc (comprimido) do schema do inquilino, sha256/bytes/tempo em plat.backup, "
    "cópia no bucket do próprio inquilino no Garage; recusa acima do teto de tamanho desta instalação",
    parametros=ExecutarParametros,
    pesado=True,
    memoria_mb=512,
    timeout_s=limites.BACKUP_DUMP_TIMEOUT_S,
    tentativas=1,
    chave=lambda p: "executar",
    perfil_minimo="admin",
)
def backup_executar(ctx, origem: str = "manual") -> dict:
    inicio = time.monotonic()
    slug, esquema = _slug_e_esquema(ctx)
    banco_nome = _banco_nome()

    diretorio: Path = ctx.dir_trabalho
    # pg_dump roda como o superusuário local `postgres` (sudo -n; mesmo padrão de backup.sh do SIG de teste
    # interno da casa — só assim o dump é completo sem um papel novo com BYPASSRLS e senha para guardar) e
    # escreve o arquivo com aquele dono: o diretório do job (do worker, 0700 por padrão) precisa aceitar
    # escrita de outro usuário, senão o pg_dump sai com "Permission denied" antes de criar o arquivo.
    diretorio.chmod(0o777)
    agora = datetime.now(UTC)
    nome = nucleo.nome_arquivo(esquema, agora)
    tmp = diretorio / nome

    ctx.progresso(5, f"despejando o schema {esquema} (pg_dump -Fc)")
    r = ctx.subprocesso([
        "sudo", "-n", "-u", "postgres", "pg_dump", "-d", banco_nome, "-n", esquema,
        "--format=custom", "--compress=6", "--no-owner", "--no-privileges", "-f", str(tmp),
    ])
    if r.returncode != 0 or not tmp.exists() or tmp.stat().st_size == 0:
        _notificar_falha(ctx, f"pg_dump de {esquema} saiu com código {r.returncode}", {"esquema": esquema})
        raise FalhaDefinitiva(f"backup: pg_dump de {esquema} saiu com código {r.returncode}")

    # o arquivo nasce 0600 do dono `postgres`: só o dono (ou root) pode liberar a leitura para o processo do
    # worker (usuário diferente) — sem isto o processo abaixo (sha256/upload) não consegue nem abrir o
    # arquivo que acabou de escrever.
    r_chmod = ctx.subprocesso(["sudo", "-n", "-u", "postgres", "chmod", "644", str(tmp)])
    if r_chmod.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise FalhaDefinitiva(f"backup: chmod do dump de {esquema} saiu com código {r_chmod.returncode}")

    tamanho = tmp.stat().st_size
    if tamanho > limites.BACKUP_DUMP_BYTES_MAX:
        tmp.unlink(missing_ok=True)
        _notificar_falha(ctx, f"dump de {tamanho} bytes acima do teto desta instalação "
                              f"({limites.BACKUP_DUMP_BYTES_MAX} bytes)", {"esquema": esquema, "bytes": tamanho})
        raise FalhaDefinitiva(
            f"backup: dump de {esquema} tem {tamanho} bytes, acima do teto desta instalação "
            f"({limites.BACKUP_DUMP_BYTES_MAX} bytes) — nada foi enviado ao armazenamento"
        )
    ctx.progresso(55, f"{tamanho / 1e6:.1f} MB despejados; subindo ao armazenamento do inquilino")

    with ctx.db() as cur:
        tabelas = _contar_tabelas(cur, esquema)
        try:
            obj = objetos.guardar_arquivo(cur, "backup", tmp, "application/octet-stream", usuario_id=ctx.usuario_id)
        except Exception as e:
            tmp.unlink(missing_ok=True)
            _notificar_falha(ctx, f"upload do dump ao armazenamento falhou: {e}", {"esquema": esquema})
            raise FalhaDefinitiva(f"backup: upload ao armazenamento do inquilino falhou: {e}") from e
    # disco a 99% (CLAUDE.md): o dump nunca fica parado no /tmp do job depois de subir ao Garage
    tmp.unlink(missing_ok=True)

    tempo = round(time.monotonic() - inicio, 2)
    with ctx.db() as cur:
        cur.execute(
            "INSERT INTO plat.backup(tenant_id, job_id, esquema, chave, sha256, bytes, tabelas, tempo_dump_s, "
            "origem, criado_por) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (ctx.tenant_id, str(ctx.job_id), esquema, obj["chave"], obj["sha256"], obj["bytes"], tabelas, tempo,
             origem, ctx.usuario_id or None),
        )
        backup_id = cur.fetchone()["id"]
        cur.execute(
            "SELECT plat.evento_registrar('backup/executar', 'backup', %s, %s::jsonb, NULL, NULL)",
            (str(backup_id), json.dumps({"esquema": esquema, "bytes": obj["bytes"], "tabelas": tabelas,
                                         "tempo_dump_s": tempo, "origem": origem}, default=str)),
        )
    ctx.entrada(None, obj["sha256"], f"dump de {esquema}")
    ctx.progresso(100, f"backup #{backup_id}: {obj['bytes'] / 1e6:.1f} MB, {tabelas} tabelas, {tempo:.1f} s "
                      f"(sha256 {obj['sha256'][:12]}…)")
    return {"backup_id": backup_id, "esquema": esquema, "chave": obj["chave"], "sha256": obj["sha256"],
            "bytes": obj["bytes"], "tabelas": tabelas, "tempo_dump_s": tempo}


# ---------------------------------------------------------------- backup.ensaio_restauracao
class EnsaioParametros(BaseModel):
    origem: str = Field("manual", max_length=40)


def _restaurar_em_schema_temporario(ctx, dump_local: Path, esquema: str, schema_ensaio: str, banco_nome: str) -> None:
    """`pg_restore -f` converte o dump `-Fc` para SQL de TEXTO (não há opção de renomear o schema de
    destino no formato binário); troca o nome do schema por substituição de texto e roda o resultado com
    `psql` — cria só o schema de ensaio, nunca toca o schema de produção do inquilino. Roda fora de
    `ctx.subprocesso` de propósito: aquele método registra CADA LINHA de stdout em `plat.job_log` (bom para
    `pg_dump`/`psql`, que são enxutos; ruim aqui, onde o SQL de texto de um schema inteiro pode ter milhares
    de linhas de COPY — estouraria o teto de 10.000 linhas do log em um único job)."""
    diretorio = dump_local.parent
    sql_bruto = diretorio / "ensaio.sql"
    r1 = subprocess.run(
        ["sudo", "-n", "-u", "postgres", "pg_restore", "--no-owner", "--no-privileges", "-f", str(sql_bruto),
         str(dump_local)],
        capture_output=True, text=True, cwd=str(diretorio), timeout=limites.BACKUP_DRILL_TIMEOUT_S,
    )
    for linha in (r1.stderr or "").splitlines():
        if linha.strip():
            ctx.log("AVISO", f"pg_restore -f: {linha}")
    if not sql_bruto.exists() or sql_bruto.stat().st_size == 0:
        raise FalhaDefinitiva(f"ensaio de restauração: pg_restore -f não gerou SQL (código {r1.returncode})")
    subprocess.run(["sudo", "-n", "-u", "postgres", "chmod", "644", str(sql_bruto)], check=False,
                   timeout=30)

    texto = sql_bruto.read_text(encoding="utf-8", errors="replace")
    reescrito = nucleo.reescrever_schema(texto, esquema, schema_ensaio)
    sql_reescrito = diretorio / "ensaio_reescrito.sql"
    sql_reescrito.write_text(reescrito, encoding="utf-8")
    sql_bruto.unlink(missing_ok=True)

    r2 = ctx.subprocesso([
        "sudo", "-n", "-u", "postgres", "psql", "-d", banco_nome, "-v", "ON_ERROR_STOP=1", "-q", "-f",
        str(sql_reescrito),
    ])
    sql_reescrito.unlink(missing_ok=True)
    if r2.returncode != 0:
        raise FalhaDefinitiva(f"ensaio de restauração: psql da cópia restaurada saiu com código {r2.returncode}")


def _largar_schema_ensaio(ctx, schema_ensaio: str, banco_nome: str) -> None:
    """DROP SCHEMA do ensaio. A guarda do prefixo está aqui, não só em quem chama — é o único lugar do
    produto que derruba schema por nome vindo de um job, e apontar isso para o schema de um inquilino de
    verdade apagaria dado de produção."""
    if not schema_ensaio.startswith(nucleo.PREFIXO_SCHEMA_ENSAIO):
        raise FalhaDefinitiva(f"ensaio de restauração: recusa derrubar schema fora do padrão de ensaio "
                              f"({schema_ensaio!r})")
    ctx.subprocesso(["sudo", "-n", "-u", "postgres", "psql", "-d", banco_nome, "-q", "-c",
                     f'DROP SCHEMA IF EXISTS "{schema_ensaio}" CASCADE'])


@tarefa(
    nome="backup.ensaio_restauracao",
    descricao="Backup: restaura o último dump do inquilino num schema temporário, confere COUNT(*) de cada "
    "tabela contra a produção e grava o veredito em plat.backup_drill; o schema temporário é sempre "
    "derrubado ao final, inclusive em erro",
    parametros=EnsaioParametros,
    pesado=True,
    memoria_mb=512,
    timeout_s=limites.BACKUP_DRILL_TIMEOUT_S,
    tentativas=1,
    chave=lambda p: "ensaio_restauracao",
    perfil_minimo="admin",
)
def backup_ensaio_restauracao(ctx, origem: str = "manual") -> dict:
    inicio = time.monotonic()
    with ctx.db() as cur:
        cur.execute(
            "SELECT id, esquema, chave, sha256, bytes FROM plat.backup WHERE tenant_id = %s "
            "ORDER BY criado_em DESC LIMIT 1", (ctx.tenant_id,),
        )
        ultimo = cur.fetchone()
    if ultimo is None:
        raise FalhaDefinitiva(
            "ensaio de restauração: nenhum backup registrado para este inquilino (rode backup.executar antes)"
        )
    banco_nome = _banco_nome()
    esquema = ultimo["esquema"]
    schema_ensaio = nucleo.nome_schema_ensaio()
    diretorio: Path = ctx.dir_trabalho
    diretorio.chmod(0o777)
    dump_local = diretorio / "ensaio.dump"

    ctx.progresso(5, "baixando o dump mais recente do armazenamento do inquilino")
    try:
        objetos.baixar(ultimo["chave"], dump_local)
    except (FileNotFoundError, objetos.ChaveInvalida) as e:
        raise FalhaDefinitiva(f"ensaio de restauração: o dump não existe mais no armazenamento: {e}") from e
    sha_atual = nucleo.sha256_arquivo(dump_local)
    if sha_atual != ultimo["sha256"]:
        _notificar_falha(ctx, "sha256 do dump baixado difere do registrado em plat.backup",
                         {"backup_id": ultimo["id"], "sha256_registrado": ultimo["sha256"],
                          "sha256_atual": sha_atual})
        dump_local.unlink(missing_ok=True)
        raise FalhaDefinitiva(
            "ensaio de restauração: sha256 do dump divergente do registrado em plat.backup — backup corrompido"
        )

    tabelas: list[str] = []
    contagens_restauradas: dict[str, int] = {}
    divergencias: list[dict] = []
    posteriores: list[dict] = []
    try:
        ctx.progresso(20, f"restaurando em {schema_ensaio}")
        _restaurar_em_schema_temporario(ctx, dump_local, esquema, schema_ensaio, banco_nome)

        ctx.progresso(55, "contando linhas por tabela (produção x cópia restaurada)")
        with ctx.db() as cur:
            cur.execute(
                "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE c.relkind = 'r' AND n.nspname = %s ORDER BY 1", (esquema,),
            )
            tabelas = [row["relname"] for row in cur.fetchall()]
            contagens_producao: dict[str, int] = {}
            for t in tabelas:
                cur.execute(f'SELECT count(*) AS n FROM "{esquema}"."{t}"')
                contagens_producao[t] = int(cur.fetchone()["n"])
            cur.execute(
                "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE c.relkind = 'r' AND n.nspname = %s", (schema_ensaio,),
            )
            restauradas_nomes = {row["relname"] for row in cur.fetchall()}
            for t in tabelas:
                if t in restauradas_nomes:
                    cur.execute(f'SELECT count(*) AS n FROM "{schema_ensaio}"."{t}"')
                    contagens_restauradas[t] = int(cur.fetchone()["n"])
        comparadas = [{"tabela": t, "restaurado": contagens_restauradas.get(t), "producao": contagens_producao[t]}
                      for t in tabelas]
        divergencias, posteriores = nucleo.classificar_contagens(comparadas)
    finally:
        # sempre — inclusive se _restaurar_em_schema_temporario ou a contagem levantarem
        ctx.progresso(90, f"derrubando o schema de ensaio {schema_ensaio}")
        _largar_schema_ensaio(ctx, schema_ensaio, banco_nome)
        dump_local.unlink(missing_ok=True)

    duracao = round(time.monotonic() - inicio, 2)
    ok = not divergencias
    mensagem = "sem divergência" if ok else "; ".join(
        f"{d['tabela']}: {d['motivo']}" for d in divergencias
    )[:900]
    linhas_restauradas = sum(contagens_restauradas.values())
    with ctx.db() as cur:
        cur.execute(
            "INSERT INTO plat.backup_drill(tenant_id, backup_id, job_id, esquema, schema_ensaio, tabelas, "
            "linhas, divergencias, posteriores, objetos_conferidos, ok, mensagem, duracao_drill_s, origem) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s) RETURNING id",
            (ctx.tenant_id, ultimo["id"], str(ctx.job_id), esquema, schema_ensaio, len(tabelas),
             linhas_restauradas, json.dumps(divergencias, default=str), json.dumps(posteriores, default=str),
             0, ok, mensagem, duracao, origem),
        )
        drill_id = cur.fetchone()["id"]
        cur.execute(
            "SELECT plat.evento_registrar('backup/ensaio_restauracao', 'backup_drill', %s, %s::jsonb, NULL, NULL)",
            (str(drill_id), json.dumps({"ok": ok, "tabelas": len(tabelas), "linhas": linhas_restauradas,
                                        "divergencias": len(divergencias), "posteriores": len(posteriores)},
                                       default=str)),
        )
    if not ok:
        _notificar_falha(ctx, f"ensaio de restauração reprovado — {mensagem}",
                         {"backup_id": ultimo["id"], "drill_id": drill_id, "divergencias": divergencias[:20]})
        raise FalhaDefinitiva(f"ensaio de restauração: {mensagem}")
    ctx.progresso(100, f"ensaio #{drill_id}: {len(tabelas)} tabelas, {linhas_restauradas} linhas restauradas, "
                      f"{len(posteriores)} tabela(s) com escrita posterior ao dump, sem divergência")
    return {"drill_id": drill_id, "backup_id": ultimo["id"], "ok": ok, "tabelas": len(tabelas),
            "linhas": linhas_restauradas, "divergencias": divergencias, "posteriores": posteriores,
            "duracao_drill_s": duracao}


from app.backup import periodicos  # noqa: E402,F401 — importar registra os periódicos do backup na lista do worker
