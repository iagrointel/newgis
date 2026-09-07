"""Rotas do acervo da casa (item L6-01-a-procedencia-acervo, estendido pelos itens L6-01-d-ficha-fonte e
L6-01-f-lgpd; ADR ver laco/decomposicao/L3L6_CONCEITO.md B1/B3/B5).

`GET /api/acervo` lista por domínio e busca (nome/órgão); `GET /api/acervo/{fonte_id}` devolve a ficha completa de
procedência (licença, frescor, sha256, comando de reexecução, nº de tabelas, registros, endpoints confirmados e
vivos, completude x/10); as três leem só `plat.acervo_ficha` (migração 021) + `plat.acervo_endpoint` (migração
036) + `plat.acervo_lgpd` (migração 037), que já filtram `licenca IS NOT NULL` — regra D17, fonte sem licença
escrita nunca aparece, nem na lista nem na ficha (404, não distinguível de "não existe": a casa não confirma que
a fonte existe para quem não pode vê-la). `POST /api/acervo/{fonte_id}/adicionar` cria um item do catálogo tipo
`conexao` (protocolo `acervo`) que referencia a fonte por `fonte_id` em `dados.parametros` — nunca copia dado,
nunca escreve em `acervo.*` (a casa só lê o registro do acervo; quem grava lá são os scripts próprios:
registro.py/contagem2.py/frescor.py). Fonte marcada `risco_pii` em `plat.acervo_lgpd` (curadoria manual, nunca
automática — item L6-01-f) exige `{"confirma_risco_pii": true}` no corpo do POST; sem isso a rota recusa com 409
antes de criar qualquer item, e o evento fica registrado (ator + timestamp, via plat.evento_registrar)."""

import uuid

import psycopg2
from fastapi import APIRouter, Query, Request

from app import db
from app.acervo.modelos import AcervoAdicionarEntrada, AcervoDominio, AcervoFicha, AcervoPagina
from app.auth.comum import paginacao
from app.auth.sessao import Auth, autenticado
from app.catalogo import comum, tipos
from app.catalogo.comum import item_json, item_ou_404, jsonb, registrar_evento
from app.catalogo.modelos import Item
from app.erros import ErroAPI

