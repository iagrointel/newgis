"""Bloco de procedência de todo item de dado (item L0-09-a-procedencia; ADR 0005 seção 6.3; D17 do
L0_CONCEITO: "procedência errada é pior que procedência nenhuma").

O bloco mora em `plat.item.dados.procedencia` (jsonb) e usa o MESMO vocabulário do registro do acervo da
casa (`acervo.fonte`, 376 fontes) e do catálogo de camadas do motor logístico: quem lê a ficha de uma fonte
em `GET /api/acervo/{id}` e o bloco de um item do catálogo lê os mesmos nomes de campo com o mesmo sentido.
A tabela de equivalência campo a campo está em `docs/PROCEDENCIA.md` e é conferida por teste.

Três regras que este módulo impõe e que os testes provam:

1. **Vazio é NULL, nunca string vazia.** `licenca: ""` (ou só espaços) vira `null` — "não registrado" e
   "registrado como nada" não podem ser a mesma coisa na busca, no filtro por licença nem na pontuação.
2. **Campo livre declara a origem.** `origem` é um objeto `{campo: "declarado"|"medido"}`: `declarado` = a
   pessoa (ou o serviço externo) afirmou; `medido` = a máquina calculou aqui (sha256 do arquivo, gerador,
   método de carga, data de acesso). Origem de campo que está vazio é descartada, e valor fora do par
   declarado/medido é 422 — inventar origem é o erro que a regra da casa proíbe.
3. **Pontuação 0-10 igual à `acervo.v_completude`.** Os mesmos 10 campos, a mesma fórmula
   (`round(campos / campos_possiveis * 10, 1)`). Nada de peso próprio: a casa já tem uma régua.

O mesmo cálculo existe em SQL (`plat.procedencia_pontuacao(dados)`, migração de L0-09-a) para a busca e o
filtro poderem ordenar/filtrar sem trazer o jsonb para o Python; `tests/unit/test_procedencia.py` compara as
duas implementações linha a linha.
"""

from __future__ import annotations

from app.erros import ErroAPI

CHAVE = "procedencia"

# ---------------------------------------------------------------- vocabulário (docs/PROCEDENCIA.md)
# campo canônico -> campo equivalente em acervo.fonte (None = não existe lá, é acréscimo do catálogo)
EQUIVALENCIA_ACERVO = {
    "fonte": "nome",
    "url": "url",
    "licenca": "licenca",
    "data_do_dado": "data_dado",
    "data_de_acesso": "data_acesso",
    "gerador": "script_gerador",
    "sha256": "sha256",
    "comando_reexecucao": "sha256_cmd",
    "metodo": "metodo",
    "confianca": "confianca",
    "limites": "limites",
    "frescor": "frescor",
    "proxima_verificacao": "proxima_verificacao",
    "responsavel": None,
}

# nome do acervo (ou outro apelido em uso) -> nome canônico do bloco. O canônico é o que a ingestão já
# grava desde o L0-04 (`data_de_acesso`, `gerador`, `data_do_dado`); os nomes do acervo entram como apelido
# para que um bloco copiado da ficha de uma fonte seja aceito sem edição manual.
APELIDOS = {
    "fonte_url": "url",
    "data_dado": "data_do_dado",
    "data_acesso": "data_de_acesso",
    "script_gerador": "gerador",
    "sha256_cmd": "comando_reexecucao",
}

# os 10 campos que a `acervo.v_completude` conta, na mesma ordem, com o nome canônico daqui
CAMPOS_PONTUADOS = (
    "url",
    "licenca",
    "frescor",
    "data_do_dado",
    "gerador",
    "sha256",
    "metodo",
    "confianca",
    "limites",
    "proxima_verificacao",
)
CAMPOS_POSSIVEIS = len(CAMPOS_PONTUADOS)

# campos que podem declarar `origem` (todos os do vocabulário; `origem` em si não se auto-descreve)
CAMPOS_COM_ORIGEM = tuple(EQUIVALENCIA_ACERVO)
ORIGENS = ("declarado", "medido")

# preenchidos pela máquina na ingestão; o portão do item exige estes 4 em toda camada importada
CAMPOS_AUTOMATICOS = ("sha256", "data_de_acesso", "gerador", "metodo")


def _texto_ou_none(v):
    """string vazia ou só espaços vira None (regra 1); o resto do valor é devolvido sem alteração."""
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


def _limites_ou_none(v):
    """`limites` aceita texto ou lista de avisos; lista sem nenhum aviso com conteúdo vira None."""
    if isinstance(v, list):
        itens = [x.strip() if isinstance(x, str) else x for x in v]
        itens = [x for x in itens if x not in (None, "", [], {})]
        return itens or None
    return _texto_ou_none(v)


