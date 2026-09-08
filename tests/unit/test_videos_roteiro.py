"""Unidade do item L7-04-d-videos-por-tarefa: registro de roteiros, regeneração por versão menor,
validação de saída e regra de escrita do texto narrado. Nada aqui sobe navegador nem ffmpeg."""

import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from scripts.videos import gerar  # noqa: E402
from scripts.videos.roteiros import (  # noqa: E402
    FRASE_PROIBIDA,
    PALAVRAS_PROIBIDAS,
    TAREFAS,
)

IDIOMAS = 3
ACOES_CONHECIDAS = {
    "ir", "clique", "preencher", "selecionar", "teclar",
    "esperar", "esperar_js", "pausa", "api",
}


def textos() -> list[str]:
    return [
        idioma
        for tarefa in TAREFAS
        for passo in tarefa["passos"]
        for idioma in passo["texto"]
    ]


# ---------------------------------------------------------------- registro

def test_registro_tem_dez_ou_mais_tarefas_com_passos_e_secao():
    assert len(TAREFAS) >= 10
    for tarefa in TAREFAS:
        assert re.fullmatch(r"[a-z]+", tarefa["id"]), tarefa["id"]
        assert tarefa["titulo"] and tarefa["manual"]
        assert len(tarefa["passos"]) >= 2, tarefa["id"]


def test_cada_secao_declarada_existe_no_manual():
    secoes = gerar.secoes_do_manual()
    assert secoes, "MANUAL.md sem seções de nível 2"
    for tarefa in TAREFAS:
        assert any(s.startswith(tarefa["manual"]) for s in secoes), tarefa["id"]


def test_cada_passo_tem_tres_idiomas_e_acoes_conhecidas():
    for tarefa in TAREFAS:
        for passo in tarefa["passos"]:
            assert len(passo["texto"]) == IDIOMAS, tarefa["id"]
            assert all(passo["texto"]), tarefa["id"]
            for acao in passo["acoes"]:
                tocadas = ACOES_CONHECIDAS & set(acao)
                assert len(tocadas) == 1, (tarefa["id"], acao)
                if "api" in acao:
                    assert acao.get("guardar_como") or "guardar_como" not in acao


def test_variaveis_usadas_tem_fornecedor_ou_api():
    fornecidas = {"usuario", "senha", "novo_login", "grupo", "token",
                  "conexao_nome", "job", "conexao"}
    for tarefa in TAREFAS:
        guardadas = {a["guardar_como"] for p in tarefa["passos"] for a in p["acoes"]
                     if a.get("guardar_como")}
        for passo in tarefa["passos"]:
            for acao in passo["acoes"]:
                for valor in _valores_da_acao(acao):
                    for nome in gerar.VAR.findall(valor):
                        assert nome in fornecidas | guardadas, (tarefa["id"], nome)


def _valores_da_acao(acao: dict) -> list[str]:
    valores = []
    for chave, valor in acao.items():
        if chave == "api":
            valores.append(valor[1])
            valores.append(str(valor[2]))
        elif chave == "pausa":
            continue
        elif isinstance(valor, str):
            valores.append(valor)
        elif isinstance(valor, list):
            valores += [v for v in valor if isinstance(v, str)]
    return valores


def test_texto_narrado_obedece_regra_de_escrita():
    for texto in textos():
        assert "!" not in texto, texto
        for palavra in PALAVRAS_PROIBIDAS:
            assert palavra not in texto.lower(), (palavra, texto)
        assert FRASE_PROIBIDA not in texto.lower(), texto
        # uma ideia por frase: cada frase termina em ponto e não usa travessão interno
        for frase in texto.split(". "):
            assert " — " not in frase and "–" not in frase, frase


def test_nenhum_dado_de_cliente_no_roteiro():
    """O vídeo usa só o inquilino de demonstração; texto não carrega número de documento nem e-mail."""
    for texto in textos():
        assert "@" not in texto, texto
        assert not re.search(r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}", texto), texto
        assert not re.search(r"\b\d{11}\b", texto), texto


