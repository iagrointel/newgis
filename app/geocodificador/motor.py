"""Motor do geocodificador (item L2-11-b-geocodificador-brasil, ADR 0013 seções 4-6): resolução de
município/UF/CEP, busca por logradouro com `pg_trgm`, hierarquia de recuo com o TIPO DE ACERTO na resposta,
reverso por vizinho mais próximo (KNN GiST) e sugestão por prefixo.

Hierarquia de recuo (do mais preciso ao menos preciso), sempre marcada em `tipo_acerto`:
  numero_exato          -> ponto do CNEFE com o mesmo número na mesma via
  interpolado_na_face    -> número entre dois pontos conhecidos da MESMA face (quadra/lado), interpolado linear
  aproximado_no_logradouro -> nenhum par cobre o número; ponto mais próximo por número na mesma via
  aproximado_no_bairro    -> via não encontrada; centróide do bairro/localidade (DSC_LOCALIDADE) no município
  aproximado_no_cep       -> nem bairro; centróide dos pontos do CEP
  aproximado_no_municipio -> nem CEP; centróide do município
Nenhuma consulta usa f-string com valor do chamador: tudo por parâmetro (%s) — ver teste de injeção SQL.
"""

import math
from dataclasses import dataclass, field

PENALIDADE_TIPO_ACERTO = {
    "numero_exato": 0,
    "interpolado_na_face": 5,
    "aproximado_no_logradouro": 15,
    "aproximado_no_bairro": 30,
    "aproximado_no_cep": 40,
    "aproximado_no_municipio": 50,
    "aproximado_no_ponto": 0,  # reverso: não se aplica penalidade de tipo, é o próprio ponto
}
LIMIAR_SIMILARIDADE = 0.24  # abaixo disso o pg_trgm (%) já não considera "parecido" (default do Postgres é 0.3;
# CNEFE tem nomes curtos ("RUA A"), por isso um pouco mais tolerante — medido em tests/medidas)

AVISO_TIPO_ACERTO = {
    # só os tipos degradados avisam; numero_exato/interpolado_na_face são precisos o bastante para não precisar
    "aproximado_no_logradouro": "número não encontrado na via; ponto mais próximo por número na mesma via",
    "aproximado_no_bairro": "logradouro não encontrado; ponto é o centro do bairro/localidade, não do endereço",
    "aproximado_no_cep": "nem logradouro nem bairro encontrados; ponto é o centro dos endereços do CEP",
    "aproximado_no_municipio": "só o município foi reconhecido; ponto é o centro do município, não do endereço",
}


@dataclass
class Candidato:
    endereco: str
    lon: float
    lat: float
    score: float
    tipo_acerto: str
    cod_municipio: int
    municipio: str
    uf: str
    cep: str | None
    bairro: str | None
    logradouro: str | None
    numero: int | None
    avisos: list[str] = field(default_factory=list)

    def como_dict(self) -> dict:
        return {
            "endereco": self.endereco,
            "lon": self.lon,
            "lat": self.lat,
            "score": round(self.score, 1),
            "tipo_acerto": self.tipo_acerto,
            "municipio": self.municipio,
            "uf": self.uf,
            "cep": self.cep,
            "bairro": self.bairro,
            "logradouro": self.logradouro,
            "numero": self.numero,
            "avisos": self.avisos,
        }


class InconsistenciaEndereco(Exception):
    """CEP e município/UF informados juntos não correspondem ao mesmo lugar no CNEFE (refutação do item:
    'CEP de outro estado com município errado deve recusar/avisar inconsistência')."""

    def __init__(self, codigo: str, mensagem: str, detalhe: dict):
        self.codigo = codigo
        self.mensagem = mensagem
        self.detalhe = detalhe
        super().__init__(mensagem)


def _municipios_do_cep(cur, cep: str) -> list[dict]:
    cur.execute(
        "SELECT DISTINCT m.cod, m.nome, u.sigla FROM plat.geo_endereco e "
        "JOIN plat.geo_municipio m ON m.cod = e.cod_municipio JOIN plat.geo_uf u ON u.cod = m.cod_uf "
        "WHERE e.cep = %s LIMIT 5",
        (cep,),
    )
    return list(cur.fetchall())


