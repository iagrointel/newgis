"""Documento de mapa: as regras que o JSON Schema de `plat.tipo_item` (mapa-v1) não expressa, e a resolução
das referências para `GET /api/mapas/{id}/completo` (item L2-01-a-documento-mapa; ADR 0022).

Divisão de trabalho, deliberada:

1. **JSON Schema** (`docs/esquemas/mapa-v1.json`, gerado de `plat.tipo_item.esquema` pela migração
   `20260906T1547_documento_mapa.sql`): forma, tipos, faixas, tetos e a extensão dentro do mundo. Roda em
   `app/catalogo/tipos.py:validar`, o MESMO validador de todo item do catálogo — documento fora do esquema
   é `422 dados_invalidos` com o caminho do campo. Nada aqui reimplementa isso.
2. **Este módulo**: o que exige olhar a LISTA INTEIRA e por isso não cabe em JSON Schema puro sem `$data` —
   id repetido, grupo inexistente, ciclo de grupo, profundidade de grupo, favorito apontando para camada que
   não está no documento, extensão invertida (oeste ≥ leste).
3. **Banco**: existência e visibilidade das referências. `ref` é sempre uuid de item do catálogo, nunca URL
   (C1 do `laco/decomposicao/L2_CONCEITO.md`); a RLS de `plat.item` decide o que o ator enxerga, então uuid de
   outro inquilino e uuid inexistente dão a MESMA resposta (`404`), como manda o contrato de erro (L0-12).

Fronteira honesta desta passagem: `filtro` é validado só como objeto (a gramática CQL2-JSON é do item
L2-01-h), `popup.embutido` e `estilo.embutido` são objetos livres até o L2-01-d e o L2-02-a fixarem a forma,
e `dominios` sai sempre vazio porque não existe vocabulário de domínio na camada (L0-04-c está PARCIAL) —
o campo vem com o motivo escrito, nunca um valor inventado.
"""

from __future__ import annotations

import uuid as uuid_mod

from app.erros import ErroAPI

# tetos espelhados do esquema publicado (docs/esquemas/mapa-v1.json); mudar lá exige mudar aqui e no teste
CAMADAS_MAX = 200
GRUPOS_MAX = 100
FAVORITOS_MAX = 50
PROFUNDIDADE_GRUPO_MAX = 3

# tipos de item que uma camada do mapa pode referenciar. `conexao` é como o acervo da casa e o serviço externo
# entram no catálogo (app/acervo/rotas.py e app/conexao); `rede` entra porque `camada_de_mapa` já a aceita.
TIPOS_REF_CAMADA = {"camada_vetorial", "vista_de_camada", "raster", "rede", "conexao"}
TIPOS_REF_BASE = {"camada_vetorial", "vista_de_camada", "raster"}
TIPOS_REF_ESTILO = {"estilo"}
TIPOS_REF_POPUP = {"estilo"}

MOTIVO_TILES_VETOR = "sem servidor de tiles vetoriais instalado nesta máquina (item L2-01-b-martin-tiles-vetoriais)"
MOTIVO_TILES_RASTER = "sem servidor de tiles raster instalado nesta máquina (item L1-02-titiler-raster)"
MOTIVO_DOMINIOS = "a camada ainda não guarda vocabulário de domínio por campo (item L0-04-c-tabela-camada, parcial)"


def corpo_de(dados) -> dict:
    return (dados or {}).get("corpo") or {}


def _erro(campo: str, mensagem: str, regra: str) -> dict:
    return {"campo": campo, "erro": mensagem, "regra": regra}


def _extensao_incoerente(campo: str, ext, saida: list[dict]) -> None:
    if not isinstance(ext, list) or len(ext) != 4 or not all(isinstance(v, (int, float)) for v in ext):
        return  # forma é problema do JSON Schema, não deste passo
    oeste, sul, leste, norte = ext
    if oeste >= leste:
        saida.append(_erro(campo, "oeste precisa ser menor que leste", "extensao_invertida"))
    if sul >= norte:
        saida.append(_erro(campo, "sul precisa ser menor que norte", "extensao_invertida"))


