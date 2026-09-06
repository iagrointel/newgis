"""Rotas /api/amc (itens L3-01-a-modelo-dado e L3-01-b-unidades). Três recursos:

- MODELO (`/api/amc/modelos`): documento JSON validado contra `docs/esquemas/amc_modelo.v1.json` e versionado pelo
  sha256 do JSON canônico (A1). Editar cria versão nova e move a cabeça; versão nunca muda (gatilho na migração 044),
  então execução antiga continua apontando para a versão que rodou.
- CONJUNTO DE UNIDADES (`/api/amc/conjuntos`): grade hexagonal/quadrada em UTM SIRGAS 2000 da zona do centróide
  (A7) gerada como job `amc.gerar_unidades`, ou feições do usuário com o id preservado (síncrono). A ficha do
  conjunto declara CRS de trabalho e distorção de área máxima — a tela é outro item; aqui a API devolve a ficha.
- EXECUÇÃO (`/api/amc/execucoes`): congela versão do modelo, pesos, proveniência de cada camada de entrada, versão
  do motor e semente (A10). A extração dos fatores e a combinação são os itens L3-01-c/e; aqui a execução nasce no
  estado `registrada` e os resultados são lidos quando existirem.

Privilégio: `analise.amc` (já no vocabulário, `app/auth/privilegios.py`) para escrita; leitura aceita token com
escopo `catalogo:ler`. RLS por inquilino em toda tabela `plat.amc_*`; nenhuma rota recebe tenant_id do cliente."""

import json
import uuid

import psycopg2
import psycopg2.extras
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from app import db, limites
from app.amc import MOTOR_VERSAO
from app.amc import camadas as mod_camadas
from app.amc import esquema as mod_esquema
from app.amc import unidades as mod_unidades
from app.auth.comum import erro_do_banco, paginacao, registrar_evento
from app.auth.sessao import Auth, autenticado
from app.erros import ErroAPI
from app.jobs import servico as jobs_servico
from app.jobs.contexto import sessao_de
from app.versao import git_sha_curto
from app.versao import versao as versao_app

router = APIRouter(prefix="/api/amc", tags=["amc"])
LER = {"x-auth": "S/T", "x-privilegio": "analise.amc"}
ESCREVER = {"x-auth": "S/T", "x-privilegio": "analise.amc"}
SEMENTE_MAX = 2**63 - 1


def _motor_versao() -> str:
    """Versão do motor gravada na execução: motor + versão da aplicação + sha do commit (A10)."""
    return f"{MOTOR_VERSAO}+{versao_app()}+{git_sha_curto()}"


def _uuid(valor: str, campo: str) -> str:
    try:
        return str(uuid.UUID(str(valor)))
    except (ValueError, AttributeError, TypeError):
        raise ErroAPI(422, "validacao", f"{campo} não é um identificador válido", {"campo": campo}) from None


def _jsonb(valor):
    return psycopg2.extras.Json(valor)


# ================================================================ modelos
class ModeloEntrada(BaseModel):
    nome: str | None = Field(None, max_length=250)
    definicao: dict


class ValidarEntrada(BaseModel):
    definicao: dict


@router.post("/modelos/validar", openapi_extra=ESCREVER)
def validar_modelo(corpo: ValidarEntrada, auth: Auth = autenticado("analise.amc")):
    """Valida sem gravar: devolve o hash que o documento teria. Modelo inválido sai 422 com todas as violações."""
    mod_esquema.validar(corpo.definicao)
    return {"valido": True, "esquema": mod_esquema.ESQUEMA_NOME,
            "versao_hash": mod_esquema.hash_modelo(corpo.definicao),
            "fatores": len(corpo.definicao.get("fatores") or []),
            "restricoes": len(corpo.definicao.get("restricoes") or [])}


