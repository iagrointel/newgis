"""Job `rede.importar_continuidade` (item L4-10-continuidade-dec-fec): traz para o inquilino o dado
aberto de continuidade da ANEEL (DEC/FEC apurados, compensação paga e limites) recortado aos conjuntos
que a rede importada declara no campo CONJ.

Ordem dentro do job:
1. confere que a rede é do inquilino e lê os conjuntos dela (campo CONJ da BDGD);
2. valida a pasta de origem (só dentro de `PLAT_ANEEL_CONTINUIDADE_RAIZ`; nada de caminho arbitrário
   do servidor);
3. lê cada arquivo com o recorte já no leitor de parquet e grava, conferindo a contagem contra o
   arquivo — o resultado do job e a tabela `plat.rede_continuidade_fonte` guardam as duas contagens.

⛔ D21 (disco): o job NÃO baixa nada da ANEEL. A pasta é um ativo local já existente; o parâmetro
opcional `caminho` só escolhe uma subpasta dentro da raiz configurada.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from pydantic import BaseModel, Field

from app import settings as cfg
from app.jobs.registro import FalhaDefinitiva, tarefa
from app.rede_utilidades import continuidade

ANO_MIN = 1990
ANO_MAX = 2100


class ImportarContinuidadeParametros(BaseModel):
    rede_id: uuid.UUID
    ano_de: int = Field(ge=ANO_MIN, le=ANO_MAX, description="primeiro ano da faixa a importar")
    ano_ate: int = Field(ge=ANO_MIN, le=ANO_MAX, description="último ano da faixa a importar")
    caminho: str | None = Field(
        default=None, max_length=1024,
        description="subpasta dentro de PLAT_ANEEL_CONTINUIDADE_RAIZ; vazio = a própria raiz",
    )


def _raiz_permitida() -> Path:
    raiz = cfg.obter().PLAT_ANEEL_CONTINUIDADE_RAIZ
    if not raiz:
        raise FalhaDefinitiva(
            "PLAT_ANEEL_CONTINUIDADE_RAIZ não configurada: a importação de continuidade fica desligada "
            "nesta instalação (D21 — o job não baixa o dado aberto da ANEEL)"
        )
    return Path(raiz).resolve()


def resolver_caminho(caminho: str | None) -> Path:
    """A pasta de onde ler, sempre dentro da raiz configurada (defesa contra leitura de caminho arbitrário)."""
    raiz = _raiz_permitida()
    if not caminho:
        p = raiz
    else:
        p = Path(caminho).resolve() if Path(caminho).is_absolute() else (raiz / caminho).resolve()
    if raiz != p and raiz not in p.parents:
        raise FalhaDefinitiva(f"caminho fora de PLAT_ANEEL_CONTINUIDADE_RAIZ ({raiz}): recusado")
    if not p.is_dir():
        raise FalhaDefinitiva(f"pasta de continuidade não encontrada: {p}")
    return p


@tarefa(
    nome="rede.importar_continuidade",
    descricao="Importa a continuidade DEC/FEC da ANEEL (apurado, compensação e limites) para os conjuntos "
              "declarados pela rede, com a contagem conferida contra o arquivo",
    parametros=ImportarContinuidadeParametros,
    pesado=True,
    memoria_mb=1024,
    timeout_s=1800,
    tentativas=1,
    chave=lambda p: f"rede-continuidade:{p.get('rede_id')}",
    perfil_minimo="editor",
)
def rede_importar_continuidade(ctx, rede_id: uuid.UUID, ano_de: int, ano_ate: int,
                               caminho: str | None = None) -> dict:
    if ano_ate < ano_de:
        raise FalhaDefinitiva("faixa de anos invertida: ano_ate menor que ano_de")
    pasta = resolver_caminho(caminho)
    ctx.progresso(1, f"pasta: {pasta.name}")
    with ctx.db() as cur:
        cur.execute("SELECT id FROM plat.rede WHERE id = %s::uuid", (str(rede_id),))
        if cur.fetchone() is None:
            raise FalhaDefinitiva("rede inexistente ou de outro inquilino")
        conjuntos = continuidade.conjuntos_da_rede(cur, str(rede_id))
        if not conjuntos:
            raise FalhaDefinitiva(
                "a rede não declara nenhum conjunto de unidades consumidoras (campo CONJ da BDGD): "
                "sem essa chave não há como ligar a rede à continuidade da ANEEL"
            )
        ctx.log("info", f"{len(conjuntos)} conjunto(s) declarados pela rede")
        try:
            resultado = continuidade.importar(
                cur, ctx.tenant_id, pasta, conjuntos, ano_de, ano_ate,
                job_id=str(ctx.job_id), progresso=ctx.progresso,
            )
        except continuidade.ErroContinuidade as e:
            raise FalhaDefinitiva(str(e)) from e
    ctx.progresso(100, "continuidade importada")
    return resultado
