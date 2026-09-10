"""Registro de ferramentas por decorador (item L2-05-a). Uma ferramenta é uma função Python
`f(ctx, entradas, parametros, destino) -> dict` mais um manifesto {nome, título, categoria, versão, parâmetros
tipados no vocabulário GP da Esri, custo estimado, limites}. A validação acontece na importação (ErroRegistro):
parâmetro sem tipo, tipo fora do vocabulário, nome repetido ou saída ausente são erro de build — e o teste de
unidade que importa o módulo é o que faz `make check` recusar um manifesto inválido."""

from __future__ import annotations

import datetime
import inspect
import json
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass

PADRAO_NOME = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
CATEGORIAS = ("proximidade", "sobreposicao", "resumo", "gestao", "raster", "rede")
# vocabulário GP da Esri (developers.arcgis.com/rest/services-reference/enterprise/gp-data-types, 07/09/2026)
TIPOS_GP = ("GPFeatureRecordSetLayer", "GPRasterDataLayer", "GPString", "GPDouble", "GPLong", "GPBoolean",
            "GPLinearUnit", "GPDate", "GPMultiValue")
UNIDADES_LINEARES = {"esriMeters": 1.0, "esriKilometers": 1000.0, "esriFeet": 0.3048, "esriMiles": 1609.344}
# `parametros` não é `additionalProperties: false` solto: a lista de chaves de fora que um cliente Esri manda
# junto (f, token, env:*) é filtrada nas rotas GP antes de chegar aqui
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)


class ErroRegistro(ValueError):
    """Manifesto mal declarado; a mensagem nomeia a ferramenta e o campo."""


class ErroParametro(ValueError):
    """Valor fora do tipo/da faixa; `campo` é o nome do parâmetro (vira 422 com detalhe na API)."""

    def __init__(self, campo: str, mensagem: str):
        super().__init__(f"{campo}: {mensagem}")
        self.campo = campo
        self.mensagem = mensagem


@dataclass(frozen=True)
class Parametro:
    nome: str
    tipo: str
    rotulo: str
    direcao: str = "entrada"  # entrada | saida
    obrigatorio: bool = True
    padrao: object = None
    descricao: str = ""
    opcoes: tuple = ()  # GPString com lista fechada
    minimo: float | None = None
    maximo: float | None = None
    subtipo: str | None = None  # GPMultiValue:<subtipo>

    @property
    def tipo_gp(self) -> str:
        return f"GPMultiValue:{self.subtipo}" if self.tipo == "GPMultiValue" else self.tipo


@dataclass(frozen=True)
class Ferramenta:
    nome: str
    titulo: str
    categoria: str
    descricao: str
    versao: int
    parametros: tuple[Parametro, ...]
    funcao: Callable
    custo: Callable[[dict, dict], int]
    limites: dict

    @property
    def entradas(self) -> tuple[Parametro, ...]:
        return tuple(p for p in self.parametros if p.direcao == "entrada")

    @property
    def saidas(self) -> tuple[Parametro, ...]:
        return tuple(p for p in self.parametros if p.direcao == "saida")


REGISTRO: dict[str, Ferramenta] = {}


def _validar_parametro(nome_ferramenta: str, p: Parametro) -> None:
    onde = f"{nome_ferramenta}.{p.nome}"
    if not isinstance(p, Parametro):
        raise ErroRegistro(f"{nome_ferramenta}: parâmetro não é Parametro")
    if not PADRAO_NOME.match(p.nome):
        raise ErroRegistro(f"{onde}: nome de parâmetro inválido")
    if not p.tipo:
        raise ErroRegistro(f"{onde}: parâmetro sem tipo")
    if p.tipo not in TIPOS_GP:
        raise ErroRegistro(f"{onde}: tipo {p.tipo!r} fora do vocabulário GP {TIPOS_GP}")
    if p.tipo == "GPMultiValue" and (p.subtipo not in TIPOS_GP or p.subtipo == "GPMultiValue"):
        raise ErroRegistro(f"{onde}: GPMultiValue exige subtipo simples do vocabulário")
    if p.direcao not in ("entrada", "saida"):
        raise ErroRegistro(f"{onde}: direcao deve ser entrada ou saida")
    if not p.rotulo:
        raise ErroRegistro(f"{onde}: rótulo obrigatório")
    if p.opcoes and p.tipo != "GPString":
        raise ErroRegistro(f"{onde}: opcoes só vale para GPString")
    numerico = p.subtipo if p.tipo == "GPMultiValue" else p.tipo
    if (p.minimo is not None or p.maximo is not None) and numerico not in ("GPDouble", "GPLong", "GPLinearUnit"):
        # faixa vale também na lista (GPMultiValue de número): é aplicada a cada valor por _normalizar
        raise ErroRegistro(f"{onde}: minimo/maximo só vale para número ou unidade linear")
    if p.padrao is not None and p.direcao == "entrada":
        try:
            _normalizar(p, p.padrao)
        except ErroParametro as e:
            raise ErroRegistro(f"{onde}: padrão fora do tipo ({e.mensagem})") from e


