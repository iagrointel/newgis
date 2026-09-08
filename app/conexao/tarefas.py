"""Periódico de saúde de `plat.conexao` (item L6-02-l-saude): reaproveita o relógio do L0-05 (mesmo padrão de
`app/jobs/periodicos.py`/`app/catalogo/periodicos.py` — um tipo de job registrado por `@tarefa`, agendado no
inquilino técnico `plataforma`, cujo corpo cruza qualquer inquilino através das funções SECURITY DEFINER de
`db/migracoes/036_conexao_saude_e_camada.sql`, nunca por SQL direto em `plat.conexao`). Roda a cada 15 min
(o mínimo do agendador, `app/jobs/agenda.py` `INTERVALO_MINIMO_S`); dentro de cada execução só testa conexões
cuja última verificação passou de `INTERVALO_RETESTE` (30 min) ou nunca foi testada, até `LIMITE_POR_EXECUCAO`
por vez — o portão do item ("URL inválida fica vermelha em ≤ 1 ciclo") vale para uma conexão RECÉM-CRIADA
(nunca testada: sempre candidata) e para qualquer uma cujo teste anterior já venceu."""

import datetime

from pydantic import BaseModel, Field

from app.conexao import credencial as credencial_mod
from app.conexao import seguranca
from app.jobs.registro import tarefa
from app.limites import CONEXAO_CONECTAR_TIMEOUT_S, CONEXAO_LER_TIMEOUT_S
from app.seguranca_rotacao import decifrar_com_rotacao
from app.settings import settings

INTERVALO_RETESTE = datetime.timedelta(minutes=30)
LIMITE_POR_EXECUCAO = 100


class SaudeVerificarParametros(BaseModel):
    limite: int = Field(LIMITE_POR_EXECUCAO, ge=1, le=1000)


@tarefa(
    nome="conexoes.saude_verificar",
    descricao="Verificação periódica de saúde das conexões externas (todos os inquilinos) vencidas há mais de 30 min",
    parametros=SaudeVerificarParametros, pesado=False, memoria_mb=256, timeout_s=900, tentativas=1,
    chave=lambda p: "saude_verificar", perfil_minimo="admin",
)
def conexoes_saude_verificar(ctx, limite: int = LIMITE_POR_EXECUCAO) -> dict:
    with ctx.db() as cur:
        cur.execute("SELECT * FROM plat.conexao_saude_candidatas(%s, %s)", (INTERVALO_RETESTE, limite))
        candidatas = cur.fetchall()
    ok = erro = 0
    for i, c in enumerate(candidatas):
        ctx.verificar()  # cancelamento cooperativo entre uma conexão e outra (o job pode ser longo)
        cabecalhos = None
        if c["credencial_cifrada"]:
            try:
                token = decifrar_com_rotacao(
                    credencial_mod.decifrar,
                    c["credencial_cifrada"],
                    settings.PLAT_SECRET,
                    settings.PLAT_SECRET_ANTERIOR,
                )
                cabecalhos = {"Authorization": f"Bearer {token}"}
            except Exception:  # noqa: BLE001 — PLAT_SECRET (e ANTERIOR) trocados ou dado corrompido: testa sem
                # credencial, nunca quebra o job (a exceção real do AEAD é InvalidTag, não ValueError — abrangida
                # de propósito, achado deste item: o except antigo só pegava ValueError e deixava InvalidTag subir)
                cabecalhos = None
        resultado = seguranca.buscar_seguro(
            c["url"], metodo="GET", timeout_conectar=CONEXAO_CONECTAR_TIMEOUT_S, timeout_ler=CONEXAO_LER_TIMEOUT_S,
            cabecalhos=cabecalhos,
        )
        if resultado.ok:
            ok += 1
        else:
            erro += 1
        with ctx.db() as cur:
            cur.execute(
                "SELECT plat.conexao_saude_registrar(%s::uuid, %s, %s, %s, %s)",
                (c["id"], resultado.ok, resultado.status, resultado.mensagem, resultado.latencia_ms),
            )
        ctx.progresso(int((i + 1) / max(len(candidatas), 1) * 100), f"{i + 1}/{len(candidatas)} conexões verificadas")
    ctx.progresso(100, f"{len(candidatas)} verificadas: {ok} ok, {erro} com erro")
    return {"candidatas": len(candidatas), "ok": ok, "erro": erro}


from app.conexao import periodicos  # noqa: E402,F401 — importar registra o periódico da saúde na lista do worker
