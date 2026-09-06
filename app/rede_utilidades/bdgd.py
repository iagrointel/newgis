"""Importador da BDGD (ANEEL) para o modelo de elementos da rede de utilidades (item
L4-01-modelo-rede; ADR 20260906T2126). Lê um FileGDB de distribuidora (camadas SUB, CTMT, SSDMT,
UNTRMT, UNSEMT, SSDBT, RAMLIG, UCBT_tab, UCMT_tab, PONNOT) e monta a rede de negócio inteira:

- junção (`rede_no` papel 'juncao') por ponto de conexão nomeado (PN_CON/PAC), com a geometria do
  PONNOT quando ela existe — ponto de conexão sem PONNOT entra sem geometria e é explicado;
- aresta por trecho (SSDMT/SSDBT) e por ramal de ligação (RAMLIG, sem geometria na BDGD —
  `comprimento_m` NULL declarado, nunca zero disfarçado);
- nó 'fonte' por subestação (SUB), 'dispositivo' por transformador (UNTRMT) e por chave (UNSEMT,
  com estado de manobra de P_N_OPE), 'consumidor' por unidade consumidora (UCBT_tab/UCMT_tab);
- hierarquia de subredes: subestação (nível 1) -> alimentador (nível 2, CTMT) -> transformador
  (nível 3, controlador da baixa tensão dele);
- associação de conectividade explícita (o ativo com a junção onde a fonte diz que ele se liga).
  O gatilho `rede_associacao_validar` confere cada uma contra o catálogo de regras do pacote; o
  importador já filtra com a mesma régua (EXISTS no SQL do lote) para que uma distribuidora com
  dado fora do catálogo entre com o desvio contado e explicado, em vez de abortar a carga.

Contagem conferida contra o arquivo: para cada camada, o feature count lido do GDB
(`pyogrio.read_info`) é comparado com o que entrou; o que não entrou vai para `desvios` com
quantidade, explicação e exemplos — nunca engolido em silêncio. O resultado é gravado em
`plat.rede_importacao` (auditoria) e devolvido como dict.

Sem placeholder: nenhum caminho é fixo no código; o GDB de entrada é sempre parâmetro.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

import pyogrio
from psycopg2.extras import Json, execute_values

# camadas de feição conferidas, na ordem de dependência da montagem. SUB/CTMT/SSDMT/UNTRMT/SSDBT/
# UCBT_tab são o mínimo do portão; as demais enriquecem o mesmo modelo (chave com estado, ramal,
# consumidor de MT) e são contadas da mesma forma. PONNOT não é camada de feição do modelo (é a
# geometria dos pontos de conexão): entra como apoio, reportada à parte.
CAMADAS = ("SUB", "CTMT", "SSDMT", "UNTRMT", "SSDBT", "UCBT_tab", "RAMLIG", "UNSEMT", "UCMT_tab")
CAMADAS_APOIO = ("PONNOT",)

# camada -> (grupo do pacote eletrica-br, tipo_codigo). A tipificação fina da BDGD (TIP_UNID, POS
# etc.) fica preservada em `atributos`; o tipo do pacote é o que a regra de conectividade usa
# (ver docs/rede/MODELO_REDE.md seção 4).
TIPO_POR_CAMADA = {
    "SUB": ("subestacao", 1),
    "SSDMT": ("trecho_de_media_tensao", 1),
    "SSDBT": ("trecho_de_baixa_tensao", 1),
    "RAMLIG": ("ramal_de_ligacao", 1),
    "UNTRMT": ("transformador_de_distribuicao", 1),
    "UNSEMT": ("chave_de_media_tensao", 1),
    "UCBT_tab": ("unidade_consumidora", 1),
    "UCMT_tab": ("unidade_consumidora", 2),
}

LOTE = 5000
EXEMPLOS_MAX = 5
CAMPOS_TECNICOS = {"Shape_Length", "Shape_Area", "geometry"}
SRID_FONTE = 4674  # SIRGAS 2000, o datum de toda BDGD


class ErroBdgd(Exception):
    """Entrada inválida (arquivo ausente, camada ilegível, pacote de ativos faltando)."""


def _texto(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def inspecionar(caminho: str | Path) -> dict[str, int]:
    """Feature count por camada do GDB — a régua contra a qual a carga é conferida."""
    caminho = Path(caminho)
    if not caminho.is_dir():
        raise ErroBdgd(f"arquivo não encontrado: {caminho}")
    contagens = {}
    for camada in CAMADAS + CAMADAS_APOIO:
        try:
            contagens[camada] = int(pyogrio.read_info(str(caminho), layer=camada)["features"])
        except Exception:
            contagens[camada] = 0  # camada ausente no GDB da distribuidora: 0 declarado, não erro
    return contagens


def sha256_gdb(caminho: str | Path) -> str:
    """Fingerprint do FileGDB: sha256 encadeado de nome+tamanho de cada arquivo e do conteúdo dos
    arquivos de controle (os .gdbtable grandes entram por nome+tamanho — uma troca de arquivo fica
    visível sem ler ~100 MB por importação)."""
    caminho = Path(caminho)
    h = hashlib.sha256()
    for arq in sorted(caminho.iterdir()):
        if not arq.is_file():
            continue
        h.update(arq.name.encode())
        h.update(str(arq.stat().st_size).encode())
        if arq.stat().st_size < (1 << 20):
            h.update(arq.read_bytes())
    return h.hexdigest()


def _ler(caminho: str, camada: str, geometria: bool = True):
    """Lê a camada inteira como dataframe (a maior camada de uma distribuidora média fica abaixo de
    100 mil linhas com geometria de linha — cabe na cota de memória do worker, medido na CERTEL)."""
    try:
        return pyogrio.read_dataframe(caminho, layer=camada, read_geometry=geometria, fid_as_index=True)
    except Exception as exc:
        raise ErroBdgd(f"falha ao ler a camada {camada}: {exc}") from exc


def _atributos(linha) -> dict:
    """Campos da fonte preservados como vieram (tipificação fina, fases, potência), sem os técnicos."""
    out = {}
    for k, v in linha.items():
        if k in CAMPOS_TECNICOS:
            continue
        if v is None or (isinstance(v, float) and v != v):
            continue
        if hasattr(v, "item"):  # numpy -> python, para o Json não engasgar
            v = v.item()
        out[k] = v
    return out


def _wkb_linha(geom) -> tuple[bytes | None, bool]:
    """(wkb, multipart_real). Multipart com uma parte vira a parte; multipart real entra pela
    primeira parte e o chamador conta o desvio."""
    if geom is None or geom.is_empty:
        return None, False
    if geom.geom_type == "MultiLineString":
        partes = list(geom.geoms)
        if not partes:
            return None, False
        return partes[0].wkb, len(partes) > 1
    if geom.geom_type == "LineString":
        return geom.wkb, False
    return None, False


def _wkb_ponto(geom) -> bytes | None:
    if geom is None or geom.is_empty:
        return None
    if geom.geom_type == "Point":
        return geom.wkb
    if geom.geom_type == "MultiPoint":
        partes = list(geom.geoms)
        return partes[0].wkb if partes else None
    return None


def importar(cur, tenant_id: int, rede_id: str, caminho: str, progresso=None,
             registrar: bool = True) -> dict:
    """Monta a rede inteira a partir do GDB. `cur` é um cursor já no contexto do inquilino (RLS de
    pé), numa transação do chamador. `progresso(pct, mensagem)` é opcional (o job usa). Com
    `registrar`, a auditoria em `plat.rede_importacao` é aberta ('rodando') e fechada aqui mesmo
    ('concluida' com contagens e desvios, ou 'falhou' com o erro — o erro sobe depois de gravado)."""
    imp = _Importador(cur, tenant_id, rede_id, caminho, progresso, registrar)
    return imp.rodar()


class _Importador:
    def __init__(self, cur, tenant_id: int, rede_id: str, caminho: str, progresso, registrar: bool):
        self.cur = cur
        self.tenant_id = tenant_id
        self.rede_id = rede_id
        self.caminho = str(caminho)
        self.progresso = progresso or (lambda pct, msg: None)
        self.registrar = registrar
        self.desvios: dict[str, dict] = {}
        self.inseridos: dict[str, int] = {}
        self.tipos: dict[tuple[str, int], str] = {}
        self.subredes: dict[tuple[int, str], str] = {}   # (nivel, codigo) -> id
        self.juncoes: dict[str, tuple[str, int]] = {}    # codigo -> (id, seq)
        self.importacao_id: str | None = None

    # ---------- utilidades ----------

    def _desvio(self, tipo: str, explicacao: str, codigo: str | None, quantidade: int = 1) -> None:
        d = self.desvios.setdefault(tipo, {"quantidade": 0, "explicacao": explicacao, "exemplos": []})
        d["quantidade"] += quantidade
        if codigo and len(d["exemplos"]) < EXEMPLOS_MAX:
            d["exemplos"].append(codigo)

    def _tipos_mapa(self) -> dict[tuple[str, int], str]:
        """(grupo, tipo_codigo) -> rede_tipo.id, da rede alvo (pacote já importado, item L4-01-a)."""
        self.cur.execute(
            "SELECT t.id, g.codigo AS grupo, t.codigo FROM plat.rede_tipo t "
            "JOIN plat.rede_grupo g ON g.id = t.grupo_id AND g.tenant_id = t.tenant_id "
            "WHERE t.rede_id = %s::uuid",
            (self.rede_id,),
        )
        mapa = {(r["grupo"], r["codigo"]): r["id"] for r in self.cur.fetchall()}
        faltam = sorted({c for c in TIPO_POR_CAMADA if TIPO_POR_CAMADA[c] not in mapa})
        if faltam:
            raise ErroBdgd(
                "a rede não tem os tipos de ativo que a BDGD exige (importe o pacote eletrica-br antes): "
                + ", ".join(faltam)
            )
        return mapa

    def _tipo_id(self, camada: str) -> str:
        return self.tipos[TIPO_POR_CAMADA[camada]]

    def _abrir_auditoria(self, arquivo: dict[str, int]) -> None:
        if not self.registrar:
            return
        self.cur.execute(
            "INSERT INTO plat.rede_importacao (tenant_id, rede_id, fonte, caminho, distribuidora, sha256) "
            "VALUES (%s, %s::uuid, 'bdgd', %s, %s, %s) RETURNING id",
            (self.tenant_id, self.rede_id, self.caminho, Path(self.caminho).name,
             sha256_gdb(self.caminho)),
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
        arquivo = inspecionar(self.caminho)
        try:
            self.tipos = self._tipos_mapa()
            self._abrir_auditoria(arquivo)

            self.progresso(5, "lendo pontos de conexão (PONNOT)")
            geometrias = self._pontos_notaveis()

            self.progresso(10, "subestações e alimentadores (SUB/CTMT)")
            self._fontes_e_alimentadores()
            self.progresso(15, "trechos de média tensão (SSDMT)")
            self._trechos("SSDMT", geometrias)
            self.progresso(35, "transformadores (UNTRMT)")
            self._dispositivos("UNTRMT", geometrias)
            self.progresso(45, "chaves de média tensão (UNSEMT)")
            self._dispositivos("UNSEMT", geometrias)
            self.progresso(50, "trechos de baixa tensão (SSDBT)")
            self._trechos("SSDBT", geometrias)
            self.progresso(70, "ramais de ligação (RAMLIG)")
            self._trechos("RAMLIG", geometrias)
            self.progresso(80, "unidades consumidoras (UCBT/UCMT)")
            self._consumidores("UCBT_tab", geometrias)
            self._consumidores("UCMT_tab", geometrias)
        except Exception as exc:
            self._fechar_auditoria(None, str(exc))
            raise

        contagens = {
            camada: {"arquivo": arquivo[camada], "inserido": self.inseridos.get(camada, 0)}
            for camada in CAMADAS
        }
        resultado = {
            "contagens": contagens,
            "apoio": {c: {"arquivo": arquivo[c], "papel": "geometria das junções"} for c in CAMADAS_APOIO},
            "desvios": self.desvios,
            "duracao_ms": int((time.monotonic() - t0) * 1000),
            "conferido": all(c["arquivo"] == c["inserido"] for c in contagens.values()),
            "importacao_id": str(self.importacao_id) if self.importacao_id else None,
        }
        self._fechar_auditoria(resultado, None)
        self.progresso(98, "auditoria gravada")
        return resultado

    def _pontos_notaveis(self) -> dict[str, bytes]:
        """codigo do ponto de conexão -> WKB (EPSG:4674), da camada PONNOT."""
        df = _ler(self.caminho, "PONNOT")
        out = {}
        for _, linha in df.iterrows():
            cod = _texto(linha.get("COD_ID"))
            wkb = _wkb_ponto(linha.geometry)
            if cod and wkb:
                out[cod] = wkb
        return out

    def _fontes_e_alimentadores(self) -> None:
        subs = _ler(self.caminho, "SUB")
        for _, linha in subs.iterrows():
            cod = _texto(linha.get("COD_ID"))
            if not cod:
                self._desvio("sub_sem_codigo", "subestação sem COD_ID: impossível nomear a subrede", None)
                continue
            geom = linha.geometry
            wkb = geom.wkb if geom is not None and not geom.is_empty else None
            self.cur.execute(
                "INSERT INTO plat.rede_no (tenant_id, rede_id, papel, tipo_id, codigo_externo, geom, atributos) "
                "VALUES (%s, %s::uuid, 'fonte', %s::uuid, %s, "
                "ST_PointOnSurface(ST_Transform(ST_SetSRID(ST_GeomFromWKB(%s), %s), 4326)), %s) "
                "ON CONFLICT (rede_id, papel, codigo_externo) DO NOTHING RETURNING id",
                (self.tenant_id, self.rede_id, self._tipo_id("SUB"), cod, wkb, SRID_FONTE,
                 Json(_atributos(linha))),
            )
            r = self.cur.fetchone()
            if r is None:
                self._desvio("fonte_duplicada", "COD_ID de subestação repetido no arquivo", cod)
                continue
            self.cur.execute(
                "INSERT INTO plat.rede_subrede (tenant_id, rede_id, nivel, codigo_externo, nome, controlador_no_id) "
                "VALUES (%s, %s::uuid, 1, %s, %s, %s::uuid) "
                "ON CONFLICT (rede_id, nivel, codigo_externo) DO NOTHING RETURNING id",
                (self.tenant_id, self.rede_id, cod, _texto(linha.get("NOME")), r["id"]),
            )
            r2 = self.cur.fetchone()
            if r2:
                self.subredes[(1, cod)] = r2["id"]
            self.inseridos["SUB"] = self.inseridos.get("SUB", 0) + 1

        ctmts = _ler(self.caminho, "CTMT", geometria=False)
        for _, linha in ctmts.iterrows():
            cod = _texto(linha.get("COD_ID"))
            if not cod:
                self._desvio("alimentador_sem_codigo", "alimentador sem COD_ID", None)
                continue
            sub = _texto(linha.get("SUB"))
            pai = self.subredes.get((1, sub)) if sub else None
            if sub and pai is None:
                self._desvio(
                    "alimentador_sem_subestacao",
                    "o campo SUB do alimentador não casa com nenhuma SUB do arquivo",
                    cod,
                )
                continue  # o gatilho recusa nível 2 sem pai; o desvio explica a ausência
            self.cur.execute(
                "INSERT INTO plat.rede_subrede (tenant_id, rede_id, nivel, codigo_externo, nome, pai_id, atributos) "
                "VALUES (%s, %s::uuid, 2, %s, %s, %s::uuid, %s) "
                "ON CONFLICT (rede_id, nivel, codigo_externo) DO NOTHING RETURNING id",
                (self.tenant_id, self.rede_id, cod, _texto(linha.get("NOME")), pai,
                 Json(_atributos(linha))),
            )
            r = self.cur.fetchone()
            if r:
                self.subredes[(2, cod)] = r["id"]
                self.inseridos["CTMT"] = self.inseridos.get("CTMT", 0) + 1
            else:
                self._desvio("alimentador_duplicado", "COD_ID de alimentador repetido no arquivo", cod)

    def _garantir_juncoes(self, codigos: set[str], geometrias: dict[str, bytes]) -> None:
        """Insere as junções novas (dedup por código) e atualiza o mapa codigo -> (id, seq)."""
        novas = sorted(c for c in codigos if c and c not in self.juncoes)
        for i in range(0, len(novas), LOTE):
            fatia = novas[i : i + LOTE]
            tuplas = []
            for c in fatia:
                wkb = geometrias.get(c)
                if wkb is None:
                    self._desvio(
                        "juncao_sem_geometria",
                        "ponto de conexão sem feição no PONNOT: a junção existe (a conectividade é "
                        "explícita pelo código) mas não tem coordenada",
                        c,
                    )
                tuplas.append((self.tenant_id, self.rede_id, "juncao", c, wkb))
            execute_values(
                self.cur,
                "INSERT INTO plat.rede_no (tenant_id, rede_id, papel, codigo_externo, geom) VALUES %s "
                "ON CONFLICT (rede_id, papel, codigo_externo) DO NOTHING",
                tuplas,
                template="(%s, %s::uuid, %s, %s, "
                         "ST_Transform(ST_SetSRID(ST_GeomFromWKB(%s), " + str(SRID_FONTE) + "), 4326))",
                page_size=LOTE,
            )
        if novas:
            self.cur.execute(
                "SELECT id, seq, codigo_externo FROM plat.rede_no "
                "WHERE rede_id = %s::uuid AND papel = 'juncao' AND codigo_externo = ANY(%s)",
                (self.rede_id, novas),
            )
            for r in self.cur.fetchall():
                self.juncoes[r["codigo_externo"]] = (r["id"], int(r["seq"]))

    def _trechos(self, camada: str, geometrias: dict[str, bytes]) -> None:
        df = _ler(self.caminho, camada, geometria=(camada != "RAMLIG"))
        codigos = set()
        for col in ("PN_CON_1", "PN_CON_2"):
            if col in df.columns:
                codigos.update(_texto(v) for v in df[col])
        codigos.discard(None)
        self._garantir_juncoes(codigos, geometrias)

        tipo_id = self._tipo_id(camada)
        pendentes: list[tuple] = []
        for _, linha in df.iterrows():
            cod = _texto(linha.get("COD_ID"))
            pn1, pn2 = _texto(linha.get("PN_CON_1")), _texto(linha.get("PN_CON_2"))
            no1 = self.juncoes.get(pn1) if pn1 else None
            no2 = self.juncoes.get(pn2) if pn2 else None
            if no1 is None or no2 is None:
                self._desvio(
                    "trecho_sem_ponto_conexao",
                    "trecho com PN_CON_1/PN_CON_2 vazio ou sem junção correspondente: sem as duas "
                    "pontas nomeadas não há conectividade explícita, e inventar ponta por geometria "
                    "é a inferência que este modelo evita de propósito",
                    cod,
                )
                continue
            if camada == "RAMLIG":
                wkb = None
            else:
                wkb, multiparte = _wkb_linha(linha.geometry)
                if wkb is None:
                    self._desvio("trecho_sem_geometria", "trecho com geometria vazia ou não linear", cod)
                    continue
                if multiparte:
                    self._desvio(
                        "trecho_multiparte",
                        "trecho com mais de uma parte: entrou a primeira; as demais ficam no arquivo",
                        cod,
                    )
            if camada == "SSDMT":
                subrede = self.subredes.get((2, _texto(linha.get("CTMT")) or ""))
            else:
                subrede = self.subredes.get((3, _texto(linha.get("UNI_TR_MT")) or "")) or self.subredes.get(
                    (2, _texto(linha.get("CTMT")) or "")
                )
            pendentes.append((
                self.tenant_id, self.rede_id, tipo_id, cod, no1[0], no2[0], wkb, wkb,
                _texto(linha.get("FAS_CON")), subrede, Json(_atributos(linha)),
            ))
            if len(pendentes) >= LOTE:
                self._gravar_arestas(pendentes)
                pendentes.clear()
        if pendentes:
            self._gravar_arestas(pendentes)
        self.cur.execute(
            "SELECT count(*) AS n FROM plat.rede_aresta WHERE rede_id = %s::uuid AND tipo_id = %s::uuid",
            (self.rede_id, tipo_id),
        )
        total = int(self.cur.fetchone()["n"])
        duplicados = (self.inseridos.get(camada, 0) + len(df) - self._falhas[camada]) - total \
            if hasattr(self, "_falhas") else 0
        self.inseridos[camada] = total

    def _gravar_arestas(self, tuplas: list[tuple]) -> None:
        # no_origem_seq/no_destino_seq entram como 0: o gatilho rede_aresta_validar copia os seqs
        # reais dos nós (o DDL proíbe a aplicação de preenchê-los à mão). ST_GeomFromWKB(NULL) é
        # NULL (função STRICT), então o ramal sem geometria entra com geom e comprimento NULL.
        execute_values(
            self.cur,
            "INSERT INTO plat.rede_aresta (tenant_id, rede_id, tipo_id, codigo_externo, no_origem_id, "
            "no_destino_id, no_origem_seq, no_destino_seq, geom, comprimento_m, fase, subrede_id, atributos) "
            "VALUES %s ON CONFLICT (rede_id, codigo_externo) DO NOTHING",
            tuplas,
            template="(%s, %s::uuid, %s::uuid, %s, %s::uuid, %s::uuid, 0, 0, "
                     "ST_Transform(ST_SetSRID(ST_GeomFromWKB(%s), " + str(SRID_FONTE) + "), 4326), "
                     "ST_Length(ST_Transform(ST_SetSRID(ST_GeomFromWKB(%s), " + str(SRID_FONTE) + "), 4326)::geography), "
                     "%s, %s::uuid, %s)",
            page_size=LOTE,
        )

    def _dispositivos(self, camada: str, geometrias: dict[str, bytes]) -> None:
        df = _ler(self.caminho, camada)
        if df.empty:
            self.inseridos[camada] = 0
            return
        self._garantir_juncoes({_texto(v) for v in df["PAC_1"]} - {None}, geometrias)
        tipo_id = self._tipo_id(camada)
        pendentes: list[tuple] = []
        for _, linha in df.iterrows():
            cod = _texto(linha.get("COD_ID"))
            pac = _texto(linha.get("PAC_1"))
            no = self.juncoes.get(pac) if pac else None
            if no is None:
                self._desvio(
                    "dispositivo_sem_ponto_conexao",
                    "dispositivo com PAC_1 vazio ou sem junção correspondente",
                    cod,
                )
                continue
            estado = "na"
            if camada == "UNSEMT":
                estado = "aberto" if _texto(linha.get("P_N_OPE")) == "A" else "fechado"
            subrede = self.subredes.get((2, _texto(linha.get("CTMT")) or ""))
            pendentes.append((
                self.tenant_id, self.rede_id, tipo_id, cod, estado, subrede,
                _wkb_ponto(linha.geometry), Json(_atributos(linha)), cod, no[0],
            ))
            if len(pendentes) >= LOTE:
                self._gravar_dispositivos(pendentes, camada)
                pendentes.clear()
        if pendentes:
            self._gravar_dispositivos(pendentes, camada)
        self.cur.execute(
            "SELECT count(*) AS n FROM plat.rede_no WHERE rede_id = %s::uuid AND papel = 'dispositivo' "
            "AND tipo_id = %s::uuid",
            (self.rede_id, tipo_id),
        )
        self.inseridos[camada] = int(self.cur.fetchone()["n"])

    def _gravar_dispositivos(self, tuplas: list[tuple], camada: str) -> None:
        """Nós de dispositivo em lote; depois subrede de nível 3 (só trafo) e a associação com a
        junção, já filtrada pela mesma régua do gatilho (aresta incidente com regra)."""
        inseridos = execute_values(
            self.cur,
            "INSERT INTO plat.rede_no (tenant_id, rede_id, papel, tipo_id, codigo_externo, estado, "
            "subrede_id, geom, atributos) VALUES %s "
            "ON CONFLICT (rede_id, papel, codigo_externo) DO NOTHING RETURNING id, codigo_externo",
            tuplas,
            template="(%s, %s::uuid, 'dispositivo', %s::uuid, %s, %s, %s::uuid, "
                     "ST_Transform(ST_SetSRID(ST_GeomFromWKB(%s), " + str(SRID_FONTE) + "), 4326), %s)",
            page_size=LOTE,
            fetch=True,
        )
        por_codigo = {r["codigo_externo"]: r["id"] for r in inseridos}
        for t in tuplas:
            cod = t[3]
            if cod not in por_codigo:
                self._desvio("dispositivo_duplicado", "COD_ID de dispositivo repetido no arquivo", cod)
                continue
            no_id = por_codigo[cod]
            if camada == "UNTRMT":
                self.cur.execute(
                    "INSERT INTO plat.rede_subrede (tenant_id, rede_id, nivel, codigo_externo, "
                    "controlador_no_id, pai_id) VALUES (%s, %s::uuid, 3, %s, %s::uuid, %s::uuid) "
                    "ON CONFLICT (rede_id, nivel, codigo_externo) DO NOTHING RETURNING id",
                    (self.tenant_id, self.rede_id, cod, no_id, t[5]),
                )
                r3 = self.cur.fetchone()
                if r3:
                    self.subredes[(3, cod)] = r3["id"]
            self.cur.execute(
                "INSERT INTO plat.rede_associacao (tenant_id, rede_id, tipo, de_no_id, para_no_id, origem) "
                "SELECT %s, %s::uuid, 'conectividade', %s::uuid, %s::uuid, 'importacao' "
                "WHERE EXISTS ("
                "  SELECT 1 FROM plat.rede_aresta a JOIN plat.rede_regra r "
                "    ON r.rede_id = %s::uuid AND r.tipo = 'conectividade_no_trecho' "
                "   AND ((r.de_tipo_id = a.tipo_id AND r.para_tipo_id = %s::uuid) "
                "     OR (r.de_tipo_id = %s::uuid AND r.para_tipo_id = a.tipo_id)) "
                "   WHERE a.rede_id = %s::uuid AND (a.no_origem_id = %s::uuid OR a.no_destino_id = %s::uuid)"
                ") RETURNING de_no_id",
                (self.tenant_id, self.rede_id, no_id, t[9], self.rede_id, t[2], t[2], self.rede_id, t[9], t[9]),
            )
            if self.cur.fetchone() is None:
                self._desvio(
                    "dispositivo_sem_regra_na_juncao",
                    "nenhuma aresta incidente na junção do dispositivo tem regra de conectividade "
                    "com o tipo dele no catálogo (o gatilho recusaria; o desvio explica a ausência)",
                    cod,
                )

    def _consumidores(self, camada: str) -> None:
        try:
            df = _ler(self.caminho, camada, geometria=False)
        except ErroBdgd:
            self.inseridos[camada] = 0
            return
        if df.empty:
            self.inseridos[camada] = 0
            return
        # UCBT_tab/UCMT_tab não têm COD_ID nem geometria: o identificador é o OBJECTID da tabela
        # (índice do dataframe, fid_as_index=True) e o ponto de ligação é o PN_CON.
        pns = {_texto(v) for v in df["PN_CON"]} - {None}
        self._garantir_juncoes_uc(pns)
        tipo_id = self._tipo_id(camada)
        pendentes: list[tuple] = []
        for idx, linha in df.iterrows():
            cod = f"{camada}:{idx}"
            pn = _texto(linha.get("PN_CON"))
            no = self.juncoes.get(pn) if pn else None
            if no is None:
                self._desvio(
                    "consumidor_sem_ponto_conexao",
                    "unidade consumidora com PN_CON vazio ou sem junção correspondente",
                    cod,
                )
                continue
            subrede = self.subredes.get((3, _texto(linha.get("UNI_TR_MT")) or ""))
            pendentes.append((
                self.tenant_id, self.rede_id, tipo_id, cod, subrede, Json(_atributos(linha)), no[0],
            ))
            if len(pendentes) >= LOTE:
                self._gravar_consumidores(pendentes)
                pendentes.clear()
        if pendentes:
            self._gravar_consumidores(pendentes)
        self.cur.execute(
            "SELECT count(*) AS n FROM plat.rede_no WHERE rede_id = %s::uuid AND papel = 'consumidor' "
            "AND tipo_id = %s::uuid",
            (self.rede_id, tipo_id),
        )
        self.inseridos[camada] = int(self.cur.fetchone()["n"])

    def _garantir_juncoes_uc(self, pns: set[str]) -> None:
        """Junções que só aparecem em PN_CON de consumidor (ponta de ramal) — sem geometria, porque
        a geometria delas viria do PONNOT e o chamador já aplica esse mapa nas fases de trecho."""
        novas = sorted(p for p in pns if p and p not in self.juncoes)
        for i in range(0, len(novas), LOTE):
            fatia = novas[i : i + LOTE]
            execute_values(
                self.cur,
                "INSERT INTO plat.rede_no (tenant_id, rede_id, papel, codigo_externo) VALUES %s "
                "ON CONFLICT (rede_id, papel, codigo_externo) DO NOTHING",
                [(self.tenant_id, self.rede_id, "juncao", c) for c in fatia],
                page_size=LOTE,
            )
            self.cur.execute(
                "SELECT id, seq, codigo_externo FROM plat.rede_no "
                "WHERE rede_id = %s::uuid AND papel = 'juncao' AND codigo_externo = ANY(%s)",
                (self.rede_id, fatia),
            )
            for r in self.cur.fetchall():
                self.juncoes[r["codigo_externo"]] = (r["id"], int(r["seq"]))

    def _gravar_consumidores(self, tuplas: list[tuple]) -> None:
        inseridos = execute_values(
            self.cur,
            "INSERT INTO plat.rede_no (tenant_id, rede_id, papel, tipo_id, codigo_externo, subrede_id, atributos) "
            "VALUES %s ON CONFLICT (rede_id, papel, codigo_externo) DO NOTHING RETURNING id, codigo_externo",
            tuplas,
            template="(%s, %s::uuid, 'consumidor', %s::uuid, %s, %s::uuid, %s)",
            page_size=LOTE,
            fetch=True,
        )
        id_por_codigo = {r["codigo_externo"]: r["id"] for r in inseridos}
        associacoes = [
            (self.tenant_id, self.rede_id, id_por_codigo[t[3]], t[6])
            for t in tuplas if t[3] in id_por_codigo
        ]
        if not associacoes:
            return
        gravadas = execute_values(
            self.cur,
            "INSERT INTO plat.rede_associacao (tenant_id, rede_id, tipo, de_no_id, para_no_id, origem) "
            "SELECT v.tenant_id, v.rede_id::uuid, 'conectividade', v.de_no::uuid, v.para_no::uuid, 'importacao' "
            "FROM (VALUES %s) AS v(tenant_id, rede_id, de_no, para_no) "
            "WHERE EXISTS ("
            "  SELECT 1 FROM plat.rede_aresta a JOIN plat.rede_regra r "
            "    ON r.rede_id = v.rede_id::uuid AND r.tipo = 'conectividade_no_trecho' "
            "   AND ((r.de_tipo_id = a.tipo_id AND r.para_tipo_id = n.tipo_id) "
            "     OR (r.de_tipo_id = n.tipo_id AND r.para_tipo_id = a.tipo_id)) "
            "   JOIN plat.rede_no n ON n.tenant_id = v.tenant_id AND n.id = v.de_no::uuid "
            "   WHERE a.rede_id = v.rede_id::uuid AND (a.no_origem_id = v.para_no::uuid OR a.no_destino_id = v.para_no::uuid)"
            ") RETURNING de_no_id",
            associacoes,
            page_size=LOTE,
            fetch=True,
        )
        ok = {r["de_no_id"] for r in gravadas}
        for _, _, de_no, _ in associacoes:
            if de_no not in ok:
                self._desvio(
                    "consumidor_sem_regra_na_juncao",
                    "nenhuma aresta incidente na junção do consumidor tem regra de conectividade "
                    "com o tipo dele no catálogo — na BDGD o consumidor de baixa liga pelo ramal, "
                    "e junção sem ramal incidente não tem como validar a regra",
                    None,
                )
