"""Importação e exportação do pacote de ativos entre o JSON e as tabelas `plat.rede_*`.

`importar` substitui o catálogo INTEIRO da rede numa transação: apaga as linhas anteriores (as chaves
estrangeiras a partir de `plat.rede` são ON DELETE CASCADE, mas aqui o apagar é explícito para que a ordem
seja legível) e grava o pacote. `exportar` reconstrói o dicionário SÓ das tabelas — nenhum byte do arquivo
recebido é guardado, e é isso que faz do teste de ida e volta uma prova de que a carga foi completa.

Regra de ausência: campo que não veio no pacote entra como NULL e sai omitido; campo que veio vazio ("") entra
como "" e sai como "". `unidade` é a exceção — é obrigatório no esquema e pode ser nulo, então sai sempre,
inclusive como null."""

import json

from app.rede_utilidades.esquema import GEOMETRIA_JUNCAO

CHAVE_PACOTE = ("codigo", "nome", "versao", "disciplina", "descricao", "fonte")


def _texto(v):
    return None if v is None else v


def _jsonb(v):
    return json.dumps(v, ensure_ascii=False)


def apagar_catalogo(cur, rede_id: str) -> None:
    """Ordem inversa da dependência; explícita para não depender só do CASCADE."""
    for tabela in ("rede_regra", "rede_atributo", "rede_tipo_categoria", "rede_tipo", "rede_grupo",
                   "rede_terminal_config", "rede_categoria", "rede_tier", "rede_dominio"):
        cur.execute(f"DELETE FROM plat.{tabela} WHERE rede_id = %s::uuid", (rede_id,))  # noqa: S608


