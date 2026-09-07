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


def importar_dominios(cur, usuario_id: int, fields: list, types: list, item: dict | None, prefixo: str | None) -> dict:
    """Corpo de `POST /api/dominios/importar`, também usado pela clonagem de camadas hospedadas (L2-08-b): domínios
    de `fields`/`types` de um FeatureServer/FGDB; nome existente é reaproveitado; com `item`, liga campo -> domínio
    e grava os subtipos (`types[0].campo_subtipo`)."""
    from app.catalogo.comum import jsonb
    from app.dominios import esri

    criados, reaproveitados, ligados, ignorados = [], [], [], []
    subtipo_saida = None
    prefixo = (prefixo + " ") if prefixo else ""
    campos_item = campos_declarados(item) if item else {}

    def garantir(objeto: dict, tipo_campo_esri: str | None) -> str | None:
        d = esri.dominio_de_esri(objeto)
        if d is None:
            ignorados.append({"motivo": "domínio não representável nesta versão",
                              "objeto": (objeto or {}).get("name") or (objeto or {}).get("type")})
            return None
        nome = prefixo + d["nome"]
        tipo_campo = esri.TIPO_PG.get(tipo_campo_esri or "", "text")
        if d["tipo"] == "intervalo" and tipo_campo in ("text", "date"):
            tipo_campo = "double precision"
        cur.execute("SELECT id, tipo FROM plat.dominio WHERE lower(nome) = lower(%s)", (nome,))
        ja = cur.fetchone()
        if ja:
            reaproveitados.append({"id": str(ja["id"]), "nome": nome})
            return str(ja["id"])
        try:
            cur.execute(
                "INSERT INTO plat.dominio (tenant_id, nome, tipo, tipo_campo, descricao, valores, "
                "criado_por, atualizado_por) VALUES (plat.tenant_atual(), %s, %s, %s, %s, %s, %s, %s) "
                "RETURNING id",
                (nome, d["tipo"], tipo_campo, d.get("descricao"), jsonb(d["valores"]),
                 usuario_id, usuario_id),
            )
        except psycopg2.Error as e:
            raise erro_do_banco(e) from e
        novo = str(cur.fetchone()["id"])
        criados.append({"id": novo, "nome": nome})
        return novo

    def ligar(campo: str, dominio_id: str, subtipo_codigo: int | None) -> None:
        if item is None:
            return
        if campo not in campos_item:
            ignorados.append({"motivo": "a camada não tem o campo", "campo": campo})
            return
        cur.execute(
            "INSERT INTO plat.dominio_campo (tenant_id, item_id, campo, subtipo_codigo, dominio_id) "
            "VALUES (plat.tenant_atual(), %s::uuid, %s, %s, %s::uuid) "
            "ON CONFLICT (item_id, campo, coalesce(subtipo_codigo, -2147483648)) "
            "DO UPDATE SET dominio_id = EXCLUDED.dominio_id RETURNING id",
            (str(item["id"]), campo, subtipo_codigo, dominio_id),
        )
        ligados.append({"campo": campo, "subtipo_codigo": subtipo_codigo, "dominio_id": dominio_id})

    for f in fields:
        if not isinstance(f, dict) or not f.get("domain"):
            continue
        did = garantir(f["domain"], f.get("type"))
        if did:
            ligar(str(f.get("name") or "").lower(), did, None)

    if types and item is not None:
        campo_sub = str(types[0].get("campo_subtipo") or "").lower() or None
        valores_sub = []
        for t in types:
            if not isinstance(t, dict) or t.get("id") is None:
                continue
            padroes = {}
            for tpl in t.get("templates") or []:
                padroes.update(((tpl or {}).get("prototype") or {}).get("attributes") or {})
            valores_sub.append({"codigo": int(t["id"]), "nome": str(t.get("name") or t["id"]),
                                "padroes": padroes})
            for campo, objeto in (t.get("domains") or {}).items():
                if not isinstance(objeto, dict) or objeto.get("type") == "inherited":
                    continue
                did = garantir(objeto, None)
                if did:
                    ligar(str(campo).lower(), did, int(t["id"]))
        if campo_sub and valores_sub:
            cur.execute(
                "INSERT INTO plat.camada_subtipo (item_id, tenant_id, campo, valores) "
                "VALUES (%s::uuid, plat.tenant_atual(), %s, %s) "
                "ON CONFLICT (item_id) DO UPDATE SET campo = EXCLUDED.campo, valores = EXCLUDED.valores, "
                "atualizado_em = now()",
                (str(item["id"]), campo_sub, jsonb(valores_sub)),
            )
            subtipo_saida = {"campo": campo_sub, "valores": valores_sub}
        elif valores_sub:
            ignorados.append({"motivo": "types sem campo_subtipo: os subtipos não foram gravados",
                              "quantos": len(valores_sub)})
    return {"criados": criados, "reaproveitados": reaproveitados, "ligados": ligados,
            "subtipos": subtipo_saida, "ignorados": ignorados}
