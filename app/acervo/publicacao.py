"""Leitura das camadas publicadas sem cópia (item L6-01-b-view-so-leitura; migração
20260906T15521aa_acervo_publicacao.sql; publicador `scripts/acervo_publicar.py`).

Cada camada exposta do registro (`plat.acervo_camada`) vira uma view em `plat_acervo`, com a lista branca de
colunas e o porteiro `plat.acervo_pode_ler('<camada>')` no WHERE. Estas rotas são a porta HTTP dessas views:

  GET    /api/acervo/camadas                        lista o que está publicado e o que este inquilino assina
  POST   /api/acervo/camadas/{camada}/assinatura    o inquilino passa a poder ler a camada
  DELETE /api/acervo/camadas/{camada}/assinatura    o inquilino deixa de poder ler
  GET    /api/acervo/camadas/{camada}/feicoes       GeoJSON por caixa envolvente
  GET    /api/acervo/camadas/{camada}/tiles/{z}/{x}/{y}.mvt   tile vetorial da MESMA view

O caminho usa `view_nome` (minúsculo, [a-z0-9_]) e não o `acervo_camada_id` (que tem '/' e '.'). A tradução
de um para o outro é uma consulta a `plat.acervo_publicacao`, nunca uma montagem de string.

Só leitura, e a recusa não é da aplicação: a view NÃO tem GRANT de INSERT/UPDATE/DELETE para `plat_app`, e a
tabela de origem em `public` não tem GRANT nenhum para `plat_app` (as duas provas negativas estão em
tests/api/test_acervo_publicacao.py, feitas com a role da aplicação, não com postgres). Por isso não existe
rota de escrita aqui: qualquer verbo de escrita nestes caminhos devolve 405 do próprio FastAPI.

Sem assinatura o resultado é 403 na API e ZERO LINHA na view — os dois, não um ou outro. O 403 é conveniência
de quem chama; a garantia é a view.
"""

import io
import json
import re
import zipfile
from datetime import date, datetime, timezone

from fastapi import APIRouter, Path, Query, Request, Response

from app import db
from app.acervo.licenca import ficha_licenca
from app.acervo.modelos import (
    AcervoAssinaturaEntrada,
    AcervoAssinaturaSaida,
    AcervoCamadaPagina,
    AcervoFeicoes,
    AcervoUsoDia,
    AcervoUsoMensal,
)
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import registrar_evento
from app.erros import ErroAPI
from app.settings import settings

