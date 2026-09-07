"""Motor do inventário de um Portal/AGOL (item L2-08-a-leitor-portal-inventario).

Roda como job (app/migracao/tarefas.py) mas o motor vive aqui, separado do registro de tarefa, para poder ser
exercido em teste sem worker — inclusive a parte que mais importa provar: a RETOMADA.

Retomada, em uma frase: o inventário é uma sequência de fases (`self` → `itens` → `grupos` → `usuarios`), o
ponto onde parou fica em `plat.migracao_inventario.retomada` e cada item/grupo/usuário já gravado tem chave
única — então a tentativa seguinte pula o que já está no banco SEM emitir pedido HTTP, e continua a página
de busca de onde a anterior parou. Um corte de rede no meio da página 3 não perde as páginas 1 e 2 nem
refaz os itens já lidos da 3.

Nada aqui escreve no portal do cliente. Nada aqui grava e-mail, nome completo ou telefone de usuário: de
`community/groups/<id>/users` e de `portals/<id>/users` só saem LOGINS (`username`), e a tabela do banco não
tem coluna para o resto (ver o cabeçalho da migração 20260906T1540).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.migracao import classificacao
from app.migracao.portal import ClientePortal, ErroPortal, ErroRede, redigir

FASES = ("self", "itens", "grupos", "usuarios", "concluido")
ID_ESRI = re.compile(r"^[0-9a-f]{32}$", re.I)
PROFUNDIDADE_MAX = 8            # varredura do JSON do documento em busca de dependência
DEPENDENCIA_MAX = 500           # teto por item (um web map patológico não vira memória sem fim)
# Tipos que têm documento JSON (`item/data`), recurso (`item/resources`) e relação (`relatedItems`) que
# interessem à migração. A lista existe para NÃO gastar 7 pedidos HTTP por item num portal de 10 mil itens:
# um CSV ou um pacote do Pro não tem documento, não tem recurso e não tem relação que esta casa converta —
# perguntar por eles seria multiplicar por sete o tempo do inventário sem trazer nada.
TIPOS_COM_DOCUMENTO = ("Web Map", "Web Scene", "Dashboard", "Web Mapping Application", "Web Experience", "Form")
TIPOS_COM_RECURSO = TIPOS_COM_DOCUMENTO
TIPOS_DE_SERVICO = ("Feature Service", "Map Service", "Table", "Image Service", "Vector Tile Service")
# relações que interessam à migração (a lista completa da Esri tem dezenas; estas são as que ligam item a
# item no que esta casa sabe converter), por categoria de item
RELACOES_DE_DOCUMENTO = ("Map2Service", "Map2FeatureCollection", "WMA2Code")
RELACOES_DE_SERVICO = ("Service2Data", "Service2Service")
CHAVES_DEPENDENCIA = ("itemid", "webmap", "mapitemid", "portalitemid")


@dataclass
class Totais:
    itens: int = 0
    grupos: int = 0
    usuarios: int = 0
    feicoes: int = 0
    bytes_declarados: int = 0
    pedidos_http: int = 0
    esperas_429: int = 0
    itens_pulados: int = 0    # achado B2: malformado (nunca trava o lote), contado, não escondido
    aviso: str | None = None  # achado B4: contagem esperada x obtida quando a ordem do portal muda

    def como_json(self) -> dict:
        d = {
            "itens": self.itens, "grupos": self.grupos, "usuarios": self.usuarios,
            "feicoes": self.feicoes, "bytes_declarados": self.bytes_declarados,
            "pedidos_http": self.pedidos_http, "esperas_429": self.esperas_429,
            "itens_pulados": self.itens_pulados,
        }
        if self.aviso:
            d["aviso"] = self.aviso
        return d


def _sanear(obj):
    """Tira NUL de toda string dentro de um valor vindo do portal de terceiro (achado B2: título com \x00
    derruba o INSERT com ValueError do psycopg2, e o mesmo vale dentro de jsonb)."""
    if isinstance(obj, str):
        return obj.replace("\x00", "")
    if isinstance(obj, dict):
        return {k: _sanear(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanear(v) for v in obj]
    return obj


def _inteiro_nao_negativo(valor) -> int | None:
    """Cast seguro para inteiro >= 0. `numViews: "muitos"` (achado B2) e `size: -1` do AGOL para "sem
    arquivo" (achado B6) viram None em vez de derrubar o INSERT ou entrar somado como bytes negativos."""
    try:
        n = int(valor)
    except (TypeError, ValueError):
        return None
    return n if n >= 0 else None


