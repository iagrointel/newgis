"""Pacote de documentos entre inquilinos (item L5-37-pacotes-modelos-entre-inquilinos), a parte que não
precisa de banco: forma canônica e assinatura, leitura do zip (inclusive as recusas do adversário),
regeração de ids sem quebrar referência e comparação de esquema campo a campo.

O que é provado aqui, cláusula por cláusula do portão:
  - "pacote assinado (sha256 do conteúdo) e conferido": `montar` grava `sha256_conteudo`; um byte trocado em
    QUALQUER lugar (manifesto ou documento) faz `ler` levantar `pacote_adulterado`; e o mesmo valor é
    reproduzido por ferramenta de fora (`json.dumps(sort_keys=True, separators=(',',':'))` = `jq -cS`).
  - "ids regenerados sem quebrar referências": `mapa_de_ids` + `reescrever` trocam UUID de documento, ULID de
    nó e UUID de fonte numa passada, e nenhum id do pacote sobra no resultado.
  - "esquema incompatível listado campo a campo": `comparar_esquema`.
  - refutação do `../` no zip e do id de outro inquilino: `ler` e `reescrever`.
"""

import io
import json
import zipfile

import pytest

from app.catalogo import pacote
from app.catalogo.documento import ULID_RE, gerar_ulid, sha256_canonico
from app.erros import ErroAPI

UUID_A = "11111111-1111-4111-8111-111111111111"
UUID_MAPA = "22222222-2222-4222-8222-222222222222"
UUID_CAMADA = "33333333-3333-4333-8333-333333333333"
UUID_ESTRANHO = "99999999-9999-4999-8999-999999999999"


def documento_app(no_a: str, no_b: str) -> dict:
    return {
        "id": UUID_A,
        "tipo": "app",
        "titulo": "app de teste",
        "resumo": None,
        "descricao": None,
        "tags": [],
        "creditos": None,
        "termos_de_uso": None,
        "dados": {
            "tipo": "app",
            "esquema_versao": 2,
            "corpo": {
                "mapas": [UUID_MAPA],
                "nos": [{"id": no_a, "tipo": "visor_mapa", "camada": UUID_CAMADA}, {"id": no_b, "tipo": "legenda"}],
                "ligacoes": [{"origem": no_a, "alvo": no_b}],
            },
        },
    }


def montar_zip(manifesto: dict, documentos: list[dict], nome_extra: str | None = None) -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            pacote.ARQUIVO_MANIFESTO,
            json.dumps(manifesto, sort_keys=True, ensure_ascii=False, separators=(",", ":")),
        )
        for d in documentos:
            zf.writestr(
                f"{pacote.PASTA_DOCUMENTOS}{d['id']}.json",
                json.dumps(d, sort_keys=True, ensure_ascii=False, separators=(",", ":")),
            )
        if nome_extra:
            zf.writestr(nome_extra, "conteudo qualquer")
    return saida.getvalue()


def manifesto_de(documentos: list[dict], fontes: list[dict]) -> dict:
    m = {
        "formato": pacote.FORMATO,
        "versao_formato": pacote.VERSAO_FORMATO,
        "criado_em": "2026-09-08T10:00:00+00:00",
        "origem": {"inquilino": "demo"},
        "raiz": documentos[-1]["id"],
        "tipo_raiz": documentos[-1]["tipo"],
        "titulo_raiz": documentos[-1]["titulo"],
        "documentos": [
            {
                "id": d["id"],
                "tipo": d["tipo"],
                "titulo": d["titulo"],
                "arquivo": f"{pacote.PASTA_DOCUMENTOS}{d['id']}.json",
                "sha256": sha256_canonico(d),
            }
            for d in documentos
        ],
        "fontes": fontes,
    }
    m["sha256_conteudo"] = sha256_canonico(m)
    return m


FONTE = {
    "id": UUID_CAMADA,
    "tipo": "camada_vetorial",
    "titulo": "camada de teste",
    "campos": [{"nome": "codigo", "tipo": "text"}, {"nome": "area_ha", "tipo": "numeric"}],
    "geometria": "MultiPolygon",
    "srid": 4674,
}


