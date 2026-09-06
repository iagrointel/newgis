"""Inspeção de zip por leitura em intervalo — RANGE, nunca o objeto inteiro (item L0-04-a; ADR 0005 seção 3.2:
"o cabeçalho central fica no fim: o L0-11 expõe leitura por range"). Motivo de existir, em vez de reaproveitar só
`app.ingestao.formatos.conferir_zip` (que já faz as mesmas checagens sobre `zipfile.ZipFile(BytesIO(dados))`):
aquele caminho exige os BYTES INTEIROS do objeto em RAM; esta máquina roda com poucos GiB livres e o upload desta
fase aceita até 2 GiB por arquivo (`limites.UPLOAD_BYTES_MAX`) — baixar um zip real de ~2 GiB inteiro só para ler
metadado do fim do arquivo reproduziria o incidente de OOM já registrado na casa. `app.uploads.tipos` decide: até
`LIMITE_DOWNLOAD_INTEIRO` baixa tudo e chama `conferir_zip` (mais simples, mesmo código testado do L0-04-b);
acima disso, só este módulo, que nunca materializa mais que o fim-de-diretório (EOCD, no máximo ~64 KiB de
comentário) e o diretório central em si (que ESCALA COM O Nº DE ENTRADAS, e `ZIP_ENTRADAS_MAX` já limita isso a
um tamanho pequeno — um diretório central de 1.000 entradas de nome curto fica na casa de 50-150 KiB).

O parser lê os registros do FORMATO PKZIP diretamente (seção 4.3 da especificação .ZIP de referência, a mesma
que `zipfile` da stdlib implementa): o End Of Central Directory (EOCD, 22 bytes fixos + até 65.535 bytes de
comentário) dá a contagem de entradas e onde/quanto ler do diretório central; cada registro do diretório central
(46 bytes fixos + nome + campo extra + comentário da entrada) já traz tamanho comprimido/descomprimido e nome —
não precisa do cabeçalho local de cada entrada (que estaria espalhado pelo arquivo, exigindo 1 leitura por
entrada). ZIP64 (arquivo com ≥ 65.535 entradas ou diretório central ≥ 4 GiB) é FORA DE ESCOPO desta passagem —
ver `_achar_eocd`: o próprio `ZIP_ENTRADAS_MAX` (1.000) já barra bem abaixo do teto de 16 bits do formato clássico,
então recusar ZIP64 cedo (em vez de implementar o registro estendido) não reduz nenhum caso real aceito."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Callable

from app.ingestao.formatos import (
    ZIP_DESCOMPRIMIDO_MAX,
    ZIP_ENTRADAS_MAX,
    ZIP_NOME_MAX,
    ZIP_RAZAO_MAX,
    ZipSuspeito,
)

EOCD_ASSINATURA = b"PK\x05\x06"
EOCD_TAMANHO_MIN = 22
EOCD_COMENTARIO_MAX = 65535
CD_ASSINATURA = b"PK\x01\x02"
CD_CABECALHO_TAMANHO = 46
CAUDA_BYTES = EOCD_COMENTARIO_MAX + EOCD_TAMANHO_MIN  # cobre o pior caso de comentário do EOCD

LeitorIntervalo = Callable[[int, int], bytes]


@dataclass(frozen=True)
class EntradaZip:
    nome: str
    tamanho_comprimido: int
    tamanho_descomprimido: int
    atributo_externo: int


def _achar_eocd(cauda: bytes) -> dict:
    """`cauda` = últimos bytes do objeto. A assinatura pode aparecer mais de uma vez por acidente dentro de um
    comentário; `rfind` acha a ÚLTIMA ocorrência, que é sempre o EOCD de verdade (ele é o último registro do
    arquivo, por definição do formato)."""
    pos = cauda.rfind(EOCD_ASSINATURA)
    if pos == -1:
        raise ZipSuspeito("zip inválido: fim de diretório central (EOCD) não encontrado")
    campo = cauda[pos : pos + EOCD_TAMANHO_MIN]
    if len(campo) < EOCD_TAMANHO_MIN:
        raise ZipSuspeito("zip inválido: EOCD truncado")
    (_sig, disco, disco_cd, _entradas_disco, entradas_total, tam_cd, offset_cd, _com_len) = struct.unpack(
        "<4sHHHHIIH", campo
    )
    if entradas_total == 0xFFFF or tam_cd == 0xFFFFFFFF or offset_cd == 0xFFFFFFFF:
        raise ZipSuspeito("zip suspeito: indicador de ZIP64 (fora de escopo desta instalação)")
    if disco != 0 or disco_cd != 0:
        raise ZipSuspeito("zip suspeito: arquivo multi-volume (fora de escopo desta instalação)")
    return {"entradas": entradas_total, "tamanho_cd": tam_cd, "offset_cd": offset_cd}


def _ler_entradas(diretorio_central: bytes, n_esperado: int) -> list[EntradaZip]:
    saida: list[EntradaZip] = []
    pos = 0
    buf = diretorio_central
    while pos < len(buf) and len(saida) < n_esperado:
        if buf[pos : pos + 4] != CD_ASSINATURA:
            raise ZipSuspeito("zip inválido: registro do diretório central fora do lugar")
        cabecalho = buf[pos : pos + CD_CABECALHO_TAMANHO]
        if len(cabecalho) < CD_CABECALHO_TAMANHO:
            raise ZipSuspeito("zip inválido: registro do diretório central truncado")
        (
            _sig, _ver_feita, _ver_exigida, _flags, _compressao, _hora_mod, _data_mod,
            _crc32, tam_comp, tam_desc, len_nome, len_extra, len_comentario,
            _disco_ini, _attr_interno, attr_externo, _offset_local,
        ) = struct.unpack("<4sHHHHHHIIIHHHHHII", cabecalho)
        inicio_nome = pos + CD_CABECALHO_TAMANHO
        nome = buf[inicio_nome : inicio_nome + len_nome].decode("utf-8", errors="replace")
        saida.append(EntradaZip(nome, tam_comp, tam_desc, attr_externo))
        pos = inicio_nome + len_nome + len_extra + len_comentario
    if len(saida) != n_esperado:
        raise ZipSuspeito(f"zip suspeito: diretório central com {len(saida)} entradas, EOCD declara {n_esperado}")
    return saida


def _conferir_entradas(entradas: list[EntradaZip]) -> None:
    """As MESMAS regras de `app.ingestao.formatos.conferir_zip`, sobre `EntradaZip` em vez de `zipfile.ZipInfo`."""
    if len(entradas) > ZIP_ENTRADAS_MAX:
        raise ZipSuspeito(f"zip com {len(entradas)} entradas; o máximo é {ZIP_ENTRADAS_MAX}")
    total_descomprimido = sum(e.tamanho_descomprimido for e in entradas)
    total_comprimido = max(1, sum(e.tamanho_comprimido for e in entradas))
    razao = total_descomprimido / total_comprimido
    if total_descomprimido > ZIP_DESCOMPRIMIDO_MAX:
        raise ZipSuspeito(f"zip descomprimiria para {total_descomprimido} bytes; o máximo é {ZIP_DESCOMPRIMIDO_MAX}")
    if razao > ZIP_RAZAO_MAX:
        raise ZipSuspeito(f"razão de compressão {razao:.1f}x acima do máximo ({ZIP_RAZAO_MAX}x)")
    for e in entradas:
        nome = e.nome
        if len(nome.encode("utf-8", errors="replace")) > ZIP_NOME_MAX:
            raise ZipSuspeito(f"nome de entrada com mais de {ZIP_NOME_MAX} bytes: {nome!r}")
        if ".." in nome.replace("\\", "/").split("/") or nome.startswith("/") or "\\" in nome:
            raise ZipSuspeito(f"caminho de entrada inválido: {nome!r}")
        if any(ord(c) < 0x20 for c in nome):
            raise ZipSuspeito(f"caractere de controle no nome de entrada: {nome!r}")
        if nome.lower().endswith(".zip"):
            raise ZipSuspeito(f"zip aninhado: {nome!r}")
        modo_unix = (e.atributo_externo >> 16) & 0xFFFF
        if modo_unix and (modo_unix & 0xF000) == 0xA000:  # S_IFLNK
            raise ZipSuspeito(f"link simbólico no zip: {nome!r}")


def inspecionar_zip_remoto(leitor_intervalo: LeitorIntervalo, tamanho_objeto: int) -> list[EntradaZip]:
    """`leitor_intervalo(inicio, fim)` devolve bytes `[inicio, fim]` inclusive (contrato de
    `app.objetos.ler_intervalo`). Levanta `ZipSuspeito` nas MESMAS condições de `conferir_zip`; nunca lê mais que
    o EOCD + o diretório central (nunca as entradas em si)."""
    if tamanho_objeto < EOCD_TAMANHO_MIN:
        raise ZipSuspeito("zip inválido: objeto menor que um EOCD")
    inicio_cauda = max(0, tamanho_objeto - CAUDA_BYTES)
    cauda = leitor_intervalo(inicio_cauda, tamanho_objeto - 1)
    eocd = _achar_eocd(cauda)
    if eocd["entradas"] > ZIP_ENTRADAS_MAX:
        # recusa ANTES de buscar o diretório central: mesmo que ele coubesse, não há por que buscá-lo
        raise ZipSuspeito(f"zip com {eocd['entradas']} entradas; o máximo é {ZIP_ENTRADAS_MAX}")
    fim_cd = eocd["offset_cd"] + eocd["tamanho_cd"]
    if eocd["tamanho_cd"] < 0 or fim_cd > tamanho_objeto:
        raise ZipSuspeito("zip inválido: diretório central aponta para fora do objeto")
    if eocd["tamanho_cd"] == 0:
        entradas: list[EntradaZip] = []
    else:
        diretorio = leitor_intervalo(eocd["offset_cd"], fim_cd - 1)
        entradas = _ler_entradas(diretorio, eocd["entradas"])
    _conferir_entradas(entradas)
    return entradas
