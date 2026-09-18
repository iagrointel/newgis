"""Rotas de LEITURA da medição de uso do inquilino (item L0-07-c-cotas-uso).

`plat.uso_inquilino` é escrita uma vez por dia pelo periódico `jobs.uso_medir` (app/jobs/periodicos.py) e,
até 18/09/2026, nunca era lida de volta: nenhuma rota e nenhuma tela — achado do adversário do T9, que
derrubou a cláusula "tela 'Uso' do admin do inquilino com gráfico" do portão do item. Estas duas rotas são
o caminho de volta:

* `GET /api/uso` — a série diária do PRÓPRIO inquilino da sessão (RLS da tabela já restringe a linha; o
  privilégio `org.configurar` restringe quem, dentro do inquilino, pode ver a conta) com as cotas em vigor
  ao lado, para a tela desenhar consumo contra teto sem fazer dois pedidos.
O mesmo corpo traz `agora`: os contadores que a plataforma já mantém ao vivo (`tenant.uso_bytes`, itens,
usuários). Sem isso a tela mentiria por até 24 h — numa instalação nova, ou antes de o periódico do dia
rodar, a série não tem o ponto de hoje e o consumo de ontem apareceria como se fosse o atual. `agora` NÃO
refaz a medição (a medição é `plat.uso_medir`, que grava, e uma rota GET não grava): é leitura dos
contadores vivos, e por isso pode divergir da série do dia anterior — a tela diz qual é qual.

Nenhuma rota de ESCRITA: quem escreve é o periódico, e mudar cota é do console do superadmin
(`PATCH /api/plataforma/inquilinos/{id}`), que já existe e já é o que o portão chama de "efeito imediato"."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app import db
from app.auth.sessao import Auth, autenticado

router = APIRouter(prefix="/api/uso", tags=["uso"])
PRIV_LER = {"x-auth": "S/T", "x-privilegio": "org.configurar"}
DIAS_MAX = 366


class PontoUso(BaseModel):
    dia: str
    bytes_banco: int
    bytes_bucket: int
    bytes_total: int
    itens: int
    itens_lixeira: int
    usuarios_total: int
    usuarios_ativos_30d: int
    jobs: int
    job_tempo_ms: int
    requisicoes: int
    bytes_servidos: int
    medido_em: str | None


class Cotas(BaseModel):
    cota_bytes: int | None
    cota_usuarios: int | None
    cota_itens: int | None
    cota_jobs_dia: int | None


class Agora(BaseModel):
    bytes_total: int
    itens: int
    itens_lixeira: int
    usuarios_total: int
    jobs_hoje: int


class SerieUso(BaseModel):
    inquilino: str
    dias: int
    pontos: list[PontoUso]
    cotas: Cotas
    agora: Agora
    ultimo_medido_em: str | None


def _ponto(r) -> dict:
    return {
        "dia": r["dia"].isoformat(),
        "bytes_banco": int(r["bytes_banco"]), "bytes_bucket": int(r["bytes_bucket"]),
        "bytes_total": int(r["bytes_banco"]) + int(r["bytes_bucket"]),
        "itens": int(r["itens"]), "itens_lixeira": int(r["itens_lixeira"]),
        "usuarios_total": int(r["usuarios_total"]), "usuarios_ativos_30d": int(r["usuarios_ativos_30d"]),
        "jobs": int(r["jobs"]), "job_tempo_ms": int(r["job_tempo_ms"]),
        "requisicoes": int(r["requisicoes"]), "bytes_servidos": int(r["bytes_servidos"]),
        "medido_em": r["medido_em"].astimezone().isoformat(timespec="seconds") if r["medido_em"] else None,
    }


def _cotas(cur) -> dict:
    """Cotas em vigor: `cota_bytes` é coluna própria de `plat.tenant`; as outras três moram em `config`
    (jsonb), como o install.sh e o console do superadmin as escrevem. Ausente = sem teto (None), nunca 0:
    zero significaria "não pode nada" e é o contrário do que ausência quer dizer aqui."""
    cur.execute("SELECT slug, cota_bytes, config FROM plat.tenant WHERE id = plat.tenant_atual()")
    r = cur.fetchone()
    cfg = r["config"] or {}

    def n(chave):
        v = cfg.get(chave)
        return int(v) if v not in (None, "") else None

    return {"slug": r["slug"],
            "cotas": {"cota_bytes": int(r["cota_bytes"]) if r["cota_bytes"] else None,
                      "cota_usuarios": n("cota_usuarios"), "cota_itens": n("cota_itens"),
                      "cota_jobs_dia": n("cota_jobs_dia")}}


def _agora(cur) -> dict:
    """Contadores vivos, os MESMOS que a plataforma já usa para cobrar cota — nunca uma segunda contagem
    própria: `tenant.uso_bytes` é o que `app/cotas.py` reserva e o expurgo devolve, e os itens/usuários são
    a contagem que as telas de conteúdo e de usuários mostram."""
    cur.execute("SELECT uso_bytes FROM plat.tenant WHERE id = plat.tenant_atual()")
    bytes_total = int(cur.fetchone()["uso_bytes"] or 0)
    cur.execute("SELECT count(*) FILTER (WHERE apagado_em IS NULL) AS vivos, "
                "       count(*) FILTER (WHERE apagado_em IS NOT NULL) AS lixeira FROM plat.item")
    r = cur.fetchone()
    cur.execute("SELECT count(*) AS n FROM plat.usuario WHERE ativo")
    usuarios = int(cur.fetchone()["n"])
    cur.execute("SELECT count(*) AS n FROM plat.job WHERE criado_em >= date_trunc('day', now())")
    jobs = int(cur.fetchone()["n"])
    return {"bytes_total": bytes_total, "itens": int(r["vivos"]), "itens_lixeira": int(r["lixeira"]),
            "usuarios_total": usuarios, "jobs_hoje": jobs}


@router.get("", response_model=SerieUso, openapi_extra=PRIV_LER)
def serie(dias: int = 30, auth: Auth = autenticado("org.configurar", escopo_token="admin:inquilino")):
    """Série diária do inquilino da sessão, do dia mais antigo para o mais recente (a ordem que um gráfico
    de linha desenha sem inverter nada no navegador)."""
    n = min(max(int(dias or 30), 1), DIAS_MAX)
    with db.db(auth.contexto()) as cur:
        base = _cotas(cur)
        agora = _agora(cur)
        cur.execute(
            "SELECT dia, bytes_banco, bytes_bucket, itens, itens_lixeira, usuarios_total, "
            "       usuarios_ativos_30d, jobs, job_tempo_ms, requisicoes, bytes_servidos, medido_em "
            "FROM plat.uso_inquilino WHERE dia > (current_date - %s::int) ORDER BY dia", (n,),
        )
        pontos = [_ponto(r) for r in cur.fetchall()]
    return {"inquilino": base["slug"], "dias": n, "pontos": pontos, "cotas": base["cotas"], "agora": agora,
            "ultimo_medido_em": pontos[-1]["medido_em"] if pontos else None}
