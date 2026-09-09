"""Fluxo completo de importação de DXF e DWG pela API (item L0-04-e; ADR 0020).

É o e2e da cláusula "e2e do fluxo com captura": envio do arquivo → item `arquivo` → importação → inspeção →
proposta com camadas do desenho, unidade, codificação e pendências → confirmação com CRS, escolha de camadas e
pontos de controle → carga → tabela do inquilino com a geometria JÁ georreferenciada. Cada passo grava
requisição e resposta em `tests/capturas/L0-04-e-formatos-cad_fluxo.json`: essa é a captura.

Não há captura de TELA porque nesta passagem não existe tela de importação no `web/` (a ingestão é só de API);
está registrado no handoff do item, não escondido."""

from __future__ import annotations

import json
import math
import os
import secrets
from pathlib import Path

import pytest

from tests.api.conftest import entrar, novo_cliente
from tests.api.ingestao.conftest import Ingestor, esperar_job
from tests.api.test_rls import contexto

ITEM = "L0-04-e-formatos-cad"
DADOS = Path(__file__).resolve().parents[2] / "dados" / "cad"
CAPTURAS = Path(__file__).resolve().parents[2] / "capturas"
SRID_ALVO = 31983            # SIRGAS 2000 / UTM 23S, em metros
ESCALA, ANGULO = 1.0, 12.0   # o desenho de teste está em metro, girado 12° e transladado
TX, TY = 330_000.0, 7_390_000.0


def _terreno(x: float, y: float) -> list[float]:
    a = ESCALA * math.cos(math.radians(ANGULO))
    b = ESCALA * math.sin(math.radians(ANGULO))
    return [a * x - b * y + TX, b * x + a * y + TY]


