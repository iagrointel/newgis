"""Cabeçalho declarativo de ferramenta-script (item L2-16-c-script-vira-ferramenta).

O usuário escreve um script Python cuja DOCSTRING DE MÓDULO é um YAML com o manifesto da
ferramenta: nome, título, descrição, parâmetros e saídas. Este módulo lê, valida e transforma
esse manifesto nas duas coisas que o resto do item consome: o FORMULÁRIO (o que a interface
pergunta, com JSON Schema por parâmetro) e a VALIDAÇÃO DE VALORES (o que a API recusa com 422
ANTES de enfileirar qualquer execução).

Vocabulário de tipos: os tipos de dado GP do serviço Geoprocessing da Esri
(developers.arcgis.com/rest/services-reference/enterprise/gp-data-types, acesso 2026-09-09) —
o MESMO vocabulário que o registro de ferramentas do L2-05-a usa, para que uma ferramenta
desta família e uma do catálogo GP falem a mesma língua quando o GPServer chegar. Aqui o
vocabulário é fechado em cinco tipos: texto (GPString), numero (GPDouble), inteiro (GPLong),
booleano (GPBoolean) e item (GPFeatureRecordSetLayer — id de item do catálogo cuja geometria
viaja para o script como GeoJSON).

Regras de validação do manifesto (tudo erro nomeado, nunca silêncio):
- a docstring tem de ser um mapeamento YAML com `nome`, `titulo` e `parametros` (lista não vazia);
- `saidas` é lista não vazia; cada entrada com `nome` e `tipo`;
- parâmetro com `padrao` é implicitamente opcional; `minimo`/`maximo` só para numero/inteiro;
- `tipo: item` exige que o VALOR (não o manifesto) seja id de item legível — isso a rota confere
  no banco, não aqui.
"""

from __future__ import annotations

import ast
import re
import uuid as modulo_uuid
from typing import Any

import yaml

NOME_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
TIPOS = {
    "texto": "GPString",
    "numero": "GPDouble",
    "inteiro": "GPLong",
    "booleano": "GPBoolean",
    "item": "GPFeatureRecordSetLayer",
}
TIPO_POR_GP = {gp: simples for simples, gp in TIPOS.items()}
JSON_TIPO = {"texto": "string", "numero": "number", "inteiro": "integer", "booleano": "boolean",
             "item": "string"}
TAM_MAX_CODIGO = 200_000  # espelho do maxLength do esquema do tipo `ferramenta_script`
TAM_MAX_TITULO = 250


class ErroCabecalho(ValueError):
    """Manifesto mal declarado no docstring; a mensagem nomeia o campo. Vira 422 na publicação."""


class ErroValor(ValueError):
    """Valor fora do tipo/da faixa de um parâmetro; `campo` nomeia o parâmetro (vira 422 com
    detalhe [{campo, erro}] — a mesma forma do 422 dados_invalidos do catálogo)."""

    def __init__(self, campo: str, mensagem: str):
        super().__init__(f"{campo}: {mensagem}")
        self.campo = campo
        self.mensagem = mensagem


def _lista_de_mapas(manifesto: dict, chave: str, obrigatorio: bool, vazia_ok: bool = False) -> list[dict]:
    bruto = manifesto.get(chave)
    if bruto is None:
        if obrigatorio:
            raise ErroCabecalho(f"cabeçalho sem `{chave}`")
        return []
    if not isinstance(bruto, list) or (not bruto and not vazia_ok):
        raise ErroCabecalho(f"`{chave}` tem de ser lista com ao menos uma entrada")
    saida = []
    for i, entrada in enumerate(bruto):
        if not isinstance(entrada, dict):
            raise ErroCabecalho(f"`{chave}[{i}]` tem de ser mapeamento")
        saida.append(entrada)
    return saida


