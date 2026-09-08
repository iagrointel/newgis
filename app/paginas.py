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
    # --- categorias do inquilino (UX-12-categorias-sem-controle): PUT /api/categorias e POST /api/categorias/importar
    "/admin/categorias": "admin/categorias.html",
    # item UX-18-plataforma-sem-tela: console do superadmin (inquilinos)
    "/admin/inquilinos": "admin/inquilinos.html",
    # --- catálogo (L0-03)
    "/conteudo": "conteudo.html",
    "/conteudo/lixeira": "conteudo_lixeira.html",
    "/conteudo/{id}": "conteudo_item.html",
    "/c/{token}": "compartilhado.html",
    # --- mapa (L2-01-a)
    "/mapa": "mapa.html",
    # --- acervo da casa (L6-01-c-tela-acervo): equivalente do Living Atlas, sobre plat.acervo_ficha
    "/acervo": "acervo.html",
    # --- conexões externas (L6-02-a/L6-02-l/L6-05)
    "/conexoes": "conexoes.html",
    # item UX-14-geocodificador-sem-tela: tela de trabalho do geocodificador (POST /api/geocodificar e /api/reverso)
    "/geocodificar": "geocodificar.html",
    # --- SMTP, convite de membro e redefinição de senha (L0-07-d-smtp-convites): públicas, sem sessão
    "/aceitar-convite": "aceitar_convite.html",
    "/redefinir-senha": "redefinir_senha.html",
    # --- upload retomável (L0-04-a-upload-arquivo)
    "/uploads": "uploads.html",
    # item UX-16-ingestao-sem-tela: importações (arquivo enviado -> camada vetorial)
    "/importacoes": "importacoes.html",
    # --- sistema de design (UX-01-sistema-de-design): guia viva de tokens e componentes
    "/estilo-guia": "estilo_guia.html",
    # --- construtor por arrasto (L5-08-editor-arrasto): ?item=<id de item app/painel>
    "/construtor": "construtor.html",
    # --- executor de páginas e layout (L5-01-a-layout-paginas): ?item=<id>&pagina=<caminho>
    "/executar": "executar.html",
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