def erros_de_coerencia(dados) -> list[dict]:
    """Lista [{campo, erro, regra}] (vazia = coerente). Não toca no banco."""
    corpo = corpo_de(dados)
    saida: list[dict] = []

    grupos = corpo.get("grupos") or []
    por_grupo: dict[str, dict] = {}
    for i, g in enumerate(grupos):
        if not isinstance(g, dict):
            continue
        gid = g.get("id")
        if gid in por_grupo:
            saida.append(_erro(f"corpo.grupos.{i}.id", f"id de grupo repetido: {gid}", "id_repetido"))
        elif isinstance(gid, str):
            por_grupo[gid] = g
    for i, g in enumerate(grupos):
        if not isinstance(g, dict):
            continue
        pai = g.get("pai")
        if pai is not None and pai not in por_grupo:
            saida.append(_erro(f"corpo.grupos.{i}.pai", f"grupo inexistente: {pai}", "grupo_inexistente"))

    # ciclo e profundidade: sobe do grupo até a raiz contando os saltos; visto repetido no caminho = ciclo
    profundidade: dict[str, int] = {}
    for i, g in enumerate(grupos):
        gid = g.get("id") if isinstance(g, dict) else None
        if not isinstance(gid, str) or gid not in por_grupo:
            continue
        caminho: list[str] = []
        atual: str | None = gid
        while atual is not None:
            if atual in caminho:
                saida.append(
                    _erro(f"corpo.grupos.{i}.pai", "ciclo de grupos: " + " → ".join([*caminho, atual]), "grupo_ciclo")
                )
                caminho = []
                break
            caminho.append(atual)
            pai = por_grupo[atual].get("pai") if atual in por_grupo else None
            atual = pai if isinstance(pai, str) and pai in por_grupo else None
        if caminho:
            profundidade[gid] = len(caminho)
            if len(caminho) > PROFUNDIDADE_GRUPO_MAX:
                saida.append(
                    _erro(
                        f"corpo.grupos.{i}.pai",
                        f"aninhamento de {len(caminho)} níveis; o máximo é {PROFUNDIDADE_GRUPO_MAX}",
                        "grupo_profundo",
                    )
                )

    camadas = corpo.get("camadas") or []
    ids_camada: set[str] = set()
    for i, c in enumerate(camadas):
        if not isinstance(c, dict):
            continue
        cid = c.get("id")
        if isinstance(cid, str):
            if cid in ids_camada:
                saida.append(_erro(f"corpo.camadas.{i}.id", f"id de camada repetido: {cid}", "id_repetido"))
            ids_camada.add(cid)
        grupo = c.get("grupo")
        if grupo is not None and grupo not in por_grupo:
            saida.append(_erro(f"corpo.camadas.{i}.grupo", f"grupo inexistente: {grupo}", "grupo_inexistente"))
        emin, emax = c.get("escala_min"), c.get("escala_max")
        if isinstance(emin, (int, float)) and isinstance(emax, (int, float)) and emin and emax and emin > emax:
            saida.append(
                _erro(
                    f"corpo.camadas.{i}.escala_max",
                    "faixa de escala invertida: escala_min é o menor denominador (mais perto) e precisa ser "
                    "menor ou igual a escala_max",
                    "escala_invertida",
                )
            )

    _extensao_incoerente("corpo.extensao_inicial", corpo.get("extensao_inicial"), saida)
    for i, f in enumerate(corpo.get("favoritos") or []):
        if not isinstance(f, dict):
            continue
        _extensao_incoerente(f"corpo.favoritos.{i}.extensao", f.get("extensao"), saida)
        for j, cid in enumerate(f.get("camadas_visiveis") or []):
            if cid not in ids_camada:
                saida.append(
                    _erro(
                        f"corpo.favoritos.{i}.camadas_visiveis.{j}",
                        f"camada fora do documento: {cid}",
                        "camada_inexistente",
                    )
                )
    return saida


def validar_coerencia(dados) -> None:
    erros = erros_de_coerencia(dados)
    if erros:
        raise ErroAPI(422, "documento_incoerente", "documento de mapa incoerente", erros)


def _uuid(v) -> str | None:
    try:
        return str(uuid_mod.UUID(str(v)))
    except (ValueError, TypeError, AttributeError):
        return None


