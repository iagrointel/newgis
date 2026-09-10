"""Portal de API (item L7-08-d): a página `/portal` e a lista de exemplos executáveis.

A página é servida do disco com uma Política de Segurança de Conteúdo (CSP) que só admite a própria
origem. Isso é o segundo cinto do "nenhum recurso externo": o primeiro é não haver nenhuma URL externa
no HTML/JS (conferido por teste), o segundo é o navegador recusar a busca se um dia alguém escrever uma.
`frame-ancestors 'none'` repete no cabeçalho o que o nginx já diz em `X-Frame-Options: DENY` — CSP é o
que navegador moderno obedece, o X-Frame-Options é o legado.

Os 20 exemplos (10 Python + 10 JavaScript) NÃO são texto copiado para dentro do portal: são os arquivos
de `exemplos/`, lidos do disco a cada pedido. Um só artefato, que a suíte executa de verdade contra a
API viva (`tests/e2e/test_portal.py`), e é o mesmo que o portal mostra — não há versão do portal que
possa divergir da versão que roda.
"""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.erros import ErroAPI

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
EXEMPLOS = ROOT / "exemplos"
LINGUAGENS = {"python": ("*.py", "Python 3 (biblioteca padrão, sem dependência)"),
              "js": ("*.mjs", "JavaScript (Node 18+, fetch nativo, sem dependência)")}
CSP = (
    "default-src 'none'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "form-action 'none'; "
    "base-uri 'none'; "
    "frame-ancestors 'none'"
)
router = APIRouter()


def listar_exemplos() -> list[dict]:
    """Os arquivos de `exemplos/<linguagem>/`, em ordem de nome, com o código lido do disco."""
    saida = []
    for linguagem, (padrao, ambiente) in LINGUAGENS.items():
        pasta = EXEMPLOS / linguagem
        if not pasta.is_dir():
            continue
        for caminho in sorted(pasta.glob(padrao)):
            if caminho.name.startswith("_"):
                continue  # _apoio.py / _apoio.mjs são o módulo comum, não exemplo
            texto = caminho.read_text(encoding="utf-8")
            titulo = ""
            for linha in texto.splitlines():
                if linha.startswith(("# ", "// ")):
                    titulo = linha.split(" ", 1)[1].strip()
                    break
            saida.append(
                {
                    "arquivo": f"exemplos/{linguagem}/{caminho.name}",
                    "linguagem": linguagem,
                    "ambiente": ambiente,
                    "titulo": titulo,
                    "codigo": texto,
                }
            )
    return saida


@router.get("/api/portal/exemplos", openapi_extra={"x-auth": "-", "x-privilegio": "publico"})
def exemplos():
    """Os 20 exemplos executáveis que o portal mostra, lidos de `exemplos/` (mesmos arquivos que a suíte roda)."""
    lista = listar_exemplos()
    return {"total": len(lista), "exemplos": lista}


@router.api_route("/portal", methods=["GET", "HEAD"], include_in_schema=False)
def pagina_portal():
    caminho = WEB / "portal.html"
    if not caminho.is_file():
        raise ErroAPI(404, "pagina_inexistente", "página inexistente")
    return FileResponse(
        caminho,
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "no-store", "Content-Security-Policy": CSP},
    )
