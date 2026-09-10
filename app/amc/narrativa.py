"""Narrativa determinística do resultado do motor AMC (item L3-20-narrativa-de-resultado).

Resumo textual das top-N unidades e do modelo, gerado por TEMPLATE a partir do documento canônico
``plat/amc_metodo`` (o formato do item L3-01-i). Nenhum modelo de linguagem afirma fato aqui: cada
frase é escrita por este módulo e cada número impresso existe no documento — o revisor automático
(``revisar``) marca a frase que traz número que não decorre dele (a refutação do item).

Regra de escrita de 03/09 (vale para todo texto a cliente): uma ideia por frase; número com
universo, base e fonte — neste texto a fonte é o próprio documento e o universo aparece nas formas
"X de 100" (escala) e "X de Y" (total de unidades); zero metáfora, zero gíria, zero superlativo,
sem exclamação; termo técnico com definição na primeira vez (as descrições do combinador e da
política vêm do documento, não daqui).

O módulo é PURO: não abre banco, não lê arquivo, não usa relógio. A varredura de números espelha a
do módulo do documento canônico (``app.amc.metodo.numeros_do_documento`` na trilha que o produziu):
valores, números DENTRO de textos (datas, sha) e DENTRO de chaves (o "256" de "sha256").
"""

from __future__ import annotations

import re

FORMATO = "plat/amc_metodo"
DECIMAIS = 4
TOP_N_PADRAO = 3

# Termos que a regra de escrita de 03/09 proíbe em texto a cliente: metáfora, gíria de casa,
# superlativo de elogio, anglicismo com substituto em português e promessa de entrega.
LISTA_PROIBIDA = frozenset({
    "maquiagem", "acolchambrado", "diamante", "testemunha", "cauda", "esquenta", "acender",
    "viaja", "impressionante", "robusto", "incrível", "aproximadamente", "cerca de",
    "lift", "recall", "prior", "band", "queue", "score", "você recebe",
})

_NUMERO = re.compile(r"-?\d+(?:[.,]\d+)?")


class ErroNarrativa(ValueError):
    """Erro de contrato da narrativa. `codigo` é curto e estável; `mensagem` é a frase."""

    def __init__(self, codigo: str, mensagem: str, detalhe: object = None) -> None:
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem
        self.detalhe = detalhe


def _num(x) -> float:
    """Normaliza um número: 4 decimais, sem -0.0. O texto usa a MESMA normalização do documento."""
    v = round(float(x), DECIMAIS)
    return 0.0 if v == 0 else v


def _fmt(v) -> str:
    """O número como o documento o guarda: inteiro sem casa decimal, senão 4 casas com vírgula."""
    f = _num(v)
    if f == int(f):
        return str(int(f))
    return f"{f:.{DECIMAIS}f}".rstrip("0").rstrip(".").replace(".", ",")


def numeros_do_documento(documento, _achados=None) -> set[float]:
    """Todo número do documento, inclusive os que aparecem DENTRO de textos e DENTRO de chaves."""
    if _achados is None:
        _achados = set()
    if isinstance(documento, bool):
        return _achados
    if isinstance(documento, (int, float)):
        _achados.add(_num(documento))
    elif isinstance(documento, str):
        for t in _NUMERO.findall(documento):
            _achados.add(_num(t.replace(",", ".")))
    elif isinstance(documento, dict):
        for chave, valor in documento.items():
            numeros_do_documento(chave, _achados)
            numeros_do_documento(valor, _achados)
    elif isinstance(documento, list):
        for valor in documento:
            numeros_do_documento(valor, _achados)
    return _achados


