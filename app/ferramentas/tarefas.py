"""Tarefas de ferramenta (item L2-16-a-sdk-python-geo), registradas pelo decorador @tarefa do L0-05 e
importadas em app/jobs/tipos.py. A primeira é `ferramentas.buffer`: buffer de uma geometria GeoJSON com
distância em metros num SRID MÉTRICO (recusa srid geográfico com FalhaDefinitiva — buffer em graus não
tem unidade). O resultado vira item `ferramenta_resultado` (migração 20260908T1847) com procedência, e o
retorno do job traz `item_id` — é esse retorno que o SDK devolve ao chamador.

A procedência do JOB (tipo, versão do tipo, git_sha, parâmetros, entradas, worker, tempos) é montada
pelo próprio worker (app/jobs/worker.py::_proveniencia); a tarefa só declara as ENTRADAS (sha256 da
geometria) em ctx.entradas e grava no item o job_id — o rastro completo fica no job.
"""

import hashlib
import json
import uuid

import psycopg2.extras
import pyproj
import shapely
from pydantic import BaseModel, Field, field_validator
from shapely.geometry import mapping, shape

from app import limites
from app.jobs.registro import FalhaDefinitiva, tarefa

GEOMETRIAS = (
    "Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon",
)


class BufferParametros(BaseModel):
    geometria: dict = Field(description="geometria GeoJSON (type + coordinates) no srid informado")
    distancia_m: float = Field(ge=0.0, le=limites.FERRAMENTA_BUFFER_MAX_M)
    srid: int = Field(default=31983, description="SRID MÉTRICO da geometria (SIRGAS 2000 UTM, metros)")
    titulo: str | None = Field(default=None, max_length=250)

    @field_validator("geometria")
    @classmethod
    def _geometria_valida(cls, v: dict) -> dict:
        if not isinstance(v, dict) or v.get("type") not in GEOMETRIAS or "coordinates" not in v:
            raise ValueError(f"geometria GeoJSON com type em {GEOMETRIAS} e coordinates")
        if len(json.dumps(v)) > limites.FERRAMENTA_GEOJSON_MAX_BYTES:
            raise ValueError(f"GeoJSON acima do teto de {limites.FERRAMENTA_GEOJSON_MAX_BYTES} bytes")
        return v

    @field_validator("srid")
    @classmethod
    def _srid_metrico(cls, v: int) -> int:
        try:
            geografico = pyproj.CRS.from_user_input(v).is_geographic
        except Exception as e:  # pyproj.CRSError e afins: srid desconhecido é recusa, nunca buffer torto
            raise ValueError(f"srid {v} desconhecido") from e
        if geografico:
            raise ValueError(f"srid {v} é geográfico (graus); buffer exige srid métrico (metros)")
        return v


@tarefa(
    nome="ferramentas.buffer",
    descricao="Buffer de uma geometria GeoJSON (distância em metros, srid métrico); resultado vira item",
    parametros=BufferParametros,
    pesado=False,
    memoria_mb=256,
    timeout_s=120,
    tentativas=2,
    perfil_minimo="editor",
    versao=1,
)
def ferramentas_buffer(ctx, geometria: dict, distancia_m: float, srid: int = 31983,
                       titulo: str | None = None) -> dict:
    entrada = json.dumps(geometria, sort_keys=True, separators=(",", ":")).encode("utf-8")
    sha_entrada = hashlib.sha256(entrada).hexdigest()
    ctx.entrada(None, sha_entrada, f"geometria GeoJSON de entrada (srid {srid})")
    forma = shape(geometria)
    if forma.is_empty:
        raise FalhaDefinitiva("geometria de entrada vazia")
    ctx.progresso(30, "calculando buffer")
    buffer = forma.buffer(distancia_m)
    buffer_geojson = mapping(buffer)
    ctx.progresso(70, "gravando item")
    item_id = str(uuid.uuid4())
    # extent do item é sempre 4326 (padrão do catálogo): transforma os cantos do envelope do buffer
    extent_4326 = _extent_em_4326(buffer, srid)
    titulo_final = (titulo or f"buffer de {distancia_m:g} m").strip()[:250]
    with ctx.db() as cur:
        cur.execute(
            "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, extent, extent_origem, "
            "criado_por, modificado_por) "
            "VALUES (%s::uuid, %s, 'ferramenta_resultado', %s, %s, %s, "
            + ("ST_MakeEnvelope(%s,%s,%s,%s,4326)" if extent_4326 else "NULL") + ", %s, %s, %s)",
            [
                item_id, ctx.tenant_id, titulo_final, ctx.usuario_id,
                psycopg2.extras.Json({
                    "ferramenta": "ferramentas.buffer",
                    "parametros": {"distancia_m": distancia_m, "srid": srid},
                    "resultado": {"buffer": buffer_geojson, "area_m2": buffer.area,
                                  "comprimento_m": buffer.length},
                    "job_id": str(ctx.job_id),
                    "procedencia": {
                        "ferramenta": "ferramentas.buffer",
                        "versao_tipo": 1,
                        "sha256_geometria_entrada": sha_entrada,
                        "biblioteca": f"shapely {shapely.__version__} (GEOS)",
                        "aproximacao": "buffer plano no srid informado; quad_segs padrão da biblioteca",
                    },
                }, dumps=lambda v: json.dumps(v, ensure_ascii=False, default=str)),
            ]
            + (list(extent_4326) if extent_4326 else [])
            + (["dado"] if extent_4326 else [None])
            + [ctx.usuario_id, ctx.usuario_id],
        )
        cur.execute("SELECT plat.evento_registrar('ferramentas/buffer', 'item', %s, %s::jsonb, NULL, NULL)",
                    (item_id, json.dumps({"distancia_m": distancia_m, "srid": srid,
                                          "job_id": str(ctx.job_id), "sha256_entrada": sha_entrada})))
    return {"item_id": item_id, "buffer": buffer_geojson, "area_m2": buffer.area, "srid": srid}


def _extent_em_4326(forma, srid: int) -> tuple[float, float, float, float] | None:
    """Envelope (minx, miny, maxx, maxy) em 4326; falha de transformação devolve None (extent vazio é
    aceitável, coordenada torta não)."""
    try:
        t = pyproj.Transformer.from_crs(pyproj.CRS.from_user_input(srid), pyproj.CRS.from_epsg(4326),
                                        always_xy=True)
        minx, miny, maxx, maxy = forma.bounds
        x0, y0 = t.transform(minx, miny)
        x1, y1 = t.transform(maxx, maxy)
        return (x0, y0, x1, y1)
    except Exception:
        return None
