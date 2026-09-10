"""Editor de metadado no Perfil MGB 2.0 da INDE (item L0-09-b-editor-iso-mgb; ISO 19115-1 núcleo).

Diferença para `app/catalogo/metadado.py` (item L0-09-metadado-catalogo): aquele módulo SÓ exporta um XML
ISO 19139/GMD somente-leitura a partir do item; este dá ao usuário um editor em abas ('essencial' e
'completo') sobre um metadado completo, armazenado em `plat.item.metadado_iso` (jsonb).

Dois grupos de campo, para não haver dois lugares de verdade (regra do item: "o título É sincronizado"):

- SINCRONIZADOS com o item: vêm de `plat.item.titulo/resumo/tags/creditos/termos_de_uso/extent` e são
  computados AO VIVO em `identificacao()`/`restricoes_sincronizadas()` — nunca duplicados no jsonb. Editar
  o título no editor grava em `plat.item.titulo` (mesmo caminho de `rotas_itens.editar_item`); editar o
  título pela tela "Visão geral" aparece no editor de metadado na próxima leitura, porque os dois leem a
  MESMA coluna.
- PRÓPRIOS do metadado: contato, restrições de licença, extensão temporal/espacial DECLARADA, sistema de
  referência, manutenção, formato de distribuição — ficam em `metadado_iso`, validados por `ESQUEMA_MGB`
  (JSON Schema Draft 2020-12). `extensao.espacial` pode divergir do extent real do item de propósito: é
  a declaração do produtor, e a divergência vira AVISO (`avisos_extent`), nunca bloqueio (refutação do item).

Linhagem (`qualidade_linhagem`) é sempre computada, nunca digitada: de `dados.procedencia` (item
L0-09-a-procedencia) e do histórico de eventos do item (`plat.evento`, alvo_tipo='item') — criação,
atualização de dados, importação. Não existe uma tabela "job por item" separada nesta plataforma; os
eventos JÁ SÃO o rastro determinístico de o que mudou o item e quando, e é isso que entra como
`processStep` da linhagem (D17: procedência errada é pior que nenhuma — melhor um processo real do
evento do que inventar um verbo genérico)."""

import datetime
from typing import Any

from jsonschema import Draft202012Validator

from app import limites
from app.auth.sessao import iso

CI_ROLE_CODE = (
    "resourceProvider", "custodian", "owner", "user", "distributor", "originator",
    "pointOfContact", "principalInvestigator", "processor", "publisher", "author",
)
MD_MAINTENANCE_FREQUENCY_CODE = (
    "continual", "daily", "weekly", "fortnightly", "monthly", "quarterly", "biannually",
    "annually", "asNeeded", "irregular", "notPlanned", "unknown",
)
ESTILOS = ("mgb2", "iso19115_3", "dublin_core")
ESTILO_PADRAO = "mgb2"

# ---------------------------------------------------------------------------- esquema (parte armazenada)
ESQUEMA_MGB: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "contato": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "organizacao": {"type": "string", "minLength": 1, "maxLength": 250},
                "individuo": {"type": "string", "minLength": 1, "maxLength": 250},
                "email": {"type": "string", "format": "email", "maxLength": 250},
                "papel": {"type": "string", "enum": list(CI_ROLE_CODE)},
            },
        },
        "restricoes": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "licenca": {"type": "string", "minLength": 1, "maxLength": 500},
                "uso_condicionado": {"type": "boolean"},
            },
        },
        "extensao": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "temporal": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "inicio": {"type": "string", "format": "date"},
                        "fim": {"type": "string", "format": "date"},
                    },
                },
                "espacial": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "xmin": {"type": "number", "minimum": -180, "maximum": 180},
                        "ymin": {"type": "number", "minimum": -90, "maximum": 90},
                        "xmax": {"type": "number", "minimum": -180, "maximum": 180},
                        "ymax": {"type": "number", "minimum": -90, "maximum": 90},
                    },
                },
            },
        },
        "sistema_referencia": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "codigo": {"type": "string", "minLength": 1, "maxLength": 20},
                "codespace": {"type": "string", "minLength": 1, "maxLength": 20},
            },
        },
        "manutencao": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "frequencia": {"type": "string", "enum": list(MD_MAINTENANCE_FREQUENCY_CODE)},
                "proxima_atualizacao": {"type": "string", "format": "date"},
            },
        },
        "distribuicao": {
            "type": "object",
            "additionalProperties": False,
            "properties": {"formato": {"type": "string", "minLength": 1, "maxLength": 100}},
        },
    },
}
_VALIDADOR = Draft202012Validator(ESQUEMA_MGB, format_checker=Draft202012Validator.FORMAT_CHECKER)

