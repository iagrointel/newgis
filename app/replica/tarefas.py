"""Tipo de job `replicas.criar` (item L2-13-b): empacota a réplica em GeoPackage. A tarefa é fina de
propósito — a lógica inteira vive em `app/replica/servico.py::gerar_pacote`, que a suíte exercita sem
precisar de um worker de pé. Registro pelo decorador @tarefa do L0-05, importado em app/jobs/tipos.py."""

import uuid

from pydantic import BaseModel

from app.erros import ErroAPI
from app.jobs.registro import FalhaDefinitiva, tarefa
from app.replica import servico


class ReplicaParametros(BaseModel):
    replica_id: uuid.UUID


@tarefa(
    nome="replicas.criar",
    descricao="Empacota a réplica de trabalho desconectado em GeoPackage (camadas, domínios e plat_sync)",
    parametros=ReplicaParametros,
    pesado=False,
    memoria_mb=1024,
    timeout_s=1800,
    tentativas=2,
    chave=lambda p: f"replica:{p.get('replica_id')}",
    perfil_minimo="campo",
    ferramentas=("ogr2ogr", "ogrinfo"),
)
def replicas_criar(ctx, replica_id: uuid.UUID) -> dict:
    rid = str(replica_id)
    try:
        with ctx.db() as cur:
            return servico.gerar_pacote(cur, rid, progresso=ctx.progresso)
    except ErroAPI as e:
        with ctx.db() as cur:
            cur.execute("UPDATE plat.replica SET estado = 'falhou', erro = %s WHERE id = %s::uuid",
                        (f"{e.erro}: {e.mensagem}", rid))
        # recorte grande demais ou filtro inválido não melhora com retentativa; falha de escrita, sim
        if e.status_code in (409, 413, 422, 404):
            raise FalhaDefinitiva(f"{e.erro}: {e.mensagem}") from e
        raise
