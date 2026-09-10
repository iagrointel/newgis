"""Escopos de token de serviço: vocabulário fechado validado por expressão regular (ADR 0002 seção 8.2).
`exigir_escopo(auth, base, uuid)` é o que as linhas futuras (L0-03, L2-04, L1-02, L0-05) chamam."""

import re

from app.erros import ErroAPI

UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
ESCOPO = re.compile(
    rf"^(catalogo:ler|camada:(ler|editar)(:{UUID})?|tiles:ler(:{UUID})?|jobs:executar|rota:usar|"
    rf"geocodificar:usar|imagens:(ler|escrever)|multiescala:usar|admin:inquilino)$"
    rf"geocodificar:usar|multiescala:usar|admin:inquilino)$"
)
ESCOPOS_SEM_UUID = (
    "catalogo:ler", "camada:ler", "camada:editar", "tiles:ler", "jobs:executar", "rota:usar",
    "geocodificar:usar", "multiescala:usar", "admin:inquilino",
    rf"geocodificar:usar|amc:usar|admin:inquilino)$"
    rf"geocodificar:usar|campo:usar|admin:inquilino)$"
    rf"geocodificar:usar|imagens:(ler|escrever)|admin:inquilino)$"
)
ESCOPOS_SEM_UUID = (
    "catalogo:ler", "camada:ler", "camada:editar", "tiles:ler", "jobs:executar", "rota:usar",
    "geocodificar:usar", "imagens:ler", "imagens:escrever", "admin:inquilino",
)
ESCOPOS_SEM_UUID = (
    "catalogo:ler", "camada:ler", "camada:editar", "tiles:ler", "jobs:executar", "rota:usar",
    "geocodificar:usar", "campo:usar", "admin:inquilino",
)
ESCOPOS_SEM_UUID = (
    "catalogo:ler", "camada:ler", "camada:editar", "tiles:ler", "jobs:executar", "rota:usar",
    "geocodificar:usar", "amc:usar", "admin:inquilino",
    "geocodificar:usar", "imagens:ler", "imagens:escrever", "multiescala:usar", "admin:inquilino",
    rf"geocodificar:usar|multiescala:usar|amc:usar|admin:inquilino)$"
)
ESCOPOS_SEM_UUID = (
    "catalogo:ler", "camada:ler", "camada:editar", "tiles:ler", "jobs:executar", "rota:usar",
    "geocodificar:usar", "multiescala:usar", "amc:usar", "admin:inquilino",
    rf"geocodificar:usar|multiescala:usar|imagens:(ler|escrever)|admin:inquilino)$"
)
ESCOPOS_SEM_UUID = (
    "catalogo:ler", "camada:ler", "camada:editar", "tiles:ler", "jobs:executar", "rota:usar",
    "geocodificar:usar", "multiescala:usar", "imagens:ler", "imagens:escrever", "admin:inquilino",
    rf"geocodificar:usar|multiescala:usar|analise3d:usar|admin:inquilino)$"
)
ESCOPOS_SEM_UUID = (
    "catalogo:ler", "camada:ler", "camada:editar", "tiles:ler", "jobs:executar", "rota:usar",
    "geocodificar:usar", "multiescala:usar", "analise3d:usar", "admin:inquilino",
    rf"geocodificar:usar|multiescala:usar|imagens:(ler|escrever)|admin:inquilino)$"
)
ESCOPOS_SEM_UUID = (
    "catalogo:ler", "camada:ler", "camada:editar", "tiles:ler", "jobs:executar", "rota:usar",
    "geocodificar:usar", "multiescala:usar", "imagens:ler", "imagens:escrever", "admin:inquilino",
    rf"geocodificar:usar|imagens:(ler|escrever)|admin:inquilino)$"
)
ESCOPOS_SEM_UUID = (
    "catalogo:ler", "camada:ler", "camada:editar", "tiles:ler", "jobs:executar", "rota:usar",
    "geocodificar:usar", "imagens:ler", "imagens:escrever", "admin:inquilino",
    rf"geocodificar:usar|amc:usar|multiescala:usar|admin:inquilino)$"
)
ESCOPOS_SEM_UUID = (
    "catalogo:ler", "camada:ler", "camada:editar", "tiles:ler", "jobs:executar", "rota:usar",
    "geocodificar:usar", "amc:usar", "multiescala:usar", "admin:inquilino",
    rf"geocodificar:usar|crs:usar|admin:inquilino)$"
)
ESCOPOS_SEM_UUID = (
    "catalogo:ler", "camada:ler", "camada:editar", "tiles:ler", "jobs:executar", "rota:usar",
    "geocodificar:usar", "crs:usar", "admin:inquilino",
    rf"geocodificar:usar|conteudo:criar|admin:inquilino)$"
)
ESCOPOS_SEM_UUID = (
    "catalogo:ler", "camada:ler", "camada:editar", "tiles:ler", "jobs:executar", "rota:usar",
    "geocodificar:usar", "conteudo:criar", "admin:inquilino",
)
# achado do adversário T3 (L0-04-a/L0-11): escopo cujo teto NÃO é "admin" (perfil), mas sim um privilégio —
# quem já tem o privilégio no perfil pode se emitir um token com este escopo. `rotas_tokens.criar` consulta.
ESCOPO_EXIGE_PRIVILEGIO = {"conteudo:criar": "conteudo.criar"}
DESCRICAO = {
    "catalogo:ler": "listar e ler metadado de itens que o dono pode ler",
    "camada:ler": "ler feições e atributos de camada legível pelo dono (opcional :<uuid> de uma camada)",
    "camada:editar": "editar feições (exige feicoes.editar no dono; opcional :<uuid>)",
    "tiles:ler": "tiles vetoriais e raster (opcional :<uuid>)",
    "jobs:executar": "criar e ler os próprios jobs (exige jobs.executar no dono)",
    "rota:usar": "calcular rota, matriz origem-destino e isócrona (L2-11-c; dado de teste, sem PII)",
    "geocodificar:usar": "geocodificar, geocodificar reverso e sugerir endereço (L2-11-b; dado aberto CNEFE, "
    "sem PII); mesmo escopo cobre o GeocodeServer compatível Esri",
    "imagens:ler": "buscar e ler coleções/itens STAC do catálogo de imagens do dono (L1-01-a), via "
    "/svc/<token>/stac/; nunca vê coleção de outro inquilino",
    "imagens:escrever": "criar coleção e item STAC no catálogo de imagens do dono (L1-01-a); quem tem este "
    "escopo também lê (checado em app/imagens/rotas_stac.py, não em escopos.cobre)",
    "multiescala:usar": "criar área de estudo, fator e amostra, e rodar execução macro/micro do motor "
    "multicritério em grades aninhadas (L3-19-multiescala; dado e execução do próprio inquilino)",
    "amc:usar": "criar e executar modelo multicritério (exige analise.amc no dono; L3-01-a)",
    "imagens:ler": "buscar e ler coleções/itens STAC do catálogo de imagens do dono (L1-01-a), via "
    "/svc/<token>/stac/; nunca vê coleção de outro inquilino",
    "imagens:escrever": "criar coleção e item STAC no catálogo de imagens do dono (L1-01-a); quem tem este "
    "escopo também lê (checado em app/imagens/rotas_stac.py, não em escopos.cobre)",
    "analise3d:usar": "rodar linha de visada, bacia visual (viewshed), perfil de elevação e sombra sobre "
    "o terreno do próprio inquilino (L2-09-d; salvar como item exige conteudo.criar além do escopo)",
    "multiescala:usar": "criar área de estudo, fator e amostra, e rodar execução macro/micro do motor "
    "multicritério em grades aninhadas (L3-19-multiescala; dado e execução do próprio inquilino)",
    "crs:usar": "listar CRS, ler definição proj4 e transformar coordenada/bbox (L2-17-crs-transformacoes; "
    "serviço transversal sem estado por inquilino)",
    "conteudo:criar": "criar/editar os próprios itens por token (upload de arquivo em partes, L0-04-a): exige "
    "que o dono do token já tenha o privilégio conteudo.criar (editor ou admin), não é exclusivo de admin",
    "campo:usar": "PWA de campo (L2-07-a): ler os mapas de campo do dono e sincronizar coletas; "
    "emitido por POST /api/campo/sessao com validade de 30 dias, revogável como todo token de serviço",
    "admin:inquilino": "tudo o que o dono pode fazer pela API, exceto gerir tokens, senha, 2FA e sessões",
}

