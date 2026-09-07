# Cobertura da interface (gerado — não editar à mão)

Gerado por `docs/gerar_cobertura_ui.py` (item UX-00-mapa-de-cobertura-da-interface). Rotas lidas da aplicação; chamadas lidas de `web/`; telas de `app/paginas.py`. Heurísticas de texto declaradas no cabeçalho do gerador: o que elas não veem, o e2e vê. Regra da trilha: nenhuma rota fica só no backend.

## Placar

| medida | valor |
|---|---|
| rotas (método × caminho) | 196 |
| coberto | 137 |
| sem controle | 22 |
| sem tela | 20 |
| externo | 0 |
| externo sem exposição | 17 |
| cobertas sem estado de erro perto da chamada | 12 |
| lacunas de ESCRITA (linha de base do teste) | 28 |
| URLs chamadas pela tela que não existem na API | 1 |

## Rotas → tela/controle → estado

| método | rota | grupo | tela | controle (arquivo:linha) | estado | erro |
|---|---|---|---|---|---|---|
| GET | `/api/acervo` | acervo | — | — | **sem tela** | não se aplica |
| GET | `/api/acervo/{fonte_id}` | acervo | — | — | **sem tela** | não se aplica |
| POST | `/api/acervo/{fonte_id}/adicionar` | acervo | — | — | **sem tela** | não se aplica |
| GET | `/api/agendas` | agendas | `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:50` | **coberto** | sem estado de erro |
| POST | `/api/agendas` | agendas | `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:52` | **coberto** | sem estado de erro |
| GET | `/api/agendas/{agenda_id}` | agendas | `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:51` | **coberto** | sem estado de erro |
| PUT | `/api/agendas/{agenda_id}` | agendas | `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:53` | **coberto** | sem estado de erro |
| DELETE | `/api/agendas/{agenda_id}` | agendas | `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:54` | **coberto** | sem estado de erro |
| POST | `/api/agendas/{agenda_id}/pausar` | agendas | `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:55` | **coberto** | sem estado de erro |
| POST | `/api/agendas/{agenda_id}/retomar` | agendas | `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:56` | **coberto** | sem estado de erro |
| POST | `/api/agendas/{agenda_id}/rodar-agora` | agendas | `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:57` | **coberto** | sem estado de erro |
| GET | `/api/arquivos` | arquivos | — | — | **sem controle** | não se aplica |
| POST | `/api/arquivos` | arquivos | — | — | **sem controle** | não se aplica |
| GET | `/api/arquivos/_varredura` | arquivos | `/admin/organizacao` | `web/js/auth/organizacao.js:165` | **coberto** | sem estado de erro |
| GET | `/api/arquivos/{sha256}` | arquivos | `/admin/organizacao` | `web/js/auth/organizacao.js:165` | **coberto** | sem estado de erro |
| DELETE | `/api/arquivos/{sha256}` | arquivos | — | — | **sem controle** | não se aplica |
| GET | `/api/categorias` | categorias | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:125` | **coberto** | com erro |
| PUT | `/api/categorias` | categorias | — | — | **sem controle** | não se aplica |
| POST | `/api/categorias/importar` | categorias | — | — | **sem controle** | não se aplica |
| GET | `/api/compartilhado/{token}` | compartilhamento | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:115` | **coberto** | com erro |
| GET | `/api/compartilhado/{token}/itens/{id}` | compartilhamento | — | — | **sem controle** | não se aplica |
| GET | `/api/compartilhado/{token}/itens/{id}/miniatura` | compartilhamento | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:116` | **coberto** | com erro |
| GET | `/api/conexoes` | conexoes | `/conexoes` | `web/js/conexoes/conexoes.js:141` | **coberto** | com erro |
| POST | `/api/conexoes` | conexoes | — | — | **sem controle** | não se aplica |
| GET | `/api/conexoes/{id}` | conexoes | — | — | **sem controle** | não se aplica |
| PATCH | `/api/conexoes/{id}` | conexoes | — | — | **sem controle** | não se aplica |
| DELETE | `/api/conexoes/{id}` | conexoes | — | — | **sem controle** | não se aplica |
| POST | `/api/conexoes/{id}/publicar` | conexoes | `/conexoes` | `web/js/conexoes/conexoes.js:95` | **coberto** | com erro |
| GET | `/api/conexoes/{id}/saude-historico` | conexoes | `/conexoes` | `web/js/conexoes/conexoes.js:70` | **coberto** | com erro |
| POST | `/api/conexoes/{id}/testar` | conexoes | `/conexoes` | `web/js/conexoes/conexoes.js:50` | **coberto** | com erro |
| GET | `/api/convites` | convites | `/admin/usuarios` | `web/js/auth/convites.js:38` | **coberto** | com erro |
| POST | `/api/convites` | convites | `/admin/usuarios` | `web/js/auth/convites.js:53` | **coberto** | com erro |
| POST | `/api/convites/aceitar` | convites | `/aceitar-convite` | `web/js/auth/aceitar_convite.js:58` | **coberto** | com erro |
| GET | `/api/convites/resolver` | convites | `/aceitar-convite` | `web/js/auth/aceitar_convite.js:31` | **coberto** | com erro |
| DELETE | `/api/convites/{id}` | convites | `/admin/usuarios` | `web/js/auth/convites.js:25` | **coberto** | com erro |
| GET | `/api/esquemas` | catalogo | — | — | **sem controle** | não se aplica |
| GET | `/api/esquemas/{tipo}` | catalogo | — | — | **sem controle** | não se aplica |
| GET | `/api/eu` | eu | `/`, `/admin/grupos`, `/admin/log`, `/admin/organizacao`, `/admin/papeis`, `/admin/tokens`, `/admin/usuarios`, `/c/{token}`, `/conexoes`, `/conta`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/entrar`, `/mapa`, `/tarefas`, `/tarefas/{job_id}`, `/uploads` | `web/app.js:36`<br>`web/js/auth/conta.js:90`<br>`web/js/auth/sessao.js:59`<br>`web/js/conexoes/conexoes.js:169`<br>`web/js/jobs/tarefas.js:52` | **coberto** | com erro |
| PUT | `/api/eu` | eu | `/conta` | `web/js/auth/conta.js:141` | **coberto** | com erro |
| POST | `/api/eu/2fa/codigos` | eu | `/conta` | `web/js/auth/conta.js:338` | **coberto** | com erro |
| POST | `/api/eu/2fa/confirmar` | eu | `/conta` | `web/js/auth/conta.js:294` | **coberto** | com erro |
| POST | `/api/eu/2fa/desativar` | eu | `/conta` | `web/js/auth/conta.js:324` | **coberto** | com erro |
| POST | `/api/eu/2fa/iniciar` | eu | `/conta` | `web/js/auth/conta.js:281` | **coberto** | com erro |
| GET | `/api/eu/convites` | eu | `/conta` | `web/js/auth/conta.js:387` | **coberto** | com erro |
| POST | `/api/eu/foto` | eu | `/conta` | `web/js/auth/conta.js:181` | **coberto** | com erro |
| DELETE | `/api/eu/foto` | eu | `/conta` | `web/js/auth/conta.js:192` | **coberto** | com erro |
| PUT | `/api/eu/senha` | eu | `/conta` | `web/js/auth/conta.js:220` | **coberto** | com erro |
| GET | `/api/eu/sessoes` | eu | `/conta` | `web/js/auth/conta.js:361` | **coberto** | com erro |
| DELETE | `/api/eu/sessoes` | eu | `/conta` | `web/js/auth/conta.js:367` | **coberto** | com erro |
| DELETE | `/api/eu/sessoes/{id}` | eu | `/conta` | `web/js/auth/conta.js:358` | **coberto** | com erro |
| GET | `/api/eventos` | log | `/admin/log` | `web/js/auth/log.js:154` | **coberto** | com erro |
| GET | `/api/favoritos` | favoritos | — | — | **sem controle** | não se aplica |
| PUT | `/api/favoritos/{item_id}` | favoritos | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:128` | **coberto** | com erro |
| DELETE | `/api/favoritos/{item_id}` | favoritos | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:129` | **coberto** | com erro |
| POST | `/api/geocodificar` | geocodificador | — | — | **sem tela** | não se aplica |
| GET | `/api/grupos` | grupos | `/admin/grupos`, `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/auth/grupos.js:101`<br>`web/js/catalogo/api.js:137` | **coberto** | com erro |
| POST | `/api/grupos` | grupos | `/admin/grupos` | `web/js/auth/grupos.js:143` | **coberto** | com erro |
| GET | `/api/grupos/{id}` | grupos | `/admin/grupos` | `web/js/auth/grupos.js:155` | **coberto** | com erro |
| PUT | `/api/grupos/{id}` | grupos | `/admin/grupos` | `web/js/auth/grupos.js:191`<br>`web/js/auth/grupos.js:242` | **coberto** | com erro |
| DELETE | `/api/grupos/{id}` | grupos | `/admin/grupos` | `web/js/auth/grupos.js:223` | **coberto** | com erro |
| POST | `/api/grupos/{id}/aceitar` | grupos | `/admin/grupos`, `/conta` | `web/js/auth/conta.js:384`<br>`web/js/auth/grupos.js:88` | **coberto** | com erro |
| POST | `/api/grupos/{id}/entrar` | grupos | `/admin/grupos`, `/conta` | `web/js/auth/conta.js:384`<br>`web/js/auth/grupos.js:88` | **coberto** | com erro |
| GET | `/api/grupos/{id}/membros` | grupos | `/admin/grupos` | `web/js/auth/grupos.js:233`<br>`web/js/auth/grupos.js:279` | **coberto** | com erro |
| POST | `/api/grupos/{id}/membros` | grupos | `/admin/grupos`, `/conta` | `web/js/auth/conta.js:384`<br>`web/js/auth/grupos.js:300`<br>`web/js/auth/grupos.js:88` | **coberto** | com erro |
| PUT | `/api/grupos/{id}/membros/{uid}` | grupos | `/admin/grupos` | `web/js/auth/grupos.js:275` | **coberto** | com erro |
| DELETE | `/api/grupos/{id}/membros/{uid}` | grupos | `/admin/grupos` | `web/js/auth/grupos.js:211`<br>`web/js/auth/grupos.js:274` | **coberto** | com erro |
| POST | `/api/grupos/{id}/membros/{uid}/aprovar` | grupos | `/admin/grupos` | `web/js/auth/grupos.js:273` | **coberto** | com erro |
| POST | `/api/grupos/{id}/recusar` | grupos | `/admin/grupos`, `/conta` | `web/js/auth/conta.js:384`<br>`web/js/auth/grupos.js:88` | **coberto** | com erro |
| GET | `/api/importacoes` | ingestao | — | — | **sem tela** | não se aplica |
| POST | `/api/importacoes` | ingestao | — | — | **sem tela** | não se aplica |
| GET | `/api/importacoes/formatos` | ingestao | — | — | **sem tela** | não se aplica |
| GET | `/api/importacoes/{id}` | ingestao | — | — | **sem tela** | não se aplica |
| DELETE | `/api/importacoes/{id}` | ingestao | — | — | **sem tela** | não se aplica |
| PUT | `/api/importacoes/{id}/confirmar` | ingestao | — | — | **sem tela** | não se aplica |
| POST | `/api/isocrona` | rede | — | — | **sem tela** | não se aplica |
| GET | `/api/itens` | catalogo | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:75` | **coberto** | com erro |
| POST | `/api/itens` | catalogo | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:79` | **coberto** | com erro |
| GET | `/api/itens/facetas` | catalogo | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:64`<br>`web/js/catalogo/api.js:76`<br>`web/js/catalogo/api.js:78` | **coberto** | com erro |
| POST | `/api/itens/lote` | catalogo | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:83` | **coberto** | com erro |
| GET | `/api/itens/tags` | catalogo | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:64`<br>`web/js/catalogo/api.js:77`<br>`web/js/catalogo/api.js:78` | **coberto** | com erro |
| POST | `/api/itens/transferir` | catalogo | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:85` | **coberto** | com erro |
| GET | `/api/itens/{id}` | catalogo | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:64`<br>`web/js/catalogo/api.js:76`<br>`web/js/catalogo/api.js:77`<br>`web/js/catalogo/api.js:78` | **coberto** | com erro |
| PUT | `/api/itens/{id}` | catalogo | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:80` | **coberto** | com erro |
| PATCH | `/api/itens/{id}` | catalogo | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:81` | **coberto** | com erro |
| DELETE | `/api/itens/{id}` | catalogo | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:82` | **coberto** | com erro |
| GET | `/api/itens/{id}/compartilhamento` | compartilhamento | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:110` | **coberto** | com erro |
| PUT | `/api/itens/{id}/compartilhamento` | compartilhamento | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:111` | **coberto** | com erro |
| GET | `/api/itens/{id}/criado-a-partir-de` | catalogo | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:105` | **coberto** | com erro |
| GET | `/api/itens/{id}/integridade` | catalogo | — | — | **sem controle** | não se aplica |
| GET | `/api/itens/{id}/links` | compartilhamento | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:112` | **coberto** | com erro |
| POST | `/api/itens/{id}/links` | compartilhamento | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:113` | **coberto** | com erro |
| DELETE | `/api/itens/{id}/links/{lid}` | compartilhamento | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:114` | **coberto** | com erro |
| GET | `/api/itens/{id}/metadado.xml` | catalogo | — | — | **sem controle** | não se aplica |
| GET | `/api/itens/{id}/miniatura` | catalogo | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:88` | **coberto** | com erro |
| POST | `/api/itens/{id}/miniatura` | catalogo | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:92` | **coberto** | com erro |
| DELETE | `/api/itens/{id}/miniatura` | catalogo | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:95` | **coberto** | com erro |
| POST | `/api/itens/{id}/miniatura/gerar` | catalogo | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:94` | **coberto** | com erro |
| POST | `/api/itens/{id}/mover` | catalogo | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:84` | **coberto** | com erro |
| GET | `/api/itens/{id}/ordem-de-exclusao` | catalogo | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:106` | **coberto** | com erro |
| PUT | `/api/itens/{id}/relacoes` | catalogo | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:107` | **coberto** | com erro |
| GET | `/api/itens/{id}/usado-por` | catalogo | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:104` | **coberto** | com erro |
| GET | `/api/itens/{id}/versoes` | catalogo | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:98` | **coberto** | com erro |
| GET | `/api/itens/{id}/versoes/{n}` | catalogo | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:99` | **coberto** | com erro |
| POST | `/api/itens/{id}/versoes/{n}/publicar` | catalogo | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:101` | **coberto** | com erro |
| POST | `/api/itens/{id}/versoes/{n}/restaurar` | catalogo | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:100` | **coberto** | com erro |
| GET | `/api/jobs` | jobs | `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:38` | **coberto** | com erro |
| POST | `/api/jobs` | jobs | `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:40` | **coberto** | com erro |
| GET | `/api/jobs/resumo` | jobs | `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:39`<br>`web/js/jobs/api.js:45` | **coberto** | com erro |
| GET | `/api/jobs/tipos` | jobs | `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:39`<br>`web/js/jobs/api.js:46` | **coberto** | com erro |
| GET | `/api/jobs/{job_id}` | jobs | `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:39`<br>`web/js/jobs/api.js:45`<br>`web/js/jobs/api.js:46` | **coberto** | com erro |
| POST | `/api/jobs/{job_id}/cancelar` | jobs | `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:41` | **coberto** | com erro |
| GET | `/api/jobs/{job_id}/eventos` | jobs | `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/eventos.js:41` | **coberto** | sem estado de erro |
| GET | `/api/jobs/{job_id}/log` | jobs | `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:44` | **coberto** | sem estado de erro |
| POST | `/api/jobs/{job_id}/repetir` | jobs | `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:42` | **coberto** | com erro |
| GET | `/api/lixeira` | lixeira | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:132` | **coberto** | com erro |
| POST | `/api/lixeira/esvaziar` | lixeira | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:134` | **coberto** | com erro |
| POST | `/api/lixeira/{id}/restaurar` | lixeira | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:133` | **coberto** | com erro |
| GET | `/api/log` | log | `/admin/log` | `web/js/auth/log.js:113`<br>`web/js/auth/log.js:115` | **coberto** | com erro |
| POST | `/api/login` | login | `/entrar` | `web/js/auth/login.js:141` | **coberto** | com erro |
| POST | `/api/login/2fa` | login | `/entrar` | `web/js/auth/login.js:164` | **coberto** | com erro |
| POST | `/api/login/ldap` | login | — | — | **sem controle** | não se aplica |
| GET | `/api/login/provedores` | login | `/entrar` | `web/js/auth/login.js:59` | **coberto** | com erro |
| POST | `/api/logout` | login | `/`, `/admin/grupos`, `/admin/log`, `/admin/organizacao`, `/admin/papeis`, `/admin/tokens`, `/admin/usuarios`, `/c/{token}`, `/conexoes`, `/conta`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/entrar`, `/mapa`, `/tarefas`, `/tarefas/{job_id}`, `/uploads` | `web/js/auth/sessao.js:73` | **coberto** | com erro |
| POST | `/api/matriz` | rede | — | — | **sem tela** | não se aplica |
| GET | `/api/objetos/{chave}` | compartilhamento | — | `entrega por URL assinada gerada pela API (ADR 0005); o navegador só a segue` | **externo sem exposição** | não se aplica |
| GET | `/api/org` | org | `/admin/organizacao` | `web/js/auth/organizacao.js:30` | **coberto** | com erro |
| PUT | `/api/org` | org | `/admin/organizacao` | `web/js/auth/organizacao.js:62` | **coberto** | com erro |
| GET | `/api/org/ldap` | login | — | — | **sem controle** | não se aplica |
| PUT | `/api/org/ldap` | login | — | — | **sem controle** | não se aplica |
| POST | `/api/org/ldap/importar` | login | — | — | **sem controle** | não se aplica |
| POST | `/api/org/logo` | org | `/admin/organizacao` | `web/js/auth/organizacao.js:190` | **coberto** | com erro |
| DELETE | `/api/org/logo` | org | `/admin/organizacao` | `web/js/auth/organizacao.js:200` | **coberto** | com erro |
| GET | `/api/org/smtp` | smtp | `/admin/organizacao` | `web/js/auth/organizacao.js:213` | **coberto** | com erro |
| PUT | `/api/org/smtp` | smtp | `/admin/organizacao` | `web/js/auth/organizacao.js:241` | **coberto** | com erro |
| POST | `/api/org/smtp/testar` | smtp | `/admin/organizacao` | `web/js/auth/organizacao.js:255` | **coberto** | com erro |
| GET | `/api/papeis` | usuarios | `/admin/grupos`, `/admin/log`, `/admin/papeis`, `/admin/usuarios`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/auth/comum.js:23`<br>`web/js/auth/papeis.js:68` | **coberto** | com erro |
| POST | `/api/papeis` | usuarios | `/admin/papeis` | `web/js/auth/papeis.js:111` | **coberto** | com erro |
| PUT | `/api/papeis/{id}` | usuarios | — | — | **sem controle** | não se aplica |
| DELETE | `/api/papeis/{id}` | usuarios | `/admin/papeis` | `web/js/auth/papeis.js:58` | **coberto** | com erro |
| GET | `/api/pastas` | pastas | — | — | **sem controle** | não se aplica |
| POST | `/api/pastas` | pastas | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:120` | **coberto** | com erro |
| GET | `/api/pastas/arvore` | pastas | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:119` | **coberto** | com erro |
| PUT | `/api/pastas/{id}` | pastas | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:121` | **coberto** | com erro |
| DELETE | `/api/pastas/{id}` | pastas | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:122` | **coberto** | com erro |
| GET | `/api/plataforma/inquilinos` | plataforma | — | — | **sem tela** | não se aplica |
| POST | `/api/plataforma/inquilinos` | plataforma | — | — | **sem tela** | não se aplica |
| DELETE | `/api/plataforma/inquilinos/{id}` | plataforma | — | — | **sem tela** | não se aplica |
| POST | `/api/plataforma/inquilinos/{id}/reativar` | plataforma | — | — | **sem tela** | não se aplica |
| POST | `/api/plataforma/inquilinos/{id}/suspender` | plataforma | — | — | **sem tela** | não se aplica |
| GET | `/api/privilegios` | usuarios | `/admin/papeis`, `/conta` | `web/js/auth/conta.js:407`<br>`web/js/auth/papeis.js:26` | **coberto** | com erro |
| GET | `/api/publico/itens/{id}` | compartilhamento | — | `leitura de item público por quem recebe o link, sem sessão; a ficha do item mostra o link` | **externo sem exposição** | não se aplica |
| GET | `/api/publico/itens/{id}/miniatura` | compartilhamento | — | `leitura de item público por quem recebe o link, sem sessão; a ficha do item mostra o link` | **externo sem exposição** | não se aplica |
| POST | `/api/reverso` | geocodificador | — | — | **sem tela** | não se aplica |
| POST | `/api/rota` | rede | — | — | **sem tela** | não se aplica |
| POST | `/api/senha/redefinir/aplicar` | redefinicao | `/redefinir-senha` | `web/js/auth/redefinir_senha.js:62` | **coberto** | com erro |
| GET | `/api/senha/redefinir/resolver` | redefinicao | `/redefinir-senha` | `web/js/auth/redefinir_senha.js:25` | **coberto** | com erro |
| POST | `/api/senha/redefinir/solicitar` | redefinicao | `/redefinir-senha` | `web/js/auth/redefinir_senha.js:47` | **coberto** | com erro |
| GET | `/api/sugerir` | geocodificador | — | — | **sem tela** | não se aplica |
| GET | `/api/tipos-item` | catalogo | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:72` | **coberto** | com erro |
| GET | `/api/tokens` | tokens | `/admin/log`, `/admin/tokens` | `web/js/auth/log.js:36`<br>`web/js/auth/tokens.js:85` | **coberto** | com erro |
| POST | `/api/tokens` | tokens | `/admin/tokens`, `/uploads` | `web/js/auth/tokens.js:155`<br>`web/js/uploads/enviar.js:25` | **coberto** | com erro |
| GET | `/api/tokens/{id}` | tokens | `/admin/tokens` | `web/js/auth/tokens.js:192` | **coberto** | com erro |
| DELETE | `/api/tokens/{id}` | tokens | `/admin/tokens` | `web/js/auth/tokens.js:124` | **coberto** | com erro |
| GET | `/api/tokens/{id}/log` | tokens | `/admin/tokens` | `web/js/auth/tokens.js:186` | **coberto** | com erro |
| POST | `/api/tokens/{id}/renovar` | tokens | `/admin/tokens` | `web/js/auth/tokens.js:116` | **coberto** | com erro |
| POST | `/api/uploads` | uploads | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/uploads` | `web/js/catalogo/api.js:141`<br>`web/js/uploads/enviar.js:162` | **coberto** | com erro |
| GET | `/api/uploads/tipos` | uploads | `/uploads` | `web/js/uploads/enviar.js:54` | **coberto** | com erro |
| GET | `/api/uploads/{id}` | uploads | `/uploads` | `web/js/uploads/enviar.js:54` | **coberto** | com erro |
| DELETE | `/api/uploads/{id}` | uploads | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/uploads` | `web/js/catalogo/api.js:144`<br>`web/js/uploads/enviar.js:105` | **coberto** | com erro |
| POST | `/api/uploads/{id}/concluir` | uploads | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:143` | **coberto** | com erro |
| PUT | `/api/uploads/{id}/partes/{n}` | uploads | `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/api.js:142` | **coberto** | com erro |
| GET | `/api/usuarios` | usuarios | `/admin/grupos`, `/admin/log`, `/admin/usuarios`, `/c/{token}`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/auth/grupos.js:292`<br>`web/js/auth/log.js:35`<br>`web/js/auth/usuarios.js:92`<br>`web/js/catalogo/api.js:138` | **coberto** | com erro |
| POST | `/api/usuarios` | usuarios | `/admin/usuarios` | `web/js/auth/usuarios.js:214` | **coberto** | com erro |
| POST | `/api/usuarios/lote` | usuarios | `/admin/usuarios` | `web/js/auth/usuarios.js:125`<br>`web/js/auth/usuarios.js:214` | **coberto** | com erro |
| GET | `/api/usuarios/{id}` | usuarios | — | — | **sem controle** | não se aplica |
| PUT | `/api/usuarios/{id}` | usuarios | `/admin/usuarios` | `web/js/auth/usuarios.js:157` | **coberto** | com erro |
| DELETE | `/api/usuarios/{id}` | usuarios | `/admin/usuarios` | `web/js/auth/usuarios.js:163` | **coberto** | com erro |
| POST | `/api/usuarios/{id}/2fa/desativar` | usuarios | `/admin/usuarios` | `web/js/auth/usuarios.js:147` | **coberto** | com erro |
| POST | `/api/usuarios/{id}/desbloquear` | usuarios | `/admin/usuarios` | `web/js/auth/usuarios.js:152` | **coberto** | com erro |
| POST | `/api/usuarios/{id}/senha` | usuarios | `/admin/usuarios` | `web/js/auth/usuarios.js:140` | **coberto** | com erro |
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
| `/entrar` | login.html | sim | **não** | **não** | sim | sim |
| `/conta` | conta.html | sim | sim | **não** | sim | sim |
| `/admin/usuarios` | admin/usuarios.html | sim | **não** | **não** | sim | sim |
| `/admin/grupos` | admin/grupos.html | sim | sim | **não** | sim | sim |
| `/admin/papeis` | admin/papeis.html | sim | sim | **não** | sim | sim |
| `/admin/tokens` | admin/tokens.html | sim | sim | **não** | sim | sim |
| `/admin/log` | admin/log.html | sim | sim | **não** | sim | sim |
| `/admin/organizacao` | admin/organizacao.html | sim | sim | **não** | sim | sim |
| `/conteudo` | conteudo.html | sim | sim | sim | sim | sim |
| `/conteudo/lixeira` | conteudo_lixeira.html | sim | sim | sim | sim | sim |
| `/conteudo/{id}` | conteudo_item.html | sim | sim | sim | sim | sim |
| `/c/{token}` | compartilhado.html | sim | sim | **não** | sim | sim |
| `/mapa` | mapa.html | sim | **não** | **não** | sim | sim |
| `/conexoes` | conexoes.html | sim | **não** | **não** | sim | sim |
| `/aceitar-convite` | aceitar_convite.html | sim | **não** | **não** | sim | **não** |
| `/redefinir-senha` | redefinir_senha.html | sim | **não** | **não** | sim | **não** |
| `/uploads` | uploads.html | sim | **não** | **não** | sim | sim |
| `/tarefas` | tarefas.html | sim | sim | sim | sim | sim |
| `/tarefas/{job_id}` | tarefas.html | sim | **não** | **não** | **não** | **não** |

