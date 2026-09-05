"""Auxiliares do catálogo: SQL do objeto `item` (ADR 0004 seção 13.2), serialização, carregamento com 404, contexto
anônimo de link, códigos de erro do banco deste item (somados aos de app/auth/comum.py) e o gancho `item_legivel`
usado pela criação de token."""

import json
import uuid
from typing import Any

import psycopg2
import psycopg2.errors
import psycopg2.extras

from app import db
from app.auth import comum as auth_comum
from app.auth.sessao import iso
from app.erros import ErroAPI

ERROS_DO_BANCO_CATALOGO = {
    "item_protegido": (409, "item protegido contra exclusão; desligue a proteção na aba Configurações"),
    "pasta_ciclo": (409, "a pasta não pode ficar dentro de si mesma"),
    "pasta_profunda": (422, "pastas têm no máximo 5 níveis"),
    "pasta_nao_vazia": (409, "a pasta tem itens ou subpastas; mova-os antes"),
    "relacao_ciclo": (409, "a relação criaria um ciclo de dependências"),
    "relacao_com_outro_inquilino": (422, "item inexistente, apagado ou de outro inquilino"),
    "relacao_familia_invalida": (422, "tipo de relação incompatível com as famílias dos itens"),
    "relacao_profunda": (422, "grafo de dependências profundo demais"),
    "limite_relacoes": (422, "limite de relações por item atingido"),
    "limite_destaques": (422, "no máximo 24 itens em destaque por grupo"),
    "sem_contribuicao_no_grupo": (403, "você não pode contribuir com esse grupo"),
    "publico_desligado": (400, "o inquilino não permite compartilhamento público"),
    "campo_imutavel": (400, "campo não editável"),
    "dono_so_por_transferencia": (400, "o dono só muda pela transferência de propriedade"),
    "pasta_de_outro_inquilino": (404, "pasta inexistente"),
    "categoria_de_outro_inquilino": (404, "categoria inexistente"),
    "classificacao_invalida": (422, "classificação fora do esquema do inquilino"),
    "limite_categorias": (422, "limite de categorias do inquilino atingido"),
    "nivel_maximo": (422, "categorias têm no máximo 3 níveis"),
}
for _k, _v in ERROS_DO_BANCO_CATALOGO.items():
    auth_comum.ERROS_DO_BANCO.setdefault(_k, _v)

SQL_ITEM = """
SELECT i.id, i.tenant_id, i.tipo, t.familia, t.abre_em, i.titulo, i.resumo, i.descricao, i.descricao_html, i.tags,
       i.creditos, i.termos_de_uso, i.termos_de_uso_html, i.dono_id, i.pasta_id, i.extent_origem, i.miniatura_chave,
       i.miniatura_sha256, i.dados, i.acesso, i.status, i.protegido, i.classificacao,
       i.categorias::text[] AS categorias,
       i.origem, i.url,
       i.tamanho_bytes, i.versao_atual, i.versao_publicada, i.pontuacao, i.criado_por, i.criado_em, i.modificado_por,
       i.modificado_em, i.apagado_em, i.apagado_por,
       ST_XMin(i.extent) AS xmin, ST_YMin(i.extent) AS ymin, ST_XMax(i.extent) AS xmax, ST_YMax(i.extent) AS ymax,
       d.login AS dono_login, d.nome AS dono_nome,
       cp.login AS criado_por_login, mp.login AS modificado_por_login, ap.login AS apagado_por_login,
       p.nome AS pasta_nome, p.ancestrais::text[] AS pasta_ancestrais,
       (SELECT jsonb_agg(jsonb_build_object('id', k.id, 'caminho', k.caminho) ORDER BY k.caminho)
          FROM plat.categoria k WHERE k.id = ANY (i.categorias)) AS categorias_json,
       EXISTS (SELECT 1 FROM plat.favorito f
               WHERE f.item_id = i.id AND f.usuario_id = plat.usuario_atual()) AS favorito,
       plat.pode_editar(i.id) AS pode_editar,
       c.usado_por, c.criado_a_partir_de, c.grupos AS compartilhado_com_grupos, c.links_ativos
FROM plat.item i
JOIN plat.tipo_item t ON t.nome = i.tipo
JOIN plat.usuario d ON d.id = i.dono_id
LEFT JOIN plat.usuario cp ON cp.id = i.criado_por
LEFT JOIN plat.usuario mp ON mp.id = i.modificado_por
LEFT JOIN plat.usuario ap ON ap.id = i.apagado_por
LEFT JOIN plat.pasta p ON p.id = i.pasta_id
LEFT JOIN LATERAL plat.item_contagens(i.id) c ON true
"""


