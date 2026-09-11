"""Cliente ArcGIS REST API (item L2-08-migracao-agol), portado de
`/home/dev/fgr/sig/pipeline/20_agol_publish.py`: generateToken -> addItem (GeoJSON) -> publish (hosted feature
service); numa rodada seguinte, overwrite do mesmo item. Igual ao original nas chamadas e no formato dos
parâmetros publicados (targetSR 4326, maxRecordCount 5000, capabilities Query); diferente porque cada
requisição passa por `app.conexao.seguranca` (validação SSRF + cliente pinado no IP já validado) em vez de
`requests` direto — o portal é uma URL que o INQUILINO digitou (mesma classe de risco que uma `plat.conexao`,
mesma defesa). Nunca loga a credencial (token incluído): as funções recebem o token já pronto e não o
imprimem; `app/agol/tarefas.py` e `app/agol/rotas.py` são os únicos que decifram a credencial, em memória."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from app import limites
from app.conexao import seguranca

Progresso = None  # tipo livre: callable(pct:int, mensagem:str) -> None, ou None (uso síncrono/teste)


class ErroAGOL(Exception):
    """Falha de rede, de validação de URL (SSRF) ou resposta de erro do próprio ArcGIS REST API
    (`{"error": {...}}`). A mensagem já vem pronta para o usuário — nunca inclui a credencial."""


def _url(portal: str, caminho: str) -> str:
    return f"{portal.rstrip('/')}{caminho}"


def _pedido(metodo: str, url: str, *, dados: dict | None = None, arquivos: dict | None = None,
            timeout_conectar: float = limites.AGOL_CONECTAR_TIMEOUT_S,
            timeout_ler: float = limites.AGOL_LER_TIMEOUT_S) -> dict:
    """POST/GET pinado (mesma defesa SSRF de `app.conexao.seguranca`, adaptada para aceitar corpo
    multipart/form — `buscar_seguro` só cobre GET/HEAD sem corpo). Levanta `ErroAGOL` para toda falha; nunca
    devolve "meio válido"."""
    try:
        validada = seguranca.validar_url(url)
    except seguranca.ErroURLInsegura as e:
        raise ErroAGOL(f"URL do portal recusada ({e.motivo}): {url}") from e
    try:
        with seguranca.cliente_pinado(validada, timeout_conectar=timeout_conectar, timeout_ler=timeout_ler) as c:
            r = c.request(metodo, url, data=dados, files=arquivos)
    except httpx.TimeoutException as e:
        raise ErroAGOL(f"tempo esgotado falando com {validada.host}") from e
    except httpx.HTTPError as e:
        raise ErroAGOL(f"erro de conexão com {validada.host}: {type(e).__name__}") from e
    if r.status_code >= 400:
        raise ErroAGOL(f"http_{r.status_code} de {validada.host}")
    try:
        corpo = r.json()
    except ValueError as e:
        raise ErroAGOL(f"resposta não é JSON de {validada.host}") from e
    if isinstance(corpo, dict) and corpo.get("error"):
        erro = corpo["error"]
        msg = erro.get("message") if isinstance(erro, dict) else str(erro)
        detalhes = erro.get("details") if isinstance(erro, dict) else None
        if detalhes:
            msg = f"{msg} ({'; '.join(str(d) for d in detalhes)[:300]})"
        raise ErroAGOL(msg or "o ArcGIS Online recusou o pedido")
    return corpo


def gerar_token(portal: str, usuario: str, senha: str, minutos: int = 120) -> str:
    corpo = _pedido("POST", _url(portal, "/sharing/rest/generateToken"), dados=dict(
        username=usuario, password=senha, referer=portal, expiration=minutos, f="json",
    ))
    tok = corpo.get("token")
    if not tok:
        raise ErroAGOL("generateToken não devolveu token (usuário/senha da organização incorretos?)")
    return tok


def info_portal(portal: str, token: str) -> dict:
    """`portals/self`: nome da organização, usuário autenticado e créditos disponíveis — o mesmo que
    `20_agol_publish.py::self_info` usava para confirmar a credencial antes de publicar qualquer coisa."""
    corpo = _pedido("GET", _url(portal, "/sharing/rest/portals/self"), dados=dict(f="json", token=token))
    return dict(
        organizacao=corpo.get("name"),
        usuario=(corpo.get("user") or {}).get("username"),
        creditos_disponiveis=corpo.get("availableCredits"),
    )


@dataclass(frozen=True)
class ResultadoPublicacao:
    geojson_item_id: str
    servico_item_id: str
    servico_url: str | None
    n_feicoes: int


def publicar_camada(
    portal: str, token: str, usuario_agol: str, *, nome_servico: str, titulo: str, caminho_geojson: Path,
    n_feicoes: int, geojson_item_id_existente: str | None,
    dormir=time.sleep, progresso=None, tentativas_status: int = limites.AGOL_POLL_TENTATIVAS_MAX,
    intervalo_status_s: float = limites.AGOL_POLL_INTERVALO_S,
) -> ResultadoPublicacao:
    """addItem (ou update, se já existe um item AGOL desta camada) -> publish (overwrite quando já existe) ->
    espera o job assíncrono terminar. `dormir` é injetável (`ctx.dormir` dentro do job, cooperativo com
    cancelamento; `time.sleep` no teste síncrono) — mesma técnica de `app.jobs.contexto_job.ContextoJob`."""
    base = _url(portal, f"/sharing/rest/content/users/{usuario_agol}")
    if progresso:
        progresso(5, "enviando o GeoJSON ao ArcGIS Online")
    with open(caminho_geojson, "rb") as fh:
        arquivos = {"file": (f"{nome_servico}.geojson", fh, "application/vnd.geo+json")}
        if geojson_item_id_existente:
            corpo = _pedido("POST", f"{base}/items/{geojson_item_id_existente}/update", dados=dict(
                f="json", token=token, title=f"{titulo} (GeoJSON)",
            ), arquivos=arquivos, timeout_ler=limites.AGOL_PUBLICAR_TIMEOUT_S)
            item_id = geojson_item_id_existente
        else:
            corpo = _pedido("POST", f"{base}/addItem", dados=dict(
                f="json", token=token, type="GeoJson", title=f"{titulo} (GeoJSON)",
                tags="plat,iagrointel,dado aberto",
                description="Publicado pela plataforma iAgroIntel — análise / beta privado — cópia do "
                             "PostGIS do inquilino; a fonte de verdade continua no banco.",
            ), arquivos=arquivos, timeout_ler=limites.AGOL_PUBLICAR_TIMEOUT_S)
            item_id = corpo.get("id")
    if not item_id:
        raise ErroAGOL("addItem/update não devolveu o id do item no ArcGIS Online")

    if progresso:
        progresso(60, "publicando o serviço hospedado (feature service)")
    parametros_publicar = json.dumps(dict(
        name=nome_servico, targetSR=dict(wkid=4326), maxRecordCount=5000, hasStaticData=False,
        layerInfo=dict(capabilities="Query"),
    ))
    dados_publicar = dict(f="json", token=token, filetype="geojson", publishParameters=parametros_publicar)
    if geojson_item_id_existente:
        dados_publicar["overwrite"] = "true"
    corpo = _pedido("POST", f"{base}/items/{item_id}/publish", dados=dados_publicar,
                    timeout_ler=limites.AGOL_PUBLICAR_TIMEOUT_S)
    servicos = corpo.get("services") or [{}]
    svc = servicos[0]
    job_id = svc.get("jobId")
    servico_item_id = svc.get("serviceItemId")
    servico_url = svc.get("serviceurl")

    for tentativa in range(tentativas_status):
        if not job_id or not servico_item_id:
            break
        s = _pedido("GET", f"{base}/items/{servico_item_id}/status",
                    dados=dict(f="json", token=token, jobId=job_id, jobType="publish"))
        estado = s.get("status")
        if estado == "completed":
            break
        if estado == "failed":
            raise ErroAGOL(f"job de publicação falhou no ArcGIS Online: {s}")
        if progresso:
            progresso(min(60 + tentativa, 95), f"aguardando o ArcGIS Online publicar ({estado or 'em fila'})")
        dormir(intervalo_status_s)
    else:
        if job_id:
            raise ErroAGOL("o job de publicação não terminou a tempo (tente publicar de novo em instantes)")

    if progresso:
        progresso(98, "concluído")
    return ResultadoPublicacao(
        geojson_item_id=item_id, servico_item_id=servico_item_id or item_id, servico_url=servico_url,
        n_feicoes=n_feicoes,
    )


__all__ = ["ErroAGOL", "ResultadoPublicacao", "gerar_token", "info_portal", "publicar_camada"]