## Lacunas de escrita (cada grupo vira um item UX-<n> no backlog via `--registrar`)

- **acervo**: POST `/api/acervo/{fonte_id}/adicionar` (sem tela)
- **arquivos**: POST `/api/arquivos` (sem controle); DELETE `/api/arquivos/{sha256}` (sem controle)
- **categorias**: PUT `/api/categorias` (sem controle); POST `/api/categorias/importar` (sem controle)
- **conexoes**: POST `/api/conexoes` (sem controle); PATCH `/api/conexoes/{id}` (sem controle); DELETE `/api/conexoes/{id}` (sem controle)
- **geocodificador**: POST `/api/geocodificar` (sem tela); POST `/api/reverso` (sem tela)
- **geocodificador-esri**: POST `/rest/services/Geocodificador/GeocodeServer` (externo sem exposição); POST `/rest/services/Geocodificador/GeocodeServer/findAddressCandidates` (externo sem exposição); POST `/rest/services/Geocodificador/GeocodeServer/geocodeAddresses` (externo sem exposição); POST `/rest/services/Geocodificador/GeocodeServer/reverseGeocode` (externo sem exposição)
- **ingestao**: POST `/api/importacoes` (sem tela); DELETE `/api/importacoes/{id}` (sem tela); PUT `/api/importacoes/{id}/confirmar` (sem tela)
- **login**: POST `/api/login/ldap` (sem controle); PUT `/api/org/ldap` (sem controle); POST `/api/org/ldap/importar` (sem controle)
- **plataforma**: POST `/api/plataforma/inquilinos` (sem tela); DELETE `/api/plataforma/inquilinos/{id}` (sem tela); POST `/api/plataforma/inquilinos/{id}/reativar` (sem tela); POST `/api/plataforma/inquilinos/{id}/suspender` (sem tela)
- **rede**: POST `/api/isocrona` (sem tela); POST `/api/matriz` (sem tela); POST `/api/rota` (sem tela)
- **usuarios**: PUT `/api/papeis/{id}` (sem controle)