def _modelo_json(r: dict, definicao=None) -> dict:
    saida = {
        "id": str(r["id"]), "nome": r["nome"], "versao_hash": r["versao_hash"], "n_versoes": r["n_versoes"],
        "criado_em": r["criado_em"].isoformat(), "atualizado_em": r["atualizado_em"].isoformat(),
        "criado_por": r["criado_por"], "atualizado_por": r["atualizado_por"],
    }
    if definicao is not None:
        saida["definicao"] = definicao
    return saida


def _modelo_ou_404(cur, mid: str, com_definicao: bool = False) -> tuple[dict, dict | None]:
    cur.execute("SELECT * FROM plat.amc_modelo WHERE id = %s::uuid AND apagado_em IS NULL", (mid,))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "nao_encontrado", "modelo inexistente")
    definicao = None
    if com_definicao:
        cur.execute("SELECT definicao FROM plat.amc_modelo_versao WHERE modelo_id = %s::uuid AND versao_hash = %s",
                    (mid, r["versao_hash"]))
        definicao = (cur.fetchone() or {}).get("definicao")
    return r, definicao


@router.post("/modelos", status_code=201, openapi_extra=ESCREVER)
def criar_modelo(corpo: ModeloEntrada, request: Request, auth: Auth = autenticado("analise.amc")):
    definicao = mod_esquema.validar(corpo.definicao)
    versao_hash = mod_esquema.hash_modelo(definicao)
    nome = (corpo.nome or definicao["nome"]).strip()
    if not nome:
        raise ErroAPI(422, "validacao", "nome do modelo vazio", {"campo": "nome"})
    try:
        with db.db(auth.contexto()) as cur:
            cur.execute("SELECT count(*) AS n FROM plat.amc_modelo WHERE apagado_em IS NULL")
            if cur.fetchone()["n"] >= limites.AMC_MODELOS_POR_INQUILINO:
                raise ErroAPI(413, "cota_modelos",
                              f"cota de modelos do inquilino esgotada ({limites.AMC_MODELOS_POR_INQUILINO})",
                              {"cota": limites.AMC_MODELOS_POR_INQUILINO})
            mid = str(uuid.uuid4())
            cur.execute(
                "INSERT INTO plat.amc_modelo(id, tenant_id, nome, versao_hash, n_versoes, criado_por, atualizado_por) "
                "VALUES (%s::uuid, %s, %s, %s, 1, %s, %s)",
                (mid, auth.tenant_id, nome, versao_hash, auth.usuario_id, auth.usuario_id),
            )
            cur.execute(
                "INSERT INTO plat.amc_modelo_versao(modelo_id, versao_hash, tenant_id, numero, definicao, criado_por) "
                "VALUES (%s::uuid, %s, %s, 1, %s, %s)",
                (mid, versao_hash, auth.tenant_id, _jsonb(definicao), auth.usuario_id),
            )
            registrar_evento(cur, request, "amc/modelo_criar", "amc_modelo", mid,
                             {"versao_hash": versao_hash, "nome": nome[:250]})
            r, _ = _modelo_ou_404(cur, mid)
            return _modelo_json(r, definicao)
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e


@router.get("/modelos", openapi_extra=LER)
def listar_modelos(auth: Auth = autenticado("analise.amc", escopo_token="catalogo:ler"),
                   limite: int | None = Query(None), deslocamento: int | None = Query(None)):
    lim, desl = paginacao(limite, deslocamento)
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT count(*) AS n FROM plat.amc_modelo WHERE apagado_em IS NULL")
        total = cur.fetchone()["n"]
        cur.execute("SELECT * FROM plat.amc_modelo WHERE apagado_em IS NULL ORDER BY atualizado_em DESC "
                    "LIMIT %s OFFSET %s", (lim, desl))
        return {"total": total, "limite": lim, "deslocamento": desl,
                "modelos": [_modelo_json(r) for r in cur.fetchall()]}


@router.get("/modelos/{modelo_id}", openapi_extra=LER)
def obter_modelo(modelo_id: str, auth: Auth = autenticado("analise.amc", escopo_token="catalogo:ler")):
    mid = _uuid(modelo_id, "modelo_id")
    with db.db(auth.contexto()) as cur:
        r, definicao = _modelo_ou_404(cur, mid, com_definicao=True)
        return _modelo_json(r, definicao)


