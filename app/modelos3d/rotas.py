"""Rotas dos modelos 3D (item L2-09-c-modelos-gltf-ifc-3dtiles).

Oito rotas, todas sob o inquilino da sessão (RLS em `plat.modelo3d` e `plat.modelo3d_elemento`):

* `POST /api/modelos` cria o modelo a partir de um arquivo JÁ enviado por `POST /api/arquivos` (o item
  L0-11 é quem sabe receber byte cru, com teto em streaming e varredura de conteúdo — repetir isso aqui
  seria uma segunda porta de entrada de arquivo, com um segundo conjunto de defesas para divergir) e
  enfileira a conversão.
* `GET /api/modelos`, `GET /api/modelos/{id}`, `DELETE /api/modelos/{id}` — a ficha.
* `GET /api/modelos/{id}/elementos` e `.../elementos/{guid}` — a tabela de elementos do IFC. É o outro
  lado do clique na tela: o nó do glTF carrega `extras.guid`, o navegador pergunta por aquele GUID.
* `GET /api/modelos/{id}/glb` — o glTF binário, entregue pela API (nunca uma URL do armazenamento).
* `GET /api/modelos/{id}/3dtiles/{caminho}` — a árvore OGC 3D Tiles. `tileset.json` e os `conteudo/N.glb`
  saem pelo MESMO caminho, com os conteúdos citados por URI RELATIVA dentro do tileset: é isso que faz
  um cliente externo (o ArcGIS Pro lê 3D Tiles por URL, DOC.md 22) consumir a árvore inteira a partir de
  um endereço só. A autenticação é a padrão da casa: sessão do navegador, ou `Authorization: Bearer` de
  token de serviço com escopo `catalogo:ler`. Consumo pelo Pro em si segue PENDENTE — depende da
  credencial do parceiro (decisão D20), e não se declara o que não foi medido.
"""

from __future__ import annotations

import json
import re

from fastapi import APIRouter, Body, Path, Query
from fastapi.responses import Response

from app import db, limites, objetos
from app.auth.sessao import Auth, autenticado
from app.erros import ErroAPI
from app.jobs import servico as jobs_servico
from app.jobs.contexto import sessao_de
from app.modelos3d import servico
from app.modelos3d.tarefas import CAMINHO_TILESET, CLASSE_GLB

router = APIRouter(tags=["modelos3d"])
X = {"x-auth": "S/T", "x-privilegio": "proprio"}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
CLASSE = re.compile(r"^[a-z0-9_]{1,40}$")
GUID = re.compile(r"^[A-Za-z0-9_$]{1,64}$")
UUID_TEXTO = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
TIPO_GLB = "model/gltf-binary"


def _id(modelo_id: str) -> str:
    if not UUID_TEXTO.match(modelo_id.lower()):
        raise ErroAPI(404, "nao_encontrado", "modelo 3D inexistente")
    return modelo_id.lower()


def _validar(corpo: dict) -> dict:
    erros = []
    nome = (corpo.get("nome") or "").strip()
    if not nome or len(nome) > limites.MODELO3D_NOME_MAX:
        erros.append({"campo": "nome", "erro": f"1 a {limites.MODELO3D_NOME_MAX} caracteres",
                      "regra": "tamanho"})
    origem = corpo.get("origem")
    if origem not in ("gltf", "ifc"):
        erros.append({"campo": "origem", "erro": "gltf ou ifc", "regra": "enumerado"})
    sha = (corpo.get("arquivo_sha256") or "").lower()
    if not SHA256.match(sha):
        erros.append({"campo": "arquivo_sha256", "erro": "64 caracteres hexadecimais", "regra": "formato"})
    classe = corpo.get("arquivo_classe") or "modelo3d"
    if not CLASSE.match(classe):
        erros.append({"campo": "arquivo_classe", "erro": "^[a-z0-9_]{1,40}$", "regra": "formato"})
    numeros = {"lon": (-180.0, 180.0), "lat": (-85.05, 85.05), "altura_m": (-1000.0, 10000.0),
               "rotacao_graus": (0.0, 360.0), "escala": (0.000001, 1000.0)}
    valores: dict = {}
    for campo, (minimo, maximo) in numeros.items():
        bruto = corpo.get(campo, {"altura_m": 0.0, "rotacao_graus": 0.0, "escala": 1.0}.get(campo))
        if bruto is None:
            erros.append({"campo": campo, "erro": "obrigatório", "regra": "obrigatorio"})
            continue
        try:
            valor = float(bruto)
        except (TypeError, ValueError):
            erros.append({"campo": campo, "erro": "número", "regra": "tipo"})
            continue
        if not (minimo <= valor <= maximo):
            erros.append({"campo": campo, "erro": f"entre {minimo} e {maximo}", "regra": "faixa"})
            continue
        valores[campo] = valor
    if erros:
        raise ErroAPI(422, "validacao", "corpo do modelo 3D inválido", erros)
    return {"nome": nome, "origem": origem, "arquivo_sha256": sha, "arquivo_classe": classe, **valores}