def referencias(dados) -> list[tuple[str, str, set[str]]]:
    """[(campo, uuid, tipos_aceitos)] de tudo que o documento aponta para o catálogo, na ordem do documento."""
    corpo = corpo_de(dados)
    saida: list[tuple[str, str, set[str]]] = []
    base = corpo.get("mapa_base")
    if isinstance(base, dict) and (u := _uuid(base.get("ref"))):
        saida.append(("corpo.mapa_base.ref", u, TIPOS_REF_BASE))
    for i, c in enumerate(corpo.get("camadas") or []):
        if not isinstance(c, dict):
            continue
        if u := _uuid(c.get("ref")):
            saida.append((f"corpo.camadas.{i}.ref", u, TIPOS_REF_CAMADA))
        for chave, aceitos in (("estilo", TIPOS_REF_ESTILO), ("popup", TIPOS_REF_POPUP)):
            alvo = c.get(chave)
            if isinstance(alvo, dict) and (u := _uuid(alvo.get("ref"))):
                saida.append((f"corpo.camadas.{i}.{chave}.ref", u, aceitos))
    return saida


def carregar_referencias(cur, dados) -> dict[str, dict]:
    """{uuid: linha do item} para tudo que o documento referencia, sob a RLS do ator.

    uuid que a RLS esconde (outro inquilino) e uuid que não existe caem no MESMO 404 — a resposta nunca
    diferencia os dois casos. Tipo de item incompatível com o lugar onde foi citado dá 422.
    """
    refs = referencias(dados)
    if not refs:
        return {}
    ids = sorted({u for _campo, u, _aceitos in refs})
    cur.execute(
        "SELECT id::text AS id, tipo, titulo, dados FROM plat.item "
        "WHERE id = ANY(%s::uuid[]) AND apagado_em IS NULL",
        (ids,),
    )
    achados = {r["id"]: dict(r) for r in cur.fetchall()}
    faltando = [{"campo": campo, "ref": u} for campo, u, _a in refs if u not in achados]
    if faltando:
        raise ErroAPI(
            404,
            "referencia_inexistente",
            "o documento referencia item que não existe ou que você não pode ler",
            faltando,
        )
    incompativeis = [
        _erro(campo, f"item do tipo {achados[u]['tipo']} não pode ser referenciado aqui", "tipo_de_ref")
        for campo, u, aceitos in refs
        if achados[u]["tipo"] not in aceitos
    ]
    if incompativeis:
        raise ErroAPI(422, "referencia_de_tipo_invalido", "referência para tipo de item incompatível", incompativeis)
    return achados


# ------------------------------------------------------------------ resolução do documento completo
def _tiles_da_camada(item: dict) -> dict:
    """Contrato de URL de tiles (C3 do L2_CONCEITO): `/tiles/{token}/c_<16 hex do uuid>/{z}/{x}/{y}.pbf` para
    camada hospedada e `/raster/{token}/<uuid>/{z}/{x}/{y}.png` para raster. Nenhum serviço responde nestes
    caminhos nesta máquina ainda (Martin e TiTiler são itens à frente): `pronto` diz isso em vez de a API
    devolver um endereço que dá 404 no navegador."""
    tipo = item["tipo"]
    if tipo in ("camada_vetorial", "vista_de_camada", "rede"):
        curto = item["id"].replace("-", "")[:16]
        return {
            "servico": "martin",
            "padrao": f"/tiles/{{token}}/c_{curto}/{{z}}/{{x}}/{{y}}.pbf",
            "formato": "application/vnd.mapbox-vector-tile",
            "pronto": False,
            "motivo": MOTIVO_TILES_VETOR,
        }
    if tipo == "raster":
        return {
            "servico": "titiler",
            "padrao": f"/raster/{{token}}/{item['id']}/{{z}}/{{x}}/{{y}}.png",
            "formato": "image/png",
            "pronto": False,
            "motivo": MOTIVO_TILES_RASTER,
        }
    if tipo == "conexao":
        dados = item.get("dados") or {}
        url = dados.get("url")
        return {
            "servico": dados.get("protocolo") or "externo",
            "url": url,
            "pronto": bool(url),
            "motivo": None if url else "conexão sem URL registrada",
        }
    return {"servico": None, "pronto": False, "motivo": f"tipo {tipo} sem serviço de tiles"}