def _municipios_por_nome(cur, nome: str, uf: str | None) -> list[dict]:
    cur.execute(
        "SELECT m.cod, m.nome, u.sigla, similarity(m.nome_norm, upper(public.unaccent(%(q)s))) AS sim "
        "FROM plat.geo_municipio m JOIN plat.geo_uf u ON u.cod = m.cod_uf "
        "WHERE m.nome_norm %% upper(public.unaccent(%(q)s)) AND (%(uf)s::text IS NULL OR u.sigla = %(uf)s) "
        "ORDER BY sim DESC LIMIT 5",
        {"q": nome, "uf": uf},
    )
    return list(cur.fetchall())


def resolver_lugar(cur, *, municipio: str | None, uf: str | None, cep: str | None) -> dict:
    """Resolve município/UF/CEP a partir do que o chamador informou, e levanta InconsistenciaEndereco quando
    dois sinais independentes (CEP e município, ou CEP e UF) apontam para lugares diferentes — a checagem
    roda ANTES de qualquer busca por logradouro, então nunca devolve candidato de um lugar não pedido."""
    municipios_cep = _municipios_do_cep(cur, cep) if cep else []
    municipios_nome = _municipios_por_nome(cur, municipio, uf) if municipio else []

    if cep and municipio and municipios_cep and municipios_nome:
        cods_cep = {m["cod"] for m in municipios_cep}
        cods_nome = {m["cod"] for m in municipios_nome}
        if cods_cep.isdisjoint(cods_nome):
            raise InconsistenciaEndereco(
                "cep_municipio_inconsistente",
                f"o CEP {cep} pertence a {municipios_cep[0]['nome']}/{municipios_cep[0]['sigla']}, "
                f"não a {municipio!r}",
                {
                    "cep": cep,
                    "municipio_do_cep": f"{municipios_cep[0]['nome']}/{municipios_cep[0]['sigla']}",
                    "municipio_pedido": municipio,
                    "uf_pedida": uf,
                },
            )
    if cep and uf and municipios_cep:
        ufs_cep = {m["sigla"] for m in municipios_cep}
        if uf not in ufs_cep:
            raise InconsistenciaEndereco(
                "cep_uf_inconsistente",
                f"o CEP {cep} pertence à UF {sorted(ufs_cep)!r}, não a {uf!r}",
                {"cep": cep, "uf_do_cep": sorted(ufs_cep), "uf_pedida": uf},
            )
    cods_municipio = None
    if municipios_nome:
        cods_municipio = [m["cod"] for m in municipios_nome]
    elif municipios_cep:
        cods_municipio = [m["cod"] for m in municipios_cep]
    return {"cods_municipio": cods_municipio, "municipios_cep": municipios_cep, "municipios_nome": municipios_nome}


def _endereco_texto(logradouro, numero, bairro, municipio, uf) -> str:
    partes = []
    if logradouro:
        partes.append(f"{logradouro}, {numero}" if numero is not None else logradouro)
    if bairro:
        partes.append(bairro)
    partes.append(f"{municipio} - {uf}")
    return ", ".join(p for p in partes if p)


def _municipio_uf(cur, cod_municipio: int) -> tuple[str, str]:
    cur.execute(
        "SELECT m.nome, u.sigla FROM plat.geo_municipio m JOIN plat.geo_uf u ON u.cod = m.cod_uf "
        "WHERE m.cod = %s",
        (cod_municipio,),
    )
    r = cur.fetchone()
    return (r["nome"], r["sigla"]) if r else (None, None)