## URLs chamadas pela tela sem rota correspondente na API

- `web/js/catalogo/api.js:68 GET /api/openapi.json`

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
| L0-08-a-oidc | parcial | `/api/sso` | rota sem tela |
| L2-01-a-documento-mapa | entregue | `/api/mapas` | rota sem tela |
| L2-01-a-documento-mapa | entregue | `/api/mapas/{id}/completo` | rota sem tela |
| L2-01-a-documento-mapa | entregue | `/c` | página existe |
| L2-01-d-popup-runtime | entregue | `/api/camadas/{id}/feicoes/{fid}/popup` | rota sem tela |
| L2-02-b-classificacao-servidor | entregue | `/api/camadas/{id}/classes` | rota sem tela |
| L2-03-a-api-edicao-transacional | entregue | `/api/camadas/{id}/edicoes` | rota sem tela |
| L2-03-d-historico-restauracao | entregue | `/api/camadas/{id}/feicoes/{fid}/historico` | rota sem tela |
| L2-04-d-featureserver-edicao-anexos | parcial | `/uploads/upload` | página existe |
| L2-04-e-vector-tile-server-tilejson | entregue | `/c` | página existe |
| L2-04-g-ogc-api-features-crs-cql2 | parcial | `/api` | página inexistente |
| L2-07-a-pwa-instalavel-cache | entregue | `/c` | página existe |
| L2-10-b-relacionamentos | entregue | `/api/camadas/{id}/relacionados/{rel}` | rota sem tela |
| L2-11-b-geocodificador-brasil | parcial | `/api/geocodificar` | rota sem tela |
| L2-11-c-rota-matriz-isocrona | parcial | `/api/rota` | rota sem tela |
| L2-17-crs-transformacoes | parcial | `/api/crs/{codigo}` | rota sem tela |
| L4-02-a-conectado-e-subrede | parcial | `/api/v1/rede/{id}/tracar` | rota sem tela |
| L5-05-documento-versoes | entregue | `/api/esquemas` | rota sem tela |
| L5-05-documento-versoes | entregue | `/api/itens/{id}/versoes` | rota coberta |
| L5-14-publicacao-links-embed | parcial | `/p` | página inexistente |
| L2-01-a-basemap-local-pmtiles | entregue | `/mapa` | página existe |

