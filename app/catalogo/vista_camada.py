"""Vistas de camada (item `L5-32-vistas-de-camada`, linha L5 builder).

Uma vista de camada é o equivalente da *hosted feature layer view*: mesma tabela de dado, com filtro
próprio, campos escondidos, leitura ou escrita, extensão limitada, estilo e janela de atributos
próprios — e compartilhável separadamente da camada-mãe.

A vista não é uma cópia nem um segundo caminho de leitura. Ela é uma VIEW do PostgreSQL criada em
`d_<slug>` com o mesmo padrão de nome de uma tabela de camada (`c_<16 hex do item>`), registrada no
catálogo como item do tipo `vista_de_camada` com `schema`/`tabela` apontando para ela. Por isso o
FeatureServer (`app.consulta.rotas_query`), o descritor de serviço, o OGC API Features e o WFS
servem a vista sem uma linha de código específica: para eles, `plat.item.dados` diz onde o dado está,
e o dado está na view.

Três consequências que são o portão deste item:

1. Campo oculto não é filtrado na saída: ele NÃO ESTÁ na view. `information_schema.columns` não o
   devolve, então `app.consulta.campos.campos_da_camada` não o vê, `outFields=*` não o pede e a lista
   branca do `where` não o aceita. Não existe parâmetro do cliente que o traga de volta.
2. O filtro é congelado dentro da definição da view (compilado por `app.consulta.where_ast`, com
   valor parametrizado literalizado por `cur.mogrify`). `where=1=1` do cliente vira `1=1 AND <filtro>`,
   porque o filtro está um nível abaixo, na relação consultada.
3. `somente_leitura` é recusado na porta única de escrita (`app.edicao.servico.exigir_camada_editavel`),
   então `applyEdits`, `/api/camadas/{id}/edicoes` e os anexos recusam com 403 pelo mesmo caminho.

Vista editável é criada `WITH CASCADED CHECK OPTION`: uma edição que empurraria a feição para fora do
filtro ou da extensão é recusada pelo banco, não aceita e escondida.
"""

from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Request
from pydantic import Field, field_validator

from app import db
from app.auth.sessao import Auth, autenticado
from app.catalogo.camada_esquema import COLUNAS_OCULTAS
from app.catalogo.comum import exigir_edicao, item_ou_404, jsonb, registrar_evento, uuid_ok
from app.catalogo.modelos import Modelo
from app.consulta import campos as campos_mod
from app.consulta.where_ast import ErroWhere, compilar_where
from app.erros import ErroAPI
from app.ingestao.inspecionar import tabela_de

router = APIRouter(tags=["vista-de-camada"])
CRIAR = {"x-auth": "S", "x-privilegio": "conteudo.publicar_camada"}
EDITAR = {"x-auth": "S", "x-privilegio": "proprio"}
LER = {"x-auth": "S/T", "x-privilegio": "proprio"}

NOME_RELACAO = re.compile(r"^[a-z][a-z0-9_]{1,62}$")
# colunas de controle que a view sempre carrega: sem elas a view não é atualizável e o FeatureServer perde
# o identificador de objeto. `tenant_id` entra porque é a coluna que a política de RLS lê (e `campos.py` já
# a esconde da saída); `geom` entra porque é a geometria.
CONTROLE = ("fid", "geom", "globalid", "versao", "tenant_id", "criado_em", "atualizado_em",
            "criado_por", "atualizado_por")
FILTRO_MAX = 4000


class VistaEntrada(Modelo):
    titulo: str = Field(min_length=1, max_length=250)
    filtro: str | None = Field(default=None, max_length=FILTRO_MAX)
    campos_ocultos: list[str] = Field(default_factory=list, max_length=500)
    somente_leitura: bool = True
    extent: list[float] | None = Field(default=None, min_length=4, max_length=4)
    estilo: dict | None = None
    popup: dict | None = None

    @field_validator("campos_ocultos")
    @classmethod
    def _ocultos_validos(cls, v):
        for nome in v:
            if not NOME_RELACAO.match(nome):
                raise ValueError(f"nome de campo fora do padrão de identificador: {nome!r}")
        return v

    @field_validator("extent")
    @classmethod
    def _extent_valido(cls, v):
        if v is not None and (v[0] >= v[2] or v[1] >= v[3]):
            raise ValueError("extent precisa ser [xmin, ymin, xmax, ymax] com xmin < xmax e ymin < ymax")
        return v


