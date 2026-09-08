"""Token interno de curta duração (item L2-12-a-motor-render-servidor, cláusula "token interno expira em
≤ 60 s e não serve fora do host"): HMAC-SHA256 sobre `PLAT_SECRET` (o mesmo segredo da instalação — nenhum
segredo novo para guardar), payload compacto `<exp_unix>.<nonce>.<assinatura>`. Não é uma sessão (não abre
`plat.sessao`, não tem cookie, não sobrevive a um restart de processo em memória) — serve só para a página
headless do motor de render chamar uma rota interna no MESMO host durante a janela curtíssima do render.

O host-lock é reforçado por FORA deste módulo, em app.render.rotas: a rota que aceita o token também confere
`request.client.host` contra `HOSTS_INTERNOS` (127.0.0.1/::1) antes de validar a assinatura — os dois juntos
são a defesa (`refutacao` do item pede tratar o dois: token vazado sozinho não abre nada de fora do host).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from app.settings import settings

HOSTS_INTERNOS = frozenset({"127.0.0.1", "::1", "localhost"})


def _assinatura(exp: int, nonce: str) -> str:
    msg = f"{exp}.{nonce}".encode()
    return hmac.new(settings.PLAT_SECRET.encode(), msg, hashlib.sha256).hexdigest()


def gerar(prazo_s: int | None = None) -> str:
    """Token válido por `prazo_s` segundos (padrão `PLAT_RENDER_TOKEN_TTL_S`, ele mesmo cortado a 60 s —
    a cláusula do portão é um TETO, nunca uma configuração que alguém possa alargar por engano)."""
    prazo = min(prazo_s or settings.PLAT_RENDER_TOKEN_TTL_S, 60)
    exp = int(time.time()) + max(prazo, 1)
    nonce = secrets.token_hex(8)
    return f"{exp}.{nonce}.{_assinatura(exp, nonce)}"


def validar(token: str) -> bool:
    """Assinatura íntegra E ainda dentro da validade. Qualquer forma inesperada é inválida, nunca uma
    exceção — quem chama só precisa de um booleano."""
    if not token or token.count(".") != 2:
        return False
    exp_s, nonce, assinatura = token.split(".")
    try:
        exp = int(exp_s)
    except ValueError:
        return False
    esperada = _assinatura(exp, nonce)
    if not hmac.compare_digest(assinatura, esperada):
        return False
    return time.time() <= exp


def host_e_interno(host: str | None) -> bool:
    return host in HOSTS_INTERNOS