def _valida(documento: dict) -> dict:
    if not isinstance(documento, dict):
        raise ErroNarrativa("documento_invalido", "a narrativa narra o documento canônico do método")
    modelo = documento.get("modelo")
    if not isinstance(modelo, dict) or not modelo.get("fatores"):
        raise ErroNarrativa("documento_invalido", "o documento não traz o modelo com os fatores")
    faltando = [c for c in ("nome", "versao", "gerado_em", "motor", "sha256", "aviso_pesos")
                if c not in documento]
    faltando += ["modelo." + c for c in
                 ("contagem_de_fatores", "pesos_normalizados", "combinador", "descricao_combinador",
                  "politica_ausente", "descricao_politica", "vetos", "escala") if c not in modelo]
    if faltando:
        raise ErroNarrativa("documento_invalido", "o documento não traz campos de que o texto precisa",
                            {"faltando": faltando})
    entrada = documento.get("entrada")
    if not isinstance(entrada, dict) or not isinstance(entrada.get("matriz"), list):
        raise ErroNarrativa("documento_invalido", "o documento não traz a entrada com a matriz bruta")
    n = len(modelo["fatores"])
    for linha in entrada["matriz"]:
        if not isinstance(linha, list) or len(linha) != n:
            raise ErroNarrativa(
                "matriz_incompativel",
                f"cada linha da matriz tem de ter {n} valores, um por fator",
            )
    resultado = documento.get("resultado")
    if resultado is not None:
        if not isinstance(resultado, dict):
            raise ErroNarrativa("documento_invalido", "resultado tem de ser o dicionário do documento")
        faltando_res = [c for c in ("fav", "ids_unidades", "cobertura", "vetado") if c not in resultado]
        if faltando_res:
            raise ErroNarrativa("documento_invalido", "o resultado não traz campos de que o texto precisa",
                                {"faltando": faltando_res})
        if len(resultado["fav"]) != len(entrada["matriz"]):
            raise ErroNarrativa(
                "resultado_incompativel",
                f"o resultado tem {len(resultado['fav'])} notas para {len(entrada['matriz'])} unidades",
            )
    return documento


def _frase_inicial(texto: str) -> str:
    return texto[0].upper() + texto[1:] if texto else texto


def _contribuinte(documento: dict, i: int) -> tuple[str, float, float]:
    """O fator de maior contribuição (peso normalizado × valor) na unidade i, com valor e peso.
    Empate resolve pela ordem dos fatores no modelo. São números do documento, não opinião."""
    modelo = documento["modelo"]
    linha = documento["entrada"]["matriz"][i]
    melhor = None
    for j, fator in enumerate(modelo["fatores"]):
        valor = linha[j]
        if valor is None:
            continue
        contribuição = modelo["pesos_normalizados"][fator] * valor
        if melhor is None or contribuição > melhor[0]:
            melhor = (contribuição, fator, valor, modelo["pesos_normalizados"][fator])
    if melhor is None:
        raise ErroNarrativa("sem_dado_na_unidade", f"a unidade {i} não tem dado em fator nenhum")
    return melhor[1], melhor[2], melhor[3]


