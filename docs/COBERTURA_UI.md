# Cobertura da interface (gerado — não editar à mão)

Gerado por `docs/gerar_cobertura_ui.py` (item UX-00-mapa-de-cobertura-da-interface). Rotas lidas da aplicação; chamadas lidas de `web/`; telas de `app/paginas.py`. Heurísticas de texto declaradas no cabeçalho do gerador: o que elas não veem, o e2e vê. Regra da trilha: nenhuma rota fica só no backend.

## Placar

| medida | valor |
|---|---|
| rotas (método × caminho) | 240 |
| coberto | 184 |
| sem controle | 27 |
| sem tela | 12 |
| externo | 1 |
| externo sem exposição | 16 |
| cobertas sem estado de erro perto da chamada | 4 |
| lacunas de ESCRITA (linha de base do teste) | 24 |
| URLs chamadas pela tela que não existem na API | 2 |

## Rotas → tela/controle → estado

| método | rota | grupo | tela | controle (arquivo:linha) | estado | erro |
|---|---|---|---|---|---|---|
| GET | `/api/acervo` | acervo | `/admin`, `/admin/acervo` | `web/js/auth/acervo.js:76`<br>`web/js/auth/admin.js:97` | **coberto** | com erro |
| GET | `/api/acervo/{fonte_id}` | acervo | `/admin/acervo` | `web/js/auth/acervo.js:104` | **coberto** | com erro |
| POST | `/api/acervo/{fonte_id}/adicionar` | acervo | `/admin/acervo` | `web/js/auth/acervo.js:154` | **coberto** | com erro |
| GET | `/api/agendas` | agendas | `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:50` | **coberto** | com erro |
| POST | `/api/agendas` | agendas | `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:52` | **coberto** | com erro |
| GET | `/api/agendas/{agenda_id}` | agendas | `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:51` | **coberto** | com erro |
| PUT | `/api/agendas/{agenda_id}` | agendas | `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:53` | **coberto** | com erro |
| DELETE | `/api/agendas/{agenda_id}` | agendas | `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:54` | **coberto** | com erro |
| POST | `/api/agendas/{agenda_id}/pausar` | agendas | `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:55` | **coberto** | com erro |
| POST | `/api/agendas/{agenda_id}/retomar` | agendas | `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:56` | **coberto** | com erro |
| POST | `/api/agendas/{agenda_id}/rodar-agora` | agendas | `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:57` | **coberto** | com erro |
| GET | `/api/anotacoes` | mapa | `/mapa` | `web/js/mapa/anotacoes.js:62` | **coberto** | com erro |
| POST | `/api/anotacoes` | mapa | `/mapa` | `web/js/mapa/anotacoes.js:88` | **coberto** | com erro |
| PATCH | `/api/anotacoes/{id}` | mapa | — | — | **sem controle** | não se aplica |
| DELETE | `/api/anotacoes/{id}` | mapa | — | — | **sem controle** | não se aplica |
| GET | `/api/arquivos` | arquivos | — | — | **sem controle** | não se aplica |
| POST | `/api/arquivos` | arquivos | — | — | **sem controle** | não se aplica |
| GET | `/api/arquivos/_varredura` | arquivos | `/admin/organizacao` | `web/js/auth/organizacao.js:185` | **coberto** | sem estado de erro |
| GET | `/api/arquivos/{sha256}` | arquivos | `/admin/organizacao` | `web/js/auth/organizacao.js:185` | **coberto** | sem estado de erro |
| DELETE | `/api/arquivos/{sha256}` | arquivos | — | — | **sem controle** | não se aplica |
| GET | `/api/camadas/{id}/feicoes/{fid}/popup` | mapa-popup | `/mapa` | `web/js/mapa/atributos.js:97` | **coberto** | com erro |
| GET | `/api/camadas/{item_id}/tabela/colunas` | tabela | `/mapa` | `web/js/mapa/tabela.js:105` | **coberto** | com erro |
| POST | `/api/camadas/{item_id}/tabela/estatisticas` | tabela | `/mapa` | `web/js/mapa/tabela.js:369` | **coberto** | com erro |
| POST | `/api/camadas/{item_id}/tabela/linhas` | tabela | `/mapa` | `web/js/mapa/tabela.js:120`<br>`web/js/mapa/tabela.js:134` | **coberto** | com erro |
| GET | `/api/camadas/{item_id}/tabela/vista` | tabela | `/mapa` | `web/js/mapa/tabela.js:315`<br>`web/js/mapa/tabela.js:331` | **coberto** | com erro |
| PUT | `/api/camadas/{item_id}/tabela/vista` | tabela | `/mapa` | `web/js/mapa/tabela.js:144` | **coberto** | com erro |
| GET | `/api/categorias` | categorias | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:147` | **coberto** | com erro |
| PUT | `/api/categorias` | categorias | — | — | **sem controle** | não se aplica |
| POST | `/api/categorias/importar` | categorias | — | — | **sem controle** | não se aplica |
| GET | `/api/compartilhado/{token}` | compartilhamento | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:130` | **coberto** | com erro |
| GET | `/api/compartilhado/{token}/itens/{id}` | compartilhamento | `/c/{token}` | `web/js/catalogo/compartilhado.js:111` | **coberto** | com erro |
| GET | `/api/compartilhado/{token}/itens/{id}/miniatura` | compartilhamento | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:131` | **coberto** | com erro |
| GET | `/api/conexoes` | conexoes | `/conexoes` | `web/js/conexoes/conexoes.js:386` | **coberto** | com erro |
| POST | `/api/conexoes` | conexoes | `/conexoes` | `web/js/conexoes/conexoes.js:274` | **coberto** | com erro |
| GET | `/api/conexoes/{id}` | conexoes | `/conexoes` | `web/js/conexoes/conexoes.js:233` | **coberto** | com erro |
| PATCH | `/api/conexoes/{id}` | conexoes | `/conexoes` | `web/js/conexoes/conexoes.js:273` | **coberto** | com erro |
| DELETE | `/api/conexoes/{id}` | conexoes | `/conexoes` | `web/js/conexoes/conexoes.js:149` | **coberto** | com erro |
| POST | `/api/conexoes/{id}/publicar` | conexoes | `/conexoes` | `web/js/conexoes/conexoes.js:120` | **coberto** | com erro |
| GET | `/api/conexoes/{id}/saude-historico` | conexoes | `/conexoes` | `web/js/conexoes/conexoes.js:93` | **coberto** | com erro |
| POST | `/api/conexoes/{id}/testar` | conexoes | `/conexoes` | `web/js/conexoes/conexoes.js:72` | **coberto** | com erro |
| GET | `/api/convites` | convites | `/admin`, `/admin/usuarios` | `web/js/auth/admin.js:68`<br>`web/js/auth/convites.js:38` | **coberto** | com erro |
| POST | `/api/convites` | convites | `/admin/usuarios` | `web/js/auth/convites.js:53` | **coberto** | com erro |
| POST | `/api/convites/aceitar` | convites | `/aceitar-convite` | `web/js/auth/aceitar_convite.js:82` | **coberto** | com erro |
| GET | `/api/convites/resolver` | convites | `/aceitar-convite` | `web/js/auth/aceitar_convite.js:54` | **coberto** | com erro |
| DELETE | `/api/convites/{id}` | convites | `/admin/usuarios` | `web/js/auth/convites.js:25` | **coberto** | com erro |
| GET | `/api/esquemas` | catalogo | — | — | **sem controle** | não se aplica |
| GET | `/api/esquemas/{tipo}` | catalogo | — | — | **sem controle** | não se aplica |
| GET | `/api/eu` | eu | `/`, `/admin`, `/admin/acervo`, `/admin/grupos`, `/admin/log`, `/admin/organizacao`, `/admin/papeis`, `/admin/tokens`, `/admin/usuarios`, `/c/{token}`, `/conexoes`, `/construtor`, `/conta`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/entrar`, `/estilo-guia`, `/executar`, `/mapa`, `/tarefas`, `/tarefas/{job_id}`, `/uploads` | `web/app.js:36`<br>`web/js/auth/conta.js:90`<br>`web/js/auth/sessao.js:59`<br>`web/js/conexoes/conexoes.js:451`<br>`web/js/jobs/tarefas.js:54` | **coberto** | com erro |
| PUT | `/api/eu` | eu | `/conta` | `web/js/auth/conta.js:143` | **coberto** | com erro |
| POST | `/api/eu/2fa/codigos` | eu | `/conta` | `web/js/auth/conta.js:350` | **coberto** | com erro |
| POST | `/api/eu/2fa/confirmar` | eu | `/conta` | `web/js/auth/conta.js:305` | **coberto** | com erro |
| POST | `/api/eu/2fa/desativar` | eu | `/conta` | `web/js/auth/conta.js:336` | **coberto** | com erro |
| POST | `/api/eu/2fa/iniciar` | eu | `/conta` | `web/js/auth/conta.js:292` | **coberto** | com erro |
| GET | `/api/eu/convites` | eu | `/conta` | `web/js/auth/conta.js:405` | **coberto** | com erro |
| POST | `/api/eu/foto` | eu | `/conta` | `web/js/auth/conta.js:190` | **coberto** | com erro |
| DELETE | `/api/eu/foto` | eu | `/conta` | `web/js/auth/conta.js:201` | **coberto** | com erro |
| PUT | `/api/eu/senha` | eu | `/conta` | `web/js/auth/conta.js:231` | **coberto** | com erro |
| GET | `/api/eu/sessoes` | eu | `/conta` | `web/js/auth/conta.js:375` | **coberto** | com erro |
| DELETE | `/api/eu/sessoes` | eu | `/conta` | `web/js/auth/conta.js:383` | **coberto** | com erro |
| DELETE | `/api/eu/sessoes/{id}` | eu | `/conta` | `web/js/auth/conta.js:370` | **coberto** | com erro |
| GET | `/api/eventos` | log | `/admin`, `/admin/acervo`, `/admin/grupos`, `/admin/log`, `/admin/organizacao`, `/admin/papeis`, `/admin/tokens`, `/admin/usuarios`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/auth/admin.js:125`<br>`web/js/auth/comum.js:67`<br>`web/js/auth/log.js:165` | **coberto** | com erro |
| GET | `/api/exportacoes` | exportacao | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:137` | **coberto** | com erro |
| POST | `/api/exportacoes` | exportacao | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/mapa` | `web/js/catalogo/api.js:135`<br>`web/js/mapa/exportar.js:175` | **coberto** | com erro |
| GET | `/api/exportacoes/formatos` | exportacao | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/mapa` | `web/js/catalogo/api.js:134`<br>`web/js/catalogo/api.js:136`<br>`web/js/mapa/exportar.js:23`<br>`web/js/mapa/exportar.js:52` | **coberto** | com erro |
| GET | `/api/exportacoes/{exportacao_id}` | exportacao | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/mapa` | `web/js/catalogo/api.js:134`<br>`web/js/catalogo/api.js:136`<br>`web/js/mapa/exportar.js:23`<br>`web/js/mapa/exportar.js:52` | **coberto** | com erro |
| DELETE | `/api/exportacoes/{exportacao_id}` | exportacao | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:138` | **coberto** | com erro |
| GET | `/api/exportacoes/{exportacao_id}/baixar` | exportacao | — | — | **sem controle** | não se aplica |
| GET | `/api/favoritos` | favoritos | — | — | **sem controle** | não se aplica |
| PUT | `/api/favoritos/{item_id}` | favoritos | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:150` | **coberto** | com erro |
| DELETE | `/api/favoritos/{item_id}` | favoritos | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:151` | **coberto** | com erro |
| GET | `/api/geocodificar` | geocodificador | `/mapa` | `web/js/mapa/busca.js:55` | **coberto** | com erro |
| POST | `/api/geocodificar` | geocodificador | — | — | **sem controle** | não se aplica |
| GET | `/api/grupos` | grupos | `/admin`, `/admin/grupos`, `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/mapa` | `web/js/auth/admin.js:72`<br>`web/js/auth/grupos.js:108`<br>`web/js/catalogo/api.js:159`<br>`web/js/mapa/anotacoes.js:32` | **coberto** | com erro |
| POST | `/api/grupos` | grupos | `/admin/grupos` | `web/js/auth/grupos.js:153` | **coberto** | com erro |
| GET | `/api/grupos/{id}` | grupos | `/admin/grupos` | `web/js/auth/grupos.js:165` | **coberto** | com erro |
| PUT | `/api/grupos/{id}` | grupos | `/admin/grupos` | `web/js/auth/grupos.js:201`<br>`web/js/auth/grupos.js:252` | **coberto** | com erro |
| DELETE | `/api/grupos/{id}` | grupos | `/admin/grupos` | `web/js/auth/grupos.js:233` | **coberto** | com erro |
| POST | `/api/grupos/{id}/aceitar` | grupos | `/admin/grupos`, `/conta` | `web/js/auth/conta.js:400`<br>`web/js/auth/grupos.js:93` | **coberto** | com erro |
| POST | `/api/grupos/{id}/entrar` | grupos | `/admin/grupos`, `/conta` | `web/js/auth/conta.js:400`<br>`web/js/auth/grupos.js:93` | **coberto** | com erro |
| GET | `/api/grupos/{id}/membros` | grupos | `/admin/grupos` | `web/js/auth/grupos.js:243`<br>`web/js/auth/grupos.js:289` | **coberto** | com erro |
| POST | `/api/grupos/{id}/membros` | grupos | `/admin/grupos`, `/conta` | `web/js/auth/conta.js:400`<br>`web/js/auth/grupos.js:310`<br>`web/js/auth/grupos.js:93` | **coberto** | com erro |
| PUT | `/api/grupos/{id}/membros/{uid}` | grupos | `/admin/grupos` | `web/js/auth/grupos.js:285` | **coberto** | com erro |
| DELETE | `/api/grupos/{id}/membros/{uid}` | grupos | `/admin/grupos` | `web/js/auth/grupos.js:221`<br>`web/js/auth/grupos.js:284` | **coberto** | com erro |
| POST | `/api/grupos/{id}/membros/{uid}/aprovar` | grupos | `/admin/grupos` | `web/js/auth/grupos.js:283` | **coberto** | com erro |
| POST | `/api/grupos/{id}/recusar` | grupos | `/admin/grupos`, `/conta` | `web/js/auth/conta.js:400`<br>`web/js/auth/grupos.js:93` | **coberto** | com erro |
| GET | `/api/importacoes` | ingestao | — | — | **sem tela** | não se aplica |
| POST | `/api/importacoes` | ingestao | — | — | **sem tela** | não se aplica |
| GET | `/api/importacoes/formatos` | ingestao | — | — | **sem tela** | não se aplica |
| GET | `/api/importacoes/{id}` | ingestao | — | — | **sem tela** | não se aplica |
| DELETE | `/api/importacoes/{id}` | ingestao | — | — | **sem tela** | não se aplica |
| PUT | `/api/importacoes/{id}/confirmar` | ingestao | — | — | **sem tela** | não se aplica |
| POST | `/api/isocrona` | rede | `/mapa` | `web/js/mapa/rotas.js:230` | **coberto** | com erro |
| GET | `/api/itens` | catalogo | `/c/{token}`, `/construtor`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/mapa` | `web/js/catalogo/api.js:90`<br>`web/js/editor/tela.js:64`<br>`web/js/mapa/tabela.js:388` | **coberto** | com erro |
| POST | `/api/itens` | catalogo | `/c/{token}`, `/construtor`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/mapa` | `web/js/catalogo/api.js:94`<br>`web/js/editor/tela.js:91`<br>`web/js/mapa/mapa.js:351` | **coberto** | com erro |
| GET | `/api/itens/facetas` | catalogo | `/aplicativo`, `/c/{token}`, `/construtor`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/executar`, `/mapa` | `web/js/catalogo/api.js:79`<br>`web/js/catalogo/api.js:91`<br>`web/js/catalogo/api.js:93`<br>`web/js/editor/tela.js:116`<br>`web/js/executor/executar_tela.js:33`<br>`web/js/mapa/mapa.js:393`<br>`web/js/widgets/aplicativo.js:114` | **coberto** | com erro |
| POST | `/api/itens/lote` | catalogo | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:98` | **coberto** | com erro |
| GET | `/api/itens/tags` | catalogo | `/aplicativo`, `/c/{token}`, `/construtor`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/executar`, `/mapa` | `web/js/catalogo/api.js:79`<br>`web/js/catalogo/api.js:92`<br>`web/js/catalogo/api.js:93`<br>`web/js/editor/tela.js:116`<br>`web/js/executor/executar_tela.js:33`<br>`web/js/mapa/mapa.js:393`<br>`web/js/widgets/aplicativo.js:114` | **coberto** | com erro |
| POST | `/api/itens/transferir` | catalogo | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:100` | **coberto** | com erro |
| GET | `/api/itens/{id}` | catalogo | `/aplicativo`, `/c/{token}`, `/construtor`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/executar`, `/mapa` | `web/js/catalogo/api.js:79`<br>`web/js/catalogo/api.js:91`<br>`web/js/catalogo/api.js:92`<br>`web/js/catalogo/api.js:93`<br>`web/js/editor/tela.js:116`<br>`web/js/executor/executar_tela.js:33`<br>`web/js/mapa/mapa.js:393`<br>`web/js/widgets/aplicativo.js:114` | **coberto** | com erro |
| PUT | `/api/itens/{id}` | catalogo | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/mapa` | `web/js/catalogo/api.js:95`<br>`web/js/mapa/mapa.js:350` | **coberto** | com erro |
| PATCH | `/api/itens/{id}` | catalogo | `/c/{token}`, `/construtor`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:96`<br>`web/js/editor/tela.js:168` | **coberto** | com erro |
| DELETE | `/api/itens/{id}` | catalogo | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:97` | **coberto** | com erro |
| GET | `/api/itens/{id}/compartilhamento` | compartilhamento | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:125` | **coberto** | com erro |
| PUT | `/api/itens/{id}/compartilhamento` | compartilhamento | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:126` | **coberto** | com erro |
| GET | `/api/itens/{id}/criado-a-partir-de` | catalogo | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:120` | **coberto** | com erro |
| GET | `/api/itens/{id}/integridade` | catalogo | — | — | **sem controle** | não se aplica |
| GET | `/api/itens/{id}/links` | compartilhamento | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:127` | **coberto** | com erro |
| POST | `/api/itens/{id}/links` | compartilhamento | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:128` | **coberto** | com erro |
| DELETE | `/api/itens/{id}/links/{lid}` | compartilhamento | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:129` | **coberto** | com erro |
| GET | `/api/itens/{id}/metadado.xml` | catalogo | — | — | **sem controle** | não se aplica |
| GET | `/api/itens/{id}/miniatura` | catalogo | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:103` | **coberto** | com erro |
| POST | `/api/itens/{id}/miniatura` | catalogo | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:107` | **coberto** | com erro |
| DELETE | `/api/itens/{id}/miniatura` | catalogo | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:110` | **coberto** | com erro |
| POST | `/api/itens/{id}/miniatura/gerar` | catalogo | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:109` | **coberto** | com erro |
| POST | `/api/itens/{id}/mover` | catalogo | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:99` | **coberto** | com erro |
| GET | `/api/itens/{id}/ordem-de-exclusao` | catalogo | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:121` | **coberto** | com erro |
| PUT | `/api/itens/{id}/relacoes` | catalogo | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:122` | **coberto** | com erro |
| GET | `/api/itens/{id}/usado-por` | catalogo | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:119` | **coberto** | com erro |
| GET | `/api/itens/{id}/versoes` | catalogo | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:113` | **coberto** | com erro |
| GET | `/api/itens/{id}/versoes/{n}` | catalogo | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:114` | **coberto** | com erro |
| POST | `/api/itens/{id}/versoes/{n}/publicar` | catalogo | `/c/{token}`, `/construtor`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:116`<br>`web/js/editor/tela.js:195` | **coberto** | com erro |
| POST | `/api/itens/{id}/versoes/{n}/restaurar` | catalogo | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:115` | **coberto** | com erro |
| GET | `/api/jobs` | jobs | `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:38` | **coberto** | com erro |
| POST | `/api/jobs` | jobs | `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:40` | **coberto** | com erro |
| GET | `/api/jobs/resumo` | jobs | `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:39`<br>`web/js/jobs/api.js:45` | **coberto** | com erro |
| GET | `/api/jobs/tipos` | jobs | `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:39`<br>`web/js/jobs/api.js:46` | **coberto** | com erro |
| GET | `/api/jobs/{job_id}` | jobs | `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:39`<br>`web/js/jobs/api.js:45`<br>`web/js/jobs/api.js:46` | **coberto** | com erro |
| POST | `/api/jobs/{job_id}/cancelar` | jobs | `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:41` | **coberto** | com erro |
| GET | `/api/jobs/{job_id}/eventos` | jobs | `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/eventos.js:41` | **coberto** | sem estado de erro |
| GET | `/api/jobs/{job_id}/log` | jobs | `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:44` | **coberto** | com erro |
| POST | `/api/jobs/{job_id}/repetir` | jobs | `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:42` | **coberto** | com erro |
| GET | `/api/lixeira` | lixeira | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:154` | **coberto** | com erro |
| POST | `/api/lixeira/esvaziar` | lixeira | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:156` | **coberto** | com erro |
| POST | `/api/lixeira/{id}/restaurar` | lixeira | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:155` | **coberto** | com erro |
| GET | `/api/log` | log | `/admin`, `/admin/log` | `web/js/auth/admin.js:100`<br>`web/js/auth/log.js:119`<br>`web/js/auth/log.js:123` | **coberto** | com erro |
| POST | `/api/login` | login | `/entrar` | `web/js/auth/login.js:169` | **coberto** | com erro |
| POST | `/api/login/2fa` | login | `/entrar` | `web/js/auth/login.js:200` | **coberto** | com erro |
| POST | `/api/login/ldap` | login | — | — | **sem controle** | não se aplica |
| GET | `/api/login/provedores` | login | `/entrar` | `web/js/auth/login.js:71` | **coberto** | com erro |
| POST | `/api/logout` | login | `/`, `/admin`, `/admin/acervo`, `/admin/grupos`, `/admin/log`, `/admin/organizacao`, `/admin/papeis`, `/admin/tokens`, `/admin/usuarios`, `/c/{token}`, `/conexoes`, `/construtor`, `/conta`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/entrar`, `/estilo-guia`, `/executar`, `/mapa`, `/tarefas`, `/tarefas/{job_id}`, `/uploads` | `web/js/auth/sessao.js:76` | **coberto** | sem estado de erro |
| GET | `/api/mapa/camadas` | mapa | `/mapa` | `web/js/mapa/catalogo.js:30` | **coberto** | com erro |
| GET | `/api/mapa/camadas/{id}` | mapa | `/mapa` | `web/js/mapa/catalogo.js:145` | **coberto** | com erro |
| GET | `/api/mapa/camadas/{id}/estilo` | mapa | `/mapa` | `web/js/mapa/exportar.js:141` | **coberto** | com erro |
| GET | `/api/mapa/camadas/{id}/feicoes/{fid}` | mapa | `/mapa` | `web/js/mapa/exportar.js:44` | **coberto** | com erro |
| POST | `/api/mapa/camadas/{id}/filtrar` | mapa | — | — | **sem controle** | não se aplica |
| POST | `/api/mapa/camadas/{id}/selecionar` | mapa | — | — | **sem controle** | não se aplica |
| GET | `/api/mapa/camadas/{id}/tilejson` | mapa | — | — | **sem controle** | não se aplica |
| GET | `/api/mapa/camadas/{id}/valores` | mapa | — | — | **sem controle** | não se aplica |
| GET | `/api/mapa/fuso` | mapa-popup | `/mapa` | `web/js/mapa/mapa.js:462` | **coberto** | com erro |
| POST | `/api/mapa/pacotes/importar` | mapa | — | — | **sem controle** | não se aplica |
| POST | `/api/mapa/selecao-espacial` | mapa | — | — | **sem controle** | não se aplica |
| POST | `/api/mapa/{mapa_id}/desenho/promover` | mapa | `/mapa` | `web/js/mapa/mapa.js:367` | **coberto** | com erro |
| POST | `/api/matriz` | rede | `/mapa` | `web/js/mapa/rotas.js:233` | **coberto** | com erro |
| GET | `/api/multiescala/conjuntos` | multiescala | `/mapa` | `web/js/mapa/motor.js:129` | **coberto** | com erro |
| POST | `/api/multiescala/conjuntos` | multiescala | `/mapa` | `web/js/mapa/motor.js:173` | **coberto** | com erro |
| GET | `/api/multiescala/conjuntos/{id}` | multiescala | — | — | **sem controle** | não se aplica |
| DELETE | `/api/multiescala/conjuntos/{id}` | multiescala | `/mapa` | `web/js/mapa/motor.js:184` | **coberto** | com erro |
| POST | `/api/multiescala/conjuntos/{id}/macro` | multiescala | `/mapa` | `web/js/mapa/motor.js:319` | **coberto** | com erro |
| GET | `/api/multiescala/execucoes` | multiescala | — | — | **sem controle** | não se aplica |
| GET | `/api/multiescala/execucoes/{id}` | multiescala | — | — | **sem controle** | não se aplica |
| GET | `/api/multiescala/execucoes/{id}/celulas` | multiescala | `/mapa` | `web/js/mapa/motor.js:361` | **coberto** | com erro |
| POST | `/api/multiescala/execucoes/{id}/micro` | multiescala | `/mapa` | `web/js/mapa/motor.js:320` | **coberto** | com erro |
| GET | `/api/multiescala/fatores` | multiescala | `/mapa` | `web/js/mapa/motor.js:209` | **coberto** | com erro |
| POST | `/api/multiescala/fatores` | multiescala | `/mapa` | `web/js/mapa/motor.js:245` | **coberto** | com erro |
| GET | `/api/multiescala/fatores/{id}` | multiescala | — | — | **sem controle** | não se aplica |
| DELETE | `/api/multiescala/fatores/{id}` | multiescala | `/mapa` | `web/js/mapa/motor.js:253` | **coberto** | com erro |
| POST | `/api/multiescala/fatores/{id}/amostras` | multiescala | `/mapa` | `web/js/mapa/motor.js:280` | **coberto** | com erro |
| GET | `/api/objetos/{chave}` | compartilhamento | — | `entrega por URL assinada gerada pela API (ADR 0005); o navegador só a segue` | **externo** | não se aplica |
| GET | `/api/org` | org | `/admin`, `/admin/organizacao` | `web/js/auth/admin.js:64`<br>`web/js/auth/organizacao.js:42` | **coberto** | com erro |
| PUT | `/api/org` | org | `/admin/organizacao` | `web/js/auth/organizacao.js:81` | **coberto** | com erro |
| GET | `/api/org/ldap` | login | `/admin`, `/admin/organizacao` | `web/js/auth/admin.js:93`<br>`web/js/auth/organizacao.js:281` | **coberto** | com erro |
| PUT | `/api/org/ldap` | login | `/admin/organizacao` | `web/js/auth/organizacao.js:340` | **coberto** | com erro |
| POST | `/api/org/ldap/importar` | login | `/admin/organizacao` | `web/js/auth/organizacao.js:369` | **coberto** | com erro |
| POST | `/api/org/logo` | org | `/admin/organizacao` | `web/js/auth/organizacao.js:211` | **coberto** | com erro |
| DELETE | `/api/org/logo` | org | `/admin/organizacao` | `web/js/auth/organizacao.js:222` | **coberto** | com erro |
| GET | `/api/org/smtp` | smtp | `/admin/organizacao` | `web/js/auth/organizacao.js:235` | **coberto** | com erro |
| PUT | `/api/org/smtp` | smtp | `/admin/organizacao` | `web/js/auth/organizacao.js:263` | **coberto** | com erro |
| POST | `/api/org/smtp/testar` | smtp | `/admin/organizacao` | `web/js/auth/organizacao.js:389` | **coberto** | com erro |
| GET | `/api/papeis` | usuarios | `/admin`, `/admin/acervo`, `/admin/grupos`, `/admin/log`, `/admin/organizacao`, `/admin/papeis`, `/admin/tokens`, `/admin/usuarios`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/auth/admin.js:75`<br>`web/js/auth/comum.js:25`<br>`web/js/auth/papeis.js:70` | **coberto** | com erro |
| POST | `/api/papeis` | usuarios | `/admin/papeis` | `web/js/auth/papeis.js:118` | **coberto** | com erro |
| PUT | `/api/papeis/{id}` | usuarios | `/admin/papeis` | `web/js/auth/papeis.js:118` | **coberto** | com erro |
| DELETE | `/api/papeis/{id}` | usuarios | `/admin/papeis` | `web/js/auth/papeis.js:58` | **coberto** | com erro |
| GET | `/api/pastas` | pastas | — | — | **sem controle** | não se aplica |
| POST | `/api/pastas` | pastas | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:142` | **coberto** | com erro |
| GET | `/api/pastas/arvore` | pastas | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:141` | **coberto** | com erro |
| PUT | `/api/pastas/{id}` | pastas | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:143` | **coberto** | com erro |
| DELETE | `/api/pastas/{id}` | pastas | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:144` | **coberto** | com erro |
| GET | `/api/plataforma/inquilinos` | plataforma | — | — | **sem tela** | não se aplica |
| POST | `/api/plataforma/inquilinos` | plataforma | — | — | **sem tela** | não se aplica |
| DELETE | `/api/plataforma/inquilinos/{id}` | plataforma | — | — | **sem tela** | não se aplica |
| POST | `/api/plataforma/inquilinos/{id}/reativar` | plataforma | — | — | **sem tela** | não se aplica |
| POST | `/api/plataforma/inquilinos/{id}/suspender` | plataforma | — | — | **sem tela** | não se aplica |
| GET | `/api/privilegios` | usuarios | `/admin/papeis`, `/conta` | `web/js/auth/conta.js:426`<br>`web/js/auth/papeis.js:26` | **coberto** | com erro |
| GET | `/api/publico/itens/{id}` | compartilhamento | — | `leitura de item público por quem recebe o link, sem sessão; a ficha do item mostra o link` | **externo sem exposição** | não se aplica |
| GET | `/api/publico/itens/{id}/miniatura` | compartilhamento | — | `leitura de item público por quem recebe o link, sem sessão; a ficha do item mostra o link` | **externo sem exposição** | não se aplica |
| GET | `/api/qr.svg` | utilidades | — | — | **sem tela** | não se aplica |
| POST | `/api/reverso` | geocodificador | — | — | **sem controle** | não se aplica |
| POST | `/api/rota` | rede | `/mapa` | `web/js/mapa/rotas.js:225` | **coberto** | com erro |
| POST | `/api/senha/redefinir/aplicar` | redefinicao | `/redefinir-senha` | `web/js/auth/redefinir_senha.js:79` | **coberto** | com erro |
| GET | `/api/senha/redefinir/resolver` | redefinicao | `/redefinir-senha` | `web/js/auth/redefinir_senha.js:40` | **coberto** | com erro |
| POST | `/api/senha/redefinir/solicitar` | redefinicao | `/redefinir-senha` | `web/js/auth/redefinir_senha.js:63` | **coberto** | com erro |
| GET | `/api/sugerir` | geocodificador | `/mapa` | `web/js/mapa/busca.js:47` | **coberto** | com erro |
| GET | `/api/tipos-item` | catalogo | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:87` | **coberto** | com erro |
| GET | `/api/tokens` | tokens | `/admin`, `/admin/log`, `/admin/tokens` | `web/js/auth/admin.js:78`<br>`web/js/auth/log.js:38`<br>`web/js/auth/tokens.js:91` | **coberto** | com erro |
| POST | `/api/tokens` | tokens | `/admin/tokens`, `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/uploads` | `web/js/auth/tokens.js:162`<br>`web/js/catalogo/api.js:43`<br>`web/js/uploads/enviar.js:36` | **coberto** | com erro |
| GET | `/api/tokens/{id}` | tokens | `/admin/tokens` | `web/js/auth/tokens.js:199` | **coberto** | com erro |
| DELETE | `/api/tokens/{id}` | tokens | `/admin/tokens` | `web/js/auth/tokens.js:131` | **coberto** | com erro |
| GET | `/api/tokens/{id}/log` | tokens | `/admin/tokens` | `web/js/auth/tokens.js:193` | **coberto** | com erro |
| POST | `/api/tokens/{id}/renovar` | tokens | `/admin/tokens` | `web/js/auth/tokens.js:122` | **coberto** | com erro |
| POST | `/api/uploads` | uploads | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/uploads` | `web/js/catalogo/api.js:163`<br>`web/js/uploads/enviar.js:342` | **coberto** | com erro |
| GET | `/api/uploads/tipos` | uploads | `/uploads` | `web/js/uploads/enviar.js:243`<br>`web/js/uploads/enviar.js:74` | **coberto** | com erro |
| GET | `/api/uploads/{id}` | uploads | `/uploads` | `web/js/uploads/enviar.js:243`<br>`web/js/uploads/enviar.js:74` | **coberto** | com erro |
| DELETE | `/api/uploads/{id}` | uploads | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:166` | **coberto** | com erro |
| POST | `/api/uploads/{id}/concluir` | uploads | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:165` | **coberto** | com erro |
| PUT | `/api/uploads/{id}/partes/{n}` | uploads | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:164` | **coberto** | com erro |
| GET | `/api/usuarios` | usuarios | `/admin`, `/admin/grupos`, `/admin/log`, `/admin/usuarios`, `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/auth/admin.js:65`<br>`web/js/auth/grupos.js:302`<br>`web/js/auth/log.js:37`<br>`web/js/auth/usuarios.js:106`<br>`web/js/catalogo/api.js:160` | **coberto** | com erro |
| POST | `/api/usuarios` | usuarios | `/admin/usuarios` | `web/js/auth/usuarios.js:268` | **coberto** | com erro |
| POST | `/api/usuarios/lote` | usuarios | `/admin/usuarios` | `web/js/auth/usuarios.js:144` | **coberto** | com erro |
| GET | `/api/usuarios/{id}` | usuarios | `/admin/usuarios` | `web/js/auth/usuarios.js:214` | **coberto** | com erro |
| PUT | `/api/usuarios/{id}` | usuarios | `/admin/usuarios` | `web/js/auth/usuarios.js:179`<br>`web/js/auth/usuarios.js:268` | **coberto** | com erro |
| DELETE | `/api/usuarios/{id}` | usuarios | `/admin/usuarios` | `web/js/auth/usuarios.js:185` | **coberto** | com erro |
| POST | `/api/usuarios/{id}/2fa/desativar` | usuarios | `/admin/usuarios` | `web/js/auth/usuarios.js:169` | **coberto** | com erro |
| POST | `/api/usuarios/{id}/desbloquear` | usuarios | `/admin/usuarios` | `web/js/auth/usuarios.js:174` | **coberto** | com erro |
| POST | `/api/usuarios/{id}/senha` | usuarios | `/admin/usuarios` | `web/js/auth/usuarios.js:161` | **coberto** | com erro |
| GET | `/api/versao` | versao | `/` | `web/app.js:12` | **coberto** | com erro |
| GET | `/ogc/records` | ogc-records | — | `OGC API Records para catálogos externos (token catalogo:ler); a ficha do item ou a tela de tokens deve mostrar a URL` | **externo sem exposição** | não se aplica |
| GET | `/ogc/records/collections` | ogc-records | — | `OGC API Records para catálogos externos (token catalogo:ler); a ficha do item ou a tela de tokens deve mostrar a URL` | **externo sem exposição** | não se aplica |
| GET | `/ogc/records/collections/{colecao_id}` | ogc-records | — | `OGC API Records para catálogos externos (token catalogo:ler); a ficha do item ou a tela de tokens deve mostrar a URL` | **externo sem exposição** | não se aplica |
| GET | `/ogc/records/collections/{colecao_id}/items` | ogc-records | — | `OGC API Records para catálogos externos (token catalogo:ler); a ficha do item ou a tela de tokens deve mostrar a URL` | **externo sem exposição** | não se aplica |
| GET | `/ogc/records/collections/{colecao_id}/items/{item_id}` | ogc-records | — | `OGC API Records para catálogos externos (token catalogo:ler); a ficha do item ou a tela de tokens deve mostrar a URL` | **externo sem exposição** | não se aplica |
| GET | `/ogc/records/conformance` | ogc-records | — | `OGC API Records para catálogos externos (token catalogo:ler); a ficha do item ou a tela de tokens deve mostrar a URL` | **externo sem exposição** | não se aplica |
| GET | `/rest/services/Geocodificador/GeocodeServer` | geocodificador-esri | — | `GeocodeServer compatível com Esri, consumido por Pro/AGOL; a tela de tokens deve mostrar a URL` | **externo sem exposição** | não se aplica |
| POST | `/rest/services/Geocodificador/GeocodeServer` | geocodificador-esri | — | `GeocodeServer compatível com Esri, consumido por Pro/AGOL; a tela de tokens deve mostrar a URL` | **externo sem exposição** | não se aplica |
| GET | `/rest/services/Geocodificador/GeocodeServer/findAddressCandidates` | geocodificador-esri | — | `GeocodeServer compatível com Esri, consumido por Pro/AGOL; a tela de tokens deve mostrar a URL` | **externo sem exposição** | não se aplica |
| POST | `/rest/services/Geocodificador/GeocodeServer/findAddressCandidates` | geocodificador-esri | — | `GeocodeServer compatível com Esri, consumido por Pro/AGOL; a tela de tokens deve mostrar a URL` | **externo sem exposição** | não se aplica |
| POST | `/rest/services/Geocodificador/GeocodeServer/geocodeAddresses` | geocodificador-esri | — | `GeocodeServer compatível com Esri, consumido por Pro/AGOL; a tela de tokens deve mostrar a URL` | **externo sem exposição** | não se aplica |
| GET | `/rest/services/Geocodificador/GeocodeServer/reverseGeocode` | geocodificador-esri | — | `GeocodeServer compatível com Esri, consumido por Pro/AGOL; a tela de tokens deve mostrar a URL` | **externo sem exposição** | não se aplica |
| POST | `/rest/services/Geocodificador/GeocodeServer/reverseGeocode` | geocodificador-esri | — | `GeocodeServer compatível com Esri, consumido por Pro/AGOL; a tela de tokens deve mostrar a URL` | **externo sem exposição** | não se aplica |
| GET | `/rest/services/Geocodificador/GeocodeServer/suggest` | geocodificador-esri | — | `GeocodeServer compatível com Esri, consumido por Pro/AGOL; a tela de tokens deve mostrar a URL` | **externo sem exposição** | não se aplica |
| GET | `/saude` | saude | `/` | `web/app.js:19` | **coberto** | com erro |

