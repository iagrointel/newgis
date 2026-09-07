"""API da tabela de atributos de uma camada (item L2-01-g-tabela-atributos).

Quatro rotas, todas sob `/api/camadas/{item_id}/tabela`:

- `GET  .../colunas`      colunas visíveis, com rótulo (alias), tipo, largura e domínio;
- `GET  .../vista`        a vista gravada do usuário (inclui o que está OCULTO — é por onde se volta atrás);
- `PUT  .../vista`        grava a vista (ordem, alias, oculta, largura, domínio);
- `POST .../linhas`       página de linhas com contagem total sob o mesmo filtro;
- `POST .../estatisticas` agregados por coluna numérica sob o mesmo filtro.

Por que `POST` para ler linhas e estatísticas: o filtro carrega a seleção do mapa (até
`limites.TABELA_FIDS_MAX` identificadores) e a extensão em coordenadas — não cabe em query string sem
esbarrar no limite de URL de servidor e navegador, e a seleção do usuário não deve entrar no log de acesso
como parte do caminho. Nenhuma das duas rotas escreve; as duas exigem só leitura do item.

A contagem é feita na MESMA transação e com o MESMO `WHERE` da página. É por isso que a resposta pode
dizer `total` sem risco de o número contradizer a lista: uma transação só, um filtro só, montado uma vez.

Isolamento: `comum.item_ou_404` já responde 404 para item de outro inquilino (RLS de `plat.item`), e a
tabela de feições tem RLS FORCE por `tenant_id` (migração 029). Nenhum filtro de inquilino é escrito aqui.
"""

import json

from fastapi import APIRouter, Body, Request
from pydantic import BaseModel, Field, field_validator

from app import db, limites
from app.auth.sessao import Auth, autenticado
from app.catalogo import comum
from app.erros import ErroAPI
from app.tabela import consulta

