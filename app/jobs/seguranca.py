"""Job periódico `seguranca.varrer_cve` (item L7-03-f-dependencias-cve-log-correcoes; docs/SEGURANCA.md seção
7.6; padrão de app/jobs/periodicos.py). Reaproveita inteiramente `scripts/varredura_cve.py::rodar()` (pip-audit
+ npm audit, a mesma varredura de `make seguranca-deps`/`make seguranca`) e só troca de onde vem o cursor: aqui
é `ctx.db()` do worker, em vez de uma conexão própria. Registrado em PERIODICOS para rodar 1x/dia pela agenda
interna (sincronizada no inquilino técnico `plataforma` na partida do worker, ADR 0003 seção 7); o timer
`deploy/plat-varredura-cve.timer` (que chama `scripts/varredura_cve.py` diretamente) é o caminho independente
da fila, para o caso de o worker estar fora do ar — os dois escrevem na mesma tabela, upsert idempotente."""

from __future__ import annotations

import sys
from pathlib import Path

from pydantic import BaseModel

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "scripts"))
import varredura_cve as vc  # noqa: E402 — módulo em scripts/, fora do pacote app

from app.jobs.registro import tarefa  # noqa: E402
from app.limites import CHAVE_RESERVADA  # noqa: E402


class VarrerCveParametros(BaseModel):
    """Sem parâmetros: varre requirements.txt (e web/vendor/VERSOES.txt via npm, quando disponível) da
    instalação inteira — não é por inquilino, como jobs.manutencao_analyze."""


@tarefa(nome="seguranca.varrer_cve",
        descricao="Varredura diária de CVE conhecido (pip-audit + npm audit) — item L7-03-f",
        parametros=VarrerCveParametros, pesado=False, memoria_mb=256, timeout_s=300, tentativas=1,
        chave=lambda p: f"{CHAVE_RESERVADA}varrer_cve", perfil_minimo="admin")
def jobs_seguranca_varrer_cve(ctx) -> dict:
    resultado = vc.rodar()
    vc.gravar_instantaneo(resultado)
    with ctx.db() as cur:
        varredura_id = vc.persistir(cur, resultado)
    ctx.progresso(100, resultado["resumo"])
    return {"varredura_id": varredura_id, "achados": len(resultado["achados"]), "rc": resultado["rc"],
            "resumo": resultado["resumo"]}


PERIODICOS: list[tuple[str, str, str, dict]] = [
    ("varredura de CVE diária", "20 5 * * *", "seguranca.varrer_cve", {}),
]

from app.jobs import periodicos as _base  # noqa: E402

for _p in PERIODICOS:
    if _p not in _base.PERIODICOS:
        _base.PERIODICOS.append(_p)