# caminho (ponto) -> rótulo em português, para a lista de faltantes do editor
CAMPOS_ESSENCIAIS: tuple[tuple[str, str], ...] = (
    ("identificacao.resumo", "resumo"),
    ("identificacao.palavras_chave", "palavras-chave (ao menos uma)"),
    ("contato.organizacao", "organização de contato"),
    ("contato.email", "e-mail de contato"),
    ("restricoes.licenca", "licença"),
    ("extensao.espacial", "extensão espacial (xmin, ymin, xmax, ymax)"),
    ("sistema_referencia.codigo", "código do sistema de referência"),
)
CAMPOS_COMPLETO_EXTRA: tuple[tuple[str, str], ...] = (
    ("contato.individuo", "responsável individual"),
    ("contato.papel", "papel do contato"),
    ("extensao.temporal.inicio", "início da extensão temporal"),
    ("extensao.temporal.fim", "fim da extensão temporal"),
    ("manutencao.frequencia", "frequência de manutenção"),
    ("distribuicao.formato", "formato de distribuição"),
)


class ErroMetadadoInvalido(ValueError):
    """`erros` é a lista [{campo, erro, regra}], mesmo contrato de `app.catalogo.tipos.erros_de`."""

    def __init__(self, erros: list[dict]):
        self.erros = erros
        super().__init__("; ".join(f"{e['campo']}: {e['erro']}" for e in erros) or "metadado inválido")


def _get(d: dict, caminho: str):
    cur = d
    for parte in caminho.split("."):
        if not isinstance(cur, dict) or parte not in cur:
            return None
        cur = cur[parte]
    return cur


def tamanho_ok(stored: dict) -> bool:
    import json

    return len(json.dumps(stored, ensure_ascii=False).encode("utf-8")) <= limites.METADADO_ISO_BYTES_MAX


def validar_estrutura(stored: dict) -> None:
    """Levanta ErroMetadadoInvalido (campo, erro, regra) se `stored` não bater com ESQUEMA_MGB ou tiver
    datas fora de ordem. É o mesmo tipo de contrato 422 que `app.catalogo.tipos.erros_de` já usa."""
    if not isinstance(stored, dict):
        raise ErroMetadadoInvalido(
            [{"campo": "(raiz)", "erro": "o metadado precisa ser um objeto JSON", "regra": "type"}]
        )
    erros = []
    for e in sorted(_VALIDADOR.iter_errors(stored), key=lambda e: list(e.absolute_path)):
        caminho = ".".join(str(p) for p in e.absolute_path)
        erros.append({"campo": caminho or "(raiz)", "erro": e.message[:500], "regra": e.validator})
    ini = _get(stored, "extensao.temporal.inicio")
    fim = _get(stored, "extensao.temporal.fim")
    if ini and fim:
        try:
            if datetime.date.fromisoformat(fim) < datetime.date.fromisoformat(ini):
                erros.append(
                    {
                        "campo": "extensao.temporal.fim",
                        "erro": "data de fim anterior à de início",
                        "regra": "ordem_datas",
                    }
                )
        except ValueError:
            pass  # já apontado pelo format-checker acima
    if erros:
        raise ErroMetadadoInvalido(erros)


TOLERANCIA_EXTENT_GRAUS = 0.01