class VistaAlteracao(VistaEntrada):
    titulo: str | None = Field(default=None, max_length=250)


def _mae_ou_404(cur, camada_id: str) -> dict:
    """A camada-mãe tem de ser legível pelo ator (`item_ou_404` já passa pela RLS e pela visibilidade) e ser
    uma camada vetorial hospedada — vista de vista não existe neste item, e camada referenciada não tem
    tabela nossa para apoiar a view."""
    item = item_ou_404(cur, camada_id)
    if item["tipo"] != "camada_vetorial":
        raise ErroAPI(422, "tipo_incompativel", "só camada vetorial tem vista de camada")
    dados = item["dados"] or {}
    if dados.get("fonte") != "hospedada":
        raise ErroAPI(422, "camada_nao_hospedada", "só camada hospedada tem vista de camada")
    if not NOME_RELACAO.match(dados.get("schema", "")) or not NOME_RELACAO.match(dados.get("tabela", "")):
        raise ErroAPI(422, "camada_sem_tabela", "a camada-mãe não aponta para uma tabela válida")
    return item


def _colunas_visiveis(cur, dados_mae: dict, ocultos: list[str]) -> tuple[list[str], list[dict]]:
    """(colunas da view, campos de atributo visíveis). Ocultar coluna de controle é recusado: sem `fid` não
    há identificador de objeto, sem `tenant_id` não há RLS — esconder isso não é opção de produto, é defeito."""
    meta = campos_mod.campos_da_camada(cur, dados_mae["schema"], dados_mae["tabela"])
    existentes = {c["nome"] for c in meta} | {"geom", "tenant_id"}
    for nome in ocultos:
        if nome not in existentes:
            raise ErroAPI(422, "campo_inexistente", f"a camada-mãe não tem o campo {nome!r}", {"campo": nome})
        if nome in COLUNAS_OCULTAS or nome in CONTROLE:
            raise ErroAPI(422, "campo_de_controle",
                          f"{nome!r} é coluna de controle e não pode ser ocultada", {"campo": nome})
    ocultos_s = set(ocultos)
    atributos = [c for c in meta if c["nome"] not in CONTROLE and c["nome"] not in ocultos_s]
    colunas = list(CONTROLE) + [c["nome"] for c in atributos]
    return colunas, atributos


def _sql_filtro(cur, dados_mae: dict, filtro: str | None, extent: list[float] | None) -> str:
    """Cláusula WHERE congelada na definição da view. O texto do filtro passa por `where_ast` (lista branca
    de coluna vinda de `information_schema`, valor sempre parametrizado); `cur.mogrify` literaliza os
    parâmetros com as regras do psycopg2, porque uma definição de view não guarda parâmetro."""
    partes = []
    if filtro:
        meta = campos_mod.campos_da_camada(cur, dados_mae["schema"], dados_mae["tabela"])
        try:
            compilado = compilar_where(filtro, campos_mod.lista_branca(meta))
        except ErroWhere as e:
            raise ErroAPI(422, "filtro_invalido", f"filtro recusado: {e.args[1] if len(e.args) > 1 else e}",
                          {"filtro": filtro}) from e
        partes.append("(" + cur.mogrify(compilado.sql, compilado.params).decode() + ")")
    if extent:
        srid = int(dados_mae["srid"])
        envelope = cur.mogrify(
            "ST_Intersects(\"geom\", ST_MakeEnvelope(%s, %s, %s, %s, %s))",
            (extent[0], extent[1], extent[2], extent[3], srid),
        ).decode()
        partes.append(envelope)
    return " AND ".join(partes) if partes else "true"


