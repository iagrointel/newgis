"""Transferência de dono (ADR 0004 seção 10): plano com pré-checagem (simular) que lista o que vai falhar por item
(novo dono fora do grupo, sem contribuição, inativo), arrasta as relações com arrasta_dono (vistas, estilo, arquivo de
origem, anexos, camadas da rede), nunca os mapas/apps que usam a camada; preserva uuid, compartilhamentos, links,
favoritos, versões, relações, proteção e status; executa com plat.transferencia = on (gatilho) e evento por item."""

from fastapi import APIRouter, Request

from app import db
from app.auth.sessao import Auth, autenticado
from app.catalogo import comum
from app.catalogo.comum import item_ou_404, registrar_evento, uuid_ok
from app.catalogo.modelos import Transferencia, TransferenciaEntrada
from app.erros import ErroAPI

router = APIRouter(tags=["catalogo"])


def _novo_dono(cur, novo_dono_id: int) -> dict:
    cur.execute("SELECT id, login, nome, ativo FROM plat.usuario WHERE id = %s", (novo_dono_id,))
    u = cur.fetchone()
    if u is None:
        raise ErroAPI(404, "usuario_inexistente", "usuário inexistente")
    if not u["ativo"]:
        raise ErroAPI(422, "novo_dono_inativo", "o novo dono está desabilitado")
    cur.execute("SELECT 'conteudo.criar' = ANY (plat.privilegios_de(%s)) AS ok", (novo_dono_id,))
    if not cur.fetchone()["ok"]:
        raise ErroAPI(422, "novo_dono_sem_privilegio", "o novo dono precisa do privilégio conteudo.criar")
    return dict(u)


def _arrastados(cur, iid: str) -> list[dict]:
    """Relações origem→destino com arrasta_dono: destinos que vão junto (vista→camada primária? não: aqui é
    quem depende da camada com arrasta_dono = vistas (origem) da camada (destino))."""
    cur.execute(
        "SELECT r.origem AS id, r.tipo, i.titulo, i.dono_id, plat.pode_editar(i.id) AS pode_editar "
        "FROM plat.item_relacao r JOIN plat.relacao_tipo rt ON rt.nome = r.tipo "
        "JOIN plat.item i ON i.id = r.origem AND i.apagado_em IS NULL WHERE r.destino = %s::uuid AND rt.arrasta_dono",
        (iid,),
    )
    return [
        {
            "id": str(r["id"]),
            "tipo_relacao": r["tipo"],
            "titulo": r["titulo"],
            "dono_id": r["dono_id"],
            "pode_editar": bool(r["pode_editar"]),
        }
        for r in cur.fetchall()
    ]


def _primaria_de(cur, iid: str) -> list[dict]:
    """Se o item é uma vista/estilo/anexo (origem com arrasta_dono), a camada primária (destino) tem de ir junto."""
    cur.execute(
        "SELECT r.destino AS id, r.tipo, i.titulo FROM plat.item_relacao r JOIN plat.relacao_tipo rt "
        "ON rt.nome = r.tipo "
        "JOIN plat.item i ON i.id = r.destino AND i.apagado_em IS NULL WHERE r.origem = %s::uuid AND rt.arrasta_dono",
        (iid,),
    )
    return [{"id": str(r["id"]), "tipo_relacao": r["tipo"], "titulo": r["titulo"]} for r in cur.fetchall()]


