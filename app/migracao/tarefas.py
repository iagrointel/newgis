"""Tipo de job `migracao.inventariar` (item L2-08-a-leitor-portal-inventario).

O corpo é fino de propósito: abre a conexão registrada (`plat.conexao`), decifra o token em memória, e entrega
tudo a `app/migracao/inventario.py`. Duas decisões que o portão exige e que ficam visíveis aqui:

1. **Tentativas = 3.** Um corte de rede no meio do inventário sobe como `ErroRede`, o job vai para nova
   tentativa e o motor CONTINUA do ponto gravado em `retomada` — não recomeça. Erro que não é de rede
   (`nao_e_portal`, `credencial_recusada`) sobe como `FalhaDefinitiva`: repetir não conserta.

2. **O token nunca entra em log.** Nem no log do job, nem na mensagem gravada em
   `plat.migracao_inventario.mensagem` (que passa por `inventario.mensagem_de_erro`, com redação), nem na
   URL (o token viaja em cabeçalho — ver o cabeçalho de app/migracao/portal.py)."""

from pydantic import BaseModel, Field

from app.conexao import credencial as credencial_mod
from app.jobs.registro import FalhaDefinitiva, tarefa
from app.migracao import inventario as motor
from app.migracao.portal import ClientePortal, ErroPortal, ErroRede
from app.settings import settings

MOTIVOS_DEFINITIVOS = ("nao_e_portal", "credencial_recusada", "url_insegura", "inventario_inexistente",
                       "token_nao_emitido")


class InventariarParametros(BaseModel):
    inventario_id: str = Field(min_length=36, max_length=36)


@tarefa(
    nome="migracao.inventariar",
    descricao="Inventário só-leitura de um Portal/AGOL registrado como conexão (itens, grupos, usuários)",
    parametros=InventariarParametros, pesado=False, memoria_mb=512, timeout_s=3600, tentativas=3,
    chave=lambda p: f"inventariar:{p['inventario_id']}", perfil_minimo="admin",
)
def migracao_inventariar(ctx, inventario_id: str) -> dict:
    with ctx.db() as cur:
        cur.execute(
            "SELECT i.id, i.tenant_id, i.portal_url, c.credencial_cifrada "
            "FROM plat.migracao_inventario i JOIN plat.conexao c ON c.id = i.conexao_id "
            "WHERE i.id = %s::uuid", (inventario_id,),
        )
        linha = cur.fetchone()
    if linha is None:
        raise FalhaDefinitiva(f"inventário {inventario_id} inexistente neste inquilino")

    token = None
    if linha["credencial_cifrada"]:
        try:
            token = credencial_mod.decifrar(linha["credencial_cifrada"], settings.PLAT_SECRET)
        except ValueError as e:
            raise FalhaDefinitiva("credencial da conexão não pôde ser decifrada (PLAT_SECRET trocado?)") from e

    with ctx.db() as cur:
        cur.execute("UPDATE plat.migracao_inventario SET estado = 'rodando', job_id = %s::uuid, "
                    "iniciado_em = coalesce(iniciado_em, now()), mensagem = NULL WHERE id = %s::uuid",
                    (str(ctx.job_id), inventario_id))

    cliente = ClientePortal(base=linha["portal_url"], token=token)
    execucao = motor.Inventario(
        cliente, ctx.db, inventario_id, int(linha["tenant_id"]),
        registrar=ctx.log, verificar=ctx.verificar, progresso=ctx.progresso,
    )
    try:
        totais = execucao.executar()
    except ErroPortal as e:
        mensagem = motor.mensagem_de_erro(e, token)
        definitivo = (not isinstance(e, ErroRede)) and e.motivo in MOTIVOS_DEFINITIVOS
        with ctx.db() as cur:
            cur.execute("UPDATE plat.migracao_inventario SET estado = %s, mensagem = %s, "
                        "terminado_em = CASE WHEN %s THEN now() ELSE terminado_em END WHERE id = %s::uuid",
                        ("falhou" if definitivo else "rodando", mensagem, definitivo, inventario_id))
        if definitivo:
            raise FalhaDefinitiva(mensagem) from e
        raise

    with ctx.db() as cur:
        cur.execute("UPDATE plat.migracao_inventario SET estado = 'concluido', terminado_em = now(), "
                    "mensagem = NULL WHERE id = %s::uuid", (inventario_id,))
    return totais