def _campos_da_camada(item: dict, achados: dict[str, dict], cur) -> list[dict]:
    """Campos legíveis da camada. `vista_de_camada` herda os campos da camada de origem menos `campos_ocultos`
    (L0-04-j); a origem pode não estar entre as referências do documento, por isso a consulta extra — sempre
    sob a mesma RLS, então vista para camada de outro inquilino simplesmente não devolve campo."""
    dados = item.get("dados") or {}
    if item["tipo"] == "camada_vetorial":
        return list(dados.get("campos") or [])
    if item["tipo"] == "raster":
        return [
            {"nome": b.get("nome"), "tipo": "banda", "alias": b.get("nome_comum")} for b in dados.get("bandas") or []
        ]
    if item["tipo"] == "vista_de_camada":
        origem = _uuid(dados.get("camada_id"))
        if not origem:
            return []
        base = achados.get(origem)
        if base is None:
            cur.execute(
                "SELECT id::text AS id, tipo, titulo, dados FROM plat.item WHERE id = %s::uuid AND apagado_em IS NULL",
                (origem,),
            )
            linha = cur.fetchone()
            if linha is None:
                return []
            base = dict(linha)
        ocultos = set(dados.get("campos_ocultos") or [])
        return [c for c in ((base.get("dados") or {}).get("campos") or []) if c.get("nome") not in ocultos]
    return []


def _resolver_estilo(alvo, achados: dict[str, dict]) -> dict:
    if not isinstance(alvo, dict):
        return {"origem": "ausente"}
    if "embutido" in alvo:
        return {"origem": "embutido", "corpo": alvo.get("embutido")}
    u = _uuid(alvo.get("ref"))
    item = achados.get(u) if u else None
    if item is None:
        return {"origem": "ausente"}
    return {
        "origem": "item",
        "ref": u,
        "titulo": item["titulo"],
        "corpo": (item.get("dados") or {}).get("corpo"),
    }


def completo(cur, item_mapa: dict, dados: dict) -> dict:
    """Documento com as camadas resolvidas em UMA chamada: título e tipo do item, campos, domínios, estilo,
    popup e contrato de tiles por camada. Duas consultas ao banco no caso comum (o item do mapa já veio de
    fora; uma para todas as referências, outra só se houver vista de camada com origem fora do documento)."""
    corpo = corpo_de(dados)
    achados = carregar_referencias(cur, dados)
    camadas = []
    for c in corpo.get("camadas") or []:
        if not isinstance(c, dict):
            continue
        u = _uuid(c.get("ref"))
        item = achados.get(u) if u else None
        if item is None:
            continue
        camadas.append(
            {
                "id": c.get("id"),
                "ref": u,
                "tipo": item["tipo"],
                "titulo": c.get("titulo") or item["titulo"],
                "visivel": c.get("visivel", True),
                "opacidade": c.get("opacidade", 1),
                "escala_min": c.get("escala_min", 0),
                "escala_max": c.get("escala_max", 0),
                "grupo": c.get("grupo"),
                "geometria": (item.get("dados") or {}).get("geometria"),
                "srid": (item.get("dados") or {}).get("srid") or (item.get("dados") or {}).get("srid_nativo"),
                "campos": _campos_da_camada(item, achados, cur),
                "dominios": {},
                "dominios_motivo": MOTIVO_DOMINIOS,
                "estilo": _resolver_estilo(c.get("estilo"), achados),
                "popup": _resolver_estilo(c.get("popup"), achados),
                "filtro": c.get("filtro"),
                "rotulos": c.get("rotulos"),
                "hora": c.get("hora"),
                "atualizacao_s": c.get("atualizacao_s", 0),
                "tiles": _tiles_da_camada(item),
            }
        )
    base = dict(corpo.get("mapa_base") or {})
    if (u := _uuid(base.get("ref"))) and u in achados:
        base["titulo"] = base.get("titulo") or achados[u]["titulo"]
        base["tiles"] = _tiles_da_camada(achados[u])
    return {
        "id": item_mapa["id"],
        "titulo": item_mapa["titulo"],
        "tipo": item_mapa["tipo"],
        "esquema_versao": (dados or {}).get("esquema_versao"),
        "mapa_base": base,
        "camadas": camadas,
        "grupos": corpo.get("grupos") or [],
        "extensao_inicial": corpo.get("extensao_inicial"),
        "rotacao": corpo.get("rotacao", 0),
        "crs_exibicao": corpo.get("crs_exibicao", 3857),
        "favoritos": corpo.get("favoritos") or [],
    }