## Telas → estados explícitos (heurística por texto dos módulos próprios da tela, fora web/js/base)

| página | arquivo | existe | vazio | carregando | erro | negado |
|---|---|---|---|---|---|---|
| `/` | index.html | sim | **não** | **não** | sim | sim |
| `/entrar` | login.html | sim | **não** | sim | sim | sim |
| `/conta` | conta.html | sim | sim | sim | sim | sim |
| `/admin` | admin/index.html | sim | sim | sim | sim | sim |
| `/admin/acervo` | admin/acervo.html | sim | sim | sim | sim | sim |
| `/admin/usuarios` | admin/usuarios.html | sim | sim | sim | sim | sim |
| `/admin/grupos` | admin/grupos.html | sim | sim | sim | sim | sim |
| `/admin/papeis` | admin/papeis.html | sim | sim | sim | sim | sim |
| `/admin/tokens` | admin/tokens.html | sim | sim | sim | sim | sim |
| `/admin/log` | admin/log.html | sim | sim | sim | sim | sim |
| `/admin/organizacao` | admin/organizacao.html | sim | sim | sim | sim | sim |
| `/conteudo` | conteudo.html | sim | sim | sim | sim | sim |
| `/conteudo/lixeira` | conteudo_lixeira.html | sim | sim | sim | sim | sim |
| `/conteudo/{id}` | conteudo_item.html | sim | sim | sim | sim | sim |
| `/c/{token}` | compartilhado.html | sim | sim | sim | sim | sim |
| `/mapa` | mapa.html | sim | sim | sim | sim | sim |
| `/aplicativo` | aplicativo.html | sim | sim | sim | sim | sim |
| `/conexoes` | conexoes.html | sim | sim | sim | sim | sim |
| `/aceitar-convite` | aceitar_convite.html | sim | sim | sim | sim | **não** |
| `/redefinir-senha` | redefinir_senha.html | sim | **não** | sim | sim | **não** |
| `/uploads` | uploads.html | sim | sim | sim | sim | sim |
| `/estilo-guia` | estilo_guia.html | sim | sim | sim | sim | sim |
| `/construtor` | construtor.html | sim | sim | sim | sim | sim |
| `/executar` | executar.html | sim | sim | sim | sim | sim |
| `/tarefas` | tarefas.html | sim | sim | sim | sim | sim |
| `/tarefas/{job_id}` | tarefas.html | sim | sim | sim | sim | sim |

