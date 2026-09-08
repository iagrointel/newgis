"""Pacote de documentos e galeria de modelos (item L5-37-pacotes-modelos-entre-inquilinos; ADR
20260908T1055-pacotes-modelos-entre-inquilinos; depende de L5-05-documento-versoes e de
L5-14-publicacao-links-embed).

Um PACOTE é um zip com `manifesto.json` e um `documentos/<id>.json` por documento. Documento é item cujo tipo
tem `tem_dado_fisico = false` (app, painel, formulário, fluxo, mapa, estilo, modelo multicritério); item cujo
tipo tem `tem_dado_fisico = true` (camada, vista, imagem, arquivo, rede) NUNCA entra: ele é declarado como
FONTE, com o esquema dos seus campos, e quem importa diz qual item do destino faz o papel de cada fonte.
Por isso o pacote não carrega dado nenhum e serve tanto entre inquilinos da mesma instalação quanto entre
instalações diferentes (o appliance do L7-11).

O grafo de dependências é o mesmo `plat.item_relacao` que o resto do catálogo já mantém
(`app/catalogo/relacoes.py`): nada aqui infere dependência lendo o documento por adivinhação. O que este
módulo lê do documento é o conjunto de UUIDs citados, e essa leitura é a trava de segurança: na importação,
todo UUID citado tem de ser (a) outro documento do mesmo pacote ou (b) uma fonte declarada e mapeada para um
item que o inquilino de destino enxerga. UUID que não seja nenhum dos dois faz a importação inteira parar —
é assim que um pacote com id de item de outro inquilino é recusado.

Ids: na importação, TODO id é regerado — o UUID de cada documento e o ULID de cada nó — e todas as
referências são reescritas pelo mesmo mapa, numa passada só. Importar o mesmo pacote duas vezes dá dois
conjuntos de itens distintos, sem colisão, e nenhum id do pacote sobra dentro do destino.

Assinatura: `manifesto.sha256_conteudo` é o sha256 da forma canônica do próprio manifesto sem esse campo
(`app/catalogo/documento.py::sha256_canonico`), e o manifesto traz o sha256 de cada arquivo de documento.
Um byte alterado em qualquer lugar do zip muda um dos dois e a leitura recusa. A forma canônica é a mesma do
L5-05, reproduzível fora daqui com `jq -cS` + `sha256sum`.
"""

from __future__ import annotations

import datetime
import io
import json
import re
import uuid
import zipfile

from app import limites
from app.auth.sessao import iso
from app.catalogo import comum, relacoes, texto, tipos
from app.catalogo.documento import ULID_RE, gerar_ulid, sha256_canonico, validar_grafo
from app.erros import ErroAPI
from app.ingestao.formatos import ZipSuspeito, conferir_zip

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
FORMATO = "plat.pacote"
VERSAO_FORMATO = 1
ARQUIVO_MANIFESTO = "manifesto.json"
PASTA_DOCUMENTOS = "documentos/"
# campos do item que viajam no pacote: descrevem o documento, nunca o lugar dele no destino (pasta, categoria,
# classificação, extent e dono são do inquilino que recebe, não do que envia)
CAMPOS_DOCUMENTO = ("tipo", "titulo", "resumo", "descricao", "tags", "creditos", "termos_de_uso", "dados")


# ---------------------------------------------------------------------------------- leitura do grafo (exportar)
def uuids_citados(valor, achados: set[str] | None = None) -> set[str]:
    """Todo UUID canônico que aparece como string em qualquer lugar da estrutura. É o conjunto que a
    importação exige ter mapeado; ler o documento inteiro (e não só o extrator de relações do tipo) é de
    propósito: um id que o extrator não conhece não pode entrar no destino sem ser conferido."""
    achados = set() if achados is None else achados
    if isinstance(valor, str):
        if UUID_RE.match(valor):
            achados.add(valor)
    elif isinstance(valor, dict):
        for v in valor.values():
            uuids_citados(v, achados)
    elif isinstance(valor, list):
        for v in valor:
            uuids_citados(v, achados)
    return achados


