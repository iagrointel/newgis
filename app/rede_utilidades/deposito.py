"""Importação e exportação do pacote de ativos entre o JSON e as tabelas `plat.rede_*`.

`importar` substitui o catálogo INTEIRO da rede numa transação: apaga as linhas anteriores (as chaves
estrangeiras a partir de `plat.rede` são ON DELETE CASCADE, mas aqui o apagar é explícito para que a ordem
seja legível) e grava o pacote. `exportar` reconstrói o dicionário SÓ das tabelas — nenhum byte do arquivo
recebido é guardado, e é isso que faz do teste de ida e volta uma prova de que a carga foi completa.

Regra de ausência: campo que não veio no pacote entra como NULL e sai omitido; campo que veio vazio ("") entra
como "" e sai como "". `unidade` é a exceção — é obrigatório no esquema e pode ser nulo, então sai sempre,
inclusive como null."""

import json

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
        de_g, _, de_c = r["de"].partition("/")
        pa_g, _, pa_c = r["para"].partition("/")
        cur.execute(
            "INSERT INTO plat.rede_regra(tenant_id, rede_id, tipo, de_tipo_id, para_tipo_id, descricao) "
            "VALUES (%s, %s::uuid, %s, %s, %s, %s)",
            (tenant_id, rede_id, r["tipo"], tipos[(de_g, int(de_c))], tipos[(pa_g, int(pa_c))],
             _texto(r.get("descricao"))),
        )

    # atributos de rede (item L4-01-d): marca fase (propagável) e p_n_ope (apoia traversabilidade) nos
    # atributos reais do pacote, e semeia as linhas sintéticas dos atributos calculados pela plataforma
    # (comprimento geodésico, is_connected, subrede) — nunca inventando origem para o que não veio da BDGD.
    from app.rede_utilidades import atributos as atributos_mod

    flags = atributos_mod.declarar_flags_padrao(cur, rede_id)
    calculados = atributos_mod.declarar_calculados(cur, tenant_id, rede_id)

    return {
        "dominios": len(doc["dominios"]), "tiers": len(doc["tiers"]), "categorias": len(doc["categorias"]),
        "terminais": len(doc["terminais"]), "grupos": len(doc["grupos"]), "tipos": len(doc["tipos"]),
        "atributos": len(doc["atributos"]), "regras": len(doc["regras"]),
        "atributos_flags": flags, "atributos_calculados": calculados,
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
    # atributos CALCULADOS (item L4-01-d: comprimento geodésico/is_connected/subrede, `origem.calculado`)
    # nunca entram no pacote exportado — não vieram de nenhum arquivo importado, e semeá-los de novo é
    # `atributos.declarar_calculados` (idempotente), não um dado a levar de uma organização a outra.
    cur.execute("SELECT grupo_id, tipo_id, codigo, nome, tipo_dado, unidade, obrigatorio, origem "
                "FROM plat.rede_atributo WHERE rede_id = %s::uuid "
                "AND coalesce(origem->>'calculado', 'false') <> 'true'", (rede_id,))
    atributos = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT tipo, de_tipo_id, para_tipo_id, descricao FROM plat.rede_regra WHERE rede_id = %s::uuid",
                (rede_id,))
    regras = [dict(r) for r in cur.fetchall()]

    meta = {"codigo": rede["pacote_codigo"], "nome": rede["pacote_nome"], "versao": rede["pacote_versao"],
            "disciplina": rede["disciplina"]}
    _com(meta, "descricao", rede["pacote_descricao"])
    _com(meta, "fonte", rede["pacote_fonte"])

    def _alvo(tipo_id):
        t = tipos[tipo_id]
        return f"{grupos[t['grupo_id']]['codigo']}/{t['codigo']}"

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
        "regras": [
            _com({"tipo": r["tipo"], "de": _alvo(r["de_tipo_id"]), "para": _alvo(r["para_tipo_id"])},
                 "descricao", r["descricao"])
            for r in regras
        ],
    }
