"""Relatórios do admin do inquilino (item L0-07-e-relatorios) como tipo de job `relatorios.gerar`: cada relatório
é uma consulta SQL sob a RLS do inquilino do job, escrita em CSV (cabeçalho documentado em CABECALHOS, o mesmo que
GET /api/relatorios/tipos publica) e guardada no armazenamento de objetos (classe `relatorio`, referência = id do
job) — o mesmo caminho da exportação do catálogo (app/catalogo/tarefas.py::catalogo_exportar_lista). Limites
declarados, iguais aos relatórios de uso da Esri: janela de até 12 meses e 10 mil linhas por relatório (o CSV é
cortado nas 10 mil e o resultado diz `truncado`).

Cinco relatórios: membros (perfil/papel, tipo de conta, último acesso, itens e grupos), itens (tipo, dono,
tamanho, compartilhamento, acessos em 30 dias, última modificação), grupos, atividade (eventos por tipo e dia)
e uso (série diária do que já é medido em master: bytes registrados em plat.arquivo, itens, jobs, membros ativos
por dia no log de acesso; a série medida do L0-07-c substitui esta quando entrar).

Dado pessoal: o CSV de membros só carrega e-mail quando o domínio está na lista corporativa do inquilino
(tenant.config.auth.dominios_email, item L0-07-a); com a lista configurada, e-mail fora dela sai vazio. Nenhum
relatório lê CPF nem telefone (a plataforma não guarda). Entrega por e-mail: link assinado do CSV (7 dias) para o
e-mail do próprio solicitante, pelo SMTP efetivo do inquilino; falha no envio não invalida o relatório."""

import csv
import datetime
import io
import uuid

from pydantic import BaseModel, Field

from app import limites, objetos
from app.auth.politica import politica_de
from app.correio import cliente
from app.correio.config import decifrar_senha, smtp_efetivo
from app.jobs.registro import FalhaDefinitiva, tarefa
from app.settings import settings

TIPOS = ("membros", "itens", "grupos", "atividade", "uso")
CABECALHOS: dict[str, list[str]] = {
    "membros": [
        "id", "login", "nome", "email_corporativo", "perfil", "papel", "tipo_conta", "ativo", "segundo_fator",
        "ultimo_acesso", "itens", "grupos", "criado_em",
    ],
    "itens": [
        "id", "tipo", "titulo", "dono", "tamanho_bytes", "acesso", "grupos", "links", "acessos_30d", "criado_em",
        "modificado_em",
    ],
    "grupos": [
        "id", "nome", "dono", "visibilidade", "entrada", "membros", "itens", "administrativo", "criado_em",
    ],
    "atividade": ["dia", "tipo", "eventos"],
    "uso": [
        "dia", "bytes_gravados", "bytes_acumulados", "itens_criados", "itens_acumulados", "jobs_criados",
        "membros_ativos",
    ],
}
DESCRICOES = {
    "membros": "um membro por linha: perfil e papel, tipo de conta (local/ldap/oidc/saml), último acesso, "
               "quantos itens possui e de quantos grupos participa",
    "itens": "um item vivo por linha: tipo, dono, tamanho, nível de acesso, grupos e links de compartilhamento, "
             "acessos nos últimos 30 dias (log de acesso), última modificação",
    "grupos": "um grupo por linha: dono, visibilidade, regra de entrada, membros ativos, itens compartilhados",
    "atividade": "eventos do inquilino por dia e tipo dentro da janela",
    "uso": "série diária dentro da janela: bytes gravados e acumulados (plat.arquivo), itens criados e "
           "acumulados, jobs criados, membros ativos no dia (log de acesso)",
}
CLASSE = "relatorio"
LINK_DIAS = 7