def planejar(cur, auth: Auth, ids: list[str], novo: dict, adicionar_aos_grupos: bool) -> list[dict]:
    plano = []
    for iid in ids:
        r = item_ou_404(cur, iid)
        falhas = []
        if not (r["pode_editar"] or auth.tem("conteudo.transferir")):
            falhas.append({"codigo": "sem_edicao_no_item", "solucao": None})
        if r["dono_id"] == novo["id"]:
            falhas.append({"codigo": "ja_e_o_dono", "solucao": None})
        arrasta = _arrastados(cur, iid)
        # item arrastado que o ator não pode editar NÃO vai mudar de dono (a RLS barra o UPDATE sem levantar erro):
        # a pré-checagem declara a falha em vez de prometer o arrasto e gravar um evento falso (achado G2-5).
        for a in arrasta:
            if not a["pode_editar"]:
                falhas.append({"codigo": "arrasto_sem_edicao", "item": a, "solucao": None})
        primarias = _primaria_de(cur, iid)
        for pr in primarias:
            if pr["id"] not in ids:
                falhas.append({"codigo": "vista_sem_camada", "item": pr, "solucao": "incluir_camada_primaria"})
        cur.execute(
            "SELECT g.id, g.nome, g.contribuicao, m.estado, m.papel, "
            "EXISTS (SELECT 1 FROM plat.grupo_membro a WHERE a.grupo_id = g.id AND a.usuario_id = %s "
            "AND a.estado = 'ativo' AND a.papel IN ('dono','gerente')) AS ator_gere "
            "FROM plat.item_grupo ig JOIN plat.grupo g ON g.id = ig.grupo_id "
            "LEFT JOIN plat.grupo_membro m ON m.grupo_id = g.id AND m.usuario_id = %s WHERE ig.item_id = %s::uuid",
            (auth.usuario_id, novo["id"], iid),
        )
        for g in cur.fetchall():
            grupo = {"id": str(g["id"]), "nome": g["nome"]}
            if g["estado"] != "ativo":
                pode_adicionar = g["ator_gere"] or auth.tem("grupos.gerir_todos")
                falhas.append(
                    {
                        "codigo": "novo_dono_fora_do_grupo",
                        "grupo": grupo,
                        "solucao": "adicionar_aos_grupos" if pode_adicionar else None,
                        "resolvida": bool(adicionar_aos_grupos and pode_adicionar),
                    }
                )
            elif g["contribuicao"] == "dono_gerentes" and g["papel"] not in ("dono", "gerente"):
                falhas.append({"codigo": "novo_dono_sem_contribuicao", "grupo": grupo, "solucao": None})
        plano.append(
            {
                "id": iid,
                "titulo": r["titulo"],
                "acao": "transferir",
                "arrasta": arrasta,
                "falhas": [f for f in falhas if not f.get("resolvida")],
                "resolvidas": [f for f in falhas if f.get("resolvida")],
            }
        )
    return plano


def executar(
    cur,
    request: Request,
    auth: Auth,
    plano: list[dict],
    novo: dict,
    corpo: TransferenciaEntrada,
    login_antigo: str | None,
) -> int:
    cur.execute("SELECT set_config('plat.transferencia', 'on', true)")
    pasta_unica = None
    if corpo.pastas == "unica":
        nome = corpo.pasta_unica_nome or f"de_{login_antigo or 'usuario'}"
        cur.execute("SELECT id FROM plat.pasta WHERE pai_id IS NULL AND lower(nome) = lower(%s)", (nome,))
        p = cur.fetchone()
        if p:
            pasta_unica = str(p["id"])
        else:
            cur.execute(
                "INSERT INTO plat.pasta(tenant_id, nome, dono_id) VALUES (%s, %s, %s) RETURNING id",
                (auth.tenant_id, nome, auth.usuario_id),
            )
            pasta_unica = str(cur.fetchone()["id"])
    feitos = 0
    for p in plano:
        if p["falhas"]:
            continue
        for f in p["resolvidas"]:
            cur.execute(
                "INSERT INTO plat.grupo_membro(grupo_id, tenant_id, usuario_id, papel, estado, convidado_por) "
                "VALUES (%s::uuid, %s, %s, 'membro', 'ativo', %s) ON CONFLICT (grupo_id, usuario_id) "
                "DO UPDATE SET estado = 'ativo'",
                (f["grupo"]["id"], auth.tenant_id, novo["id"], auth.usuario_id),
            )
        alvo = [p["id"]] + [a["id"] for a in p["arrasta"]]
        for iid in alvo:
            cur.execute("SELECT dono_id FROM plat.item WHERE id = %s::uuid", (iid,))
            r = cur.fetchone()
            if r is None:
                continue
            if pasta_unica:
                cur.execute(
                    "UPDATE plat.item SET dono_id = %s, pasta_id = %s::uuid WHERE id = %s::uuid",
                    (novo["id"], pasta_unica, iid),
                )
            else:
                cur.execute("UPDATE plat.item SET dono_id = %s WHERE id = %s::uuid", (novo["id"], iid))
            # UPDATE barrado pela RLS não é erro no Postgres: afeta zero linhas e segue. Sem esta guarda o evento
            # era gravado para item que NÃO mudou de dono e a auditoria mentia (achado G2-5). A transação inteira
            # cai: ninguém fica com meia transferência gravada.
            if cur.rowcount != 1:
                raise ErroAPI(
                    409,
                    "transferencia_sem_efeito",
                    "a transferência não alterou o item (sem permissão de edição ou item removido)",
                    {"item_id": iid, "arrastado_por": None if iid == p["id"] else p["id"]},
                )
            registrar_evento(
                cur,
                request,
                "itens/transferir",
                "item",
                iid,
                {
                    "de": r["dono_id"],
                    "para": novo["id"],
                    "arrastados": [a["id"] for a in p["arrasta"]] if iid == p["id"] else [],
                    "arrastado_por": None if iid == p["id"] else p["id"],
                },
            )
        feitos += 1
    return feitos


