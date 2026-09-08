"""Periódico do upload retomável (item L0-04-a; ADR 0005 seção 3.1: "DELETE ... aborta ... Periódico
`ingestao.uploads_expirar` (*/30 * * * *): uploads sem parte há 24 h → aborta e libera reserva"). Mesmo padrão
de `app.jobs.periodicos`/`app.catalogo.periodicos`: acrescenta a lista `PERIODICOS` do worker na importação
(`app.uploads.tarefas`, somada em `app/jobs/tipos.py`).

Cruza tenants (um único upload esquecido pode ser de qualquer inquilino): `plat.uploads_expirar_candidatos` é
SECURITY DEFINER e roda como o dono da função (postgres), que não sofre a política de RLS de `plat.upload`
(mesmo mecanismo de `plat.sessoes_expurgar`, ADR 0001 seção 3.3) — só assim o job da fila, que roda sob o
inquilino técnico `plataforma`, enxerga uploads esquecidos de QUALQUER inquilino. O abortamento em si
(`objetos.parte_abortar` + `UPDATE plat.upload`) reabre uma conexão NO CONTEXTO daquele inquilino
(`banco.db(banco.Contexto(...))`), porque `objetos.parte_abortar` precisa resolver o bucket do inquilino certo
e a RLS de `plat.arquivo_upload`/`plat.upload` exige isso — como `ctx.db()` do job está fixo no inquilino técnico,
a troca é feita à mão aqui, um upload por vez."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app import db as banco
from app import limites, objetos
from app.jobs import periodicos as base
from app.jobs.registro import tarefa


class ExpirarParametros(BaseModel):
    horas: int = Field(limites.UPLOAD_EXPIRA_HORAS, ge=1, le=720)


@tarefa(
    nome="uploads.expirar",
    descricao="Expurgo: uploads retomáveis sem atividade há 24 h (aborta o multipart e libera a reserva de cota)",
    parametros=ExpirarParametros,
    pesado=False,
    memoria_mb=256,
    timeout_s=600,
    tentativas=1,
    chave=lambda p: "uploads_expirar",
    perfil_minimo="admin",
)
def uploads_expirar(ctx, horas: int = limites.UPLOAD_EXPIRA_HORAS) -> dict:
    with ctx.db() as cur:
        cur.execute("SELECT * FROM plat.uploads_expirar_candidatos(%s)", (horas,))
        candidatos = cur.fetchall()
    abortados = 0
    erros = 0
    for c in candidatos:
        contexto = banco.Contexto(int(c["tenant_id"]), int(c["usuario_id"]), "worker")
        try:
            with banco.db(contexto) as cur2:
                try:
                    objetos.parte_abortar(cur2, c["upload_s3_id"])
                except objetos.UploadInexistente:
                    pass  # já não existia no Garage (abortado por fora, ou nunca chegou a existir de fato)
                cur2.execute(
                    "UPDATE plat.upload SET estado = 'expirado', atualizado_em = now() "
                    "WHERE id = %s::uuid AND estado = 'iniciado'",
                    (str(c["id"]),),
                )
        except Exception as e:  # noqa: BLE001 — um upload com problema não pode travar os outros candidatos
            erros += 1
            ctx.log("AVISO", f"upload {c['id']} não expirou: {e}")
            continue
        abortados += 1
    ctx.progresso(100, f"{abortados} uploads expirados de {len(candidatos)} candidatos, {erros} com erro")
    return {"candidatos": len(candidatos), "abortados": abortados, "erros": erros}


PERIODICOS: list[tuple[str, str, str, dict]] = [
    ("uploads incompletos (30 min)", "*/30 * * * *", "uploads.expirar", {}),
]

for _p in PERIODICOS:
    if _p not in base.PERIODICOS:
        base.PERIODICOS.append(_p)