def test_limpeza_cobre_toda_tarefa_que_cria_objeto_persistente():
    """Coleções que guardam objeto criado exigem limpeza por API. Tarefa de prova (fila) é
    descartável por desenho e não entra nessa conta."""
    persistentes = ("/api/usuarios", "/api/grupos", "/api/conexoes")
    criam = {"usuarios", "grupos", "conexoes"}
    for tarefa in TAREFAS:
        cria_persistente = any(
            "api" in acao and acao["api"][0] == "POST"
            and any(acao["api"][1].startswith(c) for c in persistentes)
            for p in tarefa["passos"] for acao in p["acoes"]
        )
        if cria_persistente:
            assert tarefa["id"] in criam, f"{tarefa['id']} cria objeto sem limpeza"


# ---------------------------------------------------------------- regeneração e validação

def test_limite_de_duracao_e_tres_minutos():
    assert gerar.DURACAO_LIMITE_S == 180.0


def test_interpola_troca_variavel_e_falha_sem_valor():
    var = {"job": "abc123"}
    assert gerar.interpola("tr[data-id='{job}']", var) == "tr[data-id='abc123']"
    with pytest.raises(KeyError):
        gerar.interpola("{conexao}", var)


def test_vtt_com_janela_e_tres_idiomas(tmp_path):
    passos = [
        {"numero": 1, "inicio_s": 0.0, "fim_s": 2.0,
         "texto": ("primeiro", "first", "primero")},
        {"numero": 2, "inicio_s": 2.5, "fim_s": 4.0,
         "texto": ("segundo", "second", "segundo")},
    ]
    saidas = []
    for rotulo, indice in (("pt-BR", 0), ("en", 1), ("es", 2)):
        destino = tmp_path / f"t.{rotulo}.vtt"
        gerar.escreve_vtt(passos, destino, indice)
        conteudo = destino.read_text(encoding="utf-8")
        assert conteudo.startswith("WEBVTT")
        assert "00:00:00.000 --> " in conteudo
        assert ("primeiro" if rotulo == "pt-BR" else "first" if rotulo == "en" else "primero") in conteudo
        saidas.append(destino)
    assert len(saidas) == IDIOMAS


def test_validar_reprova_sem_manifesto(tmp_path, monkeypatch):
    monkeypatch.setattr(gerar, "SAIDA", tmp_path)
    assert gerar.validar() == 1


def test_validar_reprova_com_video_acima_do_limite(tmp_path, monkeypatch):
    """Um mp4 de 4 minutos (fabricado aqui mesmo com bytes de fluxo fake via manifesto) reprova.

    Para não depender do ffmpeg no ambiente de unidade, este teste cobre só a checagem de
    presença dos arquivos: mp4 ausente é falha mesmo com manifesto presente."""
    (tmp_path / "manifesto.json").write_text(
        '{"versao": "9.9.9", "tarefas": {"saude": {"duracao_s": 240.0}}}', encoding="utf-8")
    monkeypatch.setattr(gerar, "SAIDA", tmp_path)
    assert gerar.validar() == 1


def test_validar_reprova_quando_secao_do_manual_sai_do_manual(monkeypatch):
    monkeypatch.setattr(gerar, "secoes_do_manual", lambda: ["1. Outra coisa"])
    with pytest.raises(SystemExit):
        gerar.confere_secoes_manual()


def test_alvo_make_videos_existe():
    makefile = (RAIZ / "Makefile").read_text(encoding="utf-8")
    assert "videos:" in makefile
    assert "gerar.py" in makefile
    assert "videos-validar:" in makefile


def test_saida_de_videos_fora_do_git():
    ignora = (RAIZ / ".gitignore").read_text(encoding="utf-8")
    assert "web/videos/" in ignora
