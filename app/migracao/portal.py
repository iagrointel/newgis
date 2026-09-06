"""Cliente só-leitura de um Portal for ArcGIS / ArcGIS Online de terceiro
(item L2-08-a-leitor-portal-inventario).

Só-leitura é literal: este módulo só emite GET, e o único POST que existe é `generateToken`, que não altera
nada no portal do cliente (troca usuário/senha por um token de sessão). Não há aqui nenhuma chamada a
nenhum verbo de escrita da API do Portal (criação, alteração, compartilhamento ou remoção de item). A lista
de caminhos que o módulo sabe montar está toda neste arquivo e é conferida por teste
(`tests/unit/test_migracao_classificacao.py::test_modulo_so_monta_caminho_de_leitura`).

Segurança de rede: NÃO abre socket por conta própria. Reusa `app.conexao.seguranca` (item L6-02-a) —
`validar_url` (esquema, userinfo, IP privado/loopback/link-local, DNS) e `cliente_pinado` (conexão fixada no
IP já validado, sem segunda consulta de DNS, sem seguir redirecionamento sozinho). Um portal que responde
302 tem cada salto revalidado do zero, igual ao resto da casa.

Token: viaja no cabeçalho `X-Esri-Authorization: Bearer <token>`, nunca no caminho nem na query. Essa é a
diferença que faz a cláusula "token nunca aparece em log" ser verdadeira por construção e não por um filtro
de texto: se o token fosse `?token=...`, toda URL registrada em log de job, log de acesso do nginx ou
mensagem de erro carregaria a credencial do cliente. Portal for ArcGIS 10.7+ e ArcGIS Online aceitam o
cabeçalho; `REDIGIR` existe só como rede de segurança para mensagem de erro devolvida pelo próprio portal.

Limite de uso do portal: 429 (e 503 com Retry-After) entram em espera exponencial, respeitando o
`Retry-After` quando o portal manda, até `TENTATIVAS_429`. Erro de rede no meio NÃO é engolido: sobe como
`ErroRede`, e quem chama (o job de inventário) grava o ponto de retomada e deixa a tentativa seguinte
continuar de onde parou.

Fontes (lidas em setembro de 2026):
  https://developers.arcgis.com/rest/users-groups-and-items/root/
  https://developers.arcgis.com/rest/users-groups-and-items/portal-self/
  https://developers.arcgis.com/rest/users-groups-and-items/generate-token/
  https://developers.arcgis.com/rest/users-groups-and-items/search/
  https://developers.arcgis.com/rest/users-groups-and-items/item/
  https://developers.arcgis.com/rest/users-groups-and-items/item-data/
  https://developers.arcgis.com/rest/users-groups-and-items/item-resources/
  https://developers.arcgis.com/rest/users-groups-and-items/related-items/
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx

from app.conexao import seguranca

TIMEOUT_CONECTAR_S = 5.0
TIMEOUT_LER_S = 20.0
RESPOSTA_MAX_BYTES = 8 * 1024 * 1024      # item/data de um web map grande passa de 1 MiB do teste de saúde
TENTATIVAS_429 = 4                        # 1 tentativa + 3 esperas (0,5 s, 1 s, 2 s, ou o Retry-After)
ESPERA_INICIAL_S = 0.5
ESPERA_MAX_S = 30.0
PAGINA_PADRAO = 100                       # `num` máximo aceito por /sharing/rest/search
REDIRECT_MAX = 3


class ErroPortal(Exception):
    """Falha nomeada da conversa com o portal. `motivo` é um código curto (nunca frase livre) para virar
    `erro` no contrato da API e rótulo em teste."""

    def __init__(self, motivo: str, detalhe: str = ""):
        self.motivo = motivo
        self.detalhe = detalhe[:400]
        super().__init__(f"{motivo}: {detalhe}" if detalhe else motivo)


class ErroRede(ErroPortal):
    """Corte de rede, tempo esgotado ou 5xx: vale a pena tentar de novo mais tarde, do ponto de retomada."""


def redigir(texto: str, token: str | None) -> str:
    """Troca o token por `***` em qualquer texto que vá para log, mensagem de erro ou banco."""
    if not token or not texto:
        return texto
    return texto.replace(token, "***")


def _juntar(base: str, caminho: str, parametros: dict) -> str:
    partes = urlsplit(base)
    raiz = partes.path.rstrip("/")
    novo = f"{raiz}/{caminho.lstrip('/')}" if caminho.strip("/") else (raiz or "/")
    return urlunsplit((partes.scheme, partes.netloc, novo, urlencode(parametros, doseq=True), ""))


@dataclass
class ClientePortal:
    """Conversa com UM portal. `base` é a raiz do portal (`https://<host>/portal` ou
    `https://<org>.maps.arcgis.com`), sem o `/sharing/rest` — o cliente monta os caminhos."""

    base: str
    token: str | None = None
    pausa: object = time.sleep                 # injetável no teste (nunca dorme de verdade lá)
    pedidos: int = field(default=0, init=False)   # quantos GET saíram (medida de retomada)
    esperas_429: int = field(default=0, init=False)

    # ------------------------------------------------------------------ transporte
    def _cabecalhos(self) -> dict[str, str]:
        c = {"Accept": "application/json", "User-Agent": "plat-migracao/1 (inventario somente leitura)"}
        if self.token:
            c["X-Esri-Authorization"] = f"Bearer {self.token}"
        return c

    def _requisitar(self, metodo: str, url: str, dados: dict | None = None) -> tuple[int, bytes, dict]:
        """Um pedido HTTP seguro (validação de SSRF + IP pinado), sem seguir redirecionamento sozinho."""
        alvo = url
        for _ in range(REDIRECT_MAX + 1):
            try:
                validada = seguranca.validar_url(alvo)
            except seguranca.ErroURLInsegura as e:
                raise ErroPortal("url_insegura", e.motivo) from e
            with seguranca.cliente_pinado(
                validada, timeout_conectar=TIMEOUT_CONECTAR_S, timeout_ler=TIMEOUT_LER_S
            ) as cliente:
                try:
                    with cliente.stream(metodo, alvo, headers=self._cabecalhos(), data=dados) as r:
                        lido = 0
                        pedacos = []
                        for pedaco in r.iter_bytes():
                            lido += len(pedaco)
                            if lido > RESPOSTA_MAX_BYTES:
                                raise ErroPortal("resposta_grande_demais", f"{alvo.split('?')[0]} > "
                                                                          f"{RESPOSTA_MAX_BYTES} bytes")
                            pedacos.append(pedaco)
                        status, corpo, cabecalhos = r.status_code, b"".join(pedacos), dict(r.headers)
                except httpx.TimeoutException as e:
                    raise ErroRede("tempo_esgotado", alvo.split("?")[0]) from e
                except httpx.HTTPError as e:
                    raise ErroRede("erro_de_conexao", f"{type(e).__name__} em {alvo.split('?')[0]}") from e
            if status in (301, 302, 303, 307, 308):
                local = cabecalhos.get("location")
                if not local:
                    raise ErroPortal("redirecionamento_sem_location", alvo.split("?")[0])
                alvo = str(httpx.URL(alvo).join(local))
                continue
            return status, corpo, cabecalhos
        raise ErroPortal("redirecionamentos_demais", alvo.split("?")[0])

    def _json(self, metodo: str, url: str, dados: dict | None = None) -> dict:
        """Pedido com espera pelo limite de uso (429/503) e resposta obrigatoriamente JSON.

        O Portal responde HTTP 200 mesmo quando recusa: o erro vem no corpo, em `{"error": {...}}`. Por isso
        a checagem de erro é do CORPO, não do status."""
        espera = ESPERA_INICIAL_S
        for tentativa in range(TENTATIVAS_429):
            self.pedidos += 1
            status, corpo, cabecalhos = self._requisitar(metodo, url, dados)
            if status in (429, 503):
                if tentativa == TENTATIVAS_429 - 1:
                    raise ErroRede("limite_de_uso_do_portal", f"HTTP {status} depois de {TENTATIVAS_429} tentativas")
                retry = cabecalhos.get("retry-after")
                segundos = espera
                if retry:
                    try:
                        segundos = min(float(retry), ESPERA_MAX_S)
                    except ValueError:
                        pass
                self.esperas_429 += 1
                self.pausa(segundos)
                espera = min(espera * 2, ESPERA_MAX_S)
                continue
            if status >= 500:
                raise ErroRede("erro_do_portal", f"HTTP {status}")
            if status >= 400:
                raise ErroPortal("http_erro", f"HTTP {status}")
            try:
                dado = json.loads(corpo.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                raise ErroPortal(
                    "resposta_nao_e_json",
                    f"{url.split('?')[0]} respondeu {cabecalhos.get('content-type', 'sem content-type')}",
                ) from e
            if not isinstance(dado, dict):
                raise ErroPortal("resposta_nao_e_objeto", url.split("?")[0])
            erro = dado.get("error")
            if isinstance(erro, dict):
                codigo = erro.get("code")
                mensagem = redigir(str(erro.get("message") or ""), self.token)
                if codigo in (498, 499, 401, 403):
                    raise ErroPortal("credencial_recusada", f"code={codigo} {mensagem}")
                raise ErroPortal("erro_do_portal", f"code={codigo} {mensagem}")
            return dado
        raise ErroRede("limite_de_uso_do_portal", "espera esgotada")

    def obter(self, caminho: str, **parametros) -> dict:
        parametros.setdefault("f", "json")
        return self._json("GET", _juntar(self.base, caminho, parametros))

    # ------------------------------------------------------------------ token
    @staticmethod
    def gerar_token(base: str, usuario: str, senha: str, referer: str, expiracao_min: int = 60) -> str:
        """`/sharing/rest/generateToken` com usuário/senha do cliente. A senha existe só dentro desta
        função — nunca é gravada, nunca volta no retorno, nunca entra em log."""
        cliente = ClientePortal(base=base)
        dado = cliente._json(
            "POST",
            _juntar(base, "sharing/rest/generateToken", {}),
            dados={"username": usuario, "password": senha, "client": "referer", "referer": referer,
                   "expiration": str(int(expiracao_min)), "f": "json"},
        )
        token = dado.get("token")
        if not token:
            raise ErroPortal("token_nao_emitido", "generateToken respondeu sem campo token")
        return str(token)

    # ------------------------------------------------------------------ leitura do portal
    def raiz(self) -> dict:
        """`/sharing/rest?f=json` — versão do portal. Também serve de porta: uma URL que não é Portal não
        responde JSON com `currentVersion`."""
        return self.obter("sharing/rest")

    def portal_self(self) -> dict:
        """`/sharing/rest/portals/self` — identidade da organização (id, nome, urlKey, usuário corrente)."""
        dado = self.obter("sharing/rest/portals/self")
        if "id" not in dado:
            raise ErroPortal("nao_e_portal", "portals/self respondeu JSON sem o campo id")
        return dado

    def confirmar_portal(self) -> dict:
        """Confere que a URL é mesmo um Portal/AGOL ANTES de qualquer varredura. Levanta `nao_e_portal`
        (erro nomeado, nunca 500) quando a URL responde outra coisa — uma página HTML, um GeoServer, um
        JSON qualquer."""
        try:
            raiz = self.raiz()
        except ErroPortal as e:
            if e.motivo in ("resposta_nao_e_json", "resposta_nao_e_objeto", "http_erro"):
                raise ErroPortal("nao_e_portal", f"{self.base} não responde o REST do Portal ({e.motivo})") from e
            raise
        if "currentVersion" not in raiz:
            raise ErroPortal("nao_e_portal", "a raiz do REST respondeu JSON sem currentVersion")
        return raiz

    def buscar_itens(self, consulta: str, inicio: int = 1, por_pagina: int = PAGINA_PADRAO) -> dict:
        """`/sharing/rest/search` paginado. Devolve o objeto cru (com `nextStart`, `total`, `results`)."""
        return self.obter("sharing/rest/search", q=consulta, start=inicio, num=por_pagina, sortField="created",
                          sortOrder="asc")

    def item(self, item_id: str) -> dict:
        return self.obter(f"sharing/rest/content/items/{item_id}")

    def item_dados(self, item_id: str) -> dict:
        """`item/data` — o JSON do documento (web map, dashboard...). Item binário não tem JSON: devolve {}."""
        try:
            return self.obter(f"sharing/rest/content/items/{item_id}/data")
        except ErroPortal as e:
            if e.motivo in ("resposta_nao_e_json", "resposta_nao_e_objeto", "resposta_grande_demais"):
                return {}
            raise

    def item_recursos(self, item_id: str) -> list[dict]:
        dado = self.obter(f"sharing/rest/content/items/{item_id}/resources", num=100)
        return list(dado.get("resources") or [])

    def item_relacionados(self, item_id: str, relacao: str, direcao: str = "forward") -> list[dict]:
        dado = self.obter(f"sharing/rest/content/items/{item_id}/relatedItems",
                          relationshipType=relacao, direction=direcao)
        return list(dado.get("relatedItems") or [])

    def grupos(self, portal_id: str, inicio: int = 1, por_pagina: int = PAGINA_PADRAO) -> dict:
        return self.obter(f"sharing/rest/portals/{portal_id}/groups", start=inicio, num=por_pagina)

    def membros_grupo(self, grupo_id: str) -> dict:
        return self.obter(f"sharing/rest/community/groups/{grupo_id}/users")

    def usuarios(self, portal_id: str, inicio: int = 1, por_pagina: int = PAGINA_PADRAO) -> dict:
        return self.obter(f"sharing/rest/portals/{portal_id}/users", start=inicio, num=por_pagina)

    # ------------------------------------------------------------------ serviço hospedado
    def servico(self, url_servico: str) -> dict:
        """Descrição de um FeatureServer/MapServer (`?f=json`): camadas, tabelas, tamanho declarado."""
        return self._json("GET", _juntar(url_servico, "", {"f": "json"}))

    def contagem_camada(self, url_servico: str, camada_id: int) -> int | None:
        """`<servico>/<id>/query?where=1=1&returnCountOnly=true`. Devolve None quando o serviço recusa a
        contagem (camada sem permissão de consulta, por exemplo) — nunca zero por omissão."""
        try:
            dado = self._json(
                "GET",
                _juntar(url_servico, f"{camada_id}/query",
                        {"where": "1=1", "returnCountOnly": "true", "f": "json"}),
            )
        except ErroPortal as e:
            if isinstance(e, ErroRede):
                raise
            return None
        valor = dado.get("count")
        return int(valor) if isinstance(valor, (int, float)) else None