def _validar_parametro(bruto: dict, posicao: int) -> dict:
    nome = bruto.get("nome")
    if not isinstance(nome, str) or not NOME_RE.match(nome):
        raise ErroCabecalho(f"parametros[{posicao}].nome inválido: {nome!r} "
                            "(minúsculas, dígitos e _, começando por letra; 2 a 41 caracteres)")
    tipo = bruto.get("tipo")
    if tipo not in TIPOS:
        raise ErroCabecalho(f"parametros[{posicao}].tipo fora do vocabulário: {tipo!r} "
                            f"(use um de: {', '.join(sorted(TIPOS))})")
    padrao = bruto.get("padrao")
    obrigatorio = bruto.get("obrigatorio", padrao is None)
    if not isinstance(obrigatorio, bool):
        raise ErroCabecalho(f"parametros[{posicao}].obrigatorio tem de ser booleano")
    if padrao is not None:
        try:
            _converte(tipo, padrao, f"parametros[{posicao}].padrao")
        except ErroValor as e:
            raise ErroCabecalho(str(e)) from None
    minimo = bruto.get("minimo")
    maximo = bruto.get("maximo")
    if tipo not in ("numero", "inteiro") and (minimo is not None or maximo is not None):
        raise ErroCabecalho(f"parametros[{posicao}]: minimo/maximo só valem para numero e inteiro")
    rotulo = bruto.get("rotulo") or nome
    if not isinstance(rotulo, str) or len(rotulo) > 200:
        raise ErroCabecalho(f"parametros[{posicao}].rotulo tem de ser texto de até 200")
    descricao = bruto.get("descricao") or ""
    if not isinstance(descricao, str) or len(descricao) > 500:
        raise ErroCabecalho(f"parametros[{posicao}].descricao tem de ser texto de até 500")
    return {"nome": nome, "tipo": tipo, "tipo_gp": TIPOS[tipo], "rotulo": rotulo,
            "descricao": descricao, "obrigatorio": bool(obrigatorio), "padrao": padrao,
            "minimo": minimo, "maximo": maximo}


def _validar_saida(bruto: dict, posicao: int) -> dict:
    nome = bruto.get("nome")
    if not isinstance(nome, str) or not NOME_RE.match(nome):
        raise ErroCabecalho(f"saidas[{posicao}].nome inválido: {nome!r}")
    tipo = bruto.get("tipo")
    if tipo not in TIPOS:
        raise ErroCabecalho(f"saidas[{posicao}].tipo fora do vocabulário: {tipo!r}")
    rotulo = bruto.get("rotulo") or nome
    return {"nome": nome, "tipo": tipo, "tipo_gp": TIPOS[tipo], "rotulo": rotulo}


def parse(codigo: str) -> dict:
    """Lê o manifesto do docstring do módulo e devolve o cabeçalho validado. Qualquer problema
    levanta ErroCabecalho com o campo na mensagem (a publicação converte em 422)."""
    if not isinstance(codigo, str) or not codigo.strip():
        raise ErroCabecalho("script vazio")
    if len(codigo) > TAM_MAX_CODIGO:
        raise ErroCabecalho(f"script acima do teto de {TAM_MAX_CODIGO} bytes")
    try:
        arvore = ast.parse(codigo)
    except SyntaxError as e:
        raise ErroCabecalho(f"script não compila: {e.msg} (linha {e.lineno})") from None
    doc = ast.get_docstring(arvore)
    if not doc:
        raise ErroCabecalho("script sem docstring de módulo: o cabeçalho declarativo é obrigatório")
    try:
        manifesto = yaml.safe_load(doc)
    except yaml.YAMLError as e:
        raise ErroCabecalho(f"docstring não é YAML válido: {str(e).splitlines()[0]}") from None
    if not isinstance(manifesto, dict):
        raise ErroCabecalho("docstring tem de ser um mapeamento YAML (nome, titulo, parametros, saidas)")
    nome = manifesto.get("nome")
    if not isinstance(nome, str) or not NOME_RE.match(nome):
        raise ErroCabecalho(f"cabeçalho sem `nome` válido: {nome!r}")
    titulo = manifesto.get("titulo")
    if not isinstance(titulo, str) or not titulo.strip() or len(titulo) > TAM_MAX_TITULO:
        raise ErroCabecalho("cabeçalho sem `titulo` (texto de até 250)")
    # `parametros` pode ser lista VAZIA (ferramenta sem parâmetro é legítima); a chave é obrigatória
    parametros = [_validar_parametro(p, i)
                  for i, p in enumerate(_lista_de_mapas(manifesto, "parametros", True, vazia_ok=True))]
    repetidos = {p["nome"] for p in parametros if sum(1 for x in parametros if x["nome"] == p["nome"]) > 1}
    if repetidos:
        raise ErroCabecalho(f"parâmetros repetidos: {', '.join(sorted(repetidos))}")
    saidas = [_validar_saida(s, i) for i, s in enumerate(_lista_de_mapas(manifesto, "saidas", True))]
    repetidas = {s["nome"] for s in saidas if sum(1 for x in saidas if x["nome"] == s["nome"]) > 1}
    if repetidas:
        raise ErroCabecalho(f"saídas repetidas: {', '.join(sorted(repetidas))}")
    descricao = manifesto.get("descricao") or ""
    if not isinstance(descricao, str) or len(descricao) > 2000:
        raise ErroCabecalho("`descricao` tem de ser texto de até 2000")
    return {"nome": nome, "titulo": titulo.strip(), "descricao": descricao,
            "parametros": parametros, "saidas": saidas}