@router.post(
    "/api/itens/transferir",
    response_model=Transferencia,
    openapi_extra={"x-auth": "S/T", "x-privilegio": "conteudo.transferir|conteudo.criar"},
)
def transferir(corpo: TransferenciaEntrada, request: Request, auth: Auth = autenticado()):
    if not (auth.tem("conteudo.transferir") or auth.tem("conteudo.criar")):
        raise ErroAPI(
            403,
            "sem_privilegio",
            "a operação exige conteudo.transferir ou conteudo.criar",
            {"exigido": "conteudo.transferir"},
        )
    if (corpo.ids is None) == (corpo.usuario_origem_id is None):
        raise ErroAPI(422, "validacao", "informe ids OU usuario_origem_id")
    try:
        with db.db(auth.contexto()) as cur:
            novo = _novo_dono(cur, corpo.novo_dono_id)
            login_antigo = None
            if corpo.usuario_origem_id is not None:
                if corpo.usuario_origem_id != auth.usuario_id and not auth.tem("conteudo.transferir"):
                    raise ErroAPI(
                        403,
                        "sem_privilegio",
                        "transferir tudo de outro usuário exige conteudo.transferir",
                        {"exigido": "conteudo.transferir"},
                    )
                cur.execute("SELECT login FROM plat.usuario WHERE id = %s", (corpo.usuario_origem_id,))
                u = cur.fetchone()
                if u is None:
                    raise ErroAPI(404, "usuario_inexistente", "usuário inexistente")
                login_antigo = u["login"]
                cur.execute(
                    "SELECT id FROM plat.item WHERE dono_id = %s AND apagado_em IS NULL ORDER BY criado_em",
                    (corpo.usuario_origem_id,),
                )
                ids = [str(r["id"]) for r in cur.fetchall()]
            else:
                ids = [uuid_ok(x) for x in dict.fromkeys(corpo.ids)]
                cur.execute("SELECT login FROM plat.usuario WHERE id = %s", (auth.usuario_id,))
                login_antigo = cur.fetchone()["login"]
            plano = planejar(cur, auth, ids, novo, corpo.adicionar_aos_grupos)
            com_falha = sum(1 for p in plano if p["falhas"])
            saida = {
                "plano": plano,
                "total": len(plano),
                "com_falha": com_falha,
                "novo_dono": {"id": novo["id"], "login": novo["login"], "nome": novo["nome"], "ativo": novo["ativo"]},
                "executado": False,
                "transferidos": 0,
            }
            if corpo.simular:
                return saida
            if com_falha and not corpo.forcar_parcial:
                raise ErroAPI(409, "plano_com_falhas", "o plano tem falhas; corrija-as ou use forcar_parcial", saida)
            saida["transferidos"] = executar(cur, request, auth, plano, novo, corpo, login_antigo)
            saida["executado"] = True
            return saida
    except comum.psycopg2.Error as e:
        raise comum.erro_do_banco(e) from e
