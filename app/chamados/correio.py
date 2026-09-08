"""E-mail de notificação de chamado (item L7-13-a-chamados), nos 3 idiomas de `plat.usuario.idioma_preferido`
(042_perfil_usuario.sql: pt-BR, en, es). O texto nasce AQUI (rótulo por evento + idioma do DESTINATÁRIO) e
viaja pelo job `correio.enviar` — `somente_sistema=True`, criado só por `app.jobs.sistema.enfileirar`, com o
SMTP lido fresco do banco na execução. O texto segue a regra de escrita de 03/09 (frase curta, sem exclamação,
sem travessão interno, sem a frase proibida "você recebe"); `tests/unit/test_chamados.py` reprova cada regra.

Sem e-mail no destinatário (coluna email é opcional na 002) ou sem SMTP configurado, o job não é enfileirado:
a notificação do cliente nunca vira falha da ação do operador — o banner dentro do produto cobre quem não tem
e-mail (o operador vê a fila no painel de todo jeito)."""

from app import limites
from app.jobs import sistema
from app.jobs.contexto import ErroServico
from app.settings import settings

# ---------------------------------------------------------------- textos por evento × idioma
# numero/titulo/url são interpolados com str.format; nenhuma entrada do usuário entra no assunto (só o numero).
TEXTOS: dict[str, dict[str, dict[str, str]]] = {
    "resposta": {
        "pt-BR": {
            "assunto": "plat: resposta no chamado {numero}",
            "texto": "O suporte respondeu ao chamado {numero} ({titulo}).\n"
                     "Abra a página de chamados para ler a resposta.\n{url}\n",
        },
        "en": {
            "assunto": "plat: reply on ticket {numero}",
            "texto": "Support replied to ticket {numero} ({titulo}).\n"
                     "Open the tickets page to read the reply.\n{url}\n",
        },
        "es": {
            "assunto": "plat: respuesta en el ticket {numero}",
            "texto": "El soporte respondió al ticket {numero} ({titulo}).\n"
                     "Abra la página de tickets para leer la respuesta.\n{url}\n",
        },
    },
    "resolvido": {
        "pt-BR": {
            "assunto": "plat: chamado {numero} resolvido",
            "texto": "O chamado {numero} ({titulo}) foi marcado como resolvido pelo suporte.\n"
                     "Abra a página de chamados e confirme. Se o problema voltar, comente no chamado.\n{url}\n",
        },
        "en": {
            "assunto": "plat: ticket {numero} resolved",
            "texto": "Ticket {numero} ({titulo}) was marked as resolved by support.\n"
                     "Open the tickets page and confirm. If the problem returns, comment on the ticket.\n{url}\n",
        },
        "es": {
            "assunto": "plat: ticket {numero} resuelto",
            "texto": "El ticket {numero} ({titulo}) fue marcado como resuelto por el soporte.\n"
                     "Abra la página de tickets y confirme. Si el problema vuelve, comente en el ticket.\n{url}\n",
        },
    },
}

ASSUNTO_MAX = limites.SMTP_ASSUNTO_MAX
TEXTO_MAX = limites.SMTP_TEXTO_MAX


def monta(evento: str, idioma: str, numero: int, titulo: str) -> tuple[str, str]:
    """(assunto, texto) do evento (`resposta` | `resolvido`) no idioma; idioma desconhecido cai em pt-BR
    (o padrão da coluna). O titulo entra só no corpo e já cortado — o assunto nunca leva texto do cliente."""
    t = TEXTOS[evento][idioma if idioma in TEXTOS[evento] else "pt-BR"]
    assunto = t["assunto"].format(numero=numero)[:ASSUNTO_MAX]
    texto = t["texto"].format(numero=numero, titulo=titulo[:80], url=_url())[:TEXTO_MAX]
    return assunto, texto


def _url() -> str:
    return f"{settings.PLAT_URL_PUBLICA}/chamados"


def notifica_cliente(tenant_id: int, evento: str, numero: int, titulo: str, email: str | None,
                     idioma: str | None) -> str | None:
    """Enfileira o e-mail ao cliente; devolve o id do job ou None (sem e-mail cadastrado). Falha de cota/fila
    do inquilino não derruba a ação do operador: vira ErroServico só quando o chamador decide propagar — aqui
    o banner do produto já avisou o cliente, então a falha de correio é logada pelo job e não repetida aqui."""
    if not email:
        return None
    assunto, texto = monta(evento, idioma or "pt-BR", numero, titulo)
    try:
        return sistema.enfileirar(
            tenant_id, "correio.enviar",
            {"destinatario": email, "assunto": assunto, "texto": texto, "categoria": "chamado_notificacao"},
        )
    except ErroServico:
        return None