class RelatorioParametros(BaseModel):
    tipo: str = Field(pattern="^(membros|itens|grupos|atividade|uso)$")
    desde: str | None = Field(default=None, max_length=40, description="ISO 8601; ausente = `dias` antes de `ate`")
    ate: str | None = Field(default=None, max_length=40, description="ISO 8601; ausente = agora")
    dias: int = Field(default=30, ge=1, le=limites.RELATORIO_JANELA_DIAS,
                      description="janela quando `desde` está ausente (agendamentos: 1, 7 ou 31)")
    email: bool = Field(default=False, description="enviar o link do CSV ao e-mail do solicitante")


def _instante(valor: str | None) -> datetime.datetime | None:
    if not valor:
        return None
    try:
        dt = datetime.datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError as e:
        raise FalhaDefinitiva(f"data inválida: {valor!r}") from e
    return dt if dt.tzinfo else dt.replace(tzinfo=datetime.UTC)


def janela(desde: str | None, ate: str | None, dias: int) -> tuple[datetime.datetime, datetime.datetime]:
    """[desde, ate) em UTC; `ate` nunca no futuro; janela de no máximo RELATORIO_JANELA_DIAS (12 meses)."""
    agora = datetime.datetime.now(datetime.UTC)
    fim = _instante(ate) or agora
    fim = min(fim, agora)
    inicio = _instante(desde) or (fim - datetime.timedelta(days=dias))
    if inicio >= fim:
        raise FalhaDefinitiva("desde é posterior a ate")
    if fim - inicio > datetime.timedelta(days=limites.RELATORIO_JANELA_DIAS):
        raise FalhaDefinitiva(f"janela acima de {limites.RELATORIO_JANELA_DIAS} dias (12 meses)")
    return inicio, fim


# ---------------------------------------------------------------- consultas (uma por relatório; RLS do inquilino)
def _membros(cur, inicio, fim, teto: int, politica) -> list[dict]:
    cur.execute(
        """
        SELECT u.id, u.login, u.nome, u.email, u.perfil, p.nome AS papel, u.origem AS tipo_conta, u.ativo,
               u.totp_ativo AS segundo_fator, u.ultimo_login AS ultimo_acesso, u.criado_em,
               (SELECT count(*) FROM plat.item i WHERE i.dono_id = u.id AND i.apagado_em IS NULL) AS itens,
               (SELECT count(*) FROM plat.grupo_membro m WHERE m.usuario_id = u.id AND m.estado = 'ativo') AS grupos
        FROM plat.usuario u LEFT JOIN plat.papel_personalizado p ON p.id = u.papel_id
        ORDER BY u.login LIMIT %s
        """,
        (teto,),
    )
    linhas = []
    for r in cur.fetchall():
        email = r["email"] or ""
        dominio = email.rsplit("@", 1)[-1].lower() if "@" in email else ""
        corporativo = email if (email and (not politica.dominios_email or dominio in politica.dominios_email)) else ""
        linhas.append({**r, "email_corporativo": corporativo})
    return linhas


def _itens(cur, inicio, fim, teto: int, politica) -> list[dict]:
    cur.execute(
        """
        WITH acessos AS (
          SELECT substring(l.rota FROM '^/api/itens/([0-9a-f-]{36})')::uuid AS item_id, count(*) AS n
          FROM plat.log_acesso l
          WHERE l.em >= now() - interval '30 days' AND l.rota LIKE '/api/itens/%%' AND l.status < 400
          GROUP BY 1
        )
        SELECT i.id, i.tipo, i.titulo, u.login AS dono, i.tamanho_bytes, i.acesso, i.criado_em, i.modificado_em,
               (SELECT count(*) FROM plat.item_grupo g WHERE g.item_id = i.id) AS grupos,
               (SELECT count(*) FROM plat.compartilhamento_link k
                 WHERE k.item_id = i.id AND k.revogado_em IS NULL) AS links,
               coalesce(a.n, 0) AS acessos_30d
        FROM plat.item i JOIN plat.usuario u ON u.id = i.dono_id LEFT JOIN acessos a ON a.item_id = i.id
        WHERE i.apagado_em IS NULL
        ORDER BY i.modificado_em DESC, i.id LIMIT %s
        """,
        (teto,),
    )
    return [dict(r) for r in cur.fetchall()]


