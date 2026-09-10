"""Cobertura da interface (item UX-00-mapa-de-cobertura-da-interface): regra da trilha de interface, nenhuma rota
fica só no backend. O gerador `docs/gerar_cobertura_ui.py` cruza as rotas da aplicação VIVA com o que `web/` chama e
mantém a linha de base de lacunas de escrita em `docs/cobertura_ui_lacunas.json`. Aqui:

1. uma rota de ESCRITA (POST/PUT/PATCH/DELETE) que não é chamada por tela alguma e não está na linha de base
   reprova — é o "rota nova sem tela reprova o make check" do portão; a saída é dar controle na tela ou registrar a
   lacuna (`python3 docs/gerar_cobertura_ui.py --registrar`, que também cria o item UX-<n>) e comitar o JSON;
2. a linha de base só encolhe: uma lacuna registrada que virou coberta é apagada do JSON pelo gerador (não reprova,
   só é conferida na regeneração);
3. o próprio detector é provado contra casos conhecidos do repositório (apelido `I(itemId)`, template com
   `${}` aninhado, método na linha de cima em chamada multi-linha, URL de imagem sem método = GET)."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "docs"))

import gerar_cobertura_ui as cob  # noqa: E402 — módulo em docs/, fora do pacote app


@pytest.fixture(scope="module")
def resultado(env):
    return cob.cruzar(vivo=True)


def test_nenhuma_lacuna_de_escrita_fora_da_linha_de_base(resultado):
    novas = cob.conferir(resultado)
    assert novas == [], (
        "rota(s) de escrita sem controle em tela e fora de docs/cobertura_ui_lacunas.json: "
        f"{novas}. Dê controle na tela, ou registre a lacuna com `python3 docs/gerar_cobertura_ui.py --registrar` "
        "(cria o item UX-<n> no backlog) e comite docs/cobertura_ui_lacunas.json"
    )


def test_linha_de_base_sem_rota_inexistente(resultado):
    """toda lacuna registrada ainda é uma rota da aplicação (rota apagada sai da linha de base na regeneração)."""
    existentes = {f"{r['metodo']} {r['caminho']}" for r in resultado["rotas"]}
    fantasmas = sorted(cob.lacunas_conhecidas() - existentes)
    assert fantasmas == [], f"lacunas de rotas que não existem mais: {fantasmas}; rode make cobertura-ui"


def test_documento_e_linha_de_base_existem_e_sao_gerados():
    assert cob.DESTINO.exists() and cob.LACUNAS.exists()
    assert cob.DESTINO.read_text(encoding="utf-8").startswith("# Cobertura da interface (gerado")


def test_toda_pagina_registrada_tem_arquivo_html():
    pags = cob.paginas()
    assert "/tarefas" in pags and "/mapa" in pags and "/" in pags
    faltando = [c for c, a in pags.items() if not (cob.WEB / a).is_file()]
    assert faltando == []


def test_detector_resolve_apelido_e_template_aninhado(tmp_path):
    arq = tmp_path / "api.js"
    arq.write_text(
        "const id = (v) => encodeURIComponent(String(v));\n"
        "const I = (itemId) => `/api/itens/${id(itemId)}`;\n"
        "export const substituir = (itemId, corpo) => chamar('PUT', I(itemId), corpo);\n"
        "export const apagar = (itemId, cascata = false) => chamar('DELETE', `${I(itemId)}${cascata ? '?c=1' : ''}`);\n"
        "export const busca = (q) => chamar('GET', `/api/usuarios${consulta({ q, ativo: '1', limite: 20 })}`);\n"
        "export const log = (jobId) =>\n"
        "  chamar('POST', `/api/jobs/${id(jobId)}/log${consulta({ apos: 1 })}`);\n"
        "export const miniaturaUrl = (itemId) => `${I(itemId)}/miniatura`;\n",
        encoding="utf-8",
    )
    vistas = {(c["metodo"], c["url"]) for c in cob.chamadas([arq])}
    assert ("PUT", "/api/itens/{x}") in vistas
    assert ("DELETE", "/api/itens/{x}") in vistas
    assert ("GET", "/api/usuarios") in vistas
    assert ("POST", "/api/jobs/{x}/log") in vistas
    assert ("GET", "/api/itens/{x}/miniatura") in vistas  # URL de imagem: sem chamada = leitura


def test_detector_da_o_metodo_da_chamada_mais_proxima_na_mesma_linha(tmp_path):
    """UX-06: `novo ? enviar('/api/papeis', c) : alterar(`/api/papeis/${p.id}`, c)` numa linha só — antes o PUT
    era lido como POST (o primeiro nome da linha valia para todos os literais) e /api/papeis/{id} ficava
    'sem controle' na cobertura."""
    arq = tmp_path / "papeis.js"
    arq.write_text(
        "const r = novo ? await enviar('/api/papeis', corpo) : await alterar(`/api/papeis/${p.id}`, corpo);\n"
        "const x = await apagar(`/api/tokens/${tk.id}`); const y = await obter('/api/tokens');\n",
        encoding="utf-8",
    )
    vistas = {(c["metodo"], c["url"]) for c in cob.chamadas([arq])}
    assert ("POST", "/api/papeis") in vistas
    assert ("PUT", "/api/papeis/{x}") in vistas
    assert ("DELETE", "/api/tokens/{x}") in vistas
    assert ("GET", "/api/tokens") in vistas


def test_casamento_de_template_com_rota():
    assert cob._casa("/api/itens/{x}/versoes/{x}", "/api/itens/{id}/versoes/{n}")
    assert not cob._casa("/api/itens/{x}", "/api/itens/{id}/versoes")
    assert cob._casa("/api/jobs/resumo", "/api/jobs/resumo")