def _fonte_de(item: dict) -> dict:
    """Declaração de uma fonte: o que o destino precisa conferir antes de aceitar o mapeamento. Nunca leva
    dado — só o esquema (campos, geometria, srid) que o documento assume existir."""
    dados = item.get("dados") or {}
    campos = dados.get("campos") if isinstance(dados, dict) else None
    return {
        "id": str(item["id"]),
        "tipo": item["tipo"],
        "titulo": item["titulo"],
        "campos": [
            {"nome": c.get("nome"), "tipo": c.get("tipo")}
            for c in (campos or [])
            if isinstance(c, dict) and c.get("nome")
        ],
        "geometria": dados.get("geometria") if isinstance(dados, dict) else None,
        "srid": dados.get("srid") if isinstance(dados, dict) else None,
    }


def _documento_de(item: dict) -> dict:
    d = {c: item.get(c) for c in CAMPOS_DOCUMENTO}
    d["id"] = str(item["id"])
    d["tags"] = list(d.get("tags") or [])
    return d


def coletar(cur, raiz_id: str) -> tuple[list[dict], list[dict]]:
    """Fecho de dependências do item raiz, em ordem de dependência (quem é citado vem antes de quem cita).
    Devolve (documentos, fontes). Item citado que o ator não enxerga faz parar: pacote com dependência
    invisível seria um pacote que não funciona no destino e esconde o motivo."""
    documentos: dict[str, dict] = {}
    fontes: dict[str, dict] = {}
    ordem: list[str] = []
    visitando: set[str] = set()

    def visitar(iid: str, profundidade: int) -> None:
        if iid in documentos or iid in fontes:
            return
        if profundidade > limites.PACOTE_PROFUNDIDADE_MAX:
            raise ErroAPI(
                422,
                "pacote_profundo",
                f"a cadeia de dependências passa de {limites.PACOTE_PROFUNDIDADE_MAX} níveis",
                {"item_id": iid},
            )
        if iid in visitando:  # ciclo declarado: para, não estoura a pilha
            return
        r = comum.carregar(cur, iid)
        if r is None:
            raise ErroAPI(
                422,
                "dependencia_invisivel",
                "o pacote depende de um item que você não enxerga ou que foi apagado",
                {"item_id": iid},
            )
        item = dict(r)
        if tipos.obter(item["tipo"])["tem_dado_fisico"]:
            fontes[iid] = _fonte_de(item)
            return
        visitando.add(iid)
        for citado in sorted(uuids_citados(item.get("dados"))):
            if citado != iid:
                visitar(citado, profundidade + 1)
        visitando.discard(iid)
        documentos[iid] = _documento_de(item)
        ordem.append(iid)
        if len(documentos) > limites.PACOTE_DOCUMENTOS_MAX:
            raise ErroAPI(
                422,
                "pacote_grande",
                f"o pacote passaria de {limites.PACOTE_DOCUMENTOS_MAX} documentos",
                {"documentos": len(documentos)},
            )

    visitar(raiz_id, 0)
    return [documentos[i] for i in ordem], [fontes[i] for i in sorted(fontes)]