def _grupos(cur, inicio, fim, teto: int, politica) -> list[dict]:
    cur.execute(
        """
        SELECT g.id, g.nome, u.login AS dono, g.visibilidade, g.entrada, g.administrativo, g.criado_em,
               (SELECT count(*) FROM plat.grupo_membro m WHERE m.grupo_id = g.id AND m.estado = 'ativo') AS membros,
               (SELECT count(*) FROM plat.item_grupo ig WHERE ig.grupo_id = g.id) AS itens
        FROM plat.grupo g JOIN plat.usuario u ON u.id = g.dono_id
        ORDER BY g.nome LIMIT %s
        """,
        (teto,),
    )
    return [dict(r) for r in cur.fetchall()]


def _atividade(cur, inicio, fim, teto: int, politica) -> list[dict]:
    cur.execute(
        """
        SELECT (e.em AT TIME ZONE 'UTC')::date AS dia, e.tipo, count(*) AS eventos
        FROM plat.evento e WHERE e.em >= %s AND e.em < %s
        GROUP BY 1, 2 ORDER BY 1, 2 LIMIT %s
        """,
        (inicio, fim, teto),
    )
    return [dict(r) for r in cur.fetchall()]


def _uso(cur, inicio, fim, teto: int, politica) -> list[dict]:
    cur.execute(
        """
        WITH dias AS (
          SELECT d::date AS dia FROM generate_series(%s::date, (%s - interval '1 second')::date, interval '1 day') d
        ),
        arq AS (
          SELECT (criado_em AT TIME ZONE 'UTC')::date AS dia, sum(bytes) AS b FROM plat.arquivo
          WHERE apagado_em IS NULL GROUP BY 1
        ),
        itens AS (
          SELECT (criado_em AT TIME ZONE 'UTC')::date AS dia, count(*) AS n FROM plat.item
          WHERE apagado_em IS NULL GROUP BY 1
        ),
        jobs AS (
          SELECT (criado_em AT TIME ZONE 'UTC')::date AS dia, count(*) AS n FROM plat.job GROUP BY 1
        ),
        ativos AS (
          SELECT (em AT TIME ZONE 'UTC')::date AS dia, count(DISTINCT usuario_id) AS n FROM plat.log_acesso
          WHERE usuario_id IS NOT NULL AND em >= %s AND em < %s GROUP BY 1
        )
        SELECT d.dia,
               coalesce(a.b, 0) AS bytes_gravados,
               (SELECT coalesce(sum(b), 0) FROM arq WHERE arq.dia <= d.dia) AS bytes_acumulados,
               coalesce(i.n, 0) AS itens_criados,
               (SELECT coalesce(sum(n), 0) FROM itens WHERE itens.dia <= d.dia) AS itens_acumulados,
               coalesce(j.n, 0) AS jobs_criados,
               coalesce(v.n, 0) AS membros_ativos
        FROM dias d LEFT JOIN arq a ON a.dia = d.dia LEFT JOIN itens i ON i.dia = d.dia
             LEFT JOIN jobs j ON j.dia = d.dia LEFT JOIN ativos v ON v.dia = d.dia
        ORDER BY d.dia LIMIT %s
        """,
        (inicio, fim, inicio, fim, teto),
    )
    return [dict(r) for r in cur.fetchall()]


CONSULTAS = {"membros": _membros, "itens": _itens, "grupos": _grupos, "atividade": _atividade, "uso": _uso}