def uuid_ok(valor: str, codigo: str = "item_inexistente", mensagem: str = "item inexistente") -> str:
    try:
        return str(uuid.UUID(str(valor)))
    except (ValueError, TypeError, AttributeError) as e:
        raise ErroAPI(404, codigo, mensagem) from e


def item_json(r: dict, auth=None, completo: bool = True, publico: bool = False) -> dict:
    """Objeto item (13.2). Lista omite descricao/descricao_html/dados/termos_de_uso; público omite "
    "dono.login e pode_*."""
    extent = None if r["xmin"] is None else [r["xmin"], r["ymin"], r["xmax"], r["ymax"]]
    pode_editar = bool(r["pode_editar"])
    pode_apagar = pode_editar or bool(auth is not None and auth.tem("conteudo.apagar_tudo"))
    pode_compartilhar = pode_editar and bool(
        auth is not None
        and any(
            auth.tem(p)
            for p in ("compartilhar.grupo", "compartilhar.inquilino", "compartilhar.link", "compartilhar.publico")
        )
    )
    j = {
        "id": str(r["id"]),
        "tipo": r["tipo"],
        "familia": r["familia"],
        "titulo": r["titulo"],
        "resumo": r["resumo"],
        "tags": list(r["tags"] or []),
        "creditos": r["creditos"],
        "categorias": list(r["categorias_json"] or []),
        "classificacao": r["classificacao"],
        "dono": {"id": r["dono_id"], "nome": r["dono_nome"]}
        if publico
        else {"id": r["dono_id"], "login": r["dono_login"], "nome": r["dono_nome"]},
        "pasta": None
        if r["pasta_id"] is None
        else {
            "id": str(r["pasta_id"]),
            "nome": r["pasta_nome"],
            "ancestrais": [str(a) for a in (r["pasta_ancestrais"] or [])],
        },
        "extent": extent,
        "extent_origem": r["extent_origem"],
        "miniatura": f"/api/itens/{r['id']}/miniatura" if r["miniatura_chave"] else None,
        "miniatura_sha256": r["miniatura_sha256"],
        "acesso": r["acesso"],
        "compartilhado_com_grupos": r["compartilhado_com_grupos"] or 0,
        "links_ativos": r["links_ativos"] or 0,
        "status": r["status"],
        "protegido": r["protegido"],
        "origem": r["origem"],
        "url": r["url"],
        "tamanho_bytes": r["tamanho_bytes"],
        "pontuacao": r["pontuacao"],
        "versao_atual": r["versao_atual"],
        "versao_publicada": r["versao_publicada"],
        "criado_em": iso(r["criado_em"]),
        "criado_por": None if r["criado_por"] is None else {"id": r["criado_por"], "login": r["criado_por_login"]},
        "modificado_em": iso(r["modificado_em"]),
        "modificado_por": None
        if r["modificado_por"] is None
        else {"id": r["modificado_por"], "login": r["modificado_por_login"]},
        "apagado_em": iso(r["apagado_em"]),
        "apagado_por": None if r["apagado_por"] is None else {"id": r["apagado_por"], "login": r["apagado_por_login"]},
        "favorito": bool(r["favorito"]),
        "abre_em": list(r["abre_em"] or []),
        "usado_por": r["usado_por"] or 0,
        "criado_a_partir_de": r["criado_a_partir_de"] or 0,
    }
    if publico:
        j["favorito"] = False
    else:
        j.update({"pode_editar": pode_editar, "pode_apagar": pode_apagar, "pode_compartilhar": pode_compartilhar})
    if completo:
        j.update(
            {
                "descricao": r["descricao"],
                "descricao_html": r["descricao_html"],
                "termos_de_uso": r["termos_de_uso"],
                "termos_de_uso_html": r["termos_de_uso_html"],
                "dados": r["dados"] or {},
            }
        )
    return j