def _ms_para_iso(valor) -> str | None:
    """O portal devolve tempo em milissegundos desde a época (campos `created`, `modified`, `lastLogin`)."""
    try:
        n = int(valor)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    import datetime

    return datetime.datetime.fromtimestamp(n / 1000, datetime.UTC).isoformat()


def dependencias_de(dados: dict, proprio_id: str = "") -> list[dict]:
    """Ids de item citados dentro do JSON do documento (web map → camadas; aplicativo → web map).

    Varre o JSON até `PROFUNDIDADE_MAX` procurando as chaves que a Esri usa para apontar item
    (`itemId`, `webmap`, `mapItemId`, `portalItemId`) e guarda só o que TEM CARA de id de item Esri
    (32 hexadecimais). Um texto qualquer numa chave `itemId` não vira dependência inventada."""
    achados: list[dict] = []
    vistos: set[str] = set()

    def andar(no, profundidade: int, caminho: str):
        if len(achados) >= DEPENDENCIA_MAX or profundidade > PROFUNDIDADE_MAX:
            return
        if isinstance(no, dict):
            for chave, valor in no.items():
                if chave.lower() in CHAVES_DEPENDENCIA and isinstance(valor, str) and ID_ESRI.match(valor):
                    if valor != proprio_id and valor not in vistos:
                        vistos.add(valor)
                        achados.append({"alvo": valor, "onde": f"{caminho}.{chave}".lstrip(".")})
                else:
                    andar(valor, profundidade + 1, f"{caminho}.{chave}".lstrip("."))
        elif isinstance(no, list):
            for i, valor in enumerate(no[:200]):
                andar(valor, profundidade + 1, f"{caminho}[{i}]")

    andar(dados, 0, "")
    return achados


def camadas_do_servico(cliente: ClientePortal, url: str) -> tuple[list[dict], int | None]:
    """Camadas e tabelas de um FeatureServer/MapServer com a contagem de feições de cada uma
    (`returnCountOnly=true`). Devolve (lista, soma) — soma None quando NENHUMA camada pôde ser contada."""
    try:
        descricao = cliente.servico(url)
    except ErroRede:
        raise
    except ErroPortal:
        return [], None
    saida: list[dict] = []
    soma = 0
    contou = False
    for grupo, especie in (("layers", "camada"), ("tables", "tabela")):
        for camada in descricao.get(grupo) or []:
            if not isinstance(camada, dict) or camada.get("id") is None:
                continue
            contagem = cliente.contagem_camada(url, int(camada["id"]))
            if contagem is not None:
                soma += contagem
                contou = True
            saida.append({
                "id": int(camada["id"]), "nome": camada.get("name"), "especie": especie,
                "geometria": camada.get("geometryType"), "contagem": contagem,
            })
    return saida, (soma if contou else None)