## Lacunas de escrita (cada grupo vira um item UX-<n> no backlog via `--registrar`)

- **arquivos**: POST `/api/arquivos` (sem controle); DELETE `/api/arquivos/{sha256}` (sem controle)
- **categorias**: PUT `/api/categorias` (sem controle); POST `/api/categorias/importar` (sem controle)
- **geocodificador**: POST `/api/geocodificar` (sem controle); POST `/api/reverso` (sem controle)
- **geocodificador-esri**: POST `/rest/services/Geocodificador/GeocodeServer` (externo sem exposição); POST `/rest/services/Geocodificador/GeocodeServer/findAddressCandidates` (externo sem exposição); POST `/rest/services/Geocodificador/GeocodeServer/geocodeAddresses` (externo sem exposição); POST `/rest/services/Geocodificador/GeocodeServer/reverseGeocode` (externo sem exposição)
- **ingestao**: POST `/api/importacoes` (sem tela); DELETE `/api/importacoes/{id}` (sem tela); PUT `/api/importacoes/{id}/confirmar` (sem tela)
- **login**: POST `/api/login/ldap` (sem controle)
- **mapa**: PATCH `/api/anotacoes/{id}` (sem controle); DELETE `/api/anotacoes/{id}` (sem controle); POST `/api/mapa/camadas/{id}/filtrar` (sem controle); POST `/api/mapa/camadas/{id}/selecionar` (sem controle); POST `/api/mapa/pacotes/importar` (sem controle); POST `/api/mapa/selecao-espacial` (sem controle)
- **plataforma**: POST `/api/plataforma/inquilinos` (sem tela); DELETE `/api/plataforma/inquilinos/{id}` (sem tela); POST `/api/plataforma/inquilinos/{id}/reativar` (sem tela); POST `/api/plataforma/inquilinos/{id}/suspender` (sem tela)