@router.put("/modelos/{modelo_id}", openapi_extra=ESCREVER)
def atualizar_modelo(modelo_id: str, corpo: ModeloEntrada, request: Request,
                     auth: Auth = autenticado("analise.amc")):
    """Edita: grava versão NOVA e move a cabeça. A versão anterior fica; execução que a usou não muda de resultado."""
    mid = _uuid(modelo_id, "modelo_id")
    definicao = mod_esquema.validar(corpo.definicao)
    novo_hash = mod_esquema.hash_modelo(definicao)
    try:
        with db.db(auth.contexto()) as cur:
            r, _ = _modelo_ou_404(cur, mid)
            nome = (corpo.nome or definicao["nome"]).strip() or r["nome"]
            anterior = r["versao_hash"]
            if novo_hash == anterior:
                if nome != r["nome"]:
                    cur.execute("UPDATE plat.amc_modelo SET nome = %s, atualizado_por = %s, atualizado_em = now() "
                                "WHERE id = %s::uuid", (nome, auth.usuario_id, mid))
                r, _ = _modelo_ou_404(cur, mid)
                return {**_modelo_json(r, definicao), "versao_nova": False}
            if r["n_versoes"] >= limites.AMC_VERSOES_POR_MODELO:
                raise ErroAPI(413, "cota_versoes",
                              f"o modelo já tem {r['n_versoes']} versões (máximo {limites.AMC_VERSOES_POR_MODELO})",
                              {"cota": limites.AMC_VERSOES_POR_MODELO})
            cur.execute("SELECT 1 FROM plat.amc_modelo_versao WHERE modelo_id = %s::uuid AND versao_hash = %s",
                        (mid, novo_hash))
            ja_existe = cur.fetchone() is not None
            numero = r["n_versoes"] + 1
            if not ja_existe:
                cur.execute(
                    "INSERT INTO plat.amc_modelo_versao(modelo_id, versao_hash, tenant_id, numero, definicao, "
                    "criado_por) VALUES (%s::uuid, %s, %s, %s, %s, %s)",
                    (mid, novo_hash, auth.tenant_id, numero, _jsonb(definicao), auth.usuario_id),
                )
            cur.execute(
                "UPDATE plat.amc_modelo SET nome = %s, versao_hash = %s, n_versoes = %s, atualizado_por = %s, "
                "atualizado_em = now() WHERE id = %s::uuid",
                (nome, novo_hash, numero if not ja_existe else r["n_versoes"], auth.usuario_id, mid),
            )
            registrar_evento(cur, request, "amc/modelo_atualizar", "amc_modelo", mid,
                             {"versao_hash": novo_hash, "versao_anterior": anterior})
            r, _ = _modelo_ou_404(cur, mid)
            return {**_modelo_json(r, definicao), "versao_nova": not ja_existe}
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e


@router.get("/modelos/{modelo_id}/versoes", openapi_extra=LER)
def listar_versoes(modelo_id: str, auth: Auth = autenticado("analise.amc", escopo_token="catalogo:ler")):
    mid = _uuid(modelo_id, "modelo_id")
    with db.db(auth.contexto()) as cur:
        r, _ = _modelo_ou_404(cur, mid)
        cur.execute("SELECT versao_hash, numero, criado_por, criado_em FROM plat.amc_modelo_versao "
                    "WHERE modelo_id = %s::uuid ORDER BY numero", (mid,))
        return {"modelo_id": mid, "versao_atual": r["versao_hash"],
                "versoes": [{"versao_hash": v["versao_hash"], "numero": v["numero"], "criado_por": v["criado_por"],
                             "criado_em": v["criado_em"].isoformat(), "atual": v["versao_hash"] == r["versao_hash"]}
                            for v in cur.fetchall()]}