def _criar_view(cur, schema: str, nome: str, dados_mae: dict, colunas: list[str], onde: str,
                somente_leitura: bool) -> None:
    lista = ", ".join(f'"{c}"' for c in colunas)
    checagem = "" if somente_leitura else " WITH CASCADED CHECK OPTION"
    cur.execute(f'DROP VIEW IF EXISTS "{schema}"."{nome}"')
    cur.execute(  # noqa: S608 — schema/tabela vêm de plat.item; colunas e filtro passaram por lista branca
        f'CREATE VIEW "{schema}"."{nome}" WITH (security_invoker = true) AS '
        f'SELECT {lista} FROM "{dados_mae["schema"]}"."{dados_mae["tabela"]}" WHERE {onde}{checagem}'
    )
    cur.execute(f'GRANT SELECT ON "{schema}"."{nome}" TO plat_leitor')


def _dados_da_vista(camada_id: str, dados_mae: dict, nome: str, corpo: VistaEntrada,
                    atributos: list[dict]) -> dict:
    return {
        "camada_id": str(camada_id),
        "schema": dados_mae["schema"],
        "tabela": nome,
        "geometria": dados_mae["geometria"],
        "srid": int(dados_mae["srid"]),
        "fonte": "hospedada",
        "filtro": corpo.filtro or None,
        "campos_ocultos": list(corpo.campos_ocultos),
        "somente_leitura": bool(corpo.somente_leitura),
        "extent": list(corpo.extent) if corpo.extent else None,
        "campos": [{"nome": c["nome"], "tipo": c["tipo_pg"]} for c in atributos],
        "edicao": {"habilitada": not corpo.somente_leitura},
        "estilo": corpo.estilo,
        "popup": corpo.popup,
        "procedencia": {
            "fonte": "vista de camada (L5-32)",
            "gerador": "plat vista_camada v1",
            "metodo": "view PostgreSQL com security_invoker sobre a camada-mãe",
            "limites": ["a vista mostra o que a camada-mãe tem no instante da consulta; não é cópia"],
        },
    }


@router.post("/api/camadas/{camada_id}/vistas", status_code=201, openapi_extra=CRIAR)
def criar(camada_id: str, corpo: VistaEntrada, request: Request,
          auth: Auth = autenticado("conteudo.publicar_camada")):
    """Cria a vista da camada-mãe: view no schema do inquilino + item `vista_de_camada` no catálogo +
    relação `vista_de_camada` (já declarada em 011_catalogo.sql com `apaga_junto`, o que resolve o órfão
    quando a camada-mãe é apagada)."""
    from app.catalogo import relacoes  # importação local: relacoes importa comum, que importa este módulo não

    camada_id = uuid_ok(camada_id)
    vista_id = str(uuid.uuid4())
    nome = tabela_de(vista_id)
    with db.db(auth.contexto()) as cur:
        mae = _mae_ou_404(cur, camada_id)
        dados_mae = mae["dados"]
        colunas, atributos = _colunas_visiveis(cur, dados_mae, corpo.campos_ocultos)
        onde = _sql_filtro(cur, dados_mae, corpo.filtro, corpo.extent)
        _criar_view(cur, dados_mae["schema"], nome, dados_mae, colunas, onde, corpo.somente_leitura)
        dados = _dados_da_vista(camada_id, dados_mae, nome, corpo, atributos)
        cur.execute(
            "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, criado_por, modificado_por) "
            "VALUES (%s::uuid, %s, 'vista_de_camada', %s, %s, %s, %s, %s)",
            (vista_id, auth.tenant_id, corpo.titulo[:250], auth.usuario_id, jsonb(dados),
             auth.usuario_id, auth.usuario_id),
        )
        relacoes.sincronizar(cur, auth.tenant_id, vista_id, relacoes.extrair("vista_de_camada", dados))
        registrar_evento(cur, request, "camadas/criar_vista", "item", vista_id,
                         {"camada_id": camada_id, "campos_ocultos": len(corpo.campos_ocultos),
                          "com_filtro": bool(corpo.filtro), "somente_leitura": bool(corpo.somente_leitura)})
    return {"item_id": vista_id, "camada_id": camada_id, "schema": dados["schema"], "tabela": nome,
            "campos_visiveis": [c["nome"] for c in atributos],
            "campos_ocultos": list(corpo.campos_ocultos), "somente_leitura": bool(corpo.somente_leitura)}


