"""Sistema de design (item UX-01-sistema-de-design): toda tela usa só os tokens — 0 cor e 0 tamanho literal fora de
web/estilo/tokens.css, medido por docs/verificar_tokens.py. Aqui:

1. a varredura de web/ (css, html, js; fora vendor/ e dados/) devolve lista vazia; a mensagem traz arquivo:linha;
2. toda exceção declarada em web/estilo/tokens_excecoes.json aponta para arquivo que existe e tem motivo;
3. o próprio detector é provado contra trechos conhecidos (hex em CSS, rgba em style embutido, font-size literal,
   var() com reserva literal, e o que NÃO deve contar: âncora #id em JS, cor dentro de comentário CSS, `0`);
4. tokens.css define os semânticos que as folhas usam (nenhuma var(--x) sem definição)."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "docs"))

import verificar_tokens as vt  # noqa: E402 — módulo em docs/, fora do pacote app


def test_nenhum_literal_de_cor_ou_tamanho_fora_de_tokens():
    lista = vt.ocorrencias()
    assert lista == [], "literais fora de web/estilo/tokens.css:\n" + "\n".join(lista)


def test_excecoes_apontam_para_arquivo_existente_com_motivo():
    assert vt.excecoes_sem_arquivo() == []
    for arquivo, motivo in vt._excecoes().items():
        assert len(motivo) > 20, f"exceção {arquivo} sem motivo escrito"


def test_detector_pega_o_que_deve_e_ignora_o_que_nao_deve():
    css = (
        "/* comentário com #ffffff e 12px */\n"
        ".a { color: #fff; }\n"
        ".b { background: rgba(0, 0, 0, .5); }\n"
        ".c { font-size: .85rem; }\n"
        ".d { padding: 0; margin: 0 auto; }\n"
        ".e { border-radius: var(--raio, 6px); }\n"
        ".f { width: 220px; height: 3rem; }\n"
    )
    achados = vt._ocorrencias_css(css, "x.css")
    linhas = sorted(int(a.split(":")[1]) for a in achados)
    assert linhas == [2, 3, 4, 6], achados  # 1 é comentário; 5 são zeros/auto; 7 é layout (largura/altura)
    js = "const destino = '/conta#senha';\nel.style.width = `${pct}%`;\nel.style.color = '#ff0000';\n"
    achados_js = vt._ocorrencias_estilo_embutido(js, "x.js", vt.RE_ESTILO_JS.finditer(js))
    assert [int(a.split(":")[1]) for a in achados_js] == [3], achados_js
    html = '<div style="padding: 4px; color: red"></div>\n<div style="display:none"></div>\n'
    achados_html = vt._ocorrencias_estilo_embutido(html, "x.html", vt.RE_ESTILO_HTML.finditer(html))
    assert [int(a.split(":")[1]) for a in achados_html] == [1], achados_html


def test_toda_variavel_usada_nas_folhas_esta_definida_em_tokens():
    definidas = set(re.findall(r"(--[a-z0-9-]+)\s*:", vt.TOKENS.read_text(encoding="utf-8")))
    usadas = {}
    for arq in vt._arquivos():
        if arq.suffix != ".css":
            continue
        texto = vt._apagar_comentarios(arq.read_text(encoding="utf-8"))
        # variáveis definidas localmente na própria folha (ex.: --amostra no guia) também valem
        definidas_local = set(re.findall(r"(--[a-z0-9-]+)\s*:", texto))
        for v in re.findall(r"var\((--[a-z0-9-]+)", texto):
            if v not in definidas and v not in definidas_local:
                usadas.setdefault(v, []).append(str(arq.relative_to(ROOT)))
    assert usadas == {}, f"var() sem definição em tokens.css: {usadas}"
