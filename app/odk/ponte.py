"""Ponte ODK Central -> plataforma (item L2-07-e-odk-central-ponte).

Três conversões, todas puras e testáveis sem rede (o que fala com o Central é `app/odk/central.py`):

  `achatar`               linha do OData -> ({campo: valor}, {repetição: [{campo: valor}]}).
                          O Central aninha grupo em objeto e, com `$expand=*`, repetição em lista; o documento
                          de formulário do L2-07-b é plano por NOME de campo, então o grupo some e o nome fica.
  `resposta_da_linha`     a linha achatada -> o corpo que `app.coleta.respostas.responder` já sabe aplicar
                          (mesma porta de escrita da PWA: uma resposta é uma resposta, venha do Collect ou não).
  `escolhas_de_entidades` Entities de um dataset -> lista de escolhas do formulário, com as propriedades da
                          entidade como colunas — é o que a cascata (`choice_filter` do L2-07-b) filtra.

E uma orquestração, `sincronizar`, cuja única regra dura é a idempotência: o `instanceID` do ODK (campo `__id`
do OData) é a chave em `plat.odk_envio`. Rodar o job duas vezes, ou o Central reentregar a mesma submissão,
não cria feição nova. Envio recusado (regra do formulário, domínio, tipo) fica gravado com o motivo e NÃO é
retentado como se fosse novo — nunca some em silêncio.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import mimetypes
from typing import Any

from app import limites
from app.coleta import respostas
from app.coleta.documento import folhas, nos
from app.edicao import anexos
from app.erros import ErroAPI
from app.odk.central import Central, ErroCentral

# metadados do OData que nunca são campo do formulário
META_ODATA = ("__id", "__system", "meta", "instanceID", "instanceName")


def _e_grupo(valor: dict) -> bool:
    """Objeto do OData é grupo do formulário, MENOS quando é geometria: o Central devolve geopoint/geotrace/
    geoshape como GeoJSON (`{type, coordinates}`), e descer nele perderia o campo inteiro (o valor viraria as
    chaves `type` e `coordinates`, que nenhum formulário tem)."""
    return "coordinates" not in valor and valor.get("type") not in ("Point", "LineString", "Polygon")


def achatar(linha: dict) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    """Grupo vira nada (o nome do campo-folha é único no formulário); repetição vira lista de dicionários
    achatados. Valor de repetição aninhada em repetição fica como está: o L2-07-b só grava um nível."""
    valores: dict[str, Any] = {}
    repeticoes: dict[str, list[dict[str, Any]]] = {}

    def visitar(no: dict, dentro: bool) -> None:
        for chave, valor in no.items():
            if chave in META_ODATA:
                continue
            if isinstance(valor, dict) and _e_grupo(valor):
                visitar(valor, dentro)
            elif isinstance(valor, list) and all(isinstance(x, dict) for x in valor):
                if dentro:
                    continue  # repetição dentro de repetição: fora do documento do L2-07-b
                linhas = []
                for item in valor:
                    plana: dict[str, Any] = {}
                    for c, v in item.items():
                        if c in META_ODATA:
                            continue
                        if isinstance(v, dict) and _e_grupo(v):
                            plana.update({k: x for k, x in v.items() if k not in META_ODATA})
                        elif not isinstance(v, list):
                            plana[c] = v
                    linhas.append(plana)
                repeticoes[chave] = linhas
            else:
                valores[chave] = valor

    visitar(linha, False)
    return valores, repeticoes


def instance_id(linha: dict) -> str:
    """`__id` do OData é o instanceID do envio. Sem ele não há idempotência possível: o envio é recusado."""
    valor = linha.get("__id")
    if not isinstance(valor, str) or not valor.strip():
        raise ErroAPI(422, "envio_sem_instance_id", "envio do Central sem __id (instanceID)")
    return valor.strip()[:255]


def _geoponto(valor: Any) -> str | None:
    """O OData devolve geopoint como GeoJSON Point; o documento do L2-07-b espera 'lat lon [alt]'."""
    if isinstance(valor, dict) and valor.get("type") == "Point":
        c = valor.get("coordinates") or []
        if len(c) >= 2:
            resto = f" {c[2]}" if len(c) > 2 else ""
            return f"{c[1]} {c[0]}{resto}"
        return None
    return valor if isinstance(valor, str) else None


def resposta_da_linha(doc: dict, linha: dict) -> dict:
    """Linha do OData -> corpo de `respostas.responder`, guardando só os campos que o formulário conhece.
    Campo do Central que o documento não tem é IGNORADO de propósito (o Central pode ter um formulário mais
    novo que o nosso documento); campo nosso que o Central não mandou fica ausente, e a regra `obrigatorio`
    do próprio formulário é que decide se isso recusa a resposta."""
    valores, repeticoes = achatar(linha)
    tipos = {c["nome"]: c["tipo"] for c, rep in folhas(doc.get("campos") or []) if rep is None}
    tipos_rep = {}
    for no in nos(doc.get("campos") or []):
        if no.get("tipo") == "repeticao":
            tipos_rep[no["nome"]] = {c["nome"]: c["tipo"] for c in (no.get("filhos") or [])}
    limpos = {}
    for nome, tipo in tipos.items():
        if nome not in valores:
            continue
        limpos[nome] = _geoponto(valores[nome]) if tipo == "geoponto" else valores[nome]
    limpas: dict[str, list[dict]] = {}
    for nome, filhos in tipos_rep.items():
        if nome not in repeticoes:
            continue
        limpas[nome] = [
            {k: (_geoponto(v) if filhos.get(k) == "geoponto" else v) for k, v in item.items() if k in filhos}
            for item in repeticoes[nome][: limites.FORMULARIO_REPETICOES_MAX]
        ]
    sistema = linha.get("__system") if isinstance(linha.get("__system"), dict) else {}
    envio = sistema.get("submissionDate")
    envio = envio if isinstance(envio, str) else None
    # `start`/`end` do XLSForm são campos de metadado com nome livre (aqui `inicio`/`fim`): o nome vem do
    # documento, não da palavra do tipo. Sem eles vale a data de submissão que o Central carimbou.
    meta = {c.get("meta"): c["nome"] for c, rep in folhas(doc.get("campos") or [])
            if rep is None and c.get("tipo") == "meta"}
    return {
        "valores": limpos, "repeticoes": limpas,
        "inicio": valores.get(meta.get("start") or "start") or envio,
        "fim": valores.get(meta.get("end") or "end") or envio,
        "dispositivo": "odk-central",
        "anexos": [],
    }


def nomes_de_anexo(doc: dict, linha: dict) -> dict[str, str]:
    """{nome do arquivo: campo do formulário que o citou}. No OData um campo de imagem/áudio/arquivo vale o
    NOME do arquivo; o binário vem por `/attachments/{nome}`."""
    valores, repeticoes = achatar(linha)
    conhecidos = {c["nome"] for c, _rep in folhas(doc.get("campos") or [])}
    saida: dict[str, str] = {}
    for fonte in [valores, *[li for linhas in repeticoes.values() for li in linhas]]:
        for campo, valor in fonte.items():
            if campo in conhecidos and isinstance(valor, str) and valor.strip():
                saida.setdefault(valor.strip(), campo)
    return saida


def tipo_do_arquivo(nome: str) -> str:
    return mimetypes.guess_type(nome)[0] or "application/octet-stream"


def escolhas_de_entidades(entidades: list[dict]) -> list[dict]:
    """Entities -> opções de lista de escolhas. `nome` é o uuid da entidade (estável entre versões), `rotulo`
    é o `label` da versão corrente, e cada propriedade de `data` vira coluna — é por elas que o
    `choice_filter` da cascata do L2-07-b filtra (nível 1 filtra nível 2 pela propriedade compartilhada)."""
    saida = []
    for e in entidades:
        if not isinstance(e, dict) or e.get("deletedAt"):
            continue
        uuid = e.get("uuid")
        versao = e.get("currentVersion") or {}
        dados = versao.get("data") or {}
        if not isinstance(uuid, str) or not isinstance(dados, dict):
            continue
        opcao = {"nome": uuid, "rotulo": {"pt": str(versao.get("label") or uuid)}}
        opcao.update({str(k): v for k, v in dados.items() if str(k) not in ("nome", "rotulo")})
        saida.append(opcao)
    return saida[: limites.ODK_ENTIDADES_MAX]


def _agora() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def sincronizar(cur, request, auth, ponte: dict, formulario: dict, central: Central,
                *, teto: int = limites.ODK_ENVIOS_MAX_POR_EXECUCAO) -> dict:
    """Puxa os envios e aplica os que ainda não foram aplicados. Devolve o relatório da rodada.

    Cada envio corre dentro de um SAVEPOINT: um envio recusado não pode derrubar os outros nem deixar a
    transação abortada (é a diferença entre "19 gravados e 1 explicado" e "nada gravado")."""
    doc = formulario["dados"] or {}
    projeto, xml_form_id = ponte["projeto"], ponte["xml_form_id"]
    cur.execute("SELECT instance_id FROM plat.odk_envio WHERE ponte_id = %s::uuid", (str(ponte["id"]),))
    ja = {r["instance_id"] for r in cur.fetchall()}
    lidos = aplicados = repetidos = 0
    recusados: list[dict] = []
    anexos_gravados = 0
    for linha in central.envios(projeto, xml_form_id, teto=teto):
        lidos += 1
        try:
            iid = instance_id(linha)
        except ErroAPI as e:
            recusados.append({"instance_id": None, "erro": e.erro, "mensagem": e.mensagem})
            continue
        if iid in ja:
            repetidos += 1
            continue
        cur.execute("SAVEPOINT odk_envio")
        try:
            corpo = resposta_da_linha(doc, linha)
            corpo["anexos"] = _baixar_anexos(central, ponte, doc, linha, iid)
            saida = respostas.responder(cur, request, auth, formulario, corpo)
            _conferir_sha256(cur, doc.get("camada_destino"), saida["feicao"]["id"], corpo["anexos"])
            cur.execute(
                "INSERT INTO plat.odk_envio(ponte_id, instance_id, tenant_id, feicao_id, anexos) "
                "VALUES (%s::uuid, %s, plat.tenant_atual(), %s::uuid, %s)",
                (str(ponte["id"]), iid, saida["feicao"]["id"], saida["anexos"]),
            )
            cur.execute("RELEASE SAVEPOINT odk_envio")
            aplicados += 1
            anexos_gravados += saida["anexos"]
        except (ErroAPI, ErroCentral) as e:
            cur.execute("ROLLBACK TO SAVEPOINT odk_envio")
            motivo = getattr(e, "erro", None) or getattr(e, "motivo", "falha")
            mensagem = getattr(e, "mensagem", None) or str(e)
            cur.execute(
                "INSERT INTO plat.odk_envio(ponte_id, instance_id, tenant_id, motivo) "
                "VALUES (%s::uuid, %s, plat.tenant_atual(), %s) "
                "ON CONFLICT (ponte_id, instance_id) DO NOTHING",
                (str(ponte["id"]), iid, f"{motivo}: {mensagem}"[:500]),
            )
            recusados.append({"instance_id": iid, "erro": motivo, "mensagem": mensagem})
        ja.add(iid)
    cur.execute("UPDATE plat.odk_ponte SET sincronizado_em = now() WHERE id = %s::uuid", (str(ponte["id"]),))
    return {"lidos": lidos, "aplicados": aplicados, "repetidos": repetidos, "recusados": recusados,
            "anexos": anexos_gravados, "terminou_em": _agora()}


def _conferir_sha256(cur, camada_id, globalid: str, baixados: list[dict]) -> None:
    """O sha256 de cada anexo baixado do Central tem de aparecer em `plat.feicao_anexo` depois de gravado.
    Divergência recusa o envio inteiro (o SAVEPOINT desfaz a feição): anexo trocado no caminho é dado errado,
    e dado errado gravado em silêncio é pior que envio recusado com motivo."""
    if not baixados or not camada_id:
        return
    esperados = {a["sha256"] for a in baixados}
    gravados = {a["sha256"] for a in anexos.listar(cur, str(camada_id), globalid)}
    if not esperados <= gravados:
        raise ErroAPI(422, "anexo_sha256_divergente", "anexo gravado com sha256 diferente do que veio do Central",
                      {"faltando": sorted(esperados - gravados)})


def _baixar_anexos(central: Central, ponte: dict, doc: dict, linha: dict, iid: str) -> list[dict]:
    """Anexos do envio, já em base64 e com o sha256 conferido contra os bytes baixados. A conferência é do
    conteúdo consigo mesmo (o Central não publica o sha256 do anexo na listagem): o que ela garante é que o
    que foi gravado é exatamente o que veio pela rede, e o mesmo sha256 fica em `plat.feicao_anexo`."""
    import base64

    citados = nomes_de_anexo(doc, linha)
    if not citados:
        return []
    saida = []
    for a in central.anexos_do_envio(ponte["projeto"], ponte["xml_form_id"], iid):
        nome = a.get("name")
        if not isinstance(nome, str) or not a.get("exists") or nome not in citados:
            continue
        bruto = central.anexo(ponte["projeto"], ponte["xml_form_id"], iid, nome)
        saida.append({
            "campo": citados[nome], "nome": nome, "content_type": tipo_do_arquivo(nome),
            "conteudo": base64.b64encode(bruto).decode("ascii"),
            "sha256": hashlib.sha256(bruto).hexdigest(),
        })
        if len(saida) >= limites.FORMULARIO_ANEXOS_MAX:
            break
    return saida
