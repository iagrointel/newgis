"""Periódico da exportação (item L0-04-h-exportar): `exportacao.expirar` apaga o OBJETO e o ITEM de arquivo de
toda exportação cuja validade venceu (7 dias, `limites.EXPORTACAO_VALIDADE_DIAS`) e marca a linha como
`expirada` — o histórico de quem exportou o quê fica; o arquivo não.

Cruza inquilinos pelo mesmo mecanismo do `uploads.expirar` (item L0-04-a): a função
`plat.exportacoes_expirar_candidatos()` é SECURITY DEFINER (roda como `postgres`, fora da RLS) e só LÊ; o
apagamento em si reabre conexão NO CONTEXTO do inquilino de cada linha, porque `objetos.apagar` precisa
resolver o bucket certo e a RLS de `plat.item` exige o inquilino certo.
"""

from __future__ import annotations

from pydantic import BaseModel

from app import db as banco
from app import limites, objetos
from app.jobs import periodicos as base
from app.jobs.registro import tarefa


class ExpirarParametros(BaseModel):
    """Sem parâmetro: a validade está gravada em cada linha (`expira_em`), não é opção do chamador."""


@tarefa(
    nome="exportacao.expirar",
    descricao="Expurgo: arquivos de exportação com validade vencida (apaga o objeto e o item, mantém o registro)",
    parametros=ExpirarParametros,
    pesado=False,
    memoria_mb=256,
    timeout_s=900,
    tentativas=1,
    chave=lambda p: "exportacao_expirar",
    perfil_minimo="admin",
)
def exportacao_expirar(ctx) -> dict:
    with ctx.db() as cur:
        cur.execute("SELECT * FROM plat.exportacoes_expirar_candidatos()")
        candidatos = cur.fetchall()
    apagadas = erros = 0
    for c in candidatos:
        contexto = banco.Contexto(int(c["tenant_id"]), int(c["usuario_id"]), "worker")
        try:
            if c["chave"]:
                objetos.apagar(c["chave"])
            with banco.db(contexto) as cur2:
                if c["arquivo_item_id"]:
                    cur2.execute("SELECT plat.item_lixeira(%s::uuid, true)", (str(c["arquivo_item_id"]),))
                    cur2.execute("SELECT plat.item_expurgar(%s::uuid)", (str(c["arquivo_item_id"]),))
                cur2.execute(
                    "UPDATE plat.exportacao SET estado = 'expirada', chave = NULL, arquivo_item_id = NULL "
                    "WHERE id = %s::uuid AND estado = 'pronta'",
                    (str(c["id"]),),
                )
        except Exception as e:  # noqa: BLE001 — uma exportação com problema não trava as outras
            erros += 1
            ctx.log("AVISO", f"exportação {c['id']} não expirou: {e}")
            continue
        apagadas += 1
    ctx.progresso(100, f"{apagadas} exportações expiradas de {len(candidatos)} candidatas, {erros} com erro")
    return {"candidatas": len(candidatos), "expiradas": apagadas, "erros": erros,
            "validade_dias": limites.EXPORTACAO_VALIDADE_DIAS}


PERIODICOS: list[tuple[str, str, str, dict]] = [
    ("exportações vencidas (de hora em hora)", "17 * * * *", "exportacao.expirar", {}),
]

for _p in PERIODICOS:
    if _p not in base.PERIODICOS:
        base.PERIODICOS.append(_p)
