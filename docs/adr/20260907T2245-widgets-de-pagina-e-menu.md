# ADR 20260907T2245 — widgets de página e de menu sobre o motor de widgets

Item L5-01-d-widgets-pagina-menu. Segue L5_CONCEITO D1 (sem framework), D19 (manifesto por widget, `import()`
só dos citados), D23 (Markdown + DOMPurify obrigatório) e a regra "zero renderizador duplicado" do L5-06.

## Decisões

1. **O executor de páginas (L5-01-a) delega ao motor de widgets (L5-06).** `web/js/executor/executor.js` mantém o
   único despacho por tipo; para os tipos de widget de página/menu ele chama `criarWidget` de
   `web/js/widgets/motor.js` (exportado neste item), depois de `prepararWidgets` carregar os módulos usados no
   documento inteiro. `texto` e `imagem`, que o executor desenhava por conta própria, passam pelo mesmo widget
   que a página `/aplicativo` publica; o vocabulário antigo da paleta (`nivel: corpo|titulo|legenda`) é traduzido
   em `configuracaoDoNo`. Eventos `*.pagina` (botão, menu, cartão) trocam de página pelo barramento.
2. **Segurança em duas camadas.** `web/js/widgets/seguro.js` (puro, testado no node) decide URL (`urlSegura`:
   só http/https/mailto/tel ou caminho relativo com uma barra; `data:image/*` só para imagem), domínio do embed
   (`hostPermitido`: https e lista explícita, subdomínio permitido, sufixo falso não) e tokens de sandbox (nunca
   `allow-same-origin`); todo HTML de documento entra pelo DOMPurify (`htmlSeguro`, agora com `proibir` para
   cortar `<style>`, cujo `@import` ainda disparava um pedido de rede). Texto puro continua só por `textContent`.
3. **Markdown mínimo próprio** (títulos, negrito, itálico, código, listas, link, imagem, divisor), ~90 linhas,
   em vez de markdown-it (115 kB) — D23 manda começar pelo próprio. `{campo}` é substituído pelo valor da
   feição selecionada já escapado; campo ausente fica literal para o autor ver.
4. **Incorporar**: por URL só https em domínio da lista, `sandbox` com os tokens permitidos; por HTML o conteúdo
   sanitizado vai em `srcdoc` com `sandbox=""` (nem scripts nem mesma origem).
5. **QR local**: `GET /api/qr.svg?texto=` reusa o gerador do 2FA (`app/auth/totp.py::qr_svg`, pacote `qrcode`)
   — nenhum serviço externo; sessão ou token, texto limitado por `limites.QR_TEXTO_MAX`.
6. **Menu configurável é `menu_widget`** na paleta, para não colidir com `menu` (navegação automática entre
   páginas do L5-01-a); no registro de widgets o nome continua `menu`.
7. **Tema e idioma** gravam a escolha em `localStorage` e mexem no `<html>` (`data-theme`, `lang`); o seletor de
   idioma só oferece o que o documento lista e que existe em `web/js/i18n/`.

## Fora deste item
Ícone/vídeo/áudio e "lista" (widgets de dado do L5-01-c); ações configuráveis entre widgets (L5-01-e);
QR do link de app publicado com token (L5-14); idiomas além de pt-BR (L7-10).