def _converte(tipo: str, valor: Any, campo: str) -> Any:
    """Conferência de tipo com conversão honesta (o que o JSON da API traz é que chega aqui)."""
    if tipo == "texto":
        if not isinstance(valor, str):
            raise ErroValor(campo, "tem de ser texto")
        return valor
    if tipo == "numero":
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            raise ErroValor(campo, "tem de ser número")
        return float(valor)
    if tipo == "inteiro":
        if isinstance(valor, bool) or not isinstance(valor, int):
            raise ErroValor(campo, "tem de ser inteiro")
        return int(valor)
    if tipo == "booleano":
        if not isinstance(valor, bool):
            raise ErroValor(campo, "tem de ser booleano")
        return valor
    if tipo == "item":
        if not isinstance(valor, str):
            raise ErroValor(campo, "tem de ser o id de um item do catálogo")
        try:
            modulo_uuid.UUID(valor)
        except ValueError:
            raise ErroValor(campo, f"{valor[:80]!r} não é um id de item (uuid)") from None
        return valor
    raise ErroValor(campo, f"tipo desconhecido {tipo!r}")  # improvável: o manifesto já validou


def validar_valores(cabecalho: dict, valores: dict) -> dict:
    """Valida os valores contra o cabeçalho e devolve o dicionário tipado (padrões aplicados).
    ErroValor em cada problema — a rota junta todos e responde 422 ANTES de criar o job."""
    valores = valores or {}
    if not isinstance(valores, dict):
        raise ErroValor("*", "parâmetros têm de ser um objeto {nome: valor}")
    desconhecidos = [k for k in valores if k not in {p["nome"] for p in cabecalho["parametros"]}]
    if desconhecidos:
        raise ErroValor(desconhecidos[0], "parâmetro não declarado no cabeçalho da ferramenta")
    saida: dict[str, Any] = {}
    for p in cabecalho["parametros"]:
        campo = p["nome"]
        bruto = valores.get(campo)
        if bruto is None:
            if p["obrigatorio"]:
                raise ErroValor(campo, "parâmetro obrigatório ausente")
            if p["padrao"] is None:
                continue
            bruto = p["padrao"]
        valor = _converte(p["tipo"], bruto, campo)
        if p["tipo"] in ("numero", "inteiro"):
            if p["minimo"] is not None and valor < float(p["minimo"]):
                raise ErroValor(campo, f"abaixo do mínimo {p['minimo']}")
            if p["maximo"] is not None and valor > float(p["maximo"]):
                raise ErroValor(campo, f"acima do máximo {p['maximo']}")
        saida[campo] = valor
    return saida


def formulario(cabecalho: dict) -> dict:
    """O que a interface renderiza: rótulos, ajuda, exigência e JSON Schema por parâmetro —
    derivado SÓ do cabeçalho (nunca do corpo do script)."""
    return {
        "nome": cabecalho["nome"],
        "titulo": cabecalho["titulo"],
        "descricao": cabecalho["descricao"],
        "parametros": [
            {
                "nome": p["nome"], "tipo": p["tipo"], "tipo_gp": p["tipo_gp"], "rotulo": p["rotulo"],
                "descricao": p["descricao"], "obrigatorio": p["obrigatorio"],
                "padrao": p["padrao"], "minimo": p["minimo"], "maximo": p["maximo"],
                "esquema": _esquema_parametro(p),
            }
            for p in cabecalho["parametros"]
        ],
        "saidas": [{"nome": s["nome"], "tipo": s["tipo"], "tipo_gp": s["tipo_gp"], "rotulo": s["rotulo"]}
                   for s in cabecalho["saidas"]],
    }


def _esquema_parametro(p: dict) -> dict:
    """JSON Schema do parâmetro para a interface e para o OpenAPI dinâmico da execução."""
    esquema: dict[str, Any] = {"type": JSON_TIPO[p["tipo"]], "title": p["rotulo"]}
    if p["descricao"]:
        esquema["description"] = p["descricao"]
    if p["tipo"] == "item":
        esquema["format"] = "uuid"
        esquema["pattern"] = "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    elif p["tipo"] in ("numero", "inteiro"):
        if p["minimo"] is not None:
            esquema["minimum"] = p["minimo"] if p["tipo"] == "numero" else int(p["minimo"])
        if p["maximo"] is not None:
            esquema["maximum"] = p["maximo"] if p["tipo"] == "numero" else int(p["maximo"])
    return esquema