def _melhor_face(pontos: list[dict], numero: int) -> tuple[str, dict | None]:
    """`pontos` = linhas (face_id, numero, lat, lon) de UMA via, ordenadas por face_id/numero. Devolve
    (tipo_acerto, ponto_ou_None) — ponto é {'lat','lon'} já resolvido (exato/interpolado) ou None quando só dá
    para aproximar pelo número mais próximo da via inteira."""
    exatos = [p for p in pontos if p["numero"] == numero]
    if exatos:
        lat = sum(p["lat"] for p in exatos) / len(exatos)
        lon = sum(p["lon"] for p in exatos) / len(exatos)
        return "numero_exato", {"lat": lat, "lon": lon}

    por_face: dict[str, list[dict]] = {}
    for p in pontos:
        por_face.setdefault(p["face_id"], []).append(p)

    melhor_faixa = None
    melhor = None
    for face_pontos in por_face.values():
        numeros = [p["numero"] for p in face_pontos]
        mn, mx = min(numeros), max(numeros)
        if mn <= numero <= mx and mn != mx:
            abaixo = max((p for p in face_pontos if p["numero"] <= numero), key=lambda p: p["numero"])
            acima = min((p for p in face_pontos if p["numero"] >= numero), key=lambda p: p["numero"])
            faixa = mx - mn
            if melhor_faixa is None or faixa < melhor_faixa:
                melhor_faixa = faixa
                if abaixo["numero"] == acima["numero"]:
                    melhor = {"lat": abaixo["lat"], "lon": abaixo["lon"]}
                else:
                    t = (numero - abaixo["numero"]) / (acima["numero"] - abaixo["numero"])
                    melhor = {
                        "lat": abaixo["lat"] + t * (acima["lat"] - abaixo["lat"]),
                        "lon": abaixo["lon"] + t * (acima["lon"] - abaixo["lon"]),
                    }
    if melhor is not None:
        return "interpolado_na_face", melhor

    mais_perto = min(pontos, key=lambda p: abs(p["numero"] - numero))
    return "aproximado_no_logradouro", {"lat": mais_perto["lat"], "lon": mais_perto["lon"]}


def buscar(cur, *, logradouro: str | None, numero: int | None, bairro: str | None, municipio: str | None,
           uf: str | None, cep: str | None, max_locations: int = 10) -> list[Candidato]:
    """Busca com hierarquia de recuo (ver `_buscar_interna`); aqui só se acrescenta o AVISO em português
    de cada tipo de acerto degradado (`AVISO_TIPO_ACERTO`), num único lugar, para nenhum dos 4 caminhos de
    retorno internos esquecer de preencher `avisos` — campo teria ficado sempre vazio (achado do papel
    adversário desta sessão: lista vazia sem nenhum caminho que a populasse é um sintoma de placeholder)."""
    candidatos = _buscar_interna(
        cur, logradouro=logradouro, numero=numero, bairro=bairro, municipio=municipio, uf=uf, cep=cep,
        max_locations=max_locations,
    )
    for c in candidatos:
        aviso = AVISO_TIPO_ACERTO.get(c.tipo_acerto)
        if aviso:
            c.avisos.append(aviso)
    return candidatos