def montar(cur, raiz_id: str, inquilino_slug: str) -> tuple[bytes, dict]:
    """Zip do pacote + manifesto. O item raiz é sempre o último da lista de documentos (é quem cita todo
    mundo); o consumidor usa `manifesto.raiz`, não a ordem."""
    r = comum.item_ou_404(cur, raiz_id)
    documentos, fontes = coletar(cur, str(r["id"]))
    entradas = []
    arquivos: list[tuple[str, bytes]] = []
    for d in documentos:
        bruto = sha256_canonico(d)
        conteudo = json.dumps(d, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        nome = f"{PASTA_DOCUMENTOS}{d['id']}.json"
        arquivos.append((nome, conteudo))
        entradas.append({"id": d["id"], "tipo": d["tipo"], "titulo": d["titulo"], "arquivo": nome, "sha256": bruto})
    manifesto = {
        "formato": FORMATO,
        "versao_formato": VERSAO_FORMATO,
        "criado_em": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        "origem": {"inquilino": inquilino_slug},
        "raiz": str(r["id"]),
        "tipo_raiz": r["tipo"],
        "titulo_raiz": r["titulo"],
        "documentos": entradas,
        "fontes": fontes,
    }
    manifesto["sha256_conteudo"] = sha256_canonico(manifesto)
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            ARQUIVO_MANIFESTO,
            json.dumps(manifesto, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        )
        for nome, conteudo in arquivos:
            zf.writestr(nome, conteudo)
    return saida.getvalue(), manifesto


# ---------------------------------------------------------------------------------- leitura do zip (importar)
def _erro_pacote(mensagem: str, detalhe=None) -> ErroAPI:
    return ErroAPI(422, "pacote_invalido", mensagem, detalhe)


def ler(conteudo: bytes) -> tuple[dict, dict[str, dict]]:
    """(manifesto, {id: documento}) de um zip recebido. Confere, nesta ordem: tamanho, segurança do zip
    (`app/ingestao/formatos.py::conferir_zip` — é a mesma guarda que já recusa `..`, caminho absoluto, link
    simbólico, zip aninhado e zip-bomba no upload de dado), formato, assinatura do manifesto e sha256 de cada
    documento. Nada é lido como JSON antes de o zip passar pela guarda."""
    if not conteudo:
        raise _erro_pacote("pacote vazio")
    if len(conteudo) > limites.PACOTE_BYTES_MAX:
        raise ErroAPI(
            413,
            "pacote_grande",
            f"pacote de {len(conteudo)} bytes; o máximo é {limites.PACOTE_BYTES_MAX}",
            {"bytes": len(conteudo), "maximo": limites.PACOTE_BYTES_MAX},
        )
    try:
        zf = conferir_zip(conteudo)
    except ZipSuspeito as e:
        raise _erro_pacote(f"zip recusado: {e}") from e
    nomes = set(zf.namelist())
    if ARQUIVO_MANIFESTO not in nomes:
        raise _erro_pacote(f"pacote sem {ARQUIVO_MANIFESTO}")
    try:
        manifesto = json.loads(zf.read(ARQUIVO_MANIFESTO).decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise _erro_pacote(f"{ARQUIVO_MANIFESTO} não é JSON válido: {e}") from e
    if not isinstance(manifesto, dict) or manifesto.get("formato") != FORMATO:
        raise _erro_pacote(f"manifesto não é do formato {FORMATO}")
    if manifesto.get("versao_formato") != VERSAO_FORMATO:
        raise _erro_pacote(
            f"versão de formato {manifesto.get('versao_formato')!r}; esta instalação lê a {VERSAO_FORMATO}"
        )
    assinatura = manifesto.pop("sha256_conteudo", None)
    if not isinstance(assinatura, str) or sha256_canonico(manifesto) != assinatura:
        raise ErroAPI(422, "pacote_adulterado", "a assinatura do manifesto não confere com o conteúdo dele")
    manifesto["sha256_conteudo"] = assinatura
    entradas = manifesto.get("documentos")
    if not isinstance(entradas, list) or not entradas:
        raise _erro_pacote("manifesto sem documentos")
    if len(entradas) > limites.PACOTE_DOCUMENTOS_MAX:
        raise _erro_pacote(f"pacote com {len(entradas)} documentos; o máximo é {limites.PACOTE_DOCUMENTOS_MAX}")
    documentos: dict[str, dict] = {}
    for e in entradas:
        if not isinstance(e, dict) or e.get("arquivo") not in nomes:
            raise _erro_pacote(f"manifesto cita arquivo que não está no zip: {(e or {}).get('arquivo')!r}")
        try:
            doc = json.loads(zf.read(e["arquivo"]).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise _erro_pacote(f"{e['arquivo']} não é JSON válido: {exc}") from exc
        if not isinstance(doc, dict) or not isinstance(doc.get("id"), str) or not UUID_RE.match(doc["id"]):
            raise _erro_pacote(f"{e['arquivo']} não é um documento com id")
        if sha256_canonico(doc) != e.get("sha256"):
            raise ErroAPI(
                422,
                "pacote_adulterado",
                "o sha256 de um documento não confere com o do manifesto",
                {"arquivo": e["arquivo"]},
            )
        documentos[doc["id"]] = doc
    if manifesto.get("raiz") not in documentos:
        raise _erro_pacote("o documento raiz não está no pacote")
    for f in manifesto.get("fontes") or []:
        if not isinstance(f, dict) or not isinstance(f.get("id"), str) or not UUID_RE.match(f["id"]):
            raise _erro_pacote("fonte declarada sem id")
    return manifesto, documentos


# ---------------------------------------------------------------------------------- conferência de esquema
def _campos_de(item: dict) -> list[dict]:
    dados = item.get("dados") or {}
    campos = dados.get("campos") if isinstance(dados, dict) else None
    return [c for c in (campos or []) if isinstance(c, dict) and c.get("nome")]


def _tipo_igual(a, b) -> bool:
    return str(a or "").strip().lower() == str(b or "").strip().lower()


def comparar_esquema(fonte: dict, destino: dict) -> list[dict]:
    """Diferenças campo a campo entre o que o pacote assume e o que o item do destino tem. `bloqueia = true`
    impede a importação; o SRID que difere é reportado e NÃO bloqueia (reprojetar é rotina da plataforma, e
    o documento nunca guarda coordenada de dado). Campo a mais no destino não é diferença: o documento usa
    os que cita."""
    saida: list[dict] = []
    tem = {c["nome"]: c.get("tipo") for c in _campos_de(destino)}
    for c in fonte.get("campos") or []:
        nome = c.get("nome")
        if nome not in tem:
            saida.append(
                {
                    "campo": nome,
                    "regra": "campo_ausente",
                    "esperado": c.get("tipo"),
                    "encontrado": None,
                    "bloqueia": True,
                }
            )
        elif not _tipo_igual(c.get("tipo"), tem[nome]):
            saida.append(
                {
                    "campo": nome,
                    "regra": "tipo_diferente",
                    "esperado": c.get("tipo"),
                    "encontrado": tem[nome],
                    "bloqueia": True,
                }
            )
    dados = destino.get("dados") or {}
    geo_destino = dados.get("geometria") if isinstance(dados, dict) else None
    if fonte.get("geometria") and geo_destino and fonte["geometria"] != geo_destino:
        saida.append(
            {
                "campo": "(geometria)",
                "regra": "geometria_diferente",
                "esperado": fonte["geometria"],
                "encontrado": geo_destino,
                "bloqueia": True,
            }
        )
    srid_destino = dados.get("srid") if isinstance(dados, dict) else None
    if fonte.get("srid") and srid_destino and fonte["srid"] != srid_destino:
        saida.append(
            {
                "campo": "(srid)",
                "regra": "srid_diferente",
                "esperado": fonte["srid"],
                "encontrado": srid_destino,
                "bloqueia": False,
            }
        )
    return saida


def analisar(cur, manifesto: dict, mapeamento: dict[str, str]) -> dict:
    """O que a importação faria e o que a impede. Nunca escreve nada: é a tela de "antes de importar"."""
    fontes = []
    pronto = True
    for f in manifesto.get("fontes") or []:
        linha = {
            "id": f["id"],
            "tipo": f["tipo"],
            "titulo": f.get("titulo"),
            "campos": len(f.get("campos") or []),
            "destino": None,
            "diferencas": [],
            "erro": None,
        }
        alvo = (mapeamento or {}).get(f["id"])
        if not alvo:
            linha["erro"] = "fonte_nao_mapeada"
            pronto = False
            fontes.append(linha)
            continue
        try:
            destino = comum.item_ou_404(cur, comum.uuid_ok(alvo))
        except ErroAPI:
            linha["erro"] = "fonte_inexistente"
            pronto = False
            fontes.append(linha)
            continue
        linha["destino"] = {"id": str(destino["id"]), "tipo": destino["tipo"], "titulo": destino["titulo"]}
        if not tipos.obter(destino["tipo"])["tem_dado_fisico"]:
            linha["erro"] = "destino_sem_dado"
            pronto = False
            fontes.append(linha)
            continue
        linha["diferencas"] = comparar_esquema(f, dict(destino))
        if any(d["bloqueia"] for d in linha["diferencas"]):
            linha["erro"] = "esquema_incompativel"
            pronto = False
        fontes.append(linha)
    return {
        "raiz": manifesto.get("raiz"),
        "tipo_raiz": manifesto.get("tipo_raiz"),
        "titulo_raiz": manifesto.get("titulo_raiz"),
        "origem": manifesto.get("origem"),
        "sha256_conteudo": manifesto.get("sha256_conteudo"),
        "documentos": [
            {"id": d["id"], "tipo": d["tipo"], "titulo": d["titulo"]} for d in manifesto.get("documentos") or []
        ],
        "fontes": fontes,
        "pronto": pronto,
    }


# ---------------------------------------------------------------------------------- regeração de ids
def _ids_de_nos(documento: dict) -> set[str]:
    dados = documento.get("dados")
    corpo = dados.get("corpo") if isinstance(dados, dict) else None
    nos = corpo.get("nos") if isinstance(corpo, dict) else None
    return {n["id"] for n in (nos or []) if isinstance(n, dict) and isinstance(n.get("id"), str)}


def mapa_de_ids(documentos: dict[str, dict], mapeamento: dict[str, str]) -> dict[str, str]:
    """old → new de TUDO que é identificador: UUID de documento (uuid novo), ULID de nó (ulid novo) e UUID de
    fonte (o item do destino escolhido por quem importa)."""
    mapa: dict[str, str] = {i: str(uuid.uuid4()) for i in documentos}
    for antigo, novo in (mapeamento or {}).items():
        mapa[antigo] = str(uuid.UUID(novo))
    for doc in documentos.values():
        for no in _ids_de_nos(doc):
            mapa.setdefault(no, gerar_ulid())
    return mapa


def reescrever(valor, mapa: dict[str, str], desconhecidos: set[str]):
    """Troca, em profundidade, toda string que é um identificador conhecido. UUID que não está no mapa é
    anotado em `desconhecidos` e a importação para: é um item que não veio no pacote e não foi mapeado —
    normalmente um id de outro inquilino. ULID fora do mapa fica como está: é texto do documento, não
    referência a nó (os ids de nó do pacote inteiro entram no mapa antes desta passada)."""
    if isinstance(valor, str):
        if UUID_RE.match(valor):
            novo = mapa.get(valor)
            if novo is None:
                desconhecidos.add(valor)
                return valor
            return novo
        if ULID_RE.match(valor):
            return mapa.get(valor, valor)
        return valor
    if isinstance(valor, dict):
        return {k: reescrever(v, mapa, desconhecidos) for k, v in valor.items()}
    if isinstance(valor, list):
        return [reescrever(v, mapa, desconhecidos) for v in valor]
    return valor


# ---------------------------------------------------------------------------------- importação
def _ordem_topologica(documentos: dict[str, dict]) -> list[str]:
    """Quem é citado entra antes de quem cita (plat.item_relacao exige o destino existindo). Ciclo entre
    documentos não trava: o que sobrar entra na ordem do manifesto e a relação é criada assim mesmo na
    segunda passada de `relacoes.sincronizar` (feita depois de todos existirem)."""
    pendentes = dict(documentos)
    saida: list[str] = []
    while pendentes:
        prontos = [
            i
            for i, d in pendentes.items()
            if not (uuids_citados(d.get("dados")) & set(pendentes) - {i})
        ]
        if not prontos:
            saida.extend(pendentes)
            break
        for i in sorted(prontos):
            saida.append(i)
            pendentes.pop(i)
    return saida


def _inserir(cur, auth, novo_id: str, doc: dict, pasta_id: str | None) -> None:
    tipos.validar(doc["tipo"], doc["dados"])
    validar_grafo(doc["tipo"], doc["dados"])
    cur.execute(
        """
        INSERT INTO plat.item(id, tenant_id, tipo, titulo, resumo, descricao, descricao_html, tags, creditos,
                              termos_de_uso, termos_de_uso_html, dono_id, pasta_id, dados, criado_por,
                              modificado_por)
        VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s::text[], %s, %s, %s, %s, %s::uuid, %s, %s, %s)""",
        (
            novo_id,
            auth.tenant_id,
            doc["tipo"],
            (doc.get("titulo") or "sem título").strip()[:250],
            doc.get("resumo"),
            doc.get("descricao"),
            texto.markdown_para_html(doc.get("descricao")),
            list(doc.get("tags") or []),
            doc.get("creditos"),
            doc.get("termos_de_uso"),
            texto.markdown_para_html(doc.get("termos_de_uso")),
            auth.usuario_id,
            pasta_id,
            comum.jsonb(doc["dados"]),
            auth.usuario_id,
            auth.usuario_id,
        ),
    )


def importar(cur, request, auth, manifesto: dict, documentos: dict[str, dict], mapeamento: dict, pasta_id=None) -> dict:
    """Cria no inquilino do ator os documentos do pacote, com ids novos, apontando para as fontes do destino.
    Tudo numa transação só: ou entra o pacote inteiro, ou não entra nada."""
    analise = analisar(cur, manifesto, mapeamento)
    if not analise["pronto"]:
        raise ErroAPI(
            422,
            "pacote_incompativel",
            "o pacote não pode ser importado com este mapeamento de fontes",
            {"fontes": [f for f in analise["fontes"] if f["erro"]]},
        )
    cur.execute(
        "SELECT plat.cota_itens(%s) AS cota, (SELECT count(*) FROM plat.item WHERE tenant_id = %s) AS n",
        (auth.tenant_id, auth.tenant_id),
    )
    r = cur.fetchone()
    if r["n"] + len(documentos) > r["cota"]:
        raise ErroAPI(
            413,
            "cota_itens",
            f"cota de itens do inquilino esgotada ({r['cota']})",
            {"cota": r["cota"], "documentos": len(documentos)},
        )
    mapa = mapa_de_ids(documentos, {f["id"]: f["destino"]["id"] for f in analise["fontes"]})
    desconhecidos: set[str] = set()
    reescritos = {i: reescrever(d, mapa, desconhecidos) for i, d in documentos.items()}
    if desconhecidos:
        raise ErroAPI(
            422,
            "referencia_desconhecida",
            "o pacote cita itens que não estão nele nem foram mapeados; nada foi importado",
            {"ids": sorted(desconhecidos)},
        )
    criados = []
    for antigo in _ordem_topologica(documentos):
        doc = reescritos[antigo]
        novo_id = mapa[antigo]
        _inserir(cur, auth, novo_id, doc, pasta_id)
        criados.append({"id": novo_id, "de": antigo, "tipo": doc["tipo"], "titulo": doc.get("titulo")})
    for antigo in reescritos:
        doc = reescritos[antigo]
        if relacoes.tem_extrator(doc["tipo"]):
            relacoes.sincronizar(cur, auth.tenant_id, mapa[antigo], relacoes.extrair(doc["tipo"], doc["dados"]))
    raiz = mapa[manifesto["raiz"]]
    comum.registrar_evento(
        cur,
        request,
        "pacotes/importar",
        "item",
        raiz,
        {
            "sha256_conteudo": manifesto.get("sha256_conteudo"),
            "documentos": len(criados),
            "fontes": len(analise["fontes"]),
            "origem": (manifesto.get("origem") or {}).get("inquilino"),
        },
    )
    return {"raiz": raiz, "itens": criados, "fontes_mapeadas": len(analise["fontes"])}


# ---------------------------------------------------------------------------------- galeria de modelos
COLUNAS_MODELO = (
    "id, escopo, tenant_id, nome, descricao, tipo_raiz, documentos, fontes, sha256, bytes, publicado_por, criado_em"
)


def _modelo_json(r: dict, tenant_id: int) -> dict:
    return {
        "id": str(r["id"]),
        "escopo": r["escopo"],
        "nome": r["nome"],
        "descricao": r["descricao"],
        "tipo_raiz": r["tipo_raiz"],
        "documentos": r["documentos"],
        "fontes": r["fontes"],
        "sha256": r["sha256"],
        "bytes": r["bytes"],
        "do_inquilino": r["tenant_id"] == tenant_id,
        "criado_em": iso(r["criado_em"]),
    }


def listar_modelos(cur, tenant_id: int, escopo: str | None = None) -> list[dict]:
    sql = f"SELECT {COLUNAS_MODELO} FROM plat.pacote_modelo"
    params: list = []
    if escopo:
        sql += " WHERE escopo = %s"
        params.append(escopo)
    sql += " ORDER BY criado_em DESC LIMIT %s"
    params.append(limites.PACOTE_MODELOS_MAX)
    cur.execute(sql, params)
    return [_modelo_json(dict(r), tenant_id) for r in cur.fetchall()]


def modelo_ou_404(cur, modelo_id: str) -> dict:
    cur.execute(f"SELECT {COLUNAS_MODELO}, conteudo FROM plat.pacote_modelo WHERE id = %s::uuid", (modelo_id,))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "modelo_inexistente", "modelo inexistente")
    return dict(r)


def publicar_modelo(cur, request, auth, nome: str, descricao: str, escopo: str, conteudo: bytes) -> dict:
    """Guarda um pacote na galeria. O pacote é LIDO antes de ser guardado (assinatura e sha256 de cada
    documento conferidos): modelo que não abre nunca entra na galeria de ninguém."""
    manifesto, documentos = ler(conteudo)
    cur.execute("SELECT count(*) AS n FROM plat.pacote_modelo WHERE tenant_id = %s", (auth.tenant_id,))
    if cur.fetchone()["n"] >= limites.PACOTE_MODELOS_MAX:
        raise ErroAPI(
            413,
            "cota_modelos",
            f"o inquilino já tem {limites.PACOTE_MODELOS_MAX} modelos publicados",
            {"maximo": limites.PACOTE_MODELOS_MAX},
        )
    cur.execute(
        "INSERT INTO plat.pacote_modelo(escopo, tenant_id, nome, descricao, tipo_raiz, documentos, fontes, "
        f"sha256, bytes, conteudo, publicado_por) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING {COLUNAS_MODELO}",
        (
            escopo,
            auth.tenant_id,
            nome.strip(),
            (descricao or "").strip(),
            manifesto["tipo_raiz"],
            len(documentos),
            len(manifesto.get("fontes") or []),
            manifesto["sha256_conteudo"],
            len(conteudo),
            conteudo,
            auth.usuario_id,
        ),
    )
    r = dict(cur.fetchone())
    comum.registrar_evento(
        cur, request, "modelos/publicar", "modelo", str(r["id"]), {"escopo": escopo, "nome": nome.strip()[:200]}
    )
    return _modelo_json(r, auth.tenant_id)
