"""Esquema JSON do pacote de ativos. Vocabulário fechado: disciplina, tipo de domínio, tipo de tier,
geometria, tipo de dado e tipo de regra são listas fixas — pacote com valor fora da lista é recusado na
entrada, não descoberto depois no traçado.

DUAS VERSÕES. A 1 (rascunho original do item L4-01-a) tem regras como par solto `de`/`para` em texto
("grupo/codigo") e quatro tipos (`conectividade_no_trecho`, ...). A 2 (item L4-03-a-regras-de-conectividade)
dá a cada lado da regra um objeto `{grupo, tipo, terminal?}`, acrescenta o lado VIA da regra
aresta-junção-aresta e troca o vocabulário para `juncao_juncao`, `juncao_aresta`, `aresta_juncao_aresta`,
`contencao`, `estrutura`. `pacote.ler` aceita as duas: a 1 é validada pelo esquema dela e CONVERTIDA para a
forma 2 antes de seguir (a exportação sai sempre em 2). O que a validação de esquema garante sozinha (o resto
é conferência de referência, em `pacote.py`): pacote sem `tiers`, ou com `tiers` vazio, é recusado; tipo sem
`grupo` é recusado; código fora do formato `[a-z0-9_-]` é recusado."""

ESQUEMA_VERSAO = 2
DISCIPLINAS = ("eletrica", "agua", "gas", "esgoto", "telecom", "estrutura")
TIPOS_DOMINIO = ("dominio", "estrutura")
TIPOS_TIER = ("hierarquico", "particionado")
GEOMETRIAS = ("ponto", "linha", "poligono", "sem_geometria")
TIPOS_DADO = ("texto", "inteiro", "real", "data", "booleano", "geometria")
# vocabulário da versão 1 (aceito na leitura, convertido na entrada)
TIPOS_REGRA_V1 = ("conectividade_no_trecho", "conectividade_entre_nos", "fixacao_estrutural", "contencao")
TIPOS_REGRA = ("juncao_juncao", "juncao_aresta", "aresta_juncao_aresta", "contencao", "estrutura")
# lado da regra que é junção x aresta, por tipo (conferido em pacote.py, com a geometria do grupo)
GEOMETRIA_JUNCAO = ("ponto", "sem_geometria")
GEOMETRIA_ARESTA = ("linha",)

_CODIGO = {"type": "string", "pattern": "^[a-z0-9][a-z0-9_-]{0,62}$"}
_NOME = {"type": "string", "minLength": 1, "maxLength": 200}
_DESCRICAO = {"type": "string", "maxLength": 2000}
_TERMINAL = {"type": "string", "minLength": 1, "maxLength": 62}


def _obj(propriedades: dict, obrigatorios: list[str]) -> dict:
    return {
        "type": "object",
        "properties": propriedades,
        "required": obrigatorios,
        "additionalProperties": False,
    }


# um lado da regra na versão 2: o tipo de ativo (grupo + código) e, quando faz sentido, o terminal
_REF_REGRA = _obj(
    {"grupo": _CODIGO, "tipo": {"type": "integer", "minimum": 1, "maximum": 32767}, "terminal": _TERMINAL},
    ["grupo", "tipo"],
)

_PACOTE_META = _obj(
    {
        "codigo": _CODIGO,
        "nome": _NOME,
        "versao": {"type": "string", "pattern": r"^\d+\.\d+\.\d+$"},
        "disciplina": {"enum": list(DISCIPLINAS)},
        "descricao": _DESCRICAO,
        "fonte": {"type": "string", "maxLength": 2048},
    },
    ["codigo", "nome", "versao", "disciplina"],
)

_DOMINIOS = {
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
}

_TIERS = {
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
}

_CATEGORIAS = {
    "type": "array",
    "items": _obj({"codigo": _CODIGO, "nome": _NOME, "descricao": _DESCRICAO}, ["codigo", "nome"]),
}

_TERMINAIS = {
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
}

_GRUPOS = {
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
}

_TIPOS = {
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
}

_ATRIBUTOS = {
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
}

_REGRAS_V1 = {
    "type": "array",
    "items": _obj(
        {
            "tipo": {"enum": list(TIPOS_REGRA_V1)},
            "de": {"type": "string", "maxLength": 130},
            "para": {"type": "string", "maxLength": 130},
            "descricao": _DESCRICAO,
        },
        ["tipo", "de", "para"],
    ),
}

_REGRAS_V2 = {
    "type": "array",
    "items": _obj(
        {
            "tipo": {"enum": list(TIPOS_REGRA)},
            "de": _REF_REGRA,
            "para": _REF_REGRA,
            "via": _REF_REGRA,
            "descricao": _DESCRICAO,
        },
        ["tipo", "de", "para"],
    ),
}


def _esquema(versao: int, regras: dict) -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://iagrointel.invalido/esquemas/plat.rede.pacote/{versao}",
        "title": "Pacote de ativos de rede de utilidades",
        "type": "object",
        "additionalProperties": False,
        "required": ["esquema", "esquema_versao", "pacote", "dominios", "tiers", "categorias", "terminais",
                     "grupos", "tipos", "atributos", "regras"],
        "properties": {
            "esquema": {"const": "plat.rede.pacote"},
            "esquema_versao": {"const": versao},
            "pacote": _PACOTE_META,
            "dominios": _DOMINIOS,
            "tiers": _TIERS,
            "categorias": _CATEGORIAS,
            "terminais": _TERMINAIS,
            "grupos": _GRUPOS,
            "tipos": _TIPOS,
            "atributos": _ATRIBUTOS,
            "regras": regras,
        },
    }


ESQUEMA_V1 = _esquema(1, _REGRAS_V1)
ESQUEMA = _esquema(ESQUEMA_VERSAO, _REGRAS_V2)
ESQUEMAS = {1: ESQUEMA_V1, ESQUEMA_VERSAO: ESQUEMA}
