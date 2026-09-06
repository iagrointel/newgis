"""Leitura de DXF e DWG (item L0-04-e; ADR 0020). Cada teste é uma cláusula do portão de pronto:

* 4 DXF abertos (blocos — inclusive bloco ANINHADO —, polilinhas 2D e 3D, textos/cotas/hachuras, camada com
  nome longo e acentuado), com a contagem POR CAMADA conferida contra o `ogrinfo` rodado à parte;
* 2 DWG convertidos (R2000 e R2018);
* DWG que o LibreDWG não lê devolve mensagem COM A VERSÃO do arquivo;
* o isolamento do subprocesso (ADR 0015) é MEDIDO, não prometido.

Também estão aqui os ataques que o item manda o adversário fazer: DXF binário, DXF com 2 milhões de entidades,
DWG cifrado/ilegível, e DXF em unidade não declarada (a escala tem de ser PERGUNTADA)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from app.ingestao import cad, formatos, isolamento

ITEM = "L0-04-e-formatos-cad"
DADOS = Path(__file__).resolve().parents[1] / "dados" / "cad"
DXFS = ("blocos.dxf", "polilinhas.dxf", "textos.dxf", "camada_longa.dxf")


def _copiar(nome: str, destino: Path) -> Path:
    alvo = destino / nome
    shutil.copy(DADOS / nome, alvo)
    return alvo


def _ogrinfo_por_camada(caminho: Path, dir_trabalho: Path, codificacao: str = "UTF-8") -> dict[str, int]:
    """Contagem por camada feita com o `ogrinfo` DIRETO, fora do nosso código: é a referência da cláusula
    'contagem por camada igual à do ogrinfo'."""
    argv = ["ogrinfo", "-ro", "-q", "--config", "DXF_INLINE_BLOCKS", "FALSE",
            "--config", "DXF_ENCODING", codificacao, "-dialect", "SQLITE",
            "-sql", "SELECT Layer AS c, COUNT(*) AS n FROM entities GROUP BY Layer", str(caminho)]
    saida = subprocess.run(argv, capture_output=True, text=True, timeout=180,
                           env={**os.environ, "GDAL_SKIP": "HTTP"}, cwd=dir_trabalho)
    assert saida.returncode == 0, saida.stderr[-500:]
    contagem, camada = {}, None
    for linha in saida.stdout.splitlines():
        linha = linha.strip()
        if linha.startswith("c (String) = "):
            camada = linha[len("c (String) = "):]
        elif linha.startswith("n (Integer) = ") and camada is not None:
            contagem[camada] = int(linha[len("n (Integer) = "):])
            camada = None
    return contagem


@pytest.fixture
def trabalho():
    with tempfile.TemporaryDirectory(prefix="cad-") as td:
        yield Path(td)


@pytest.mark.parametrize("nome", DXFS)
def test_dxf_abre_e_conta_por_camada_igual_ao_ogrinfo(nome, trabalho, medida):
    """Cláusula 1 do portão: os 4 DXF abrem e a contagem por camada bate com a do ogrinfo, camada a camada."""
    caminho = _copiar(nome, trabalho)
    rel = cad.inspecionar(caminho, trabalho, formato="dxf")
    assert rel.estado in ("aceito", "pendente"), rel.problemas
    nossa = {c["nome"]: c["entidades"] for c in rel.camadas if c["entidades"]}
    referencia = _ogrinfo_por_camada(caminho, trabalho)
    assert nossa == referencia, f"{nome}: nossa contagem {nossa} != ogrinfo {referencia}"
    assert rel.totais["entidades"] == sum(referencia.values())
    medida(ITEM)(f"dxf_{nome.replace('.dxf', '')}",
                 {"camadas": rel.totais["camadas"], "entidades": rel.totais["entidades"],
                  "cotas": rel.totais["cotas"], "textos": rel.totais["textos"],
                  "hachuras": rel.totais["hachuras"], "blocos": rel.totais["blocos"], "versao": rel.versao,
                  "unidade": rel.unidade.get("nome"), "por_camada": nossa, "ogrinfo": referencia},
                 "contagem", f"venv/bin/pytest tests/unit/test_cad_formatos.py -k {nome.split('.')[0]}")


def test_bloco_aninhado_o_gdal_resolve_sem_ezdxf(trabalho, medida):
    """A hipótese do item admitia trazer o ezdxf se o driver do GDAL não desse conta de bloco dentro de bloco.
    MEDIDO: dá. `CONJUNTO_ILUMINACAO` insere dois `POSTE`; com blocos explodidos a geometria dos dois postes
    aparece, transladada, dentro de cada uma das 4 inserções."""
    caminho = _copiar("blocos.dxf", trabalho)
    como_ponto = cad.inspecionar(caminho, trabalho, formato="dxf", respostas={"blocos": "ponto"})
    assert como_ponto.totais["blocos"] == 7
    nomes = {b["nome"] for b in como_ponto.blocos}
    assert {"POSTE", "CONJUNTO_ILUMINACAO"} <= nomes, nomes

    alvo = trabalho / "explodido.jsonl"
    r = isolamento.executar(
        ["ogr2ogr", "-f", "GeoJSONSeq", str(alvo), str(caminho),
         "--config", "DXF_INLINE_BLOCKS", "TRUE", "--config", "DXF_ENCODING", "UTF-8",
         "-dialect", "SQLITE",
         "-sql", "SELECT Layer AS c, ST_NumGeometries(geometry) AS partes FROM entities WHERE Layer='MOBILIARIO'"],
        raiz=trabalho)
    assert r.ok, r.stderr[-400:]
    partes = [json.loads(ln)["properties"]["partes"] for ln in alvo.read_text().splitlines() if ln.strip()]
    # cada inserção do conjunto traz: 2 blocos POSTE (círculo+haste) + a linha do próprio conjunto
    assert partes and min(partes) >= 3, partes
    medida(ITEM)("bloco_aninhado", {"ezdxf_necessario": False, "partes_por_insercao": partes,
                                    "blocos_definidos": sorted(nomes)}, "partes",
                 "venv/bin/pytest tests/unit/test_cad_formatos.py -k bloco_aninhado")


def test_camada_com_nome_longo_e_acento_chega_inteira(trabalho):
    """Camada de 203 caracteres com acento. O arquivo declara `$DWGCODEPAGE ANSI_1252` e grava UTF-8 — quem
    decide é o byte, não o cabeçalho (ADR 0020 seção 3)."""
    caminho = _copiar("camada_longa.dxf", trabalho)
    rel = cad.inspecionar(caminho, trabalho, formato="dxf")
    longa = max((c["nome"] for c in rel.camadas), key=len)
    assert len(longa) > 190
    assert longa.endswith("ÁGUA PLUVIAL"), repr(longa[-20:])
    assert rel.codificacao["valor"] == "UTF-8"
    assert rel.codificacao["declarada"] == "ANSI_1252"


def test_polilinha_3d_mantem_z(trabalho):
    caminho = _copiar("polilinhas.dxf", trabalho)
    rel = cad.inspecionar(caminho, trabalho, formato="dxf")
    por_camada = {c["nome"]: c["entidades"] for c in rel.camadas}
    assert por_camada == {"QUADRA": 8, "TALUDE_3D": 4}
    alvo = trabalho / "z.jsonl"
    r = isolamento.executar(
        ["ogr2ogr", "-f", "GeoJSONSeq", str(alvo), str(caminho), "--config", "DXF_INLINE_BLOCKS", "FALSE",
         "-dialect", "SQLITE",
         "-sql", "SELECT ST_Z(ST_PointN(ST_GeometryN(geometry,1),1)) AS z FROM entities WHERE Layer='TALUDE_3D'"],
        raiz=trabalho)
    assert r.ok, r.stderr[-300:]
    zs = [json.loads(ln)["properties"]["z"] for ln in alvo.read_text().splitlines() if ln.strip()]
    assert zs and all(z and z >= 700 for z in zs), zs


def test_cota_texto_e_hachura_saem_separados(trabalho):
    """O driver do GDAL DECOMPÕE a DIMENSION em linhas e texto: nenhuma feição sai com `AcDbDimension`. A cota
    é contada no texto do DXF por isso — e a contagem tem de bater com o número de DIMENSION do arquivo."""
    caminho = _copiar("textos.dxf", trabalho)
    rel = cad.inspecionar(caminho, trabalho, formato="dxf")
    no_arquivo = (DADOS / "textos.dxf").read_text(encoding="utf-8", errors="replace").count("\nDIMENSION\n")
    assert rel.totais["cotas"] == no_arquivo == 4
    assert rel.totais["hachuras"] == 3
    assert rel.totais["textos"] == 13
    por_camada = {c["nome"]: c for c in rel.camadas}
    assert por_camada["HACHURA"]["hachuras"] == 3
    assert por_camada["COTA"]["cotas"] == 4
    assert por_camada["ROTULO"]["textos"] == 9


# ------------------------------------------------------------------------------------------------- DWG
def _tem_conversor() -> bool:
    return cad.conversor() is not None


sem_conversor = pytest.mark.skipif(not _tem_conversor(), reason="LibreDWG (dwg2dxf) não instalado nesta máquina")


@sem_conversor
@pytest.mark.parametrize("nome,versao", [("r2000.dwg", "R2000"), ("r2018.dwg", "R2018")])
def test_dwg_convertido_e_lido(nome, versao, trabalho, medida):
    """Cláusula 2 do portão: R2000 e R2018 convertidos pelo LibreDWG e lidos."""
    caminho = _copiar(nome, trabalho)
    rel = cad.inspecionar(caminho, trabalho, formato="dwg")
    assert rel.estado in ("aceito", "pendente"), rel.problemas
    assert rel.versao == versao
    assert rel.conversao["codigo"] == 0 and rel.conversao["bytes_dxf"] > 0
    assert rel.totais["entidades"] >= 1
    medida(ITEM)(f"dwg_{versao}", {"versao": rel.versao, "marca": rel.conversao["marca"],
                                   "conversor": rel.conversao.get("versao_conversor"),
                                   "bytes_dxf": rel.conversao["bytes_dxf"], "tempo_s": rel.conversao["tempo_s"],
                                   "ram_pico_kb": rel.conversao["ram_pico_kb"],
                                   "entidades": rel.totais["entidades"], "camadas": rel.totais["camadas"]},
                  "conversao", "venv/bin/pytest tests/unit/test_cad_formatos.py -k dwg_convertido")


@sem_conversor
def test_r2000_preserva_o_desenho_de_origem(trabalho):
    """O r2000.dwg foi gerado do nosso polilinhas.dxf: ida e volta tem de devolver as mesmas 2 camadas e as
    mesmas 12 entidades."""
    rel = cad.inspecionar(_copiar("r2000.dwg", trabalho), trabalho, formato="dwg")
    assert {c["nome"]: c["entidades"] for c in rel.camadas} == {"QUADRA": 8, "TALUDE_3D": 4}


@sem_conversor
def test_dwg_ilegivel_diz_a_versao_do_arquivo(trabalho):
    """Cláusula 3 do portão, e o ataque 'DWG cifrado': o corpo do arquivo é ilegível, o cabeçalho é AC1032.
    A mensagem tem de nomear a versão — quem enviou precisa saber que o problema é a versão, não o desenho."""
    rel = cad.inspecionar(_copiar("r2018_ilegivel.dwg", trabalho), trabalho, formato="dwg")
    assert rel.estado == "recusado"
    problema = rel.problemas[0]
    assert "R2018" in problema and "AC1032" in problema and "LibreDWG" in problema, problema
    assert "/" not in problema.replace("R11/R12", ""), f"caminho vazou na mensagem: {problema}"


def test_dwg_sem_conversor_diz_a_versao(trabalho, monkeypatch):
    """Instalação sem LibreDWG: a recusa continua nomeando a versão do arquivo, e diz o que fazer."""
    monkeypatch.setattr(cad, "conversor", lambda: None)
    rel = cad.inspecionar(_copiar("r2018.dwg", trabalho), trabalho, formato="dwg")
    assert rel.estado == "recusado"
    assert "R2018" in rel.problemas[0] and "dwg2dxf" in rel.problemas[0]


# ------------------------------------------------------------------------------- ataques do adversário
def test_dxf_binario_e_recusado_com_mensagem_propria(trabalho):
    rel = cad.inspecionar(_copiar("binario.dxf", trabalho), trabalho, formato="dxf")
    assert rel.estado == "recusado"
    assert "BINÁRIO" in rel.problemas[0] and "ASCII" in rel.problemas[0]


def test_unidade_nao_declarada_vira_pendencia_nunca_suposicao(trabalho):
    """`$INSUNITS = 0`: a escala é PERGUNTADA. Nada de 'assume-se metro'."""
    rel = cad.inspecionar(_copiar("polegada.dxf", trabalho), trabalho, formato="dxf")
    assert rel.estado == "pendente"
    assert rel.unidade["perguntar"] is True and rel.unidade["metros_por_unidade"] is None
    assert any("unidade" in p for p in rel.pendencias)
    # respondida como polegada, a escala passa a existir
    rel2 = cad.inspecionar(_copiar("polegada.dxf", trabalho), trabalho, formato="dxf", respostas={"unidade": 1})
    assert rel2.unidade["metros_por_unidade"] == 0.0254 and rel2.unidade["origem"] == "usuario"


def test_crs_ausente_nunca_vira_4326(trabalho):
    rel = cad.inspecionar(_copiar("blocos.dxf", trabalho), trabalho, formato="dxf")
    assert rel.estado == "pendente"
    assert any("sistema de coordenadas" in p for p in rel.pendencias)
    rel2 = cad.inspecionar(_copiar("blocos.dxf", trabalho), trabalho, formato="dxf", respostas={"crs": 31983})
    assert not any("sistema de coordenadas" in p for p in rel2.pendencias)


GRANDE = Path(os.environ.get("PLAT_CAD_GRANDE", "/tmp/cadbig/milhao.dxf"))


@pytest.mark.skipif(not GRANDE.exists(),
                    reason="gere o arquivo de 2 milhões de entidades (ver handoff do item L0-04-e)")
def test_dxf_com_dois_milhoes_de_entidades(trabalho, medida):
    """Ataque do adversário: 2 milhões de entidades (180 MB de DXF). Tem de ser LIDO, não recusado por
    desistência — e sem estourar a memória do subprocesso (RLIMIT_AS = 768 MB)."""
    import time

    inicio = time.monotonic()
    rel = cad.inspecionar(GRANDE, GRANDE.parent, formato="dxf")
    segundos = round(time.monotonic() - inicio, 1)
    assert rel.estado in ("aceito", "pendente"), rel.problemas
    assert rel.totais["entidades"] == 2_000_000
    assert segundos < 120, f"a leitura levou {segundos} s"
    medida(ITEM)("dxf_2_milhoes_de_entidades",
                 {"entidades": rel.totais["entidades"], "bytes": GRANDE.stat().st_size, "segundos": segundos,
                  "estado": rel.estado, "camadas": rel.totais["camadas"]},
                 "segundo", "PLAT_CAD_GRANDE=<arquivo> venv/bin/pytest tests/unit/test_cad_formatos.py "
                            "-k dois_milhoes")


def test_acima_do_teto_de_entidades_recusa_dizendo_o_que_fazer(trabalho, monkeypatch):
    monkeypatch.setattr(cad, "ENTIDADES_MAX", 5)
    rel = cad.inspecionar(_copiar("polilinhas.dxf", trabalho), trabalho, formato="dxf")
    assert rel.estado == "recusado"
    assert "12 entidades" in rel.problemas[0] and "envie em partes" in rel.problemas[0]


def test_arquivo_vazio_e_arquivo_gigante_recusados(trabalho, monkeypatch):
    vazio = trabalho / "vazio.dxf"
    vazio.write_bytes(b"")
    assert cad.inspecionar(vazio, trabalho, formato="dxf").estado == "recusado"
    monkeypatch.setattr(cad, "TAMANHO_MAX", 10)
    rel = cad.inspecionar(_copiar("blocos.dxf", trabalho), trabalho, formato="dxf")
    assert rel.estado == "recusado" and "máximo" in rel.problemas[0]


def test_caminho_fora_do_envio_e_recusado(trabalho):
    """Regra do ADR 0015 seção 3: caminho resolvido por realpath tem de cair dentro do diretório do envio."""
    fora = Path(tempfile.mkdtemp(prefix="fora-")) / "x.dxf"
    shutil.copy(DADOS / "blocos.dxf", fora)
    rel = cad.inspecionar(fora, trabalho, formato="dxf")
    assert rel.estado == "recusado" and "fora do diretório" in rel.problemas[0]
    with pytest.raises(isolamento.CaminhoRecusado):
        isolamento.caminho_dentro("/vsicurl/http://exemplo.invalido/a.dxf", trabalho)


def test_isolamento_do_subprocesso_e_medido(trabalho, medida):
    """Não se promete isolamento: lê-se `/proc/self/status` do filho."""
    estado = isolamento.isolamento_declarado(trabalho)
    assert estado["seccomp"] == 2 and estado["no_new_privs"] == 1, estado
    r = isolamento.executar(["ogrinfo", "--version"], raiz=trabalho)
    assert r.ok and "GDAL" in r.stdout
    medida(ITEM)("isolamento", {**estado, "gdal": r.stdout.strip()}, "proc",
                 "venv/bin/pytest tests/unit/test_cad_formatos.py -k isolamento")


def test_rede_fechada_no_processo_do_gdal(trabalho):
    """O ataque de rede do ADR 0015: um DXF cujo nome de arquivo é uma URL não pode sair para a rede."""
    r = isolamento.executar(["ogrinfo", "-ro", "-so", "http://exemplo.invalido/a.dxf"], raiz=trabalho, timeout_s=20)
    assert r.codigo != 0
    assert r.tempo_s < 15, f"a tentativa de rede demorou {r.tempo_s} s (deveria falhar de imediato)"


def test_formato_declarado_e_conferido_pelos_bytes():
    formatos.verificar_conteudo("dxf", (DADOS / "polilinhas.dxf").read_bytes())
    formatos.verificar_conteudo("dwg", (DADOS / "r2000.dwg").read_bytes())
    for tipo, arquivo, trecho in (("dxf", "binario.dxf", "BINÁRIO"),
                                  ("dxf", "r2000.dwg", "R2000"),
                                  ("dwg", "polilinhas.dxf", "AC10xx")):
        with pytest.raises(formatos.ConteudoNaoCorresponde) as e:
            formatos.verificar_conteudo(tipo, (DADOS / arquivo).read_bytes())
        assert trecho in str(e.value)
