"""e2e dos vídeos por tarefa (item L7-04-d) contra a instalação real, DEPOIS de `make videos`.

Prova: (1) a página /videos lista os vídeos do manifesto, cada um com a seção do manual e as três
legendas; (2) o vídeo reproduz no navegador do e2e com duração dentro do limite de 3 minutos e as
cues da legenda carregam; (3) um quadro do vídeo é confrontado com a tela real da mesma página
(captura do quadro por canvas x captura ao vivo, diferença média por pixel com teto frouxo).

Precisa dos artefatos de `make videos` em web/videos/ (fora do git); sem manifesto o e2e é pulado
com a razão escrita — nunca falha por falta de build."""

import base64
import io
import json
from pathlib import Path

import pytest

from tests.e2e.apoio import Tela

RAIZ = Path(__file__).resolve().parents[2]
SAIDA = RAIZ / "web" / "videos" / "manifesto.json"
CAPTURAS = Path(__file__).resolve().parent / "capturas"
ITEM = "L7-04-d-videos-por-tarefa"
LIMITE_DURACAO_S = 180.0
TETO_DIFERENCA_MEDIA = 24.0  # 0-255; compressão do vídeo e números vivos da tela entram nessa folga

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


@pytest.fixture(scope="module")
def manifesto(api_videos):
    """A mesma cópia que GET /api/videos serve (o /api/videos exige sessão; a página busca autenticada)."""
    return json.loads(SAIDA.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def api_videos(rotas_api):
    if not SAIDA.exists():
        pytest.skip("web/videos/manifesto.json ausente; rode make videos contra esta instalação")
    if "/api/videos" not in rotas_api:
        pytest.skip("o backend desta trilha ainda não publica /api/videos")
    return True


def _video_da_pagina(page, id_tarefa: str):
    return page.evaluate_handle(
        "(id) => [...document.querySelectorAll('video')].find(v => v.src.includes(`/${id}.mp4`))",
        arg=id_tarefa,
    )


def test_pagina_videos_lista_manifesto_com_manual_e_legendas(page, base_url, credenciais_demo, manifesto):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha, proximo="/videos")
    tela.ir("/videos")
    total = int(page.text_content("#videos-total").strip())
    assert total == len(manifesto["tarefas"])
    cartoes = page.locator(".video-cartao")
    assert cartoes.count() == total
    for id_tarefa, meta in manifesto["tarefas"].items():
        cartao = page.locator(".video-cartao", has_text=meta["titulo"]).first
        assert meta["manual"] in (cartao.text_content() or ""), id_tarefa
    trilhas = page.locator(".video-cartao video track")
    assert trilhas.count() == total * 3


def test_playback_duracao_e_legendas_no_navegador(page, base_url, credenciais_demo, manifesto):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha, proximo="/videos")
    tela.ir("/videos")
    alvo = _video_da_pagina(page, "saude")
    estado = page.evaluate(
        """async (v) => {
            await new Promise((ok, falhou) => {
                if (v.readyState >= 1) { ok(); return; }
                v.addEventListener('loadedmetadata', ok, { once: true });
                v.addEventListener('error', falhou, { once: true });
            });
            v.muted = true;
            await v.play();
            return { duration: v.duration };
        }""",
        alvo,
    )
    assert 0 < estado["duration"] <= LIMITE_DURACAO_S, estado
    page.wait_for_function("v => v.currentTime > 0.5", arg=alvo, timeout=15000)
    page.evaluate("v => v.pause()", alvo)
    # legenda: mode=showing força a carga do vtt; as cues têm de existir
    cues = page.evaluate(
        """async (v) => {
            const t = v.textTracks[0];
            t.mode = 'showing';
            for (let i = 0; i < 40 && t.cues.length === 0; i++) {
                await new Promise(ok => setTimeout(ok, 250));
            }
            return { modo: t.mode, idioma: t.language, cues: t.cues.length };
        }""",
        alvo,
    )
    assert cues["modo"] == "showing" and cues["cues"] > 0 and cues["idioma"].startswith("pt"), cues


def test_quadro_do_video_confrontado_com_a_tela_real(page, base_url, credenciais_demo, manifesto):
    slug, login, senha = credenciais_demo
    janela = manifesto["tarefas"]["saude"]["passos_s"][0]
    meio = (janela[0] + janela[1]) / 2 + 0.4
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha, proximo="/videos")
    tela.ir("/videos")
    alvo = _video_da_pagina(page, "saude")
    quadro_b64 = page.evaluate(
        """async ([v, tempo]) => {
            await new Promise((ok, falhou) => {
                if (v.readyState >= 1) { ok(); return; }
                v.addEventListener('loadedmetadata', ok, { once: true });
                v.addEventListener('error', falhou, { once: true });
            });
            for (const t of v.textTracks) { t.mode = 'disabled'; }
            await new Promise(ok => {
                v.addEventListener('seeked', ok, { once: true });
                v.currentTime = tempo;
            });
            const c = document.createElement('canvas');
            c.width = v.videoWidth; c.height = v.videoHeight;
            c.getContext('2d').drawImage(v, 0, 0);
            return c.toDataURL('image/png');
        }""",
        [alvo, meio],
    )
    assert quadro_b64.startswith("data:image/png;base64,"), quadro_b64[:40]

    # a tela real, agora: a mesma página que o vídeo filmou, no MESMO estado de sessão
    # (a tarefa saude é gravada sem login prévio, então a comparação é com a página pública)
    tela.sair()
    tela.ir("/")
    page.wait_for_function(
        "() => document.getElementById('saude-json')?.textContent?.trim().startsWith('{')",
        timeout=15000,
    )
    ao_vivo = tela.page.screenshot()

    CAPTURAS.mkdir(parents=True, exist_ok=True)
    (CAPTURAS / f"{ITEM}_quadro_do_video.png").write_bytes(
        base64.b64decode(quadro_b64.split(",", 1)[1]))
    (CAPTURAS / f"{ITEM}_tela_ao_vivo.png").write_bytes(ao_vivo)

    from PIL import Image

    def cinza_32x20(bytes_png: bytes):
        imagem = Image.open(io.BytesIO(bytes_png)).convert("L")
        return list(imagem.resize((32, 20)).tobytes())  # 'L': 1 byte por pixel

    a = cinza_32x20(base64.b64decode(quadro_b64.split(",", 1)[1]))
    b = cinza_32x20(ao_vivo)
    diferenca = sum(abs(x - y) for x, y in zip(a, b, strict=True)) / len(a)
    assert diferenca <= TETO_DIFERENCA_MEDIA, (
        f"quadro do vídeo e tela real divergem (diferença média {diferenca:.1f})")
