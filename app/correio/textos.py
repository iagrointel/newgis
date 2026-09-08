"""Modelos de e-mail em português (item L0-07-d-smtp-convites), com o nome do inquilino. Texto simples (sem
HTML) de propósito: menos superfície de ataque (sem link disfarçado, sem tracking) e sem exigir um segundo
formato para manter sincronizado. Sem emoji, sem exclamação (regra da casa)."""

from app import limites


def convite_assunto(tenant_nome: str) -> str:
    return f"Convite para {tenant_nome}"[: limites.SMTP_ASSUNTO_MAX]


def convite_texto(tenant_nome: str, link: str, dias_validade: int) -> str:
    return (
        f"Você foi convidado para o inquilino {tenant_nome} na plataforma.\n\n"
        f"Para criar sua conta, abra o link abaixo:\n{link}\n\n"
        f"O link vale por {dias_validade} dias e só pode ser usado uma vez.\n"
        f"Se você não esperava este convite, ignore esta mensagem."
    )


def redefinicao_assunto(tenant_nome: str) -> str:
    return f"Redefinição de senha em {tenant_nome}"[: limites.SMTP_ASSUNTO_MAX]


def redefinicao_texto(tenant_nome: str, login: str, link: str, horas_validade: int) -> str:
    return (
        f"Foi solicitada a redefinição da senha do usuário {login} no inquilino {tenant_nome}.\n\n"
        f"Para escolher uma senha nova, abra o link abaixo:\n{link}\n\n"
        f"O link vale por {horas_validade} hora(s) e só pode ser usado uma vez.\n"
        f"Se você não pediu essa redefinição, ignore esta mensagem; sua senha continua a mesma."
    )


def aviso_expiracao_assunto(tenant_nome: str, tipo: str) -> str:
    alvo = "token de serviço" if tipo == "token" else "recurso"
    return f"Aviso de expiração de {alvo} em {tenant_nome}"[: limites.SMTP_ASSUNTO_MAX]


def aviso_expiracao_texto(tenant_nome: str, descricao: str, dias_restantes: int) -> str:
    plural = "dia" if dias_restantes == 1 else "dias"
    return (
        f"No inquilino {tenant_nome}, {descricao} expira em {dias_restantes} {plural}.\n\n"
        f"Renove ou substitua antes do vencimento para não interromper o que depende dele."
    )