def _buscar_interna(cur, *, logradouro: str | None, numero: int | None, bairro: str | None,
                     municipio: str | None, uf: str | None, cep: str | None,
                     max_locations: int = 10) -> list[Candidato]:
    """Busca com hierarquia de recuo. `logradouro` já deve ter passado por
    `normalizacao.expandir_abreviacoes` (feito pela rota); a dobra de acento/caixa é feita aqui em SQL."""
    lugar = resolver_lugar(cur, municipio=municipio, uf=uf, cep=cep)
    cods_municipio = lugar["cods_municipio"]

    candidatos: list[Candidato] = []

    if logradouro:
        cur.execute(
            "SELECT cod_municipio, logradouro_norm, tipo_logradouro, nome_logradouro, "
            "  MAX(similarity(logradouro_norm, upper(public.unaccent(%(q)s)))) AS sim "
            "FROM plat.geo_endereco "
            "WHERE (%(mun)s::int[] IS NULL OR cod_municipio = ANY(%(mun)s)) "
            "  AND logradouro_norm %% upper(public.unaccent(%(q)s)) "
            "GROUP BY cod_municipio, logradouro_norm, tipo_logradouro, nome_logradouro "
            "HAVING MAX(similarity(logradouro_norm, upper(public.unaccent(%(q)s)))) >= %(limiar)s "
            "ORDER BY sim DESC LIMIT %(n)s",
            {"q": logradouro, "mun": cods_municipio, "limiar": LIMIAR_SIMILARIDADE, "n": max_locations * 3},
        )
        ruas = list(cur.fetchall())
        for rua in ruas:
            cur.execute(
                "SELECT face_id, numero, cep, localidade, lat, lon FROM plat.geo_endereco "
                "WHERE cod_municipio = %s AND logradouro_norm = %s AND numero IS NOT NULL "
                "ORDER BY face_id, numero",
                (rua["cod_municipio"], rua["logradouro_norm"]),
            )
            pontos = list(cur.fetchall())
            if not pontos:
                continue
            nome_mun, sigla_uf = _municipio_uf(cur, rua["cod_municipio"])
            if numero is not None:
                tipo_acerto, ponto = _melhor_face(pontos, numero)
            else:
                tipo_acerto, ponto = "aproximado_no_logradouro", {
                    "lat": sum(p["lat"] for p in pontos) / len(pontos),
                    "lon": sum(p["lon"] for p in pontos) / len(pontos),
                }
            score = max(0.0, min(100.0, rua["sim"] * 100 - PENALIDADE_TIPO_ACERTO[tipo_acerto]))
            candidatos.append(Candidato(
                endereco=_endereco_texto(
                    f"{rua['tipo_logradouro'] or ''} {rua['nome_logradouro'] or ''}".strip(), numero, bairro,
                    nome_mun, sigla_uf,
                ),
                lon=ponto["lon"], lat=ponto["lat"], score=score, tipo_acerto=tipo_acerto,
                cod_municipio=rua["cod_municipio"], municipio=nome_mun, uf=sigla_uf, cep=None, bairro=bairro,
                logradouro=f"{rua['tipo_logradouro'] or ''} {rua['nome_logradouro'] or ''}".strip(),
                numero=numero,
            ))
        candidatos.sort(key=lambda c: c.score, reverse=True)
        if candidatos:
            return candidatos[:max_locations]

    # sem logradouro (ou sem casar nenhum): recuo por bairro -> CEP -> município
    if bairro and cods_municipio:
        cur.execute(
            "SELECT cod_municipio, localidade, AVG(lat) AS lat, AVG(lon) AS lon, "
            "  MAX(similarity(localidade_norm, upper(public.unaccent(%(q)s)))) AS sim "
            "FROM plat.geo_endereco WHERE cod_municipio = ANY(%(mun)s) "
            "  AND localidade_norm %% upper(public.unaccent(%(q)s)) "
            "GROUP BY cod_municipio, localidade ORDER BY sim DESC LIMIT %(n)s",
            {"q": bairro, "mun": cods_municipio, "n": max_locations},
        )
        for r in cur.fetchall():
            nome_mun, sigla_uf = _municipio_uf(cur, r["cod_municipio"])
            penalidade = PENALIDADE_TIPO_ACERTO["aproximado_no_bairro"]
            candidatos.append(Candidato(
                endereco=_endereco_texto(None, None, r["localidade"], nome_mun, sigla_uf),
                lon=r["lon"], lat=r["lat"], score=max(0.0, r["sim"] * 100 - penalidade),
                tipo_acerto="aproximado_no_bairro", cod_municipio=r["cod_municipio"], municipio=nome_mun,
                uf=sigla_uf, cep=None, bairro=r["localidade"], logradouro=None, numero=None,
            ))
        if candidatos:
            return candidatos[:max_locations]

    if cep and lugar["municipios_cep"]:
        cur.execute("SELECT AVG(lat) AS lat, AVG(lon) AS lon FROM plat.geo_endereco WHERE cep = %s", (cep,))
        r = cur.fetchone()
        m = lugar["municipios_cep"][0]
        candidatos.append(Candidato(
            endereco=_endereco_texto(None, None, None, m["nome"], m["sigla"]), lon=r["lon"], lat=r["lat"],
            score=max(0.0, 90 - PENALIDADE_TIPO_ACERTO["aproximado_no_cep"]), tipo_acerto="aproximado_no_cep",
            cod_municipio=m["cod"], municipio=m["nome"], uf=m["sigla"], cep=cep, bairro=None, logradouro=None,
            numero=None,
        ))
        return candidatos[:max_locations]

    if cods_municipio:
        for cod in cods_municipio[:max_locations]:
            cur.execute("SELECT centro_lat, centro_lon FROM plat.geo_municipio WHERE cod = %s", (cod,))
            r = cur.fetchone()
            if r is None or r["centro_lat"] is None:
                continue
            nome_mun, sigla_uf = _municipio_uf(cur, cod)
            candidatos.append(Candidato(
                endereco=_endereco_texto(None, None, None, nome_mun, sigla_uf), lon=r["centro_lon"],
                lat=r["centro_lat"], score=max(0.0, 80 - PENALIDADE_TIPO_ACERTO["aproximado_no_municipio"]),
                tipo_acerto="aproximado_no_municipio", cod_municipio=cod, municipio=nome_mun, uf=sigla_uf,
                cep=None, bairro=None, logradouro=None, numero=None,
            ))
    return candidatos[:max_locations]