@router.get("/modelos/{modelo_id}/versoes/{versao_hash}", openapi_extra=LER)
def obter_versao(modelo_id: str, versao_hash: str,
                 auth: Auth = autenticado("analise.amc", escopo_token="catalogo:ler")):
    mid = _uuid(modelo_id, "modelo_id")
    with db.db(auth.contexto()) as cur:
        _modelo_ou_404(cur, mid)
        cur.execute("SELECT versao_hash, numero, definicao, criado_em, criado_por FROM plat.amc_modelo_versao "
                    "WHERE modelo_id = %s::uuid AND versao_hash = %s", (mid, versao_hash))
        v = cur.fetchone()
        if v is None:
            raise ErroAPI(404, "nao_encontrado", "versão de modelo inexistente")
        return {"modelo_id": mid, "versao_hash": v["versao_hash"], "numero": v["numero"],
                "criado_em": v["criado_em"].isoformat(), "criado_por": v["criado_por"], "definicao": v["definicao"]}


@router.delete("/modelos/{modelo_id}", status_code=204, openapi_extra=ESCREVER)
def apagar_modelo(modelo_id: str, request: Request, auth: Auth = autenticado("analise.amc")):
    """Esconde o modelo (apagado_em). Versões e execuções ficam: são a proveniência do que já rodou."""
    mid = _uuid(modelo_id, "modelo_id")
    try:
        with db.db(auth.contexto()) as cur:
            _modelo_ou_404(cur, mid)
            cur.execute("UPDATE plat.amc_modelo SET apagado_em = now(), atualizado_por = %s, atualizado_em = now() "
                        "WHERE id = %s::uuid", (auth.usuario_id, mid))
            registrar_evento(cur, request, "amc/modelo_apagar", "amc_modelo", mid, {})
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e
    return None


# ================================================================ conjuntos de unidades (L3-01-b)
class ConjuntoEntrada(BaseModel):
    nome: str = Field(..., min_length=1, max_length=250)
    tipo: str = Field(..., description="hexagonal, quadrada ou feicoes")
    lado_m: float | None = None
    area_estudo: dict | None = Field(None, description="Polygon/MultiPolygon GeoJSON em EPSG:4326 (grade)")
    feicoes: dict | None = Field(None, description="FeatureCollection GeoJSON em EPSG:4326 (tipo 'feicoes')")
    campo_id: str | None = Field(None, max_length=128,
                                 description="propriedade que carrega o id da unidade; sem ela, usa feature.id")


def _conjunto_json(r: dict) -> dict:
    return {
        "id": str(r["id"]), "nome": r["nome"], "tipo": r["tipo"], "lado_m": r["lado_m"],
        "srid_trabalho": r["srid_trabalho"], "estado": r["estado"], "job_id": str(r["job_id"]) if r["job_id"] else None,
        "n_unidades": r["n_unidades"], "area_total_m2": r["area_total_m2"], "ficha": r["ficha"], "erro": r["erro"],
        "criado_em": r["criado_em"].isoformat(), "criado_por": r["criado_por"],
        "pronto_em": r["pronto_em"].isoformat() if r["pronto_em"] else None,
    }


def _conjunto_ou_404(cur, cid: str) -> dict:
    cur.execute("SELECT * FROM plat.amc_conjunto_unidade WHERE id = %s::uuid", (cid,))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "nao_encontrado", "conjunto de unidades inexistente")
    return r


