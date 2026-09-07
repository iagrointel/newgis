#!/usr/bin/env python3
"""Gera os ícones do manifest do PWA de campo (item L2-07-a-pwa-instalavel-cache), em `web/campo/`.

Não é chamado em produção: roda uma vez (ou de novo se a marca mudar) e o PNG resultante fica versionado no
git, como o favicon.svg já é. Mesma paleta do favicon (`web/favicon.svg`: fundo #1f3a5f, texto #e8f0fa) para
o ícone do PWA não destoar do resto do produto. Desenho simples e sólido (sem borda fina, sem detalhe fino)
de propósito: precisa sobreviver ao recorte de "maskable" do Android, que corta as bordas em círculo."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

RAIZ = Path(__file__).resolve().parents[1]
SAIDA = RAIZ / "web" / "campo"
FUNDO = (31, 58, 95, 255)  # #1f3a5f
LETRA = (232, 240, 250, 255)  # #e8f0fa


def _fonte(tamanho: int) -> ImageFont.FreeTypeFont:
    for caminho in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ):
        if Path(caminho).is_file():
            return ImageFont.truetype(caminho, tamanho)
    return ImageFont.load_default()


def gerar(tamanho: int) -> Image.Image:
    img = Image.new("RGBA", (tamanho, tamanho), FUNDO)
    d = ImageDraw.Draw(img)
    fonte = _fonte(int(tamanho * 0.58))
    letra = "p"
    caixa = d.textbbox((0, 0), letra, font=fonte)
    largura, altura = caixa[2] - caixa[0], caixa[3] - caixa[1]
    d.text(((tamanho - largura) / 2 - caixa[0], (tamanho - altura) / 2 - caixa[1]), letra, font=fonte, fill=LETRA)
    return img


if __name__ == "__main__":
    SAIDA.mkdir(parents=True, exist_ok=True)
    for tamanho in (192, 512):
        gerar(tamanho).save(SAIDA / f"icone-{tamanho}.png", "PNG")
        print(f"escrito {SAIDA / f'icone-{tamanho}.png'}")
