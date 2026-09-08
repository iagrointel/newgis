"""Esquema JSON da subrede exportada (item L4-04-b-atualizar-e-exportar-subrede; rascunho 2020-12).

O `Export Subnetwork` da fonte devolve um JSON com controladores, elementos e conectividade da subrede, para
o sistema de operação consumir (exportsubnetwork-utility-network-server). Aqui o esquema é CONTRATO, não
documentação: `exportar()` valida a própria saída contra ele antes de devolver, e o teste do item valida de
novo do lado de fora. `additionalProperties: false` em todo objeto — campo novo sem entrar aqui reprova."""

ESQUEMA_VERSAO = 1
ESQUEMA_ID = "plat.rede.subrede_exportada"

_UUID = {"type": "string", "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"}
_NOME = {"type": "string", "minLength": 1, "maxLength": 200}


def _obj(propriedades: dict, obrigatorios: list[str]) -> dict:
    return {"type": "object", "properties": propriedades, "required": obrigatorios,
            "additionalProperties": False}


ESQUEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": f"https://iagrointel.invalido/esquemas/{ESQUEMA_ID}/{ESQUEMA_VERSAO}",
    "title": "Subrede exportada",
    "type": "object",
    "additionalProperties": False,
    "required": ["esquema", "esquema_versao", "rede", "subrede", "controladores", "elementos",
                 "conectividade", "resumo", "exportado_em"],
    "properties": {
        "esquema": {"const": ESQUEMA_ID},
        "esquema_versao": {"const": ESQUEMA_VERSAO},
        "exportado_em": {"type": "string", "minLength": 20},
        "rede": _obj({"id": _UUID, "nome": _NOME, "disciplina": {"type": "string"}},
                     ["id", "nome", "disciplina"]),
        "subrede": _obj({
            "id": _UUID,
            "nome": _NOME,
            "tier": {"type": "string"},
            "tier_nome": {"type": "string"},
            "tier_tipo": {"type": "string", "enum": ["hierarquico", "particionado"]},
            "estado": {"type": "string", "enum": ["limpa", "suja"]},
            "atualizado_em": {"type": ["string", "null"]},
            "comprimento_m": {"type": ["number", "null"]},
            "propagados": {"type": "object"},
            "linha": {"type": ["object", "null"]},
        }, ["id", "nome", "tier", "tier_nome", "tier_tipo", "estado", "atualizado_em", "comprimento_m",
            "propagados", "linha"]),
        "controladores": {"type": "array", "items": _obj({
            "id": _UUID,
            "nome": _NOME,
            "papel": {"type": "string", "enum": ["fonte", "sumidouro"]},
            "origem": {"type": "string", "enum": ["dispositivo", "no_de_cabeca"]},
            "feicao_id": {"oneOf": [_UUID, {"type": "null"}]},
            "terminal": {"type": ["integer", "null"]},
            "grupo": {"type": ["string", "null"]},
            "tipo_chave": {"type": ["string", "null"]},
            "lon": {"type": "number"},
            "lat": {"type": "number"},
        }, ["id", "nome", "papel", "origem", "feicao_id", "terminal", "grupo", "tipo_chave", "lon", "lat"])},
        "elementos": {"type": "array", "items": _obj({
            "feicao_id": _UUID,
            "terminal": {"type": ["integer", "null"]},
            "geometria": {"type": "string", "enum": ["ponto", "linha"]},
            "grupo": {"type": ["string", "null"]},
            "tipo_chave": {"type": ["string", "null"]},
            "propagados": {"type": "object"},
        }, ["feicao_id", "terminal", "geometria", "grupo", "tipo_chave", "propagados"])},
        "conectividade": {"type": "array", "items": _obj({
            "feicao_id": {"oneOf": [_UUID, {"type": "null"}]},
            "de": _UUID,
            "para": _UUID,
        }, ["feicao_id", "de", "para"])},
        "resumo": {"type": "object"},
    },
}