def importar(cur, tenant_id: int, rede_id: str, doc: dict, usuario_id: int, sha256: str, bytes_: int) -> dict:
    """Grava o pacote validado nas tabelas da rede. Devolve a contagem por seção (o que vai no evento)."""
    apagar_catalogo(cur, rede_id)
    meta = doc["pacote"]
    cur.execute(
        "UPDATE plat.rede SET disciplina = %s, pacote_codigo = %s, pacote_nome = %s, pacote_descricao = %s, "
        "pacote_versao = %s, pacote_esquema_versao = %s, pacote_fonte = %s, pacote_sha256 = %s, "
        "pacote_bytes = %s, importado_em = now(), importado_por = %s WHERE id = %s::uuid",
        (meta["disciplina"], meta["codigo"], meta["nome"], _texto(meta.get("descricao")), meta["versao"],
         doc["esquema_versao"], _texto(meta.get("fonte")), sha256, bytes_, usuario_id, rede_id),
    )
    if cur.rowcount != 1:
        raise LookupError("rede_inexistente")

    dominios: dict = {}
    for d in doc["dominios"]:
        cur.execute(
            "INSERT INTO plat.rede_dominio(tenant_id, rede_id, codigo, nome, tipo, disciplina, ordem, descricao) "
            "VALUES (%s, %s::uuid, %s, %s, %s, %s, %s, %s) RETURNING id",
            (tenant_id, rede_id, d["codigo"], d["nome"], d["tipo"], d["disciplina"], d["ordem"],
             _texto(d.get("descricao"))),
        )
        dominios[d["codigo"]] = cur.fetchone()["id"]

    tiers: dict = {}
    for t in doc["tiers"]:
        cur.execute(
            "INSERT INTO plat.rede_tier(tenant_id, rede_id, dominio_id, codigo, nome, ordem, tipo, descricao) "
            "VALUES (%s, %s::uuid, %s, %s, %s, %s, %s, %s) RETURNING id",
            (tenant_id, rede_id, dominios[t["dominio"]], t["codigo"], t["nome"], t["ordem"], t["tipo"],
             _texto(t.get("descricao"))),
        )
        tiers[t["codigo"]] = cur.fetchone()["id"]

    categorias: dict = {}
    for c in doc["categorias"]:
        cur.execute(
            "INSERT INTO plat.rede_categoria(tenant_id, rede_id, codigo, nome, descricao) "
            "VALUES (%s, %s::uuid, %s, %s, %s) RETURNING id",
            (tenant_id, rede_id, c["codigo"], c["nome"], _texto(c.get("descricao"))),
        )
        categorias[c["codigo"]] = cur.fetchone()["id"]

    terminais: dict = {}
    for t in doc["terminais"]:
        cur.execute(
            "INSERT INTO plat.rede_terminal_config(tenant_id, rede_id, codigo, nome, terminais, caminhos_validos) "
            "VALUES (%s, %s::uuid, %s, %s, %s::jsonb, %s::jsonb) RETURNING id",
            (tenant_id, rede_id, t["codigo"], t["nome"], _jsonb(t["terminais"]), _jsonb(t["caminhos_validos"])),
        )
        terminais[t["codigo"]] = cur.fetchone()["id"]

    grupos: dict = {}
    for g in doc["grupos"]:
        cur.execute(
            "INSERT INTO plat.rede_grupo(tenant_id, rede_id, dominio_id, codigo, nome, geometria, descricao, "
            "camadas_fonte) VALUES (%s, %s::uuid, %s, %s, %s, %s, %s, %s::jsonb) RETURNING id",
            (tenant_id, rede_id, dominios[g["dominio"]], g["codigo"], g["nome"], g["geometria"],
             _texto(g.get("descricao")), _jsonb(g["camadas_fonte"])),
        )
        grupos[g["codigo"]] = cur.fetchone()["id"]

    tipos: dict = {}
    for t in doc["tipos"]:
        cur.execute(
            "INSERT INTO plat.rede_tipo(tenant_id, rede_id, grupo_id, tier_id, terminal_id, codigo, chave, nome, "
            "descricao, codigos_fonte) VALUES (%s, %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s::jsonb) RETURNING id",
            (tenant_id, rede_id, grupos[t["grupo"]], tiers[t["tier"]], terminais[t["terminal"]], t["codigo"],
             t["chave"], t["nome"], _texto(t.get("descricao")), _jsonb(t["codigos_fonte"])),
        )
        tipos[(t["grupo"], t["codigo"])] = cur.fetchone()["id"]
        for c in t["categorias"]:
            cur.execute(
                "INSERT INTO plat.rede_tipo_categoria(tenant_id, rede_id, tipo_id, categoria_id) "
                "VALUES (%s, %s::uuid, %s, %s)",
                (tenant_id, rede_id, tipos[(t["grupo"], t["codigo"])], categorias[c]),
            )

    for a in doc["atributos"]:
        tipo_id = tipos[(a["grupo"], a["tipo"])] if a.get("tipo") is not None else None
        cur.execute(
            "INSERT INTO plat.rede_atributo(tenant_id, rede_id, grupo_id, tipo_id, codigo, nome, tipo_dado, "
            "unidade, obrigatorio, origem) VALUES (%s, %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)",
            (tenant_id, rede_id, grupos[a["grupo"]], tipo_id, a["codigo"], a["nome"], a["tipo_dado"],
             a["unidade"], a["obrigatorio"], _jsonb(a["origem"]) if a.get("origem") is not None else None),
        )

    for r in doc["regras"]:
        via = r.get("via")
        cur.execute(
            "INSERT INTO plat.rede_regra(tenant_id, rede_id, tipo, de_tipo_id, para_tipo_id, via_tipo_id, "
            "de_terminal, para_terminal, via_terminal, descricao) "
            "VALUES (%s, %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s)",
            (tenant_id, rede_id, r["tipo"], tipos[(r["de"]["grupo"], r["de"]["tipo"])],
             tipos[(r["para"]["grupo"], r["para"]["tipo"])],
             tipos[(via["grupo"], via["tipo"])] if via else None,
             _texto(r["de"].get("terminal")), _texto(r["para"].get("terminal")),
             _texto(via.get("terminal")) if via else None, _texto(r.get("descricao"))),
        )

    return {
        "dominios": len(doc["dominios"]), "tiers": len(doc["tiers"]), "categorias": len(doc["categorias"]),
        "terminais": len(doc["terminais"]), "grupos": len(doc["grupos"]), "tipos": len(doc["tipos"]),
        "atributos": len(doc["atributos"]), "regras": len(doc["regras"]),
    }


def _com(destino: dict, chave: str, valor) -> dict:
    if valor is not None:
        destino[chave] = valor
    return destino