def carregar(cur, item_id: str) -> dict | None:
    cur.execute(SQL_ITEM + " WHERE i.id = %s::uuid", (item_id,))
    return cur.fetchone()


def item_ou_404(cur, item_id: str) -> dict:
    r = carregar(cur, uuid_ok(item_id))
    if r is None:
        raise ErroAPI(404, "item_inexistente", "item inexistente")
    return r


def exigir_edicao(cur, item_id: str) -> dict:
    """404 se não lê; 403 sem_edicao_no_item se lê mas não edita."""
    r = item_ou_404(cur, item_id)
    if not r["pode_editar"]:
        raise ErroAPI(403, "sem_edicao_no_item", "você não pode editar este item", [str(r["id"])])
    return r


def ligar_lixeira(cur) -> None:
    cur.execute("SELECT set_config('plat.lixeira', 'on', true)")


def ligar_superadmin(cur) -> None:
    cur.execute("SELECT set_config('plat.superadmin', 'on', true)")


def rotular_versao(cur, rotulo: str, comentario: str | None = None) -> None:
    cur.execute(
        "SELECT set_config('plat.versao_rotulo', %s, true), set_config('plat.versao_comentario', %s, true)",
        (rotulo, comentario or ""),
    )


def contexto_anonimo(cur, tenant_id: int, itens: list[str]) -> None:
    """Contexto de link: inquilino do link, usuário vazio (NULL), lista de itens que pode_ler aceita."""
    cur.execute(
        "SELECT set_config('plat.tenant_id', %s, true), set_config('plat.usuario_id', '', true), "
        "set_config('plat.login', '', true), set_config('plat.link_itens', %s, true)",
        (str(tenant_id), ",".join(itens)),
    )


def jsonb(valor: Any):
    return psycopg2.extras.Json(valor, dumps=lambda v: json.dumps(v, ensure_ascii=False, default=str))


def erro_do_banco(e: Exception) -> ErroAPI:
    """Como app.auth.comum.erro_do_banco, mas carrega o DETAIL de relacao_ciclo (o caminho)."""
    if isinstance(e, psycopg2.errors.RaiseException):
        codigo = (e.diag.message_primary or "").strip()
        if codigo == "relacao_ciclo":
            caminho = (e.diag.message_detail or "").split(",") if e.diag.message_detail else []
            return ErroAPI(409, "relacao_ciclo", ERROS_DO_BANCO_CATALOGO["relacao_ciclo"][1], {"caminho": caminho})
    return auth_comum.erro_do_banco(e)


def item_legivel(auth, item_id: str) -> bool:
    """Gancho para app/auth/escopos.py: o uuid de camada:ler:<uuid>/tiles:ler:<uuid> existe e o dono do token o lê."""
    try:
        iid = str(uuid.UUID(str(item_id)))
    except (ValueError, TypeError):
        return False
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT 1 FROM plat.item WHERE id = %s::uuid", (iid,))
        return cur.fetchone() is not None


def registrar_evento(cur, request, tipo: str, alvo_tipo: str, alvo_id: Any, propriedades: dict | None = None) -> None:
    auth_comum.registrar_evento(cur, request, tipo, alvo_tipo, alvo_id, propriedades)