class Captura:
    """Transcrição do fluxo: cada passo com o que foi pedido e o que voltou. Gravada só com
    PLAT_GRAVAR_MEDIDAS=1, pela mesma razão da fixture `medida`: a suíte não suja a árvore sozinha."""

    def __init__(self, nome: str):
        self.nome = nome
        self.passos: list[dict] = []

    def passo(self, titulo: str, pedido, resposta) -> None:
        self.passos.append({"passo": len(self.passos) + 1, "titulo": titulo,
                            "pedido": pedido, "resposta": resposta})

    def gravar(self) -> Path | None:
        if os.environ.get("PLAT_GRAVAR_MEDIDAS") != "1":
            return None
        CAPTURAS.mkdir(parents=True, exist_ok=True)
        caminho = CAPTURAS / f"{ITEM}_{self.nome}.json"
        caminho.write_text(json.dumps({"item": ITEM, "fluxo": self.nome, "passos": self.passos},
                                      ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        return caminho


def _importar_cad(ing, nome: str, formato: str, captura: Captura | None = None):
    caminho = DADOS / nome
    obj = ing.enviar_arquivo(caminho)
    item_id = ing.item_arquivo(obj, nome)
    r = ing.sessao.post("/api/importacoes", json={"arquivo_id": item_id, "formato": formato})
    assert r.status_code == 202, r.text
    corpo = r.json()
    esperar_job(ing.sessao, corpo["job_id"], timeout=180)
    r = ing.sessao.get(f"/api/importacoes/{corpo['importacao_id']}")
    imp = r.json()
    if captura:
        captura.passo("enviar arquivo", {"arquivo": nome, "bytes": obj["bytes"]},
                      {"sha256": obj["sha256"][:16] + "…"})
        captura.passo("criar importação", {"formato": formato}, {"job_id": corpo["job_id"]})
        captura.passo("proposta da inspeção", {"importacao_id": imp["id"]},
                      {"estado": imp["estado"], "perguntas": imp["proposta"]["perguntas"],
                       "camadas_desenho": imp["proposta"].get("camadas_desenho"),
                       "cad": {k: imp["proposta"]["cad"][k] for k in ("versao", "unidade", "totais", "camadas")}})
    return imp["id"], imp


def _porque_falhou(ing, final: dict) -> str:
    """Mensagem de falha útil: o estado da importação NÃO diz por quê; o erro está no job de carga."""
    if final.get("estado") == "concluida":
        return ""
    partes = [f"importação em {final.get('estado')!r}", f"erro da importação: {final.get('erro')!r}"]
    if final.get("job_carga"):
        r = ing.sessao.get(f"/api/jobs/{final['job_carga']}")
        if r.status_code == 200:
            j = r.json()
            partes.append(f"job de carga {j.get('estado')}: {str(j.get('erro'))[:400]}")
    return " | ".join(partes)


def _tabela_de(cur, item_id: str) -> tuple[str, str]:
    cur.execute("SELECT dados->>'schema' AS schema, dados->>'tabela' AS tabela FROM plat.item WHERE id=%s::uuid",
                (item_id,))
    r = cur.fetchone()
    return r["schema"], r["tabela"]


class InquilinoDeCarga:
    """Inquilino criado só para este teste, com slug SEM hífen. Dois motivos, os dois medidos aqui:

    * `plat.camada_schema_garantir` exige `^[a-z][a-z0-9_]{0,60}$` no slug — o `inquilino_temporario` do
      conftest usa `zt-inq-<hex>`, com hífen, e a carga morre com `slug_invalido` antes de criar a tabela;
    * o schema de dados é `d_<slug>` e **não** é reescrito por `laco/trilha_ambiente.sh`: rodar a carga no
      inquilino `demo` de uma trilha bate em `permission denied for schema d_demo`, que é da produção.

    Apagar o inquilino no fim leva junto a tabela da camada e o schema."""

    def __init__(self, sessao_plat):
        self.slug = f"zt{secrets.token_hex(4)}"
        r = sessao_plat.post("/api/plataforma/inquilinos", json={
            "slug": self.slug, "nome": f"Inquilino de carga CAD {self.slug}",
            "admin_login": "admin", "admin_nome": "Administrador de teste", "config": {}})
        assert r.status_code == 201, r.text
        self.id = r.json()["id"]
        self.admin_id = r.json()["admin"]["id"]
        temporaria = r.json()["senha_temporaria"]
        self.admin = novo_cliente()
        assert entrar(self.admin, self.slug, "admin", temporaria).status_code == 200
        senha = "Senha-do-admin-1" + secrets.token_hex(3)
        assert self.admin.put("/api/eu/senha", json={"atual": temporaria, "nova": senha}).status_code == 204
        self._plat = sessao_plat

    def apagar(self):
        self._plat.delete(f"/api/plataforma/inquilinos/{self.id}")


@pytest.fixture
def ingestor_cad(sessao_plat):
    inq = InquilinoDeCarga(sessao_plat)
    ing = Ingestor(inq.admin)
    ing.inquilino = inq
    try:
        yield ing
    finally:
        ing.liberar_token()
        inq.apagar()


def _admin(con, inq):
    contexto(con, inq.id, usuario_id=inq.admin_id, login="admin")


def test_dxf_fluxo_completo_com_pontos_de_controle(ingestor_cad, conexao_plat_app, medida):
    """O fluxo inteiro, do envio à tabela: 3 pontos de controle, RMSE reportado antes da carga, e a geometria
    no banco cai onde os pontos mandaram."""
    captura = Captura("dxf_com_pontos_de_controle")
    importacao_id, imp = _importar_cad(ingestor_cad, "polilinhas.dxf", "dxf", captura)
    proposta = imp["proposta"]
    assert imp["estado"] == "proposta", imp
    assert proposta["driver"] == "DXF"
    assert proposta["cad"]["versao"] == "R2010"
    assert proposta["cad"]["unidade"]["nome"] == "metro"
    assert sorted(proposta["camadas_desenho"]) == ["QUADRA", "TALUDE_3D"]
    assert proposta["geometria"]["tipos"] == {"LineString": 8, "LineString Z": 4}, proposta["geometria"]
    assert proposta["geometria"]["escolhida"] in ("LineString", "MultiLineString"), proposta["geometria"]
    assert "crs" in proposta["perguntas"] and "georreferencia" in proposta["perguntas"]
    assert proposta["cad"]["isolamento"]["seccomp"] == 2, "o subprocesso do GDAL rodou sem seccomp"

    pontos = [{"desenho": [0.0, 0.0], "terreno": _terreno(0.0, 0.0)},
              {"desenho": [200.0, 0.0], "terreno": _terreno(200.0, 0.0)},
              {"desenho": [0.0, 30.0], "terreno": _terreno(0.0, 30.0)}]
    corpo = {"crs": {"srid": SRID_ALVO}, "cad": {"unidade": 6, "camadas": ["QUADRA"],
                                                 "georreferencia": {"pontos": pontos}}}
    final = ingestor_cad.confirmar(importacao_id, corpo, timeout=300)
    assert final.get("estado") == "concluida", _porque_falhou(ingestor_cad, final) or final
    ajuste = final["confirmacao"]["cad"]["georreferencia"]["ajuste"]
    assert ajuste["pontos"] == 3 and ajuste["rmse"] < 1e-6
    assert abs(ajuste["rotacao_graus"] - ANGULO) < 1e-6
    captura.passo("confirmar", corpo, {"estado": final["estado"], "rmse": ajuste["rmse"],
                                       "escala": ajuste["escala"], "rotacao_graus": ajuste["rotacao_graus"]})

    _admin(conexao_plat_app, ingestor_cad.inquilino)
    with conexao_plat_app.cursor() as cur:
        schema, tabela = _tabela_de(cur, final["item_id"])
        cur.execute(f'SELECT count(*) AS n, max(ST_SRID(geom)) AS srid, '
                    f'ST_X(ST_Centroid(ST_Extent(geom)::geometry)) AS cx, '
                    f'ST_Y(ST_Centroid(ST_Extent(geom)::geometry)) AS cy FROM "{schema}"."{tabela}"')
        r = cur.fetchone()
    assert r["n"] == 8, "só a camada QUADRA foi pedida (8 entidades das 12 do desenho)"
    assert r["srid"] == SRID_ALVO
    # o desenho vai de x 0..240, y 0..30: o centro tem de cair perto da imagem do centro pela semelhança
    esperado = _terreno(120.0, 15.0)
    assert abs(r["cx"] - esperado[0]) < 60 and abs(r["cy"] - esperado[1]) < 60, (r["cx"], r["cy"], esperado)
    captura.passo("tabela no banco", {"schema": schema, "tabela": tabela},
                  {"feicoes": r["n"], "srid": r["srid"], "centro": [r["cx"], r["cy"]]})

    arquivo = captura.gravar()
    medida(ITEM)("e2e_dxf", {"passos": len(captura.passos), "feicoes": r["n"], "srid": r["srid"],
                             "rmse": ajuste["rmse"], "captura": str(arquivo) if arquivo else None},
                 "passos", "venv/bin/pytest tests/api/ingestao/test_ingestao_cad.py -k fluxo_completo")


def test_dwg_r2000_importa_pelo_conversor(ingestor_cad, conexao_plat_app, medida):
    captura = Captura("dwg_r2000")
    importacao_id, imp = _importar_cad(ingestor_cad, "r2000.dwg", "dwg", captura)
    proposta = imp["proposta"]
    assert proposta["cad"]["versao"] == "R2000"
    assert proposta["cad"]["conversao"]["codigo"] == 0
    final = ingestor_cad.confirmar(importacao_id, {"crs": {"srid": SRID_ALVO}, "cad": {"unidade": 6}}, timeout=300)
    assert final.get("estado") == "concluida", _porque_falhou(ingestor_cad, final) or final
    _admin(conexao_plat_app, ingestor_cad.inquilino)
    with conexao_plat_app.cursor() as cur:
        schema, tabela = _tabela_de(cur, final["item_id"])
        cur.execute(f'SELECT count(*) AS n FROM "{schema}"."{tabela}"')
        assert cur.fetchone()["n"] == 12
    captura.passo("carga", {"formato": "dwg"}, {"estado": final["estado"], "feicoes": 12})
    captura.gravar()
    medida(ITEM)("e2e_dwg_r2000", {"versao": "R2000", "feicoes": 12,
                                   "conversor": proposta["cad"]["conversao"].get("versao_conversor")},
                 "feicoes", "venv/bin/pytest tests/api/ingestao/test_ingestao_cad.py -k dwg_r2000")


def test_unidade_nao_declarada_bloqueia_a_confirmacao(ingestor_cad):
    """`$INSUNITS = 0`: confirmar sem responder a unidade tem de dar 422 nomeando a pergunta que falta."""
    importacao_id, imp = _importar_cad(ingestor_cad, "polegada.dxf", "dxf")
    assert "unidade" in imp["proposta"]["perguntas"]
    r = ingestor_cad.sessao.put(f"/api/importacoes/{importacao_id}/confirmar", json={"crs": {"srid": SRID_ALVO}})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "perguntas_pendentes"
    assert r.json()["detalhe"]["perguntas"] == ["unidade"], r.json()
    r = ingestor_cad.sessao.put(f"/api/importacoes/{importacao_id}/confirmar",
                              json={"crs": {"srid": SRID_ALVO}, "cad": {"unidade": 1}})
    assert r.status_code == 202, r.text
    esperar_job(ingestor_cad.sessao, r.json()["job_id"], timeout=300)
    r = ingestor_cad.sessao.get(f"/api/importacoes/{importacao_id}")
    final = r.json()
    assert final.get("estado") == "concluida", _porque_falhou(ingestor_cad, final) or final
    assert final["confirmacao"]["cad"]["metros_por_unidade"] == 0.0254


def test_dxf_binario_recusado_na_criacao_da_importacao(ingestor_cad):
    obj = ingestor_cad.enviar_arquivo(DADOS / "binario.dxf")
    item_id = ingestor_cad.item_arquivo(obj, "binario.dxf")
    r = ingestor_cad.sessao.post("/api/importacoes", json={"arquivo_id": item_id, "formato": "dxf"})
    assert r.status_code == 422, r.text
    assert "BINÁRIO" in json.dumps(r.json(), ensure_ascii=False)


def test_camada_do_desenho_que_nao_existe_e_recusada(ingestor_cad):
    importacao_id, imp = _importar_cad(ingestor_cad, "polilinhas.dxf", "dxf")
    r = ingestor_cad.sessao.put(f"/api/importacoes/{importacao_id}/confirmar",
                              json={"crs": {"srid": SRID_ALVO}, "cad": {"camadas": ["NAO_EXISTE"]}})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "camada_desconhecida", r.json()


def test_pontos_de_controle_degenerados_recusados_com_mensagem(ingestor_cad):
    importacao_id, _imp = _importar_cad(ingestor_cad, "polilinhas.dxf", "dxf")
    iguais = [{"desenho": [0.0, 0.0], "terreno": [1.0, 1.0]}] * 3
    r = ingestor_cad.sessao.put(f"/api/importacoes/{importacao_id}/confirmar",
                              json={"crs": {"srid": SRID_ALVO},
                                    "cad": {"georreferencia": {"pontos": iguais}}})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "georreferencia_invalida", r.json()
    assert "colineares" in r.json()["mensagem"] or "coincidentes" in r.json()["mensagem"]


def test_formatos_publicados_incluem_dxf_e_dwg(ingestor_cad):
    r = ingestor_cad.sessao.get("/api/importacoes/formatos")
    assert r.status_code == 200
    tipos = {f["tipo"]: f for f in r.json()}
    assert tipos["dxf"]["extensoes"] == [".dxf"] and tipos["dwg"]["extensoes"] == [".dwg"]
