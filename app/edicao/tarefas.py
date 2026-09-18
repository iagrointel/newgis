"""Job `camadas.lote` (item L2-03-f): a edição em lote acima de LOTE_SINCRONO_MAX feições roda no worker (L0-05)
com progresso por sub-lote e cancelamento cooperativo. O corpo é o MESMO `LoteEntrada` da rota síncrona e a
execução é a mesma função (`app.edicao.lote.executar`), numa transação só: cancelar ou falhar no meio desfaz tudo
e a camada volta ao estado anterior (portão do item). `editar_total` vem da rota que criou o job (o privilégio foi
checado lá, na sessão de quem pediu); o inquilino é o do próprio job (RLS pelo contexto do worker)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app import limites
from app.edicao import lote
from app.edicao.modelos import LoteEntrada
from app.erros import ErroAPI
from app.jobs.registro import FalhaDefinitiva, tarefa


class LoteParametros(BaseModel):
    camada_id: str = Field(min_length=36, max_length=36)
    corpo: dict
    editar_total: bool = False


@tarefa(
    nome="camadas.lote",
    descricao="Edição em lote de feições (calcular campo, atribuir, apagar, corrigir geometria, copiar/mover)",
    parametros=LoteParametros, pesado=False, memoria_mb=512, timeout_s=limites.LOTE_JOB_TIMEOUT_S, tentativas=1,
    perfil_minimo="editor",
)
def camadas_lote(ctx, camada_id: str, corpo: dict, editar_total: bool = False) -> dict:
    entrada = LoteEntrada.model_validate(corpo)
    ator = lote.Ator(usuario_id=int(ctx.usuario_id or 0), editar_total=bool(editar_total))
    try:
        with ctx.db() as cur:  # UMA transação: progresso/cancelamento usam outra conexão (ctx.progresso)
            plano = lote.planejar(cur, camada_id, entrada, ator)
            ctx.log("INFO", f"{entrada.operacao}: {len(plano.fids)} feições; tradução={plano.traducao or '-'}")

            def progresso(feitas: int, total: int) -> None:
                ctx.verificar()
                ctx.progresso(int(feitas * 100 / max(total, 1)), f"{feitas}/{total} feições")

            saida = lote.executar(cur, plano, entrada, ator, progresso=progresso)
            saida.execucao = "job"

            def evento(tipo: str, props: dict) -> None:
                import json

                cur.execute("SELECT plat.evento_registrar(%s, %s, %s, %s::jsonb, NULL, NULL)",
                            (tipo, "item", camada_id, json.dumps({**props, "job_id": str(ctx.job_id)}, default=str)))

            lote.registrar_efeitos(cur, plano, saida, camada_id, evento)
    except ErroAPI as e:
        # erro nomeado do lote (domínio, expressão, tipo): definitivo, sem retentativa; a transação já foi desfeita
        raise FalhaDefinitiva(f"{e.erro}: {e.detail}") from e
    ctx.progresso(100, f"{saida.alteradas + saida.apagadas + saida.criadas + saida.corrigidas} feições tocadas")
    return saida.model_dump()


# ---------------------------------------------------------------- edicao.anexos_ceifar (L2-03-e)
class CeifarParametros(BaseModel):
    limite: int = Field(1000, ge=1, le=100000)


@tarefa(
    nome="edicao.anexos_ceifar",
    descricao="Ceife de objetos órfãos de anexo: remove do Garage o objeto de anexo com apagado_em marcado "
              "(por DELETE de anexo ou pela cascata do apagar da feição) e sem linha viva na mesma chave",
    parametros=CeifarParametros, pesado=False, memoria_mb=256, timeout_s=1800, tentativas=1,
    chave=lambda p: "anexos_ceifar",
    perfil_minimo="admin",
)
def edicao_anexos_ceifar(ctx, limite: int = 1000) -> dict:
    """Periódico diário (app/jobs/periodicos.py). Roda sem contexto de inquilino: a seleção é a função
    SECURITY DEFINER `plat.feicao_anexo_orfaos` (cross-inquilino por construção — um ceife por inquilino
    deixaria órfão em todo inquilino cujo job não rodou)."""
    from app.edicao import anexos

    with ctx.db() as cur:
        saida = anexos.ceifar_orfaos(cur, limite=limite)
    ctx.log("INFO", f"ceife de anexos: {saida['objetos_removidos']} removidos, "
                    f"{saida['falhas']} falhas, {saida['candidatos']} candidatos")
    return saida
