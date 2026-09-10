"""Rotas /api/amc/presets (item L3-01-h-presets): CRUD por API, aplicação SÍNCRONA (recalcula sem
job), exportação e importação em JSON do motor multicritério. Ver `app/amc/presets.py` (módulo
puro: conteúdo validado, presets integrados, fatores faltando) e a migração
`20260908T1659_amc_preset.sql` (modelo de dado e RLS por inquilino).

Acesso: o privilégio `analise.amc` ("criar e executar modelo multicritério") cobre ler e escrever;
presets de escopo 'usuario' são visíveis SÓ ao dono (filtro na consulta — a RLS por si mostra a
linha do inquilino inteiro); 'inquilino' é de todo o inquilino. Só o dono edita ou apaga. Presets
integrados ('pesos iguais' + exemplos do motor logístico) são somente leitura e nunca recebem
PUT/DELETE."""

import numpy as np
import psycopg2
from fastapi import APIRouter, Request

from app import db, limites
from app.amc import presets as pres
from app.amc.combinacao import ErroCombinacao, combinar
from app.amc.modelos import (
    AplicacaoFeita,
    Preset,
    PresetAplicar,
    PresetEditar,
    PresetEntrada,
    PresetImportado,
    PresetImportar,
    PresetPagina,
)
from app.auth import comum as auth_comum
from app.auth.comum import paginacao, registrar_evento
from app.auth.sessao import Auth, autenticado, iso
from app.catalogo.comum import jsonb, uuid_ok
from app.erros import ErroAPI

router = APIRouter(prefix="/api/amc", tags=["amc"])
AMC = {"x-auth": "S/T", "x-privilegio": "analise.amc"}


def _erro_conteudo(e: pres.ErroConteudo) -> ErroAPI:
    return ErroAPI(422, e.codigo, e.mensagem, e.detalhe)


def _preset_json(r: dict) -> dict:
    return {
        "id": r["id"],
        "nome": r["nome"],
        "descricao": r["descricao"],
        "escopo": r["escopo"],
        "integrado": bool(r.get("integrado")),
        "conteudo": r["conteudo"],
        "dono_id": None if r.get("dono_id") is None else str(r["dono_id"]),
        "dono_login": r.get("dono_login"),
        "criado_em": iso(r.get("criado_em")),
        "atualizado_em": iso(r.get("atualizado_em")),
    }


SQL_BASE = (
    "SELECT p.id::text, p.nome, p.descricao, p.escopo, p.conteudo, p.dono_id, "
    "p.criado_em, p.atualizado_em, u.login AS dono_login "
    "FROM plat.amc_preset p JOIN plat.usuario u ON u.id = p.dono_id "
)


def _visiveis(auth: Auth) -> str:
    """Cláusula de visibilidade: 'usuario' é só do dono; 'inquilino' é de todos (a RLS já isola o
    inquilino)."""
    return "(p.escopo = 'inquilino' OR p.dono_id = %s)"


def _carregar(cur, auth: Auth, pid: str, *, dono_exigido: bool = False) -> dict:
    """Preset pelo identificador: slug integrado ou uuid de tabela. Preset de OUTRO usuário
    (escopo usuario) e preset de OUTRO inquilino são o mesmo 404 para o chamador."""
    integrado = pres.integrado_por_id(pid)
    if integrado is not None:
        if dono_exigido:
            raise ErroAPI(403, "integrado_somente_leitura",
                          "preset integrado é somente leitura; copie-o e edite a cópia")
        integrado["conteudo"] = pres.validar_conteudo(integrado["conteudo"])
        return integrado
    uid = uuid_ok(pid, "preset_inexistente", "preset inexistente")
    cur.execute(SQL_BASE + "WHERE p.id = %s::uuid AND " + _visiveis(auth), (uid, auth.usuario_id))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "preset_inexistente", "preset inexistente")
    if dono_exigido and r["dono_id"] != auth.usuario_id:
        raise ErroAPI(403, "preset_de_outro_dono", "só quem criou o preset pode alterá-lo")
    r["id"] = str(r["id"])
    r["integrado"] = False
    r["conteudo"] = pres.validar_conteudo(r["conteudo"])
    return r


@router.get("/presets", response_model=PresetPagina, openapi_extra=AMC)
def listar(limite: int | None = None, deslocamento: int | None = None,
           auth: Auth = autenticado(escopo_token="admin:inquilino", privilegio="analise.amc")):
    """Lista os presets visíveis: os INTEGRADOS primeiro (sempre existem), depois os do inquilino."""
    lim, desl = paginacao(limite, deslocamento)
    integrados = [pres.integrado_por_id(s) for s in sorted(pres.INTEGRADOS)]
    with db.db(auth.contexto()) as cur:
        cur.execute(f"SELECT count(*) AS n FROM plat.amc_preset p WHERE {_visiveis(auth)}",
                    (auth.usuario_id,))
        total = cur.fetchone()["n"] + len(integrados)
        cur.execute(
            SQL_BASE + f"WHERE {_visiveis(auth)} ORDER BY lower(p.nome) LIMIT %s OFFSET %s",
            (auth.usuario_id, lim, desl),
        )
        linhas = []
        for r in cur.fetchall():
            r["id"] = str(r["id"])
            r["integrado"] = False
            r["conteudo"] = pres.validar_conteudo(r["conteudo"])
            linhas.append(r)
    itens = [_preset_json(r) for r in integrados + linhas]
    return {"total": total, "itens": itens}