# --- perfis de chave de API (item L7-08-d): os quatro nomes que o portal oferece na criação de chave são
# APELIDOS de conjuntos do vocabulário acima, nunca escopos novos. O vocabulário fechado de `ESCOPO` não
# muda: ele já é o que o servidor confere em `exigir_escopo`, e inventar um segundo eixo de nomes daria
# duas verdades sobre a mesma chave. `leitura` é o perfil da chave de demonstração do portal.
PERFIS_DE_CHAVE = {
    "leitura": (
        ("catalogo:ler", "camada:ler", "tiles:ler"),
        "ler catálogo, feições e tiles; nenhuma escrita",
    ),
    "edicao": (
        ("catalogo:ler", "camada:ler", "camada:editar", "tiles:ler", "jobs:executar"),
        "o de leitura mais editar feições e executar jobs",
    ),
    "tiles": (("tiles:ler",), "só tiles vetoriais e raster (chave de aplicação de mapa)"),
    "admin": (("admin:inquilino",), "tudo o que o dono pode fazer pela API, exceto gerir token, senha, 2FA e sessão"),
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


# --- catálogo (L0-03; ADR 0004 seção 13): o <uuid> de camada:ler/camada:editar/tiles:ler tem de existir e ser
# legível pelo dono do token na criação (422 escopo_item_inexistente); a função vem do catálogo para não acoplar
COM_UUID = re.compile(rf"^(camada:(ler|editar)|tiles:ler):({UUID})$")


def uuids_inexistentes(auth, escopos: list[str]) -> list[str]:
    from app.catalogo import item_legivel

    ruins = []
    for e in escopos:
        m = COM_UUID.match(e)
        if m and not item_legivel(auth, m.group(3)):
            ruins.append(e)
    return ruins