@router.post("/conjuntos", status_code=201, openapi_extra=ESCREVER)
def criar_conjunto(corpo: ConjuntoEntrada, request: Request, auth: Auth = autenticado("analise.amc")):
    """Grade: grava o conjunto e enfileira `amc.gerar_unidades` (estado 'pendente'). Feições: grava e responde
    'pronto' na mesma chamada. A ficha traz sempre CRS de trabalho e distorção de área medida."""
    if corpo.tipo not in ("hexagonal", "quadrada", "feicoes"):
        raise ErroAPI(422, "tipo_invalido", "tipo tem de ser hexagonal, quadrada ou feicoes", {"campo": "tipo"})
    try:
        with db.db(auth.contexto()) as cur:
            cur.execute("SELECT count(*) AS n FROM plat.amc_conjunto_unidade")
            if cur.fetchone()["n"] >= limites.AMC_CONJUNTOS_POR_INQUILINO:
                raise ErroAPI(413, "cota_conjuntos",
                              f"cota de conjuntos do inquilino esgotada ({limites.AMC_CONJUNTOS_POR_INQUILINO})",
                              {"cota": limites.AMC_CONJUNTOS_POR_INQUILINO})
            cid = str(uuid.uuid4())
            if corpo.tipo == "feicoes":
                if corpo.feicoes is None:
                    raise ErroAPI(422, "feicoes_invalidas", "conjunto do tipo 'feicoes' exige $.feicoes "
                                  "(FeatureCollection)", {"campo": "feicoes"})
                try:
                    lista = mod_unidades.validar_feicoes(corpo.feicoes, corpo.campo_id)
                except mod_unidades.ErroValidacao as e:
                    raise e.api() from e
                cur.execute(
                    "INSERT INTO plat.amc_conjunto_unidade(id, tenant_id, nome, tipo, srid_trabalho, estado, "
                    "criado_por) VALUES (%s::uuid, %s, %s, 'feicoes', 4326, 'pendente', %s)",
                    (cid, auth.tenant_id, corpo.nome.strip(), auth.usuario_id),
                )
                try:
                    mod_unidades.gravar_feicoes(cur, cid, auth.tenant_id, lista)
                except mod_unidades.ErroValidacao as e:
                    raise e.api() from e
                registrar_evento(cur, request, "amc/conjunto_criar", "amc_conjunto_unidade", cid,
                                 {"tipo": "feicoes", "n_unidades": len(lista)})
                return _conjunto_json(_conjunto_ou_404(cur, cid))
            if corpo.lado_m is None or corpo.area_estudo is None:
                raise ErroAPI(422, "validacao", "grade exige lado_m e area_estudo (Polygon/MultiPolygon em 4326)",
                              {"campos": ["lado_m", "area_estudo"]})
            try:
                preparo = mod_unidades.preparar_grade(cur, corpo.tipo, float(corpo.lado_m), corpo.area_estudo)
            except mod_unidades.ErroValidacao as e:
                raise e.api() from e
            ficha = dict(preparo["ficha_crs"])
            ficha.update({"tipo": corpo.tipo, "lado_m": float(corpo.lado_m),
                          "contagem_esperada": round(preparo["contagem_esperada"], 2),
                          "area_estudo_geodesica_m2": round(preparo["area_geodesica_m2"], 3),
                          "area_estudo_plano_m2": round(preparo["area_plano_m2"], 3)})
            cur.execute(
                "INSERT INTO plat.amc_conjunto_unidade(id, tenant_id, nome, tipo, lado_m, srid_trabalho, area_estudo, "
                "estado, ficha, criado_por) VALUES (%s::uuid, %s, %s, %s, %s, %s, "
                "ST_Multi(ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))), 'pendente', %s, %s)",
                (cid, auth.tenant_id, corpo.nome.strip(), corpo.tipo, float(corpo.lado_m),
                 ficha["srid_trabalho"], json.dumps(corpo.area_estudo), _jsonb(ficha), auth.usuario_id),
            )
            registrar_evento(cur, request, "amc/conjunto_criar", "amc_conjunto_unidade", cid,
                             {"tipo": corpo.tipo, "lado_m": float(corpo.lado_m),
                              "srid_trabalho": ficha["srid_trabalho"]})
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e
    job = jobs_servico.criar(sessao_de(auth), "amc.gerar_unidades", {"conjunto_id": cid})
    try:
        with db.db(auth.contexto()) as cur:
            cur.execute("UPDATE plat.amc_conjunto_unidade SET job_id = %s::uuid WHERE id = %s::uuid",
                        (str(job["id"]), cid))
            return _conjunto_json(_conjunto_ou_404(cur, cid))
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e