def avisos_extent(stored: dict, item_row: dict) -> list[dict]:
    """Aviso (não bloqueio, refutação do item) quando a extensão espacial DECLARADA no metadado diverge do
    extent registrado no item (o 'dado')."""
    esp = _get(stored, "extensao.espacial")
    if not esp or item_row.get("xmin") is None:
        return []
    reais = {"xmin": item_row["xmin"], "ymin": item_row["ymin"], "xmax": item_row["xmax"], "ymax": item_row["ymax"]}
    for chave, real in reais.items():
        declarado = esp.get(chave)
        if declarado is not None and abs(float(declarado) - float(real)) > TOLERANCIA_EXTENT_GRAUS:
            return [
                {
                    "campo": "extensao.espacial",
                    "aviso": "a extensão espacial declarada diverge do extent registrado no item (o dado); "
                    f"confira antes de publicar (declarado {esp}, item {reais})",
                }
            ]
    return []


def espacial_efetivo(stored: dict, item_row: dict) -> dict | None:
    esp = _get(stored, "extensao.espacial")
    if esp and all(k in esp and esp[k] is not None for k in ("xmin", "ymin", "xmax", "ymax")):
        return esp
    if item_row.get("xmin") is not None:
        return {
            "xmin": item_row["xmin"], "ymin": item_row["ymin"], "xmax": item_row["xmax"], "ymax": item_row["ymax"],
        }
    return None


_DESCRICAO_EVENTO = {
    "itens/adicionar": "item criado",
    "itens/atualizar": "metadado ou dados do item alterados",
    "itens/dados_migrar": "dados migrados para esquema novo do tipo",
    "itens/metadado_iso_atualizar": "metadado ISO/MGB alterado pelo editor",
}


def linhagem(item_row: dict, eventos: list[dict]) -> dict:
    """Alimentada pela procedência (item L0-09-a) e pelos eventos do item (o rastro de jobs/edições que a
    plataforma já grava em `plat.evento`) — nunca digitada à mão."""
    dados = item_row.get("dados") or {}
    procedencia = dados.get("procedencia") if isinstance(dados, dict) else None
    partes = []
    if procedencia:
        for chave, rotulo in (
            ("fonte", "fonte"), ("url", "endereço"), ("licenca", "licença"),
            ("data_do_dado", "data do dado"), ("metodo", "método"), ("confianca", "confiança"),
        ):
            v = procedencia.get(chave)
            if v:
                partes.append(f"{rotulo}: {v}")
    processos = [
        {
            "evento": ev["tipo"],
            "em": iso(ev["em"]),
            "descricao": _DESCRICAO_EVENTO.get(ev["tipo"], ev["tipo"]),
            "propriedades": ev.get("propriedades") or {},
        }
        for ev in eventos
    ]
    return {
        "declaracao": "; ".join(partes) or None,
        "fontes": [procedencia] if procedencia else [],
        "processos": processos,
    }


def identificacao(item_row: dict) -> dict:
    """Bloco 100% sincronizado com o item — computado ao vivo, nunca lido de `metadado_iso`."""
    return {
        "titulo": item_row["titulo"],
        "resumo": item_row.get("resumo"),
        "palavras_chave": list(item_row.get("tags") or []),
        "creditos": item_row.get("creditos"),
    }


def visao(item_row: dict, stored: dict, eventos: list[dict], base_url: str) -> dict:
    """Monta a leitura completa (identificação sincronizada + parte própria armazenada + linhagem
    computada + distribuição). É o que `GET /api/itens/{id}/metadado` devolve."""
    stored = stored or {}
    item_id = str(item_row["id"])
    dist = dict(stored.get("distribuicao") or {})
    dist["url_online"] = [
        f"{base_url}/api/itens/{item_id}",
        f"{base_url}/api/itens/{item_id}/metadado.xml",
    ]
    return {
        "identificacao": identificacao(item_row),
        "restricoes": {**(stored.get("restricoes") or {}), "termos_de_uso": item_row.get("termos_de_uso")},
        "contato": dict(stored.get("contato") or {}),
        "extensao": {
            "temporal": dict((stored.get("extensao") or {}).get("temporal") or {}),
            "espacial": espacial_efetivo(stored, item_row),
        },
        "sistema_referencia": dict(stored.get("sistema_referencia") or {}),
        "manutencao": dict(stored.get("manutencao") or {}),
        "distribuicao": dist,
        "qualidade_linhagem": linhagem(item_row, eventos),
    }


