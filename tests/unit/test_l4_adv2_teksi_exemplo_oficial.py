"""Adversário da linha L4 rede de utilidades (rodada 2) — item L4-05-e-gas-e-esgoto.

O portão (LITERAL) exige: "importação do esquema TEKSI (GeoPackage de exemplo do projeto) mapeada".
"GeoPackage de exemplo do projeto" só pode se referir ao arquivo de amostra publicado pelo próprio
projeto TEKSI (https://teksi.github.io/wastewater/) — não a um arquivo que a própria casa fabrica para
imitar o esquema que ela mesma entendeu.

CONSERTADO (trilha l405ega0f8c): o projeto TEKSI não publica `.gpkg` de amostra — o dado de exemplo
oficial é o "demo dataset" de Aletsch, publicado como dump PostgreSQL no release 2026.1.0 de
teksi/wastewater. O repositório agora traz `tests/dados/teksi_wastewater_demo_aletsch.gpkg`, que são
as duas views de trabalho do modelo (`vw_tww_wastewater_structure`, `vw_tww_reach`) exportadas do
dump oficial, sem filtro e sem edição (cadeia de origem e hashes em
`tests/dados/teksi_wastewater_demo_aletsch.origem.md`). O dado real ainda ensinou três lições que o
sintético não ensinava — estrutura sem geometria, espécie sem grupo correspondente, progressão em
CompoundCurve com arco de verdade — e o importador aprendeu as três em `app/rede_utilidades/teksi.py`
(conta e avisa, nunca adivinha em silêncio). Deixa de ser xfail e vira teste normal da cláusula."""

import hashlib
import json
from pathlib import Path

from app.rede_utilidades import teksi

ROOT = Path(__file__).resolve().parents[2]
GPKG = ROOT / "tests" / "dados" / "teksi_wastewater_demo_aletsch.gpkg"
ORIGEM = ROOT / "tests" / "dados" / "teksi_wastewater_demo_aletsch.origem.md"
SHA256_OFICIAL = "f3138640ae8fac5dea5be8ee8eb8cd6fe2eeb6aa08fd324ef38a2f26fb737093"


def _doc_pacote() -> dict:
    return json.loads(
        (ROOT / "app" / "rede_utilidades" / "pacotes" / "esgoto-teksi.json").read_text("utf-8"))


def test_o_geopackage_oficial_esta_no_repositorio_integro_e_com_procedencia():
    assert GPKG.exists(), f"{GPKG} ausente"
    assert hashlib.sha256(GPKG.read_bytes()).hexdigest() == SHA256_OFICIAL
    texto = ORIGEM.read_text("utf-8")
    # a procedência aponta o artefato oficial do projeto (release + hash), não "feito em casa"
    assert "github.com/teksi/wastewater/releases/download/2026.1.0" in texto
    assert "a4da2fab4740ad9bda2aa6bb794cad067c9d169f1272cc0b4446fc456714961e" in texto


def test_importacao_do_arquivo_oficial_mapeada_pelo_pacote():
    lido = teksi.ler_geopackage(GPKG, _doc_pacote())
    # contagens do dado oficial de Aletsch (77 estruturas, 102 trechos): as 7 ignoradas são as
    # lacunas do próprio dado, cada uma com aviso nomeado — nada some em silêncio
    assert lido["contagens"] == {"estruturas_lidas": 71, "trechos_lidos": 101, "ignoradas": 7}
    avisos = {(a["aviso"], a.get("valor")): a["feicoes"] for a in lido["avisos"]}
    assert avisos[("estrutura_sem_geometria", None)] == 4
    assert avisos[("especie_sem_correspondencia", "infiltration_installation")] == 2
    assert avisos[("trecho_com_arco", None)] == 1

    # o de-para sai do pacote e pega coluna de verdade: cota de fundo do poço, cotas do trecho,
    # identificadores — valores reais dos Alpes, não constantes de teste
    poco = next(p for p in lido["pontos"] if p["attributes"]["grupo"] == "poco_de_visita")
    atributos = poco["attributes"]["atributos"]
    assert {"cota_de_fundo", "cota_da_tampa", "identificador"} <= set(atributos)
    assert 1000 < atributos["cota_de_fundo"] < 3000  # Aletsch é alpino
    com_cota = [x for x in lido["linhas"] if "cota_montante" in x["attributes"]["atributos"]]
    assert len(com_cota) == 81  # 20 dos 101 trechos lidos vêm sem cota nas duas pontas: lacuna real
    # e o dado real não é a ficção do sintético: 5 trechos SOBEM de verdade (sifões/recalques da
    # região alpina) e 5 empacam — são exatamente os que a conferência de escoamento marca como
    # contrafluxo, a cláusula do adversário do item operando sobre dado do projeto
    descendo = sum(1 for x in com_cota
                   if x["attributes"]["atributos"]["cota_jusante"] < x["attributes"]["atributos"]["cota_montante"])
    assert descendo == 71

    # geometria real em 4326, na área de Aletsch
    xs = [pt[0] for x in lido["linhas"] for pt in x["geometry"]["paths"][0]]
    ys = [pt[1] for x in lido["linhas"] for pt in x["geometry"]["paths"][0]]
    assert 7.9 < min(xs) and max(xs) < 8.2 and 46.3 < min(ys) and max(ys) < 46.6
    assert all(p["geometry"]["x"] for p in lido["pontos"])