Itens com efeito visível que não citam página nem rota no texto (91; a cobertura deles é conferida pelo e2e do item, não por este cruzamento): L0-02-b-politica-senha-bloqueio, L0-02-c-2fa-totp, L0-02-d-token-servico, L0-02-f-tela-usuarios, L0-02-g-perfil-usuario, L0-02-tenant-auth, L0-03-b-pastas-tags-categorias-classificacao, L0-03-catalogo, L0-03-d-grupos, L0-03-g-detalhe-item-miniatura, L0-04-d-formatos-base, L0-04-e-formatos-cad, L0-04-h-exportar, L0-04-i-fonte-registrada, L0-04-ingest-vetor, L0-05-d-periodicos, L0-05-jobs, L0-07-a-configuracoes-org, L0-07-b-papeis-privilegios, L0-07-c-cotas-uso, L0-07-d-smtp-convites, L0-08-d-ldap, L0-09-a-procedencia, L0-09-b-editor-iso-mgb, L0-10-eventos-historico, L0-11-arquivos-objetos, L0-12-contrato-api-e-limites, L0-13-dado-demonstracao, L1-01-ingest-raster, L2-01-b-martin-tiles-vetoriais, L2-01-c-lista-camadas-legenda, L2-01-e-mapas-base, L2-01-g-tabela-atributos, L2-01-h-selecao-filtros, L2-01-k-desenho-anotacoes, L2-01-l-exportacao-do-mapa, L2-01-mapa-web, L2-02-a-modelo-estilo, L2-02-d-rotulos, L2-02-e-simbolos-sprites-glifos, L2-02-f-estilo-raster, L2-03-b-ferramentas-geometria, L2-03-c-formulario-atributos-runtime, L2-03-e-anexos, L2-03-edicao, L2-04-b-featureserver-catalogo-metadados, L2-04-c-featureserver-query, L2-04-servicos-esri-ogc, L2-05-a-catalogo-ferramentas-gpserver, L2-06-a-modelo-painel-fontes, L2-07-b-formulario-de-coleta-xlsform, L2-08-a-leitor-portal-inventario, L2-09-a-terreno-terrain-rgb-relevo, L2-10-a-dominios-subtipos, L2-10-c-linguagem-expressao, L2-11-a-geocodificacao-csv, L2-12-a-motor-render-servidor, L3-01-b-unidades, L3-01-e-combinacao, L3-01-f-explicacao, L3-04-restricoes, L3-14-cobertura-dado-ausente, L3-16-desempenho-escala, L4-02-d-lacos-e-caminho-curto, L4-18-rede-simples-trace-network, L5-01-a-layout-paginas, L5-06-motor-widgets, L5-08-editor-arrasto, L5-09-desfazer-refazer-rascunho, L5-12-acessibilidade-i18n-construtores, L5-15-vista-movel-responsivo, L5-31-construtor-de-camada-esquema, L6-01-b-view-so-leitura, L6-01-c-tela-acervo, L6-01-d-ficha-fonte, L6-01-g-licenca-curada, L6-02-b-wms-wmts, L6-02-c-wfs-ogcapi, L6-02-d-arcgis-rest-externo, L6-02-k-agendamento, L6-02-l-saude, L6-05-proveniencia-camada-externa, L7-01-c-dado-demonstracao, L7-06-b-alertas, L7-06-c-logs-consulta-req-id, L7-06-d-paineis, L7-08-b-sdk-python, L7-08-d-portal-api-chaves, L7-20-trilha-auditoria, L7-33-modo-somente-leitura, L7-34-saude-profunda