def ferramenta(*, nome: str, titulo: str, categoria: str, parametros: tuple[Parametro, ...], custo: Callable,
               descricao: str = "", versao: int = 1, limites: dict | None = None):
    """Decorador de registro. Recusa na importação tudo o que a seção C19 do L2_CONCEITO proíbe."""
    if not PADRAO_NOME.match(nome):
        raise ErroRegistro(f"nome de ferramenta inválido: {nome!r}")
    if nome in REGISTRO:
        raise ErroRegistro(f"ferramenta repetida: {nome!r}")
    if not titulo:
        raise ErroRegistro(f"{nome}: título obrigatório")
    if categoria not in CATEGORIAS:
        raise ErroRegistro(f"{nome}: categoria {categoria!r} fora de {CATEGORIAS}")
    if not isinstance(versao, int) or versao < 1:
        raise ErroRegistro(f"{nome}: versao deve ser inteiro >= 1")
    if not parametros:
        raise ErroRegistro(f"{nome}: ao menos um parâmetro")
    nomes = [p.nome for p in parametros]
    if len(set(nomes)) != len(nomes):
        raise ErroRegistro(f"{nome}: nome de parâmetro repetido")
    for p in parametros:
        _validar_parametro(nome, p)
    if not any(p.direcao == "saida" for p in parametros):
        raise ErroRegistro(f"{nome}: ferramenta sem saída declarada")
    if not callable(custo):
        raise ErroRegistro(f"{nome}: custo deve ser função (entradas, parametros) -> int")

    def decorar(funcao: Callable) -> Callable:
        assinatura = inspect.signature(funcao)
        if list(assinatura.parameters) != ["ctx", "entradas", "parametros", "destino"]:
            raise ErroRegistro(f"{nome}: a função recebe (ctx, entradas, parametros, destino)")
        REGISTRO[nome] = Ferramenta(nome=nome, titulo=titulo, categoria=categoria, descricao=descricao,
                                    versao=versao, parametros=tuple(parametros), funcao=funcao, custo=custo,
                                    limites=dict(limites or {}))
        return funcao

    return decorar


def obter(nome: str) -> Ferramenta | None:
    return REGISTRO.get(nome)


# ---------------------------------------------------------------- normalização de valores
def _numero(p: Parametro, valor, inteiro: bool):
    if isinstance(valor, bool):
        raise ErroParametro(p.nome, "esperado número, recebido booleano")
    if isinstance(valor, str):
        try:
            valor = float(valor) if not inteiro else int(valor)
        except ValueError as e:
            raise ErroParametro(p.nome, f"esperado {'inteiro' if inteiro else 'número'}") from e
    if not isinstance(valor, (int, float)):
        raise ErroParametro(p.nome, f"esperado {'inteiro' if inteiro else 'número'}")
    if inteiro and (isinstance(valor, float) and not valor.is_integer()):
        raise ErroParametro(p.nome, "esperado inteiro")
    valor = int(valor) if inteiro else float(valor)
    if p.minimo is not None and valor < p.minimo:
        raise ErroParametro(p.nome, f"mínimo {p.minimo}")
    if p.maximo is not None and valor > p.maximo:
        raise ErroParametro(p.nome, f"máximo {p.maximo}")
    return valor


def _camada(p: Parametro, valor) -> str:
    """Referência a item de camada: uuid, {"itemId"}, ou {"url"} de FeatureServer da própria instalação."""
    if isinstance(valor, dict):
        valor = valor.get("itemId") or valor.get("item_id") or valor.get("url") or ""
    if not isinstance(valor, str):
        raise ErroParametro(p.nome, "esperado uuid de item de camada")
    m = _UUID.search(valor)
    if not m:
        raise ErroParametro(p.nome, "esperado uuid de item de camada")
    return str(uuid.UUID(m.group(0)))