def exportar(cur, rede_id: str) -> dict | None:
    """Reconstrói o pacote a partir das tabelas. None quando a rede nunca recebeu um pacote."""
    cur.execute(
        "SELECT pacote_codigo, pacote_nome, pacote_descricao, pacote_versao, pacote_esquema_versao, "
        "pacote_fonte, disciplina FROM plat.rede WHERE id = %s::uuid", (rede_id,)
    )
    rede = cur.fetchone()
    if rede is None or rede["pacote_codigo"] is None:
        return None

    cur.execute("SELECT id, codigo, nome, tipo, disciplina, ordem, descricao FROM plat.rede_dominio "
                "WHERE rede_id = %s::uuid", (rede_id,))
    dominios = {r["id"]: dict(r) for r in cur.fetchall()}
    cur.execute("SELECT id, dominio_id, codigo, nome, ordem, tipo, descricao FROM plat.rede_tier "
                "WHERE rede_id = %s::uuid", (rede_id,))
    tiers = {r["id"]: dict(r) for r in cur.fetchall()}
    cur.execute("SELECT id, codigo, nome, descricao FROM plat.rede_categoria WHERE rede_id = %s::uuid", (rede_id,))
    categorias = {r["id"]: dict(r) for r in cur.fetchall()}
    cur.execute("SELECT id, codigo, nome, terminais, caminhos_validos FROM plat.rede_terminal_config "
                "WHERE rede_id = %s::uuid", (rede_id,))
    terminais = {r["id"]: dict(r) for r in cur.fetchall()}
    cur.execute("SELECT id, dominio_id, codigo, nome, geometria, descricao, camadas_fonte FROM plat.rede_grupo "
                "WHERE rede_id = %s::uuid", (rede_id,))
    grupos = {r["id"]: dict(r) for r in cur.fetchall()}
    cur.execute("SELECT id, grupo_id, tier_id, terminal_id, codigo, chave, nome, descricao, codigos_fonte "
                "FROM plat.rede_tipo WHERE rede_id = %s::uuid", (rede_id,))
    tipos = {r["id"]: dict(r) for r in cur.fetchall()}
    cur.execute("SELECT tipo_id, categoria_id FROM plat.rede_tipo_categoria WHERE rede_id = %s::uuid", (rede_id,))
    cats_por_tipo: dict = {}
    for r in cur.fetchall():
        cats_por_tipo.setdefault(r["tipo_id"], []).append(categorias[r["categoria_id"]]["codigo"])
    cur.execute("SELECT grupo_id, tipo_id, codigo, nome, tipo_dado, unidade, obrigatorio, origem "
                "FROM plat.rede_atributo WHERE rede_id = %s::uuid", (rede_id,))
    atributos = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT tipo, de_tipo_id, para_tipo_id, via_tipo_id, de_terminal, para_terminal, via_terminal, "
                "descricao FROM plat.rede_regra WHERE rede_id = %s::uuid", (rede_id,))
    regras = [dict(r) for r in cur.fetchall()]

    meta = {"codigo": rede["pacote_codigo"], "nome": rede["pacote_nome"], "versao": rede["pacote_versao"],
            "disciplina": rede["disciplina"]}
    _com(meta, "descricao", rede["pacote_descricao"])
    _com(meta, "fonte", rede["pacote_fonte"])

    def _ref(tipo_id, terminal=None):
        """Lado de regra na forma 2: {grupo, tipo, terminal?}. Na junção-aresta a JUNÇÃO vai no lado `de`;
        linha antiga (pré-versão 2) pode ter gravado a aresta em `de` — a exportação normaliza pela
        geometria do grupo, com a mesma regra da conversão de pacote versão 1."""
        t = tipos[tipo_id]
        ref = {"grupo": grupos[t["grupo_id"]]["codigo"], "tipo": t["codigo"]}
        if terminal is not None:
            ref["terminal"] = terminal
        return ref

    def _regra(r):
        de_ref = _ref(r["de_tipo_id"], r["de_terminal"])
        para_ref = _ref(r["para_tipo_id"], r["para_terminal"])
        if r["tipo"] == "juncao_aresta":
            geo_de = grupos[tipos[r["de_tipo_id"]]["grupo_id"]]["geometria"]
            geo_para = grupos[tipos[r["para_tipo_id"]]["grupo_id"]]["geometria"]
            if geo_para in GEOMETRIA_JUNCAO and geo_de not in GEOMETRIA_JUNCAO:
                de_ref, para_ref = para_ref, de_ref
        doc_r = {"tipo": r["tipo"], "de": de_ref, "para": para_ref}
        if r["via_tipo_id"] is not None:
            doc_r["via"] = _ref(r["via_tipo_id"], r["via_terminal"])
        return _com(doc_r, "descricao", r["descricao"])

    return {
        "esquema": "plat.rede.pacote",
        "esquema_versao": rede["pacote_esquema_versao"],
        "pacote": meta,
        "dominios": [
            _com({"codigo": d["codigo"], "nome": d["nome"], "tipo": d["tipo"], "disciplina": d["disciplina"],
                  "ordem": d["ordem"]}, "descricao", d["descricao"])
            for d in dominios.values()
        ],
        "tiers": [
            _com({"codigo": t["codigo"], "dominio": dominios[t["dominio_id"]]["codigo"], "nome": t["nome"],
                  "ordem": t["ordem"], "tipo": t["tipo"]}, "descricao", t["descricao"])
            for t in tiers.values()
        ],
        "categorias": [
            _com({"codigo": c["codigo"], "nome": c["nome"]}, "descricao", c["descricao"])
            for c in categorias.values()
        ],
        "terminais": [
            {"codigo": t["codigo"], "nome": t["nome"], "terminais": t["terminais"],
             "caminhos_validos": t["caminhos_validos"]}
            for t in terminais.values()
        ],
        "grupos": [
            _com({"codigo": g["codigo"], "dominio": dominios[g["dominio_id"]]["codigo"], "nome": g["nome"],
                  "geometria": g["geometria"], "camadas_fonte": g["camadas_fonte"]}, "descricao", g["descricao"])
            for g in grupos.values()
        ],
        "tipos": [
            _com({"codigo": t["codigo"], "grupo": grupos[t["grupo_id"]]["codigo"], "chave": t["chave"],
                  "nome": t["nome"], "tier": tiers[t["tier_id"]]["codigo"],
                  "categorias": sorted(cats_por_tipo.get(t["id"], [])),
                  "terminal": terminais[t["terminal_id"]]["codigo"] if t["terminal_id"] else None,
                  "codigos_fonte": t["codigos_fonte"]}, "descricao", t["descricao"])
            for t in tipos.values()
        ],
        "atributos": [
            _com(_com({"codigo": a["codigo"], "grupo": grupos[a["grupo_id"]]["codigo"], "nome": a["nome"],
                       "tipo_dado": a["tipo_dado"], "unidade": a["unidade"], "obrigatorio": a["obrigatorio"]},
                      "tipo", tipos[a["tipo_id"]]["codigo"] if a["tipo_id"] else None),
                 "origem", a["origem"])
            for a in atributos
        ],
        "regras": [_regra(r) for r in regras],
    }