@router.get("/conjuntos", openapi_extra=LER)
def listar_conjuntos(auth: Auth = autenticado("analise.amc", escopo_token="catalogo:ler"),
                     limite: int | None = Query(None), deslocamento: int | None = Query(None)):
    lim, desl = paginacao(limite, deslocamento)
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT count(*) AS n FROM plat.amc_conjunto_unidade")
        total = cur.fetchone()["n"]
        cur.execute("SELECT * FROM plat.amc_conjunto_unidade ORDER BY criado_em DESC LIMIT %s OFFSET %s", (lim, desl))
        return {"total": total, "limite": lim, "deslocamento": desl,
                "conjuntos": [_conjunto_json(r) for r in cur.fetchall()]}


@router.get("/conjuntos/{conjunto_id}", openapi_extra=LER)
def obter_conjunto(conjunto_id: str, auth: Auth = autenticado("analise.amc", escopo_token="catalogo:ler")):
    """Ficha do conjunto: CRS de trabalho, distorção de área mínima/máxima medida, contagem esperada × obtida."""
    cid = _uuid(conjunto_id, "conjunto_id")
    with db.db(auth.contexto()) as cur:
        return _conjunto_json(_conjunto_ou_404(cur, cid))


@router.get("/conjuntos/{conjunto_id}/unidades", openapi_extra=LER)
def listar_unidades(conjunto_id: str, auth: Auth = autenticado("analise.amc", escopo_token="catalogo:ler"),
                    limite: int = Query(1000, ge=1, le=limites.AMC_UNIDADES_PAGINA_MAX),
                    deslocamento: int = Query(0, ge=0), geometria: bool = Query(True)):
    """FeatureCollection paginada (ou só os ids e áreas com geometria=false)."""
    cid = _uuid(conjunto_id, "conjunto_id")
    with db.db(auth.contexto()) as cur:
        r = _conjunto_ou_404(cur, cid)
        cur.execute("SELECT count(*) AS n FROM plat.amc_unidade WHERE conjunto_id = %s::uuid", (cid,))
        total = cur.fetchone()["n"]
        if geometria:
            cur.execute("SELECT unidade_id, area_m2, ST_AsGeoJSON(geom)::json AS g FROM plat.amc_unidade "
                        "WHERE conjunto_id = %s::uuid ORDER BY unidade_id LIMIT %s OFFSET %s", (cid, limite,
                                                                                                deslocamento))
            feicoes = [{"type": "Feature", "id": u["unidade_id"], "geometry": u["g"],
                        "properties": {"unidade_id": u["unidade_id"], "area_m2": u["area_m2"]}}
                       for u in cur.fetchall()]
        else:
            cur.execute("SELECT unidade_id, area_m2 FROM plat.amc_unidade WHERE conjunto_id = %s::uuid "
                        "ORDER BY unidade_id LIMIT %s OFFSET %s", (cid, limite, deslocamento))
            feicoes = [{"type": "Feature", "id": u["unidade_id"], "geometry": None,
                        "properties": {"unidade_id": u["unidade_id"], "area_m2": u["area_m2"]}}
                       for u in cur.fetchall()]
        return {"type": "FeatureCollection", "total": total, "limite": limite, "deslocamento": deslocamento,
                "srid_trabalho": r["srid_trabalho"], "crs_saida": 4326, "features": feicoes}


@router.delete("/conjuntos/{conjunto_id}", status_code=204, openapi_extra=ESCREVER)
def apagar_conjunto(conjunto_id: str, request: Request, auth: Auth = autenticado("analise.amc")):
    """Apaga o conjunto e as suas unidades. Conjunto usado por execução é recusado (FK RESTRICT → 409)."""
    cid = _uuid(conjunto_id, "conjunto_id")
    try:
        with db.db(auth.contexto()) as cur:
            _conjunto_ou_404(cur, cid)
            cur.execute("SELECT count(*) AS n FROM plat.amc_execucao WHERE conjunto_id = %s::uuid", (cid,))
            if cur.fetchone()["n"]:
                raise ErroAPI(409, "em_uso", "o conjunto é entrada de uma execução e não se apaga")
            cur.execute("DELETE FROM plat.amc_conjunto_unidade WHERE id = %s::uuid", (cid,))
            registrar_evento(cur, request, "amc/conjunto_apagar", "amc_conjunto_unidade", cid, {})
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e
    return None


