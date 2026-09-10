"""Telemetria OPCIONAL do appliance (item L7-11-c-telemetria-opcional; L7_CONCEITO C13). Desligada por padrão;
só o superadmin liga, depois de ver na tela o JSON EXATO que sairá (`GET /api/telemetria` devolve a prévia; o
que o job envia é `relatorio()` — a mesma função — e o enviado fica gravado em `plat.telemetria.ultimo_relatorio`
para o teste comparar). Uma vez por dia (periódico `telemetria.enviar`), com a chave própria do appliance no
cabeçalho `X-Plat-Chave`. O relatório tem SÓ os campos de `CAMPOS` (o teste reprova qualquer chave a mais):
versão, saúde dos componentes e contagens agregadas — nunca nome de inquilino/usuário, nunca geometria, nunca
conteúdo. Desligada, este módulo não abre conexão nenhuma (o job devolve sem tocar a rede — cláusula do portão).

O RECEPTOR (`POST /api/telemetria/receber`) é a mesma aplicação rodando na casa: aceita só chave registrada por
superadmin em `plat.telemetria_appliance` (403 para desconhecida, sem gravar nada) e guarda o último relatório
de cada appliance para o painel de suporte."""

from __future__ import annotations

import datetime
import json

import httpx
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from app import db
from app.auth.comum import registrar_evento
from app.auth.sessao import Auth, autenticado, iso
from app.erros import ErroAPI
from app.jobs.registro import tarefa
from app.saude import estado_banco, estado_fila, sondar_servico
from app.settings import settings
from app.versao import git_sha_curto, versao

router = APIRouter(prefix="/api/telemetria", tags=["telemetria"])
SUPER = {"x-auth": "S", "x-privilegio": "superadmin"}
CABECALHO_CHAVE = "X-Plat-Chave"
TIMEOUT_S = 15.0
# Os campos do relatório, e nada além deles (docs/APPLIANCE.md §5). Ordem = ordem no JSON.
CAMPOS = (
    "esquema", "chave", "nome_instalacao", "enviado_em", "versao", "git_sha", "ambiente",
    "banco", "migracoes_aplicadas", "migracoes_pendentes", "servicos", "fila", "contagens",
)
CAMPOS_CONTAGENS = ("inquilinos", "usuarios", "itens", "camadas", "jobs_24h", "gb_arquivos")


class TelemetriaEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ligada: bool
    nome_instalacao: str | None = Field(default=None, max_length=120)


class ApplianceEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chave: str = Field(min_length=16, max_length=128, pattern=r"^[0-9a-f]+$")
    nome: str = Field(min_length=1, max_length=120)


# --------------------------------------------------------------------------- relatório


def _estado(cur) -> dict:
    cur.execute("SELECT * FROM plat.telemetria WHERE id = 1")
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(500, "telemetria_sem_linha", "plat.telemetria sem a linha da instalação (migração 20260908T0555)")
    return r


def relatorio() -> dict:
    """O JSON que sai — o mesmo que a tela mostra antes de ligar. Só agregados."""
    banco, aplicadas, pendentes, _ultima = estado_banco()
    with db.db() as cur:
        estado = _estado(cur)
        cur.execute("SELECT plat.telemetria_contagens() AS c")
        contagens = cur.fetchone()["c"]
    fila = estado_fila() if banco == "ok" else {"erro": True}
    corpo = {
        "esquema": 1,
        "chave": estado["chave"],
        "nome_instalacao": estado["nome_instalacao"],
        "enviado_em": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "versao": versao(),
        "git_sha": git_sha_curto(),
        "ambiente": settings.PLAT_AMBIENTE,
        "banco": banco,
        "migracoes_aplicadas": aplicadas,
        "migracoes_pendentes": pendentes,
        "servicos": {nome: sondar_servico(url) for nome, url in settings.servicos().items()},
        "fila": {k: fila.get(k) for k in ("pendentes", "rodando", "workers_vivos")} if "erro" not in fila else fila,
        "contagens": {k: contagens.get(k) for k in CAMPOS_CONTAGENS},
    }
    assert tuple(corpo) == CAMPOS  # o contrato é a tupla; quem acrescentar campo tem de acrescentar em CAMPOS
    return corpo


def conferir_campos(corpo: dict) -> list[str]:
    """chaves fora do contrato (para o teste e para o receptor): vazio = só os campos declarados."""
    extras = [k for k in corpo if k not in CAMPOS]
    extras += [f"contagens.{k}" for k in (corpo.get("contagens") or {}) if k not in CAMPOS_CONTAGENS]
    return extras


