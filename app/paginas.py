"""Páginas servidas pela API a partir de web/ com Cache-Control: no-store (ADR 0002 seção 15). Cada trilha
acrescenta a sua linha em PAGINAS; main.py só inclui o router. Arquivo ausente = 404 (nunca uma casca)."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.erros import ErroAPI

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
PAGINAS = {
    # --- identidade (L0-02)
    "/entrar": "login.html",
    "/conta": "conta.html",
    "/admin/usuarios": "admin/usuarios.html",
    "/admin/grupos": "admin/grupos.html",
    "/admin/papeis": "admin/papeis.html",
    "/admin/tokens": "admin/tokens.html",
    "/admin/log": "admin/log.html",
    # --- configurações da organização (L0-07-a-configuracoes-org)
    "/admin/organizacao": "admin/organizacao.html",
    # --- catálogo (L0-03)
    "/conteudo": "conteudo.html",
    "/conteudo/lixeira": "conteudo_lixeira.html",
    "/conteudo/{id}": "conteudo_item.html",
    "/c/{token}": "compartilhado.html",
    # --- mapa (L2-01-a)
    "/mapa": "mapa.html",
    # --- ferramentas de análise (L2-05-a): formulário gerado do manifesto
    "/analise": "analise.html",
    # --- conexões externas (L6-02-a/L6-02-l/L6-05)
    "/conexoes": "conexoes.html",
    # --- SMTP, convite de membro e redefinição de senha (L0-07-d-smtp-convites): públicas, sem sessão
    "/aceitar-convite": "aceitar_convite.html",
    "/redefinir-senha": "redefinir_senha.html",
    # --- upload retomável (L0-04-a-upload-arquivo)
    "/uploads": "uploads.html",
}
router = APIRouter()


def servir(arquivo: str) -> FileResponse:
    caminho = WEB / arquivo
    if not caminho.is_file():
        raise ErroAPI(404, "pagina_inexistente", "página inexistente")
    return FileResponse(caminho, media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-store"})


def _registrar(caminho: str, arquivo: str) -> None:
    async def pagina():
        return servir(arquivo)

    pagina.__name__ = "pagina_" + caminho.strip("/").replace("/", "_")
    router.add_api_route(caminho, pagina, methods=["GET", "HEAD"], include_in_schema=False)


for _caminho, _arquivo in PAGINAS.items():
    _registrar(_caminho, _arquivo)
