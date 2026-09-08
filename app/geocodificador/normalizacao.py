"""Normalização de endereço brasileiro (item L2-11-b-geocodificador-brasil, ADR 0013 seção 3).

Duas camadas, de propósito separadas:
  1. Dobra de acento/caixa (unaccent + upper) — feita SEMPRE em SQL (`public.unaccent`), nunca em Python, para
     que o valor gravado em `plat.geo_endereco.logradouro_norm` (carga) e o valor comparado na consulta (busca)
     passem pela MESMA função; duplicar o dicionário de acentuação em Python divergiria da versão do unaccent
     instalada no Postgres (armadilha nomeada no ADR).
  2. Expansão de abreviação e achatamento de pontuação/ordinal — feita aqui, em Python, porque não existe
     função de banco para isso: dicionário fechado de abreviações de tipo de logradouro e de preposição comuns
     no cadastro do IBGE/Correios, e parsing de endereço em linha única (equivalente ao `SingleLine` do Esri).
"""

import re

# tipo de logradouro: abreviação (sem ponto, maiúscula) -> forma completa usada pelo IBGE em NOM_TIPO_SEGLOGR.
# fonte: Dicionário CNEFE 2022 (vocabulário fechado do IBGE) + abreviação postal comum (Correios/ECT).
ABREVIACOES_TIPO_LOGRADOURO = {
    "R": "RUA", "RUA": "RUA",
    "AV": "AVENIDA", "AVEN": "AVENIDA",
    "AL": "ALAMEDA", "ALM": "ALAMEDA",
    "TRAV": "TRAVESSA", "TRV": "TRAVESSA", "TR": "TRAVESSA",
    "ROD": "RODOVIA",
    "EST": "ESTRADA",
    "PC": "PRACA", "PCA": "PRACA", "PRC": "PRACA",
    "LGO": "LARGO", "LG": "LARGO",
    "VL": "VILA", "VLA": "VILA",
    "JD": "JARDIM", "JRD": "JARDIM",
    "RES": "RESIDENCIAL",
    "COND": "CONDOMINIO",
    "QD": "QUADRA",
    "LT": "LOTE",
    "VD": "VIADUTO",
    "TUN": "TUNEL",
    "STR": "SETOR",
}
# preposições/artigos que o CNEFE mantém mas que a busca deve tolerar ausentes/presentes (não removidos do
# valor gravado; usados só para relaxar a comparação quando o usuário digita sem eles).
PREPOSICOES = {"DE", "DA", "DO", "DAS", "DOS", "E"}

_ORDINAL = re.compile(r"(\d+)\s*[ºª°]")
_PONTUACAO = re.compile(r"[.,;:/\\]+")
_ESPACOS = re.compile(r"\s+")
_TOKEN = re.compile(r"[A-ZÀ-Ú0-9]+", re.UNICODE)

# CEP: 8 dígitos, com ou sem hífen (NNNNN-NNN); UF: sigla de 2 letras da lista fechada do IBGE.
_CEP = re.compile(r"\b(\d{5})-?(\d{3})\b")
_UF_VALIDAS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI",
    "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
}
_NUMERO = re.compile(r"\b(\d{1,6})\b")


def expandir_abreviacoes(texto: str) -> str:
    """Ordinal 1º/1°/1ª -> 1; pontuação -> espaço; 1ª palavra reconhecida como tipo de logradouro expandida
    (R. -> RUA); espaços colapsados. Não mexe em acento/caixa (isso é unaccent() em SQL)."""
    if not texto:
        return ""
    t = _ORDINAL.sub(r"\1", texto)
    t = _PONTUACAO.sub(" ", t)
    t = _ESPACOS.sub(" ", t).strip()
    palavras = t.split(" ")
    if palavras:
        primeira = palavras[0].upper()
        if primeira in ABREVIACOES_TIPO_LOGRADOURO:
            palavras[0] = ABREVIACOES_TIPO_LOGRADOURO[primeira]
    return " ".join(palavras)


def extrair_cep(texto: str) -> str | None:
    m = _CEP.search(texto)
    return f"{m.group(1)}{m.group(2)}" if m else None