# --- regras avaliáveis e feições (item L4-03-a-regras-de-conectividade) --------------------------------------


def carregar_regras(cur, rede_id: str) -> list:
    """As regras da rede como `regras.Regra`, com as chaves naturais (codigo do grupo, codigo do tipo) no
    lugar dos uuids internos — é a chave estável que a avaliação, a mensagem de recusa e o CSV usam."""
    from app.rede_utilidades.regras import Regra

    cur.execute(
        "SELECT rg.id, rg.tipo, rg.de_terminal, rg.para_terminal, rg.via_terminal, rg.descricao, "
        "gd.codigo AS de_grupo, td.codigo AS de_tipo, gp.codigo AS para_grupo, tp.codigo AS para_tipo, "
        "gv.codigo AS via_grupo, tv.codigo AS via_tipo "
        "FROM plat.rede_regra rg "
        "JOIN plat.rede_tipo td ON td.id = rg.de_tipo_id "
        "JOIN plat.rede_grupo gd ON gd.id = td.grupo_id "
        "JOIN plat.rede_tipo tp ON tp.id = rg.para_tipo_id "
        "JOIN plat.rede_grupo gp ON gp.id = tp.grupo_id "
        "LEFT JOIN plat.rede_tipo tv ON tv.id = rg.via_tipo_id "
        "LEFT JOIN plat.rede_grupo gv ON gv.id = tv.grupo_id "
        "WHERE rg.rede_id = %s::uuid ORDER BY rg.tipo, gd.codigo, td.codigo, gp.codigo, tp.codigo",
        (rede_id,),
    )
    return [
        Regra(
            id=str(r["id"]), tipo=r["tipo"],
            de=(r["de_grupo"], r["de_tipo"]), para=(r["para_grupo"], r["para_tipo"]),
            de_terminal=r["de_terminal"], para_terminal=r["para_terminal"],
            via=(r["via_grupo"], r["via_tipo"]) if r["via_grupo"] is not None else None,
            via_terminal=r["via_terminal"], descricao=r["descricao"],
        )
        for r in cur.fetchall()
    ]


