"""Núcleo do módulo formulário (item L5-03-form-builder): CRUD de `plat.formulario`/`formulario_versao`
e a publicação, que resolve domínio "vindo da camada" (snapshot na hora de publicar — ver docstring de
`publicar`) e compila o desenho em `plat.item.dados` da camada (`app/formulario/motor.py::compilar`),
onde `app/edicao/servico.py::validar_atributos` já lê `regras_campo` desde o item L2-03-a e passa a ler
`form_condicionais`/`form_calculados` a partir deste item."""

from __future__ import annotations

import json
import re

from app import limites
from app.catalogo import comum
from app.erros import ErroAPI
from app.formulario import motor

_RE_SCHEMA = re.compile(r"^d_[a-z0-9_]{1,60}$")
_RE_TABELA = re.compile(r"^c_[0-9a-f]{16}$")
_RE_CAMPO = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,62}$")


def camada_ou_404(cur, camada_id: str) -> tuple[dict, dict]:
    r = comum.item_ou_404(cur, camada_id)
    if r["tipo"] != "camada_vetorial":
        raise ErroAPI(404, "item_inexistente", "item inexistente")
    dados = r["dados"] or {}
    return r, dados


def campos_validos_de(dados_camada: dict) -> dict[str, dict]:
    return {c["nome"]: c for c in dados_camada.get("campos") or [] if isinstance(c, dict) and c.get("nome")}


def _checar_tamanho(desenho: dict) -> None:
    grupos = desenho.get("grupos") or []
    if len(grupos) > limites.FORMULARIO_GRUPOS_MAX:
        raise ErroAPI(422, "formulario_grande", f"mais de {limites.FORMULARIO_GRUPOS_MAX} grupos")
    for g in grupos:
        if len(g.get("campos") or []) > limites.FORMULARIO_CAMPOS_POR_GRUPO_MAX:
            raise ErroAPI(
                422, "formulario_grande",
                f"grupo com mais de {limites.FORMULARIO_CAMPOS_POR_GRUPO_MAX} campos",
            )
    if len(json.dumps(desenho, ensure_ascii=False).encode("utf-8")) > limites.FORMULARIO_DESENHO_BYTES_MAX:
        raise ErroAPI(422, "formulario_grande", f"desenho acima de {limites.FORMULARIO_DESENHO_BYTES_MAX} bytes")


def formulario_json(f: dict) -> dict:
    return {
        "id": str(f["id"]), "camada_id": str(f["camada_id"]), "nome": f["nome"],
        "publicado_versao": f.get("publicado_versao"),
        "criado_em": f["criado_em"].isoformat(), "atualizado_em": f["atualizado_em"].isoformat(),
    }


def formulario_obter(cur, camada_id: str) -> dict | None:
    cur.execute(
        "SELECT f.*, fv.versao AS publicado_versao FROM plat.formulario f "
        "LEFT JOIN plat.formulario_versao fv ON fv.id = f.publicado_versao_id "
        "WHERE f.camada_id = %s::uuid", (camada_id,),
    )
    return cur.fetchone()


def formulario_ou_criar(cur, auth, camada_id: str, nome: str | None = None) -> dict:
    f = formulario_obter(cur, camada_id)
    if f is not None:
        return f
    cur.execute(
        "INSERT INTO plat.formulario(tenant_id, camada_id, nome, criado_por) VALUES (%s, %s::uuid, %s, %s) "
        "RETURNING *", (auth.tenant_id, camada_id, nome or "Formulário", auth.usuario_id),
    )
    row = dict(cur.fetchone())
    row["publicado_versao"] = None
    return row


def formulario_ou_404(cur, camada_id: str) -> dict:
    f = formulario_obter(cur, camada_id)
    if f is None:
        raise ErroAPI(404, "formulario_inexistente", "esta camada ainda não tem formulário")
    return f


def versoes_listar(cur, formulario_id: str) -> list[dict]:
    cur.execute(
        "SELECT id, versao, publicado, criado_em FROM plat.formulario_versao "
        "WHERE formulario_id = %s::uuid ORDER BY versao DESC", (formulario_id,),
    )
    return cur.fetchall()


def versao_obter(cur, formulario_id: str, versao: int) -> dict | None:
    cur.execute(
        "SELECT * FROM plat.formulario_versao WHERE formulario_id = %s::uuid AND versao = %s",
        (formulario_id, versao),
    )
    return cur.fetchone()


def versao_ou_404(cur, formulario_id: str, versao: int) -> dict:
    v = versao_obter(cur, formulario_id, versao)
    if v is None:
        raise ErroAPI(404, "formulario_versao_inexistente", "versão inexistente")
    return v


def desenho_publicado(cur, camada_id: str) -> dict | None:
    """desenho jsonb da versão publicada, ou `None` se a camada não tem formulário publicado (usado por
    `app/campo/rotas.py` para validar `VisitaCriar.dados` — ver motor.validar_dados_livre)."""
    cur.execute(
        "SELECT fv.desenho FROM plat.formulario f JOIN plat.formulario_versao fv ON fv.id = f.publicado_versao_id "
        "WHERE f.camada_id = %s::uuid", (camada_id,),
    )
    r = cur.fetchone()
    return r["desenho"] if r else None


