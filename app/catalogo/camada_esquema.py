"""Construtor de camada por esquema (item `L5-31-construtor-de-camada-esquema`, linha L5 builder).

`POST /api/camadas/esquema` cria uma camada VAZIA a partir de uma lista de campos (a tela arrasta tipos de
campo para montar essa lista; este módulo só sabe da lista já montada — o arrasto em si é DOM puro, sem
chamada ao servidor por campo). Reaproveita, do L0-04-ingest-vetor, exatamente as duas peças que fazem uma
tabela de camada nascer igual à de uma importação: `plat.camada_schema_garantir` (cria/garante o schema
`d_<slug>` do inquilino) e `plat.camada_preparar` (colunas obrigatórias, RLS FORCE, índice espacial, gatilhos
de tenant/versão — a MESMA função que `app.ingestao.carregar` chama depois do `ogr2ogr`); e a normalização de
nome de campo de `app.ingestao.nomes.normalizar` (mesma regra de acento/palavra reservada/duplicata que a
ingestão já usa — é a fronteira que o adversário deste item ataca com 300 campos e nomes hostis).

`PUT /api/camadas/{id}/esquema` altera o esquema de uma camada já existente com um PLANO mostrado antes de
aplicar (`POST .../esquema/plano`, mesmo corpo, sem `aplicar`): adicionar campo e renomear alias sempre
aplicam; alargar (`mudar_tamanho` para cima, `mudar_tipo` para um tipo mais largo) aplica; qualquer mudança
que possa perder dado (reduzir tamanho, ou um `mudar_tipo` fora da lista de alargamentos seguros) só aplica
se a tabela estiver VAZIA — com dado, é recusada com mensagem, nunca aplicada calada (ADR 0005 seção 8 dá o
mesmo tratamento a nome de campo; aqui é o mesmo princípio para TIPO de campo).

`GET /api/camadas/{id}/campos` devolve os campos no formato `fields` de um FeatureServer Esri (name, type,
alias, length, nullable, defaultValue, domain) — o alias e o domínio vêm de `plat.camada_campo_meta` (o que o
PostgreSQL não guarda), o resto vem direto de `information_schema.columns` (o banco é a autoridade sobre
tipo/tamanho/obrigatoriedade reais, nunca uma cópia que pode desalinhar). O roteador de FeatureServer/OGC
completo é o item `L2-04-servicos-esri-ogc` (PARCIAL, branch própria, ainda não integrado a esta árvore): esta
rota é o contrato mínimo que ele consome quando integrar — o formato já é o dele, só falta o roteador de fora
montar o `/rest/services/.../FeatureServer` em volta dela."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import Field, field_validator

from app import db, limites
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import item_ou_404, jsonb, registrar_evento
from app.catalogo.modelos import Modelo
from app.erros import ErroAPI
from app.ingestao.inspecionar import tabela_de
from app.ingestao.nomes import normalizar, normalizar_titulo

router = APIRouter(tags=["camada-esquema"])
CRIAR = {"x-auth": "S", "x-privilegio": "conteudo.publicar_camada"}
EDITAR = {"x-auth": "S", "x-privilegio": "proprio"}
LER = {"x-auth": "S/T", "x-privilegio": "proprio"}

GEOMETRIAS = ("Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon", "Geometry")
# Só os tipos-alvo que app.ingestao.tipos_campo.MAPA produz (mesma paleta que a ingestão já usa; bytea fora —
# não é campo de atributo de camada, é o binário do arquivo de origem).
TIPOS_ACEITOS = ("text", "integer", "bigint", "double precision", "real", "boolean", "date", "time",
                 "timestamp with time zone")
CAMPOS_MAX = limites.INGESTAO_CAMPOS_MAX
NOME_ESQUEMA_TABELA = __import__("re").compile(r"^d_[a-z0-9_]{1,60}$")

# alargamento seguro: se o tipo NOVO está no conjunto do tipo ATUAL, a mudança nunca perde dado (widen-only).
# Fora disso é "destrutivo" — só aplica em tabela vazia. `text` não alarga para nada (qualquer texto pode
# falhar o parse do tipo de destino) e é o próprio caso do portão ("texto→inteiro com dado" recusado).
ALARGAMENTO_SEGURO: dict[str, set[str]] = {
    "integer": {"integer", "bigint", "double precision", "real", "text"},
    "bigint": {"bigint", "double precision", "text"},
    "real": {"real", "double precision", "text"},
    "double precision": {"double precision", "text"},
    "boolean": {"boolean", "text"},
    "date": {"date", "timestamp with time zone", "text"},
    "time": {"time", "text"},
    "timestamp with time zone": {"timestamp with time zone", "text"},
    "text": {"text"},
}

COLUNAS_OCULTAS = {"fid", "globalid", "versao", "tenant_id", "geom", "criado_em", "atualizado_em",
                   "criado_por", "atualizado_por"}

TIPO_ESRI = {
    "text": "esriFieldTypeString", "integer": "esriFieldTypeInteger", "bigint": "esriFieldTypeBigInteger",
    "double precision": "esriFieldTypeDouble", "real": "esriFieldTypeSingle", "boolean": "esriFieldTypeSmallInteger",
    "date": "esriFieldTypeDate", "time": "esriFieldTypeString", "timestamp with time zone": "esriFieldTypeDate",
    "character varying": "esriFieldTypeString",
}


class CampoEntrada(Modelo):
    nome: str = Field(min_length=1, max_length=250)
    tipo: str
    tamanho: int | None = Field(default=None, ge=1, le=10000)
    alias: str | None = Field(default=None, max_length=250)
    obrigatorio: bool = False
    padrao: str | None = Field(default=None, max_length=2000)
    dominio: list[dict] | None = Field(default=None, max_length=1000)
    indice: bool = False

    @field_validator("tipo")
    @classmethod
    def _tipo_valido(cls, v):
        if v not in TIPOS_ACEITOS:
            raise ValueError(f"tipo {v!r} não aceito; use um de {list(TIPOS_ACEITOS)}")
        return v

    @field_validator("dominio")
    @classmethod
    def _dominio_valido(cls, v):
        if v is None:
            return v
        for item in v:
            if not isinstance(item, dict) or "codigo" not in item or "rotulo" not in item:
                raise ValueError("cada valor de domínio precisa de 'codigo' e 'rotulo'")
        return v


class CamadaEsquemaEntrada(Modelo):
    titulo: str = Field(min_length=1, max_length=250)
    geometria: str
    srid: int = Field(ge=1, le=999999)
    campos: list[CampoEntrada] = Field(default_factory=list, max_length=CAMPOS_MAX)

    @field_validator("geometria")
    @classmethod
    def _geom_valida(cls, v):
        if v not in GEOMETRIAS:
            raise ValueError(f"geometria {v!r} inválida; use uma de {list(GEOMETRIAS)}")
        return v


class MudancaEntrada(Modelo):
    tipo: Literal["adicionar_campo", "renomear_alias", "mudar_tamanho", "mudar_tipo"]
    campo: str | None = None
    novo_campo: CampoEntrada | None = None
    novo_alias: str | None = Field(default=None, max_length=250)
    novo_tamanho: int | None = Field(default=None, ge=1, le=10000)
    novo_tipo: str | None = None

    @field_validator("novo_tipo")
    @classmethod
    def _novo_tipo_valido(cls, v):
        if v is not None and v not in TIPOS_ACEITOS:
            raise ValueError(f"tipo {v!r} não aceito; use um de {list(TIPOS_ACEITOS)}")
        return v


class PlanoEntrada(Modelo):
    mudancas: list[MudancaEntrada] = Field(default_factory=list, max_length=CAMPOS_MAX)


def _valor_padrao(tipo: str, padrao: str | None):
    """Converte o texto do formulário para o tipo Python que o psycopg2 sabe literalizar certo no DEFAULT
    (int sem aspas, bool TRUE/FALSE; texto/data/hora ficam string — o Postgres coage o literal não tipado
    para o tipo da coluna sozinho, igual a `DEFAULT '2024-01-01'` numa coluna date)."""
    if padrao is None or padrao == "":
        return None
    try:
        if tipo in ("integer", "bigint"):
            return int(padrao)
        if tipo in ("double precision", "real"):
            return float(padrao)
        if tipo == "boolean":
            return str(padrao).strip().lower() in ("1", "true", "t", "sim", "yes", "verdadeiro")
        return padrao
    except (ValueError, TypeError) as e:
        raise ErroAPI(422, "padrao_invalido", f"valor padrão {padrao!r} não é um {tipo} válido",
                      {"tipo": tipo, "padrao": padrao}) from e


def _coluna_sql(tipo: str, tamanho: int | None) -> str:
    if tipo == "text" and tamanho:
        return f"varchar({int(tamanho)})"
    return tipo


def _normalizar_campos(campos: list[CampoEntrada]) -> tuple[list[dict], list[dict]]:
    usados: set[str] = set()
    normalizados = []
    avisos = []
    for i, c in enumerate(campos):
        nome, motivo = normalizar(c.nome, usados, posicao=i)
        if motivo:
            avisos.append({"campo_original": c.nome, "campo": nome, "motivo": motivo})
        normalizados.append({
            "nome": nome, "origem": c.nome, "tipo": c.tipo, "tamanho": c.tamanho,
            "alias": normalizar_titulo(c.alias) if c.alias else normalizar_titulo(c.nome),
            "obrigatorio": c.obrigatorio, "padrao": c.padrao, "dominio": c.dominio, "indice": c.indice,
        })
    return normalizados, avisos


def _fields_de(cur, item: dict) -> list[dict]:
    schema, tabela = item["dados"]["schema"], item["dados"]["tabela"]
    cur.execute(
        "SELECT column_name, data_type, character_maximum_length, is_nullable, column_default "
        "FROM information_schema.columns WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position",
        (schema, tabela),
    )
    colunas = list(cur.fetchall())
    cur.execute(
        "SELECT coluna, alias, dominio, ordem, indice FROM plat.camada_campo_meta "
        "WHERE item_id = %s::uuid ORDER BY ordem, coluna", (item["id"],),
    )
    metas = {r["coluna"]: r for r in cur.fetchall()}
    campos = []
    for col in colunas:
        nome = col["column_name"]
        if nome in COLUNAS_OCULTAS:
            continue
        meta = metas.get(nome, {})
        campos.append({
            "name": nome,
            "type": TIPO_ESRI.get(col["data_type"], "esriFieldTypeString"),
            "sqlType": col["data_type"],
            "alias": meta.get("alias") or nome,
            "length": col["character_maximum_length"],
            "nullable": col["is_nullable"] == "YES",
            "defaultValue": col["column_default"],
            "domain": ({"type": "codedValue", "name": nome, "codedValues": meta["dominio"]}
                       if meta.get("dominio") else None),
            "indexed": bool(meta.get("indice")),
        })
    return campos


@router.post("/api/camadas/esquema", status_code=201, openapi_extra=CRIAR)
def criar(corpo: CamadaEsquemaEntrada, request: Request, auth: Auth = autenticado("conteudo.publicar_camada")):
    campos, avisos = _normalizar_campos(corpo.campos)
    item_id = str(uuid.uuid4())
    tabela = tabela_de(item_id)

    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT slug FROM plat.tenant WHERE id = %s", (auth.tenant_id,))
        slug = cur.fetchone()["slug"]
        schema = f"d_{slug}"
        if not NOME_ESQUEMA_TABELA.match(schema):
            raise ErroAPI(422, "slug_invalido", "slug de inquilino fora do padrão")

        cur.execute("SELECT plat.camada_schema_garantir(%s)", (slug,))

        colunas_ddl = ['fid bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY',
                       f'geom geometry({corpo.geometria}, {corpo.srid})']
        for c in campos:
            colunas_ddl.append(f'"{c["nome"]}" {_coluna_sql(c["tipo"], c["tamanho"])}')
        ddl = f'CREATE TABLE "{schema}"."{tabela}" (' + ", ".join(colunas_ddl) + ")"
        cur.execute(ddl)

        cur.execute("SELECT plat.camada_preparar(%s, %s, %s, %s, %s)",
                    (schema, tabela, corpo.srid, corpo.geometria, auth.usuario_id))

        for c in campos:
            if c["obrigatorio"]:
                cur.execute(f'ALTER TABLE "{schema}"."{tabela}" ALTER COLUMN "{c["nome"]}" SET NOT NULL')
            valor = _valor_padrao(c["tipo"], c["padrao"])
            if valor is not None:
                cur.execute(f'ALTER TABLE "{schema}"."{tabela}" ALTER COLUMN "{c["nome"]}" SET DEFAULT %s', (valor,))
            if c["indice"]:
                cur.execute(f'CREATE INDEX IF NOT EXISTS "ix_{tabela}_{c["nome"]}" '
                            f'ON "{schema}"."{tabela}" ("{c["nome"]}")')

        item_dados = {
            "schema": schema, "tabela": tabela, "geometria": corpo.geometria, "srid": corpo.srid,
            "campos": [{"nome": c["nome"], "tipo": c["tipo"], "alias": c["alias"]} for c in campos],
            "fonte": "hospedada",
            "procedencia": {
                "fonte": "construtor de camada por esquema", "url": None, "licenca": None, "data_do_dado": None,
                "data_de_acesso": None, "gerador": "plat camada_esquema v1", "sha256": None,
                "metodo": "arrasto de campos (L5-31)", "confianca": None, "limites": avisos,
            },
            "estatisticas": {"feicoes": 0, "extent_nativo": None, "por_campo": {}, "calculadas_em": None},
        }
        # o item precisa existir ANTES do camada_campo_meta: a FK composta (tenant_id, item_id) exige a
        # linha-pai já commitada dentro desta mesma transação, senão a inserção do metadado é recusada.
        cur.execute(
            "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, criado_por, modificado_por) "
            "VALUES (%s::uuid, %s, 'camada_vetorial', %s, %s, %s, %s, %s)",
            (item_id, auth.tenant_id, corpo.titulo[:250], auth.usuario_id, jsonb(item_dados),
             auth.usuario_id, auth.usuario_id),
        )

        for ordem, c in enumerate(campos):
            cur.execute(
                "INSERT INTO plat.camada_campo_meta(tenant_id, item_id, coluna, alias, dominio, ordem, indice) "
                "VALUES (%s, %s::uuid, %s, %s, %s, %s, %s)",
                (auth.tenant_id, item_id, c["nome"], c["alias"], jsonb(c["dominio"]) if c["dominio"] else None,
                 ordem, c["indice"]),
            )

        registrar_evento(cur, request, "camadas/criar_esquema", "item", item_id,
                          {"campos": len(campos), "geometria": corpo.geometria, "srid": corpo.srid})

    return {"item_id": item_id, "schema": schema, "tabela": tabela, "campos": len(campos), "avisos": avisos}


@router.get("/api/camadas/{item_id}/campos", openapi_extra=LER)
def campos(item_id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    with db.db(auth.contexto()) as cur:
        item = item_ou_404(cur, item_id)
        if item["tipo"] != "camada_vetorial":
            raise ErroAPI(422, "tipo_incompativel", "item não é uma camada vetorial")
        return {"fields": _fields_de(cur, item)}


def _coluna_info(cur, schema: str, tabela: str, coluna: str) -> dict | None:
    cur.execute(
        "SELECT column_name, data_type, character_maximum_length, is_nullable "
        "FROM information_schema.columns WHERE table_schema=%s AND table_name=%s AND column_name=%s",
        (schema, tabela, coluna),
    )
    return cur.fetchone()


def _avaliar_mudanca(cur, schema: str, tabela: str, m: MudancaEntrada) -> dict:
    base = {"tipo": m.tipo, "campo": m.campo}
    if m.tipo == "adicionar_campo":
        if m.novo_campo is None:
            return {**base, "aplicavel": False, "motivo": "novo_campo é obrigatório para adicionar_campo"}
        nome, motivo_nome = normalizar(m.novo_campo.nome, set())
        existe = _coluna_info(cur, schema, tabela, nome)
        if existe:
            return {**base, "aplicavel": False, "motivo": f"já existe uma coluna chamada {nome!r}"}
        return {**base, "aplicavel": True, "motivo": None, "coluna_normalizada": nome, "aviso_nome": motivo_nome}

    if m.campo is None:
        return {**base, "aplicavel": False, "motivo": "campo é obrigatório para esta mudança"}
    if m.campo in COLUNAS_OCULTAS:
        return {**base, "aplicavel": False, "motivo": "coluna de sistema; não é alterável pelo esquema"}
    col = _coluna_info(cur, schema, tabela, m.campo)
    if col is None:
        return {**base, "aplicavel": False, "motivo": f"coluna {m.campo!r} não existe nesta camada"}

    if m.tipo == "renomear_alias":
        return {**base, "aplicavel": True, "motivo": None}

    cur.execute(f'SELECT count(*) AS n FROM "{schema}"."{tabela}"')
    tem_dado = cur.fetchone()["n"] > 0

    if m.tipo == "mudar_tamanho":
        atual = col["character_maximum_length"]
        if m.novo_tamanho is None:
            return {**base, "aplicavel": True, "motivo": None}  # text ilimitado: sempre alarga
        if atual is not None and m.novo_tamanho < atual and tem_dado:
            return {**base, "aplicavel": False,
                    "motivo": f"reduzir o tamanho de {atual} para {m.novo_tamanho} pode truncar dado existente"}
        if atual is None and tem_dado:
            # coluna hoje é text (sem teto): o teto novo só é seguro se NENHUM valor já gravado for maior —
            # sem medir isso um "varchar(N)" pequeno truncaria dado que existe hoje, calado.
            cur.execute(f'SELECT max(length("{m.campo}")) AS maior FROM "{schema}"."{tabela}"')
            maior = cur.fetchone()["maior"] or 0
            if maior > m.novo_tamanho:
                return {**base, "aplicavel": False,
                        "motivo": f"o maior valor já gravado tem {maior} caracteres; "
                                  f"{m.novo_tamanho} truncaria dado existente"}
        return {**base, "aplicavel": True, "motivo": None}

    if m.tipo == "mudar_tipo":
        if m.novo_tipo is None:
            return {**base, "aplicavel": False, "motivo": "novo_tipo é obrigatório para mudar_tipo"}
        tipo_atual = "text" if col["data_type"] in ("character varying", "text") else col["data_type"]
        seguro = m.novo_tipo in ALARGAMENTO_SEGURO.get(tipo_atual, set())
        if seguro:
            return {**base, "aplicavel": True, "motivo": None}
        if tem_dado:
            return {**base, "aplicavel": False,
                    "motivo": f"mudança destrutiva ({tipo_atual} → {m.novo_tipo}) recusada: a camada tem dado"}
        return {**base, "aplicavel": True, "motivo": "destrutiva, mas aceita porque a camada está vazia"}

    return {**base, "aplicavel": False, "motivo": "tipo de mudança desconhecido"}


def _plano(cur, item: dict, entrada: PlanoEntrada) -> list[dict]:
    schema, tabela = item["dados"]["schema"], item["dados"]["tabela"]
    return [_avaliar_mudanca(cur, schema, tabela, m) for m in entrada.mudancas]


@router.post("/api/camadas/{item_id}/esquema/plano", openapi_extra=EDITAR)
def plano(item_id: str, corpo: PlanoEntrada, auth: Auth = autenticado("conteudo.publicar_camada")):
    with db.db(auth.contexto()) as cur:
        item = item_ou_404(cur, item_id)
        if item["tipo"] != "camada_vetorial":
            raise ErroAPI(422, "tipo_incompativel", "item não é uma camada vetorial")
        return {"plano": _plano(cur, item, corpo)}


@router.put("/api/camadas/{item_id}/esquema", openapi_extra=EDITAR)
def alterar(item_id: str, corpo: PlanoEntrada, request: Request,
            auth: Auth = autenticado("conteudo.publicar_camada")):
    with db.db(auth.contexto()) as cur:
        item = item_ou_404(cur, item_id)
        if item["tipo"] != "camada_vetorial":
            raise ErroAPI(422, "tipo_incompativel", "item não é uma camada vetorial")
        schema, tabela = item["dados"]["schema"], item["dados"]["tabela"]
        avaliacoes = _plano(cur, item, corpo)

        aplicadas, recusadas = [], []
        for m, av in zip(corpo.mudancas, avaliacoes, strict=True):
            if not av["aplicavel"]:
                recusadas.append(av)
                continue
            if m.tipo == "adicionar_campo":
                nome = av["coluna_normalizada"]
                nc = m.novo_campo
                col_sql = _coluna_sql(nc.tipo, nc.tamanho)
                valor = _valor_padrao(nc.tipo, nc.padrao)
                ddl = f'ALTER TABLE "{schema}"."{tabela}" ADD COLUMN "{nome}" {col_sql}'
                if valor is not None:
                    # DEFAULT dentro do próprio ADD COLUMN preenche as linhas existentes na mesma passada
                    # (Postgres >= 11 não reescreve a tabela para um default constante)
                    cur.execute(ddl + " DEFAULT %s", (valor,))
                else:
                    cur.execute(ddl)
                if nc.obrigatorio:
                    cur.execute(f'SELECT count(*) FILTER (WHERE "{nome}" IS NULL) AS n FROM "{schema}"."{tabela}"')
                    if cur.fetchone()["n"] == 0:
                        cur.execute(f'ALTER TABLE "{schema}"."{tabela}" ALTER COLUMN "{nome}" SET NOT NULL')
                    else:
                        av["aviso"] = "obrigatorio não aplicado: existe linha sem valor e sem padrão"
                if nc.indice:
                    cur.execute(f'CREATE INDEX IF NOT EXISTS "ix_{tabela}_{nome}" '
                                f'ON "{schema}"."{tabela}" ("{nome}")')
                cur.execute("SELECT coalesce(max(ordem), -1) + 1 AS n FROM plat.camada_campo_meta "
                            "WHERE item_id=%s::uuid", (item_id,))
                ordem = cur.fetchone()["n"]
                cur.execute(
                    "INSERT INTO plat.camada_campo_meta(tenant_id, item_id, coluna, alias, dominio, ordem, indice) "
                    "VALUES (%s, %s::uuid, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (item_id, coluna) DO UPDATE SET alias=EXCLUDED.alias, dominio=EXCLUDED.dominio, "
                    "indice=EXCLUDED.indice",
                    (auth.tenant_id, item_id, nome,
                     normalizar_titulo(m.novo_campo.alias) if m.novo_campo.alias else nome,
                     jsonb(m.novo_campo.dominio) if m.novo_campo.dominio else None, ordem, m.novo_campo.indice),
                )
            elif m.tipo == "renomear_alias":
                cur.execute(
                    "INSERT INTO plat.camada_campo_meta(tenant_id, item_id, coluna, alias, ordem) "
                    "VALUES (%s, %s::uuid, %s, %s, 0) "
                    "ON CONFLICT (item_id, coluna) DO UPDATE SET alias = EXCLUDED.alias",
                    (auth.tenant_id, item_id, m.campo, normalizar_titulo(m.novo_alias or m.campo)),
                )
            elif m.tipo == "mudar_tamanho":
                novo = f"varchar({m.novo_tamanho})" if m.novo_tamanho else "text"
                cur.execute(f'ALTER TABLE "{schema}"."{tabela}" ALTER COLUMN "{m.campo}" TYPE {novo}')
            elif m.tipo == "mudar_tipo":
                cur.execute(f'ALTER TABLE "{schema}"."{tabela}" ALTER COLUMN "{m.campo}" TYPE {m.novo_tipo} '
                            f'USING "{m.campo}"::{m.novo_tipo}')
            aplicadas.append(av)

        cur.execute("SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position", (schema, tabela))
        colunas_vivas = [r for r in cur.fetchall() if r["column_name"] not in COLUNAS_OCULTAS]
        cur.execute("SELECT coluna, alias FROM plat.camada_campo_meta WHERE item_id=%s::uuid", (item_id,))
        alias_por_coluna = {r["coluna"]: r["alias"] for r in cur.fetchall()}
        novos_campos = [{"nome": c["column_name"],
                          "tipo": "text" if c["data_type"] == "character varying" else c["data_type"],
                          "alias": alias_por_coluna.get(c["column_name"]) or c["column_name"]}
                        for c in colunas_vivas]
        dados = dict(item["dados"])
        dados["campos"] = novos_campos
        cur.execute("UPDATE plat.item SET dados = %s WHERE id = %s::uuid", (jsonb(dados), item_id))
        registrar_evento(cur, request, "camadas/alterar_esquema", "item", item_id,
                          {"aplicadas": len(aplicadas), "recusadas": len(recusadas)})

    return {"aplicadas": aplicadas, "recusadas": recusadas}
