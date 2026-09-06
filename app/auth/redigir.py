"""Redação de segredos antes de qualquer linha de log ou de `log_acesso.rota` (ADR 0002 seções 5.2 e 9.1):
parâmetros `token`, `senha`, `codigo`, `desafio` da query string, os cabeçalhos Cookie/Authorization e o token de
link compartilhado, que viaja no CAMINHO (`/api/compartilhado/<token>...` e a página `/c/<token>`, ADR 0004 seção 6):
o segredo do link nunca fica em `log_acesso.rota` (que o admin do inquilino lê em /admin/log) nem no journal."""

import re
from urllib.parse import parse_qsl, urlencode

PARAMETROS_SECRETOS = frozenset({"token", "senha", "codigo", "desafio", "codigo_recuperacao", "atual", "nova"})
REDIGIDO = "<redigido>"
_CABECALHO = re.compile(r"(?i)\b(cookie|authorization|set-cookie)\s*[:=]\s*([^\r\n;]+)")
_VALOR_PLAT = re.compile(r"\bplat_[A-Za-z0-9_-]{20,}")
_SESSAO = re.compile(r"\bplat_sessao=[0-9a-f]{64}")
# segmento do caminho logo depois de /api/compartilhado/ ou de /c/ — o token do link (64 hex) ou qualquer tentativa
_LINK_NO_CAMINHO = re.compile(r"(?:(?<=/api/compartilhado/)|(?<=/c/))[^/?#\s]+")


def caminho_redigido(caminho: str) -> str:
    """`/api/compartilhado/<token>/itens/<id>` → `/api/compartilhado/<redigido>/itens/<id>`; `/c/<token>` idem."""
    return _LINK_NO_CAMINHO.sub(REDIGIDO, caminho or "")


def query_redigida(query: str) -> str:
    if not query:
        return ""
    pares = [
        (k, REDIGIDO if k.lower() in PARAMETROS_SECRETOS else v) for k, v in parse_qsl(query, keep_blank_values=True)
    ]
    return urlencode(pares)


def rota_redigida(caminho: str, query: str, maximo: int = 500) -> str:
    q = query_redigida(query)
    return (caminho_redigido(caminho) + (f"?{q}" if q else ""))[:maximo]


def linha_redigida(texto: str) -> str:
    """Qualquer linha de log: cabeçalhos sensíveis, cookie de sessão e token de serviço viram <redigido>."""
    texto = _CABECALHO.sub(lambda m: f"{m.group(1)}: {REDIGIDO}", texto)
    texto = _SESSAO.sub(f"plat_sessao={REDIGIDO}", texto)
    texto = caminho_redigido(texto)
    return _VALOR_PLAT.sub(REDIGIDO, texto)
