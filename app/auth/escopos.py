"""Escopos de token de serviço: vocabulário fechado validado por expressão regular (ADR 0002 seção 8.2).
`exigir_escopo(auth, base, uuid)` é o que as linhas futuras (L0-03, L2-04, L1-02, L0-05) chamam."""

import re

from app.erros import ErroAPI

UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
ESCOPO = re.compile(
    rf"^(catalogo:ler|camada:(ler|editar)(:{UUID})?|tiles:ler(:{UUID})?|jobs:executar|admin:inquilino)$"
)
ESCOPOS_SEM_UUID = ("catalogo:ler", "camada:ler", "camada:editar", "tiles:ler", "jobs:executar", "admin:inquilino")
DESCRICAO = {
    "catalogo:ler": "listar e ler metadado de itens que o dono pode ler",
    "camada:ler": "ler feições e atributos de camada legível pelo dono (opcional :<uuid> de uma camada)",
    "camada:editar": "editar feições (exige feicoes.editar no dono; opcional :<uuid>)",
    "tiles:ler": "tiles vetoriais e raster (opcional :<uuid>)",
    "jobs:executar": "criar e ler os próprios jobs (exige jobs.executar no dono)",
    "admin:inquilino": "tudo o que o dono pode fazer pela API, exceto gerir tokens, senha, 2FA e sessões",
}


def valido(escopo: str) -> bool:
    return isinstance(escopo, str) and bool(ESCOPO.match(escopo))


def invalidos(escopos: list) -> list:
    return [e for e in escopos if not valido(e)]


def cobre(escopos: list[str], base: str, uuid: str | None = None) -> bool:
    """`base` sem uuid cobre `base:<uuid>`; `admin:inquilino` cobre tudo."""
    if "admin:inquilino" in escopos:
        return True
    if base in escopos:
        return True
    return uuid is not None and f"{base}:{uuid}" in escopos


def exigir_escopo(auth, base: str, uuid: str | None = None) -> None:
    """Sob sessão não se aplica; sob token, escopo insuficiente = 403 com o exigido e o que o token tem."""
    if auth is None or auth.modo != "token":
        return
    if not cobre(auth.escopos, base, uuid):
        exigido = f"{base}:{uuid}" if uuid else base
        raise ErroAPI(
            403,
            "escopo_insuficiente",
            f"o token não tem o escopo {exigido}",
            {"exigido": exigido, "token_tem": list(auth.escopos)},
        )