def versao_salvar(cur, auth, camada_id: str, dados_camada: dict, desenho: dict) -> dict:
    _checar_tamanho(desenho)
    motor.validar_desenho(desenho, campos_validos_de(dados_camada))
    f = formulario_ou_criar(cur, auth, camada_id)
    cur.execute(
        "SELECT coalesce(max(versao), 0) + 1 AS prox FROM plat.formulario_versao WHERE formulario_id = %s::uuid",
        (f["id"],),
    )
    prox = cur.fetchone()["prox"]
    cur.execute(
        "SELECT count(*) AS n FROM plat.formulario_versao WHERE formulario_id = %s::uuid", (f["id"],),
    )
    if cur.fetchone()["n"] >= limites.FORMULARIO_VERSOES_MAX:
        raise ErroAPI(422, "formulario_muitas_versoes", f"mais de {limites.FORMULARIO_VERSOES_MAX} versões salvas")
    cur.execute(
        "INSERT INTO plat.formulario_versao(tenant_id, formulario_id, versao, desenho, criado_por) "
        "VALUES (%s, %s::uuid, %s, %s, %s) RETURNING id, versao, publicado, criado_em, desenho",
        (auth.tenant_id, f["id"], prox, comum.jsonb(desenho), auth.usuario_id),
    )
    return cur.fetchone()


def _resolver_dominios_de_camada(cur, desenho: dict, dados_camada: dict) -> dict:
    """`dominio.de_camada: true` -> snapshot dos valores distintos hoje na tabela da camada, gravado como
    `dominio.valores` (documentado: domínio "vindo da camada" é resolvido NA HORA DE PUBLICAR; a camada
    mudando depois não republica sozinha — republicar é o gesto que atualiza a lista)."""
    schema, tabela = dados_camada.get("schema"), dados_camada.get("tabela")
    schema_ok = isinstance(schema, str) and _RE_SCHEMA.match(schema)
    tabela_ok = isinstance(tabela, str) and _RE_TABELA.match(tabela)
    novo = {"grupos": []}
    for grupo in desenho.get("grupos") or []:
        g2 = dict(grupo)
        campos2 = []
        for c in grupo.get("campos") or []:
            c2 = dict(c)
            dominio = c.get("dominio") or {}
            if dominio.get("de_camada") and c.get("campo") and schema_ok and tabela_ok and _RE_CAMPO.match(c["campo"]):
                cur.execute(
                    f'SELECT DISTINCT "{c["campo"]}" AS v FROM "{schema}"."{tabela}" '
                    f'WHERE "{c["campo"]}" IS NOT NULL ORDER BY 1 LIMIT 500',
                )
                c2 = dict(c2, dominio={**dominio, "valores": [r["v"] for r in cur.fetchall()]})
            campos2.append(c2)
        g2["campos"] = campos2
        novo["grupos"].append(g2)
    return novo


def versao_publicar(cur, auth, camada_id: str, dados_camada: dict, versao: int) -> dict:
    f = formulario_ou_404(cur, camada_id)
    v = versao_ou_404(cur, f["id"], versao)
    motor.validar_desenho(v["desenho"], campos_validos_de(dados_camada))
    desenho_resolvido = _resolver_dominios_de_camada(cur, v["desenho"], dados_camada)
    compilado = motor.compilar(desenho_resolvido)
    cur.execute("UPDATE plat.formulario_versao SET publicado = false WHERE formulario_id = %s::uuid", (f["id"],))
    cur.execute(
        "UPDATE plat.formulario_versao SET publicado = true, desenho = %s WHERE id = %s::uuid",
        (comum.jsonb(desenho_resolvido), v["id"]),
    )
    cur.execute("UPDATE plat.formulario SET publicado_versao_id = %s::uuid WHERE id = %s::uuid", (v["id"], f["id"]))
    # merge atômico no banco (não lê-modifica-escreve em Python): `regras_campo` some ACRESCENTA/SOBRESCREVE
    # por campo (outro mecanismo pode ter posto regra em OUTRO campo entretanto, ver docstring do módulo);
    # `form_condicionais`/`form_calculados` são a projeção inteira deste formulário, então SUBSTITUEM.
    cur.execute(
        "UPDATE plat.item SET dados = dados || jsonb_build_object("
        "'regras_campo', coalesce(dados->'regras_campo', '{}'::jsonb) || %s::jsonb, "
        "'form_condicionais', %s::jsonb, 'form_calculados', %s::jsonb) WHERE id = %s::uuid",
        (comum.jsonb(compilado["regras_campo"]), comum.jsonb(compilado["form_condicionais"]),
         comum.jsonb(compilado["form_calculados"]), camada_id),
    )
    return {"formulario_id": str(f["id"]), "versao": versao, "regras_campo": compilado["regras_campo"],
            "form_condicionais": compilado["form_condicionais"], "form_calculados": compilado["form_calculados"]}


__all__ = [
    "camada_ou_404", "campos_validos_de", "formulario_obter", "formulario_ou_criar", "formulario_ou_404",
    "versoes_listar", "versao_obter", "versao_ou_404", "desenho_publicado", "versao_salvar", "versao_publicar",
]
