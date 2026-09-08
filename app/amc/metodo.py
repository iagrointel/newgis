"""Exportação e importação do método do motor multicritério (item L3-01-i-exportacao-metodo).

O documento é o método em forma canônica: modelo (fatores, pesos, vetos, combinador, política de
dado ausente, gama), a entrada bruta que ele avaliou, as camadas de entrada com sha256 e contagem,
o resultado quando houve aplicação, versão do motor, data e o sha256 do próprio documento. O PDF
do relatório é gerado DESTE documento e só dele: nenhum número entra no PDF que não esteja no JSON.

Regras do documento:

- números em ponto flutuante são normalizados a 4 decimais NA CRIAÇÃO (o cálculo é interno em
  precisão dupla; o documento é o registro do que se usou e do que se achou);
- o hash é o sha256 da serialização canônica (chaves ordenadas, separadores mínimos) do documento
  SEM o próprio campo ``sha256`` — reimportar o documento sem alteração recria o modelo com o
  MESMO hash; alterar um peso muda o hash e a importação recusa (``documento_alterado``);
- o módulo é PURO: não abre banco, não usa relógio (``gerado_em`` entra por parâmetro), não lê
  arquivo.
"""

from __future__ import annotations

import hashlib
import json
import re

from app import versao
from app.amc.combinacao import AVISO_PESOS, COMBINADORES, POLITICAS_AUSENTE

FORMATO = "plat/amc_metodo"
VERSAO_DOCUMENTO = 1
DECIMAIS = 4
ESCALA_MIN, ESCALA_MAX = 0.0, 100.0

