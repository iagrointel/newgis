"""Escopos de token de serviço: vocabulário fechado validado por expressão regular (ADR 0002 seção 8.2).
`exigir_escopo(auth, base, uuid)` é o que as linhas futuras (L0-03, L2-04, L1-02, L0-05) chamam."""

import re

from app.erros import ErroAPI

UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
# L1-02-b (conserto 17/09): o escopo POR LISTA de `tiles:ler` tem de alcançar item de IMAGEM, e o id de um
# item STAC não é um uuid — é uma string livre da própria fonte (a suíte da casa usa `item-nao-uuid-1`, uma
# cena Sentinel-2 chega como `S2B_MSIL2A_...`). Enquanto só `tiles:ler:<uuid>` era aceito, `POST /api/tokens`
# devolvia 422 "escopo fora do vocabulário" para o caso mais comum do item, e o único jeito de servir tile de
# imagem por token era `imagens:ler`/`tiles:ler` SEM lista — isto é, escopo largo, o oposto do que o item
# promete. `ID_ITEM` aceita uuid E id de item STAC; o `:` fica de fora do conjunto de propósito, porque é o
# separador do próprio escopo (com ele, `tiles:ler:a:b` viraria ambíguo).
ID_ITEM = r"[A-Za-z0-9_][A-Za-z0-9._~\-]{0,127}"
# ⚠ Este vocabulário é a UNIÃO de todos os escopos que as rotas de fato exigem. A fusão de ramos o
# encolheu duas vezes: em 10/09 a expressão regular nasceu concatenada doze vezes, e em 11/09 faltavam
# QUATRO escopos que rotas vivas exigem — `conteudo:criar` (app/uploads/rotas.py, o envio de arquivo
# inteiro), `imagens:ler` e `imagens:escrever` (app/imagens/*) e `catalogo:escrever` (app/modelos3d).
# Sem eles, `POST /api/tokens` recusa com "escopo fora do vocabulário" e a funcionalidade morre sem
# erro visível no lado que a implementa. Medido ao publicar a união.
# Regra ao mexer aqui: o conjunto desta expressão tem de ser o mesmo de ESCOPOS_SEM_UUID e o mesmo das
# chaves de DESCRICAO; `tests/unit/test_escopos_vocabulario.py` confere os três contra as rotas.
ESCOPO = re.compile(
    rf"^(catalogo:(ler|escrever)|camada:(ler|editar)(:{UUID})?|tiles:ler(:{ID_ITEM})?|jobs:executar|"
    rf"rota:usar|geocodificar:usar|multiescala:usar|parcelas:usar|conteudo:(criar|exportar)|"
    rf"imagens:(ler|escrever)|rede:(ler|editar|validar|analisar)|campo:usar|crs:usar|fluxo:ler|"
    rf"analise3d:usar|admin:inquilino)$"
)
ESCOPOS_SEM_UUID = (
    "catalogo:ler", "catalogo:escrever", "camada:ler", "camada:editar", "tiles:ler", "jobs:executar",
    "rota:usar", "geocodificar:usar", "multiescala:usar", "parcelas:usar", "conteudo:criar", "conteudo:exportar",
    "imagens:ler", "imagens:escrever", "rede:ler", "rede:editar", "rede:validar", "rede:analisar",
    "campo:usar",
    "crs:usar", "fluxo:ler", "analise3d:usar", "admin:inquilino",
)
DESCRICAO = {
    "catalogo:ler": "listar e ler metadado de itens que o dono pode ler",
    "camada:ler": "ler feições e atributos de camada legível pelo dono (opcional :<uuid> de uma camada)",
    "camada:editar": "editar feições (exige feicoes.editar no dono; opcional :<uuid>)",
    "tiles:ler": "tiles vetoriais e raster (opcional :<uuid>)",
    "jobs:executar": "criar e ler os próprios jobs (exige jobs.executar no dono)",
    "rota:usar": "calcular rota, matriz origem-destino e isócrona (L2-11-c; dado de teste, sem PII)",
    "geocodificar:usar": "geocodificar, geocodificar reverso e sugerir endereço (L2-11-b; dado aberto CNEFE, "
    "sem PII); mesmo escopo cobre o GeocodeServer compatível Esri",
    "multiescala:usar": "criar área de estudo, fator e amostra, e rodar execução macro/micro do motor "
    "multicritério em grades aninhadas (L3-19-multiescala; dado e execução do próprio inquilino)",
    "parcelas:usar": "rodar os fluxos da malha de parcelas do próprio inquilino na fachada "
    "/api/parcelas/fabrica (L4-parcelas-02: build, divide, merge, clip, seeds, assignFeaturesToRecord)",
    "catalogo:escrever": "editar, mover, apagar/restaurar, versionar e relacionar item do catálogo do próprio "
    "inquilino pela API (RLS `plat.pode_editar`, mesma trava de sessão; também cobre modelo 3D, app/modelos3d)",
    "conteudo:criar": "criar item novo no catálogo (POST /api/itens) e enviar arquivo pelo upload retomável "
    "(exige conteudo.criar no dono); é o escopo que a tela troca pela sessão antes de começar o envio, "
    "porque o corpo da parte é byte cru",
    "conteudo:exportar": "ler o status, baixar e cancelar/apagar a própria exportação de camada (exige "
    "conteudo.exportar no dono)",
    "imagens:ler": "ler imagem: ficha, ladrilho, COG por HTTPS, predefinição de renderização e STAC",
    "imagens:escrever": "criar e alterar coleção e item STAC do próprio inquilino",
    "rede:ler": "ler rede de utilidades: nós, arestas, subredes, diagrama e sumário",
    "rede:editar": "criar e alterar feição de rede, topologia e subrede do próprio inquilino",
    "rede:validar": "rodar as regras de validação de rede (conectividade, atributo, contenção)",
    "rede:analisar": "rodar traçado (conectado, montante, jusante, isolamento), fluxo de potência, "
    "curto-circuito e exportação para OpenDSS, pandapower, MATPOWER e EPANET",
    "campo:usar": "fila, roteiro, visita e foto do módulo de campo (o app do aparelho usa este escopo)",
    "crs:usar": "converter coordenada entre sistemas de referência",
    "fluxo:ler": "ler definição e execução de fluxo de geoprocessamento",
    "analise3d:usar": "linha de visada, bacia visual, perfil de elevação e sombra projetada sobre terreno "
    "inline (L2-09-d); salvar o resultado como item exige conteudo.criar no dono",
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


# --- catálogo (L0-03; ADR 0004 seção 13): o <uuid> de camada:ler/camada:editar/tiles:ler tem de existir e ser
# legível pelo dono do token na criação (422 escopo_item_inexistente); a função vem do catálogo para não acoplar
COM_UUID = re.compile(rf"^(camada:(ler|editar)|tiles:ler):({UUID})$")
# L1-02-b: `tiles:ler:<id>` em que `<id>` NÃO é uuid só pode ser item STAC (imagem). A existência continua
# exigida — o que muda é ONDE se procura: `plat.item` para uuid, catálogo STAC do próprio inquilino para o resto.
COM_ID_STAC = re.compile(rf"^tiles:ler:({ID_ITEM})$")


def uuids_inexistentes(auth, escopos: list[str]) -> list[str]:
    from app.catalogo import item_legivel

    ruins = []
    for e in escopos:
        m = COM_UUID.match(e)
        if m:
            if not item_legivel(auth, m.group(3)):
                ruins.append(e)
            continue
        m = COM_ID_STAC.match(e)
        if m and not _item_stac_legivel(auth, m.group(1)):
            ruins.append(e)
    return ruins


def _item_stac_legivel(auth, item_id: str) -> bool:
    """O item STAC existe em alguma coleção DO PRÓPRIO INQUILINO do dono do token. Nunca confirma a
    existência de item alheio: a busca é filtrada pelo prefixo `<tenant_id>-` das coleções."""
    from app import db
    from app.imagens import pgstac

    with db.db(auth.contexto()) as cur:
        return pgstac.item_existe_no_tenant(cur, auth.tenant_id, item_id)


# ---------------------------------------------------------------------------------------------
# (entrega 10/09) União das definições que outros ramos acrescentaram a este mesmo arquivo e que a
# fusão descartou ao ficar com um lado só. Ordem preservada do ramo de origem.


# de wt/t4port
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


# de wt/upload; `conteudo:exportar` acrescentado no item de seguimento de L0-04-a/L0-11 (mesma causa raiz:
# app/exportacao/rotas.py::apagar exigia admin:inquilino para cancelar/apagar a PRÓPRIA exportação — só
# perfil admin conseguia emitir, embora `conteudo.exportar` já seja privilégio de editor/admin, não só admin)
ESCOPO_EXIGE_PRIVILEGIO = {"conteudo:criar": "conteudo.criar", "conteudo:exportar": "conteudo.exportar"}