router = APIRouter(prefix="/api/camadas/{item_id}/tabela", tags=["tabela"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
ESCREVER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}


class Filtro(BaseModel):
    """Filtro comum a `linhas` e `estatisticas` — os dois têm de ver exatamente o mesmo conjunto."""

    busca: str | None = Field(default=None, max_length=limites.TABELA_BUSCA_MAX)
    bbox: list[float] | None = Field(default=None, min_length=4, max_length=4,
                                     description="extensão do mapa em WGS84: [oeste, sul, leste, norte]")
    fids: list[int] | None = Field(default=None, max_length=limites.TABELA_FIDS_MAX,
                                   description="seleção vinda do mapa: valores da chave primária")


class PedidoLinhas(Filtro):
    pagina: int = Field(default=1, ge=1)
    por_pagina: int = Field(default=limites.TABELA_PAGINAS[0])
    ordenar_por: str | None = Field(default=None, max_length=63)
    ordem: str = Field(default="asc")
    geometria: bool = Field(default=False, description="devolve a geometria em GeoJSON 4326 para o mapa desenhar")
    contar: bool = Field(default=True, description="conta o total sob o mesmo filtro; false devolve total nulo")

    @field_validator("por_pagina")
    @classmethod
    def _v_pagina(cls, v):
        if v not in limites.TABELA_PAGINAS:
            raise ValueError(f"por_pagina precisa ser um de {list(limites.TABELA_PAGINAS)}")
        return v

    @field_validator("ordem")
    @classmethod
    def _v_ordem(cls, v):
        if (v or "").lower() not in ("asc", "desc"):
            raise ValueError("ordem precisa ser 'asc' ou 'desc'")
        return v.lower()


class PedidoEstatisticas(Filtro):
    colunas: list[str] | None = Field(default=None, max_length=limites.TABELA_COLUNAS_MAX)


class ColunaVista(BaseModel):
    nome: str = Field(max_length=63)
    alias: str | None = Field(default=None, max_length=limites.TABELA_ALIAS_MAX)
    oculta: bool = False
    largura: int | None = Field(default=None, ge=limites.TABELA_LARGURA_MIN, le=limites.TABELA_LARGURA_MAX)
    dominio: dict[str, str] | None = None

    @field_validator("dominio")
    @classmethod
    def _v_dominio(cls, v):
        if v is None:
            return v
        if len(v) > limites.TABELA_DOMINIO_ITENS_MAX:
            raise ValueError(f"domínio aceita no máximo {limites.TABELA_DOMINIO_ITENS_MAX} pares")
        for codigo, descricao in v.items():
            if len(codigo) > limites.TABELA_DOMINIO_TEXTO_MAX or len(descricao) > limites.TABELA_DOMINIO_TEXTO_MAX:
                raise ValueError(f"código e descrição do domínio: até {limites.TABELA_DOMINIO_TEXTO_MAX} caracteres")
        return v


class PedidoVista(BaseModel):
    colunas: list[ColunaVista] = Field(default_factory=list, max_length=limites.TABELA_COLUNAS_MAX)


def _camada(cur, item_id: str) -> dict:
    item = comum.item_ou_404(cur, item_id)
    if (item.get("tipo") or "") != "camada_vetorial":
        raise ErroAPI(409, "nao_e_camada", "este item não é uma camada vetorial")
    return item


def _vista_gravada(cur, item_id: str, usuario_id: int) -> dict[str, dict]:
    cur.execute("SELECT colunas FROM plat.tabela_vista WHERE item_id = %s::uuid AND usuario_id = %s",
                (item_id, usuario_id))
    r = cur.fetchone()
    if not r:
        return {}
    return {c["nome"]: c for c in (r["colunas"] or []) if isinstance(c, dict) and c.get("nome")}


def _aliases_do_item(item: dict) -> dict[str, str]:
    campos = ((item.get("dados") or {}).get("campos") or [])
    return {c["nome"]: c["alias"] for c in campos if isinstance(c, dict) and c.get("nome") and c.get("alias")}


def _colunas(cur, item: dict, usuario_id: int) -> tuple[list[dict], list[dict], str | None, str | None, str, str, int]:
    """(todas, visíveis, chave, geometria, schema, tabela, srid) já com alias/largura/domínio/ordem da vista."""
    schema, tabela, srid = consulta.origem_da_camada(item)
    fisicas = consulta.colunas_do_banco(cur, schema, tabela)
    if not fisicas:
        raise ErroAPI(404, "tabela_inexistente", "a tabela de feições desta camada não existe mais")
    chave = consulta.coluna_chave(cur, schema, tabela)
    geom = consulta.coluna_geometria(fisicas)
    vista = _vista_gravada(cur, str(item["id"]), usuario_id)
    aliases = _aliases_do_item(item)
    ordem_vista = {nome: i for i, nome in enumerate(vista)}
    todas = []
    for c in fisicas:
        v = vista.get(c["nome"], {})
        todas.append({
            "nome": c["nome"],
            "alias": v.get("alias") or aliases.get(c["nome"]) or c["nome"],
            "tipo": c["tipo"],
            "udt": c["udt"],
            "aceita_nulo": c["aceita_nulo"],
            "chave": c["nome"] == chave,
            "oculta": bool(v.get("oculta")),
            "largura": v.get("largura"),
            "dominio": v.get("dominio"),
        })
    # ordem: primeiro o que a vista do usuário ordenou, depois o que ela não menciona, na ordem física
    ordem_fisica = {c["nome"]: i for i, c in enumerate(fisicas)}
    todas.sort(key=lambda c: (0, ordem_vista[c["nome"]]) if c["nome"] in ordem_vista
               else (1, ordem_fisica[c["nome"]]))
    visiveis = [c for c in todas if not c["oculta"] and c["tipo"] != "geometria"]
    return todas, visiveis, chave, geom, schema, tabela, srid


@router.get("/colunas", summary="colunas visíveis da tabela de atributos", openapi_extra=LER)
def colunas(item_id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):  # noqa: B008
    """Só o que a vista do usuário mostra: coluna marcada como oculta não sai daqui (nem a geometria, que não
    é atributo). Para ver o que está oculto e voltar atrás, `GET .../vista`."""
    with db.db(auth.contexto(), somente_leitura=True) as cur:
        item = _camada(cur, item_id)
        _todas, visiveis, chave, geom, _s, _t, _srid = _colunas(cur, item, auth.usuario_id)
        return {"colunas": visiveis, "chave": chave, "tem_geometria": bool(geom)}


@router.get("/vista", summary="vista gravada da tabela (inclui colunas ocultas)", openapi_extra=LER)
def vista_ver(item_id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):  # noqa: B008
    with db.db(auth.contexto(), somente_leitura=True) as cur:
        item = _camada(cur, item_id)
        todas, _v, chave, geom, _s, _t, _srid = _colunas(cur, item, auth.usuario_id)
        return {"colunas": todas, "chave": chave, "tem_geometria": bool(geom)}


@router.put("/vista", summary="grava a vista da tabela para o usuário", openapi_extra=ESCREVER)
def vista_gravar(item_id: str, corpo: PedidoVista, request: Request,
                 auth: Auth = autenticado()):  # noqa: B008
    """Ordem, rótulo, visibilidade, largura e domínio — por usuário e por camada. A largura persistida aqui é
    o que a tela lê no próximo carregamento; nada disso fica no navegador."""
    with db.db(auth.contexto()) as cur:
        item = _camada(cur, item_id)
        todas, _v, _chave, _geom, _s, _t, _srid = _colunas(cur, item, auth.usuario_id)
        conhecidas = {c["nome"] for c in todas}
        for c in corpo.colunas:
            if c.nome not in conhecidas:
                raise ErroAPI(422, "coluna_invalida", f"a camada não tem a coluna {c.nome!r}")
        guardar = [c.model_dump(exclude_none=True) for c in corpo.colunas]
        cur.execute(
            "INSERT INTO plat.tabela_vista (tenant_id, item_id, usuario_id, colunas) "
            "VALUES (plat.tenant_atual(), %s::uuid, %s, %s) "
            "ON CONFLICT (item_id, usuario_id) DO UPDATE SET colunas = EXCLUDED.colunas",
            (str(item["id"]), auth.usuario_id, comum.jsonb(guardar)),
        )
        comum.registrar_evento(cur, request, "camadas/vista_tabela", "item", str(item["id"]),
                               {"colunas": len(guardar)})
        todas, visiveis, chave, geom, _s, _t, _srid = _colunas(cur, item, auth.usuario_id)
    return {"colunas": todas, "visiveis": len(visiveis), "chave": chave, "tem_geometria": bool(geom)}


@router.post("/linhas", summary="página de linhas da tabela de atributos", openapi_extra=LER)
def linhas(item_id: str, corpo: PedidoLinhas = Body(default_factory=PedidoLinhas),  # noqa: B008
           auth: Auth = autenticado(escopo_token="catalogo:ler")):  # noqa: B008
    with db.db(auth.contexto(), somente_leitura=True) as cur:
        item = _camada(cur, item_id)
        _todas, visiveis, chave, geom, schema, tabela, srid = _colunas(cur, item, auth.usuario_id)
        pedido = corpo.model_dump()
        onde, params = consulta.filtro(_todas, chave, geom, srid, pedido)
        alvo = f'{consulta.citar(schema)}.{consulta.citar(tabela)}'
        clausula = f" WHERE {onde}" if onde else ""

        # A contagem é um `count(*)` de verdade sob o mesmo filtro, e numa camada larga de 1 milhão de linhas
        # ela custa mais que a página: a política de RLS vira `current_setting(...)`, que é PARALLEL RESTRICTED,
        # então a varredura é serial (MEDIDO: 263 ms em 281 MB, contra 0,05 ms da página pelo índice). Trocar
        # a página ou a ordem NÃO muda o total; por isso a tela pede `contar` uma vez, quando o filtro muda, e
        # manda `contar: false` ao paginar e ao reordenar. Quem quiser o número em toda chamada só não manda o
        # campo — o padrão continua contando.
        total = None
        if corpo.contar:
            cur.execute(f"SELECT count(*) AS total FROM {alvo}{clausula}", params)
            total = int(cur.fetchone()["total"])

        com_geometria = bool(corpo.geometria and geom and corpo.por_pagina <= limites.TABELA_GEOMETRIA_LIMITE)
        campos = consulta.selecao(visiveis, chave, geom, com_geometria)
        ordem = consulta.ordenacao(_todas, chave, corpo.ordenar_por, corpo.ordem)
        deslocamento = (corpo.pagina - 1) * corpo.por_pagina
        cur.execute(f"SELECT {campos} FROM {alvo}{clausula}{ordem} LIMIT %s OFFSET %s",
                    [*params, corpo.por_pagina, deslocamento])
        brutas = cur.fetchall()

    saida = []
    for r in brutas:
        linha = dict(r)
        geometria = linha.pop("__geometria", None)
        registro = {"valores": linha}
        if chave:
            registro["id"] = linha.get(chave)
        if com_geometria:
            registro["geometria"] = json.loads(geometria) if geometria else None
        saida.append(registro)
    return {
        "total": total, "pagina": corpo.pagina, "por_pagina": corpo.por_pagina,
        "paginas": None if total is None else (total + corpo.por_pagina - 1) // corpo.por_pagina,
        "colunas": visiveis, "chave": chave, "linhas": saida,
    }


@router.post("/estatisticas", summary="estatísticas por coluna numérica sob o mesmo filtro", openapi_extra=LER)
def estatisticas(item_id: str, corpo: PedidoEstatisticas = Body(default_factory=PedidoEstatisticas),  # noqa: B008
                 auth: Auth = autenticado(escopo_token="catalogo:ler")):  # noqa: B008
    """Contagem, soma, média, mínimo, máximo e nulos, calculados no banco — nunca sobre a página carregada na
    tela (a página é 50 linhas de um milhão; a média dela não é a média da camada)."""
    with db.db(auth.contexto(), somente_leitura=True) as cur:
        item = _camada(cur, item_id)
        todas, visiveis, chave, geom, schema, tabela, srid = _colunas(cur, item, auth.usuario_id)
        if corpo.colunas:
            alvo_colunas = []
            for nome in corpo.colunas:
                c = consulta.achar(todas, nome, "colunas")
                if c["tipo"] != "numero":
                    raise ErroAPI(422, "coluna_nao_numerica", f"a coluna {nome!r} não é numérica")
                alvo_colunas.append(c)
        else:
            alvo_colunas = [c for c in visiveis if c["tipo"] == "numero"]
        onde, params = consulta.filtro(todas, chave, geom, srid, corpo.model_dump())
        alvo = f'{consulta.citar(schema)}.{consulta.citar(tabela)}'
        clausula = f" WHERE {onde}" if onde else ""
        saida = {}
        for c in alvo_colunas:
            cur.execute(f"SELECT {consulta.estatisticas_sql(c)} FROM {alvo}{clausula}", params)
            r = cur.fetchone()
            saida[c["nome"]] = {
                "contagem": int(r["contagem"]), "soma": r["soma"], "media": r["media"],
                "minimo": r["minimo"], "maximo": r["maximo"], "nulos": int(r["nulos"]),
            }
    return {"colunas": saida}