def faltantes(v: dict, modo: str) -> list[dict]:
    """`modo` = 'essencial' (só a lista curta) ou 'completo' (essencial + o resto do perfil)."""
    campos = list(CAMPOS_ESSENCIAIS)
    if modo == "completo":
        campos = campos + list(CAMPOS_COMPLETO_EXTRA)
    saida = []
    for caminho, rotulo in campos:
        valor = _get(v, caminho)
        vazio = valor is None or valor == "" or valor == {} or (isinstance(valor, list) and not valor)
        if vazio:
            saida.append({"campo": caminho, "rotulo": rotulo})
    return saida


# ---------------------------------------------------------------------------- estilo por inquilino (D do item:
# "apenas muda a apresentação, o armazenamento é um só")
def estilo_do_tenant(config: dict | None) -> str:
    e = (config or {}).get("estilo_metadado")
    return e if e in ESTILOS else ESTILO_PADRAO


_ROTULOS_ISO19115_3 = {
    "identificacao.titulo": "mdb:identificationInfo > mri:citation > cit:title",
    "identificacao.resumo": "mri:abstract",
    "identificacao.palavras_chave": "mri:descriptiveKeywords",
    "contato.organizacao": "mdb:contact > cit:party > cit:name",
    "restricoes.licenca": "mri:resourceConstraints > mco:MD_LegalConstraints",
    "extensao.espacial": "mri:extent > gex:EX_GeographicBoundingBox",
    "extensao.temporal": "mri:extent > gex:EX_TemporalExtent",
    "sistema_referencia.codigo": "mdb:referenceSystemInfo > mrs:MD_ReferenceSystem",
    "manutencao.frequencia": "mdb:metadataMaintenance > mmi:MD_MaintenanceInformation",
    "qualidade_linhagem.declaracao": "mdq:DQ_DataQuality > mrl:LI_Lineage > mrl:statement",
}
_ROTULOS_DUBLIN_CORE = {
    "identificacao.titulo": "dc:title",
    "identificacao.resumo": "dc:description",
    "identificacao.palavras_chave": "dc:subject",
    "identificacao.creditos": "dc:creator",
    "contato.organizacao": "dc:publisher",
    "restricoes.licenca": "dc:rights",
    "extensao.espacial": "dc:coverage",
    "extensao.temporal": "dc:date",
    "sistema_referencia.codigo": "dc:relation",
    "manutencao.frequencia": None,  # sem equivalente em Dublin Core simples — perfil mais pobre, de propósito
    "qualidade_linhagem.declaracao": "dc:source",
}


def formatar_estilo(v: dict, estilo: str) -> dict:
    """Só apresentação: rótulo/agrupamento do MESMO `v` (a leitura de `visao()`). Nunca lê nem escreve
    outro armazenamento — é a regra do item ('um estilo por inquilino... o armazenamento é um só')."""
    if estilo == "mgb2" or estilo not in ESTILOS:
        return {"estilo": "mgb2", "perfil": "Perfil MGB 2.0 (INDE)", "campos": v}
    rotulos = _ROTULOS_ISO19115_3 if estilo == "iso19115_3" else _ROTULOS_DUBLIN_CORE
    perfil = "ISO 19115-3:2016 (mdb)" if estilo == "iso19115_3" else "Dublin Core (simples, 15 elementos)"
    linhas = []
    for caminho, rotulo_campo in rotulos.items():
        if rotulo_campo is None:
            continue
        linhas.append({"caminho": caminho, "rotulo_padrao": rotulo_campo, "valor": _get(v, caminho)})
    return {"estilo": estilo, "perfil": perfil, "campos": v, "apresentacao": linhas}