@router.post("/presets", response_model=Preset, status_code=201, openapi_extra=AMC)
def criar(corpo: PresetEntrada, request: Request,
          auth: Auth = autenticado(escopo_token="admin:inquilino", privilegio="analise.amc")):
    conteudo = _validado(corpo.conteudo)
    with db.db(auth.contexto()) as cur:
        try:
            cur.execute(
                "INSERT INTO plat.amc_preset(tenant_id, nome, descricao, escopo, conteudo, dono_id) "
                "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id::text",
                (auth.tenant_id, " ".join(corpo.nome.split()), corpo.descricao, corpo.escopo,
                 jsonb(conteudo), auth.usuario_id),
            )
        except psycopg2.errors.UniqueViolation as e:
            raise ErroAPI(409, "nome_existente", "já existe um preset com esse nome neste escopo") from e
        except psycopg2.Error as e:
            raise auth_comum.erro_do_banco(e) from e
        pid = cur.fetchone()["id"]
        registrar_evento(cur, request, "amc/preset", "amc_preset", pid,
                         {"nome": corpo.nome, "escopo": corpo.escopo,
                          "fatores": conteudo["fatores"], "pesos_iguais": conteudo["pesos_iguais"]})
        r = _carregar(cur, auth, pid)
    return _preset_json(r)


@router.post("/presets/importar", response_model=PresetImportado, status_code=201, openapi_extra=AMC)
def importar(corpo: PresetImportar, request: Request,
             auth: Auth = autenticado(escopo_token="admin:inquilino", privilegio="analise.amc")):
    """Importa o documento de exportação. Com `fatores_modelo` informado, preset que declara fator
    fora do modelo é recusado com a LISTA do que falta (refutação do item)."""
    documento = {"formato": corpo.formato, "versao": corpo.versao, "nome": corpo.nome,
                 "descricao": corpo.descricao, "escopo": corpo.escopo, "conteudo": corpo.conteudo,
                 "fatores_modelo": corpo.fatores_modelo}
    try:
        doc = pres.documento_validar(documento)
    except pres.ErroConteudo as e:
        raise _erro_conteudo(e) from e
    with db.db(auth.contexto()) as cur:
        try:
            cur.execute(
                "INSERT INTO plat.amc_preset(tenant_id, nome, descricao, escopo, conteudo, dono_id) "
                "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id::text",
                (auth.tenant_id, doc["nome"], doc["descricao"], doc["escopo"], jsonb(doc["conteudo"]),
                 auth.usuario_id),
            )
        except psycopg2.errors.UniqueViolation as e:
            raise ErroAPI(409, "nome_existente", "já existe um preset com esse nome neste escopo") from e
        except psycopg2.Error as e:
            raise auth_comum.erro_do_banco(e) from e
        pid = cur.fetchone()["id"]
        registrar_evento(cur, request, "amc/preset_importar", "amc_preset", pid,
                         {"nome": doc["nome"], "escopo": doc["escopo"],
                          "fatores": doc["conteudo"]["fatores"],
                          "pesos_iguais": doc["conteudo"]["pesos_iguais"]})
    return {"id": pid, "nome": doc["nome"], "escopo": doc["escopo"], "faltando": doc["faltando"]}


@router.get("/presets/{id}", response_model=Preset, openapi_extra=AMC)
def ver(id: str, auth: Auth = autenticado(escopo_token="admin:inquilino", privilegio="analise.amc")):
    with db.db(auth.contexto()) as cur:
        return _preset_json(_carregar(cur, auth, id))


@router.patch("/presets/{id}", response_model=Preset, openapi_extra=AMC)
def editar(id: str, corpo: PresetEditar, request: Request,
           auth: Auth = autenticado(escopo_token="admin:inquilino", privilegio="analise.amc")):
    with db.db(auth.contexto()) as cur:
        atual = _carregar(cur, auth, id, dono_exigido=True)
        nome = " ".join(corpo.nome.split()) if corpo.nome is not None else atual["nome"]
        descricao = corpo.descricao if corpo.descricao is not None else atual["descricao"]
        escopo = corpo.escopo if corpo.escopo is not None else atual["escopo"]
        conteudo = _validado(corpo.conteudo) if corpo.conteudo is not None else atual["conteudo"]
        try:
            cur.execute(
                "UPDATE plat.amc_preset SET nome = %s, descricao = %s, escopo = %s, conteudo = %s, "
                "atualizado_em = now() WHERE id = %s::uuid",
                (nome, descricao, escopo, jsonb(conteudo), atual["id"]),
            )
        except psycopg2.errors.UniqueViolation as e:
            raise ErroAPI(409, "nome_existente", "já existe um preset com esse nome neste escopo") from e
        except psycopg2.Error as e:
            raise auth_comum.erro_do_banco(e) from e
        registrar_evento(cur, request, "amc/preset_atualizar", "amc_preset", atual["id"],
                         {"nome": nome, "escopo": escopo, "fatores": conteudo["fatores"],
                          "pesos_iguais": conteudo["pesos_iguais"]})
        r = _carregar(cur, auth, atual["id"])
    return _preset_json(r)


