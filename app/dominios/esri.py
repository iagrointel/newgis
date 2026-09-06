"""Tradução entre o domínio/subtipo da casa e o objeto de domínio da Esri (item L2-10-a).

Vale nos dois sentidos e é o mesmo par de funções usado pela importação (`POST /api/dominios/importar`,
que recebe o `fields`/`types` de um `/FeatureServer/0?f=json` ou de um FGDB já lido) e pela exposição
(`/rest/services/{item_id}/FeatureServer/0`). Referência: developers.arcgis.com, "Domain objects" —
`codedValue` com `codedValues:[{name, code}]` e `range` com `range:[min, max]`.

Cuidado com a inversão de vocabulário, que é a origem de quase todo erro nesta ponte: na Esri o `name` do
valor codificado é a DESCRIÇÃO que aparece na tela e o `code` é o que vai gravado. Aqui os campos se chamam
`descricao` e `codigo`, na mesma ordem."""

from __future__ import annotations

# tipo PostgreSQL -> tipo de campo do FeatureServer. Fora deste mapa, esriFieldTypeString (o que o Pro
# aceita sem reclamar); a tabela cresce quando a linha L2-08 precisar de mais tipos.
TIPO_ESRI = {
    "text": "esriFieldTypeString",
    "character varying": "esriFieldTypeString",
    "smallint": "esriFieldTypeSmallInteger",
    "integer": "esriFieldTypeInteger",
    "bigint": "esriFieldTypeBigInteger",
    "double precision": "esriFieldTypeDouble",
    "real": "esriFieldTypeSingle",
    "numeric": "esriFieldTypeDouble",
    "date": "esriFieldTypeDate",
    "timestamp with time zone": "esriFieldTypeDate",
    "boolean": "esriFieldTypeSmallInteger",
    "uuid": "esriFieldTypeGUID",
}
# volta: tipo do FeatureServer -> tipo de campo do domínio da casa
TIPO_PG = {
    "esriFieldTypeString": "text",
    "esriFieldTypeSmallInteger": "smallint",
    "esriFieldTypeInteger": "integer",
    "esriFieldTypeBigInteger": "bigint",
    "esriFieldTypeOID": "integer",
    "esriFieldTypeDouble": "double precision",
    "esriFieldTypeSingle": "real",
    "esriFieldTypeDate": "date",
}


def tipo_esri(tipo_pg: str) -> str:
    return TIPO_ESRI.get((tipo_pg or "").lower(), "esriFieldTypeString")


def dominio_para_esri(d: dict) -> dict:
    """Linha de plat.dominio -> objeto de domínio da Esri. Valor inativo não é oferecido na lista (é assim
    que o Pro trata `ativo=false`), mas continua válido no banco para o dado que já o usa."""
    if d["tipo"] == "codificado":
        return {
            "type": "codedValue",
            "name": d["nome"],
            "description": d.get("descricao") or "",
            "codedValues": [
                {"name": v.get("descricao", ""), "code": v.get("codigo")}
                for v in sorted(d["valores"], key=lambda v: (v.get("ordem") if v.get("ordem") is not None else 0))
                if v.get("ativo", True)
            ],
            "mergePolicy": "esriMPTDefaultValue",
            "splitPolicy": "esriSPTDuplicate",
        }
    return {
        "type": "range",
        "name": d["nome"],
        "description": d.get("descricao") or "",
        "range": [d["valores"]["min"], d["valores"]["max"]],
        "mergePolicy": "esriMPTDefaultValue",
        "splitPolicy": "esriSPTDuplicate",
    }


def dominio_de_esri(objeto: dict) -> dict | None:
    """Objeto de domínio da Esri -> {nome, tipo, tipo_campo, valores} da casa. `None` quando o objeto não é
    um domínio que esta versão sabe representar (herdado do subtipo, ou tipo novo) — quem chama registra o
    caso em `ignorados` em vez de inventar um domínio."""
    if not isinstance(objeto, dict):
        return None
    tipo = objeto.get("type")
    nome = (objeto.get("name") or "").strip()
    if not nome:
        return None
    if tipo == "codedValue":
        valores = []
        for i, v in enumerate(objeto.get("codedValues") or []):
            if not isinstance(v, dict) or v.get("code") is None:
                return None
            valores.append({
                "codigo": str(v["code"]),
                "descricao": str(v.get("name") or v["code"]),
                "ordem": i,
                "ativo": True,
            })
        if not valores:
            return None
        return {"nome": nome, "tipo": "codificado", "valores": valores,
                "descricao": objeto.get("description") or None}
    if tipo == "range":
        faixa = objeto.get("range")
        if not (isinstance(faixa, list) and len(faixa) == 2):
            return None
        try:
            minimo, maximo = float(faixa[0]), float(faixa[1])
        except (TypeError, ValueError):
            return None
        return {"nome": nome, "tipo": "intervalo", "valores": {"min": minimo, "max": maximo},
                "descricao": objeto.get("description") or None}
    return None


def tipos_para_esri(subtipo: dict | None, dominios_por_subtipo: dict[int, dict[str, dict]]) -> list[dict]:
    """`types` do FeatureServer a partir de plat.camada_subtipo + as ligações com subtipo_codigo.

    `dominios_por_subtipo[codigo][campo]` é a linha de plat.dominio já carregada. Campo sem domínio próprio
    naquele subtipo sai como `{"type": "inherited"}`, que é como a Esri diz "vale o domínio da camada"."""
    if not subtipo:
        return []
    saida = []
    for v in subtipo["valores"]:
        codigo = int(v["codigo"])
        dominios = {campo: dominio_para_esri(d) for campo, d in (dominios_por_subtipo.get(codigo) or {}).items()}
        prototipo = dict(v.get("padroes") or {})
        prototipo[subtipo["campo"]] = codigo
        saida.append({
            "id": codigo,
            "name": v["nome"],
            "domains": dominios,
            "templates": [{
                "name": v["nome"],
                "description": "",
                "drawingTool": "esriFeatureEditToolNone",
                "prototype": {"attributes": prototipo},
            }],
        })
    return saida


def campos_para_esri(campos: list[dict], dominios_por_campo: dict[str, dict]) -> list[dict]:
    """`fields` do FeatureServer: o que o item de catálogo declara (dados.campos), com o domínio da camada
    (o da ligação sem subtipo) pendurado em cada campo que tiver um."""
    saida = []
    for c in campos:
        nome = c.get("nome")
        if not nome:
            continue
        d = dominios_por_campo.get(nome)
        saida.append({
            "name": nome,
            "type": tipo_esri(c.get("tipo", "")),
            "alias": c.get("alias") or nome,
            "nullable": True,
            "editable": True,
            "domain": dominio_para_esri(d) if d else None,
        })
    return saida