# ================================================================ execuções (proveniência congelada)
class ExecucaoEntrada(BaseModel):
    modelo_id: str
    conjunto_id: str
    pesos: dict | None = Field(None, description="{fator_id: peso}; sem isto, os pesos do modelo")
    semente: int | None = Field(None, ge=0, le=SEMENTE_MAX)


def _execucao_json(r: dict) -> dict:
    return {
        "id": str(r["id"]), "modelo_id": str(r["modelo_id"]), "versao_hash": r["versao_hash"],
        "conjunto_id": str(r["conjunto_id"]), "pesos": r["pesos"], "camadas": r["camadas"],
        "motor_versao": r["motor_versao"], "semente": r["semente"], "estado": r["estado"],
        "job_id": str(r["job_id"]) if r["job_id"] else None, "erro": r["erro"],
        "criado_em": r["criado_em"].isoformat(), "criado_por": r["criado_por"],
        "iniciado_em": r["iniciado_em"].isoformat() if r["iniciado_em"] else None,
        "terminado_em": r["terminado_em"].isoformat() if r["terminado_em"] else None,
    }


def _execucao_ou_404(cur, eid: str) -> dict:
    cur.execute("SELECT * FROM plat.amc_execucao WHERE id = %s::uuid", (eid,))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "nao_encontrado", "execução inexistente")
    return r


@router.post("/execucoes", status_code=201, openapi_extra=ESCREVER)
def criar_execucao(corpo: ExecucaoEntrada, request: Request, auth: Auth = autenticado("analise.amc")):
    """Congela a proveniência (A10): versão do modelo, pesos, ficha de cada camada de entrada, versão do motor e
    semente. Nada disso muda depois (gatilho `amc_execucao_guarda`). A extração é o item L3-01-c."""
    mid = _uuid(corpo.modelo_id, "modelo_id")
    cid = _uuid(corpo.conjunto_id, "conjunto_id")
    semente = corpo.semente if corpo.semente is not None else int.from_bytes(uuid.uuid4().bytes[:7], "big")
    try:
        with db.db(auth.contexto()) as cur:
            r, definicao = _modelo_ou_404(cur, mid, com_definicao=True)
            conjunto = _conjunto_ou_404(cur, cid)
            if conjunto["estado"] != "pronto":
                raise ErroAPI(409, "conjunto_nao_pronto",
                              f"o conjunto de unidades está em '{conjunto['estado']}'; espere a grade ficar pronta",
                              {"estado": conjunto["estado"], "job_id": str(conjunto["job_id"] or "")})
            pesos = mod_esquema.validar_pesos(definicao, corpo.pesos)
            entradas = mod_camadas.resolver(cur, definicao)
            eid = str(uuid.uuid4())
            cur.execute(
                "INSERT INTO plat.amc_execucao(id, tenant_id, modelo_id, versao_hash, conjunto_id, pesos, camadas, "
                "motor_versao, semente, estado, criado_por) "
                "VALUES (%s::uuid, %s, %s::uuid, %s, %s::uuid, %s, %s, %s, %s, 'registrada', %s)",
                (eid, auth.tenant_id, mid, r["versao_hash"], cid, _jsonb(pesos), _jsonb(entradas),
                 _motor_versao(), semente, auth.usuario_id),
            )
            registrar_evento(cur, request, "amc/execucao_criar", "amc_execucao", eid,
                             {"modelo_id": mid, "versao_hash": r["versao_hash"], "conjunto_id": cid,
                              "camadas": len(entradas)})
            return _execucao_json(_execucao_ou_404(cur, eid))
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e