class Inventario:
    """Uma execução. `bd` é uma função sem argumentos que devolve o contexto de cursor (ctx.db)."""

    def __init__(self, cliente: ClientePortal, bd, inventario_id: str, tenant_id: int, *,
                 registrar=None, verificar=None, progresso=None):
        self.cliente = cliente
        self.bd = bd
        self.inventario_id = str(inventario_id)
        self.tenant_id = int(tenant_id)
        self._registrar = registrar or (lambda nivel, msg: None)
        self._verificar = verificar or (lambda: None)
        self._progresso = progresso or (lambda pct, msg: None)
        self.totais = Totais()
        self._total_itens_declarado = 0   # achado B4: o que o portal disse no último `total` visto

    # ------------------------------------------------------------------ estado no banco
    def _ler_estado(self) -> dict:
        with self.bd() as cur:
            cur.execute("SELECT retomada, totais, portal_id FROM plat.migracao_inventario WHERE id = %s",
                        (self.inventario_id,))
            linha = cur.fetchone()
        if linha is None:
            raise ErroPortal("inventario_inexistente", self.inventario_id)
        return dict(linha)

    def _gravar_retomada(self, retomada: dict) -> None:
        with self.bd() as cur:
            cur.execute(
                "UPDATE plat.migracao_inventario SET retomada = %s::jsonb, totais = %s::jsonb WHERE id = %s",
                (json.dumps(retomada), json.dumps(self.totais.como_json()), self.inventario_id),
            )

    def _ids_ja_lidos(self) -> set[str]:
        with self.bd() as cur:
            cur.execute("SELECT item_esri_id FROM plat.migracao_item WHERE inventario_id = %s",
                        (self.inventario_id,))
            return {r["item_esri_id"] for r in cur.fetchall()}

    def _logins_ja_lidos(self) -> set[str]:
        with self.bd() as cur:
            cur.execute("SELECT lower(login) AS l FROM plat.migracao_usuario WHERE inventario_id = %s",
                        (self.inventario_id,))
            return {r["l"] for r in cur.fetchall()}

    def _grupos_ja_lidos(self) -> set[str]:
        with self.bd() as cur:
            cur.execute("SELECT grupo_esri_id FROM plat.migracao_grupo WHERE inventario_id = %s",
                        (self.inventario_id,))
            return {r["grupo_esri_id"] for r in cur.fetchall()}

    def _contar(self) -> None:
        with self.bd() as cur:
            cur.execute("SELECT count(*) AS n, coalesce(sum(contagem_total), 0) AS f, "
                        "coalesce(sum(tamanho_bytes), 0) AS b FROM plat.migracao_item WHERE inventario_id = %s",
                        (self.inventario_id,))
            r = cur.fetchone()
            self.totais.itens = int(r["n"])
            self.totais.feicoes = int(r["f"])
            self.totais.bytes_declarados = int(r["b"])
            cur.execute("SELECT count(*) AS n FROM plat.migracao_grupo WHERE inventario_id = %s",
                        (self.inventario_id,))
            self.totais.grupos = int(cur.fetchone()["n"])
            cur.execute("SELECT count(*) AS n FROM plat.migracao_usuario WHERE inventario_id = %s",
                        (self.inventario_id,))
            self.totais.usuarios = int(cur.fetchone()["n"])
        self.totais.pedidos_http = self.cliente.pedidos
        self.totais.esperas_429 = self.cliente.esperas_429

    # ------------------------------------------------------------------ fases
    def fase_self(self) -> dict:
        self.cliente.confirmar_portal()
        eu = self.cliente.portal_self()
        with self.bd() as cur:
            cur.execute(
                "UPDATE plat.migracao_inventario SET portal_id = %s, portal_nome = %s, portal_versao = %s "
                "WHERE id = %s",
                (str(eu.get("id") or ""), eu.get("name") or eu.get("urlKey"),
                 str(eu.get("currentVersion") or ""), self.inventario_id),
            )
        return eu

    def _gravar_item(self, resultado: dict) -> None:
        item_id = str(resultado.get("id") or "")
        tipo = str(resultado.get("type") or "")
        palavras = resultado.get("typeKeywords") or []
        decisao = classificacao.classificar(tipo, palavras, resultado.get("url"))

        camadas: list[dict] = []
        contagem_total = None
        url = resultado.get("url")
        if url and tipo in ("Feature Service", "Map Service", "Table"):
            camadas, contagem_total = camadas_do_servico(self.cliente, str(url))
        camadas = _sanear(camadas)

        dados = {}
        if tipo in TIPOS_COM_DOCUMENTO:
            dados = self.cliente.item_dados(item_id)
        dependencias = _sanear(dependencias_de(dados, item_id) if dados else [])

        recursos = []
        relacionados = []
        if tipo in TIPOS_COM_RECURSO:
            try:
                recursos = [r.get("resource") for r in self.cliente.item_recursos(item_id) if isinstance(r, dict)]
            except ErroRede:
                raise
            except ErroPortal:
                recursos = []
        relacoes = RELACOES_DE_DOCUMENTO if tipo in TIPOS_COM_DOCUMENTO else (
            RELACOES_DE_SERVICO if tipo in TIPOS_DE_SERVICO else ())
        for relacao in relacoes:
            try:
                ligados = self.cliente.item_relacionados(item_id, relacao)
            except ErroRede:
                raise
            except ErroPortal:
                continue
            for lig in ligados:
                if isinstance(lig, dict) and lig.get("id"):
                    relacionados.append({"relacao": relacao, "alvo": str(lig["id"])})
        recursos = _sanear(recursos)
        relacionados = _sanear(relacionados)

        with self.bd() as cur:
            cur.execute(
                "INSERT INTO plat.migracao_item (inventario_id, tenant_id, item_esri_id, tipo, titulo, "
                " dono_login, url, tamanho_bytes, criado_esri_em, modificado_esri_em, ultimo_acesso_em, "
                " num_visualizacoes, classificacao, classificacao_motivo, contagem_total, camadas, "
                " dependencias, recursos, relacionados) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, "
                " %s::jsonb, %s::jsonb) "
                "ON CONFLICT (inventario_id, item_esri_id) DO NOTHING",
                (self.inventario_id, self.tenant_id, item_id, tipo, _sanear(resultado.get("title")),
                 _sanear(resultado.get("owner")), _sanear(url), _inteiro_nao_negativo(resultado.get("size")),
                 _ms_para_iso(resultado.get("created")), _ms_para_iso(resultado.get("modified")),
                 _ms_para_iso(resultado.get("lastViewed")), _inteiro_nao_negativo(resultado.get("numViews")),
                 decisao.classe, decisao.motivo, contagem_total,
                 json.dumps(camadas), json.dumps(dependencias), json.dumps(recursos),
                 json.dumps(relacionados)),
            )

    def fase_itens(self, portal_id: str, inicio: int) -> None:
        consulta = f"orgid:{portal_id}" if portal_id else "*"
        ja = self._ids_ja_lidos()
        pagina_inicio = inicio or 1
        while pagina_inicio > 0:
            self._verificar()
            resposta = self.cliente.buscar_itens(consulta, inicio=pagina_inicio)
            resultados = resposta.get("results") or []
            total = int(resposta.get("total") or 0)
            if total:
                self._total_itens_declarado = total
            for resultado in resultados:
                self._verificar()
                item_id = str(resultado.get("id") or "")
                if not item_id or item_id in ja:
                    continue
                try:
                    self._gravar_item(resultado)
                except ErroRede:
                    raise
                except Exception as e:
                    # achado B2: item com campo fora do esperado (título com NUL, numViews texto, etc.)
                    # é registrado e PULADO — nunca trava o lote nem deixa o inventário rodando para sempre.
                    self.totais.itens_pulados += 1
                    self._registrar("AVISO", f"item {item_id} pulado ({type(e).__name__}): {e}"[:400])
                ja.add(item_id)
            proxima = int(resposta.get("nextStart") or -1)
            self._contar()
            self._gravar_retomada({"fase": "itens", "start": proxima if proxima > 0 else 0})
            if total:
                self._progresso(min(60, int(len(ja) / max(total, 1) * 60)), f"{len(ja)}/{total} itens lidos")
            if proxima <= 0 or proxima == pagina_inicio:
                break
            pagina_inicio = proxima

    def fase_grupos(self, portal_id: str) -> None:
        ja = self._grupos_ja_lidos()
        inicio = 1
        while inicio > 0:
            self._verificar()
            resposta = self.cliente.grupos(portal_id, inicio=inicio)
            for grupo in resposta.get("groups") or resposta.get("results") or []:
                grupo_id = str(grupo.get("id") or "")
                if not grupo_id or grupo_id in ja:
                    continue
                membros: list[str] = []
                try:
                    pessoas = self.cliente.membros_grupo(grupo_id)
                except ErroRede:
                    raise
                except ErroPortal:
                    pessoas = {}
                # SÓ LOGIN (LGPD): o portal devolve owner/admins/users como nomes de login; nenhum outro
                # campo da resposta é lido, nem quando o portal manda e-mail junto.
                for chave in ("owner", "admins", "users"):
                    valor = pessoas.get(chave)
                    if isinstance(valor, str):
                        membros.append(valor)
                    elif isinstance(valor, list):
                        membros.extend(str(v) for v in valor if isinstance(v, str))
                membros = sorted(dict.fromkeys(membros))
                with self.bd() as cur:
                    cur.execute(
                        "INSERT INTO plat.migracao_grupo (inventario_id, tenant_id, grupo_esri_id, titulo, "
                        " acesso, dono_login, membros, num_membros) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s) "
                        "ON CONFLICT (inventario_id, grupo_esri_id) DO NOTHING",
                        (self.inventario_id, self.tenant_id, grupo_id, grupo.get("title"),
                         grupo.get("access"), grupo.get("owner"), json.dumps(membros), len(membros)),
                    )
                ja.add(grupo_id)
            proxima = int(resposta.get("nextStart") or -1)
            self._contar()
            self._gravar_retomada({"fase": "grupos", "start": proxima if proxima > 0 else 0})
            if proxima <= 0 or proxima == inicio:
                break
            inicio = proxima

    def fase_usuarios(self, portal_id: str) -> None:
        ja = self._logins_ja_lidos()
        inicio = 1
        while inicio > 0:
            self._verificar()
            resposta = self.cliente.usuarios(portal_id, inicio=inicio)
            for pessoa in resposta.get("users") or resposta.get("results") or []:
                login = str(pessoa.get("username") or "")
                if not login or login.lower() in ja:
                    continue
                # `email`, `fullName`, `firstName`, `lastName` e `description` NÃO são lidos aqui e não têm
                # coluna no banco (LGPD; refutação do item).
                with self.bd() as cur:
                    cur.execute(
                        "INSERT INTO plat.migracao_usuario (inventario_id, tenant_id, login, papel, nivel, "
                        " desativado) VALUES (%s, %s, %s, %s, %s, %s) "
                        "ON CONFLICT (inventario_id, lower(login)) DO NOTHING",
                        (self.inventario_id, self.tenant_id, login, pessoa.get("role"),
                         str(pessoa.get("userLicenseTypeId") or pessoa.get("level") or "") or None,
                         pessoa.get("disabled")),
                    )
                ja.add(login.lower())
            proxima = int(resposta.get("nextStart") or -1)
            self._contar()
            self._gravar_retomada({"fase": "usuarios", "start": proxima if proxima > 0 else 0})
            if proxima <= 0 or proxima == inicio:
                break
            inicio = proxima

    # ------------------------------------------------------------------ execução
    def executar(self) -> dict:
        estado = self._ler_estado()
        retomada = estado.get("retomada") or {}
        fase = retomada.get("fase") or "self"
        portal_id = estado.get("portal_id") or ""

        if fase == "self" or not portal_id:
            self._progresso(2, "lendo a identidade do portal")
            eu = self.fase_self()
            portal_id = str(eu.get("id") or "")
            fase = "itens"
            self._gravar_retomada({"fase": "itens", "start": 1})
            retomada = {"fase": "itens", "start": 1}

        if fase == "itens":
            self._registrar("INFO", "fase de itens (busca paginada)")
            self.fase_itens(portal_id, int(retomada.get("start") or 1))
            # achado B4: a retomada confia na ordem do portal; se o portal declarou mais itens do que
            # ficaram gravados, avisa em vez de terminar "concluido" em silêncio.
            if self._total_itens_declarado and self.totais.itens < self._total_itens_declarado:
                self.totais.aviso = (
                    f"o portal declarou {self._total_itens_declarado} itens mas só "
                    f"{self.totais.itens} foram gravados (a ordem da busca pode ter mudado durante "
                    f"a leitura); confira o inventário e rode de novo se precisar dos que faltam"
                )
                self._registrar("AVISO", self.totais.aviso)
            fase = "grupos"
            self._gravar_retomada({"fase": "grupos", "start": 1})

        if fase == "grupos":
            self._progresso(70, "lendo grupos e membros")
            self.fase_grupos(portal_id)
            fase = "usuarios"
            self._gravar_retomada({"fase": "usuarios", "start": 1})

        if fase == "usuarios":
            self._progresso(85, "lendo usuários (só o nome de login)")
            self.fase_usuarios(portal_id)

        self._contar()
        self._gravar_retomada({"fase": "concluido", "start": 0})
        self._progresso(100, f"{self.totais.itens} itens, {self.totais.grupos} grupos, "
                             f"{self.totais.usuarios} usuários")
        return self.totais.como_json()


def mensagem_de_erro(e: Exception, token: str | None) -> str:
    """Texto curto e sem credencial para gravar em `plat.migracao_inventario.mensagem`."""
    if isinstance(e, ErroPortal):
        return redigir(f"{e.motivo}: {e.detalhe}" if e.detalhe else e.motivo, token)[:400]
    return redigir(f"{type(e).__name__}: {e}", token)[:400]