def reverso(cur, lon: float, lat: float, raio_m: float = 2000.0) -> dict | None:
    """Vizinho mais próximo por GiST (operador `<->`, KNN); `raio_m` é só um teto de sanidade (a consulta usa
    ORDER BY distância e LIMIT 1, sem filtro de raio, para achar o vizinho mesmo em área rarefeita — o raio
    entra depois, para marcar `fora_do_raio` sem descartar a resposta)."""
    cur.execute(
        "SELECT e.id, e.tipo_logradouro, e.nome_logradouro, e.numero, e.cep, e.localidade, e.cod_municipio, "
        "  m.nome AS municipio, u.sigla AS uf, e.lat, e.lon, "
        "  ST_Distance(e.geom::geography, ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography) AS dist_m "
        "FROM plat.geo_endereco e "
        "JOIN plat.geo_municipio m ON m.cod = e.cod_municipio JOIN plat.geo_uf u ON u.cod = m.cod_uf "
        "ORDER BY e.geom <-> ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326) LIMIT 1",
        {"lon": lon, "lat": lat},
    )
    r = cur.fetchone()
    if r is None:
        return None
    logradouro = f"{r['tipo_logradouro'] or ''} {r['nome_logradouro'] or ''}".strip() or None
    return {
        "endereco": _endereco_texto(logradouro, r["numero"], r["localidade"], r["municipio"], r["uf"]),
        "logradouro": logradouro,
        "numero": r["numero"],
        "bairro": r["localidade"],
        "municipio": r["municipio"],
        "uf": r["uf"],
        "cep": r["cep"],
        "distancia_m": round(r["dist_m"], 1),
        "fora_do_raio": r["dist_m"] > raio_m,
        "tipo_acerto": "reverso_vizinho_mais_proximo",
        "lon": lon,
        "lat": lat,
    }


def sugerir(cur, texto: str, limite: int = 10) -> list[dict]:
    """Autocomplete por prefixo sobre `logradouro_norm` (índice trigram GIN cobre LIKE 'prefixo%')."""
    prefixo = texto.upper()
    cur.execute(
        "SELECT DISTINCT ON (e.cod_municipio, e.logradouro_norm) e.tipo_logradouro, e.nome_logradouro, "
        "  e.cod_municipio, m.nome AS municipio, u.sigla AS uf "
        "FROM plat.geo_endereco e "
        "JOIN plat.geo_municipio m ON m.cod = e.cod_municipio JOIN plat.geo_uf u ON u.cod = m.cod_uf "
        "WHERE e.logradouro_norm LIKE upper(public.unaccent(%(p)s)) || '%%' "
        "ORDER BY e.cod_municipio, e.logradouro_norm LIMIT %(n)s",
        {"p": prefixo, "n": limite},
    )
    saida = []
    for r in cur.fetchall():
        texto_sugestao = f"{r['tipo_logradouro'] or ''} {r['nome_logradouro'] or ''}".strip()
        saida.append({
            "texto": f"{texto_sugestao}, {r['municipio']} - {r['uf']}",
            "chave": f"{r['cod_municipio']}:{texto_sugestao}",
        })
    return saida


def distancia_m(lon1, lat1, lon2, lat2) -> float:
    """Haversine simples (usado só pelos testes para conferir erro; a API usa ST_Distance geography)."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
