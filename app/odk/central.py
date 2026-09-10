"""Cliente da API do ODK Central (item L2-07-e-odk-central-ponte; Apache-2.0, docs.getodk.org/central-api).

Só o que a ponte precisa, e tudo pelo `app.conexao.seguranca.buscar_seguro` do L6-02-a — nunca `httpx` direto:
assim a defesa de SSRF (esquema, userinfo, IP privado, DNS rebinding, redirecionamento revalidado, credencial
que não atravessa mudança de origem) vale para o Central igual vale para um WMS.

Endpoints usados (docs de 2026-09-08):
  POST /v1/projects/{p}/forms?publish=true            publica o XLSForm (planilha .xlsx no corpo)
  GET  /v1/projects/{p}/forms/{xmlFormId}             estado do formulário publicado
  GET  /v1/projects/{p}/forms/{xmlFormId}.svc/Submissions   envios por OData ($top/$skip/$count/$expand)
  GET  /v1/projects/{p}/forms/{f}/submissions/{i}/attachments          lista de anexos do envio
  GET  /v1/projects/{p}/forms/{f}/submissions/{i}/attachments/{nome}   um anexo
  GET  /v1/projects/{p}/datasets/{nome}/entities      Entities do dataset (lista de escolhas)

Autenticação: cabeçalho `Authorization: Bearer <token>`, com o token guardado como credencial da conexão
(cifrado em `plat.conexao.credencial_cifrada`). É o mesmo cabeçalho que o Central aceita para sessão
(`POST /v1/sessions`) e para App User — a plataforma NUNCA guarda e-mail e senha do Central: quem cadastra a
conexão cola um token, e trocar o token é editar a conexão. Decisão registrada no ADR do item.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import quote, urlencode

from app import limites
from app.conexao import seguranca

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class ErroCentral(Exception):
    """Falha ao falar com o Central. `motivo` é curto e estável (vai para a tela e para o log); `status` é o
    HTTP quando houve resposta, e None quando nem chegou a haver (URL insegura, DNS, tempo esgotado)."""

    def __init__(self, motivo: str, status: int | None = None, detalhe: str | None = None):
        self.motivo = motivo
        self.status = status
        self.detalhe = detalhe
        super().__init__(f"{motivo} (status={status})")


@dataclass(frozen=True)
class Central:
    """Uma conexão `odk_central` já resolvida: URL base e token em memória (nunca gravado, nunca logado)."""

    url_base: str
    token: str | None = None

    def _cabecalhos(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        c = dict(extra or {})
        if self.token:
            c["Authorization"] = f"Bearer {self.token}"
        return c

    def _url(self, caminho: str, consulta: dict | None = None) -> str:
        url = self.url_base.rstrip("/") + caminho
        return url + ("?" + urlencode(consulta) if consulta else "")

    def _pedir(self, caminho: str, *, metodo: str = "GET", consulta: dict | None = None,
               corpo: bytes | None = None, tipo_corpo: str | None = None, cabecalhos: dict | None = None,
               max_bytes: int = limites.ODK_RESPOSTA_MAX_BYTES) -> bytes:
        extra = dict(cabecalhos or {})
        if tipo_corpo:
            extra["Content-Type"] = tipo_corpo
        r = seguranca.buscar_seguro(
            self._url(caminho, consulta), metodo=metodo, cabecalhos=self._cabecalhos(extra),
            timeout_conectar=limites.CONEXAO_CONECTAR_TIMEOUT_S, timeout_ler=limites.ODK_LER_TIMEOUT_S,
            max_bytes=max_bytes, guardar_corpo=True, corpo_envio=corpo,
        )
        if not r.ok:
            if r.status in (401, 403):
                raise ErroCentral("credencial_recusada", r.status, r.mensagem)
            raise ErroCentral(r.mensagem or "falha", r.status, None)
        return r.corpo

    def _json(self, caminho: str, **kw):
        bruto = self._pedir(caminho, **kw)
        try:
            return json.loads(bruto.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as e:
            raise ErroCentral("resposta_nao_e_json", None, str(e)[:200]) from e

    # -- formulários ------------------------------------------------------------------------------------
    def publicar_xlsform(self, projeto: int, conteudo: bytes, form_id_alternativo: str) -> dict:
        """POST /v1/projects/{p}/forms?publish=true com a planilha no corpo. O Central converte o XLSForm e
        devolve o formulário publicado (xmlFormId, version, hash, publishedAt)."""
        if len(conteudo) > limites.XLSFORM_TAMANHO_MAX:
            raise ErroCentral("xlsform_grande_demais", None, f"{len(conteudo)} bytes")
        return self._json(
            f"/v1/projects/{int(projeto)}/forms", metodo="POST",
            consulta={"publish": "true", "ignoreWarnings": "true"}, corpo=conteudo, tipo_corpo=XLSX,
            cabecalhos={"X-XlsForm-FormId-Fallback": form_id_alternativo[:255]},
        )

    def formulario(self, projeto: int, xml_form_id: str) -> dict:
        return self._json(f"/v1/projects/{int(projeto)}/forms/{quote(xml_form_id, safe='')}")

    # -- envios (OData) ---------------------------------------------------------------------------------
    def envios(self, projeto: int, xml_form_id: str, *, teto: int = limites.ODK_ENVIOS_MAX_POR_EXECUCAO):
        """Gera as linhas de `Submissions` do OData, paginando por `$top`/`$skip` até `teto` ou até a página
        vir curta. `$expand=*` traz as repetições aninhadas na mesma linha (o Central as expõe como tabelas
        separadas quando não se pede a expansão)."""
        caminho = f"/v1/projects/{int(projeto)}/forms/{quote(xml_form_id, safe='')}.svc/Submissions"
        lidos = 0
        for pagina in range(limites.ODK_PAGINAS_MAX):
            falta = teto - lidos
            if falta <= 0:
                return
            top = min(limites.ODK_PAGINA_ENVIOS, falta)
            doc = self._json(caminho, consulta={"$top": top, "$skip": pagina * limites.ODK_PAGINA_ENVIOS,
                                                "$count": "true", "$expand": "*"})
            linhas = doc.get("value")
            if not isinstance(linhas, list):
                raise ErroCentral("odata_sem_value", None, None)
            for linha in linhas:
                if isinstance(linha, dict):
                    yield linha
                    lidos += 1
            if len(linhas) < top:
                return

    def anexos_do_envio(self, projeto: int, xml_form_id: str, instance_id: str) -> list[dict]:
        doc = self._json(
            f"/v1/projects/{int(projeto)}/forms/{quote(xml_form_id, safe='')}"
            f"/submissions/{quote(instance_id, safe='')}/attachments"
        )
        return [a for a in doc if isinstance(a, dict)] if isinstance(doc, list) else []

    def anexo(self, projeto: int, xml_form_id: str, instance_id: str, nome: str) -> bytes:
        return self._pedir(
            f"/v1/projects/{int(projeto)}/forms/{quote(xml_form_id, safe='')}"
            f"/submissions/{quote(instance_id, safe='')}/attachments/{quote(nome, safe='')}",
            max_bytes=limites.ANEXO_TAMANHO_MAX,
        )

    # -- entidades --------------------------------------------------------------------------------------
    def entidades(self, projeto: int, dataset: str) -> list[dict]:
        doc = self._json(f"/v1/projects/{int(projeto)}/datasets/{quote(dataset, safe='')}/entities")
        if not isinstance(doc, list):
            raise ErroCentral("entidades_sem_lista", None, None)
        return doc[: limites.ODK_ENTIDADES_MAX]