TRIAGEM = "triagem: sinal, não prova"
RESSALVA_PROXIES = "cada camada de entrada é proxy declarado do critério, não a medição direta do fenômeno"
RESSALVA_PROXIES_AUSENTE = (
    "camadas de entrada sem sha256 declarado: proveniência do conteúdo não está registrada neste método"
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_NUMERO_EM_TEXTO = re.compile(r"-?\d+(?:\.\d+)?")


class ErroMetodo(ValueError):
    """Erro de contrato do documento de método. `codigo` é curto e estável; `mensagem` é a frase."""

    def __init__(self, codigo: str, mensagem: str, detalhe: object = None) -> None:
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem
        self.detalhe = detalhe


def _num(x) -> float:
    """Normaliza um número do documento: 4 decimais, sem -0.0."""
    v = round(float(x), DECIMAIS)
    return 0.0 if v == 0 else v


def _canonico(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def hash_canonico(documento: dict) -> str:
    """sha256 da serialização canônica do documento SEM o próprio campo ``sha256``."""
    corpo = {k: v for k, v in documento.items() if k != "sha256"}
    return hashlib.sha256(_canonico(corpo).encode("utf-8")).hexdigest()


def _valida_modelo(modelo: dict) -> dict:
    if not isinstance(modelo, dict):
        raise ErroMetodo("modelo_invalido", "o modelo do método é um objeto com fatores, pesos e vetos")
    fatores = modelo.get("fatores")
    if not isinstance(fatores, list) or not fatores or not all(isinstance(f, str) and f for f in fatores):
        raise ErroMetodo("fatores_ausentes", "o modelo precisa de uma lista não vazia de fatores (texto)")
    if len(set(fatores)) != len(fatores):
        raise ErroMetodo("fator_duplicado", "o mesmo fator aparece mais de uma vez no modelo")
    pesos = modelo.get("pesos")
    if not isinstance(pesos, dict) or set(pesos) != set(fatores):
        raise ErroMetodo(
            "peso_fora_da_lista",
            "os pesos precisam cobrir exatamente os fatores do modelo",
            {"faltando": sorted(set(fatores) - set(pesos or {})), "sobrando": sorted(set(pesos or {}) - set(fatores))},
        )
    valores = {}
    for f, p in pesos.items():
        try:
            v = _num(p)
        except (TypeError, ValueError):
            raise ErroMetodo("peso_invalido", f"peso do fator '{f}' não é número") from None
        if v < 0:
            raise ErroMetodo("peso_negativo", f"peso do fator '{f}' é negativo; peso é multiplicador ≥ 0")
        valores[f] = v
    if sum(valores.values()) <= 0:
        raise ErroMetodo("soma_de_pesos_zero", "a soma dos pesos é zero; não há como normalizar")
    vetos_brutos = modelo.get("vetos") or {}
    if not isinstance(vetos_brutos, dict) or not set(vetos_brutos) <= set(fatores):
        raise ErroMetodo(
            "veto_fora_da_lista",
            "todo veto precisa ser de um fator do modelo",
            {"sobrando": sorted(set(vetos_brutos) - set(fatores))},
        )
    vetos = {}
    for f, v in vetos_brutos.items():
        try:
            fv = _num(v)
        except (TypeError, ValueError):
            raise ErroMetodo("veto_invalido", f"veto do fator '{f}' não é número") from None
        if not 0.0 <= fv <= 1.0:
            raise ErroMetodo("veto_fora_da_faixa", f"veto do fator '{f}' fora da faixa 0-1: {fv}")
        vetos[f] = fv
    combinador = modelo.get("combinador", "soma_ponderada")
    if combinador not in COMBINADORES:
        raise ErroMetodo(
            "combinador_desconhecido",
            "combinador desconhecido: " + str(combinador),
            {"aceitos": sorted(COMBINADORES)},
        )
    politica = modelo.get("politica_ausente", "excluir")
    if politica not in POLITICAS_AUSENTE:
        raise ErroMetodo(
            "politica_ausente_desconhecida",
            "política de dado ausente desconhecida: " + str(politica),
            {"aceitas": sorted(POLITICAS_AUSENTE)},
        )
    gama = _num(modelo.get("gama", 0.5))
    if not 0.0 <= gama <= 1.0:
        raise ErroMetodo("gama_fora_da_faixa", "o parâmetro gama tem de estar entre 0 e 1")
    return {
        "fatores": list(fatores),
        "contagem_de_fatores": len(fatores),
        "pesos": valores,
        "pesos_normalizados": {f: _num(v / sum(valores.values())) for f, v in valores.items()},
        "vetos": vetos,
        "combinador": combinador,
        "descricao_combinador": COMBINADORES[combinador],
        "politica_ausente": politica,
        "descricao_politica": POLITICAS_AUSENTE[politica],
        "gama": gama,
        "escala": {"min": ESCALA_MIN, "max": ESCALA_MAX},
    }


def _valida_camadas(camadas, fatores: list[str]) -> dict:
    if camadas is None:
        camadas = []
    if not isinstance(camadas, list):
        raise ErroMetodo("camadas_invalidas", "camadas é a lista das camadas de entrada, uma por fator")
    por_fator = []
    for c in camadas:
        if not isinstance(c, dict) or set(c) - {"fator", "nome", "sha256"} or "fator" not in c:
            raise ErroMetodo("camada_invalida", "cada camada declara fator, nome e sha256 opcional")
        if c["fator"] not in fatores:
            raise ErroMetodo(
                "camada_fora_do_modelo",
                "camada de entrada de fator que o modelo não declara: " + str(c["fator"]),
                {"fator": c["fator"], "fatores": fatores},
            )
        sha = c.get("sha256")
        if sha is not None and not (isinstance(sha, str) and _SHA256.match(sha)):
            raise ErroMetodo("sha256_invalido", "sha256 de camada precisa ser hexadecimal de 64 caracteres")
        por_fator.append({"fator": c["fator"], "nome": str(c.get("nome") or c["fator"]), "sha256": sha})
    return {"contagem": len(por_fator), "por_fator": por_fator}


def _valida_entrada(entrada, fatores: list[str]) -> dict:
    """Matriz bruta avaliada pelo método (unidade × fator, None = sem dado). O PDF do relatório só
    mostra números daqui, por isso a entrada entra no documento."""
    if not isinstance(entrada, dict) or not isinstance(entrada.get("matriz"), list) or not entrada["matriz"]:
        raise ErroMetodo("entrada_invalida", "a entrada é um objeto com a matriz bruta (lista de linhas)")
    matriz = []
    for linha in entrada["matriz"]:
        if not isinstance(linha, list) or len(linha) != len(fatores):
            raise ErroMetodo(
                "matriz_incompativel",
                f"cada linha da matriz bruta tem de ter {len(fatores)} valores, um por fator",
            )
        nova = []
        for v in linha:
            if v is None:
                nova.append(None)
            else:
                try:
                    x = _num(v)
                except (TypeError, ValueError):
                    raise ErroMetodo("valor_invalido", "valor da matriz bruta não é número nem null") from None
                if not ESCALA_MIN <= x <= ESCALA_MAX:
                    raise ErroMetodo(
                        "valor_fora_da_escala",
                        f"valor bruto fora da escala {ESCALA_MIN:g}-{ESCALA_MAX:g}: {x}",
                    )
                nova.append(x)
        matriz.append(nova)
    cobertura_fator = {}
    for i, f in enumerate(fatores):
        com_dado = [linha[i] for linha in matriz if linha[i] is not None]
        cobertura_fator[f] = _num(len(com_dado) / len(matriz)) if matriz else 0.0
    return {"unidades": len(matriz), "ids_unidades": list(range(len(matriz))), "matriz": matriz,
            "cobertura_por_fator": cobertura_fator}


def _valida_transformacoes(transformacoes, fatores: list[str]) -> dict:
    """Transformação declarada por fator (texto: o que a camada bruta virou nota 0-100). O produtor
    do método informa quando as tem; o documento canônico carrega o lugar delas."""
    if transformacoes is None:
        return {"contagem": 0, "por_fator": {}}
    if not isinstance(transformacoes, dict) or not set(transformacoes) <= set(fatores):
        raise ErroMetodo(
            "transformacao_fora_do_modelo",
            "toda transformação precisa ser de um fator do modelo",
            {"sobrando": sorted(set(transformacoes or {}) - set(fatores))},
        )
    return {"contagem": len(transformacoes),
            "por_fator": {f: str(t) for f, t in transformacoes.items()}}


def metodo_canonico(
    *,
    nome: str,
    modelo: dict,
    camadas=None,
    entrada=None,
    resultado=None,
    transformacoes=None,
    gerado_em: str,
) -> dict:
    """Monta o documento canônico do método. `gerado_em` vem do chamador (o módulo é puro).
    `resultado` é a forma serializável de `app.amc.combinacao.Resultado.como_dicionario()`.
    `transformacoes` é opcional: {fator: texto} com o que a camada bruta virou nota do fator."""
    if not isinstance(nome, str) or not nome.strip():
        raise ErroMetodo("nome_ausente", "o método precisa de um nome")
    m = _valida_modelo(modelo)
    c = _valida_camadas(camadas, m["fatores"])
    t = _valida_transformacoes(transformacoes, m["fatores"])
    e = _valida_entrada(entrada or {"matriz": [[None] * len(m["fatores"])]}, m["fatores"])
    res = None
    if resultado is not None:
        if not isinstance(resultado, dict):
            raise ErroMetodo("resultado_invalido", "resultado é o dicionário de como_dicionario() da combinação")
        res = {
            "ids_unidades": list(range(e["unidades"])) if e else [],
            "fav": [_num(v) if v is not None else None for v in resultado.get("fav", [])],
            "cobertura": [_num(v) for v in resultado.get("cobertura", [])],
            "vetado": [bool(v) for v in resultado.get("vetado", [])],
            "motivo": [None if mo is None else str(mo) for mo in resultado.get("motivo", [])],
            "aviso_pesos": resultado.get("aviso_pesos", AVISO_PESOS),
            "observacoes": [str(o) for o in resultado.get("observacoes", [])],
        }
        if len(res["fav"]) != e["unidades"]:
            raise ErroMetodo(
                "resultado_incompativel",
                f"o resultado tem {len(res['fav'])} notas para {e['unidades']} unidades de entrada",
            )
    documento = {
        "formato": FORMATO,
        "versao": VERSAO_DOCUMENTO,
        "nome": nome.strip(),
        "gerado_em": str(gerado_em),
        "motor": {"versao": versao.versao(), "sha": versao.git_sha_curto()},
        "aviso_pesos": res["aviso_pesos"] if res else AVISO_PESOS,
        "modelo": m,
        "camadas": c,
        "transformacoes": t,
        "entrada": e,
        "resultado": res,
        "ressalvas": [AVISO_PESOS, TRIAGEM, RESSALVA_PROXIES]
        + ([RESSALVA_PROXIES_AUSENTE]
           if any(campo["sha256"] is None for campo in c["por_fator"]) else []),
    }
    documento["sha256"] = hash_canonico(documento)
    return documento


def importar_metodo(documento: dict) -> dict:
    """Revalida o documento e confere o hash: importar o documento SEM alteração recria o modelo
    com o MESMO hash; qualquer alteração de conteúdo muda o hash calculado e é recusada."""
    if not isinstance(documento, dict) or documento.get("formato") != FORMATO:
        raise ErroMetodo("formato_desconhecido", f"documento não é {FORMATO}")
    if documento.get("versao") != VERSAO_DOCUMENTO:
        raise ErroMetodo("versao_desconhecida", f"versão de documento desconhecida: {documento.get('versao')}")
    guardado = documento.get("sha256")
    if not (isinstance(guardado, str) and _SHA256.match(guardado)):
        raise ErroMetodo("sha256_invalido", "o documento não traz o próprio sha256 (hexadecimal de 64)")
    recalculado = hash_canonico(documento)
    if recalculado != guardado:
        raise ErroMetodo(
            "documento_alterado",
            "o conteúdo do documento não corresponde ao sha256 gravado nele: foi alterado depois da exportação",
            {"gravado": guardado, "recalculado": recalculado},
        )
    importado = dict(documento)
    importado["modelo"] = _valida_modelo(documento.get("modelo") or {})
    fatores = importado["modelo"]["fatores"]
    importado["camadas"] = _valida_camadas((documento.get("camadas") or {}).get("por_fator"), fatores)
    importado["transformacoes"] = _valida_transformacoes(
        (documento.get("transformacoes") or {}).get("por_fator"), fatores
    )
    importado["entrada"] = _valida_entrada(documento.get("entrada") or {"matriz": []}, fatores)
    return importado


def numeros_do_documento(documento, _achados=None) -> set[float]:
    """Todo número do documento, inclusive os que aparecem DENTRO de textos (datas, sha curto do
    motor) e DENTRO de chaves (o '256' de 'sha256'). É o universo com que o teste confere os
    números impressos no PDF: número no PDF que não está aqui foi digitado, e o portão reprova."""
    if _achados is None:
        _achados = set()
    if isinstance(documento, bool):
        return _achados
    if isinstance(documento, (int, float)):
        _achados.add(_num(documento))
    elif isinstance(documento, str):
        for t in _NUMERO_EM_TEXTO.findall(documento):
            _achados.add(_num(t))
    elif isinstance(documento, dict):
        for k, v in documento.items():
            numeros_do_documento(k, _achados)
            numeros_do_documento(v, _achados)
    elif isinstance(documento, list):
        for v in documento:
            numeros_do_documento(v, _achados)
    return _achados


def confere_pdf(texto_pdf: str, documento: dict) -> bool:
    """O PDF é deste método? O relatório imprime o sha256 do documento; um PDF gerado de outra
    versão do método (peso alterado, hash diferente) NÃO confere. É o que impede o PDF antigo de
    ser aceito como do modelo novo. O texto é limpo de espaço e quebra de linha antes da busca:
    o relatório imprime o hash em duas linhas de 32 e a extração as devolve separadas."""
    colado = re.sub(r"\s+", "", texto_pdf.lower())
    hexes = set(re.findall(r"[0-9a-f]{64}", colado))
    return documento.get("sha256", "").lower() in hexes
