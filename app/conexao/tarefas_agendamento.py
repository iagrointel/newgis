"""Item L6-02-k-agendamento: atualização agendada de camadas copiadas (`plat.conexao.modo = 'copiada'`).

NÃO é outro relógio: `conexao.atualizar_copia` é só mais um tipo de job agendável pelo mecanismo já
construído no L0-05 (`plat.agenda`, `app/jobs/agenda.py::tick`, cron mínimo de 15 min, "5 falhas seguidas
pausam" já gravado em `plat.agenda_registrar_fim`). O usuário cria a agenda pela API/tela já existente
(`POST /api/agendas` com `tipo=conexao.atualizar_copia`, `parametros={"conexao_id": ...}`) — nada de rota
nova para "agendar uma camada"; é a mesma tela `web/tarefas.html` que já lista qualquer agenda.

Este arquivo entrega três coisas:
  1. o tipo de job em si (busca o conteúdo pelo `app.conexao.seguranca.buscar_seguro`, já defendido contra
     SSRF, com `guardar_corpo=True`; grava uma VERSÃO nova e faz a TROCA ATÔMICA por ponteiro — 004);
  2. o teto de tarefas ATIVAS por USUÁRIO (Esri publica 10/usuário e 50/organização; a organização já
     existe em `plat.cota_agendas` desde a 004 — aqui só falta o de usuário): `plat.cota_agendas_usuario`/
     `plat.agendas_ativas_usuario` (migração desta trilha) mais duas checagens em `agenda_criar`/
     `agenda_retomar` de `app/jobs/servico.py` — mudança mínima, mesmo padrão do teto de organização já ali;
  3. o periódico `agenda.avisos_enviar`, que consome `plat.agenda_aviso` (fila gravada por
     `plat.agenda_registrar_fim` quando uma agenda pausa por 5 falhas seguidas) e enfileira `correio.enviar`
     por `app.jobs.sistema.enfileirar` — o throttle de "no máximo 1 e-mail a cada 6h" já está na ENTRADA da
     fila (`plat.agenda_aviso_registrar`), então este job só drena o que existe, sem lógica de tempo própria.
"""

import psycopg2
from pydantic import BaseModel, Field

from app.conexao import credencial as credencial_mod
from app.conexao import seguranca
from app.jobs.registro import FalhaDefinitiva, tarefa
from app.limites import CONEXAO_CONECTAR_TIMEOUT_S, CONEXAO_COPIA_MAX_BYTES, CONEXAO_LER_TIMEOUT_S
from app.settings import settings

AGENDA_AVISOS_LIMITE_POR_EXECUCAO = 50


class AtualizarCopiaParametros(BaseModel):
    conexao_id: str = Field(min_length=1, max_length=64)


@tarefa(
    nome="conexao.atualizar_copia",
    descricao="Atualização agendada de uma camada copiada: busca o conteúdo do conector e troca a versão "
               "corrente de forma atômica (a antiga só sai quando a nova tiver entrado inteira)",
    parametros=AtualizarCopiaParametros, pesado=False, memoria_mb=256, timeout_s=300, tentativas=3,
    chave=lambda p: f"atualizar_copia:{p.get('conexao_id')}", perfil_minimo="editor",
)
def conexao_atualizar_copia(ctx, conexao_id: str) -> dict:
    with ctx.db() as cur:
        cur.execute(
            "SELECT tipo, modo, url, config, credencial_cifrada FROM plat.conexao WHERE id = %s::uuid",
            (conexao_id,),
        )
        c = cur.fetchone()
    if c is None:
        raise FalhaDefinitiva(f"conexão {conexao_id} inexistente (ou fora deste inquilino)")
    if c["modo"] != "copiada":
        raise FalhaDefinitiva(f"conexão {conexao_id} está em modo {c['modo']!r}; agendamento é só para 'copiada'")

    cabecalhos = None
    if c["credencial_cifrada"]:
        try:
            token = credencial_mod.decifrar(c["credencial_cifrada"], settings.PLAT_SECRET)
            cabecalhos = {"Authorization": f"Bearer {token}"}
        except ValueError:
            cabecalhos = None  # PLAT_SECRET trocado ou dado corrompido: tenta sem credencial, nunca quebra o job

    ctx.progresso(10, f"buscando {c['url']}")
    resultado = seguranca.buscar_seguro(
        c["url"], metodo="GET", timeout_conectar=CONEXAO_CONECTAR_TIMEOUT_S, timeout_ler=CONEXAO_LER_TIMEOUT_S,
        max_bytes=CONEXAO_COPIA_MAX_BYTES, cabecalhos=cabecalhos, guardar_corpo=True,
    )
    if not resultado.ok:
        # falha comum (rede, HTTP != 2xx/3xx, corpo grande demais): conta tentativa, repete, e só vira
        # "falhou" definitivo depois de esgotar `tentativas` — é aí que `plat.agenda_registrar_fim` soma 1
        # falha SEGUIDA da agenda (não desta tentativa isolada).
        raise RuntimeError(f"busca falhou: {resultado.mensagem} (status={resultado.status})")

    ctx.progresso(60, f"{len(resultado.corpo)} bytes recebidos; gravando versão nova")
    with ctx.db() as cur:
        cur.execute(
            "SELECT plat.camada_copia_versao_inserir(%s::uuid, %s, %s) AS id",
            (conexao_id, c["tipo"], psycopg2.Binary(resultado.corpo)),
        )
        versao_nova = cur.fetchone()["id"]

    ctx.progresso(85, "trocando a versão corrente (troca atômica)")
    with ctx.db() as cur:
        cur.execute("SELECT plat.camada_copia_trocar(%s::uuid, %s::uuid) AS anterior", (conexao_id, versao_nova))
        anterior = cur.fetchone()["anterior"]
        # poda best-effort: mantém só a versão corrente (D21, disco a 98%). Se falhar (ex.: outra troca
        # concorrente já mudou o ponteiro de novo), não derruba o job — a poda de novo no próximo ciclo pega.
        try:
            cur.execute("SELECT plat.camada_copia_podar(%s::uuid, %s::uuid) AS podadas", (conexao_id, versao_nova))
            podadas = cur.fetchone()["podadas"]
        except Exception:  # noqa: BLE001 — poda é limpeza, nunca motivo de falha do job
            podadas = None

    ctx.progresso(100, f"camada {conexao_id} atualizada: {len(resultado.corpo)} bytes, versão {versao_nova}")
    return {
        "conexao_id": conexao_id, "versao_id": str(versao_nova), "versao_anterior": str(anterior) if anterior else None,
        "tamanho_bytes": len(resultado.corpo), "latencia_ms": resultado.latencia_ms, "versoes_podadas": podadas,
    }


