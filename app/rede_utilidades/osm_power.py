"""Conector OpenStreetMap power=* para o modelo de elementos da rede de utilidades
(item L4-05-g-osm-power; ADR docs/adr/20260906T2226-conector-osm-power.md).

Lê um extrato OSM (.pbf ou .osm) pela ferramenta `osmium` (pacote osmium-tool, pré-requisito de
máquina), recorta as feições power=* de UM município (polígono GeoJSON em EPSG:4326, parâmetro)
e monta a rede de negócio (plat.rede_no / plat.rede_aresta / plat.rede_associacao) sobre o pacote
eletrica-br, como rede de BAIXA CONFIANÇA: cada elemento grava `fonte = 'OSM'` nos atributos e a
auditoria (plat.rede_importacao) registra licença ODbL e o aviso "cadastro comunitário, não
oficial" — o que a ficha da importação mostra sempre.

Mapeamento (declarado, não inferido além da etiqueta OSM):

- via power=line        -> arestas do tipo trecho_de_media_tensao/1
- via power=minor_line  -> arestas do tipo trecho_de_baixa_tensao/1
- nó power=tower        -> ponto_notavel/2 (torre), junção tipada
- nó power=pole         -> ponto_notavel/1 (poste), junção tipada
- nó power=transformer  -> transformador_de_distribuicao/1, dispositivo (CORTA a via: é ponto de rede)
- nó power=substation   -> subestacao/1, fonte (CORTA a via)
- nó power=generator    -> geracao_distribuida/2, dispositivo (CORTA a via)
- área power=substation -> subestacao/1, fonte (nó no centróide; liga às junções dentro da cerca)
- área power=plant|generator -> geracao_distribuida/2, dispositivo (nó no centróide)

Topologia (explícita, vem dos refs do extrato — nunca de coincidência geométrica inventada):

- uma via vira UM OU MAIS trechos (arestas): ela é cortada nos vértices que são (a) compartilhados
  com outra via de energia do recorte, (b) ponta da via ou (c) nó tipado que corta (transformador/
  subestação/gerador). Cada trecho grava `osm_way_id` nos atributos, então a contagem de LINHAS do
  extrato se confere por via, não por trecho;
- torre/poste NÃO cortam a via: viram junção tipada LIGADA ao trecho por associação de fixação
  estrutural (a regra fixacao_estrutural do pacote, validada pelo gatilho rede_associacao_validar);
- junção fora do polígono existe quando a via cruza o limite (a via entra inteira, sem corte);
  ativo (torre/poste/transformador/...) fora do polígono NÃO entra — conta em `fora_do_limite`.

Contagem conferida contra o extrato: para cada etiqueta, o que o extrato tinha dentro do recorte
(`arquivo`) contra o que entrou (`inserido`); o que não entrou vai para `desvios` com quantidade,
explicação e exemplos — nunca engolido em silêncio. Relações (multipolígonos) não entram nesta
passagem: contadas em `desvios.relacao_nao_importada`.

Isolamento entre fontes (a refutação do item): cada importação é uma rede própria do inquilino; os
gatilhos do modelo (aresta/subrede/associação) recusam qualquer ponta fora da rede, então um trecho
OSM nunca se liga a um nó BDGD sem uma associação explícita — e associação explícita entre fontes
não é criada por este conector.

Nada fixo no código: o extrato, o polígono e o nome do município são sempre parâmetros.

Teto de leitura: a leitura do extrato é em fluxo (osmium escreve OPL linha a linha no stdout do
subprocesso, nunca o .pbf inteiro carregado de uma vez), mas o que sobra depois do filtro
`nwr/power` ainda vai para dicionários em memória — por isso há um teto declarado
(`MAX_ELEMENTOS`, hoje 300 mil nós+vias): acima dele o subprocesso é encerrado e a importação
falha com erro explicado, em vez de a máquina ficar sem RAM (regra dura da casa: nunca extração
de OSM em memória sem limite).
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import time
from pathlib import Path

from psycopg2.extras import Json, execute_values

LOTE = 5000
EXEMPLOS_MAX = 5
# teto declarado da leitura em memória (nós+vias power=* do recorte já filtrado por osmium):
# município real medido (Taquari-RS, fixture do item) fica na casa das centenas; 300 mil
# elementos cobre uma capital inteira com folga e ainda impede o extrato errado (ex.: o Brasil
# inteiro por engano) de estourar a RAM da máquina (regra dura: nunca ler .pbf sem teto).
MAX_ELEMENTOS = 300_000

LICENCA_OSM = "ODbL 1.0 — OpenStreetMap contributors (www.openstreetmap.org/copyright)"
AVISO_OSM = "cadastro comunitário, não oficial"

# etiqueta OSM de nó -> (grupo do pacote eletrica-br, tipo_codigo, papel na rede)
MAPA_NO = {
    "tower": ("ponto_notavel", 2, "juncao"),
    "pole": ("ponto_notavel", 1, "juncao"),
    "transformer": ("transformador_de_distribuicao", 1, "dispositivo"),
    "substation": ("subestacao", 1, "fonte"),
    "generator": ("geracao_distribuida", 2, "dispositivo"),
}
# etiqueta OSM de via linear -> (grupo, tipo_codigo)
MAPA_VIA = {
    "line": ("trecho_de_media_tensao", 1),
    "minor_line": ("trecho_de_baixa_tensao", 1),
}
# etiqueta OSM de área (via fechada) -> (grupo, tipo_codigo, papel)
MAPA_AREA = {
    "substation": ("subestacao", 1, "fonte"),
    "plant": ("geracao_distribuida", 2, "dispositivo"),
    "generator": ("geracao_distribuida", 2, "dispositivo"),
}
# nós tipados que CORTAM a via (ponto onde a rede muda de dono do trecho)
NOS_QUE_CORTAM = {"transformer", "substation", "generator"}
# atributos OSM preservados (os demais ficam só no extrato)
ATRIBUTOS_VIA = ("power", "voltage", "operator", "name", "ref", "circuits", "cables", "wires", "frequency")
ATRIBUTOS_NO = ("power", "voltage", "operator", "name", "ref", "height", "structure", "design",
                "transformer", "rating", "source")


class ErroOsm(Exception):
    """Entrada inválida (arquivo ausente, osmium indisponível, pacote de ativos faltando)."""


def _texto(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def sha256_arquivo(caminho: str | Path) -> str:
    """Fingerprint do extrato inteiro (sha256 em blocos — vale para .pbf de qualquer porte)."""
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _osmium() -> str:
    exe = shutil.which("osmium")
    if exe is None:
        raise ErroOsm(
            "a ferramenta 'osmium' não está instalada nesta máquina (pacote osmium-tool): "
            "é ela que lê o extrato .pbf; sem ela o conector não roda"
        )
    return exe


def _ler_extrato(caminho: str | Path):
    """Fluxo OPL do subconjunto power=* do extrato (tags-filter inclui os nós referenciados pelas
    vias que casam — comportamento padrão do osmium, conferido na contagem do extrato da casa)."""
    caminho = Path(caminho)
    if not caminho.is_file():
        raise ErroOsm(f"extrato não encontrado: {caminho}")
    cmd = [_osmium(), "tags-filter", "--no-progress", str(caminho), "nwr/power", "-o", "-", "-f", "opl"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True, stderr=subprocess.PIPE)
    assert proc.stdout is not None
    nos: dict[int, tuple[float, float, dict]] = {}
    vias: list[tuple[int, list[int], dict]] = []
    relacoes = 0
    total = 0
    for linha in proc.stdout:
        tipo = linha[0]
        if tipo == "r":
            relacoes += 1
            continue
        total += 1
        if total > MAX_ELEMENTOS:
            # teto declarado (regra dura da casa): nunca ler extrato OSM em memória sem limite.
            # Corta o subprocesso na hora — não deixa o osmium terminar de gerar o resto — e
            # devolve erro explicado em vez de continuar acumulando nos/vias sem fim.
            proc.stdout.close()
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            raise ErroOsm(
                f"o extrato tem mais de {MAX_ELEMENTOS} elementos power=* dentro do subconjunto "
                "filtrado pelo osmium — acima do teto declarado desta leitura (nunca em memória "
                "sem limite); recorte um extrato menor (um município, não o estado/país inteiro) "
                "antes de importar"
            )
        if tipo == "n":
            partes = linha.split(" ")
            osm_id = int(partes[0][1:])
            lon = lat = None
            tags: dict[str, str] = {}
            for campo in partes[1:]:
                if campo.startswith("x"):
                    lon = float(campo[1:])
                elif campo.startswith("y"):
                    lat = float(campo[1:])
                elif campo.startswith("T"):
                    # OPL separa etiquetas por vírgula; valor com vírgula fica truncado — aceito
                    # e documentado: as etiquetas decisivas (power, voltage) nunca têm vírgula.
                    for par in campo[1:].rstrip("\n").split(","):
                        if "=" in par:
                            k, v = par.split("=", 1)
                            tags[k] = v
            if lon is not None and lat is not None:
                nos[osm_id] = (lon, lat, tags)
        elif tipo == "w":
            partes = linha.split(" ")
            osm_id = int(partes[0][1:])
            refs: list[int] = []
            tags = {}
            for campo in partes[1:]:
                if campo.startswith("N"):
                    refs = [int(x[1:]) for x in campo[1:].split(",") if x]
                elif campo.startswith("T"):
                    for par in campo[1:].rstrip("\n").split(","):
                        if "=" in par:
                            k, v = par.split("=", 1)
                            tags[k] = v
            vias.append((osm_id, refs, tags))
    proc.wait()
    if proc.returncode != 0:
        erro = proc.stderr.read() if proc.stderr else ""
        raise ErroOsm(f"osmium recusou o extrato ({proc.returncode}): {erro.strip()[:500]}")
    return nos, vias, relacoes


def _poligono(municipio_geojson: dict):
    """Polígono do município (GeoJSON: Geometry ou Feature ou FeatureCollection), em shapely."""
    from shapely.geometry import shape
    from shapely.ops import unary_union

    doc = municipio_geojson
    if doc.get("type") == "FeatureCollection":
        geoms = [shape(f["geometry"]) for f in doc.get("features", []) if f.get("geometry")]
    elif doc.get("type") == "Feature":
        geoms = [shape(doc["geometry"])]
    else:
        geoms = [shape(doc)]
    if not geoms:
        raise ErroOsm("o GeoJSON do município não tem geometria")
    pol = unary_union(geoms)
    if pol.is_empty:
        raise ErroOsm("a geometria do município é vazia")
    return pol


def _atributos(tags: dict, campos: tuple[str, ...]) -> dict:
    out = {c: tags[c] for c in campos if _texto(tags.get(c))}
    out["fonte"] = "OSM"
    out["confianca"] = "baixa"
    out["licenca"] = "ODbL"
    return out


def importar(cur, tenant_id: int, rede_id: str, caminho: str, municipio_geojson: dict,
             nome_municipio: str, progresso=None, registrar: bool = True) -> dict:
    """Monta a rede power=* do município. `cur` é um cursor já no contexto do inquilino (RLS de
    pé), numa transação do chamador. `progresso(pct, mensagem)` é opcional. Com `registrar`, a
    auditoria em `plat.rede_importacao` é aberta ('rodando') e fechada aqui mesmo."""
    imp = _Importador(cur, tenant_id, rede_id, caminho, municipio_geojson, nome_municipio,
                      progresso, registrar)
    return imp.rodar()


def contar_extrato(caminho: str | Path, municipio_geojson: dict) -> dict[str, int]:
    """Contagem do extrato por etiqueta, dentro do recorte — a régua pública contra a qual a
    carga é conferida (mesma leitura que o importador faz, sem gravar nada)."""
    nos, vias, relacoes = _ler_extrato(caminho)
    pol = _poligono(municipio_geojson)
    from shapely.geometry import LineString, Point
    from shapely.prepared import prep

    p = prep(pol)
    conta: dict[str, int] = {}
    for lon, lat, tags in nos.values():
        pw = tags.get("power")
        if pw in MAPA_NO and p.covers(Point(lon, lat)):
            conta[pw] = conta.get(pw, 0) + 1
    for _osm_id, refs, tags in vias:
        pw = tags.get("power")
        if pw in MAPA_VIA or (pw in MAPA_AREA and refs and refs[0] == refs[-1]):
            coords = [(nos[r][0], nos[r][1]) for r in refs if r in nos]
            minimo = 2 if pw in MAPA_VIA else 4
            if len(coords) >= minimo and pol.intersects(LineString(coords)):
                chave = pw if pw in MAPA_VIA else f"{pw}_area"
                conta[chave] = conta.get(chave, 0) + 1
    if relacoes:
        conta["relacao"] = relacoes
    return conta


class _Importador:
    def __init__(self, cur, tenant_id: int, rede_id: str, caminho: str, municipio_geojson: dict,
                 nome_municipio: str, progresso, registrar: bool):
        self.cur = cur
        self.tenant_id = tenant_id
        self.rede_id = rede_id
        self.caminho = str(caminho)
        self.geojson = municipio_geojson
        self.municipio = nome_municipio
        self.progresso = progresso or (lambda pct, msg: None)
        self.registrar = registrar
        self.desvios: dict[str, dict] = {}
        self.fora_do_limite: dict[str, int] = {}
        self.inseridos: dict[str, int] = {}
        self.tipos: dict[tuple[str, int], str] = {}
        self.nos_por_osm: dict[int, tuple[str, int]] = {}   # osm node id -> (rede_no.id, seq)
        self.arestas_por_codigo: dict[str, str] = {}        # codigo_externo -> rede_aresta.id
        self.importacao_id: str | None = None

    # ---------- utilidades ----------

    def _desvio(self, tipo: str, explicacao: str, codigo: str | None, quantidade: int = 1) -> None:
        d = self.desvios.setdefault(tipo, {"quantidade": 0, "explicacao": explicacao, "exemplos": []})
        d["quantidade"] += quantidade
        if codigo and len(d["exemplos"]) < EXEMPLOS_MAX:
            d["exemplos"].append(codigo)

    def _fora(self, etiqueta: str) -> None:
        self.fora_do_limite[etiqueta] = self.fora_do_limite.get(etiqueta, 0) + 1

    def _tipos_mapa(self) -> dict[tuple[str, int], str]:
        """(grupo, tipo_codigo) -> rede_tipo.id, da rede alvo (pacote eletrica-br já importado)."""
        self.cur.execute(
            "SELECT t.id, g.codigo AS grupo, t.codigo FROM plat.rede_tipo t "
            "JOIN plat.rede_grupo g ON g.id = t.grupo_id AND g.tenant_id = t.tenant_id "
            "WHERE t.rede_id = %s::uuid",
            (self.rede_id,),
        )
        mapa = {(r["grupo"], r["codigo"]): r["id"] for r in self.cur.fetchall()}
        precisa = ({(g, c) for g, c, _ in MAPA_NO.values()}
                   | set(MAPA_VIA.values())
                   | {(g, c) for g, c, _ in MAPA_AREA.values()})
        faltam = sorted(f"{g}/{c}" for g, c in precisa if (g, c) not in mapa)
        if faltam:
            raise ErroOsm(
                "a rede não tem os tipos de ativo que o conector OSM exige "
                "(importe o pacote eletrica-br antes): " + ", ".join(faltam)
            )
        return mapa

    def _tipo_id(self, grupo: str, codigo: int) -> str:
        return self.tipos[(grupo, codigo)]

    def _abrir_auditoria(self) -> None:
        if not self.registrar:
            return
        self.cur.execute(
            "INSERT INTO plat.rede_importacao (tenant_id, rede_id, fonte, caminho, distribuidora, "
            "sha256, licenca, aviso, municipio) "
            "VALUES (%s, %s::uuid, 'osm', %s, %s, %s, %s, %s, %s) RETURNING id",
            (self.tenant_id, self.rede_id, self.caminho, "OpenStreetMap contributors",
             sha256_arquivo(self.caminho), LICENCA_OSM, AVISO_OSM, self.municipio),
        )
        self.importacao_id = self.cur.fetchone()["id"]

    def _fechar_auditoria(self, resultado: dict | None, erro: str | None) -> None:
        if not self.registrar or self.importacao_id is None:
            return
        if erro is not None:
            self.cur.execute(
                "UPDATE plat.rede_importacao SET estado = 'falhou', erro = %s, atualizado_em = now() "
                "WHERE id = %s::uuid",
                (erro[:2000], self.importacao_id),
            )
        else:
            self.cur.execute(
                "UPDATE plat.rede_importacao SET estado = 'concluida', contagens = %s, desvios = %s, "
                "atualizado_em = now(), concluido_em = now() WHERE id = %s::uuid",
                (Json(resultado["contagens"]), Json(resultado["desvios"]), self.importacao_id),
            )

    # ---------- montagem ----------

    def rodar(self) -> dict:
        t0 = time.monotonic()
        # confere o extrato ANTES de abrir a auditoria (que já calcula o sha256 do arquivo): um
        # caminho inexistente vira ErroOsm explicado, nunca um FileNotFoundError cru sem tratamento
        # na rota (achado do teste `test_extrato_inexistente_e_erro_explicado_nao_excecao_crua`).
        if not Path(self.caminho).is_file():
            raise ErroOsm(f"extrato não encontrado: {self.caminho}")
        try:
            self.tipos = self._tipos_mapa()
            self._abrir_auditoria()

            self.progresso(5, "lendo o extrato (osmium, subconjunto power=*)")
            nos, vias, relacoes = _ler_extrato(self.caminho)
            pol = _poligono(self.geojson)

            self.progresso(15, "recortando ao município e derivando a topologia")
            plano = self._planejar(nos, vias, pol, relacoes)

            self.progresso(35, "gravando os nós da rede")
            self._gravar_nos(plano)
            self.progresso(60, "gravando os trechos")
            self._gravar_arestas(plano)
            self.progresso(75, "ligando torres e postes aos trechos (fixação estrutural)")
            self._gravar_fixacoes(plano)
            self.progresso(85, "áreas de subestação e geração (nó + conexão declarada)")
            self._gravar_areas(plano)
            self.progresso(92, "ativos sem via de rede (declarados)")
            self._gravar_avulsos(plano)
        except Exception as exc:
            self._fechar_auditoria(None, str(exc))
            raise

        contagens = self._contagens(plano)
        resultado = {
            "contagens": contagens,
            "trechos_gerados": self.inseridos.get("trecho", 0),
            "fixacoes": self.inseridos.get("fixacao", 0),
            "fora_do_limite": self.fora_do_limite,
            "desvios": self.desvios,
            "duracao_ms": int((time.monotonic() - t0) * 1000),
            "conferido": all(c["arquivo"] == c["inserido"] for c in contagens.values()),
            "importacao_id": str(self.importacao_id) if self.importacao_id else None,
        }
        self._fechar_auditoria(resultado, None)
        self.progresso(98, "auditoria gravada")
        return resultado

    def _planejar(self, nos: dict, vias: list, pol, relacoes: int) -> dict:
        """Recorte + plano de topologia, sem tocar no banco. Devolve o que cada fase grava."""
        from shapely.geometry import LineString, Point
        from shapely.prepared import prep

        p = prep(pol)
        dentro = {osm_id: p.covers(Point(lon, lat)) for osm_id, (lon, lat, _) in nos.items()}

        if relacoes:
            self._desvio(
                "relacao_nao_importada",
                "relação OSM com power=* (multipolígono): esta passagem lê nós e vias; a relação é "
                "contada aqui e fica no extrato",
                None, quantidade=relacoes,
            )

        # vias de energia do recorte (line/minor_line que intersectam o polígono, geometria inteira)
        vias_rede: list[tuple[int, list[int], dict]] = []
        for osm_id, refs, tags in vias:
            pw = tags.get("power")
            if pw not in MAPA_VIA:
                continue
            coords = [(nos[r][0], nos[r][1]) for r in refs if r in nos]
            if len(coords) < 2:
                self._desvio("via_sem_geometria",
                             "via power=* com menos de dois vértices resolúveis no extrato",
                             f"w{osm_id}")
                continue
            if not pol.intersects(LineString(coords)):
                continue
            vias_rede.append((osm_id, refs, tags))

        # grau de cada vértice entre as vias do recorte
        grau: dict[int, int] = {}
        for _, refs, _ in vias_rede:
            for r in refs:
                grau[r] = grau.get(r, 0) + 1

        cortam: set[int] = set()
        for _osm_id, refs, _tags in vias_rede:
            for i, r in enumerate(refs):
                pw = nos.get(r, (None, None, {}))[2].get("power")
                if i in (0, len(refs) - 1) or grau.get(r, 0) > 1 or pw in NOS_QUE_CORTAM:
                    cortam.add(r)

        # trechos (arestas): fatias da via entre vértices de corte consecutivos
        trechos: list[dict] = []
        for osm_id, refs, tags in vias_rede:
            pw = tags["power"]
            inicio = 0
            seq_trecho = 0
            for i in range(1, len(refs)):
                if refs[i] in cortam and i > inicio:
                    seq_trecho += 1
                    trechos.append({
                        "codigo": f"w{osm_id}#{seq_trecho:02d}",
                        "osm_way_id": osm_id, "power": pw,
                        "de": refs[inicio], "para": refs[i], "de_idx": inicio, "para_idx": i,
                        "coords": [(nos[r][0], nos[r][1]) for r in refs[inicio:i + 1] if r in nos],
                        "tags": tags,
                    })
                    inicio = i
            if inicio < len(refs) - 1:
                seq_trecho += 1
                trechos.append({
                    "codigo": f"w{osm_id}#{seq_trecho:02d}",
                    "osm_way_id": osm_id, "power": pw,
                    "de": refs[inicio], "para": refs[-1],
                    "de_idx": inicio, "para_idx": len(refs) - 1,
                    "coords": [(nos[r][0], nos[r][1]) for r in refs[inicio:] if r in nos],
                    "tags": tags,
                })

        # nós de vértice de corte; tipado só se o ativo está DENTRO do polígono
        nos_vertice: dict[int, dict] = {}
        for r in sorted(cortam):
            lon, lat, tags = nos.get(r, (None, None, {}))
            if lon is None:
                self._desvio("vertice_sem_geometria",
                             "vértice de via sem nó correspondente no extrato", f"n{r}")
                continue
            pw = tags.get("power")
            if pw in MAPA_NO and dentro.get(r):
                grupo, codigo, papel = MAPA_NO[pw]
                nos_vertice[r] = {"osm_id": r, "lon": lon, "lat": lat, "etiqueta": pw,
                                  "grupo": grupo, "tipo_codigo": codigo, "papel": papel,
                                  "tags": tags, "tipado": True}
            else:
                if pw in MAPA_NO:
                    self._fora(pw)
                nos_vertice[r] = {"osm_id": r, "lon": lon, "lat": lat, "etiqueta": pw,
                                  "grupo": None, "tipo_codigo": None, "papel": "juncao",
                                  "tags": tags, "tipado": False}

        # torres/postes sobre as vias, fora dos pontos de corte: fixação estrutural no trecho
        estruturas: list[dict] = []
        trechos_por_via: dict[int, list[dict]] = {}
        for t in trechos:
            trechos_por_via.setdefault(t["osm_way_id"], []).append(t)
        for osm_id, refs, _tags in vias_rede:
            for i, r in enumerate(refs):
                pw = nos.get(r, (None, None, {}))[2].get("power")
                if pw not in ("tower", "pole") or r in cortam:
                    continue
                if not dentro.get(r):
                    self._fora(pw)
                    continue
                # o trecho que contém o vértice i da via (pelos índices dos refs, nunca pela
                # geometria acumulada — vértice sem nó no extrato não desalinha a conta)
                dono = None
                for t in trechos_por_via.get(osm_id, []):
                    if t["de_idx"] <= i <= t["para_idx"]:
                        dono = t
                        break
                if dono is None:
                    self._desvio("estrutura_sem_trecho",
                                 "torre/poste sobre a via sem trecho correspondente no plano", f"n{r}")
                    continue
                grupo, codigo, papel = MAPA_NO[pw]
                lon, lat, ttags = nos[r]
                estruturas.append({"osm_id": r, "lon": lon, "lat": lat, "etiqueta": pw,
                                   "grupo": grupo, "tipo_codigo": codigo, "tags": ttags,
                                   "trecho": dono["codigo"], "trecho_tipo": MAPA_VIA[dono["power"]]})

        # áreas (subestação, usina, gerador como polígono fechado)
        areas: list[dict] = []
        for osm_id, refs, tags in vias:
            pw = tags.get("power")
            if pw not in MAPA_AREA or not refs or refs[0] != refs[-1]:
                continue
            coords = [(nos[r][0], nos[r][1]) for r in refs if r in nos]
            if len(coords) < 4:
                self._desvio("area_sem_geometria",
                             "área power=* com anel incompleto no extrato", f"w{osm_id}")
                continue
            from shapely.geometry import Polygon
            anel = Polygon(coords)
            if not pol.intersects(anel):
                continue
            grupo, codigo, papel = MAPA_AREA[pw]
            juncoes_dentro = [r for r, n in nos_vertice.items()
                              if anel.covers(Point(n["lon"], n["lat"]))]
            areas.append({"osm_id": osm_id, "etiqueta": pw, "grupo": grupo, "tipo_codigo": codigo,
                          "papel": papel, "tags": tags, "coords": coords,
                          "juncoes_dentro": juncoes_dentro})

        # ativos pontuais DENTRO do polígono que não são vértice de via do recorte
        vertices_usados = set(nos_vertice) | {e["osm_id"] for e in estruturas}
        avulsos: list[dict] = []
        for osm_id, (lon, lat, tags) in nos.items():
            pw = tags.get("power")
            if pw not in MAPA_NO or osm_id in vertices_usados or not dentro.get(osm_id):
                continue
            grupo, codigo, papel = MAPA_NO[pw]
            avulsos.append({"osm_id": osm_id, "lon": lon, "lat": lat, "etiqueta": pw,
                            "grupo": grupo, "tipo_codigo": codigo, "papel": papel, "tags": tags})
            self._desvio("ativo_sem_via_de_rede",
                         "ativo power=* dentro do município sem via de energia do recorte passando "
                         "por ele: entra como nó tipado sem conexão (o extrato não declara a ligação)",
                         f"n{osm_id}")

        return {"vias_rede": vias_rede, "trechos": trechos, "nos_vertice": nos_vertice,
                "estruturas": estruturas, "areas": areas, "avulsos": avulsos,
                "dentro": dentro, "nos": nos}

    def _gravar_nos(self, plano: dict) -> None:
        """Nós de vértice de corte e estruturas (torre/poste). codigo_externo = 'n<osm_id>'."""
        pendentes: list[tuple] = []
        for n in plano["nos_vertice"].values():
            tipo_id = self._tipo_id(n["grupo"], n["tipo_codigo"]) if n["tipado"] else None
            pendentes.append((self.tenant_id, self.rede_id, n["papel"], tipo_id,
                              f"n{n['osm_id']}", n["lon"], n["lat"],
                              Json(_atributos(n["tags"], ATRIBUTOS_NO))))
        for e in plano["estruturas"]:
            pendentes.append((self.tenant_id, self.rede_id, "juncao",
                              self._tipo_id(e["grupo"], e["tipo_codigo"]),
                              f"n{e['osm_id']}", e["lon"], e["lat"],
                              Json(_atributos(e["tags"], ATRIBUTOS_NO))))
        for i in range(0, len(pendentes), LOTE):
            execute_values(
                self.cur,
                "INSERT INTO plat.rede_no (tenant_id, rede_id, papel, tipo_id, codigo_externo, geom, atributos) "
                "VALUES %s ON CONFLICT (rede_id, papel, codigo_externo) DO NOTHING",
                pendentes[i: i + LOTE],
                template="(%s, %s::uuid, %s, %s::uuid, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s)",
                page_size=LOTE,
            )
        codigos = [t[4] for t in pendentes]
        for i in range(0, len(codigos), LOTE):
            self.cur.execute(
                "SELECT id, seq, codigo_externo FROM plat.rede_no "
                "WHERE rede_id = %s::uuid AND codigo_externo = ANY(%s)",
                (self.rede_id, codigos[i: i + LOTE]),
            )
            for r in self.cur.fetchall():
                self.nos_por_osm[int(r["codigo_externo"][1:])] = (r["id"], int(r["seq"]))
        self.inseridos["no"] = len(pendentes)

    def _gravar_arestas(self, plano: dict) -> None:
        pendentes: list[tuple] = []
        wkt_vazio = 0
        for t in plano["trechos"]:
            de = self.nos_por_osm.get(t["de"])
            para = self.nos_por_osm.get(t["para"])
            if de is None or para is None:
                self._desvio("trecho_sem_ponta",
                             "trecho com ponta sem nó na rede (vértice sem geometria no extrato)",
                             t["codigo"])
                continue
            if len(t["coords"]) < 2:
                wkt_vazio += 1
                self._desvio("trecho_sem_geometria",
                             "trecho com menos de dois vértices com coordenada", t["codigo"])
                continue
            grupo, codigo = MAPA_VIA[t["power"]]
            wkt = "LINESTRING(" + ",".join(f"{x} {y}" for x, y in t["coords"]) + ")"
            atributos = _atributos(t["tags"], ATRIBUTOS_VIA)
            atributos["osm_way_id"] = t["osm_way_id"]
            pendentes.append((self.tenant_id, self.rede_id, self._tipo_id(grupo, codigo),
                              t["codigo"], de[0], para[0], wkt, wkt, Json(atributos)))
        for i in range(0, len(pendentes), LOTE):
            execute_values(
                self.cur,
                "INSERT INTO plat.rede_aresta (tenant_id, rede_id, tipo_id, codigo_externo, "
                "no_origem_id, no_destino_id, no_origem_seq, no_destino_seq, geom, comprimento_m, atributos) "
                "VALUES %s ON CONFLICT (rede_id, codigo_externo) DO NOTHING",
                pendentes[i: i + LOTE],
                template="(%s, %s::uuid, %s::uuid, %s, %s::uuid, %s::uuid, 0, 0, "
                         "ST_GeomFromText(%s, 4326), "
                         "ST_Length(ST_GeomFromText(%s, 4326)::geography), %s)",
                page_size=LOTE,
            )
        codigos = [t[3] for t in pendentes]
        for i in range(0, len(codigos), LOTE):
            self.cur.execute(
                "SELECT id, codigo_externo FROM plat.rede_aresta "
                "WHERE rede_id = %s::uuid AND codigo_externo = ANY(%s)",
                (self.rede_id, codigos[i: i + LOTE]),
            )
            for r in self.cur.fetchall():
                self.arestas_por_codigo[r["codigo_externo"]] = r["id"]
        self.inseridos["trecho"] = len(pendentes)

    def _gravar_fixacoes(self, plano: dict) -> None:
        """Associação de fixação estrutural torre/poste -> trecho, filtrada pela MESMA régua do
        gatilho (regra fixacao_estrutural no catálogo): o que o pacote não cobre vira desvio."""
        gravadas = 0
        for e in plano["estruturas"]:
            no = self.nos_por_osm.get(e["osm_id"])
            aresta = self.arestas_por_codigo.get(e["trecho"])
            if no is None or aresta is None:
                self._desvio("fixacao_sem_elemento",
                             "estrutura ou trecho da fixação não encontrado depois da gravação",
                             f"n{e['osm_id']}")
                continue
            tipo_id = self._tipo_id(e["grupo"], e["tipo_codigo"])
            aresta_tipo_id = self._tipo_id(*e["trecho_tipo"])
            self.cur.execute(
                "INSERT INTO plat.rede_associacao (tenant_id, rede_id, tipo, de_no_id, para_aresta_id, origem) "
                "SELECT %s, %s::uuid, 'fixacao', %s::uuid, %s::uuid, 'importacao' "
                "WHERE EXISTS ("
                "  SELECT 1 FROM plat.rede_regra r WHERE r.rede_id = %s::uuid AND r.tipo = 'fixacao_estrutural' "
                "  AND ((r.de_tipo_id = %s::uuid AND r.para_tipo_id = %s::uuid) "
                "    OR (r.de_tipo_id = %s::uuid AND r.para_tipo_id = %s::uuid))"
                ") RETURNING id",
                (self.tenant_id, self.rede_id, no[0], aresta, self.rede_id,
                 aresta_tipo_id, tipo_id, tipo_id, aresta_tipo_id),
            )
            if self.cur.fetchone() is None:
                self._desvio(
                    "fixacao_sem_regra_no_pacote",
                    "o catálogo do pacote não tem regra de fixação estrutural entre o tipo da "
                    "estrutura e o tipo do trecho (ex.: torre sobre linha de baixa tensão) — a "
                    "estrutura fica gravada, a fixação não",
                    f"n{e['osm_id']}",
                )
            else:
                gravadas += 1
        self.inseridos["fixacao"] = gravadas

    def _gravar_areas(self, plano: dict) -> None:
        for a in plano["areas"]:
            wkt = "POLYGON((" + ",".join(f"{x} {y}" for x, y in a["coords"]) + "))"
            self.cur.execute(
                "INSERT INTO plat.rede_no (tenant_id, rede_id, papel, tipo_id, codigo_externo, geom, atributos) "
                "VALUES (%s, %s::uuid, %s, %s::uuid, %s, "
                "ST_PointOnSurface(ST_SetSRID(ST_GeomFromText(%s, 4326), 4326)), %s) "
                "ON CONFLICT (rede_id, papel, codigo_externo) DO NOTHING RETURNING id",
                (self.tenant_id, self.rede_id, a["papel"], self._tipo_id(a["grupo"], a["tipo_codigo"]),
                 f"w{a['osm_id']}", wkt, Json(_atributos(a["tags"], ATRIBUTOS_NO) | {"osm_way_id": a["osm_id"]})),
            )
            r = self.cur.fetchone()
            if r is None:
                self._desvio("area_duplicada", "área com identificador repetido", f"w{a['osm_id']}")
                continue
            self.inseridos[a["etiqueta"] + "_area"] = self.inseridos.get(a["etiqueta"] + "_area", 0) + 1
            if not a["juncoes_dentro"]:
                self._desvio(
                    "area_sem_juncao_dentro",
                    "nenhuma junção de via de energia do recorte cai dentro da área: o nó entra sem "
                    "conexão declarada (o extrato não liga a cerca à rede)",
                    f"w{a['osm_id']}",
                )
                continue
            ligou = False
            for osm_no in a["juncoes_dentro"]:
                no = self.nos_por_osm.get(osm_no)
                if no is None:
                    continue
                self.cur.execute(
                    "INSERT INTO plat.rede_associacao (tenant_id, rede_id, tipo, de_no_id, para_no_id, origem) "
                    "SELECT %s, %s::uuid, 'conectividade', %s::uuid, %s::uuid, 'importacao' "
                    "WHERE EXISTS ("
                    "  SELECT 1 FROM plat.rede_aresta ar JOIN plat.rede_regra rr "
                    "    ON rr.rede_id = %s::uuid AND rr.tipo = 'conectividade_no_trecho' "
                    "   AND ((rr.de_tipo_id = ar.tipo_id AND rr.para_tipo_id = %s::uuid) "
                    "     OR (rr.de_tipo_id = %s::uuid AND rr.para_tipo_id = ar.tipo_id)) "
                    "  WHERE ar.rede_id = %s::uuid AND (ar.no_origem_id = %s::uuid OR ar.no_destino_id = %s::uuid)"
                    ") RETURNING id",
                    (self.tenant_id, self.rede_id, r["id"], no[0], self.rede_id,
                     self._tipo_id(a["grupo"], a["tipo_codigo"]),
                     self._tipo_id(a["grupo"], a["tipo_codigo"]), self.rede_id, no[0], no[0]),
                )
                if self.cur.fetchone() is not None:
                    ligou = True
            if not ligou:
                self._desvio(
                    "area_sem_regra_de_conexao",
                    "as junções dentro da área não têm aresta incidente com regra de conectividade "
                    "para o tipo do ativo no catálogo do pacote",
                    f"w{a['osm_id']}",
                )

    def _gravar_avulsos(self, plano: dict) -> None:
        pendentes = [
            (self.tenant_id, self.rede_id, a["papel"], self._tipo_id(a["grupo"], a["tipo_codigo"]),
             f"n{a['osm_id']}", a["lon"], a["lat"], Json(_atributos(a["tags"], ATRIBUTOS_NO)))
            for a in plano["avulsos"]
        ]
        for i in range(0, len(pendentes), LOTE):
            execute_values(
                self.cur,
                "INSERT INTO plat.rede_no (tenant_id, rede_id, papel, tipo_id, codigo_externo, geom, atributos) "
                "VALUES %s ON CONFLICT (rede_id, papel, codigo_externo) DO NOTHING",
                pendentes[i: i + LOTE],
                template="(%s, %s::uuid, %s, %s::uuid, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s)",
                page_size=LOTE,
            )
        self.inseridos["avulsos"] = len(pendentes)

    def _contagens(self, plano: dict) -> dict:
        """`arquivo` = o que o extrato tinha dentro do recorte; `inserido` = o que virou elemento
        da rede. Linha confere POR VIA (osm_way_id distinto nos trechos), não por trecho."""
        vias_por_etiqueta: dict[str, set[int]] = {}
        for t in plano["trechos"]:
            if t["codigo"] in self.arestas_por_codigo:
                vias_por_etiqueta.setdefault(t["power"], set()).add(t["osm_way_id"])

        arquivo_via: dict[str, int] = {}
        for _osm_id, _, tags in plano["vias_rede"]:
            pw = tags["power"]
            arquivo_via[pw] = arquivo_via.get(pw, 0) + 1

        conta: dict[str, dict] = {}
        for pw in MAPA_VIA:
            conta[pw] = {"arquivo": arquivo_via.get(pw, 0),
                         "inserido": len(vias_por_etiqueta.get(pw, set()))}

        dentro = plano["dentro"]
        vertices_tipados = {r for r, n in plano["nos_vertice"].items() if n["tipado"]}
        for pw in ("tower", "pole", "transformer", "substation", "generator"):
            arquivo = sum(1 for osm_id, (_, _, tags) in plano["nos"].items()
                          if tags.get("power") == pw and dentro.get(osm_id))
            inserido = (
                sum(1 for r in vertices_tipados
                    if plano["nos_vertice"][r]["etiqueta"] == pw)
                + sum(1 for e in plano["estruturas"] if e["etiqueta"] == pw
                      and e["osm_id"] in self.nos_por_osm)
                + sum(1 for a in plano["avulsos"] if a["etiqueta"] == pw)
            )
            if arquivo or inserido:
                conta[pw] = {"arquivo": arquivo, "inserido": inserido}
        for pw in MAPA_AREA:
            chave = f"{pw}_area"
            arquivo = sum(1 for a in plano["areas"] if a["etiqueta"] == pw)
            inserido = self.inseridos.get(chave, 0)
            if arquivo or inserido:
                conta[chave] = {"arquivo": arquivo, "inserido": inserido}
        return conta
