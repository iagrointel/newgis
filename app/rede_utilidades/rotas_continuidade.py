"""Rotas da continuidade DEC/FEC (item L4-10-continuidade-dec-fec).

Tudo pendurado na rede, porque a chave da junção (CONJ) é da rede:

* `GET  /api/rede/{rede_id}/continuidade/conjuntos`     — a ficha do conjunto, ano a ano;
* `GET  /api/rede/{rede_id}/continuidade/alimentadores` — o mesmo número levado ao alimentador;
* `GET  /api/rede/{rede_id}/continuidade/dic-fic`       — DIC e FIC médios por transformador (da BDGD);
* `GET  /api/rede/{rede_id}/continuidade/painel`        — a série por ano que o painel desenha;
* `POST /api/rede/{rede_id}/continuidade/importar`      — importa o dado aberto da ANEEL (síncrono no
  threadpool quando a faixa é curta; o job `rede.importar_continuidade` é o caminho para faixa longa);
* `DELETE /api/rede/{rede_id}/continuidade`             — apaga a continuidade dos conjuntos desta rede.

Escrita exige `rede.editar`; leitura segue a visibilidade por inquilino (RLS), como o resto da linha L4.

⛔ Nenhuma resposta desta rota classifica infração. A comparação com o limite devolve, em `situacao`,
"dentro do limite" ou "acima do limite regulatório", sempre com `apurado` e `limite` ao lado.
"""

import csv
import io
import uuid as uuid_mod

import psycopg2
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from app import db
from app.auth import comum as auth_comum
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import registrar_evento
from app.erros import ErroAPI
from app.jobs.registro import FalhaDefinitiva
from app.rede_utilidades import continuidade, tarefas_continuidade