def pacote_minimo() -> tuple[bytes, dict, dict]:
    doc = documento_app(gerar_ulid(), gerar_ulid())
    m = manifesto_de([doc], [FONTE])
    return montar_zip(m, [doc]), m, doc


# ---------------------------------------------------------------- assinatura
def test_pacote_valido_abre_e_traz_manifesto_e_documento():
    bruto, m, doc = pacote_minimo()
    manifesto, documentos = pacote.ler(bruto)
    assert manifesto["sha256_conteudo"] == m["sha256_conteudo"]
    assert list(documentos) == [doc["id"]]


def test_assinatura_reproduzivel_por_ferramenta_de_fora():
    """O mesmo número que a API devolve sai de `json.dumps(sort_keys, separators)` — o que `jq -cS` faz."""
    _, m, _ = pacote_minimo()
    sem_assinatura = {k: v for k, v in m.items() if k != "sha256_conteudo"}
    import hashlib

    texto = json.dumps(sem_assinatura, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    assert hashlib.sha256(texto.encode("utf-8")).hexdigest() == m["sha256_conteudo"]


def test_byte_trocado_no_documento_e_recusado():
    doc = documento_app(gerar_ulid(), gerar_ulid())
    m = manifesto_de([doc], [FONTE])
    adulterado = {**doc, "titulo": "app de teste "}  # um espaço a mais
    with pytest.raises(ErroAPI) as e:
        pacote.ler(montar_zip(m, [adulterado]))
    assert e.value.erro == "pacote_adulterado"


def test_byte_trocado_no_manifesto_e_recusado():
    doc = documento_app(gerar_ulid(), gerar_ulid())
    m = manifesto_de([doc], [FONTE])
    m["titulo_raiz"] = "outro título"
    with pytest.raises(ErroAPI) as e:
        pacote.ler(montar_zip(m, [doc]))
    assert e.value.erro == "pacote_adulterado"


# ---------------------------------------------------------------- refutação: zip hostil
def test_caminho_com_ponto_ponto_no_zip_e_recusado():
    doc = documento_app(gerar_ulid(), gerar_ulid())
    m = manifesto_de([doc], [FONTE])
    with pytest.raises(ErroAPI) as e:
        pacote.ler(montar_zip(m, [doc], nome_extra="../../etc/plat/segredo.txt"))
    assert e.value.erro == "pacote_invalido" and "zip recusado" in e.value.mensagem


def test_caminho_absoluto_no_zip_e_recusado():
    doc = documento_app(gerar_ulid(), gerar_ulid())
    m = manifesto_de([doc], [FONTE])
    with pytest.raises(ErroAPI) as e:
        pacote.ler(montar_zip(m, [doc], nome_extra="/etc/passwd"))
    assert e.value.erro == "pacote_invalido"


def test_zip_sem_manifesto_e_recusado():
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as zf:
        zf.writestr("documentos/x.json", "{}")
    with pytest.raises(ErroAPI) as e:
        pacote.ler(saida.getvalue())
    assert e.value.erro == "pacote_invalido"


def test_bytes_que_nao_sao_zip_sao_recusados():
    with pytest.raises(ErroAPI) as e:
        pacote.ler(b"nao sou um zip")
    assert e.value.erro == "pacote_invalido"


# ---------------------------------------------------------------- regeração de ids
def test_ids_regerados_e_referencias_preservadas():
    no_a, no_b = gerar_ulid(), gerar_ulid()
    doc = documento_app(no_a, no_b)
    documentos = {doc["id"]: doc}
    mapa = pacote.mapa_de_ids(documentos, {UUID_CAMADA: "44444444-4444-4444-8444-444444444444"})
    # o mapa do documento raiz e o do mapa citado NÃO existe (o mapa não veio no pacote): fica desconhecido
    desconhecidos: set[str] = set()
    novo = pacote.reescrever(doc, mapa, desconhecidos)
    assert desconhecidos == {UUID_MAPA}  # é exatamente o que faz a importação parar
    ids_novos = [n["id"] for n in novo["dados"]["corpo"]["nos"]]
    assert ids_novos != [no_a, no_b] and all(ULID_RE.match(i) for i in ids_novos)
    ligacao = novo["dados"]["corpo"]["ligacoes"][0]
    assert ligacao["origem"] == ids_novos[0] and ligacao["alvo"] == ids_novos[1]
    assert novo["dados"]["corpo"]["nos"][0]["camada"] == "44444444-4444-4444-8444-444444444444"
    assert novo["id"] != UUID_A


def test_duas_regeracoes_do_mesmo_pacote_nao_colidem():
    doc = documento_app(gerar_ulid(), gerar_ulid())
    documentos = {doc["id"]: doc}
    m1 = pacote.mapa_de_ids(documentos, {})
    m2 = pacote.mapa_de_ids(documentos, {})
    assert set(m1.values()).isdisjoint(set(m2.values()))


def test_id_de_outro_inquilino_e_anotado_como_desconhecido():
    doc = documento_app(gerar_ulid(), gerar_ulid())
    doc["dados"]["corpo"]["intruso"] = UUID_ESTRANHO
    documentos = {doc["id"]: doc}
    mapa = pacote.mapa_de_ids(documentos, {UUID_CAMADA: UUID_CAMADA, UUID_MAPA: UUID_MAPA})
    desconhecidos: set[str] = set()
    pacote.reescrever(doc, mapa, desconhecidos)
    assert desconhecidos == {UUID_ESTRANHO}


def test_ulid_que_nao_e_no_fica_como_esta():
    """Texto do documento que por acaso tem forma de ULID não é referência e não é trocado."""
    outro = gerar_ulid()
    doc = documento_app(gerar_ulid(), gerar_ulid())
    doc["dados"]["corpo"]["rotulo"] = outro
    mapa = pacote.mapa_de_ids({doc["id"]: doc}, {})
    novo = pacote.reescrever(doc, mapa, set())
    assert novo["dados"]["corpo"]["rotulo"] == outro


# ---------------------------------------------------------------- esquema campo a campo
def _destino(campos, geometria="MultiPolygon", srid=4674):
    return {"dados": {"campos": campos, "geometria": geometria, "srid": srid}}


def test_esquema_igual_nao_tem_diferenca():
    assert pacote.comparar_esquema(FONTE, _destino(FONTE["campos"])) == []


def test_campo_que_falta_e_listado_e_bloqueia():
    d = pacote.comparar_esquema(FONTE, _destino([{"nome": "codigo", "tipo": "text"}]))
    assert d == [
        {"campo": "area_ha", "regra": "campo_ausente", "esperado": "numeric", "encontrado": None, "bloqueia": True}
    ]


def test_tipo_diferente_e_listado_com_os_dois_lados():
    d = pacote.comparar_esquema(
        FONTE, _destino([{"nome": "codigo", "tipo": "text"}, {"nome": "area_ha", "tipo": "text"}])
    )
    assert d[0]["campo"] == "area_ha" and d[0]["esperado"] == "numeric" and d[0]["encontrado"] == "text"
    assert d[0]["bloqueia"] is True


def test_campo_a_mais_no_destino_nao_e_diferenca():
    campos = [*FONTE["campos"], {"nome": "extra", "tipo": "text"}]
    assert pacote.comparar_esquema(FONTE, _destino(campos)) == []


def test_geometria_diferente_bloqueia_e_srid_diferente_nao():
    d = pacote.comparar_esquema(FONTE, _destino(FONTE["campos"], geometria="Point", srid=4326))
    regras = {x["regra"]: x["bloqueia"] for x in d}
    assert regras == {"geometria_diferente": True, "srid_diferente": False}


def test_uuids_citados_varre_a_estrutura_inteira():
    doc = documento_app(gerar_ulid(), gerar_ulid())
    assert pacote.uuids_citados(doc["dados"]) == {UUID_MAPA, UUID_CAMADA}