def mapas_catalogo(cur, rede_id: str) -> dict:
    """Os quatro mapas que a validação de CSV e o applyEdits usam, todos por chave natural:
    tipos_por_grupo {grupo: {codigo: chave}}, terminais {(grupo, codigo): {nomes de terminal}},
    geometrias {grupo: geometria}, ids {(grupo, codigo): uuid do tipo}, grupo_ids {grupo: uuid}."""
    cur.execute("SELECT id, codigo FROM plat.rede_grupo WHERE rede_id = %s::uuid", (rede_id,))
    grupo_ids = {r["codigo"]: str(r["id"]) for r in cur.fetchall()}
    cur.execute(
        "SELECT t.id, g.codigo AS grupo, g.geometria, t.codigo, t.chave, tc.terminais "
        "FROM plat.rede_tipo t JOIN plat.rede_grupo g ON g.id = t.grupo_id "
        "LEFT JOIN plat.rede_terminal_config tc ON tc.id = t.terminal_id "
        "WHERE t.rede_id = %s::uuid",
        (rede_id,),
    )
    tipos_por_grupo: dict = {}
    terminais: dict = {}
    geometrias: dict = {}
    ids: dict = {}
    for r in cur.fetchall():
        tipos_por_grupo.setdefault(r["grupo"], {})[r["codigo"]] = r["chave"]
        geometrias[r["grupo"]] = r["geometria"]
        ids[(r["grupo"], r["codigo"])] = str(r["id"])
        nomes = {t["nome"] for t in (r["terminais"] or [])}
        if nomes:
            terminais[(r["grupo"], r["codigo"])] = nomes
    return {"tipos_por_grupo": tipos_por_grupo, "terminais": terminais,
            "geometrias": geometrias, "ids": ids, "grupo_ids": grupo_ids}


def regras_ativas(cur, rede_id: str) -> bool:
    cur.execute("SELECT regras_ativas FROM plat.rede WHERE id = %s::uuid", (rede_id,))
    return cur.fetchone()["regras_ativas"]


def definir_regras_ativas(cur, rede_id: str, ativa: bool) -> None:
    cur.execute("UPDATE plat.rede SET regras_ativas = %s WHERE id = %s::uuid", (ativa, rede_id))


def substituir_regras(cur, tenant_id: int, rede_id: str, regras: list[dict], ids: dict) -> int:
    """Substitui o conjunto INTEIRO de regras pelo validado no CSV, na transação do chamador. As conexões e
    associações já gravadas ficam (regra_id vira NULL pelo ON DELETE SET NULL): a regra nova vale da próxima
    edição em diante, e a validação em lote reavalia o que já existe contra o conjunto novo."""
    cur.execute("DELETE FROM plat.rede_regra WHERE rede_id = %s::uuid", (rede_id,))
    for r in regras:
        cur.execute(
            "INSERT INTO plat.rede_regra(tenant_id, rede_id, tipo, de_tipo_id, para_tipo_id, via_tipo_id, "
            "de_terminal, para_terminal, via_terminal) VALUES (%s, %s::uuid, %s, %s, %s, %s, %s, %s, %s)",
            (tenant_id, rede_id, r["tipo"], ids[(r["de"][0], r["de"][1])], ids[(r["para"][0], r["para"][1])],
             ids[(r["via"][0], r["via"][1])] if r["via"] else None,
             r["de_terminal"], r["para_terminal"], r["via_terminal"]),
        )
    return len(regras)