router = APIRouter(prefix="/api/rede", tags=["rede de utilidades — continuidade DEC/FEC"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
EDITAR = {"x-auth": "S/T", "x-privilegio": "rede.editar"}

ANO_MIN = 1990
ANO_MAX = 2100
# faixa que o painel abre por padrão (item: "painel com série 2020-2025")
ANO_PADRAO_DE = 2020
ANO_PADRAO_ATE = 2025
FAIXA_MAX_ANOS = 30


class ImportarEntrada(BaseModel):
    # título único no OpenAPI: colidia com app.dominios.modelos.ImportarEntrada e impedia gerar o SDK
    model_config = ConfigDict(title="ImportarEntradaContinuidade")

    ano_de: int = Field(default=ANO_PADRAO_DE, ge=ANO_MIN, le=ANO_MAX)
    ano_ate: int = Field(default=ANO_PADRAO_ATE, ge=ANO_MIN, le=ANO_MAX)
    caminho: str | None = Field(default=None, max_length=1024,
                                description="subpasta dentro de PLAT_ANEEL_CONTINUIDADE_RAIZ")


def _uuid_ok(valor: str) -> str:
    try:
        return str(uuid_mod.UUID(valor))
    except (ValueError, AttributeError, TypeError) as e:
        raise ErroAPI(404, "rede_inexistente", "rede inexistente") from e


def _rede_existe(cur, rede_id: str) -> None:
    cur.execute("SELECT 1 FROM plat.rede WHERE id = %s::uuid", (rede_id,))
    if cur.fetchone() is None:
        raise ErroAPI(404, "rede_inexistente", "rede inexistente")


def _faixa(ano_de: int, ano_ate: int) -> tuple[int, int]:
    if not (ANO_MIN <= ano_de <= ANO_MAX) or not (ANO_MIN <= ano_ate <= ANO_MAX):
        raise ErroAPI(422, "ano_invalido", f"ano fora da faixa aceita ({ANO_MIN}-{ANO_MAX})")
    if ano_ate < ano_de:
        raise ErroAPI(422, "faixa_invertida", "ano_ate menor que ano_de")
    if ano_ate - ano_de + 1 > FAIXA_MAX_ANOS:
        raise ErroAPI(422, "faixa_larga", f"a faixa não pode passar de {FAIXA_MAX_ANOS} anos")
    return ano_de, ano_ate


@router.get("/{rede_id}/continuidade/conjuntos", openapi_extra=LER)
def conjuntos(rede_id: str, ano_de: int = ANO_PADRAO_DE, ano_ate: int = ANO_PADRAO_ATE,
              auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """A ficha de cada conjunto declarado pela rede: DEC e FEC apurados no ano, o limite daquele ano com o
    arquivo de onde veio e a situação.

    Conjunto que a rede declara e o arquivo da ANEEL não tem sai com `apurado` nulo e `situacao` igual a
    "sem dado" — nunca zero."""
    de, ate = _faixa(ano_de, ano_ate)
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        itens = continuidade.ficha_conjuntos(cur, rid, de, ate)
    return {"ano_de": de, "ano_ate": ate, "total": len(itens), "itens": itens}


@router.get("/{rede_id}/continuidade/alimentadores", openapi_extra=LER)
def alimentadores(rede_id: str, ano: int = ANO_PADRAO_ATE,
                  auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """O indicador do conjunto levado ao alimentador, ponderado pelas unidades consumidoras que cada
    conjunto tem naquele alimentador. `uc_sem_dado` diz quantas ficaram de fora da média."""
    ano, _ = _faixa(ano, ano)
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        itens = continuidade.ficha_alimentadores(cur, rid, ano)
    return {"ano": ano, "total": len(itens), "itens": itens,
            "metodo": "média por unidade consumidora dos conjuntos presentes no alimentador; o "
                      "alimentador não tem indicador próprio publicado pela agência"}


@router.get("/{rede_id}/continuidade/dic-fic", openapi_extra=LER)
def dic_fic(rede_id: str, limite: int = 1000, formato: str = "json",
            auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """DIC e FIC médios por transformador, calculados sobre as unidades consumidoras da própria BDGD.
    `formato=csv` devolve a mesma tabela como arquivo."""
    if formato not in ("json", "csv"):
        raise ErroAPI(422, "formato_invalido", "formato só pode ser json ou csv")
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        itens = continuidade.dic_fic_por_trafo(cur, rid, limite)
    if formato == "csv":
        saida = io.StringIO()
        w = csv.writer(saida, lineterminator="\n")
        w.writerow(["trafo", "alimentador", "conjunto_id", "n_uc", "n_uc_com_dic", "dic_medio",
                    "n_uc_com_fic", "fic_medio"])
        for it in itens:
            w.writerow([it["trafo"], it["alimentador"] or "", it["conjunto_id"] or "", it["n_uc"],
                        it["n_uc_com_dic"], "" if it["dic_medio"] is None else it["dic_medio"],
                        it["n_uc_com_fic"], "" if it["fic_medio"] is None else it["fic_medio"]])
        return Response(
            content=saida.getvalue().encode("utf-8"),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="dic-fic-por-trafo.csv"',
                     "Cache-Control": "no-store"},
        )
    return {"total": len(itens), "itens": itens,
            "origem": "DIC e FIC por unidade consumidora declarados na BDGD (camada UCBT), não o "
                      "indicador coletivo da ANEEL"}


@router.get("/{rede_id}/continuidade/painel", openapi_extra=LER)
def painel(rede_id: str, ano_de: int = ANO_PADRAO_DE, ano_ate: int = ANO_PADRAO_ATE,
           auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """A série por ano de cada conjunto (apurado, limite e situação), com a base normativa do limite."""
    de, ate = _faixa(ano_de, ano_ate)
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        return continuidade.painel(cur, rid, de, ate)


def _importar_sincrono(rid: str, corpo: ImportarEntrada, auth: Auth, request: Request) -> dict:
    with db.db(auth.contexto()) as cur:
        # a rede vem ANTES da configuração de propósito: quem não enxerga a rede recebe 404 e não descobre
        # se esta instalação tem ou não o dado aberto da ANEEL em disco
        _rede_existe(cur, rid)
        try:
            pasta = tarefas_continuidade.resolver_caminho(corpo.caminho)
        except FalhaDefinitiva as e:
            raise ErroAPI(422, "continuidade_indisponivel", str(e)) from e
        conjuntos_rede = continuidade.conjuntos_da_rede(cur, rid)
        if not conjuntos_rede:
            raise ErroAPI(422, "rede_sem_conjunto",
                          "a rede não declara nenhum conjunto de unidades consumidoras (campo CONJ)")
        try:
            resultado = continuidade.importar(cur, auth.tenant_id, pasta, conjuntos_rede,
                                              corpo.ano_de, corpo.ano_ate)
        except continuidade.ErroContinuidade as e:
            raise ErroAPI(422, "continuidade_indisponivel", str(e)) from e
        except psycopg2.Error as e:
            raise auth_comum.erro_do_banco(e) from e
        registrar_evento(cur, request, "redes/continuidade_importar", "rede", rid,
                         {"conjuntos": len(resultado["conjuntos"]),
                          "linhas_arquivo": resultado["linhas_arquivo"],
                          "linhas_gravadas": resultado["linhas_gravadas"],
                          "conferido": resultado["conferido"]})
    return resultado


@router.post("/{rede_id}/continuidade/importar", openapi_extra=EDITAR)
async def importar(rede_id: str, corpo: ImportarEntrada, request: Request,
                   auth: Auth = autenticado("rede.editar")):
    """Importa o dado aberto de continuidade da ANEEL para os conjuntos que esta rede declara.

    A leitura de arquivo e a carga vão para o threadpool, para não segurar o laço de eventos. A resposta
    traz, por arquivo, quantas linhas o arquivo tinha no recorte e quantas foram gravadas: é a
    conferência de contagem, e ela também fica gravada em `plat.rede_continuidade_fonte`."""
    _faixa(corpo.ano_de, corpo.ano_ate)
    rid = _uuid_ok(rede_id)
    return await run_in_threadpool(_importar_sincrono, rid, corpo, auth, request)


@router.delete("/{rede_id}/continuidade", status_code=204, openapi_extra=EDITAR)
def apagar(rede_id: str, request: Request, auth: Auth = autenticado("rede.editar")):
    """Apaga a continuidade dos conjuntos desta rede (o dado é do inquilino, não da rede: outra rede do
    mesmo inquilino que declare o mesmo conjunto perde o dado junto, e por isso o evento registra os
    conjuntos afetados)."""
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        alvo = continuidade.conjuntos_da_rede(cur, rid)
        if alvo:
            cur.execute("DELETE FROM plat.rede_continuidade WHERE conjunto_id = ANY(%s)", (alvo,))
            cur.execute("DELETE FROM plat.rede_continuidade_limite WHERE conjunto_id = ANY(%s)", (alvo,))
        registrar_evento(cur, request, "redes/continuidade_apagar", "rede", rid, {"conjuntos": alvo})
    return Response(status_code=204)