router = APIRouter(tags=["acervo"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
ASSINAR = {"x-auth": "S/T", "x-privilegio": "conteudo.registrar_fonte"}
LIMITE_MAX = 5000
_NOME_VIEW = re.compile(r"^[a-z0-9_]{1,63}$")


def _schema_views() -> str:
    """`plat_acervo` em produção; `<schema>_acervo` em homologação e nas bases por trilha (a mesma regra que
    app/schema_ambiente.py aplica ao texto das consultas)."""
    return f"{settings.PLAT_SCHEMA}_acervo"


def _publicacao(cur, camada: str) -> dict:
    """Linha de plat.acervo_publicacao pelo nome da view. 404 quando não existe — a API não distingue
    'camada inexistente' de 'camada não publicada': quem não pode ver não recebe confirmação de existência."""
    if not _NOME_VIEW.match(camada):
        raise ErroAPI(404, "camada_inexistente", "camada do acervo inexistente")
    cur.execute(
        "SELECT p.acervo_camada_id, p.view_nome, p.schema_origem, p.tabela_origem, p.coluna_geom, p.srid, "
        "p.colunas, c.fonte_id, c.linhas_exatas "
        "FROM plat.acervo_publicacao p JOIN plat.acervo_camada c USING (acervo_camada_id) "
        "WHERE p.view_nome = %s",
        (camada,),
    )
    linha = cur.fetchone()
    if linha is None:
        raise ErroAPI(404, "camada_inexistente", "camada do acervo inexistente")
    return linha


def _exigir_assinatura(cur, pub: dict) -> None:
    cur.execute("SELECT plat.acervo_pode_ler(%s) AS pode", (pub["acervo_camada_id"],))
    if not cur.fetchone()["pode"]:
        raise ErroAPI(
            403,
            "sem_assinatura",
            "o inquilino não assina esta camada do acervo",
            {"camada": pub["view_nome"]},
        )


def _registrar_uso(cur, tenant_id: int, acervo_camada_id: str, feicoes: int) -> None:
    """Item L6-01-e: uma leitura = +1 consulta e +N feições servidas, por inquilino, camada e DIA. Roda na
    MESMA transação da leitura (commit junto): não existe leitura contada sem ter acontecido, nem leitura
    feita sem contagem. UPSERT pela chave (tenant, camada, dia) — concorrência de duas leituras no mesmo
    dia soma, nunca perde."""
    cur.execute(
        "INSERT INTO plat.acervo_uso(tenant_id, acervo_camada_id, dia, consultas, feicoes) "
        "VALUES (%s, %s, current_date, 1, %s) "
        "ON CONFLICT (tenant_id, acervo_camada_id, dia) DO UPDATE SET "
        "consultas = plat.acervo_uso.consultas + 1, "
        "feicoes = plat.acervo_uso.feicoes + EXCLUDED.feicoes",
        (tenant_id, acervo_camada_id, feicoes),
    )


@router.get("/api/acervo/camadas", response_model=AcervoCamadaPagina, openapi_extra=LER)
def listar_camadas(auth: Auth = autenticado(escopo_token="catalogo:ler")):
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "SELECT p.view_nome, p.acervo_camada_id, c.fonte_id, p.schema_origem, p.tabela_origem, "
            "p.coluna_geom, p.srid, p.colunas, c.linhas_exatas, c.tipo_geom, "
            "(a.tenant_id IS NOT NULL) AS assinada "
            "FROM plat.acervo_publicacao p "
            "JOIN plat.acervo_camada c USING (acervo_camada_id) "
            "LEFT JOIN plat.acervo_assinatura a ON a.acervo_camada_id = p.acervo_camada_id "
            "ORDER BY p.view_nome"
        )
        linhas = [dict(li) for li in cur.fetchall()]
        # item L6-01-e: o texto da licença que a tela mostra é o MESMO que o aceite grava (app/acervo/
        # licenca.py é a única montadora); sem licença curada os campos ficam None e a assinatura recusa.
        for li in linhas:
            ficha = ficha_licenca(cur, li["fonte_id"])
            li.update(ficha or {"licenca_tipo": None, "licenca_texto": None,
                                "licenca_url": None, "licenca_sha256": None})
    return {"total": len(linhas), "camadas": linhas}


@router.post(
    "/api/acervo/camadas/{camada}/assinatura",
    response_model=AcervoAssinaturaSaida,
    status_code=201,
    openapi_extra=ASSINAR,
)
def assinar(camada: str, request: Request, corpo: AcervoAssinaturaEntrada,
            auth: Auth = autenticado("conteudo.registrar_fonte")):
    """Item L6-01-e: assinar exige o clique no texto da licença, gravado. O clique chega como
    `aceite_licenca=true` + o sha256 do texto que a tela mostrou; o servidor grava QUEM (assinado_por),
    QUANDO (assinado_em) e O TEXTO aceito na hora (licenca_texto, cópia byte a byte, não referência).
    Sem aceite ou com sha defasado nada é gravado — e a recusa acontece ANTES do INSERT."""
    ctx = auth.contexto()
    with db.db(ctx) as cur:
        pub = _publicacao(cur, camada)
        ficha = ficha_licenca(cur, pub["fonte_id"])
        if ficha is None:
            raise ErroAPI(
                409,
                "sem_licenca",
                "a fonte desta camada não tem licença curada; sem licença escrita a camada não circula",
                {"camada": pub["view_nome"], "fonte_id": pub["fonte_id"]},
            )
        if not corpo.aceite_licenca:
            raise ErroAPI(
                409,
                "aceite_exigido",
                "assinar exige o aceite do texto da licença "
                '(corpo {"aceite_licenca": true, "licenca_sha256": "<sha exibido>"})',
                {"camada": pub["view_nome"]},
            )
        if corpo.licenca_sha256 != ficha["licenca_sha256"]:
            raise ErroAPI(
                409,
                "licenca_mudou",
                "o texto da licença não é o que estava na tela; releia o texto atual e confirme de novo",
                {"camada": pub["view_nome"], "licenca_sha256": ficha["licenca_sha256"]},
            )
        cur.execute(
            "INSERT INTO plat.acervo_assinatura(tenant_id, acervo_camada_id, assinado_por, "
            "  licenca_tipo, licenca_texto, licenca_url, licenca_sha256) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (tenant_id, acervo_camada_id) DO NOTHING "
            "RETURNING assinado_em",
            (auth.tenant_id, pub["acervo_camada_id"], auth.usuario_id,
             ficha["licenca_tipo"], ficha["licenca_texto"], ficha["licenca_url"], ficha["licenca_sha256"]),
        )
        gravada = cur.fetchone()
        if gravada is None:
            # já assinada com o texto atual: idempotente, só relê o carimbo para a resposta
            cur.execute(
                "SELECT assinado_em FROM plat.acervo_assinatura "
                "WHERE tenant_id = %s AND acervo_camada_id = %s",
                (auth.tenant_id, pub["acervo_camada_id"]),
            )
            gravada = cur.fetchone()
        registrar_evento(cur, request, "acervo/assinar", "acervo_camada", None,
                         {"camada": camada, "acervo_camada_id": pub["acervo_camada_id"],
                          "licenca_tipo": ficha["licenca_tipo"], "licenca_sha256": ficha["licenca_sha256"]})
    return {
        "camada": camada,
        "assinada": True,
        "licenca_tipo": ficha["licenca_tipo"],
        "licenca_sha256": ficha["licenca_sha256"],
        "assinado_em": gravada["assinado_em"].isoformat(),
    }


@router.delete("/api/acervo/camadas/{camada}/assinatura", openapi_extra=ASSINAR)
def cancelar_assinatura(camada: str, request: Request, auth: Auth = autenticado("conteudo.registrar_fonte")):
    ctx = auth.contexto()
    with db.db(ctx) as cur:
        pub = _publicacao(cur, camada)
        cur.execute(
            "DELETE FROM plat.acervo_assinatura WHERE tenant_id = %s AND acervo_camada_id = %s",
            (auth.tenant_id, pub["acervo_camada_id"]),
        )
        registrar_evento(cur, request, "acervo/cancelar", "acervo_camada", None,
                         {"camada": camada, "acervo_camada_id": pub["acervo_camada_id"]})
    return {"camada": camada, "assinada": False}


def _caixa(bbox: str | None) -> tuple[float, float, float, float] | None:
    if not bbox:
        return None
    partes = bbox.split(",")
    if len(partes) != 4:
        raise ErroAPI(422, "bbox_invalida", "bbox precisa ser 'oeste,sul,leste,norte' em graus")
    try:
        oeste, sul, leste, norte = (float(p) for p in partes)
    except ValueError:
        raise ErroAPI(422, "bbox_invalida", "bbox precisa ser 'oeste,sul,leste,norte' em graus") from None
    if not (oeste < leste and sul < norte):
        raise ErroAPI(422, "bbox_invalida", "bbox precisa ter oeste < leste e sul < norte")
    return oeste, sul, leste, norte


def _buscar_linhas(cur, pub: dict, caixa: tuple[float, float, float, float] | None,
                   limite: int) -> list[dict]:
    """Linhas da view publicada no recorte pedido, com a geometria em GeoJSON. Consulta única de
    `feicoes` (resposta direta) e `exportar` (pacote .zip): os dois servem exatamente as mesmas feições
    para os mesmos parâmetros. Identificadores vêm do REGISTRO (validados por _NOME_VIEW e pela lista de
    colunas da view), nunca do chamador; ainda assim vão citados por _ident, que é a citação do próprio
    servidor."""
    colunas = [c for c in pub["colunas"] if c != pub["coluna_geom"]]
    lista = ", ".join(_ident(c) for c in colunas)
    geom = _ident(pub["coluna_geom"])
    onde, params = "true", []
    if caixa:
        onde = f"{geom} && ST_MakeEnvelope(%s, %s, %s, %s, 4326)"
        params = list(caixa)
    sql = (
        f"SELECT {lista}, ST_AsGeoJSON({geom})::json AS geometria "
        f'FROM {_ident(_schema_views())}.{_ident(pub["view_nome"])} WHERE {onde} LIMIT %s'
    )
    cur.execute(sql, [*params, limite])
    return cur.fetchall()


def _colecao_geojson(camada: str, linhas: list[dict]) -> dict:
    """FeatureCollection das linhas lidas da view — a mesma montagem para a resposta de `feicoes` e para
    o arquivo .geojson do pacote de exportação."""
    feats = []
    for li in linhas:
        g = li.pop("geometria")
        feats.append({"type": "Feature", "geometry": g, "properties": {k: _json_ok(v) for k, v in li.items()}})
    return {"type": "FeatureCollection", "camada": camada, "total": len(feats), "features": feats}


@router.get("/api/acervo/camadas/{camada}/feicoes", response_model=AcervoFeicoes, openapi_extra=LER)
def feicoes(
    camada: str,
    bbox: str | None = Query(default=None, description="oeste,sul,leste,norte em graus (EPSG:4326)"),
    limite: int = Query(default=500, ge=1, le=LIMITE_MAX),
    auth: Auth = autenticado(escopo_token="catalogo:ler"),
):
    with db.db(auth.contexto()) as cur:
        pub = _publicacao(cur, camada)
        _exigir_assinatura(cur, pub)
        linhas = _buscar_linhas(cur, pub, _caixa(bbox), limite)
        _registrar_uso(cur, auth.tenant_id, pub["acervo_camada_id"], len(linhas))
    return _colecao_geojson(camada, linhas)


@router.get("/api/acervo/camadas/{camada}/tiles/{z}/{x}/{y}.mvt", openapi_extra=LER)
def tile(
    camada: str,
    z: int = Path(ge=0, le=22),
    x: int = Path(ge=0),
    y: int = Path(ge=0),
    auth: Auth = autenticado(escopo_token="catalogo:ler"),
):
    """Tile vetorial (MVT) da MESMA view — é este o SQL que o Martin publicaria como função. Sem assinatura,
    403; e mesmo que alguém chegue ao SQL por fora, a view devolve zero feição (o porteiro está nela)."""
    limite = 1 << z
    if x >= limite or y >= limite:
        raise ErroAPI(422, "tile_invalido", f"x e y precisam ser menores que {limite} no zoom {z}")
    with db.db(auth.contexto()) as cur:
        pub = _publicacao(cur, camada)
        _exigir_assinatura(cur, pub)
        geom = _ident(pub["coluna_geom"])
        alvo = f'{_ident(_schema_views())}.{_ident(pub["view_nome"])}'
        # o recorte acontece em 4326 (ST_Transform da CAIXA, não da coluna): assim o índice GiST da tabela
        # original é usado e só as feições que sobram são reprojetadas. Transformar a coluna no WHERE varreria
        # as 7,36 mi de linhas e estoura em geometria com coordenada inválida (medido: "transform: Invalid
        # coordinate (2049)" no CAR nacional). MATERIALIZED porque o recorte alimenta dois consumidores: o
        # MVT e a contagem de feições servidas do registro de uso (item L6-01-e).
        cur.execute(
            f"WITH caixa AS (SELECT ST_TileEnvelope(%s, %s, %s) AS env), "  # noqa: S608 — identificadores citados
            f"recorte AS MATERIALIZED (SELECT ST_AsMVTGeom(ST_Transform(ST_MakeValid(t.{geom}), 3857), "
            f"  c.env, 4096, 64, true) AS geom FROM {alvo} t, caixa c "
            f"  WHERE t.{geom} && ST_Transform(c.env, 4326)), "
            f"pacote AS (SELECT ST_AsMVT(recorte, %s, 4096, 'geom') AS mvt FROM recorte "
            f"  WHERE geom IS NOT NULL) "
            f"SELECT (SELECT mvt FROM pacote) AS mvt, "
            f"  (SELECT count(*) FROM recorte WHERE geom IS NOT NULL) AS n",
            (z, x, y, camada),
        )
        saida = cur.fetchone()
        _registrar_uso(cur, auth.tenant_id, pub["acervo_camada_id"], saida["n"])
    return Response(content=bytes(saida["mvt"] or b""), media_type="application/vnd.mapbox-vector-tile")


@router.get("/api/acervo/camadas/{camada}/exportar", openapi_extra=LER)
def exportar(
    camada: str,
    request: Request,
    bbox: str | None = Query(default=None, description="oeste,sul,leste,norte em graus (EPSG:4326)"),
    limite: int = Query(default=LIMITE_MAX, ge=1, le=LIMITE_MAX),
    auth: Auth = autenticado(escopo_token="catalogo:ler"),
):
    """Pacote .zip da camada (item L6-01-e): `<camada>.geojson` com as feições do recorte e `LICENCA.txt`
    com o aviso da licença — tipo, termo verificado, trecho literal, atribuição exigida e obrigações (ODbL
    e CC-BY-SA carregam atribuição E share-alike). O texto é o ATUAL da fonte, com o registro do aceite do
    inquilino anexado; se a licença mudou depois do aceite, o arquivo diz isso em linha própria. A
    exportação conta no registro de uso e gera evento `acervo/exportar` (quem, quando, quantas feições)."""
    ctx = auth.contexto()
    with db.db(ctx) as cur:
        pub = _publicacao(cur, camada)
        _exigir_assinatura(cur, pub)
        linhas = _buscar_linhas(cur, pub, _caixa(bbox), limite)
        ficha = ficha_licenca(cur, pub["fonte_id"])
        if ficha is None:
            # não deveria acontecer (sem licença a assinatura teria sido recusada), mas a exportação é a
            # última linha de defesa: pacote sem aviso de licença NUNCA sai.
            raise ErroAPI(
                409,
                "sem_licenca",
                "a fonte desta camada não tem licença curada; o pacote não sai sem o aviso da licença",
                {"camada": pub["view_nome"], "fonte_id": pub["fonte_id"]},
            )
        cur.execute(
            "SELECT assinado_em, licenca_tipo, licenca_sha256 FROM plat.acervo_assinatura "
            "WHERE tenant_id = %s AND acervo_camada_id = %s",
            (auth.tenant_id, pub["acervo_camada_id"]),
        )
        aceite = cur.fetchone()
        cur.execute("SELECT slug FROM plat.tenant WHERE id = %s", (auth.tenant_id,))
        inquilino = cur.fetchone()["slug"]
        _registrar_uso(cur, auth.tenant_id, pub["acervo_camada_id"], len(linhas))
        registrar_evento(cur, request, "acervo/exportar", "acervo_camada", None,
                         {"camada": camada, "acervo_camada_id": pub["acervo_camada_id"],
                          "feicoes": len(linhas), "licenca_tipo": ficha["licenca_tipo"]})
    feats = _colecao_geojson(camada, [dict(li) for li in linhas])
    geojson = json.dumps(feats, ensure_ascii=False)
    truncado = feats["total"] == limite
    aviso = ficha["licenca_texto"] + (
        "\n--\n\n"
        f"Pacote exportado da plataforma em {datetime.now(timezone.utc).isoformat()}.\n"
        f"Camada: {pub['view_nome']} ({pub['acervo_camada_id']}).\n"
        f"Inquilino: {inquilino}. Assinatura registrada em {aceite['assinado_em'].isoformat()} "
        f"(licença {aceite['licenca_tipo']}, sha256 do texto aceito {aceite['licenca_sha256']}).\n"
    )
    if aceite["licenca_sha256"] != ficha["licenca_sha256"]:
        aviso += "O texto da licença mudou depois da assinatura; este pacote carrega o texto ATUAL.\n"
    aviso += f"Feições neste pacote: {feats['total']}.\n"
    if truncado:
        aviso += f"O pacote foi truncado no limite de {limite} feições; refine a caixa envolvente.\n"
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w", zipfile.ZIP_DEFLATED) as pacote:
        pacote.writestr("LICENCA.txt", aviso)
        pacote.writestr(f"{pub['view_nome']}.geojson", geojson)
    nome = f"{pub['view_nome']}.zip"
    return Response(
        content=memoria.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


@router.get("/api/acervo/uso", response_model=AcervoUsoDia, openapi_extra=LER)
def uso_do_dia(
    dia: date | None = Query(default=None, description="dia no formato AAAA-MM-DD; padrão é hoje"),
    auth: Auth = autenticado(escopo_token="catalogo:ler"),
):
    """Registro de leitura do acervo do inquilino num dia (item L6-01-e): consultas e feições servidas por
    camada. A RLS de plat.acervo_uso recorta pelo inquilino da sessão — ninguém lê o uso de outro."""
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "SELECT u.acervo_camada_id, p.view_nome, u.consultas, u.feicoes "
            "FROM plat.acervo_uso u "
            "LEFT JOIN plat.acervo_publicacao p ON p.acervo_camada_id = u.acervo_camada_id "
            "WHERE u.dia = coalesce(%s, current_date) ORDER BY u.consultas DESC, u.acervo_camada_id",
            (dia,),
        )
        linhas = cur.fetchall()
    camadas = [
        {"view_nome": li["view_nome"], "acervo_camada_id": li["acervo_camada_id"],
         "consultas": li["consultas"], "feicoes": li["feicoes"]}
        for li in linhas
    ]
    return {
        "dia": (dia or date.today()).isoformat(),
        "total_consultas": sum(c["consultas"] for c in camadas),
        "total_feicoes": sum(c["feicoes"] for c in camadas),
        "camadas": camadas,
    }


@router.get("/api/acervo/uso/mensal", response_model=AcervoUsoMensal, openapi_extra=LER)
def uso_mensal(
    ano: int | None = Query(default=None, ge=2000, le=2100),
    mes: int | None = Query(default=None, ge=1, le=12),
    auth: Auth = autenticado(escopo_token="catalogo:ler"),
):
    """Relatório mensal de uso do acervo pelo inquilino (item L6-01-e): consultas, feições servidas e em
    quantos dias do mês houve leitura, por camada. É a entrada do item L7-09 (cobrança/relatório)."""
    hoje = date.today()
    ano = ano or hoje.year
    mes = mes or hoje.month
    inicio = date(ano, mes, 1)
    fim = date(ano + (1 if mes == 12 else 0), 1 if mes == 12 else mes + 1, 1)
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "SELECT u.acervo_camada_id, p.view_nome, "
            "sum(u.consultas)::int AS consultas, sum(u.feicoes)::bigint AS feicoes, count(*)::int AS dias "
            "FROM plat.acervo_uso u "
            "LEFT JOIN plat.acervo_publicacao p ON p.acervo_camada_id = u.acervo_camada_id "
            "WHERE u.dia >= %s AND u.dia < %s "
            "GROUP BY u.acervo_camada_id, p.view_nome ORDER BY consultas DESC, u.acervo_camada_id",
            (inicio, fim),
        )
        linhas = cur.fetchall()
    camadas = [dict(li) for li in linhas]
    return {
        "ano": ano,
        "mes": mes,
        "total_consultas": sum(c["consultas"] for c in camadas),
        "total_feicoes": sum(c["feicoes"] for c in camadas),
        "camadas": camadas,
    }


def _ident(nome: str) -> str:
    """Citação de identificador sem depender de conexão aberta: só nomes que já passaram por validação
    chegam aqui (nome de view do registro, coluna da lista branca, schema montado de settings)."""
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$", nome):
        raise ErroAPI(500, "identificador_invalido", "identificador do registro fora do formato esperado")
    return '"' + nome + '"'


def _json_ok(valor):
    """datetime/date/Decimal do psycopg2 não são serializáveis por padrão; nada aqui inventa valor."""
    if valor is None or isinstance(valor, (str, int, float, bool, list, dict)):
        return valor
    try:
        json.dumps(valor)
        return valor
    except TypeError:
        return str(valor)
