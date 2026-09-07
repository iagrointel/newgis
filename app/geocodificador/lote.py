"""Geocodificação de tabela (item L2-11-a-geocodificacao-csv, ADR 0013): CSV/XLSX com endereço e sem
coordenada — a Esri geocodifica ao publicar; aqui o mesmo papel é o job `geocodificador.lote_csv` — mapeia
colunas do CSV para os campos que `app.geocodificador.motor.buscar` já entende (logradouro, número, bairro,
município, UF, CEP ou endereço em linha única), chama o motor do L2-11-b linha a linha e classifica cada
resultado em RESOLVIDO ou PENDENTE (revisão manual: tela de lista + mapa, item L2-11-a). Pura Python +
SQL: sem dependência de arquivo em disco, sem GDAL — o CSV chega como texto (a mesma regra do L0-04-d de não
processar em memória sem limite é respeitada pelo teto `GEOCODIFICADOR_LOTE_MAX_LINHAS`).

Hierarquia de RESOLVIDO x PENDENTE (mais estrita que o próprio motor): só `numero_exato` e
`interpolado_na_face` COM score >= limiar resolvem sozinhos; todo recuo mais fraco (aproximado_no_logradouro/
bairro/cep/município) ou a ausência total de candidato cai em revisão manual — é a leitura do item ("pendentes
aparecem na tela de revisão") e do próprio ADR (avisos por tipo de acerto degradado)."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from app import limites
from app.geocodificador import motor
from app.geocodificador.normalizacao import expandir_abreviacoes

CAMPOS_MAPEAVEIS = ("logradouro", "numero", "bairro", "municipio", "uf", "cep", "endereco")
TIPOS_RESOLVIDOS = frozenset({"numero_exato", "interpolado_na_face"})


class MapeamentoInvalido(ValueError):
    """Mapeamento de coluna aponta para uma coluna que não existe no CSV, ou para um campo desconhecido."""


@dataclass
class LinhaGeocodificada:
    linha_origem: int              # número da linha no CSV (1-based, sem contar cabeçalho)
    endereco_entrada: str          # o que foi de fato mandado ao motor (para auditoria/revisão)
    campos_entrada: dict           # os campos originais do CSV desta linha (para re-geocodificar depois)
    lon: float | None = None
    lat: float | None = None
    score: float | None = None
    tipo_acerto: str | None = None
    cod_municipio: int | None = None
    municipio: str | None = None
    uf: str | None = None
    avisos: list = field(default_factory=list)
    erro: str | None = None        # InconsistenciaEndereco (CEP x município/UF não batem) ou "sem_correspondencia"
    pendente: bool = True


def ler_csv(texto: str, *, delimitador: str = ",") -> tuple[list[str], list[dict]]:
    """CSV -> (cabeçalho, linhas como dict). `csv.DictReader` padrão da std lib — CSV/XLSX exportado como CSV
    é o mesmo texto; conversão de .xlsx para texto é responsabilidade de quem chama esta função (a rota aceita
    só texto CSV; o `README`/handoff do item nomeia o XLSX como pendência de UI, não de motor)."""
    if not texto or not texto.strip():
        raise MapeamentoInvalido("CSV vazio")
    leitor = csv.DictReader(io.StringIO(texto), delimiter=delimitador)
    if not leitor.fieldnames:
        raise MapeamentoInvalido("CSV sem cabeçalho")
    linhas = list(leitor)
    if len(linhas) > limites.GEOCODIFICADOR_LOTE_MAX_LINHAS:
        raise MapeamentoInvalido(
            f"{len(linhas)} linhas > teto de {limites.GEOCODIFICADOR_LOTE_MAX_LINHAS} por lote"
        )
    return list(leitor.fieldnames), linhas


def validar_mapeamento(cabecalho: list[str], mapeamento: dict) -> None:
    if not mapeamento:
        raise MapeamentoInvalido("mapeamento vazio: informe ao menos uma coluna (logradouro, bairro, cep ou "
                                  "endereco em linha única)")
    campos_desconhecidos = set(mapeamento) - set(CAMPOS_MAPEAVEIS)
    if campos_desconhecidos:
        raise MapeamentoInvalido(f"campo(s) de mapeamento desconhecido(s): {sorted(campos_desconhecidos)}; "
                                  f"esperado um de {CAMPOS_MAPEAVEIS}")
    colunas_faltando = {coluna for coluna in mapeamento.values() if coluna not in cabecalho}
    if colunas_faltando:
        raise MapeamentoInvalido(f"coluna(s) do mapeamento ausente(s) no CSV: {sorted(colunas_faltando)}")
    if not ({"logradouro", "endereco"} & set(mapeamento)):
        raise MapeamentoInvalido("mapeamento precisa de 'logradouro' ou 'endereco' (linha única) para geocodificar "
                                  "além do centro do município")


def aplicar_mapeamento(linha: dict, mapeamento: dict) -> dict:
    """Uma linha do CSV -> campos do motor (`logradouro`, `numero`, `bairro`, `municipio`, `uf`, `cep`,
    `endereco`); célula vazia vira None (o motor já trata None como "não informado")."""
    saida = {}
    for campo, coluna in mapeamento.items():
        valor = (linha.get(coluna) or "").strip()
        saida[campo] = valor or None
    if saida.get("numero") is not None:
        try:
            saida["numero"] = int("".join(c for c in saida["numero"] if c.isdigit()) or "0") or None
        except ValueError:
            saida["numero"] = None
    if saida.get("uf"):
        saida["uf"] = saida["uf"].strip().upper()[:2]
    if saida.get("cep"):
        digitos = "".join(c for c in saida["cep"] if c.isdigit())
        saida["cep"] = digitos if len(digitos) == 8 else None
    if saida.get("logradouro"):
        saida["logradouro"] = expandir_abreviacoes(saida["logradouro"])
    return saida


def _endereco_auditoria(campos: dict) -> str:
    if campos.get("endereco"):
        return campos["endereco"]
    partes = []
    if campos.get("logradouro"):
        partes.append(f"{campos['logradouro']}, {campos['numero']}" if campos.get("numero") else campos["logradouro"])
    if campos.get("bairro"):
        partes.append(campos["bairro"])
    if campos.get("cep"):
        partes.append(campos["cep"])
    resto = f"{campos.get('municipio') or ''} - {campos.get('uf') or ''}".strip(" -")
    if resto:
        partes.append(resto)
    return ", ".join(p for p in partes if p) or "(endereço vazio)"


def geocodificar_linha(cur, linha_origem: int, linha_csv: dict, mapeamento: dict, *,
                        limiar_pendente: float) -> LinhaGeocodificada:
    """Geocodifica UMA linha CRUA do CSV: aplica o mapeamento de coluna e delega a `geocodificar_campos`."""
    campos = aplicar_mapeamento(linha_csv, mapeamento)
    return geocodificar_campos(cur, linha_origem, campos, limiar_pendente=limiar_pendente)


def geocodificar_campos(cur, linha_origem: int, campos_entrada: dict, *, limiar_pendente: float) -> LinhaGeocodificada:
    """Geocodifica campos JÁ MAPEADOS (`logradouro`/`numero`/`bairro`/`municipio`/`uf`/`cep`/`endereco`) — usada
    tanto pela carga inicial (depois do mapeamento de coluna) quanto pelo re-geocodificar dos pendentes (que
    relê `campos_entrada` já gravado na camada, sem mapeamento nenhum: a coluna já virou campo há muito tempo).
    Reusa `app.geocodificador.motor` (L2-11-b) ponto a ponto, então o resultado (tipo de acerto, score, avisos)
    é EXATAMENTE o mesmo vocabulário da API própria do geocodificador, nunca um cálculo paralelo."""
    campos = dict(campos_entrada)
    resultado = LinhaGeocodificada(
        linha_origem=linha_origem, endereco_entrada=_endereco_auditoria(campos), campos_entrada=campos,
    )
    if campos.get("endereco"):
        # mesma resolução de linha única da rota própria (import tardio evita ciclo: rotas.py já importa lote?
        # não — lote.py é importado por rotas_lote.py, então não há ciclo; feito local só por clareza)
        from app.geocodificador.normalizacao import analisar_linha_unica

        livre = analisar_linha_unica(campos["endereco"])
        logradouro_livre = expandir_abreviacoes(livre.logradouro) if livre.logradouro else None
        campos = {
            "logradouro": campos.get("logradouro") or logradouro_livre,
            "numero": campos.get("numero") if campos.get("numero") is not None else livre.numero,
            "bairro": campos.get("bairro") or livre.bairro,
            "municipio": campos.get("municipio") or livre.municipio,
            "uf": campos.get("uf") or livre.uf,
            "cep": campos.get("cep") or livre.cep,
        }
    if not any([campos.get("logradouro"), campos.get("bairro"), campos.get("municipio"), campos.get("cep")]):
        resultado.erro = "endereco_vazio"
        return resultado
    try:
        candidatos = motor.buscar(
            cur, logradouro=campos.get("logradouro"), numero=campos.get("numero"), bairro=campos.get("bairro"),
            municipio=campos.get("municipio"), uf=campos.get("uf"), cep=campos.get("cep"), max_locations=1,
        )
    except motor.InconsistenciaEndereco as e:
        resultado.erro = e.codigo
        return resultado
    if not candidatos:
        resultado.erro = "sem_correspondencia"
        return resultado
    melhor = candidatos[0]
    resultado.lon, resultado.lat, resultado.score = melhor.lon, melhor.lat, melhor.score
    resultado.tipo_acerto, resultado.avisos = melhor.tipo_acerto, list(melhor.avisos)
    resultado.cod_municipio, resultado.municipio, resultado.uf = melhor.cod_municipio, melhor.municipio, melhor.uf
    resultado.pendente = not (melhor.tipo_acerto in TIPOS_RESOLVIDOS and melhor.score >= limiar_pendente)
    return resultado


def processar_lote(cur, linhas_csv: list[dict], mapeamento: dict, *,
                    limiar_pendente: float = limites.GEOCODIFICADOR_LOTE_LIMIAR_PENDENTE_PADRAO,
                    ao_progredir=None) -> list[LinhaGeocodificada]:
    """Geocodifica a tabela inteira; `ao_progredir(indice, total)` é chamado a cada
    `_INTERVALO_PROGRESSO` linhas (o job usa para `ctx.progresso`; os testes de unidade passam None)."""
    total = len(linhas_csv)
    saida: list[LinhaGeocodificada] = []
    for i, linha in enumerate(linhas_csv, start=1):
        saida.append(geocodificar_linha(cur, i, linha, mapeamento, limiar_pendente=limiar_pendente))
        if ao_progredir is not None and (i % 100 == 0 or i == total):
            ao_progredir(i, total)
    return saida


def resumo(linhas: list[LinhaGeocodificada]) -> dict:
    por_tipo: dict[str, int] = {}
    for linha in linhas:
        chave = linha.tipo_acerto or (f"erro:{linha.erro}" if linha.erro else "sem_candidato")
        por_tipo[chave] = por_tipo.get(chave, 0) + 1
    pendentes = sum(1 for linha in linhas if linha.pendente)
    return {
        "total": len(linhas), "resolvidos": len(linhas) - pendentes, "pendentes": pendentes,
        "por_tipo_acerto": por_tipo,
    }