def _unidade_linear(p: Parametro, valor) -> dict:
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        valor = {"distance": valor, "units": "esriMeters"}
    if not isinstance(valor, dict) or "distance" not in valor:
        raise ErroParametro(p.nome, 'esperado {"distance": <número>, "units": "esriMeters|esriKilometers|esriFeet|'
                                    'esriMiles"}')
    unidade = valor.get("units") or "esriMeters"
    if unidade not in UNIDADES_LINEARES:
        raise ErroParametro(p.nome, f"unidade {unidade!r} fora de {sorted(UNIDADES_LINEARES)}")
    distancia = _numero(Parametro(p.nome, "GPDouble", p.rotulo), valor["distance"], False)
    metros = distancia * UNIDADES_LINEARES[unidade]
    if p.minimo is not None and metros < p.minimo:
        raise ErroParametro(p.nome, f"mínimo {p.minimo} m")
    if p.maximo is not None and metros > p.maximo:
        raise ErroParametro(p.nome, f"máximo {p.maximo} m")
    return {"distance": distancia, "units": unidade, "metros": metros}


def _normalizar(p: Parametro, valor):
    tipo = p.tipo if p.tipo != "GPMultiValue" else p.subtipo
    if p.tipo == "GPMultiValue":
        if isinstance(valor, str):
            valor = [v.strip() for v in valor.split(";") if v.strip()]
        if not isinstance(valor, list):
            raise ErroParametro(p.nome, "esperado lista")
        sub = Parametro(p.nome, tipo, p.rotulo, opcoes=p.opcoes, minimo=p.minimo, maximo=p.maximo)
        return [_normalizar(sub, v) for v in valor]
    if tipo == "GPString":
        if not isinstance(valor, str):
            raise ErroParametro(p.nome, "esperado texto")
        if len(valor) > 2000:
            raise ErroParametro(p.nome, "máximo 2000 caracteres")
        if p.opcoes and valor not in p.opcoes:
            raise ErroParametro(p.nome, f"valor fora de {list(p.opcoes)}")
        return valor
    if tipo == "GPDouble":
        return _numero(p, valor, False)
    if tipo == "GPLong":
        return _numero(p, valor, True)
    if tipo == "GPBoolean":
        if isinstance(valor, str) and valor.lower() in ("true", "false"):
            return valor.lower() == "true"
        if not isinstance(valor, bool):
            raise ErroParametro(p.nome, "esperado booleano")
        return valor
    if tipo == "GPLinearUnit":
        return _unidade_linear(p, valor)
    if tipo == "GPDate":
        try:
            return datetime.date.fromisoformat(str(valor)[:10]).isoformat()
        except ValueError as e:
            raise ErroParametro(p.nome, "esperada data ISO 8601 (AAAA-MM-DD)") from e
    if tipo in ("GPFeatureRecordSetLayer", "GPRasterDataLayer"):
        return _camada(p, valor)
    raise ErroParametro(p.nome, f"tipo {tipo} sem normalizador")


def validar_parametros(f: Ferramenta, dados: dict) -> dict:
    """Devolve os parâmetros de ENTRADA normalizados (JSON puro). Campo desconhecido, obrigatório ausente ou valor
    fora do tipo levantam ErroParametro nomeando o campo."""
    if not isinstance(dados, dict):
        raise ErroParametro("parametros", "esperado objeto")
    conhecidos = {p.nome: p for p in f.entradas}
    for chave in dados:
        if chave not in conhecidos:
            raise ErroParametro(chave, "parâmetro desconhecido")
    saida = {}
    for p in f.entradas:
        valor = dados.get(p.nome)
        if valor is None or valor == "":
            if p.padrao is not None:
                saida[p.nome] = _normalizar(p, p.padrao)
            elif p.obrigatorio:
                raise ErroParametro(p.nome, "parâmetro obrigatório")
            else:
                saida[p.nome] = None
            continue
        saida[p.nome] = _normalizar(p, valor)
    return saida