# ---------------------------------------------------------------- avisos por e-mail (agenda pausada por falha)
class AgendaAvisosEnviarParametros(BaseModel):
    limite: int = Field(AGENDA_AVISOS_LIMITE_POR_EXECUCAO, ge=1, le=500)


@tarefa(
    nome="agenda.avisos_enviar",
    descricao="Drena plat.agenda_aviso (agendas pausadas por 5 falhas seguidas) e envia 1 e-mail por aviso, "
               "todos os inquilinos; o teto de 1 a cada 6h por agenda já foi decidido na entrada da fila",
    parametros=AgendaAvisosEnviarParametros, pesado=False, memoria_mb=256, timeout_s=300, tentativas=1,
    chave=lambda p: "agenda_avisos_enviar", perfil_minimo="admin",
)
def agenda_avisos_enviar(ctx, limite: int = AGENDA_AVISOS_LIMITE_POR_EXECUCAO) -> dict:
    from app.jobs import sistema as jobs_sistema  # importação tardia: app.jobs.sistema -> servico -> tipos -> este
                                                   # módulo fecharia um ciclo se importado no topo do arquivo

    with ctx.db() as cur:
        cur.execute("SELECT * FROM plat.agenda_avisos_pendentes(%s)", (limite,))
        pendentes = cur.fetchall()
    enviados = sem_email = erro = 0
    for i, p in enumerate(pendentes):
        ctx.verificar()
        if not p["email"]:
            sem_email += 1  # agenda sem dono com e-mail (inquilino técnico, ou usuário apagado): não há a quem avisar
        else:
            assunto = f"tarefa agendada pausada: {p['nome']}"
            texto = (
                f"A tarefa agendada \"{p['nome']}\" foi pausada automaticamente após 5 execuções seguidas "
                f"com falha.\n\nMotivo da última: {p['motivo']}\n\n"
                "Reative a tarefa na tela Tarefas depois de corrigir a causa (ex.: URL ou credencial da "
                "conexão), ou apague-a se não for mais necessária."
            )
            parametros = {"destinatario": p["email"], "assunto": assunto, "texto": texto,
                          "categoria": "aviso_agenda_pausada"}
            try:
                jobs_sistema.enfileirar(p["tenant_id"], "correio.enviar", parametros, usuario_id=p["usuario_id"])
                enviados += 1
            except Exception as e:  # noqa: BLE001 — cota de e-mail do inquilino esgotada não pode travar os demais avisos
                erro += 1
                ctx.log("AVISO", f"aviso {p['id']} (agenda {p['agenda_id']}) não enfileirado: {e}")
                continue
        with ctx.db() as cur:
            cur.execute("SELECT plat.agenda_aviso_marcar_enviado(%s)", (p["id"],))
        ctx.progresso(int((i + 1) / max(len(pendentes), 1) * 100), f"{i + 1}/{len(pendentes)} avisos processados")
    ctx.progresso(100, f"{len(pendentes)} avisos: {enviados} enviados, {sem_email} sem e-mail, {erro} com erro")
    return {"pendentes": len(pendentes), "enviados": enviados, "sem_email": sem_email, "erro": erro}


from app.conexao import periodicos  # noqa: E402,F401 — importar registra os periódicos desta lista no worker
