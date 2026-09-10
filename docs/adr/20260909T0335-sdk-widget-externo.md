# SDK de widget externo por inquilino (item L5-36-widgets-personalizados-sdk)

Data: 09/09/2026. Estado: aceito. Par: ADR `20260907T1930-motor-de-widgets` (L5-06) e
`20260908T1050-fontes-vistas-mensagens` (L5-07); conceito `laco/decomposicao/L5_CONCEITO.md` (widgets).

## Contexto
O motor de widgets só conhece os tipos da casa (REGISTRO fechado no navegador). Inquilino que quiser um
widget próprio precisava de deploy. O item pede: instalar widget por pacote (sem deploy), com procedência
auditable e sem abrir a página a código que a casa não conferiu.

## Decisões
1. **Pacote = {manifesto, modulo, i18n?, sandbox?}, instalado por POST** `/api/widgets/externos`
   (privilégio `org.configurar`, só sessão). Tabela `plat.widget_externo` com PK (tenant_id, nome) e
   upsert: reinstalar atualiza. O **sha256 é calculado na instalação** e volta em toda listagem.
2. **O mesmo manifesto passa nas duas pontas**: `app/widgets/modelos.py` na instalação e
   `web/js/widgets/registro.js::validarManifesto` no carregamento (mesmos regex de nome/elemento/semver,
   mesma recusa de `api_widget ≠ 1` nomeando o widget — a acusação de API antiga). O servidor aceita só
   `modulo` relativo (`./x.js`); a URL de serviço é do próprio servidor e nunca do pacote.
3. **Confere-antes-de-correr no navegador** (`externos.js`): baixa o módulo, reconfere o sha256 com
   `crypto.subtle` sobre o TEXTO e é esse texto que corre — blob URL no modo normal (o motor importa o
   blob), cache `modulosVerificados` no sandbox. Nunca uma segunda descarga.
4. **Sandbox = iframe `allow-scripts` SEM `allow-same-origin`, com CSP embutido** (`connect-src 'none'`,
   `default-src 'none'`) e código em linha no srcdoc (`</script` neutralizado). Origem opaca:
   `document.cookie` lança, fetch sai sem credenciais e é barrado pelo CSP. Ponte por postMessage nos dois
   sentidos, com portão: o sandbox só emite eventos do `manifesto.eventos` e só recebe ações do
   `manifesto.acoes` (portão do motor). `<plat-widget-sandboxe>` é um PlatWidget comum na página, então
   ligações, edições e o chrome do construtor valem para ele de graça.
5. **Procedência visível e auditável**: `data-widget-origem` no iframe (nome, versão, sha256 curto);
   GET do módulo passa pelo log de acesso; `instalado_por`/`instalado_em` no banco; desinstalação vira
   evento (`widgets/desinstalar`).
6. **i18n com namespace fechado**: toda chave do pacote precisa começar com `manifesto.i18n.`
   (`widget.<nome>.`); chave fora do namespace é recusada na instalação (422) e descartada com aviso no
   navegador — pacote nenhum sobrescreve tradução da casa nem de outro widget
   (`i18n.acrescentar` injeta em tempo de execução).
7. **Tetos**: módulo ≤ 256 kB, i18n ≤ 500 chaves × 2000 caracteres, e o que o documento já tem por nó.
8. **Pacote de exemplo da casa** (`web/ext/exemplo/semaforo`, sandbox) + empacotador stdlib
   (`scripts/widget_empacotar.py`): pasta → envelope do POST. O verificador do `make check`
   (`tests/unit/test_widget_externo_check.py`) roda `validarManifesto` do navegador no pacote de exemplo
   via node — as duas pontas não podem deixar de falar a mesma língua.

## Ressalva honesta
A adaptação `web/ext/<inquilino>/` (arquivos servidos do disco, prevista no rascunho do item) virou
tabela + API: arquivo do disco não passa pelo log de acesso nem pelo RLS de inquilino. L0-07
(configurações da organização) ainda não tinha ramo quando este item foi construído; a instalação usa o
privilégio `org.configurar` já existente, e a revisão em cima do L0-07 é adaptação na junção.

## Consequências
Widget externo do inquilino entra em /aplicativo sem deploy, com o mesmo portão de ligação dos widgets da
casa. Código em modo normal corre com privilégio de página — o manual manda sandbox para terceiro e modo
normal só para código auditado. Versionar API (`api_widget`) já existe; migrá-la é recusar o pacote velho
com a mensagem que diz o que fazer.
