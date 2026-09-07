"""Tipo de job `correio.enviar` (item L0-07-d-smtp-convites; ADR 0013), `somente_sistema=True`: só
`app/jobs/sistema.py::enfileirar` cria este job (convite, redefinição de senha, aviso de expiração) — nunca
`POST /api/jobs`, mesmo por um admin, porque os parâmetros aceitos (destinatário/assunto/texto livres)
usariam o SMTP do inquilino como canhão de e-mail arbitrário se qualquer chamador pudesse escolhê-los.
A configuração de SMTP é lida FRESCA do banco a cada tentativa (nunca guardada nos parâmetros do job): a
senha só existe em memória entre a leitura e o envio, e a mensagem de erro de `app.correio.cliente.ErroSMTP`
nunca a cita — é o que prova `tests/unit/test_correio_tarefas.py` (grep no log do worker)."""

from pydantic import BaseModel, Field

from app import limites
from app.correio import cliente
from app.correio.config import decifrar_senha, smtp_efetivo
from app.jobs.registro import FalhaDefinitiva, tarefa
from app.settings import settings


class CorreioEnviarParametros(BaseModel):
    destinatario: str = Field(max_length=320)
    assunto: str = Field(max_length=limites.SMTP_ASSUNTO_MAX)
    texto: str = Field(max_length=limites.SMTP_TEXTO_MAX)
    categoria: str = Field(
        max_length=40, description="convite | redefinicao_senha | aviso_expiracao (só rótulo de log/proveniência)"
    )


@tarefa(
    nome="correio.enviar",
    descricao="Envia um e-mail pelo SMTP efetivo do inquilino (ou o da instalação); nunca criável por POST /api/jobs",
    parametros=CorreioEnviarParametros,
    pesado=False,
    memoria_mb=512,  # 192 e 256 MB estouravam na prática (RLIMIT_DATA do filho, item L0-05-e): a cifra AES-GCM
                     # (app/correio/cifra.py) é o primeiro tipo de job a importar `cryptography` DEPOIS do fork
                     # (outros tipos ou já a tinham carregada por outro caminho, ou não a usam); medido com o
                     # worker real desta máquina, "memória excedida (limite 192 MB)" e depois "(limite 256 MB)"
    timeout_s=30,
    tentativas=3,
    perfil_minimo="admin",
    somente_sistema=True,
)
def correio_enviar(ctx, destinatario: str, assunto: str, texto: str, categoria: str = "") -> dict:
    with ctx.db() as cur:
        cur.execute("SELECT config FROM plat.tenant WHERE id = plat.tenant_atual()")
        r = cur.fetchone()
    if r is None:
        raise FalhaDefinitiva("inquilino inexistente")
    cfg = smtp_efetivo(r["config"], settings)
    if cfg is None:
        # SMTP removido/nunca configurado entre o pedido e a execução: não adianta repetir (ADR 0002 seção
        # 6.3 — o caminho manual já cobre quem não tem SMTP; o job só existe quando havia SMTP no pedido).
        raise FalhaDefinitiva("SMTP não configurado neste inquilino nem na instalação")
    senha = decifrar_senha(cfg, settings.PLAT_SECRET, settings.PLAT_SECRET_ANTERIOR)
    ctx.progresso(30, f"conectando a {cfg.host}:{cfg.porta}")
    try:
        cliente.enviar(cfg, senha, destinatario, assunto, texto)
    finally:
        senha = None  # noqa: F841 — solta a referência assim que possível (não fica pendurada no frame)
    ctx.progresso(100, "e-mail enviado")
    ctx.log("INFO", f"correio.enviar: {categoria or 'sem categoria'} para {destinatario} via {cfg.host}:{cfg.porta} "
                    f"({cfg.origem})")
    return {"destinatario": destinatario, "host": cfg.host, "porta": cfg.porta, "origem": cfg.origem}