@router.delete("/presets/{id}", status_code=204, openapi_extra=AMC)
def apagar(id: str, request: Request,
           auth: Auth = autenticado(escopo_token="admin:inquilino", privilegio="analise.amc")):
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, auth, id, dono_exigido=True)
        cur.execute("DELETE FROM plat.amc_preset WHERE id = %s::uuid", (r["id"],))
        registrar_evento(cur, request, "amc/preset_apagar", "amc_preset", r["id"], {"nome": r["nome"]})


@router.get("/presets/{id}/exportar", openapi_extra=AMC)
def exportar(id: str,
             auth: Auth = autenticado(escopo_token="admin:inquilino", privilegio="analise.amc")):
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, auth, id)
    return pres.documento_exportar(r)


@router.post("/presets/{id}/aplicar", response_model=AplicacaoFeita, openapi_extra=AMC)
def aplicar(id: str, corpo: PresetAplicar, request: Request,
            auth: Auth = autenticado(escopo_token="admin:inquilino", privilegio="analise.amc")):
    """Aplica o preset sobre a matriz enviada e devolve a nota recalculada NA HORA (nenhum job é
    criado; a rota nem toca em plat.job). Preset que declara fator fora da matriz é recusado com a
    lista do que falta."""
    ids = [str(f).strip() for f in corpo.ids_fatores]
    if len(set(ids)) != len(ids):
        raise ErroAPI(422, "fator_duplicado", "a matriz traz o mesmo fator mais de uma vez")
    if len(corpo.fatores) > limites.AMC_PRESET_UNIDADES_MAX:
        raise ErroAPI(422, "unidades_demais",
                      f"aplicação síncrona aceita até {limites.AMC_PRESET_UNIDADES_MAX} unidades; "
                      f"recebeu {len(corpo.fatores)}",
                      {"limite": limites.AMC_PRESET_UNIDADES_MAX, "recebido": len(corpo.fatores)})
    for linha in corpo.fatores:
        if len(linha) != len(ids):
            raise ErroAPI(422, "matriz_invalida",
                          f"cada linha da matriz precisa de {len(ids)} valores (um por fator)")
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, auth, id)
    conteudo = r["conteudo"]
    faltando = pres.fatores_faltando(conteudo, ids)
    if faltando:
        raise ErroAPI(422, "fator_fora_do_modelo",
                      "o preset declara fator que a matriz não traz: " + ", ".join(faltando),
                      {"faltando": faltando, "fatores_do_preset": conteudo["fatores"]})
    try:
        pesos = pres.pesos_da_matriz(conteudo, ids)
        m = _matriz(corpo.fatores)
        veto = pres.fracao_vetada_do_conteudo(conteudo, m, ids)
        saida = combinar(m, pesos, combinador=conteudo["combinador"],
                         politica_ausente=conteudo["politica_ausente"], gama=conteudo["gama"],
                         fracao_vetada=veto, ids_fatores=ids)
    except pres.ErroConteudo as e:
        raise _erro_conteudo(e) from e
    except ErroCombinacao as e:
        raise ErroAPI(422, e.codigo, e.mensagem, e.detalhe) from e
    with db.db(auth.contexto()) as cur:
        registrar_evento(cur, request, "amc/preset_aplicar", "amc_preset", r["id"],
                         {"nome": r["nome"], "unidades": m.shape[0], "fatores": ids,
                          "faltando": faltando})
    return {"preset_id": r["id"], "preset_nome": r["nome"],
            "pesos_iguais": bool(conteudo["pesos_iguais"]), "resultado": saida.como_dicionario()}


def _validado(conteudo: dict) -> dict:
    try:
        return pres.validar_conteudo(conteudo)
    except pres.ErroConteudo as e:
        raise _erro_conteudo(e) from e


def _matriz(linhas: list[list]):
    try:
        m = np.array(
            [[np.nan if v is None else v for v in linha] for linha in linhas], dtype=float
        )
    except (TypeError, ValueError) as e:
        raise ErroAPI(422, "matriz_invalida",
                      "a matriz precisa de números (ou null para sem dado) na escala 0-100") from e
    return m