def extrair_uf(texto: str) -> str | None:
    """UF isolada (2 letras maiúsculas, palavra inteira) em qualquer posição — tipicamente o último token."""
    for tok in reversed(_TOKEN.findall(texto.upper())):
        if tok in _UF_VALIDAS:
            return tok
    return None


class EnderecoLivre:
    """Resultado do parsing de uma linha única (equivalente ao `SingleLine` do Esri; ADR 0013 seção 3.2)."""

    __slots__ = ("logradouro", "numero", "bairro", "municipio", "uf", "cep", "bruto")

    def __init__(self, logradouro, numero, bairro, municipio, uf, cep, bruto):
        self.logradouro = logradouro
        self.numero = numero
        self.bairro = bairro
        self.municipio = municipio
        self.uf = uf
        self.cep = cep
        self.bruto = bruto

    def __repr__(self):
        return (
            f"EnderecoLivre(logradouro={self.logradouro!r}, numero={self.numero!r}, bairro={self.bairro!r}, "
            f"municipio={self.municipio!r}, uf={self.uf!r}, cep={self.cep!r})"
        )


def analisar_linha_unica(texto: str) -> EnderecoLivre:
    """Heurística de parsing por vírgula (o formato mais comum em correspondência/formulário BR):
    'Logradouro, numero, Bairro, Município - UF, CEP' — todos os campos além do logradouro são opcionais e
    detectados por padrão (CEP = 8 dígitos; UF = sigla de 2 letras da lista fechada; número = 1º inteiro isolado
    que sobra depois de CEP/UF removidos). Segmentos que sobram viram bairro/município pela ORDEM (penúltimo
    segmento de texto = município quando há um "- UF" colado nele; o de antes = bairro, se houver 3+)."""
    bruto = texto
    cep = extrair_cep(texto)
    uf = extrair_uf(texto)
    sem_cep = _CEP.sub(" ", texto)
    segmentos = [expandir_abreviacoes(s) for s in sem_cep.split(",")]
    segmentos = [s for s in segmentos if s]

    municipio = None
    if segmentos:
        for i in range(len(segmentos) - 1, -1, -1):
            m = re.match(r"^(.*?)\s*-\s*([A-Za-zÀ-ú]{2})$", segmentos[i])
            if m and m.group(2).upper() in _UF_VALIDAS:
                municipio = m.group(1).strip()
                segmentos.pop(i)
                if uf is None:
                    uf = m.group(2).upper()
                break
        else:
            # sem "- UF" explícito: se a UF foi achada solta como último segmento/token, o segmento anterior é
            # o município
            if uf and segmentos and segmentos[-1].strip().upper() == uf:
                segmentos.pop()
                if segmentos:
                    municipio = segmentos.pop()

    numero = None
    logradouro = segmentos[0] if segmentos else expandir_abreviacoes(texto)
    bairro = None
    if len(segmentos) >= 2:
        # procura o número no 2º segmento (uso mais comum: "Rua X, 123")
        m = _NUMERO.search(segmentos[1])
        if m:
            numero = int(m.group(1))
            resto = _NUMERO.sub(" ", segmentos[1]).strip()
            if resto:
                bairro = resto
            if len(segmentos) >= 3:
                bairro = segmentos[2] if bairro is None else f"{bairro} {segmentos[2]}".strip()
        else:
            bairro = segmentos[1]
            if len(segmentos) >= 3:
                bairro = f"{bairro} {segmentos[2]}".strip()
    if numero is None:
        m = _NUMERO.search(logradouro)
        if m and not logradouro[: m.start()].strip().isdigit():
            # número colado no fim do próprio logradouro ("Rua X 123") só quando não é o logradouro inteiro
            resto_antes = logradouro[: m.start()].strip()
            if resto_antes:
                numero = int(m.group(1))
                logradouro = resto_antes

    return EnderecoLivre(logradouro=logradouro, numero=numero, bairro=bairro, municipio=municipio, uf=uf,
                          cep=cep, bruto=bruto)