def normalizar(bloco) -> dict | None:
    """Bloco cru (do usuário, da ingestão ou da sondagem de conexão) -> bloco canônico.

    Levanta ErroAPI 422 `procedencia_invalida` quando o bloco não é objeto, quando `origem` não é objeto,
    quando cita campo desconhecido ou quando o valor de origem não é declarado/medido.
    Devolve None quando o bloco é None (item sem procedência continua sem procedência: não se inventa).
    """
    if bloco is None:
        return None
    if not isinstance(bloco, dict):
        raise ErroAPI(
            422,
            "procedencia_invalida",
            "dados.procedencia precisa ser um objeto",
            {"campo": "dados.procedencia"},
        )
    saida: dict = {}
    for chave, valor in bloco.items():
        if chave == "origem":
            continue
        nome = APELIDOS.get(chave, chave)
        saida[nome] = _limites_ou_none(valor) if nome == "limites" else _texto_ou_none(valor)

    origem_crua = bloco.get("origem")
    if origem_crua is not None:
        if not isinstance(origem_crua, dict):
            raise ErroAPI(
                422,
                "procedencia_invalida",
                "dados.procedencia.origem precisa ser um objeto {campo: declarado|medido}",
                {"campo": "dados.procedencia.origem"},
            )
        origem: dict = {}
        for chave, valor in origem_crua.items():
            nome = APELIDOS.get(chave, chave)
            if nome not in CAMPOS_COM_ORIGEM:
                raise ErroAPI(
                    422,
                    "procedencia_invalida",
                    f"dados.procedencia.origem cita campo desconhecido: {chave}",
                    {"campo": f"dados.procedencia.origem.{chave}", "conhecidos": list(CAMPOS_COM_ORIGEM)},
                )
            if valor not in ORIGENS:
                raise ErroAPI(
                    422,
                    "procedencia_invalida",
                    f"origem de '{nome}' precisa ser 'declarado' ou 'medido'",
                    {"campo": f"dados.procedencia.origem.{nome}", "valor": valor},
                )
            # origem de campo vazio é descartada: origem sem valor é procedência inventada
            if saida.get(nome) is not None:
                origem[nome] = valor
        saida["origem"] = origem or None
    return saida


def campos_preenchidos(bloco) -> int:
    """Quantos dos 10 campos da `acervo.v_completude` estão preenchidos (mesma contagem, mesmos campos)."""
    if not isinstance(bloco, dict):
        return 0
    n = 0
    for campo in CAMPOS_PONTUADOS:
        valor = bloco.get(campo)
        if valor is None and campo in EQUIVALENCIA_ACERVO:
            for apelido, canonico in APELIDOS.items():
                if canonico == campo:
                    valor = bloco.get(apelido)
                    if valor is not None:
                        break
        valor = _limites_ou_none(valor) if campo == "limites" else _texto_ou_none(valor)
        if valor is not None:
            n += 1
    return n


def pontuacao(bloco) -> float | None:
    """0-10 com uma casa, `round(campos / campos_possiveis * 10, 1)` — a fórmula da `acervo.v_completude`.
    None quando o item não tem bloco: 'não registrado' nunca é 0,0 (isso é o que o acervo faz, e é o certo:
    zero é uma medida, ausência não é)."""
    if not isinstance(bloco, dict) or not bloco:
        return None
    return round(campos_preenchidos(bloco) / CAMPOS_POSSIVEIS * 10, 1)


def completude_texto(bloco) -> str | None:
    """'4,5/10' (vírgula decimal, pt-BR) — o mesmo texto da ficha do acervo (app/acervo/rotas.py)."""
    p = pontuacao(bloco)
    return None if p is None else f"{p:.1f}".replace(".", ",") + "/10"


def bloco_de(dados) -> dict | None:
    """Bloco de procedência de um `dados` de item (None quando não há)."""
    if not isinstance(dados, dict):
        return None
    b = dados.get(CHAVE)
    return b if isinstance(b, dict) and b else None


def resumo(dados) -> dict:
    """O que a API acrescenta ao item (`procedencia` do objeto item, ADR 0004 seção 13.2)."""
    bloco = bloco_de(dados)
    return {
        "pontuacao": pontuacao(bloco),
        "campos": campos_preenchidos(bloco) if bloco else 0,
        "campos_possiveis": CAMPOS_POSSIVEIS,
        "completude_texto": completude_texto(bloco),
        "licenca": (bloco or {}).get("licenca"),
    }


def resumo_de_linha(linha) -> dict:
    """Resumo a partir de uma linha de `comum.SQL_ITEM`/`SQL_ITEM_LISTA`: usa a coluna `procedencia_resumo`
    (calculada no banco por `plat.procedencia_resumo`, porque a consulta da lista não traz `i.dados`) e cai
    para o cálculo em Python quando a linha não a tem."""
    bruto = linha.get("procedencia_resumo") if hasattr(linha, "get") else None
    if not isinstance(bruto, dict):
        return resumo(linha.get("dados") if hasattr(linha, "get") else None)
    p = bruto.get("pontuacao")
    p = None if p is None else float(p)
    return {
        "pontuacao": p,
        "campos": bruto.get("campos") or 0,
        "campos_possiveis": bruto.get("campos_possiveis") or CAMPOS_POSSIVEIS,
        "completude_texto": None if p is None else f"{p:.1f}".replace(".", ",") + "/10",
        "licenca": bruto.get("licenca"),
    }


def normalizar_em_dados(dados):
    """Normaliza `dados.procedencia` no lugar (devolve o mesmo objeto quando não há bloco)."""
    if not isinstance(dados, dict) or CHAVE not in dados:
        return dados
    bloco = normalizar(dados[CHAVE])
    novo = dict(dados)
    if bloco is None:
        novo[CHAVE] = None
    else:
        novo[CHAVE] = bloco
    return novo