def _texto(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "sim" if v else "nao"
    if isinstance(v, datetime.datetime):
        return v.astimezone(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(v, datetime.date):
        return v.isoformat()
    return str(v)


def csv_de(tipo: str, linhas: list[dict]) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CABECALHOS[tipo], extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for r in linhas:
        w.writerow({k: _texto(r.get(k)) for k in CABECALHOS[tipo]})
    return buf.getvalue().encode("utf-8")


def _enviar_link(cur, ctx, tipo: str, chave: str, inicio, fim) -> dict:
    """Link assinado (7 dias) ao e-mail do solicitante pelo SMTP efetivo do inquilino; devolve o que aconteceu."""
    cur.execute("SELECT config, nome FROM plat.tenant WHERE id = plat.tenant_atual()")
    t = cur.fetchone()
    cur.execute("SELECT email, login FROM plat.usuario WHERE id = %s", (ctx.usuario_id,))
    u = cur.fetchone()
    if not u or not u["email"]:
        return {"enviado": False, "motivo": "solicitante sem e-mail"}
    cfg = smtp_efetivo(t["config"], settings)
    if cfg is None:
        return {"enviado": False, "motivo": "SMTP não configurado neste inquilino nem na instalação"}
    link = settings.PLAT_URL_PUBLICA + objetos.url_assinada(chave, LINK_DIAS * 86400)
    assunto = f"[{t['nome']}] relatório de {tipo} pronto"
    texto = (
        f"O relatório de {tipo} do inquilino {t['nome']} está pronto.\n"
        f"Janela: {_texto(inicio)} a {_texto(fim)}.\n\n"
        f"Baixe o CSV pelo link abaixo (válido por {LINK_DIAS} dias):\n{link}\n"
    )
    senha = decifrar_senha(cfg, settings.PLAT_SECRET, settings.PLAT_SECRET_ANTERIOR)
    try:
        cliente.enviar(cfg, senha, u["email"], assunto, texto)
    except cliente.ErroSMTP as e:
        ctx.log("AVISO", f"relatorio {tipo}: e-mail não enviado: {e}")
        return {"enviado": False, "motivo": str(e)[:300]}
    finally:
        senha = None  # noqa: F841
    ctx.log("INFO", f"relatorio {tipo}: link enviado a {u['email']} via {cfg.host}:{cfg.porta}")
    return {"enviado": True, "destinatario": u["email"]}


@tarefa(
    nome="relatorios.gerar",
    descricao="Gera um relatório do inquilino (membros, itens, grupos, atividade, uso) em CSV no armazenamento",
    parametros=RelatorioParametros,
    pesado=False,
    memoria_mb=512,
    timeout_s=600,
    tentativas=1,
    perfil_minimo="admin",
)
def relatorios_gerar(ctx, tipo: str, desde: str | None = None, ate: str | None = None, dias: int = 30,
                     email: bool = False) -> dict:
    inicio, fim = janela(desde, ate, dias)
    teto = limites.RELATORIO_LINHAS_MAX
    ctx.progresso(5, f"consultando {tipo}")
    with ctx.db() as cur:
        cur.execute("SELECT slug, config FROM plat.tenant WHERE id = plat.tenant_atual()")
        t = cur.fetchone()
        if t is None:
            raise FalhaDefinitiva("inquilino inexistente")
        politica = politica_de(t["config"] or {}, t["slug"])
        linhas = CONSULTAS[tipo](cur, inicio, fim, teto + 1, politica)
    truncado = len(linhas) > teto
    linhas = linhas[:teto]
    ctx.progresso(60, f"{len(linhas)} linhas; gravando CSV")
    dados = csv_de(tipo, linhas)
    with ctx.db() as cur:
        o = objetos.guardar(cur, CLASSE, dados, "text/csv", item_id=ctx.job_id, usuario_id=ctx.usuario_id)
        correio = _enviar_link(cur, ctx, tipo, o["chave"], inicio, fim) if email else None
    ctx.progresso(100, f"relatório de {tipo} pronto ({len(linhas)} linhas)")
    return {
        "tipo": tipo,
        "linhas": len(linhas),
        "truncado": truncado,
        "limite_linhas": teto,
        "cabecalho": CABECALHOS[tipo],
        "desde": _texto(inicio),
        "ate": _texto(fim),
        "chave": o["chave"],
        "sha256": o["sha256"],
        "bytes": o["bytes"],
        "email": correio,
    }


def nome_arquivo(tipo: str, job_id: uuid.UUID | str) -> str:
    return f"relatorio_{tipo}_{str(job_id)[:8]}.csv"