def narrar(documento: dict, top_n: int = TOP_N_PADRAO) -> str:
    """Gera o texto do resumo: o modelo, as top-N unidades por nota e as ressalvas do documento.
    Uma ideia por frase, um número só com origem no documento."""
    _valida(documento)
    if not isinstance(top_n, int) or top_n < 1:
        raise ErroNarrativa("top_n_invalido", "top_n é um inteiro maior ou igual a 1")
    modelo = documento["modelo"]
    resultado = documento.get("resultado")
    fatores = modelo["fatores"]
    linhas: list[str] = []

    linhas.append(f"Resumo do método {documento['nome']}.")
    linhas.append(f"O documento é o {FORMATO}, versão {documento['versao']}, "
                  f"gerado em {documento['gerado_em']}.")
    linhas.append(f"O texto vale exatamente para o conteúdo com o sha256 {documento['sha256']}.")
    linhas.append(f"O motor é a versão {documento['motor']['versao']}, declarada no documento.")
    linhas.append(f"O modelo combina {modelo['contagem_de_fatores']} fatores.")
    if len(fatores) == 1:
        linhas.append(f"O fator do modelo é o {fatores[0]}.")
    else:
        linhas.append(f"Os fatores são o {', o '.join(fatores[:-1])} e o {fatores[-1]}.")
    linhas.append(f"O combinador é o {modelo['combinador']}.")
    linhas.append(f"A definição gravada dele no documento é \"{modelo['descricao_combinador']}\".")
    linhas.append(f"O dado ausente segue a política {modelo['politica_ausente']}.")
    linhas.append(f"A política gravada no documento é \"{modelo['descricao_politica']}\".")
    linhas.append(f"A escala das notas vai de {_fmt(modelo['escala']['min'])} "
                  f"a {_fmt(modelo['escala']['max'])}.")
    for fator, fracao in modelo["vetos"].items():
        linhas.append(f"O modelo declara restrição no fator {fator}, "
                      f"que veta a fração {_fmt(fracao)} da unidade.")
    if not modelo["vetos"]:
        linhas.append("O modelo não declara restrição de veto.")
    linhas.append(_frase_inicial(documento["aviso_pesos"]) + ".")

    if resultado is None:
        linhas.append("O método não foi aplicado a dado nenhum e não há nota a narrar.")
    else:
        notas = resultado["fav"]
        ordenadas = sorted(
            (i for i, nota in enumerate(notas) if nota is not None),
            key=lambda i: (-notas[i], resultado["ids_unidades"][i]),
        )
        linhas.append("Unidades com as maiores notas primeiro.")
        for i in ordenadas[:top_n]:
            ident = resultado["ids_unidades"][i]
            nota = notas[i]
            cobertura = resultado["cobertura"][i]
            linhas.append(f"A unidade {ident} tem nota {_fmt(nota)} "
                          f"de {_fmt(modelo['escala']['max'])}, com cobertura {_fmt(cobertura)}.")
            if resultado["vetado"][i]:
                linhas.append(f"A unidade {ident} está vetada por restrição declarada no modelo.")
                motivo = (resultado.get("motivo") or [None] * len(notas))[i]
                if motivo:
                    linhas.append(f"O motivo gravado no documento é \"{motivo}\".")
                continue
            fator, valor, peso = _contribuinte(documento, i)
            linhas.append(f"A nota tem essa magnitude porque o fator {fator}, "
                          f"de peso normalizado {_fmt(peso)}, tem valor {_fmt(valor)} nessa unidade.")
        linhas.append(f"O resultado cobre {len(notas)} unidades no documento.")
    emitidas = set(linhas)
    for ressalva in documento.get("ressalvas", []):
        frase = _frase_inicial(ressalva) + "."
        if frase in emitidas:
            continue
        emitidas.add(frase)
        linhas.append(frase)
    linhas.append("Este texto foi gerado por template a partir do documento, "
                  "sem modelo de linguagem.")
    return "\n".join(linhas)


def revisar(texto: str, documento: dict) -> list[dict]:
    """Revisor automático da regra de escrita de 03/09: marca, no texto, frase com número que não
    existe no documento (número_sem_origem), frase com termo da lista proibida (termo_proibido) e
    frase com exclamação ou interrogação (pontuacao_proibida). Devolve a lista das marcações."""
    if not isinstance(texto, str):
        raise ErroNarrativa("texto_invalido", "o texto a revisar é uma cadeia de caracteres")
    _valida(documento)
    universo = numeros_do_documento(documento)
    marcacoes: list[dict] = []
    partes = re.split(r"(?<=[.!?])\s+", texto)
    for frase in (p.strip() for p in partes):
        if not frase:
            continue
        for termo in sorted(LISTA_PROIBIDA):
            if re.search(rf"\b{re.escape(termo)}\b", frase, re.IGNORECASE):
                marcacoes.append({"frase": frase, "motivo": "termo_proibido", "termo": termo})
        if "!" in frase or "?" in frase:
            marcacoes.append({"frase": frase, "motivo": "pontuacao_proibida"})
        for bruto in _NUMERO.findall(frase):
            numero = _num(bruto.replace(",", "."))
            if numero not in universo:
                marcacoes.append({
                    "frase": frase,
                    "motivo": "numero_sem_origem",
                    "numero": numero,
                })
    return marcacoes