def _vista_ou_404(cur, vista_id: str, para_editar: bool = False) -> dict:
    item = exigir_edicao(cur, vista_id) if para_editar else item_ou_404(cur, vista_id)
    if item["tipo"] != "vista_de_camada":
        raise ErroAPI(404, "item_inexistente", "item inexistente")
    return item


@router.get("/api/vistas/{vista_id}", openapi_extra=LER)
def definicao(vista_id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Definição da vista mais os campos que ela publica, lidos da PRÓPRIA view (não da camada-mãe): é a
    mesma fonte que o FeatureServer usa, então o que está aqui é o que vaza — nada mais."""
    with db.db(auth.contexto()) as cur:
        item = _vista_ou_404(cur, vista_id)
        d = item["dados"]
        campos = campos_mod.campos_da_camada(cur, d["schema"], d["tabela"])
        return {
            "item_id": str(item["id"]), "camada_id": d["camada_id"], "titulo": item["titulo"],
            "filtro": d.get("filtro"), "campos_ocultos": d.get("campos_ocultos") or [],
            "somente_leitura": bool(d.get("somente_leitura", True)), "extent": d.get("extent"),
            "estilo": d.get("estilo"), "popup": d.get("popup"),
            "campos": [{"nome": c["nome"], "tipo": c["tipo_esri"]} for c in campos if c["nome"] != "geom"],
        }


@router.put("/api/vistas/{vista_id}", openapi_extra=EDITAR)
def alterar(vista_id: str, corpo: VistaAlteracao, request: Request,
            auth: Auth = autenticado("conteudo.publicar_camada")):
    """Refaz a view com a definição nova. A view é recriada por `CREATE VIEW` depois de um `DROP VIEW`, na
    mesma transação: ou a definição nova vale inteira, ou nada muda."""
    vista_id = uuid_ok(vista_id)
    with db.db(auth.contexto()) as cur:
        item = _vista_ou_404(cur, vista_id, para_editar=True)
        antigo = item["dados"]
        mae = _mae_ou_404(cur, antigo["camada_id"])
        dados_mae = mae["dados"]
        colunas, atributos = _colunas_visiveis(cur, dados_mae, corpo.campos_ocultos)
        onde = _sql_filtro(cur, dados_mae, corpo.filtro, corpo.extent)
        nome = antigo["tabela"]
        _criar_view(cur, dados_mae["schema"], nome, dados_mae, colunas, onde, corpo.somente_leitura)
        dados = _dados_da_vista(antigo["camada_id"], dados_mae, nome, corpo, atributos)
        titulo = corpo.titulo or item["titulo"]
        cur.execute(
            "UPDATE plat.item SET titulo = %s, dados = %s, modificado_por = %s, modificado_em = now() "
            "WHERE id = %s::uuid",
            (titulo[:250], jsonb(dados), auth.usuario_id, vista_id),
        )
        registrar_evento(cur, request, "camadas/alterar_vista", "item", vista_id,
                         {"campos_ocultos": len(corpo.campos_ocultos), "com_filtro": bool(corpo.filtro),
                          "somente_leitura": bool(corpo.somente_leitura)})
    return {"item_id": vista_id, "campos_visiveis": [c["nome"] for c in atributos],
            "campos_ocultos": list(corpo.campos_ocultos), "somente_leitura": bool(corpo.somente_leitura)}
