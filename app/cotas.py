"""Cotas e medição de uso por inquilino (item L0-07-c-cotas-uso): o que é comum ao periódico
`jobs.uso_medir` (app/jobs/periodicos.py), à tela /admin/uso (app/auth/rotas_uso.py) e aos testes.

Modelo (ADR docs/adr/20260906T2124-cotas-uso.md):
- cota_bytes (coluna de plat.tenant): armazenamento TOTAL do inquilino — objetos no bucket Garage
  (reserva atômica em app/objetos.py::guardar sob SELECT ... FOR UPDATE + plat.arquivo_uso_bytes) e
  tabelas de camada d_<slug> (reserva da 029 em tenant.uso_reservado_bytes, app/ingestao/carregar.py);
- cota_usuarios / cota_jobs_dia (tenant.config) e cota_itens (tenant.config.catalogo): lidas AO VIVO
  pelas funções plat.cota_* a cada requisição — mudança de cota (org ou superadmin) tem efeito imediato
  por construção, sem cache;
- aviso a 80 % (AVISO_FRAC): calculado na leitura (GET /api/org/uso), nunca gravado — o aviso é sempre
  contra a cota VIGENTE, mesmo que ela mude depois da medição;
- série diária em plat.uso_inquilino (migração 20260906T2124), alimentada pelo periódico jobs.uso_medir;
- sem crédito e sem assento (regra da spec: taxímetro de TB, nunca crédito) — as cotas são de recurso
  físico/contagem, nunca de saldo pré-pago.
"""

from __future__ import annotations

AVISO_FRAC = 0.8  # portão do item: aviso a 80 % de qualquer cota

UNIDADES = ("B", "KB", "MB", "GB", "TB")


def fmt_bytes(n: int | None) -> str:
    """123456789 -> '117,7 MB' (vírgula pt-BR); None -> 'não medido' (bucket nunca criado ou Garage fora)."""
    if n is None:
        return "não medido"
    v = float(n)
    for unidade in UNIDADES:
        if v < 1024 or unidade == UNIDADES[-1]:
            texto = f"{v:.1f}".rstrip("0").rstrip(".")
            return f"{texto.replace('.', ',')} {unidade}"
        v /= 1024
    return f"{n} B"  # pragma: no cover — inalcançável pelo laço acima


def avisos(recursos: list[dict]) -> list[dict]:
    """[{'recurso', 'uso', 'cota', 'fracao'}] só dos recursos em AVISO_FRAC ou mais. `recursos` é a lista de
    {'recurso': str, 'uso': int|None, 'cota': int|None}; uso None (bucket não medido) ou cota None/0 não avisa
    (cota 0 de jobs = bloqueio deliberado, o 429 na criação é o aviso)."""
    saida = []
    for r in recursos:
        uso, cota = r.get("uso"), r.get("cota")
        if uso is None or not cota:
            continue
        frac = uso / cota
        if frac >= AVISO_FRAC:
            saida.append({"recurso": r["recurso"], "uso": uso, "cota": cota, "fracao": round(frac, 4)})
    return saida
