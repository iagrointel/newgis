"""Resposta de formulário -> feição na camada de destino (+ N feições nas camadas filhas das repetições + anexos),
pela única porta de escrita `app.edicao.servico.aplicar_edicoes` (C5). Item L2-07-b."""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from fastapi import Request

from app import limites
from app.auth.sessao import Auth
from app.coleta import motor
from app.coleta.documento import COLUNAS_AUTOMATICAS, folhas, nos
from app.edicao import anexos
from app.edicao.modelos import EdicoesEntrada, FeicaoAdicionar
from app.edicao.servico import aplicar_edicoes
from app.erros import ErroAPI

_NUM = r"(-?\d+(?:\.\d+)?)"
_RE_GEOPONTO = re.compile(rf"^\s*{_NUM}\s+{_NUM}(?:\s+{_NUM})?(?:\s+{_NUM})?\s*$")


def valor_para_coluna(campo: dict, valor: Any) -> Any:
    """Valor da resposta -> valor aceito pelo tipo da coluna (`documento.TIPO_PG`)."""
    if valor is None or valor == "":
        return None
    tipo = campo.get("tipo")
    if tipo == "select_multiple" and isinstance(valor, list):
        return " ".join(str(v) for v in valor)
    if tipo == "inteiro":
        return int(valor) if not isinstance(valor, bool) else None
    if tipo == "decimal":
        return float(valor)
    if tipo in ("calculo", "texto", "oculto", "fora", "select_one"):
        if isinstance(valor, float) and valor.is_integer():
            valor = int(valor)
        return str(valor) if not isinstance(valor, (list, dict)) else None
    return valor


def geometria_de(valor: Any) -> dict | None:
    """geopoint do XLSForm: "lat lon [alt [precisão]]" -> GeoJSON Point (lon, lat)."""
    if not isinstance(valor, str):
        return None
    m = _RE_GEOPONTO.match(valor)
    if not m:
        raise ErroAPI(422, "geoponto_invalido", "geoponto tem de ser 'latitude longitude [altitude [precisão]]'")
    lat, lon = float(m.group(1)), float(m.group(2))
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ErroAPI(422, "geoponto_invalido", "latitude/longitude fora da faixa")
    return {"type": "Point", "coordinates": [lon, lat]}


def _atributos(campos: list[dict], valores: dict, res: motor.Resultado) -> tuple[dict, dict | None]:
    atributos: dict[str, Any] = {}
    geometria = None
    for c, rep in folhas(campos):
        if rep is not None or c["nome"] not in res.relevantes:
            continue  # campo de repetição vai na camada filha, nunca na feição pai
        v = valores.get(c["nome"])
        if c["tipo"] == "geoponto":
            geometria = geometria_de(v)
            continue
        if c.get("campo_destino"):
            atributos[c["campo_destino"]] = valor_para_coluna(c, v)
    return atributos, geometria


def _agora() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def responder(cur, request: Request, auth: Auth, formulario: dict, resposta: dict) -> dict:
    """`resposta`: {valores, repeticoes, inicio, fim, dispositivo, anexos: [{campo, nome, content_type, conteudo}]}."""
    doc = formulario["dados"] or {}
    camada = doc.get("camada_destino")
    if not camada:
        raise ErroAPI(409, "formulario_sem_camada", "formulário sem camada de destino")
    reps = resposta.get("repeticoes") or {}
    for nome, linhas in reps.items():
        if len(linhas) > limites.FORMULARIO_REPETICOES_MAX:
            raise ErroAPI(422, "repeticao_grande", f"repetição {nome} acima de {limites.FORMULARIO_REPETICOES_MAX}")
    res = motor.avaliar_resposta(doc, resposta.get("valores") or {}, reps)
    if not res.ok:
        raise ErroAPI(422, "resposta_invalida", "a resposta viola regras do formulário", res.erros)
    atributos, geometria = _atributos(doc["campos"], res.valores, res)
    automaticos = {
        "coleta_inicio": resposta.get("inicio"), "coleta_fim": resposta.get("fim") or _agora(),
        "coleta_usuario": auth.login, "coleta_dispositivo": (resposta.get("dispositivo") or "")[:200] or None,
        "coleta_versao": doc.get("versao_formulario") or None,
    }
    colunas_auto = {n for n, _t in COLUNAS_AUTOMATICAS}
    atributos.update({k: v for k, v in automaticos.items() if k in colunas_auto})
    for c, _rep in folhas(doc["campos"]):
        if c.get("tipo") == "meta" and c.get("campo_destino") and c["nome"] in res.relevantes:
            atributos[c["campo_destino"]] = {
                "start": resposta.get("inicio"), "end": automaticos["coleta_fim"], "username": auth.login,
                "deviceid": automaticos["coleta_dispositivo"], "today": automaticos["coleta_fim"][:10],
            }.get(c.get("meta"), res.valores.get(c["nome"]))
    saida = aplicar_edicoes(cur, request, auth, camada, EdicoesEntrada(
        adicionar=[FeicaoAdicionar(atributos=atributos, geometria=geometria)]))
    pai = saida.adicionar[0]
    if not pai.sucesso:
        raise ErroAPI(422, pai.erro or "feicao_recusada", pai.mensagem or "feição recusada", pai.detalhe)
    gravadas: dict[str, int] = {}
    for no in nos(doc["campos"]):
        if no.get("tipo") != "repeticao" or no["nome"] not in res.relevantes:
            continue
        filha = (doc.get("camadas_filhas") or {}).get(no["nome"])
        linhas = res.repeticoes.get(no["nome"]) or []
        if not linhas:
            gravadas[no["nome"]] = 0
            continue
        if not filha:
            raise ErroAPI(409, "repeticao_sem_camada", f"repetição {no['nome']} sem camada filha")
        adicionar = []
        for i, linha in enumerate(linhas):
            atr, _g = _atributos(no.get("filhos") or [], linha, res)
            atr.update({"pai_globalid": pai.id, "indice": i})
            adicionar.append(FeicaoAdicionar(atributos=atr, geometria=None))
        s = aplicar_edicoes(cur, request, auth, filha, EdicoesEntrada(adicionar=adicionar))
        ruim = next((r for r in s.adicionar if not r.sucesso), None)
        if ruim is not None:
            raise ErroAPI(422, ruim.erro or "repeticao_recusada", ruim.mensagem or "linha de repetição recusada",
                          ruim.detalhe)
        gravadas[no["nome"]] = len(adicionar)
    enviados = 0
    for a in resposta.get("anexos") or []:
        anexos.enviar(cur, auth, request, camada, pai.id, a["nome"], a["content_type"], a["conteudo"])
        enviados += 1
    return {"feicao": {"id": pai.id, "fid": pai.fid, "versao": pai.versao}, "camada": camada,
            "repeticoes": gravadas, "anexos": enviados, "avisos": saida.avisos}
