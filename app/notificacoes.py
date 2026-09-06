"""Notificações internas por usuário (item L0-03-k; achado G2-7 do adversário do grupo G2: a metade de
notificação do item não existia — nenhuma rota, tabela, migração ou linha de código).

Uma notificação é uma linha de `plat.notificacao` para UM usuário, com lida/não lida e uma `chave` de dedup
(a mesma chave para o mesmo usuário nunca vira duas linhas: índice único no banco). Quem escreve chama
`plat.notificar(...)`, função SECURITY DEFINER da migração 20260906T1607, porque o worker (role `plat_worker`,
sem privilégio de tabela) também notifica ao terminar um job. A função aplica o teto por minuto por usuário
(`limites.NOTIFICACOES_POR_MINUTO`): passando do teto ela devolve NULL e a notificação é DESCARTADA, nunca
enfileirada — é assim que 10 mil notificações em 1 minuto viram no máximo o teto.

Ler, marcar como lida e apagar são do próprio usuário: a segurança de linha da tabela usa `usuario_id =
plat.usuario_atual()`, então notificação de outro usuário não aparece na lista nem é alcançável por id (404).
"""

import logging

from app import limites

log = logging.getLogger("plat.notificacoes")

# tipos emitidos hoje; a tela traduz por chave de i18n `notificacao.tipo_<tipo com / trocado por _>`
TIPOS = (
    "grupos/convite",  # você foi convidado para um grupo
    "grupos/pedido",  # alguém pediu entrada no grupo que você gere
    "jobs/concluido",  # seu job terminou
    "jobs/falhou",  # seu job falhou
)


def notificar(
    cur,
    tenant_id: int,
    usuario_id: int,
    tipo: str,
    titulo: str,
    chave: str,
    corpo: str | None = None,
    url: str | None = None,
    alvo_tipo: str | None = None,
    alvo_id: str | None = None,
) -> str | None:
    """Cria a notificação e devolve o id, ou None quando a chave repete ou o teto por minuto foi atingido.

    Nunca levanta por causa de dedup nem de teto: notificar é efeito colateral de outra operação e não pode
    derrubar a transação de quem a originou. Só levanta se o usuário não for do inquilino (erro de programação).
    """
    cur.execute(
        "SELECT plat.notificar(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) AS id",
        (tenant_id, usuario_id, tipo, titulo, chave, corpo, url, alvo_tipo, alvo_id, limites.NOTIFICACOES_POR_MINUTO),
    )
    novo = cur.fetchone()["id"]
    if novo is None:
        log.info("notificação não criada (chave repetida ou teto por minuto): %s %s", tipo, chave)
    return str(novo) if novo else None


def nao_lidas(cur, usuario_id: int) -> int:
    """Contagem do sino. Índice parcial ix_notificacao_sino (usuario_id) WHERE lida_em IS NULL."""
    cur.execute(
        "SELECT count(*) AS n FROM plat.notificacao WHERE usuario_id = %s AND lida_em IS NULL", (usuario_id,)
    )
    return int(cur.fetchone()["n"])
