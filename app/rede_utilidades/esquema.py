"""Esquema JSON do pacote de ativos (rascunho 2020-12). Vocabulário fechado: disciplina, tipo de domínio, tipo
de tier, geometria e tipo de dado são listas fixas — pacote com valor fora da lista é recusado na entrada, não
descoberto depois no traçado.

O que a validação de esquema garante sozinha (o resto é conferência de referência, em `pacote.py`):
pacote sem `tiers`, ou com `tiers` vazio, é recusado; tipo sem `grupo` é recusado; código fora do formato
`[a-z0-9_-]` é recusado."""

ESQUEMA_VERSAO = 1
DISCIPLINAS = ("eletrica", "agua", "gas", "esgoto", "telecom", "estrutura")
TIPOS_DOMINIO = ("dominio", "estrutura")
TIPOS_TIER = ("hierarquico", "particionado")
GEOMETRIAS = ("ponto", "linha", "poligono", "sem_geometria")
TIPOS_DADO = ("texto", "inteiro", "real", "data", "booleano", "geometria")
TIPOS_REGRA = ("conectividade_no_trecho", "conectividade_entre_nos", "fixacao_estrutural", "contencao")

_CODIGO = {"type": "string", "pattern": "^[a-z0-9][a-z0-9_-]{0,62}$"}
_NOME = {"type": "string", "minLength": 1, "maxLength": 200}
_DESCRICAO = {"type": "string", "maxLength": 2000}


def _obj(propriedades: dict, obrigatorios: list[str]) -> dict:
    return {
        "type": "object",
        "properties": propriedades,
        "required": obrigatorios,
        "additionalProperties": False,
    }


ESQUEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://iagrointel.invalido/esquemas/plat.rede.pacote/1",
    "title": "Pacote de ativos de rede de utilidades",
    "type": "object",
    "additionalProperties": False,
    "required": ["esquema", "esquema_versao", "pacote", "dominios", "tiers", "categorias", "terminais",
                 "grupos", "tipos", "atributos", "regras"],
    "properties": {
        "esquema": {"const": "plat.rede.pacote"},
        "esquema_versao": {"const": ESQUEMA_VERSAO},
        "pacote": _obj(
            {
                "codigo": _CODIGO,
                "nome": _NOME,
                "versao": {"type": "string", "pattern": r"^\d+\.\d+\.\d+$"},
                "disciplina": {"enum": list(DISCIPLINAS)},
                "descricao": _DESCRICAO,
                "fonte": {"type": "string", "maxLength": 2048},
            },
            ["codigo", "nome", "versao", "disciplina"],
        ),
        "dominios": {
            "type": "array",
            "minItems": 1,
            "items": _obj(
                {
                    "codigo": _CODIGO,
                    "nome": _NOME,
                    "tipo": {"enum": list(TIPOS_DOMINIO)},
                    "disciplina": {"enum": list(DISCIPLINAS)},
                    "ordem": {"type": "integer", "minimum": 1, "maximum": 999},
                    "descricao": _DESCRICAO,
                },
                ["codigo", "nome", "tipo", "disciplina", "ordem"],
            ),
        },
        "tiers": {
            "type": "array",
            "minItems": 1,
            "items": _obj(
                {
                    "codigo": _CODIGO,
                    "dominio": _CODIGO,
                    "nome": _NOME,
                    "ordem": {"type": "integer", "minimum": 1, "maximum": 999},
                    "tipo": {"enum": list(TIPOS_TIER)},
                    "descricao": _DESCRICAO,
                },
                ["codigo", "dominio", "nome", "ordem", "tipo"],
            ),
        },
        "categorias": {
            "type": "array",
            "items": _obj({"codigo": _CODIGO, "nome": _NOME, "descricao": _DESCRICAO}, ["codigo", "nome"]),
        },
        "terminais": {
            "type": "array",
            "items": _obj(
                {
                    "codigo": _CODIGO,
                    "nome": _NOME,
                    "terminais": {
                        "type": "array",
                        "maxItems": 8,
                        "items": _obj(
                            {
                                "id": {"type": "integer", "minimum": 1, "maximum": 8},
                                "nome": _NOME,
                                "montante": {"type": "boolean"},
                            },
                            ["id", "nome", "montante"],
                        ),
                    },
                    "caminhos_validos": {
                        "type": "array",
                        "items": _obj(
                            {
                                "de": {"type": "integer", "minimum": 1, "maximum": 8},
                                "para": {"type": "integer", "minimum": 1, "maximum": 8},
                                "nome": _NOME,
                            },
                            ["de", "para", "nome"],
                        ),
                    },
                },
                ["codigo", "nome", "terminais", "caminhos_validos"],
            ),
        },
        "grupos": {
            "type": "array",
            "minItems": 1,
            "items": _obj(
                {
                    "codigo": _CODIGO,
                    "dominio": _CODIGO,
                    "nome": _NOME,
                    "geometria": {"enum": list(GEOMETRIAS)},
                    "descricao": _DESCRICAO,
                    "camadas_fonte": {"type": "array", "items": {"type": "string", "maxLength": 60}},
                },
                ["codigo", "dominio", "nome", "geometria", "camadas_fonte"],
            ),
        },
        "tipos": {
            "type": "array",
            "minItems": 1,
            "items": _obj(
                {
                    "codigo": {"type": "integer", "minimum": 1, "maximum": 32767},
                    "grupo": _CODIGO,
                    "chave": _CODIGO,
                    "nome": _NOME,
                    "tier": _CODIGO,
                    "categorias": {"type": "array", "items": _CODIGO},
                    "terminal": _CODIGO,
                    "codigos_fonte": {"type": "array", "items": {"type": "string", "maxLength": 60}},
                    "descricao": _DESCRICAO,
                },
                ["codigo", "grupo", "chave", "nome", "tier", "categorias", "terminal", "codigos_fonte"],
            ),
        },
        "atributos": {
            "type": "array",
            "items": _obj(
                {
                    "codigo": _CODIGO,
                    "grupo": _CODIGO,
                    "tipo": {"type": "integer", "minimum": 1, "maximum": 32767},
                    "nome": _NOME,
                    "tipo_dado": {"enum": list(TIPOS_DADO)},
                    "unidade": {"type": ["string", "null"], "maxLength": 30},
                    "obrigatorio": {"type": "boolean"},
                    "origem": _obj(
                        {
                            "esquema": {"type": "string", "maxLength": 60},
                            "camada": {"type": "string", "maxLength": 60},
                            "coluna": {"type": "string", "maxLength": 60},
                            "conferida": {"type": "boolean"},
                            "nota": {"type": "string", "maxLength": 500},
                        },
                        ["esquema", "camada", "coluna", "conferida"],
                    ),
                },
                ["codigo", "grupo", "nome", "tipo_dado", "unidade", "obrigatorio"],
            ),
        },
        "regras": {
            "type": "array",
            "items": _obj(
                {
                    "tipo": {"enum": list(TIPOS_REGRA)},
                    "de": {"type": "string", "maxLength": 130},
                    "para": {"type": "string", "maxLength": 130},
                    "descricao": _DESCRICAO,
                    # tolerância de coincidência DESTE par de tipos, em metros (item L4-01-f). Ausente = a
                    # tolerância da rede. Existe porque a precisão da coordenada não é a mesma em toda camada:
                    # cadastro de ponto escrito com menos casas decimais que o vértice da linha desloca o
                    # MESMO ponto físico por meia unidade da última casa, e isso é do par, não da rede.
                    "tolerancia_m": {"type": "number", "exclusiveMinimum": 0, "maximum": 5},
                },
                ["tipo", "de", "para"],
            ),
        },
    },
}
