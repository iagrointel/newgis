"""Rotas de LEITURA do backup lógico por inquilino (item L0-06-backup-status): `GET /api/backup/backups` e
`GET /api/backup/ensaios` alimentam a tela `/admin/backup`. Disparar um backup ou um ensaio não tem rota
própria — a tela usa a MESMA fila genérica que qualquer tarefa (`POST /api/jobs {"tipo": "backup.executar"}`
/ `"backup.ensaio_restauracao"`, `app/jobs/rotas.py`), que já recusa quem não é admin do inquilino pelo
`perfil_minimo="admin"` registrado em `app/backup/tarefas.py` — duas portas de autorização diferentes
(privilégio nesta rota, perfil na fila) teriam o mesmo efeito com o dobro de lugar para divergir."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app import db, limites
from app.auth.sessao import Auth, autenticado

router = APIRouter(prefix="/api/backup", tags=["backup"])
PRIV_LER = {"x-auth": "S/T", "x-privilegio": "org.configurar"}


class BackupSaida(BaseModel):
    id: int
    job_id: str | None
    esquema: str
    sha256: str
    bytes: int
    tabelas: int
    tempo_dump_s: float
    origem: str
    criado_em: str


class BackupsPagina(BaseModel):
    itens: list[BackupSaida]
    total: int


class EnsaioSaida(BaseModel):
    id: int
    backup_id: int | None
    job_id: str | None
    esquema: str
    schema_ensaio: str | None
    tabelas: int
    linhas: int
    objetos_conferidos: int
    ok: bool
    mensagem: str | None
    duracao_drill_s: float
    origem: str
    criado_em: str


class EnsaiosPagina(BaseModel):
    itens: list[EnsaioSaida]
    total: int


def _limite_deslocamento(limite: int | None, deslocamento: int | None) -> tuple[int, int]:
    lim = min(max(int(limite or 50), 1), limites.BACKUP_LISTA_MAX)
    des = max(int(deslocamento or 0), 0)
    return lim, des


def _quando(v) -> str:
    return v.astimezone().isoformat(timespec="seconds") if v else None  # type: ignore[return-value]


@router.get("/backups", response_model=BackupsPagina, openapi_extra=PRIV_LER)
def backups_listar(limite: int = 50, deslocamento: int = 0,
                   auth: Auth = autenticado("org.configurar", escopo_token="admin:inquilino")):
    lim, des = _limite_deslocamento(limite, deslocamento)
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT count(*) AS n FROM plat.backup")
        total = int(cur.fetchone()["n"])
        cur.execute(
            "SELECT id, job_id, esquema, sha256, bytes, tabelas, tempo_dump_s, origem, criado_em "
            "FROM plat.backup ORDER BY criado_em DESC LIMIT %s OFFSET %s", (lim, des),
        )
        linhas = cur.fetchall()
    itens = [
        {"id": r["id"], "job_id": str(r["job_id"]) if r["job_id"] else None, "esquema": r["esquema"],
         "sha256": r["sha256"], "bytes": r["bytes"], "tabelas": r["tabelas"],
         "tempo_dump_s": float(r["tempo_dump_s"]), "origem": r["origem"], "criado_em": _quando(r["criado_em"])}
        for r in linhas
    ]
    return {"itens": itens, "total": total}


@router.get("/ensaios", response_model=EnsaiosPagina, openapi_extra=PRIV_LER)
def ensaios_listar(limite: int = 50, deslocamento: int = 0,
                   auth: Auth = autenticado("org.configurar", escopo_token="admin:inquilino")):
    lim, des = _limite_deslocamento(limite, deslocamento)
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT count(*) AS n FROM plat.backup_drill")
        total = int(cur.fetchone()["n"])
        cur.execute(
            "SELECT id, backup_id, job_id, esquema, schema_ensaio, tabelas, linhas, objetos_conferidos, ok, "
            "mensagem, duracao_drill_s, origem, criado_em FROM plat.backup_drill "
            "ORDER BY criado_em DESC LIMIT %s OFFSET %s", (lim, des),
        )
        linhas = cur.fetchall()
    itens = [
        {"id": r["id"], "backup_id": r["backup_id"], "job_id": str(r["job_id"]) if r["job_id"] else None,
         "esquema": r["esquema"], "schema_ensaio": r["schema_ensaio"], "tabelas": r["tabelas"],
         "linhas": r["linhas"], "objetos_conferidos": r["objetos_conferidos"], "ok": r["ok"],
         "mensagem": r["mensagem"], "duracao_drill_s": float(r["duracao_drill_s"]), "origem": r["origem"],
         "criado_em": _quando(r["criado_em"])}
        for r in linhas
    ]
    return {"itens": itens, "total": total}