def enviar(corpo: dict, url: str, chave: str) -> tuple[bool, int | None, str]:
    """POST do relatório ao receptor. Nunca levanta: (ok, status, mensagem)."""
    try:
        r = httpx.post(url, json=corpo, headers={CABECALHO_CHAVE: chave}, timeout=TIMEOUT_S, trust_env=False)
    except httpx.HTTPError as e:
        return False, None, f"erro_de_conexao:{type(e).__name__}"
    return 200 <= r.status_code < 300, r.status_code, f"http_{r.status_code}"


def enviar_se_ligada(agora: bool = False) -> dict:
    """Corpo do job (e do 'enviar agora'). Desligada = devolve sem abrir conexão. Grava o resultado e o JSON
    EXATO enviado em plat.telemetria."""
    with db.db() as cur:
        estado = _estado(cur)
    if not estado["ligada"]:
        return {"enviado": False, "motivo": "telemetria desligada: nenhum pedido de rede"}
    url = settings.PLAT_TELEMETRIA_URL
    corpo = relatorio()
    if not url:
        ok, status, msg = False, None, "sem_destino_configurado (PLAT_TELEMETRIA_URL vazio)"
    else:
        ok, status, msg = enviar(corpo, url, estado["chave"])
    with db.db() as cur:
        cur.execute(
            "UPDATE plat.telemetria SET ultimo_envio_em = now(), ultimo_envio_ok = %s, ultimo_envio_msg = %s, "
            "ultimo_relatorio = %s::jsonb, atualizado_em = now() WHERE id = 1",
            (ok, msg, json.dumps(corpo, ensure_ascii=False)),
        )
    return {"enviado": ok, "status": status, "motivo": msg, "relatorio": corpo}


# --------------------------------------------------------------------------- rotas do appliance (superadmin)


def _json_estado(r: dict) -> dict:
    return {
        "ligada": r["ligada"], "chave": r["chave"], "nome_instalacao": r["nome_instalacao"],
        "ligada_por": r["ligada_por"], "ligada_em": iso(r["ligada_em"]), "ultimo_envio_em": iso(r["ultimo_envio_em"]),
        "ultimo_envio_ok": r["ultimo_envio_ok"], "ultimo_envio_msg": r["ultimo_envio_msg"],
        "ultimo_relatorio": r["ultimo_relatorio"], "destino": settings.PLAT_TELEMETRIA_URL,
        "campos": list(CAMPOS), "campos_contagens": list(CAMPOS_CONTAGENS),
    }


@router.get("", openapi_extra=SUPER)
def ver(auth: Auth = autenticado(superadmin=True, so_sessao=True)):
    """estado + PRÉVIA: o JSON exatamente como sairia agora (é o que a tela mostra antes de ligar)."""
    with db.db() as cur:
        estado = _estado(cur)
    return {**_json_estado(estado), "previa": relatorio()}


@router.put("", openapi_extra=SUPER)
def ligar_ou_desligar(corpo: TelemetriaEntrada, request: Request,
                      auth: Auth = autenticado(superadmin=True, so_sessao=True)):
    with db.db(auth.contexto()) as cur:
        if corpo.ligada:
            cur.execute(
                "UPDATE plat.telemetria SET ligada = true, ligada_por = %s, ligada_em = now(), "
                "nome_instalacao = coalesce(%s, nome_instalacao), atualizado_em = now() WHERE id = 1",
                (auth.login, corpo.nome_instalacao),
            )
        else:
            cur.execute("UPDATE plat.telemetria SET ligada = false, atualizado_em = now() WHERE id = 1")
        registrar_evento(cur, request, "telemetria/ligar" if corpo.ligada else "telemetria/desligar", "telemetria", 1,
                         {"nome_instalacao": corpo.nome_instalacao, "campos": list(CAMPOS)})
        estado = _estado(cur)
    return _json_estado(estado)


@router.post("/enviar", openapi_extra=SUPER)
def enviar_agora(request: Request, auth: Auth = autenticado(superadmin=True, so_sessao=True)):
    resultado = enviar_se_ligada(agora=True)
    with db.db(auth.contexto()) as cur:
        registrar_evento(cur, request, "telemetria/enviar", "telemetria", 1,
                         {"enviado": resultado["enviado"], "motivo": resultado["motivo"]})
    return resultado


