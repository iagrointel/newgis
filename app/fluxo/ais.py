"""Decodificador AIS (AIVDM/AIVDO) das mensagens de POSIÇÃO, para a fonte de fluxo do tipo `ais`
(item L2-14-a-ingestao-de-fluxos).

Escopo declarado: mensagens 1, 2 e 3 (relatório de posição de Classe A) e 18 (relatório de posição de
Classe B). Fora: 5 e 24 (dados estáticos e de viagem), 21 (auxílio à navegação) e todas as demais — chegam,
não quebram nada e são contadas como sentença ignorada. A casa já tem um decodificador completo em Rust no
outro servidor (RASTRO) e a tabela `ais_positions` com 164,9 milhões de linhas; o que falta aqui é só a
ponta que transforma NMEA em evento de fluxo, e é só isso que este arquivo faz.

Formato: `!AIVDM,<total>,<parte>,<seq>,<canal>,<carga>,<preenchimento>*<checksum>`. A carga é ASCII de 6 bits
(cada caractere carrega 6 bits, com 48 subtraído e 8 a mais acima de 87). Sentença multiparte é remontada
por (canal, sequência); parte solta expira sozinha quando a próxima da mesma chave chega.

Coordenadas: 1/10000 de minuto, complemento de dois. 181°/91° são os valores de "não disponível" do padrão e
viram `None`, nunca 181 grau — é o erro clássico de quem lê AIS sem ler a norma.
"""

from __future__ import annotations

from dataclasses import dataclass, field

TIPOS_POSICAO = (1, 2, 3, 18)
LON_INDISPONIVEL = 0x6791AC0   # 181 graus em 1/10000 min
LAT_INDISPONIVEL = 0x3412140   # 91 graus


@dataclass
class Remontador:
    """Junta sentenças multiparte. Uma instância por conexão."""

    partes: dict = field(default_factory=dict)

    def alimentar(self, linha: str) -> dict | None:
        """Sentença → dicionário do evento, ou None (parte incompleta, sentença ignorada ou inválida)."""
        campos = _campos(linha)
        if campos is None:
            return None
        total, parte, seq, canal, carga, preenchimento = campos
        if total == 1:
            return decodificar_carga(carga, preenchimento)
        chave = (canal, seq)
        acumulado = self.partes.get(chave)
        if parte == 1 or acumulado is None:
            self.partes[chave] = {"total": total, "proxima": 2, "carga": carga, "preenchimento": preenchimento}
            return None
        if acumulado["proxima"] != parte:
            self.partes.pop(chave, None)
            return None
        acumulado["carga"] += carga
        acumulado["preenchimento"] = preenchimento
        acumulado["proxima"] += 1
        if parte < total:
            return None
        self.partes.pop(chave, None)
        return decodificar_carga(acumulado["carga"], acumulado["preenchimento"])


def _campos(linha: str):
    linha = linha.strip()
    if not linha.startswith(("!AIVDM", "!AIVDO", "!BSVDM", "!ABVDM")):
        return None
    corpo, _, resto = linha.partition("*")
    if resto:
        try:
            esperado = int(resto[:2], 16)
        except ValueError:
            return None
        soma = 0
        for c in corpo[1:]:
            soma ^= ord(c)
        if soma != esperado:
            return None
    partes = corpo.split(",")
    if len(partes) < 7:
        return None
    try:
        total, parte = int(partes[1]), int(partes[2])
        preenchimento = int(partes[6]) if partes[6] else 0
    except ValueError:
        return None
    if not 1 <= parte <= total <= 9 or not 0 <= preenchimento <= 5:
        return None
    return total, parte, partes[3], partes[4], partes[5], preenchimento


def _bits(carga: str, preenchimento: int) -> str:
    saida = []
    for c in carga:
        v = ord(c) - 48
        if v > 40:
            v -= 8
        if not 0 <= v < 64:
            return ""
        saida.append(f"{v:06b}")
    inteiro = "".join(saida)
    return inteiro[:len(inteiro) - preenchimento] if preenchimento else inteiro


def _uint(bits: str, inicio: int, tamanho: int) -> int | None:
    pedaco = bits[inicio:inicio + tamanho]
    return int(pedaco, 2) if len(pedaco) == tamanho else None


def _int(bits: str, inicio: int, tamanho: int) -> int | None:
    valor = _uint(bits, inicio, tamanho)
    if valor is None:
        return None
    return valor - (1 << tamanho) if valor >= (1 << (tamanho - 1)) else valor


def decodificar_carga(carga: str, preenchimento: int = 0) -> dict | None:
    bits = _bits(carga, preenchimento)
    if len(bits) < 38:
        return None
    tipo = _uint(bits, 0, 6)
    if tipo not in TIPOS_POSICAO:
        return None
    mmsi = _uint(bits, 8, 30)
    if tipo == 18:
        velocidade, lon_i, lat_i, rumo, proa, segundo = (
            _uint(bits, 46, 10), _int(bits, 57, 28), _int(bits, 85, 27),
            _uint(bits, 112, 12), _uint(bits, 124, 9), _uint(bits, 133, 6))
        navegacao = None
    else:
        navegacao = _uint(bits, 38, 4)
        velocidade, lon_i, lat_i, rumo, proa, segundo = (
            _uint(bits, 50, 10), _int(bits, 61, 28), _int(bits, 89, 27),
            _uint(bits, 116, 12), _uint(bits, 128, 9), _uint(bits, 137, 6))
    if lon_i is None or lat_i is None:
        return None
    evento = {
        "tipo_mensagem": tipo,
        "mmsi": str(mmsi) if mmsi is not None else None,
        "lon": None if abs(lon_i) == LON_INDISPONIVEL else round(lon_i / 600000.0, 6),
        "lat": None if abs(lat_i) == LAT_INDISPONIVEL else round(lat_i / 600000.0, 6),
        "velocidade_no": None if velocidade in (None, 1023) else velocidade / 10.0,
        "rumo_grau": None if rumo in (None, 3600) else rumo / 10.0,
        "proa_grau": None if proa in (None, 511) else float(proa),
        "segundo_utc": None if segundo is None or segundo > 59 else segundo,
    }
    if navegacao is not None:
        evento["estado_navegacao"] = navegacao
    if evento["lon"] is not None and not -180 <= evento["lon"] <= 180:
        evento["lon"] = None
    if evento["lat"] is not None and not -90 <= evento["lat"] <= 90:
        evento["lat"] = None
    return evento
