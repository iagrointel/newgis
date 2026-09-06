"""Regras de domínio/subtipo compartilhadas pelas rotas (item L2-10-a): carga, tradução de erro do banco,
contagem de uso e instalação do gatilho na tabela da camada.

Nenhuma rota instala gatilho na tabela de camada: quem faz isso é o BANCO. Gatilhos AFTER em
`plat.dominio_campo`, `plat.camada_subtipo` e `plat.dominio` chamam `plat.camada_dominios_aplicar`, que
escreve a função de validação da camada (migração 20260906T1620, ADR 0021). Uma rota que mudasse a ligação
sem passar por essas tabelas simplesmente não existe, e quem mexer por `psql` regenera do mesmo jeito."""

from __future__ import annotations

import psycopg2

from app.auth import comum as auth_comum
from app.catalogo.comum import item_ou_404, uuid_ok
from app.erros import ErroAPI

# código do banco -> (status, mensagem). Fora desta lista cai no tradutor comum (409 regra_do_banco).
ERROS = {
    "dominio_valores_invalidos": (422, "domínio codificado espera uma lista de valores"),
    "dominio_sem_valores": (422, "domínio codificado precisa de pelo menos um valor"),
    "dominio_valor_incompleto": (422, "cada valor do domínio precisa de código e descrição"),
    "dominio_intervalo_invalido": (422, 'domínio de intervalo espera {"min": número, "max": número}'),
    "dominio_intervalo_invertido": (422, "o mínimo é maior que o máximo"),
    "dominio_intervalo_tipo": (422, "domínio de intervalo só sobre campo numérico"),
    "subtipo_invalido": (422, "subtipo fora da lista da camada"),
    "valor_fora_do_dominio": (422, "valor fora do domínio do campo"),
    "sem_tenant_no_contexto": (403, "operação fora do inquilino da sessão"),
    "nome_de_tabela_invalido": (409, "a camada aponta para um nome de tabela inválido"),
}


def erro_do_banco(e: Exception) -> ErroAPI:
    """Traduz os RAISE do gatilho. Dois casos carregam número no DETAIL e por isso não cabem no dicionário:
    `valor_em_uso` ('<código>|<contagem>') vira 409 com a contagem, e `dominio_valores_demais` vira 422 com o
    tamanho que veio."""
    if isinstance(e, psycopg2.errors.RaiseException):
        codigo = (e.diag.message_primary or "").strip()
        detalhe = (e.diag.message_detail or "").strip()
        if codigo == "valor_em_uso":
            cod, _, n = detalhe.partition("|")
            usos = int(n) if n.isdigit() else 0
            return ErroAPI(
                409, "valor_em_uso",
                f"o valor {cod!r} está em uso por {usos} feição(ões); troque as feições antes de removê-lo",
                {"codigo": cod, "usos": usos},
            )
        if codigo == "dominio_valores_demais":
            return ErroAPI(
                422, "dominio_valores_demais",
                f"domínio codificado aceita no máximo 2000 códigos (vieram {detalhe})",
                {"recebidos": int(detalhe) if detalhe.isdigit() else None},
            )
        if codigo == "dominio_codigo_duplicado":
            return ErroAPI(422, "dominio_codigo_duplicado", f"código repetido na lista: {detalhe}",
                           {"codigo": detalhe})
        if codigo in ("valor_fora_do_dominio", "subtipo_invalido"):
            status, _ = ERROS[codigo]
            return ErroAPI(status, codigo, detalhe or ERROS[codigo][1],
                           {"campo": e.diag.column_name} if e.diag.column_name else None)
        if codigo in ERROS:
            status, mensagem = ERROS[codigo]
            return ErroAPI(status, codigo, mensagem, {"detalhe": detalhe} if detalhe else None)
    return auth_comum.erro_do_banco(e)


def dominio_json(r: dict) -> dict:
    return {
        "id": str(r["id"]),
        "nome": r["nome"],
        "tipo": r["tipo"],
        "tipo_campo": r["tipo_campo"],
        "descricao": r["descricao"],
        "valores": r["valores"],
        "criado_em": r["criado_em"].isoformat() if r.get("criado_em") else None,
        "atualizado_em": r["atualizado_em"].isoformat() if r.get("atualizado_em") else None,
    }


def dominio_ou_404(cur, dominio_id: str) -> dict:
    """404 também quando o domínio é de outro inquilino: a RLS o esconde e a API não confirma que existe."""
    did = uuid_ok(dominio_id, "dominio_inexistente", "domínio inexistente")
    cur.execute("SELECT * FROM plat.dominio WHERE id = %s::uuid", (did,))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "dominio_inexistente", "domínio inexistente")
    return r


def camada_ou_404(cur, item_id: str) -> dict:
    """O item existe, é legível e é camada vetorial. Item de outro tipo (ou de outro inquilino) = 404 —
    é este ponto que faz o ataque 'ligar domínio de A a campo de B' responder 404 e não 500."""
    r = item_ou_404(cur, item_id)
    if r["tipo"] != "camada_vetorial":
        raise ErroAPI(404, "camada_inexistente", "camada vetorial inexistente")
    return r


def campos_declarados(item: dict) -> dict[str, str]:
    """{nome: tipo} dos campos declarados no item de catálogo (dados.campos da 029)."""
    dados = item.get("dados") or {}
    return {c["nome"]: c.get("tipo", "") for c in (dados.get("campos") or []) if isinstance(c, dict) and "nome" in c}


def exigir_campo(item: dict, campo: str) -> str:
    campos = campos_declarados(item)
    if campo not in campos:
        raise ErroAPI(
            404, "campo_inexistente", f"a camada não tem o campo {campo!r}",
            {"campos": sorted(campos)[:200]},
        )
    return campos[campo]


def tipos_compativeis(tipo_pg: str, tipo_dominio: str) -> bool:
    """O domínio precisa casar com o tipo do campo. Texto aceita só domínio de tipo_campo text; campo
    numérico aceita domínio numérico de qualquer largura (o gatilho compara como numérico)."""
    numericos = {"smallint", "integer", "bigint", "double precision", "real", "numeric"}
    a = (tipo_pg or "").lower()
    b = (tipo_dominio or "").lower()
    if a in numericos and b in numericos:
        return True
    return a == b


def uso_do_dominio(cur, dominio_id: str) -> dict:
    """Camadas que usam o domínio (com campo e subtipo) e a contagem de feições por código. A contagem sai de
    plat.dominio_uso_contar, a MESMA função que o gatilho de remoção usa — não há dois números possíveis."""
    cur.execute(
        "SELECT dc.id, dc.item_id, dc.campo, dc.subtipo_codigo, i.titulo "
        "FROM plat.dominio_campo dc JOIN plat.item i ON i.id = dc.item_id "
        "WHERE dc.dominio_id = %s::uuid AND i.apagado_em IS NULL ORDER BY i.titulo, dc.campo",
        (dominio_id,),
    )
    camadas = [
        {"ligacao_id": str(r["id"]), "item_id": str(r["item_id"]), "titulo": r["titulo"],
         "campo": r["campo"], "subtipo_codigo": r["subtipo_codigo"]}
        for r in cur.fetchall()
    ]
    cur.execute(
        "SELECT codigo, descricao, ordem, ativo, plat.dominio_uso_contar(%s::uuid, codigo) AS usos "
        "FROM plat.dominio_valor WHERE dominio_id = %s::uuid ORDER BY ordem, codigo",
        (dominio_id, dominio_id),
    )
    valores = [dict(r) for r in cur.fetchall()]
    return {"dominio_id": dominio_id, "camadas": camadas, "valores": valores}