## URLs chamadas pela tela sem rota correspondente na API

- `web/js/catalogo/api.js:83 GET /api/openapi.json`
- `web/js/mapa/tabela.js:89 GET /api/camadas/{x}/tabela`

## Backlog: hipóteses com efeito visível × páginas e rotas cobertas

| item | estado do item | referência no texto | veredito |
|---|---|---|---|
| L0-02-a-login-sessao | entregue | `/api/eu` | rota coberta |
| L0-02-a-login-sessao | entregue | `/api/login` | rota coberta |
| L0-02-a-login-sessao | entregue | `/api/logout` | rota coberta |
| L0-02-a-login-sessao | entregue | `/entrar` | página existe |
| L0-03-a-modelo-item | entregue | `/api/itens` | rota coberta |
| L0-03-a-modelo-item | entregue | `/api/itens/{id}` | rota coberta |
| L0-03-i-dependencias | entregue | `/api/itens/{camada}/usado_por` | rota sem tela |
| L0-06-e-status | parcial | `/api/status` | rota sem tela |
| L0-07-f-console-plataforma | parcial | `/api/plataforma` | rota sem tela |
| L0-07-f-console-plataforma | parcial | `/p` | página inexistente |
| L0-08-a-oidc | parcial | `/api/sso` | rota sem tela |
| L0-08-b-saml | parcial | `/api/sso/saml/metadata` | rota sem tela |
| L0-09-c-xml-iso-validacao | parcial | `/api/itens/{id}/metadado` | rota sem tela |
| L2-01-a-documento-mapa | entregue | `/api/mapas` | rota sem tela |
| L2-01-a-documento-mapa | entregue | `/api/mapas/{id}/completo` | rota sem tela |
| L2-01-a-documento-mapa | entregue | `/c` | página existe |
| L2-04-d-featureserver-edicao-anexos | parcial | `/uploads/upload` | página existe |
| L2-04-g-ogc-api-features-crs-cql2 | parcial | `/api` | página inexistente |
| L2-10-b-relacionamentos | entregue | `/api/camadas/{id}/relacionados/{rel}` | rota sem tela |
| L2-11-b-geocodificador-brasil | parcial | `/api/geocodificar` | rota coberta |
| L2-11-c-rota-matriz-isocrona | parcial | `/api/rota` | rota coberta |
| L2-17-crs-transformacoes | parcial | `/api/crs/{codigo}` | rota sem tela |
| L4-02-a-conectado-e-subrede | parcial | `/api/v1/rede/{id}/tracar` | rota sem tela |
| L4-02-e-configuracoes-de-tracado | parcial | `/api/v1/rede/{id}/config_tracado` | rota sem tela |
| L4-04-a-controladores-e-tiers | parcial | `/c` | página existe |
| L5-05-documento-versoes | entregue | `/api/esquemas` | rota sem tela |
| L5-05-documento-versoes | entregue | `/api/itens/{id}/versoes` | rota coberta |
| L5-14-publicacao-links-embed | parcial | `/p` | página inexistente |
| L2-01-a-basemap-local-pmtiles | entregue | `/mapa` | página existe |
| UX-01-sistema-de-design | parcial | `/estilo-guia` | página existe |
| UX-02-telas-entrada-conta-convite | parcial | `/aceitar-convite` | página existe |
| UX-02-telas-entrada-conta-convite | parcial | `/conta` | página existe |
| UX-02-telas-entrada-conta-convite | parcial | `/entrar` | página existe |
| UX-02-telas-entrada-conta-convite | parcial | `/redefinir-senha` | página existe |
| UX-03-tela-conteudo-item-lixeira | parcial | `/conteudo` | página existe |
| UX-03-tela-conteudo-item-lixeira | parcial | `/conteudo/item` | página existe |
| UX-03-tela-conteudo-item-lixeira | parcial | `/conteudo/lixeira` | página existe |
| UX-04-tela-mapa-polimento | parcial | `/mapa` | página existe |
| UX-05-telas-conexoes-uploads-tarefas-compartilhado | parcial | `/c` | página existe |
| UX-05-telas-conexoes-uploads-tarefas-compartilhado | parcial | `/conexoes` | página existe |
| UX-05-telas-conexoes-uploads-tarefas-compartilhado | parcial | `/tarefas` | página existe |
| UX-05-telas-conexoes-uploads-tarefas-compartilhado | parcial | `/uploads` | página existe |
| UX-06-tela-administracao-inquilino | parcial | `/api/convites` | rota coberta |
| UX-06-tela-administracao-inquilino | parcial | `/api/cotas` | rota sem tela |
| UX-06-tela-administracao-inquilino | parcial | `/api/grupos` | rota coberta |
| UX-06-tela-administracao-inquilino | parcial | `/api/org` | rota coberta |
| UX-06-tela-administracao-inquilino | parcial | `/api/sso` | rota sem tela |
| UX-10-acervo-sem-tela | parcial | `/api/acervo/{fonte_id}/adicionar` | rota coberta |
| UX-12-categorias-sem-controle | parcial | `/api/categorias` | rota coberta |
| UX-12-categorias-sem-controle | parcial | `/api/categorias/importar` | rota sem tela |
| UX-13-conexoes-sem-controle | parcial | `/api/conexoes` | rota coberta |
| UX-13-conexoes-sem-controle | parcial | `/api/conexoes/{id}` | rota coberta |
| UX-14-geocodificador-sem-tela | parcial | `/api/geocodificar` | rota coberta |
| UX-14-geocodificador-sem-tela | parcial | `/api/reverso` | rota sem tela |