# --------------------------------------------------------------------------- receptor (a instalação da casa)


@router.get("/appliances", openapi_extra=SUPER)
def appliances(auth: Auth = autenticado(superadmin=True, so_sessao=True)):
    with db.db() as cur:
        cur.execute("SELECT chave, nome, registrado_em, ultimo_recebido_em, recebidos, ultimo_relatorio "
                    "FROM plat.telemetria_appliance ORDER BY nome")
        return [{**r, "registrado_em": iso(r["registrado_em"]), "ultimo_recebido_em": iso(r["ultimo_recebido_em"])}
                for r in cur.fetchall()]


@router.post("/appliances", status_code=201, openapi_extra=SUPER)
def registrar_appliance(corpo: ApplianceEntrada, request: Request,
                        auth: Auth = autenticado(superadmin=True, so_sessao=True)):
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "INSERT INTO plat.telemetria_appliance(chave, nome) VALUES (%s, %s) "
            "ON CONFLICT (chave) DO UPDATE SET nome = EXCLUDED.nome RETURNING chave, nome",
            (corpo.chave, corpo.nome),
        )
        r = cur.fetchone()
        registrar_evento(cur, request, "telemetria/receber", "telemetria_appliance", corpo.chave,
                         {"acao": "registrar", "nome": corpo.nome})
    return {"chave": r["chave"], "nome": r["nome"]}


@router.delete("/appliances/{chave}", status_code=204, openapi_extra=SUPER)
def apagar_appliance(chave: str, auth: Auth = autenticado(superadmin=True, so_sessao=True)):
    with db.db() as cur:
        cur.execute("DELETE FROM plat.telemetria_appliance WHERE chave = %s", (chave,))
        if cur.rowcount == 0:
            raise ErroAPI(404, "appliance_inexistente", "chave não registrada")


@router.post("/receber", openapi_extra={"x-auth": "-", "x-privilegio": "publico"})
async def receber(request: Request):
    """Sem sessão: a autenticação é a chave do appliance. Chave desconhecida = 403 e NADA gravado."""
    chave = request.headers.get(CABECALHO_CHAVE, "")
    if not chave:
        raise ErroAPI(401, "chave_ausente", f"informe {CABECALHO_CHAVE}")
    try:
        corpo = await request.json()
    except ValueError as e:
        raise ErroAPI(400, "json_invalido", "corpo precisa ser JSON") from e
    if not isinstance(corpo, dict):
        raise ErroAPI(400, "json_invalido", "corpo precisa ser um objeto JSON")
    with db.db() as cur:
        cur.execute("SELECT nome FROM plat.telemetria_appliance WHERE chave = %s", (chave,))
        r = cur.fetchone()
        if r is None:
            raise ErroAPI(403, "chave_desconhecida", "appliance não registrado nesta instalação")
        extras = conferir_campos(corpo)
        if extras or corpo.get("chave") != chave:
            raise ErroAPI(422, "relatorio_fora_do_contrato",
                          "relatório com campo fora da lista declarada ou chave do corpo diferente do cabeçalho",
                          {"extras": extras})
        cur.execute(
            "UPDATE plat.telemetria_appliance SET ultimo_recebido_em = now(), ultimo_relatorio = %s::jsonb, "
            "recebidos = recebidos + 1 WHERE chave = %s",
            (json.dumps(corpo, ensure_ascii=False), chave),
        )
    return {"recebido": True, "appliance": r["nome"]}


# --------------------------------------------------------------------------- job diário


class EnviarParametros(BaseModel):
    pass


@tarefa(
    nome="telemetria.enviar", descricao="Envio diário da telemetria do appliance (só quando ligada pelo superadmin)",
    parametros=EnviarParametros, pesado=False, memoria_mb=128, timeout_s=120, tentativas=1,
    chave=lambda p: "telemetria_enviar", perfil_minimo="admin",
)
def telemetria_enviar(ctx) -> dict:
    resultado = enviar_se_ligada()
    return {k: v for k, v in resultado.items() if k != "relatorio"}


from app.jobs import periodicos as _base  # noqa: E402 — importar registra o periódico

_PERIODICO = ("telemetria do appliance", "30 4 * * *", "telemetria.enviar", {})
if _PERIODICO not in _base.PERIODICOS:
    _base.PERIODICOS.append(_PERIODICO)