@router.get("/execucoes", openapi_extra=LER)
def listar_execucoes(auth: Auth = autenticado("analise.amc", escopo_token="catalogo:ler"),
                     modelo_id: str | None = None, limite: int | None = Query(None),
                     deslocamento: int | None = Query(None)):
    lim, desl = paginacao(limite, deslocamento)
    filtro, params = "", []
    if modelo_id:
        filtro, params = "WHERE modelo_id = %s::uuid", [_uuid(modelo_id, "modelo_id")]
    with db.db(auth.contexto()) as cur:
        cur.execute(f"SELECT count(*) AS n FROM plat.amc_execucao {filtro}", params)
        total = cur.fetchone()["n"]
        cur.execute(f"SELECT * FROM plat.amc_execucao {filtro} ORDER BY criado_em DESC LIMIT %s OFFSET %s",
                    [*params, lim, desl])
        return {"total": total, "limite": lim, "deslocamento": desl,
                "execucoes": [_execucao_json(r) for r in cur.fetchall()]}


@router.get("/execucoes/{execucao_id}", openapi_extra=LER)
def obter_execucao(execucao_id: str, auth: Auth = autenticado("analise.amc", escopo_token="catalogo:ler")):
    eid = _uuid(execucao_id, "execucao_id")
    with db.db(auth.contexto()) as cur:
        r = _execucao_ou_404(cur, eid)
        cur.execute("SELECT definicao FROM plat.amc_modelo_versao WHERE modelo_id = %s AND versao_hash = %s",
                    (r["modelo_id"], r["versao_hash"]))
        v = cur.fetchone()
        return {**_execucao_json(r), "definicao": (v or {}).get("definicao")}


@router.get("/execucoes/{execucao_id}/resultados", openapi_extra=LER)
def listar_resultados(execucao_id: str, auth: Auth = autenticado("analise.amc", escopo_token="catalogo:ler"),
                      limite: int = Query(1000, ge=1, le=limites.AMC_RESULTADOS_PAGINA_MAX),
                      deslocamento: int = Query(0, ge=0)):
    """Favorabilidade por unidade. Execução sem resultado ainda devolve lista vazia com o estado — nunca zero."""
    eid = _uuid(execucao_id, "execucao_id")
    with db.db(auth.contexto()) as cur:
        r = _execucao_ou_404(cur, eid)
        cur.execute("SELECT count(*) AS n FROM plat.amc_resultado WHERE execucao_id = %s::uuid", (eid,))
        total = cur.fetchone()["n"]
        cur.execute("SELECT unidade_id, favorabilidade, vetado, motivo, cobertura FROM plat.amc_resultado "
                    "WHERE execucao_id = %s::uuid ORDER BY unidade_id LIMIT %s OFFSET %s", (eid, limite, deslocamento))
        return {"execucao_id": eid, "estado": r["estado"], "escala": "favorabilidade 0-100 (NULL = sem dado)",
                "total": total, "limite": limite, "deslocamento": deslocamento,
                "resultados": [dict(x) for x in cur.fetchall()]}


@router.delete("/execucoes/{execucao_id}", status_code=204, openapi_extra=ESCREVER)
def apagar_execucao(execucao_id: str, request: Request, auth: Auth = autenticado("analise.amc")):
    """Só execução NÃO concluída se apaga (o gatilho do banco é quem manda; aqui a mensagem é em português)."""
    eid = _uuid(execucao_id, "execucao_id")
    try:
        with db.db(auth.contexto()) as cur:
            r = _execucao_ou_404(cur, eid)
            if r["estado"] == "concluida":
                raise ErroAPI(409, "execucao_concluida_imutavel",
                              "execução concluída não se apaga: os resultados são o que se audita")
            cur.execute("DELETE FROM plat.amc_execucao WHERE id = %s::uuid", (eid,))
            registrar_evento(cur, request, "amc/execucao_apagar", "amc_execucao", eid, {"estado": r["estado"]})
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e
    return None