Itens com efeito visível que não citam página nem rota no texto (107; a cobertura deles é conferida pelo e2e do item, não por este cruzamento): L0-02-b-politica-senha-bloqueio, L0-02-c-2fa-totp, L0-02-d-token-servico, L0-02-f-tela-usuarios, L0-02-tenant-auth, L0-03-b-pastas-tags-categorias-classificacao, L0-03-catalogo, L0-03-d-grupos, L0-03-g-detalhe-item-miniatura, L0-04-d-formatos-base, L0-04-e-formatos-cad, L0-04-h-exportar, L0-04-i-fonte-registrada, L0-04-ingest-vetor, L0-05-d-periodicos, L0-05-e-justica-entre-inquilinos, L0-05-jobs, L0-06-c-restore-drill, L0-06-d-exportar-inquilino, L0-07-a-configuracoes-org, L0-07-b-papeis-privilegios, L0-07-c-cotas-uso, L0-07-d-smtp-convites, L0-07-e-relatorios, L0-08-c-govbr, L0-08-d-ldap, L0-08-e-mapeamento-provisionamento, L0-09-a-procedencia, L0-09-b-editor-iso-mgb, L0-10-eventos-historico, L0-11-arquivos-objetos, L0-12-contrato-api-e-limites, L0-13-dado-demonstracao, L0-14-cli-admin, L1-01-ingest-raster, L2-01-b-martin-tiles-vetoriais, L2-01-c-lista-camadas-legenda, L2-01-e-mapas-base, L2-01-f-navegacao-medicao-coordenadas, L2-01-g-tabela-atributos, L2-01-h-selecao-filtros, L2-01-i-graficos-de-camada, L2-01-mapa-web, L2-02-a-modelo-estilo, L2-02-c-editor-simbologia-vetor, L2-02-d-rotulos, L2-03-b-ferramentas-geometria, L2-03-c-formulario-atributos-runtime, L2-03-f-edicao-em-lote-calculo-campo, L2-04-b-featureserver-catalogo-metadados, L2-04-c-featureserver-query, L2-04-h-wfs-2-gml, L2-04-j-conformidade-clientes-e-paridade, L2-04-servicos-esri-ogc, L2-05-a-catalogo-ferramentas-gpserver, L2-05-b-vetor-basico, L2-05-c-sobreposicao-agregacao, L2-05-d-grades-densidade-padroes-interpolacao, L2-05-f-rede-isocrona-rota-ferramentas, L2-06-a-modelo-painel-fontes, L2-07-b-formulario-de-coleta-xlsform, L2-08-a-leitor-portal-inventario, L2-08-b-clonar-camadas-hospedadas, L2-09-a-terreno-terrain-rgb-relevo, L2-10-c-linguagem-expressao, L2-11-a-geocodificacao-csv, L2-12-a-motor-render-servidor, L3-01-b-unidades, L3-01-e-combinacao, L3-01-f-explicacao, L3-06-criterios-de-feicao, L3-14-cobertura-dado-ausente, L3-16-desempenho-escala, L4-02-b-montante-jusante, L4-02-c-isolamento, L4-02-d-lacos-e-caminho-curto, L4-02-f-resultados-e-exportacao, L4-04-b-atualizar-e-exportar-subrede, L4-04-c-sumarios-por-subrede, L5-01-a-layout-paginas, L5-01-d-widgets-pagina-menu, L5-04-a-blocos-de-conteudo, L5-06-motor-widgets, L5-08-editor-arrasto, L5-09-desfazer-refazer-rascunho, L5-12-acessibilidade-i18n-construtores, L5-15-vista-movel-responsivo, L5-31-construtor-de-camada-esquema, L6-01-b-view-so-leitura, L6-01-d-ficha-fonte, L6-01-g-licenca-curada, L6-02-c-wfs-ogcapi, L6-02-j-bancos-externos, L6-02-k-agendamento, L6-02-l-saude, L6-02-m-catalogo-endpoints-brasil, L6-05-proveniencia-camada-externa, L7-03-e-cabecalhos-csp-tls, L7-06-b-alertas, L7-06-c-logs-consulta-req-id, L7-06-d-paineis, L7-08-c-sdk-js, L7-11-b-appliance-sem-internet, L7-11-c-telemetria-opcional, L7-20-trilha-auditoria, UX-00-mapa-de-cobertura-da-interface, UX-07-telas-do-construtor-e-aplicativo