@router.get("/api/modelos", openapi_extra=X)
def listar(limite: int = Query(50, ge=1, le=limites.MODELO3D_PAGINA_MAX),
           deslocamento: int = Query(0, ge=0),
           auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Modelos 3D do inquilino, do mais recente para o mais antigo."""
    with db.db(auth.contexto()) as cur:
        return servico.listar(cur, limite, deslocamento)


@router.post("/api/modelos", status_code=201, openapi_extra=X)
def criar(corpo: dict = Body(...), auth: Auth = autenticado(escopo_token="catalogo:escrever")):
    """Cria o modelo e enfileira a conversão. O arquivo já tem de estar no inquilino (`POST /api/arquivos`)."""
    dados = _validar(corpo)
    gerar_tileset = bool(corpo.get("gerar_tileset"))
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT 1 FROM plat.arquivo WHERE classe = %s AND sha256 = %s AND referencia IS NULL "
                    "AND apagado_em IS NULL", (dados["arquivo_classe"], dados["arquivo_sha256"]))
        if cur.fetchone() is None:
            raise ErroAPI(404, "arquivo_nao_encontrado",
                          "nenhum arquivo deste inquilino com essa classe e esse sha256")
        cur.execute("SELECT 1 FROM plat.modelo3d WHERE lower(nome) = lower(%s)", (dados["nome"],))
        if cur.fetchone() is not None:
            raise ErroAPI(409, "nome_em_uso", "já existe um modelo 3D com esse nome neste inquilino")
        modelo = servico.criar(cur, auth.usuario_id, auth.tenant_id, dados)
        cur.execute("SELECT plat.evento_registrar('modelos3d/criar', 'modelo3d', %s, %s::jsonb, NULL, NULL)",
                    (modelo["id"], json.dumps({"nome": dados["nome"], "origem": dados["origem"],
                                               "lon": dados["lon"], "lat": dados["lat"]},
                                              ensure_ascii=False)))
    job = jobs_servico.criar(sessao_de(auth), "modelo3d.converter",
                             {"modelo_id": modelo["id"], "gerar_tileset": gerar_tileset})
    return {**modelo, "job_id": str(job["id"])}


@router.get("/api/modelos/{id}", openapi_extra=X)
def obter(id: str = Path(...), auth: Auth = autenticado(escopo_token="catalogo:ler")):
    with db.db(auth.contexto()) as cur:
        return servico.obter(cur, _id(id))


@router.delete("/api/modelos/{id}", openapi_extra=X)
def apagar(id: str = Path(...), auth: Auth = autenticado(escopo_token="catalogo:escrever")):
    """Apaga o modelo; os elementos saem em cascata pelo banco. Os objetos gravados (glTF e tileset) ficam
    para a varredura de órfãos do L0-11 — apagar objeto aqui duplicaria aquela responsabilidade."""
    mid = _id(id)
    with db.db(auth.contexto()) as cur:
        fora = servico.apagar(cur, mid)
        cur.execute("SELECT plat.evento_registrar('modelos3d/apagar', 'modelo3d', %s, %s::jsonb, NULL, NULL)",
                    (mid, json.dumps({"nome": fora["nome"]}, ensure_ascii=False)))
    return {"apagado": True, "id": mid}


@router.get("/api/modelos/{id}/elementos", openapi_extra=X)
def elementos(id: str = Path(...), tipo: str | None = Query(None, max_length=80),
              pavimento: str | None = Query(None, max_length=200),
              limite: int = Query(200, ge=1, le=limites.MODELO3D_ELEMENTOS_PAGINA_MAX),
              deslocamento: int = Query(0, ge=0),
              auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Elementos do modelo (um por linha do IFC), filtráveis por tipo e por pavimento."""
    mid = _id(id)
    with db.db(auth.contexto()) as cur:
        servico.obter(cur, mid)
        return servico.listar_elementos(cur, mid, tipo, pavimento, limite, deslocamento)


@router.get("/api/modelos/{id}/elementos/{guid}", openapi_extra=X)
def elemento(id: str = Path(...), guid: str = Path(..., max_length=64),
             auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Propriedades de um elemento pelo identificador global que o próprio arquivo IFC carrega."""
    mid = _id(id)
    if not GUID.match(guid):
        raise ErroAPI(404, "nao_encontrado", "elemento inexistente neste modelo")
    with db.db(auth.contexto()) as cur:
        servico.obter(cur, mid)
        return servico.obter_elemento(cur, mid, guid)


def _entregar(chave: str, tipo: str) -> Response:
    try:
        corpo = objetos.ler(chave)
    except (FileNotFoundError, objetos.ChaveInvalida) as e:
        raise ErroAPI(404, "nao_encontrado", "arquivo do modelo ausente no armazenamento") from e
    return Response(content=corpo, media_type=tipo,
                    headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"})


@router.get("/api/modelos/{id}/glb", openapi_extra=X)
def glb_do_modelo(id: str = Path(...), auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """glTF binário do modelo, entregue pela API (a chave do armazenamento nunca sai para o cliente)."""
    mid = _id(id)
    with db.db(auth.contexto()) as cur:
        modelo = servico.obter(cur, mid)
        if not modelo.get("glb_sha256"):
            raise ErroAPI(409, "sem_glb", f"o modelo ainda não foi convertido (estado: {modelo['estado']})")
        cur.execute("SELECT chave FROM plat.arquivo WHERE classe = %s AND sha256 = %s AND referencia = %s "
                    "AND apagado_em IS NULL ORDER BY criado_em DESC LIMIT 1",
                    (CLASSE_GLB, modelo["glb_sha256"], mid))
        linha = cur.fetchone()
    if linha is None:
        raise ErroAPI(404, "nao_encontrado", "glTF do modelo ausente no armazenamento")
    return _entregar(linha["chave"], TIPO_GLB)


@router.get("/api/modelos/{id}/3dtiles/{caminho:path}", openapi_extra=X)
def tres_d_tiles(id: str = Path(...), caminho: str = Path(..., max_length=64),
                 auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Árvore OGC 3D Tiles 1.1: `tileset.json` e `conteudo/N.glb`, por URI relativa a partir daqui."""
    mid = _id(id)
    if not CAMINHO_TILESET.match(caminho):
        raise ErroAPI(404, "nao_encontrado", "caminho fora da árvore do tileset")
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT tileset, tileset_arquivos FROM plat.modelo3d WHERE id = %s::uuid", (mid,))
        linha = cur.fetchone()
        if linha is None:
            raise ErroAPI(404, "nao_encontrado", "modelo 3D inexistente")
        if not linha["tileset"]:
            raise ErroAPI(409, "sem_tileset", "este modelo ainda não tem árvore 3D Tiles gerada")
        chave = (linha["tileset_arquivos"] or {}).get(caminho)
    if not chave:
        raise ErroAPI(404, "nao_encontrado", "arquivo inexistente nesta árvore")
    return _entregar(chave, "application/json" if caminho.endswith(".json") else TIPO_GLB)


def enfileirar_tileset(tenant_id: int, modelo_id: str, usuario_id: int | None = None) -> str:
    """Usada pela conversão e pelos testes: o tipo é `somente_sistema`, nunca sai por `POST /api/jobs`."""
    from app.jobs.sistema import enfileirar  # importação tardia (ciclo jobs.sistema -> jobs.tipos -> este)
    return enfileirar(tenant_id, "modelo3d.tileset", {"modelo_id": modelo_id}, usuario_id=usuario_id)


__all__ = ["router", "enfileirar_tileset"]
