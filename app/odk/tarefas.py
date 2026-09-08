"""Job `odk.sincronizar` (item L2-07-e-odk-central-ponte): puxa os envios de UMA ponte pelo relógio do L0-05,
sem ninguém na tela. É o mesmo corpo da rota `POST /api/odk/pontes/{id}/sincronizar` — a idempotência por
`instanceID` está em `app/odk/ponte.py` e vale para os dois caminhos, que é justamente o ponto: rodar o job
duas vezes, ou rodar o job e a rota, não duplica feição.

Agendar é o agendamento comum do inquilino (`plat.agenda`, tipo `odk.sincronizar`, parâmetro `ponte`), não um
periódico da plataforma: quem decide de quanto em quanto tempo puxar é o dono do formulário, e um periódico
global teria de atravessar inquilinos por função SECURITY DEFINER sem que ninguém tivesse pedido.

O job age COMO O DONO DA PONTE: as feições ficam no nome de quem cadastrou a ponte, e os privilégios são os
dele, lidos do banco a cada execução (`plat.privilegios_de`) — conta desabilitada ou privilégio retirado para
o job na hora, em vez de continuar escrevendo com uma permissão de ontem."""

from types import SimpleNamespace

from pydantic import BaseModel, Field

from app.auth.politica import Politica, politica_de
from app.auth.sessao import Auth
from app.conexao import credencial as credencial_mod
from app.jobs.registro import FalhaDefinitiva, tarefa
from app.odk import ponte as ponte_mod
from app.odk.central import Central, ErroCentral
from app.seguranca_rotacao import decifrar_com_rotacao
from app.settings import settings

# O evento e o log de acesso pedem um `request`; num job não existe requisição. Este objeto responde só ao que
# `app.auth.comum.registrar_evento` lê (cliente e `req_id`), e nada mais — nenhum cabeçalho, nenhum corpo.
PEDIDO_DE_JOB = SimpleNamespace(client=None, state=SimpleNamespace())


class SincronizarParametros(BaseModel):
    ponte: str = Field(min_length=36, max_length=36)


def _auth_do_dono(cur, tenant_id: int, usuario_id: int) -> Auth:
    cur.execute(
        "SELECT u.id, u.login, u.nome, u.email, u.perfil, u.papel_id, u.ativo, u.origem, "
        "u.superadmin, u.totp_ativo, t.slug AS tenant_slug, t.nome AS tenant_nome, t.config, "
        "plat.privilegios_de(u.id) AS privilegios "
        "FROM plat.usuario u JOIN plat.tenant t ON t.id = u.tenant_id WHERE u.id = %s AND u.tenant_id = %s",
        (usuario_id, tenant_id),
    )
    r = cur.fetchone()
    if r is None or not r["ativo"]:
        raise FalhaDefinitiva("o dono da ponte não existe mais ou está desabilitado")
    politica: Politica = politica_de(r["config"], r["tenant_slug"])
    return Auth(
        modo="token", usuario_id=r["id"], tenant_id=tenant_id, login=r["login"], nome=r["nome"], email=r["email"],
        perfil=r["perfil"], superadmin=r["superadmin"], origem=r["origem"], papel_id=r["papel_id"],
        privilegios=list(r["privilegios"] or []), trocar_senha=False, totp_ativo=r["totp_ativo"],
        tenant_slug=r["tenant_slug"], tenant_nome=r["tenant_nome"], config=r["config"] or {}, politica=politica,
    )


@tarefa(
    nome="odk.sincronizar",
    descricao="Puxa os envios de uma ponte com o ODK Central e grava as feições (idempotente por instanceID)",
    parametros=SincronizarParametros, pesado=False, memoria_mb=512, timeout_s=900, tentativas=2,
    chave=lambda p: f"odk_sincronizar:{p.get('ponte')}", perfil_minimo="editor",
)
def odk_sincronizar(ctx, ponte: str) -> dict:
    with ctx.db() as cur:
        cur.execute(
            "SELECT p.*, c.url, c.tipo AS conexao_tipo, c.credencial_cifrada "
            "FROM plat.odk_ponte p JOIN plat.conexao c ON c.id = p.conexao_id WHERE p.id = %s::uuid", (ponte,)
        )
        r = cur.fetchone()
        if r is None:
            raise FalhaDefinitiva("ponte inexistente neste inquilino")
        if r["conexao_tipo"] != "odk_central":
            raise FalhaDefinitiva("a conexão da ponte deixou de ser do tipo odk_central")
        auth = _auth_do_dono(cur, ctx.tenant_id, r["dono_id"])
        cur.execute("SELECT id, tipo, titulo, dados FROM plat.item WHERE id = %s::uuid", (str(r["formulario_id"]),))
        formulario = cur.fetchone()
        if formulario is None or formulario["tipo"] != "formulario":
            raise FalhaDefinitiva("o formulário da ponte não existe mais")
        token = None
        if r["credencial_cifrada"]:
            try:
                token = decifrar_com_rotacao(credencial_mod.decifrar, r["credencial_cifrada"],
                                             settings.PLAT_SECRET, settings.PLAT_SECRET_ANTERIOR)
            except Exception:  # noqa: BLE001 — segredo trocado ou dado corrompido: fala sem token e o Central 401
                token = None
        ctx.progresso(10, "lendo envios do ODK Central")
        try:
            relatorio = ponte_mod.sincronizar(cur, PEDIDO_DE_JOB, auth, r, formulario,
                                              Central(url_base=r["url"], token=token))
        except ErroCentral as e:
            cur.execute("SELECT plat.conexao_saude_registrar(%s::uuid, false, %s, %s, NULL)",
                        (str(r["conexao_id"]), e.status, f"odk:{e.motivo}"[:200]))
            raise
    ctx.progresso(100, f"{relatorio['aplicados']} aplicados, {relatorio['repetidos']} repetidos, "
                       f"{len(relatorio['recusados'])} recusados")
    return relatorio