# ---------------------------------------------------------------- descrições (API própria, formulário, GPServer)
def _esquema_de(p: Parametro) -> dict:
    tipo = p.tipo if p.tipo != "GPMultiValue" else p.subtipo
    base = {"title": p.rotulo, "description": p.descricao, "x-tipo-gp": p.tipo_gp}
    if tipo == "GPString":
        base.update({"type": "string", "maxLength": 2000})
        if p.opcoes:
            base["enum"] = list(p.opcoes)
    elif tipo == "GPDouble" or tipo == "GPLong":
        base["type"] = "number" if tipo == "GPDouble" else "integer"
        if p.minimo is not None:
            base["minimum"] = p.minimo
        if p.maximo is not None:
            base["maximum"] = p.maximo
    elif tipo == "GPBoolean":
        base["type"] = "boolean"
    elif tipo == "GPLinearUnit":
        base.update({"type": "object", "required": ["distance"], "additionalProperties": False,
                     "properties": {"distance": {"type": "number", "minimum": 0},
                                    "units": {"type": "string", "enum": sorted(UNIDADES_LINEARES)}}})
    elif tipo == "GPDate":
        base.update({"type": "string", "format": "date"})
    else:
        base.update({"type": "string", "format": "uuid", "x-item-familia": "camada" if tipo.startswith("GPFeature")
                     else "raster"})
    if p.padrao is not None:
        base["default"] = p.padrao
    if p.tipo == "GPMultiValue":
        return {"type": "array", "items": base, "title": p.rotulo, "x-tipo-gp": p.tipo_gp}
    return base


def esquema_json(f: Ferramenta) -> dict:
    """JSON Schema dos parâmetros de entrada (o formulário do navegador é gerado daqui)."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object", "additionalProperties": False,
        "required": [p.nome for p in f.entradas if p.obrigatorio and p.padrao is None],
        "properties": {p.nome: _esquema_de(p) for p in f.entradas},
    }


def descrever(f: Ferramenta) -> dict:
    return {
        "nome": f.nome, "titulo": f.titulo, "categoria": f.categoria, "descricao": f.descricao, "versao": f.versao,
        "parametros": [{"nome": p.nome, "tipo": p.tipo_gp, "rotulo": p.rotulo, "direcao": p.direcao,
                        "obrigatorio": p.obrigatorio, "padrao": p.padrao, "descricao": p.descricao,
                        "opcoes": list(p.opcoes), "minimo": p.minimo, "maximo": p.maximo} for p in f.parametros],
        "limites": f.limites, "esquema": esquema_json(f),
        "gpserver": f"/rest/services/{f.nome}/GPServer/{f.nome}",
    }


def _valor_gp(p: Parametro, valor):
    if valor is None:
        return None
    if p.tipo == "GPLinearUnit" and isinstance(valor, dict):
        return {"distance": valor.get("distance"), "units": valor.get("units", "esriMeters")}
    return valor


def descrever_gp(f: Ferramenta) -> dict:
    """Descritor da tarefa no vocabulário do GPServer (gp-task da referência REST da Esri)."""
    return {
        "name": f.nome, "displayName": f.titulo, "category": f.categoria, "description": f.descricao,
        "helpUrl": "", "executionType": "esriExecutionTypeAsynchronous",
        "parameters": [{
            "name": p.nome, "dataType": p.tipo_gp, "displayName": p.rotulo, "description": p.descricao,
            "direction": "esriGPParameterDirectionInput" if p.direcao == "entrada"
            else "esriGPParameterDirectionOutput",
            "defaultValue": _valor_gp(p, p.padrao), "parameterType": "esriGPParameterTypeRequired"
            if (p.obrigatorio and p.direcao == "entrada" and p.padrao is None) else "esriGPParameterTypeOptional",
            "category": "", "choiceList": list(p.opcoes),
        } for p in f.parametros],
    }


def parametros_de_formulario_gp(f: Ferramenta, crus: dict) -> dict:
    """Um cliente Esri manda cada parâmetro como texto (JSON para os compostos) na querystring ou no form,
    junto com f/token/env:*; devolve só o que é parâmetro da ferramenta, já decodificado."""
    conhecidos = {p.nome for p in f.entradas}
    saida = {}
    for chave, valor in crus.items():
        if chave in ("f", "token", "returnZ", "returnM", "returnTrueCurves", "context") or chave.startswith("env:"):
            continue
        if chave not in conhecidos:
            raise ErroParametro(chave, "parâmetro desconhecido")
        if isinstance(valor, str) and valor[:1] in ("{", "["):
            try:
                valor = json.loads(valor)
            except ValueError as e:
                raise ErroParametro(chave, "JSON inválido") from e
        saida[chave] = valor
    return saida
