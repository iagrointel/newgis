"""Leitura da TABELA enviada pelo usuário para geocodificar em lote (item L2-11-a-geocodificacao-csv):
CSV/TXT e XLSX. Três responsabilidades, todas sem tocar no banco:

  1. `colunas(dados, nome)`  -> os nomes de coluna do arquivo + uma PROPOSTA de mapeamento por nome de
     cabeçalho (logradouro, número, bairro, município, UF, CEP ou "endereço único"). A proposta é palpite,
     nunca decisão: a rota devolve, a tela mostra e o usuário confirma.
  2. `linhas(dados, mapeamento)` -> gerador de `LinhaTabela` com o número da linha NO ARQUIVO, os campos de
     endereço já separados e, quando a linha não dá para usar, o MOTIVO em português — a linha ruim vira uma
     linha de resultado com estado 'malformada', nunca uma exceção que derruba o lote inteiro. O que conta
     como malformada: linha com menos colunas do que o cabeçalho na posição mapeada, número que não é
     inteiro, célula que estoura o teto de texto e linha sem nenhum campo de endereço preenchido.
  3. `conferir_tamanho(bytes)` -> teto de tamanho medido nos bytes REAIS, antes de qualquer leitura.

O CSV é decodificado e o separador detectado pelo MESMO código da ingestão vetorial
(`app.ingestao.csv_normalizar`), para os dois caminhos de importação nunca divergirem na leitura do mesmo
arquivo. O XLSX é lido com openpyxl em modo `read_only` (linha a linha, sem carregar a planilha inteira).
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from dataclasses import dataclass, field

from app import limites
from app.ingestao.csv_normalizar import _decodificar as _decodificar_por_estatistica
from app.ingestao.csv_normalizar import _detectar_separador

CAMPOS = limites.GEOCOD_CAMPOS
TEXTO_MAX = limites.GEOCOD_CAMPO_TEXTO_MAX

# cabeçalho (normalizado: sem acento, minúsculo, sem pontuação) -> campo de endereço. Vocabulário fechado:
# o que aparece em planilha de cadastro brasileira. Nada aqui adivinha por conteúdo, só por nome de coluna.
SINONIMOS = {
    "endereco": "endereco", "endereco completo": "endereco", "enderecocompleto": "endereco",
    "logradouro completo": "endereco", "end": "endereco", "endereço": "endereco",
    "logradouro": "logradouro", "rua": "logradouro", "via": "logradouro", "av": "logradouro",
    "avenida": "logradouro", "nome do logradouro": "logradouro", "tipo e nome do logradouro": "logradouro",
    "numero": "numero", "num": "numero", "n": "numero", "nr": "numero", "no": "numero",
    "numero do imovel": "numero", "num endereco": "numero",
    "bairro": "bairro", "distrito": "bairro", "localidade": "bairro", "setor": "bairro",
    "municipio": "municipio", "cidade": "municipio", "nome do municipio": "municipio",
    "uf": "uf", "estado": "uf", "sigla uf": "uf", "unidade da federacao": "uf",
    "cep": "cep", "codigo postal": "cep",
}
_ACENTOS = str.maketrans("áàâãäéèêëíìîïóòôõöúùûüçÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ",
                          "aaaaaeeeeiiiiooooouuuucAAAAAEEEEIIIIOOOOOUUUUC")
_SO_DIGITO = re.compile(r"\d+")


class ArquivoGrandeDemais(ValueError):
    """Teto de bytes do arquivo (limites.GEOCOD_ARQUIVO_BYTES_MAX) estourado."""


class ArquivoIlegivel(ValueError):
    """Nem CSV nem XLSX legível (arquivo vazio, sem cabeçalho, zip que não é planilha)."""


class LinhasDemais(ValueError):
    """Teto de linhas (limites.GEOCOD_LINHAS_MAX) estourado."""


@dataclass
class LinhaTabela:
    n: int                       # número da linha no arquivo, 1 = primeira linha de dado (sem o cabeçalho)
    campos: dict                 # {logradouro, numero, bairro, municipio, uf, cep, endereco} já limpos
    motivo: str | None = None    # preenchido quando a linha é malformada; a linha ainda assim é devolvida
    avisos: list = field(default_factory=list)


def conferir_tamanho(bytes_arquivo: int) -> None:
    if bytes_arquivo > limites.GEOCOD_ARQUIVO_BYTES_MAX:
        mb = limites.GEOCOD_ARQUIVO_BYTES_MAX // (1024 * 1024)
        raise ArquivoGrandeDemais(
            f"arquivo de {bytes_arquivo / (1024 * 1024):.1f} MB acima do teto de {mb} MB desta instalação"
        )


def normalizar_cabecalho(nome: str) -> str:
    t = (nome or "").translate(_ACENTOS).lower()
    t = re.sub(r"[^a-z0-9]+", " ", t).strip()
    return re.sub(r"\s+", " ", t)


def e_xlsx(dados: bytes) -> bool:
    """Decide pelos BYTES, nunca pela extensão: zip cujo conteúdo tem a pasta `xl/` do OOXML."""
    return dados[:4] == b"PK\x03\x04" and _tem_planilha(dados)


def _tem_planilha(dados: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(dados)) as zf:
            return any(n.startswith("xl/") for n in zf.namelist())
    except (zipfile.BadZipFile, OSError):
        return False


def _decodificar(dados: bytes) -> str:
    """Bytes -> texto, na ordem que serve a UMA planilha de endereço brasileira:

      1. marca de ordem de byte (UTF-8/UTF-16), quando existe, decide sozinha;
      2. UTF-8 estrito;
      3. Windows-1252 (cp1252), que é o que o Excel em português grava quando o usuário salva "CSV";
      4. só então o palpite estatístico do `charset_normalizer` (o mesmo que a ingestão vetorial usa).

    O passo 3 existe por MEDIÇÃO desta sessão: um CSV latin-1 com 39 linhas de "Rua São João" foi lido pelo
    `charset_normalizer` como codificação asiática ("Rua S<CJK>o Jo<CJK>o"), porque `ã` repetido em bytes
    latin-1 é um par válido em várias codificações multibyte. Para o caminho da ingestão vetorial a ordem
    estatística continua valendo (lá o arquivo pode ser de qualquer origem); aqui o universo é planilha, e a
    codificação do Excel brasileiro vale mais do que a estatística.

    Fronteira: UTF-16 SEM marca de ordem de byte cai no passo 3 e vira texto errado. Por isso o passo 3 é
    pulado quando há byte zero no começo do arquivo, que é a assinatura prática de UTF-16 sem marca."""
    for bom, cod in ((b"\xef\xbb\xbf", "utf-8-sig"), (b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be")):
        if dados.startswith(bom):
            return dados.decode(cod)
    try:
        return dados.decode("utf-8")
    except UnicodeDecodeError:
        pass
    if b"\x00" not in dados[:4096]:
        try:
            return dados.decode("cp1252")
        except UnicodeDecodeError:
            pass
    return _decodificar_por_estatistica(dados)


def _limpar(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    return str(valor).strip()


def _cabecalho_e_corpo(dados: bytes):
    """Devolve (cabecalho: list[str], gerador de list[str]) para CSV ou XLSX, sem carregar tudo em memória
    duas vezes. Levanta ArquivoIlegivel quando não há cabeçalho."""
    if e_xlsx(dados):
        import openpyxl

        try:
            wb = openpyxl.load_workbook(io.BytesIO(dados), read_only=True, data_only=True)
        except (zipfile.BadZipFile, KeyError, OSError, ValueError) as e:
            raise ArquivoIlegivel(f"o arquivo XLSX não abriu: {e}") from e
        ws = wb.worksheets[0] if wb.worksheets else None
        if ws is None:
            raise ArquivoIlegivel("a planilha não tem nenhuma aba")
        iterador = ws.iter_rows(values_only=True)
        try:
            primeira = next(iterador)
        except StopIteration as e:
            raise ArquivoIlegivel("a planilha está vazia (sem cabeçalho)") from e
        cabecalho = [_limpar(c) for c in primeira]

        def corpo():
            for linha in iterador:
                yield [_limpar(c) for c in linha]

        return cabecalho, corpo()

    texto = _decodificar(dados)
    if not texto.strip():
        raise ArquivoIlegivel("o arquivo está vazio")
    separador = _detectar_separador(texto)
    leitor = csv.reader(io.StringIO(texto), delimiter=separador)
    try:
        cabecalho = [c.strip() for c in next(leitor)]
    except StopIteration as e:
        raise ArquivoIlegivel("o arquivo está vazio (sem cabeçalho)") from e
    if not any(cabecalho):
        raise ArquivoIlegivel("a primeira linha não parece um cabeçalho (todas as colunas vazias)")
    return cabecalho, leitor


def colunas(dados: bytes) -> dict:
    """Nomes de coluna do arquivo + proposta de mapeamento por nome de cabeçalho. Só a proposta — a decisão
    é do usuário (a rota devolve isto para a tela de mapeamento)."""
    cabecalho, _corpo = _cabecalho_e_corpo(dados)
    proposta: dict[str, str] = {}
    for nome in cabecalho:
        campo = SINONIMOS.get(normalizar_cabecalho(nome))
        if campo and campo not in proposta:
            proposta[campo] = nome
    return {"colunas": cabecalho, "mapeamento_proposto": proposta}


def conferir_mapeamento(mapeamento: dict, cabecalho: list[str]) -> None:
    """Todo campo mapeado tem de existir no cabeçalho, e pelo menos um campo que localize tem de estar lá."""
    desconhecidos = [c for c in mapeamento if c not in CAMPOS]
    if desconhecidos:
        raise ValueError(f"campo de endereço desconhecido: {sorted(desconhecidos)}; aceitos: {list(CAMPOS)}")
    faltando = [v for v in mapeamento.values() if v not in cabecalho]
    if faltando:
        raise ValueError(f"coluna inexistente no arquivo: {sorted(faltando)}; colunas: {cabecalho}")
    if not ({"endereco", "logradouro", "bairro", "municipio", "cep"} & set(mapeamento)):
        raise ValueError(
            "mapeie ao menos uma coluna de endereco, logradouro, bairro, municipio ou cep — só numero e uf "
            "não localizam nada"
        )


def linhas(dados: bytes, mapeamento: dict):
    """Gerador de LinhaTabela. Nunca levanta por causa de UMA linha: linha ruim vem com `motivo` preenchido
    (o chamador grava estado 'malformada' e segue). Levanta só o que impede o lote inteiro: arquivo ilegível
    (sem cabeçalho) e teto de linhas."""
    cabecalho, corpo = _cabecalho_e_corpo(dados)
    conferir_mapeamento(mapeamento, cabecalho)
    indice = {campo: cabecalho.index(coluna) for campo, coluna in mapeamento.items()}
    n = 0
    for bruta in corpo:
        n += 1
        if n > limites.GEOCOD_LINHAS_MAX:
            raise LinhasDemais(
                f"arquivo com mais de {limites.GEOCOD_LINHAS_MAX} linhas de dado; divida em partes"
            )
        if all(_limpar(c) == "" for c in bruta):
            yield LinhaTabela(n=n, campos={}, motivo="linha em branco")
            continue
        campos: dict = {}
        avisos: list[str] = []
        motivo = None
        for campo, i in indice.items():
            if i >= len(bruta):
                motivo = (f"a linha tem {len(bruta)} coluna(s) e o campo {campo!r} está na coluna "
                          f"{i + 1} do cabeçalho")
                continue
            valor = _limpar(bruta[i])
            if len(valor) > TEXTO_MAX:
                valor = valor[:TEXTO_MAX]
                avisos.append(f"valor de {campo!r} truncado em {TEXTO_MAX} caracteres")
            if valor == "":
                continue
            if campo == "numero":
                m = _SO_DIGITO.search(valor)
                if not m:
                    avisos.append(f"número {valor!r} não tem dígito; a linha foi geocodificada sem número")
                    continue
                numero = int(m.group(0)[:6])
                if m.group(0) != valor:
                    avisos.append(f"número {valor!r} lido como {numero}")
                campos["numero"] = numero
                continue
            if campo == "uf":
                valor = valor.upper()[:2]
            campos[campo] = valor
        if motivo is None and not campos:
            motivo = "nenhum campo de endereço preenchido nesta linha"
        yield LinhaTabela(n=n, campos=campos, motivo=motivo, avisos=avisos)


def total_estimado(dados: bytes) -> int:
    """ESTIMATIVA do número de linhas de dado, só para a barra de progresso do job. No CSV é a contagem de
    quebras de linha menos o cabeçalho — superestima quando uma célula entre aspas tem quebra de linha
    dentro; no XLSX é `max_row - 1`, que o openpyxl também dá como estimativa. Nunca é usada para decidir
    nada (o teto de linhas é conferido no gerador, com a contagem REAL)."""
    try:
        if e_xlsx(dados):
            import openpyxl

            wb = openpyxl.load_workbook(io.BytesIO(dados), read_only=True, data_only=True)
            ws = wb.worksheets[0] if wb.worksheets else None
            return max(0, (ws.max_row or 1) - 1) if ws is not None else 0
        texto = _decodificar(dados)
        return max(0, sum(1 for linha in texto.splitlines() if linha.strip()) - 1)
    except (ValueError, OSError, zipfile.BadZipFile, KeyError):
        return 0
