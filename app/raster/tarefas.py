"""Job `raster.validar` (item L1-01-b; ADR 0015): baixa o objeto enviado, roda `app.raster.validacao.validar()` no
subprocesso isolado e grava o relatório inteiro no resultado do job (`resultado.validacao`). Estados do relatório:
`aceito` (pode seguir para conversão), `pendente` (o usuário tem de responder CRS/NoData/data/escala — o job
CONCLUI com o relatório e a tela cria outro job com `respostas`; nunca se assume um valor) e `recusado` (com a
mensagem exata). Só a ausência do objeto no armazenamento é FalhaDefinitiva: defeito do ARQUIVO nunca é falha do
job, é relatório."""

from __future__ import annotations

import hashlib
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, Field

from app import objetos
from app.jobs.registro import FalhaDefinitiva, tarefa
from app.raster import validacao


class RespostasRaster(BaseModel):
    crs: str | int | None = Field(None, description="EPSG (ex. 4674) ou WKT, quando o arquivo não tem CRS")
    nodata: float | None = Field(None, description="valor de 'sem dado', quando o arquivo não declara")
    data_aquisicao: str | None = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="AAAA-MM-DD")
    escala: tuple[float, float] | None = Field(None, description="[mínimo, máximo] para reescalar a 8 bits (visual)")


class ValidarParametros(BaseModel):
    arquivo_chave: str = Field(..., max_length=512, description="chave do objeto enviado (POST /api/arquivos)")
    perfil: Literal["dados", "visual"] = "dados"
    respostas: RespostasRaster = Field(default_factory=RespostasRaster)


@tarefa(nome="raster.validar", descricao="Valida um raster enviado em subprocesso isolado antes de qualquer conversão",
        parametros=ValidarParametros, pesado=False, memoria_mb=1024, timeout_s=600, tentativas=1,
        chave=lambda p: f"raster.validar:{p.get('arquivo_chave')}", perfil_minimo="editor")
def raster_validar(ctx, arquivo_chave: str, perfil: str = "dados", respostas: dict | None = None) -> dict:
    try:
        dados = objetos.ler(arquivo_chave)
    except (FileNotFoundError, objetos.ChaveInvalida) as e:
        raise FalhaDefinitiva(f"arquivo inexistente no armazenamento: {e}") from e
    sha = hashlib.sha256(dados).hexdigest()
    ctx.entrada(None, sha, f"raster enviado {arquivo_chave}")
    extensao = PurePosixPath(arquivo_chave).suffix.lower() or ".bin"
    caminho = ctx.dir_trabalho / f"original{extensao}"
    caminho.write_bytes(dados)
    del dados
    with ctx.db() as cur:
        cota = objetos._cota_bytes_tenant(cur, ctx.tenant_id)
    respostas = {k: v for k, v in (respostas or {}).items() if v is not None}
    ctx.log("INFO", f"validando {caminho.name} ({caminho.stat().st_size} bytes) perfil={perfil} "
                    f"respostas={sorted(respostas)} em subprocesso RLIMIT_AS={validacao.RLIMIT_AS_MB} MB")
    relatorio = validacao.validar(caminho, perfil=perfil, respostas=respostas, cota_bytes=cota,
                                  dir_trabalho=ctx.dir_trabalho)
    ctx.log("AVISO" if relatorio["estado"] != "aceito" else "INFO", validacao.resumo(relatorio))
    return {"validacao": relatorio, "arquivo_chave": arquivo_chave, "sha256": sha}