router = APIRouter(tags=["acervo"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
CAMPOS_FICHA = (
    "f.fonte_id, f.nome, f.orgao, f.dominio, f.url, f.url_http, f.url_conferida_em, f.licenca, f.frescor, "
    "f.data_dado, f.data_acesso, f.script_gerador, f.sha256, f.comando_reexecucao, f.metodo, f.confianca, "
    "f.limites, f.proxima_verificacao, f.numero_tabelas, f.registros_estimados, f.bytes, f.procedencia_campos, "
    "f.procedencia_campos_possiveis, f.procedencia_pontuacao, f.atualizado_em, "
    "coalesce(l.risco_pii, false) AS risco_pii, l.motivo AS risco_pii_motivo, "
    # item L6-01-c-tela-acervo: licença CURADA (vocabulário fechado do L6-01-g, plat.acervo_licenca) quando
    # existir verificação por HTTP; None (nunca '') quando a fonte só tem o texto livre de f.licenca — a tela
    # só exige atribuição (ODbL/CC-BY-SA) sobre o tipo curado, nunca sobre o texto livre não verificado.
    "lc.tipo AS licenca_curada_tipo"
)
CAMPOS_FICHA_DE = (
    "plat.acervo_ficha f LEFT JOIN plat.acervo_lgpd l ON l.fonte_id = f.fonte_id "
    "LEFT JOIN plat.acervo_licenca lc ON lc.fonte_id = f.fonte_id"
)


def _completude_texto(r: dict) -> str | None:
    """'4,5/10' a partir de procedencia_pontuacao; None quando a view não tem base de cálculo (campos_possiveis
    ausente ou zero) — 'não registrado' é responsabilidade de quem exibe, a API nunca inventa um número."""
    p = r.get("procedencia_pontuacao")
    if p is None:
        return None
    return f"{p:.1f}".replace(".", ",") + "/10"


def _iso_datas(r: dict) -> dict:
    j = dict(r)
    for campo in ("url_conferida_em", "data_acesso", "proxima_verificacao", "testado_em"):
        if j.get(campo) is not None:
            j[campo] = j[campo].isoformat()
    if j.get("atualizado_em") is not None:
        j["atualizado_em"] = j["atualizado_em"].isoformat()
    return j


@router.get("/api/acervo", response_model=AcervoPagina, openapi_extra=LER)
def listar(
    dominio: str | None = None,
    q: str | None = Query(default=None, max_length=200),
    limite: int | None = None,
    deslocamento: int | None = None,
    auth: Auth = autenticado(escopo_token="catalogo:ler"),
):
    lim, desl = paginacao(limite, deslocamento)
    onde, params = ["true"], []
    if dominio:
        onde.append("f.dominio = %s")
        params.append(dominio)
    if q:
        onde.append("(f.nome ILIKE %s OR f.orgao ILIKE %s)")
        params.extend([f"%{q}%", f"%{q}%"])
    filtro = " AND ".join(onde)
    with db.db(auth.contexto()) as cur:
        cur.execute(f"SELECT count(*) AS n FROM {CAMPOS_FICHA_DE} WHERE {filtro}", params)
        total = cur.fetchone()["n"]
        cur.execute(
            f"SELECT f.fonte_id, f.nome, f.orgao, f.dominio, f.licenca, f.frescor, f.numero_tabelas, "
            f"f.registros_estimados, f.procedencia_pontuacao, f.proxima_verificacao, "
            f"coalesce(l.risco_pii, false) AS risco_pii, l.motivo AS risco_pii_motivo, lc.tipo AS licenca_curada_tipo "
            f"FROM {CAMPOS_FICHA_DE} WHERE {filtro} "
            f"ORDER BY f.dominio, f.nome LIMIT %s OFFSET %s",
            [*params, lim, desl],
        )
        itens = [_iso_datas(r) for r in cur.fetchall()]
    return {"total": total, "itens": itens}


@router.get("/api/acervo/dominios", response_model=list[AcervoDominio], openapi_extra=LER)
def dominios(auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """22 domínios como filtro (hipótese do item L6-01-c-tela-acervo): a lista de NOMES vem da taxonomia
    inteira de `acervo.fonte` (categoria pública, não identifica fonte nenhuma — regra D17 vale para
    QUAL fonte existe, não para o nome de uma categoria), com a contagem de fontes VISÍVEIS (licença
    escrita) por domínio; domínio sem fonte visível hoje aparece com fontes=0, nunca some da lista, para
    a tela poder mostrar a categoria vazia em vez de fingir que ela não existe."""
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "SELECT d.dominio, coalesce(v.fontes, 0) AS fontes "
            "FROM (SELECT DISTINCT dominio FROM acervo.fonte) d "
            "LEFT JOIN (SELECT dominio, count(*) AS fontes FROM plat.acervo_ficha GROUP BY dominio) v "
            "USING (dominio) ORDER BY d.dominio"
        )
        return cur.fetchall()


@router.get("/api/acervo/{fonte_id}", response_model=AcervoFicha, openapi_extra=LER)
def ver(fonte_id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    with db.db(auth.contexto()) as cur:
        cur.execute(f"SELECT {CAMPOS_FICHA} FROM {CAMPOS_FICHA_DE} WHERE f.fonte_id = %s", (fonte_id,))
        r = cur.fetchone()
        if r is None:
            # não distingue "fonte inexistente" de "fonte sem licença escrita" (regra D17): as duas somem da API.
            raise ErroAPI(404, "fonte_inexistente", "fonte do acervo inexistente")
        j = _iso_datas(r)
        j["completude_texto"] = _completude_texto(r)
        # endpoints testados por HTTP (item L6-01-d): total e vivos contados à parte da lista (LIMIT 200 na
        # lista nunca vira "endpoints_total" errado, mesmo no dia em que uma fonte passar de 200 endereços).
        cur.execute(
            "SELECT count(*) AS total, count(*) FILTER (WHERE vivo) AS vivos "
            "FROM plat.acervo_endpoint WHERE fonte_id = %s",
            (fonte_id,),
        )
        contagem = cur.fetchone()
        cur.execute(
            "SELECT url, origem, http, content_type, bytes, ms, testado_em, confirmado, vivo "
            "FROM plat.acervo_endpoint WHERE fonte_id = %s ORDER BY vivo DESC, testado_em DESC NULLS LAST LIMIT 200",
            (fonte_id,),
        )
        j["endpoints"] = [_iso_datas(e) for e in cur.fetchall()]
        j["endpoints_total"] = contagem["total"]
        j["endpoints_confirmados_vivos"] = contagem["vivos"]
    return j


def _recusar_pii(request: Request, ctx: db.Contexto, fonte_id: str, motivo: str | None) -> ErroAPI:
    """Registra a recusa em transação PRÓPRIA (mesmo padrão de app/auth/rotas_login.py::_falhou) e devolve o
    erro para o chamador levantar FORA de qualquer `with db.db(...)` — levantar a exceção dentro do bloco que
    fez o registrar_evento faria `db.db` dar rollback e apagar o próprio evento que a auditoria pede."""
    with db.db(ctx) as cur:
        registrar_evento(
            cur,
            request,
            "acervo/adicionar_recusado_pii",
            "acervo_fonte",
            fonte_id,
            {"fonte_id": fonte_id, "motivo": motivo},
        )
    return ErroAPI(
        409,
        "confirmacao_pii_exigida",
        "esta fonte pode ter dado pessoal identificável; confirme que sabe disso antes de adicionar "
        '(corpo {"confirma_risco_pii": true})',
        {"risco_pii_motivo": motivo},
    )


@router.post(
    "/api/acervo/{fonte_id}/adicionar",
    response_model=Item,
    status_code=201,
    openapi_extra={"x-auth": "S/T", "x-privilegio": "conteudo.criar|conteudo.registrar_fonte"},
)
def adicionar(
    fonte_id: str,
    request: Request,
    corpo: AcervoAdicionarEntrada | None = None,
    auth: Auth = autenticado("conteudo.criar"),
):
    if not auth.tem("conteudo.registrar_fonte"):
        raise ErroAPI(
            403,
            "sem_privilegio",
            "a operação exige o privilégio conteudo.registrar_fonte",
            {"exigido": "conteudo.registrar_fonte"},
        )
    confirma_risco_pii = bool(corpo and corpo.confirma_risco_pii)
    ctx = auth.contexto()
    with db.db(ctx) as cur:
        cur.execute(f"SELECT {CAMPOS_FICHA} FROM {CAMPOS_FICHA_DE} WHERE f.fonte_id = %s", (fonte_id,))
        f = cur.fetchone()
    if f is None:
        raise ErroAPI(404, "fonte_inexistente", "fonte do acervo inexistente")
    # item L6-01-f-lgpd: fonte marcada em plat.acervo_lgpd (curadoria manual) exige confirmação explícita ANTES
    # de qualquer INSERT — a recusa acontece sem tocar plat.item, e fica registrada como evento mesmo recusando
    # (para auditoria: quem tentou, quando, sem confirmar).
    if f["risco_pii"] and not confirma_risco_pii:
        raise _recusar_pii(request, ctx, fonte_id, f["risco_pii_motivo"])
    with db.db(ctx) as cur:
        cur.execute(
            "SELECT plat.cota_itens(%s) AS cota, (SELECT count(*) FROM plat.item WHERE tenant_id = %s) AS n",
            (auth.tenant_id, auth.tenant_id),
        )
        cota = cur.fetchone()
        if cota["n"] >= cota["cota"]:
            raise ErroAPI(
                413, "cota_itens", f"cota de itens do inquilino esgotada ({cota['cota']})", {"cota": cota["cota"]}
            )
        dados = {
            "protocolo": "acervo",
            "url": f["url_http"] or f["url"] or f"acervo:{f['fonte_id']}",
            "parametros": {
                "fonte_id": f["fonte_id"],
                "dominio": f["dominio"],
                "licenca": f["licenca"],
                # tipo do vocabulário fechado (item L6-01-g), congelado no momento de adicionar — a mesma
                # disciplina de sha256/comando_reexecucao abaixo (snapshot, não referência viva): a tela do
                # mapa usa ISTO para decidir a atribuição obrigatória de ODbL/CC-BY-SA na legenda (item
                # L6-01-c), sem precisar reconsultar o acervo por fonte a cada carga do mapa.
                "licenca_curada_tipo": f["licenca_curada_tipo"],
                "frescor": f["frescor"],
                "numero_tabelas": f["numero_tabelas"],
                "registros_estimados": f["registros_estimados"],
                "sha256": f["sha256"],
                "comando_reexecucao": f["comando_reexecucao"],
                "modo": "referenciada",
                # presente (true) só quando a fonte era marcada risco_pii e o chamador confirmou; ausente
                # (chave nem aparece) quando a fonte nunca precisou de confirmação — nunca "false" fingindo
                # uma confirmação que não foi pedida.
                **({"confirma_risco_pii": True} if f["risco_pii"] else {}),
            },
        }
        tipos.validar("conexao", dados)
        iid = str(uuid.uuid4())
        titulo = f"Acervo — {f['nome']}"[:250]
        resumo = (
            f"{f['dominio']} · {f['numero_tabelas']} tabela(s) · "
            f"{f['registros_estimados']} registro(s) (estimativa)"
        )[:2048]
        try:
            cur.execute(
                """
                INSERT INTO plat.item(id, tenant_id, tipo, titulo, resumo, creditos, termos_de_uso, dono_id,
                                       dados, origem, criado_por, modificado_por)
                VALUES (%s::uuid, %s, 'conexao', %s, %s, %s, %s, %s, %s, 'referenciado', %s, %s)
                """,
                (
                    iid,
                    auth.tenant_id,
                    titulo,
                    resumo,
                    f["orgao"],
                    f["licenca"],
                    auth.usuario_id,
                    jsonb(dados),
                    auth.usuario_id,
                    auth.usuario_id,
                ),
            )
            registrar_evento(
                cur,
                request,
                "itens/adicionar",
                "item",
                iid,
                {
                    "tipo": "conexao",
                    "fonte_id": f["fonte_id"],
                    "titulo": titulo,
                    "risco_pii": f["risco_pii"],
                    "confirma_risco_pii": confirma_risco_pii if f["risco_pii"] else None,
                },
            )
            return item_json(item_ou_404(cur, iid), auth)
        except psycopg2.Error as e:
            raise comum.erro_do_banco(e) from e
