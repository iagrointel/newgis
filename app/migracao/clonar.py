"""Motor de clonagem de camadas hospedadas e tabelas de um FeatureServer da Esri (item L2-08-b), retomável por
camada como o inventário (`app/migracao/inventario.py`).

Por camada pedida (ou todas as `layers` + `tables` do serviço): esquema (`app/migracao/esquema.py`) → tabela e
item `camada_vetorial` (`app/catalogo/camada_nova.py`, o mesmo preparo da ingestão) → domínios e subtipos
(`app/dominios/servico.importar_dominios`, a mesma função da rota) → dados paginados por `resultOffset` (ou por
`objectIds` quando o serviço não pagina), em lotes, geometria por `ST_GeomFromEWKT` → anexos por feição para o
armazém de objetos (L0-11, sha256) → relacionamentos entre as camadas clonadas (`app/relacionamentos/servico`)
→ verificação (contagem origem × destino; sha256 de uma amostra normalizada) → relatório por camada. Segunda
execução: camada cujo `editingInfo.lastEditDate` não mudou não é reescrita (`escritas = 0`).

O que NÃO faz nesta rodada (portão diz, handoff repete): caminho por exportação de File Geodatabase
(`createReplica`/`exportItem`) e vistas hospedadas como vistas do L0-04-j (a vista vira camada comum com o aviso)."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
from collections.abc import Callable
from typing import Any

import psycopg2.extras

from app import limites, objetos
from app.catalogo.camada_nova import criar_camada
from app.consulta.geometria_esri import para_ewkt
from app.dominios import servico as dominios
from app.migracao import esquema as esquema_mod
from app.migracao.portal import ClientePortal, ErroPortal
from app.relacionamentos import servico as relacionamentos
from app.relacionamentos.modelos import RelacionamentoEntrada

log = logging.getLogger("plat.migracao.clonar")
TIPO_ESRI_GEOM = {
    "esriGeometryPoint": "point",
    "esriGeometryMultipoint": "multipoint",
    "esriGeometryPolyline": "polyline",
    "esriGeometryPolygon": "polygon",
}


def _jsonb(v):
    return psycopg2.extras.Json(v, dumps=lambda x: json.dumps(x, ensure_ascii=False, default=str))


def hash_amostra(linhas: list[dict]) -> str:
    """sha256 de uma lista de {atributos (sem rastreio), wkb hex normalizado} em ordem de id de origem."""
    h = hashlib.sha256()
    for linha in linhas:
        h.update(json.dumps(linha, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8"))
        h.update(b"\\n")
    return h.hexdigest()


class Clonagem:
    def __init__(
        self,
        cliente: ClientePortal,
        bd: Callable,
        clone_id: str,
        tenant_id: int,
        usuario_id: int,
        *,
        registrar=None,
        verificar=None,
        progresso=None,
    ):
        self.cliente = cliente
        self.bd = bd
        self.clone_id = clone_id
        self.tenant_id = tenant_id
        self.usuario_id = usuario_id
        self._registrar = registrar or (lambda nivel, msg: log.log(logging.INFO, "%s", msg))
        self._verificar = verificar or (lambda: None)
        self._progresso = progresso or (lambda pct, msg="": None)
        self.escritas = 0

    # ------------------------------------------------------------------ estado
    def _ler(self) -> dict:
        with self.bd() as cur:
            cur.execute(
                "SELECT url_servico, camadas_pedidas, retomada, camadas, relatorio FROM plat.migracao_clone "
                "WHERE id = %s::uuid",
                (self.clone_id,),
            )
            r = cur.fetchone()
        if r is None:
            raise ErroPortal("clone_inexistente", self.clone_id)
        return dict(r)

    def _gravar(self, retomada: dict, camadas: list[dict], relatorio: dict | None = None) -> None:
        with self.bd() as cur:
            cur.execute(
                "UPDATE plat.migracao_clone SET retomada = %s, camadas = %s, relatorio = coalesce(%s, relatorio) "
                "WHERE id = %s::uuid",
                (_jsonb(retomada), _jsonb(camadas), _jsonb(relatorio) if relatorio else None, self.clone_id),
            )

    # ------------------------------------------------------------------ passos
    def _criar_camada(self, esq: dict, url: str) -> tuple[str, dict]:
        colunas = [
            {
                "nome": c["nome"],
                "tipo": c["tipo"],
                "alias": c["alias"],
                "tamanho": c["tamanho"],
                "nulavel": True,
                "padrao": c["padrao"],
            }
            for c in esq["campos"]
        ]
        if esq["campo_globalid"]:
            colunas.append({"nome": "globalid_origem", "tipo": "uuid", "alias": "GlobalID de origem"})
        colunas.append({"nome": "oid_origem", "tipo": "bigint", "alias": "OBJECTID de origem"})
        extra = {
            "clonagem": {
                "url": url,
                "camada": esq["id_origem"],
                "clone_id": self.clone_id,
                "edit_date": esq["edit_date"],
                "mapa_nomes": esq["mapa_nomes"],
                "e_vista": esq["e_vista"],
            }
        }
        if esq["e_tabela"]:
            extra["geometria"] = "nenhuma"
        with self.bd() as cur:
            item_id, dados = criar_camada(
                cur,
                self.usuario_id,
                esq["nome"][:250],
                colunas,
                geometria=esq["geometria"] or "Point",
                srid=esq["srid"],
                extra_dados=extra,
            )
            cur.execute(
                "SELECT plat.evento_registrar('camadas/importar', 'item', %s, %s::jsonb, NULL, NULL)",
                (item_id, json.dumps({"formato": "clonagem_esri", "clone_id": self.clone_id})),
            )
        return item_id, dados

    def _dominios(self, esq: dict, item_id: str) -> dict:
        d = esq["dominios"]
        if not d["fields"] and not d["types"]:
            return {"criados": 0, "reaproveitados": 0, "ligados": 0, "subtipos": 0, "ignorados": []}
        with self.bd() as cur:
            item = dominios.camada_ou_404(cur, item_id)
            s = dominios.importar_dominios(cur, self.usuario_id, d["fields"], d["types"], item, None)
        return {
            "criados": len(s["criados"]),
            "reaproveitados": len(s["reaproveitados"]),
            "ligados": len(s["ligados"]),
            "subtipos": len((s.get("subtipos") or {}).get("valores") or []),
            "ignorados": s["ignorados"],
        }

    def _inserir_lote(self, dados: dict, esq: dict, feicoes: list[dict], wkid: int) -> int:
        if not feicoes:
            return 0
        campos = esq["campos"]
        colunas = [c["nome"] for c in campos] + ["oid_origem"] + (["globalid_origem"] if esq["campo_globalid"] else [])
        tipo_geom = TIPO_ESRI_GEOM.get(esq["tipo_esri"] or "")
        linhas = []
        for f in feicoes:
            atr = f.get("attributes") or {}
            valores = [esquema_mod.valor_para_coluna(c, atr.get(c["original"])) for c in campos]
            valores.append(atr.get(esq["campo_oid"]))
            if esq["campo_globalid"]:
                g = atr.get(esq["campo_globalid"])
                valores.append(str(g).strip("{}").lower() if g else None)
            geom = f.get("geometry")
            ewkt = None
            if tipo_geom and geom and not esq["e_tabela"] and _geometria_valida(geom):
                try:
                    ewkt = para_ewkt(geom, tipo_geom, wkid)
                except Exception as e:  # noqa: BLE001 — geometria inválida vira NULL com aviso, nunca aborta o lote
                    self._registrar("aviso", f"geometria descartada (oid {atr.get(esq['campo_oid'])}): {str(e)[:120]}")
            linhas.append(tuple(valores) + (ewkt,))
        sql_cols = ", ".join(f'"{c}"' for c in colunas) + ", geom"
        modelo = (
            "(" + ", ".join(["%s"] * len(colunas)) + ", ST_Multi(ST_MakeValid(ST_GeomFromEWKT(%s))))"
            if esq["geometria"] and esq["geometria"].startswith("Multi")
            else "(" + ", ".join(["%s"] * len(colunas)) + ", ST_MakeValid(ST_GeomFromEWKT(%s)))"
        )
        if esq["srid"] != wkid:
            modelo = modelo.replace("ST_GeomFromEWKT(%s)", f"ST_Transform(ST_GeomFromEWKT(%s), {int(esq['srid'])})")
        with self.bd() as cur:
            psycopg2.extras.execute_values(
                cur,
                f'INSERT INTO "{dados["schema"]}"."{dados["tabela"]}" ({sql_cols}) VALUES %s',
                linhas,
                template=modelo,
                page_size=limites.CLONE_PAGINA,
            )
        self.escritas += len(linhas)
        return len(linhas)

    def _dados(self, url: str, esq: dict, dados: dict, retomada: dict) -> int:
        deslocamento = int(retomada.get("deslocamento") or 0)
        total = 0
        modo = retomada.get("modo") or "offset"
        wkid = esq["srid"]
        while True:
            self._verificar()
            if modo == "offset":
                pagina = self.cliente.feicoes(
                    url, esq["id_origem"], deslocamento, limites.CLONE_PAGINA, esq["campo_oid"], wkid
                )
                feicoes = pagina.get("features") or []
                if deslocamento == 0 and not feicoes and pagina.get("error"):
                    modo = "ids"
                    continue
            else:
                ids = retomada.get("ids")
                if ids is None:
                    ids = self.cliente.ids_camada(url, esq["id_origem"])
                    retomada["ids"] = ids
                fatia = ids[deslocamento : deslocamento + limites.CLONE_PAGINA]
                feicoes = (
                    (self.cliente.feicoes_por_ids(url, esq["id_origem"], fatia, wkid).get("features") or [])
                    if fatia
                    else []
                )
                pagina = {"exceededTransferLimit": deslocamento + len(fatia) < len(ids)}
            sr = pagina.get("spatialReference") or {}
            wkid_pagina = sr.get("latestWkid") or sr.get("wkid") or wkid
            n = self._inserir_lote(dados, esq, feicoes, int(3857 if wkid_pagina == 102100 else wkid_pagina))
            total += n
            deslocamento += len(feicoes)
            retomada.update({"fase": "dados", "deslocamento": deslocamento, "modo": modo})
            self._salvar_retomada_camada(esq["id_origem"], retomada)
            if not feicoes or not pagina.get("exceededTransferLimit"):
                break
        return total

    def _anexos(self, url: str, esq: dict, dados: dict, item_id: str) -> dict:
        if not esq["tem_anexos"]:
            return {"feicoes_com_anexo": 0, "anexos": 0, "bytes": 0, "sha256": []}
        saida = {"feicoes_com_anexo": 0, "anexos": 0, "bytes": 0, "sha256": []}
        with self.bd() as cur:
            cur.execute(f'SELECT fid, globalid, oid_origem FROM "{dados["schema"]}"."{dados["tabela"]}" ORDER BY fid')
            linhas = cur.fetchall()
        for linha in linhas:
            self._verificar()
            try:
                infos = self.cliente.anexos_de(url, esq["id_origem"], int(linha["oid_origem"]))
            except ErroPortal as e:
                self._registrar("aviso", f"anexos da feição {linha['oid_origem']} não lidos: {e.motivo}")
                continue
            if not infos:
                continue
            saida["feicoes_com_anexo"] += 1
            for a in infos:
                try:
                    conteudo, tipo = self.cliente.anexo_bytes(
                        url, esq["id_origem"], int(linha["oid_origem"]), int(a["id"]), limites.CLONE_ANEXO_MAX
                    )
                except ErroPortal as e:
                    self._registrar(
                        "aviso", f"anexo {a.get('id')} da feição {linha['oid_origem']} não lido: {e.motivo}"
                    )
                    continue
                with self.bd() as cur:
                    obj = objetos.guardar(
                        cur,
                        "feicao_anexo",
                        conteudo,
                        a.get("contentType") or tipo,
                        item_id=str(linha["globalid"]),
                        usuario_id=self.usuario_id,
                    )
                    cur.execute("SELECT to_regclass('plat.feicao_anexo') AS t")
                    if cur.fetchone()["t"] is not None:  # tabela de vínculo do L2-03-e, quando presente
                        cur.execute(
                            "INSERT INTO plat.feicao_anexo (tenant_id, schema_dado, tabela_dado, globalid, nome, "
                            "content_type, bytes, sha256, chave, criado_por) "
                            "VALUES (plat.tenant_atual(), %s, %s, %s::uuid, "
                            "%s, %s, %s, %s, %s, %s)",
                            (
                                dados["schema"],
                                dados["tabela"],
                                str(linha["globalid"]),
                                (a.get("name") or "anexo")[-255:],
                                a.get("contentType") or tipo,
                                obj["bytes"],
                                obj["sha256"],
                                obj["chave"],
                                self.usuario_id,
                            ),
                        )
                saida["anexos"] += 1
                saida["bytes"] += obj["bytes"]
                if len(saida["sha256"]) < 20:
                    saida["sha256"].append(
                        {"oid_origem": int(linha["oid_origem"]), "anexo": a.get("id"), "sha256": obj["sha256"]}
                    )
        return saida

    def _relacionamentos(self, esquemas: dict[int, dict], itens: dict[int, str]) -> list[dict]:
        saida = []
        vistos: set[tuple[int, int]] = set()
        for origem_id, esq in esquemas.items():
            for r in esq["relacionamentos"]:
                if r["papel"] != "origem" or r["camada_relacionada"] not in itens:
                    continue
                destino_id = int(r["camada_relacionada"])
                chave_par = (origem_id, destino_id)
                if chave_par in vistos:
                    continue
                vistos.add(chave_par)
                esq_dest = esquemas.get(destino_id) or {}
                rel_dest = next(
                    (x for x in esq_dest.get("relacionamentos") or [] if x["camada_relacionada"] == origem_id), {}
                )
                entrada = RelacionamentoEntrada(
                    origem_item_id=itens[origem_id],
                    destino_item_id=itens[destino_id],
                    cardinalidade=r["cardinalidade"] if r["cardinalidade"] != "N:M" else "N:M",
                    chave_origem=r["chave"] or "globalid",
                    chave_destino=rel_dest.get("chave") or r["chave"] or "globalid",
                    composto=bool(r["composto"]) and r["cardinalidade"] != "N:M",
                    nome_direto=(r["nome"] or f"rel_{origem_id}_{destino_id}")[:120],
                    nome_inverso=(rel_dest.get("nome") or f"rel_{destino_id}_{origem_id}")[:120],
                )
                try:
                    with self.bd() as cur:
                        criado = relacionamentos.criar(cur, entrada, self.usuario_id)
                    saida.append(
                        {
                            "id": str(criado["id"]),
                            "origem": origem_id,
                            "destino": destino_id,
                            "cardinalidade": entrada.cardinalidade,
                            "nome": entrada.nome_direto,
                        }
                    )
                    continue
                except Exception as e:  # noqa: BLE001 — chave de origem repetida no dado: sem FK possível
                    motivo = str(getattr(e, "detail", e))[:200]
                # a Esri não exige chave de origem única no dado gravado; sem unicidade não há chave estrangeira, e a
                # relação é reproduzida como N:M pela tabela de junção (mesmo dado em queryRelatedRecords)
                try:
                    junc = entrada.model_copy(update={"cardinalidade": "N:M", "composto": False})
                    with self.bd() as cur:
                        criado = relacionamentos.criar(cur, junc, self.usuario_id)
                        to, tab_o = relacionamentos._tabela_de(cur, itens[origem_id])  # noqa: SLF001
                        td, tab_d = relacionamentos._tabela_de(cur, itens[destino_id])  # noqa: SLF001
                        cur.execute(
                            f"INSERT INTO plat.relacionamento_junc "
                            f"(rel_id, tenant_id, origem_valor, destino_valor, criado_por) "
                            f'SELECT DISTINCT %s::uuid, plat.tenant_atual(), o."{junc.chave_origem}"::text, '
                            f'd."{junc.chave_destino}"::text, %s FROM "{to}"."{tab_o}" o JOIN "{td}"."{tab_d}" d '
                            f'ON o."{junc.chave_origem}"::text = d."{junc.chave_destino}"::text '
                            f"ON CONFLICT DO NOTHING",
                            (str(criado["id"]), self.usuario_id),
                        )
                        pares = cur.rowcount
                    saida.append(
                        {
                            "id": str(criado["id"]),
                            "origem": origem_id,
                            "destino": destino_id,
                            "cardinalidade": "N:M",
                            "nome": junc.nome_direto,
                            "pares": pares,
                            "aviso": f"chave de origem não única no dado ({motivo}); reproduzido como N:M por junção",
                        }
                    )
                except Exception as e:  # noqa: BLE001 — relacionamento não reproduzível vira aviso no relatório
                    saida.append(
                        {"origem": origem_id, "destino": destino_id, "erro": str(getattr(e, "detail", e))[:200]}
                    )
        return saida

    def _verificacao(self, url: str, esq: dict, dados: dict) -> dict:
        contagem_origem = self.cliente.contagem_camada(url, esq["id_origem"])
        with self.bd() as cur:
            cur.execute(f'SELECT count(*) AS n FROM "{dados["schema"]}"."{dados["tabela"]}"')
            contagem_destino = int(cur.fetchone()["n"])
            cur.execute(
                f"SELECT oid_origem, ST_AsBinary(ST_Normalize(geom)) AS wkb, to_jsonb(t) - 'geom' AS atr "
                f'FROM "{dados["schema"]}"."{dados["tabela"]}" t ORDER BY oid_origem LIMIT %s',
                (limites.CLONE_AMOSTRA,),
            )
            amostra_destino = []
            oids = []
            for r in cur.fetchall():
                atr = {c["nome"]: r["atr"].get(c["nome"]) for c in esq["campos"]}
                amostra_destino.append(
                    {
                        "oid": r["oid_origem"],
                        "atributos": atr,
                        "wkb": bytes(r["wkb"]).hex() if r["wkb"] is not None else None,
                    }
                )
                oids.append(int(r["oid_origem"]))
        igual = None
        if oids:
            try:
                origem = self.cliente.feicoes_por_ids(url, esq["id_origem"], oids, esq["srid"]).get("features") or []
                por_oid = {int((f.get("attributes") or {}).get(esq["campo_oid"])): f for f in origem}
                amostra_origem = []
                with self.bd() as cur:
                    for oid in oids:
                        f = por_oid.get(oid) or {}
                        atr = {
                            c["nome"]: esquema_mod.valor_para_coluna(c, (f.get("attributes") or {}).get(c["original"]))
                            for c in esq["campos"]
                        }
                        wkb = None
                        g = f.get("geometry")
                        tipo_geom = TIPO_ESRI_GEOM.get(esq["tipo_esri"] or "")
                        if tipo_geom and g and not esq["e_tabela"] and _geometria_valida(g):
                            cur.execute(
                                "SELECT ST_AsBinary(ST_Normalize(ST_MakeValid(ST_GeomFromEWKT(%s)))) AS wkb",
                                (para_ewkt(g, tipo_geom, esq["srid"]),),
                            )
                            wkb = bytes(cur.fetchone()["wkb"]).hex()
                            if esq["geometria"] and esq["geometria"].startswith("Multi"):
                                cur.execute(
                                    "SELECT ST_AsBinary(ST_Normalize(ST_Multi(ST_MakeValid("
                                    "ST_GeomFromEWKT(%s))))) AS wkb",
                                    (para_ewkt(g, tipo_geom, esq["srid"]),),
                                )
                                wkb = bytes(cur.fetchone()["wkb"]).hex()
                        amostra_origem.append({"oid": oid, "atributos": _normalizar(atr), "wkb": wkb})
                igual = hash_amostra(amostra_origem) == hash_amostra(
                    [{**a, "atributos": _normalizar(a["atributos"])} for a in amostra_destino]
                )
            except ErroPortal as e:
                self._registrar("aviso", f"amostra da origem não lida: {e.motivo}")
        return {
            "contagem_origem": contagem_origem,
            "contagem_destino": contagem_destino,
            "contagem_igual": contagem_origem == contagem_destino,
            "amostra": len(oids),
            "hash_amostra_igual": igual,
        }

    def _salvar_retomada_camada(self, id_origem: int, retomada_camada: dict) -> None:
        estado = self._ler()
        ret = estado["retomada"] or {}
        ret[str(id_origem)] = retomada_camada
        self._gravar(ret, estado["camadas"] or [])

    # ------------------------------------------------------------------ execução
    def executar(self) -> dict:
        estado = self._ler()
        url = estado["url_servico"].rstrip("/")
        self._progresso(1, "lendo o serviço")
        raiz = self.cliente.servico(url)
        if raiz.get("error"):
            raise ErroPortal("servico_recusado", str(raiz["error"])[:200])
        ids = [int(c["id"]) for c in (raiz.get("layers") or []) + (raiz.get("tables") or [])]
        if estado["camadas_pedidas"]:
            ids = [i for i in ids if i in set(estado["camadas_pedidas"])]
        if len(ids) > limites.CLONE_CAMADAS_MAX:
            raise ErroPortal("camadas_demais", f"{len(ids)} > {limites.CLONE_CAMADAS_MAX}")
        retomada = estado["retomada"] or {}
        relatorio_camadas = {int(c["origem_id"]): c for c in (estado["camadas"] or [])}
        esquemas: dict[int, dict] = {}
        itens: dict[int, str] = {}
        avisos: list[str] = []
        for n, cid in enumerate(ids):
            self._verificar()
            self._progresso(2 + int(85 * n / max(len(ids), 1)), f"camada {cid}")
            descritor = self.cliente.camada(url, cid)
            if descritor.get("error"):
                avisos.append(f"camada {cid}: {descritor['error']}")
                continue
            esq = esquema_mod.esquema_de(descritor)
            esquemas[cid] = esq
            ret = retomada.get(str(cid)) or {}
            anterior = relatorio_camadas.get(cid)
            # assinatura de mudança: lastEditDate quando o serviço publica; senão a contagem de feições da origem
            if esq["edit_date"] is not None:
                assinatura = f"edit:{esq['edit_date']}"
            else:
                assinatura = f"contagem:{self.cliente.contagem_camada(url, cid)}"
            if (
                anterior
                and anterior.get("item_id")
                and anterior.get("assinatura") == assinatura
                and ret.get("fase") == "concluido"
            ):
                itens[cid] = anterior["item_id"]
                anterior["escritas"] = 0
                anterior["reexecucao"] = "sem_mudanca"
                continue
            if ret.get("item_id"):
                item_id = ret["item_id"]
                with self.bd() as cur:
                    cur.execute("SELECT dados FROM plat.item WHERE id = %s::uuid", (item_id,))
                    dados = (cur.fetchone() or {}).get("dados")
                if dados is None:
                    ret = {}
            if not ret.get("item_id"):
                item_id, dados = self._criar_camada(esq, url)
                ret = {"fase": "tabela", "item_id": item_id, "deslocamento": 0}
                self._salvar_retomada_camada(cid, ret)
            itens[cid] = item_id
            resumo = {
                "origem_id": cid,
                "nome": esq["nome"],
                "item_id": item_id,
                "e_tabela": esq["e_tabela"],
                "geometria": esq["geometria"],
                "campos": len(esq["campos"]),
                "avisos": list(esq["avisos"]),
                "edit_date": esq["edit_date"],
                "assinatura": assinatura,
                "e_vista": esq["e_vista"],
            }
            if esq["e_vista"]:
                resumo["avisos"].append(
                    "vista hospedada clonada como camada comum (vista do L0-04-j ainda não em master)"
                )
            if ret.get("fase") == "tabela":
                ret["fase"] = "dados"
                self._salvar_retomada_camada(cid, ret)
            if ret.get("fase") == "dados":
                # dados ANTES dos domínios: o portal da Esri não valida o dado gravado contra o domínio, e uma cópia
                # fiel traz o valor fora do domínio como está; o gatilho de domínio (L2-10-a) só vale para edições novas
                resumo["feicoes"] = self._dados(url, esq, dados, ret)
                ret["fase"] = "dominios"
                self._salvar_retomada_camada(cid, ret)
            if ret.get("fase") == "dominios":
                resumo["dominios"] = self._dominios(esq, item_id)
                ret["fase"] = "anexos"
                self._salvar_retomada_camada(cid, ret)
            else:
                resumo["dominios"] = (anterior or {}).get("dominios") or {}
            if ret.get("fase") == "anexos":
                resumo["anexos"] = self._anexos(url, esq, dados, item_id)
                ret["fase"] = "verificacao"
                self._salvar_retomada_camada(cid, ret)
            resumo["verificacao"] = self._verificacao(url, esq, dados)
            resumo["escritas"] = self.escritas
            ret["fase"] = "concluido"
            self._salvar_retomada_camada(cid, ret)
            relatorio_camadas[cid] = resumo
            self._gravar(self._ler()["retomada"], list(relatorio_camadas.values()))
        self._progresso(90, "relacionamentos")
        rels = self._relacionamentos(esquemas, itens) if len(itens) > 1 else []
        relatorio = {
            "camadas": len(itens),
            "relacionamentos": rels,
            "escritas": self.escritas,
            "avisos": avisos,
            "terminado_em": dt.datetime.now(dt.UTC).isoformat(),
        }
        with self.bd() as cur:
            cur.execute(
                "UPDATE plat.migracao_clone SET estado = 'concluido', terminado_em = now(), relatorio = %s, "
                "camadas = %s WHERE id = %s::uuid",
                (_jsonb(relatorio), _jsonb(list(relatorio_camadas.values())), self.clone_id),
            )
        self._progresso(100, "concluído")
        return relatorio


def _normalizar(atr: dict) -> dict:
    saida = {}
    for k, v in atr.items():
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        if isinstance(v, str) and len(v) >= 19 and v[4] == "-" and v[10] in "T ":
            v = v[:19].replace(" ", "T")  # timestamps: mesma resolução dos dois lados (segundo)
        saida[k] = v
    return saida


def _geometria_valida(g: Any) -> bool:
    if not isinstance(g, dict):
        return False
    for chave in ("x", "y"):
        if chave in g and (g[chave] is None or (isinstance(g[chave], str) and g[chave].lower() == "nan")):
            return False
    return True
