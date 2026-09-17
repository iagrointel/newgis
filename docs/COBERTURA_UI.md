# Cobertura da interface (gerado — não editar à mão)

Gerado por `docs/gerar_cobertura_ui.py` (item UX-00-mapa-de-cobertura-da-interface). Rotas lidas da aplicação; chamadas lidas de `web/`; telas de `app/paginas.py`. Heurísticas de texto declaradas no cabeçalho do gerador: o que elas não veem, o e2e vê. Regra da trilha: nenhuma rota fica só no backend.

## Placar

| medida | valor |
|---|---|
| rotas (método × caminho) | 958 |
| coberto | 375 |
| sem controle | 266 |
| sem tela | 165 |
| externo | 37 |
| externo sem exposição | 2 |
| sem tela por desenho | 113 |
| cobertas sem estado de erro perto da chamada | 13 |
| lacunas de ESCRITA (linha de base do teste) | 194 |
| URLs chamadas pela tela que não existem na API | 15 |

## Rotas → tela/controle → estado

| método | rota | grupo | tela | controle (arquivo:linha) | estado | erro |
|---|---|---|---|---|---|---|
| GET | `/api/acervo` | acervo | `/admin`, `/admin/acervo` | `web/js/auth/acervo.js:76`<br>`web/js/auth/admin.js:97` | **coberto** | com erro |
| GET | `/api/acervo/camadas` | acervo | `/admin/acervo`, `/amc/motor`, `/mapa` | `web/js/amc/motor_pagina.js:484`<br>`web/js/auth/acervo.js:104`<br>`web/js/mapa/mapa.js:65` | **coberto** | com erro |
| GET | `/api/acervo/camadas/{acervo_camada_id}/verificacoes` | acervo | `/acervo` | `web/js/acervo/acervo.js:59` | **coberto** | com erro |
| POST | `/api/acervo/camadas/{camada}/assinatura` | acervo | — | — | **sem controle** | não se aplica |
| DELETE | `/api/acervo/camadas/{camada}/assinatura` | acervo | — | — | **sem controle** | não se aplica |
| GET | `/api/acervo/camadas/{camada}/exportar` | acervo | — | — | **sem controle** | não se aplica |
| GET | `/api/acervo/camadas/{camada}/feicoes` | acervo | — | — | **sem controle** | não se aplica |
| GET | `/api/acervo/camadas/{camada}/tiles/{z}/{x}/{y}.mvt` | acervo | — | — | **sem controle** | não se aplica |
| GET | `/api/acervo/frescor/camadas` | acervo | `/acervo` | `web/js/acervo/acervo.js:99` | **coberto** | com erro |
| GET | `/api/acervo/frescor/execucoes` | acervo | — | — | **sem controle** | não se aplica |
| GET | `/api/acervo/frescor/mudancas` | acervo | `/acervo` | `web/js/acervo/acervo.js:122` | **coberto** | com erro |
| GET | `/api/acervo/uso` | acervo | `/admin/acervo` | `web/js/auth/acervo.js:104` | **coberto** | com erro |
| GET | `/api/acervo/uso/mensal` | acervo | — | — | **sem controle** | não se aplica |
| GET | `/api/acervo/{fonte_id}` | acervo | `/admin/acervo`, `/amc/motor`, `/mapa` | `web/js/amc/motor_pagina.js:484`<br>`web/js/auth/acervo.js:104`<br>`web/js/mapa/mapa.js:65` | **coberto** | com erro |
| POST | `/api/acervo/{fonte_id}/adicionar` | acervo | `/admin/acervo` | `web/js/auth/acervo.js:154` | **coberto** | com erro |
| GET | `/api/agendas` | agendas | `/ferramentas`, `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:57` | **coberto** | com erro |
| POST | `/api/agendas` | agendas | `/ferramentas`, `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:59` | **coberto** | com erro |
| GET | `/api/agendas/{agenda_id}` | agendas | `/ferramentas`, `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:58` | **coberto** | com erro |
| PUT | `/api/agendas/{agenda_id}` | agendas | `/ferramentas`, `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:60` | **coberto** | com erro |
| DELETE | `/api/agendas/{agenda_id}` | agendas | `/admin/atividade`, `/ferramentas`, `/tarefas`, `/tarefas/{job_id}` | `web/js/auth/atividade.js:208`<br>`web/js/jobs/api.js:61` | **coberto** | com erro |
| POST | `/api/agendas/{agenda_id}/pausar` | agendas | `/ferramentas`, `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:62` | **coberto** | com erro |
| POST | `/api/agendas/{agenda_id}/retomar` | agendas | `/ferramentas`, `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:63` | **coberto** | com erro |
| POST | `/api/agendas/{agenda_id}/rodar-agora` | agendas | `/admin/atividade`, `/ferramentas`, `/tarefas`, `/tarefas/{job_id}` | `web/js/auth/atividade.js:203`<br>`web/js/jobs/api.js:64` | **coberto** | com erro |
| GET | `/api/agol/credencial` | agol | `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/tipos/camada_vetorial.js:167` | **coberto** | com erro |
| PUT | `/api/agol/credencial` | agol | `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/tipos/camada_vetorial.js:198` | **coberto** | com erro |
| GET | `/api/agol/publicacoes` | agol | — | — | **sem controle** | não se aplica |
| POST | `/api/agol/publicacoes` | agol | `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/tipos/camada_vetorial.js:260` | **coberto** | com erro |
| GET | `/api/agol/publicacoes/{item_id}` | agol | `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/tipos/camada_vetorial.js:168` | **coberto** | com erro |
| POST | `/api/agol/testar` | agol | `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/tipos/camada_vetorial.js:212` | **coberto** | com erro |
| GET | `/api/amc/conjuntos` | amc | — | — | **sem controle** | não se aplica |
| POST | `/api/amc/conjuntos` | amc | — | — | **sem controle** | não se aplica |
| GET | `/api/amc/conjuntos/{conjunto_id}` | amc | — | — | **sem controle** | não se aplica |
| DELETE | `/api/amc/conjuntos/{conjunto_id}` | amc | — | — | **sem controle** | não se aplica |
| GET | `/api/amc/conjuntos/{conjunto_id}/unidades` | amc | `/amc/motor` | `web/js/amc/motor_pagina.js:795` | **coberto** | com erro |
| POST | `/api/amc/criterios-feicao` | amc | `/amc/criterios-feicao` | `web/js/amc/criterios_feicao_pagina.js:146` | **coberto** | com erro |
| POST | `/api/amc/criterios-feicao/exportar` | amc | — | — | **sem controle** | não se aplica |
| GET | `/api/amc/execucoes` | amc | — | — | **sem controle** | não se aplica |
| POST | `/api/amc/execucoes` | amc | `/amc/motor` | `web/js/amc/motor_pagina.js:671` | **coberto** | com erro |
| GET | `/api/amc/execucoes/{execucao_id}` | amc | `/amc/motor` | `web/js/amc/motor_pagina.js:692`<br>`web/js/amc/motor_pagina.js:865` | **coberto** | com erro |
| DELETE | `/api/amc/execucoes/{execucao_id}` | amc | — | — | **sem controle** | não se aplica |
| GET | `/api/amc/execucoes/{execucao_id}/matriz` | amc | `/amc/motor` | `web/js/amc/motor_pagina.js:804` | **coberto** | com erro |
| GET | `/api/amc/execucoes/{execucao_id}/resultados` | amc | — | — | **sem controle** | não se aplica |
| GET | `/api/amc/execucoes/{execucao_id}/unidades/{unidade_id}/explicacao` | amc | `/amc/explicacao/{execucao_id}/{unidade_id}` | `web/js/amc/explicacao_pagina.js:144` | **coberto** | com erro |
| GET | `/api/amc/modelos` | amc | — | — | **sem controle** | não se aplica |
| POST | `/api/amc/modelos` | amc | — | — | **sem controle** | não se aplica |
| POST | `/api/amc/modelos/validar` | amc | — | — | **sem controle** | não se aplica |
| GET | `/api/amc/modelos/{modelo_id}` | amc | `/amc/motor` | `web/js/amc/motor_pagina.js:881` | **coberto** | com erro |
| PUT | `/api/amc/modelos/{modelo_id}` | amc | `/amc/motor` | `web/js/amc/motor_pagina.js:652` | **coberto** | com erro |
| DELETE | `/api/amc/modelos/{modelo_id}` | amc | — | — | **sem controle** | não se aplica |
| GET | `/api/amc/modelos/{modelo_id}/versoes` | amc | — | — | **sem controle** | não se aplica |
| GET | `/api/amc/modelos/{modelo_id}/versoes/{versao_hash}` | amc | — | — | **sem controle** | não se aplica |
| POST | `/api/amc/pareto` | amc | — | — | **sem controle** | não se aplica |
| POST | `/api/amc/pareto/camada` | amc | `/amc/pareto` | `web/js/amc/pareto_tela.js:237`<br>`web/js/amc/pareto_tela.js:69` | **coberto** | sem estado de erro |
| GET | `/api/amc/presets` | amc | `/amc/presets` | `web/js/amc/presets.js:265` | **coberto** | com erro |
| POST | `/api/amc/presets` | amc | `/amc/presets` | `web/js/amc/presets.js:97` | **coberto** | com erro |
| POST | `/api/amc/presets/importar` | amc | `/amc/presets` | `web/js/amc/presets.js:203` | **coberto** | com erro |
| GET | `/api/amc/presets/{id}` | amc | — | — | **sem controle** | não se aplica |
| PATCH | `/api/amc/presets/{id}` | amc | `/amc/presets` | `web/js/amc/presets.js:96` | **coberto** | com erro |
| DELETE | `/api/amc/presets/{id}` | amc | `/amc/presets` | `web/js/amc/presets.js:235` | **coberto** | com erro |
| POST | `/api/amc/presets/{id}/aplicar` | amc | `/amc/presets` | `web/js/amc/presets.js:131` | **coberto** | com erro |
| GET | `/api/amc/presets/{id}/exportar` | amc | `/amc/presets` | `web/js/amc/presets.js:163` | **coberto** | com erro |
| POST | `/api/amc/similaridade` | amc | — | — | **sem controle** | não se aplica |
| POST | `/api/amc/similaridade/exportar` | amc | — | — | **sem controle** | não se aplica |
| POST | `/api/amc/transformacoes/previsao` | amc | `/amc/motor` | `web/js/amc/motor_pagina.js:430` | **coberto** | com erro |
| POST | `/api/analise3d/perfil` | analise3d | `/analise3d` | `web/js/analise3d/painel.js:157` | **coberto** | com erro |
| POST | `/api/analise3d/sombra` | analise3d | `/analise3d` | `web/js/analise3d/painel.js:177` | **coberto** | com erro |
| POST | `/api/analise3d/viewshed` | analise3d | `/analise3d` | `web/js/analise3d/painel.js:130` | **coberto** | com erro |
| POST | `/api/analise3d/visada` | analise3d | `/analise3d` | `web/js/analise3d/painel.js:90` | **coberto** | com erro |
| GET | `/api/anotacoes` | mapa | — | — | **sem controle** | não se aplica |
| POST | `/api/anotacoes` | mapa | — | — | **sem controle** | não se aplica |
| PATCH | `/api/anotacoes/{id}` | mapa | — | — | **sem controle** | não se aplica |
| DELETE | `/api/anotacoes/{id}` | mapa | — | — | **sem controle** | não se aplica |
| GET | `/api/arquivos` | arquivos | — | — | **sem controle** | não se aplica |
| POST | `/api/arquivos` | arquivos | — | — | **sem controle** | não se aplica |
| GET | `/api/arquivos/_chave-leitura` | arquivos | `/admin/organizacao`, `/aplicativo`, `/executar` | `web/js/app/fontes.js:72`<br>`web/js/auth/organizacao.js:178` | **coberto** | com erro |
| GET | `/api/arquivos/_cog/autorizar` | arquivos | — | — | **sem controle** | não se aplica |
| GET | `/api/arquivos/_varredura` | arquivos | `/admin/organizacao`, `/aplicativo`, `/executar` | `web/js/app/fontes.js:72`<br>`web/js/auth/organizacao.js:178` | **coberto** | com erro |
| GET | `/api/arquivos/{sha256}` | arquivos | `/admin/organizacao`, `/aplicativo`, `/executar` | `web/js/app/fontes.js:72`<br>`web/js/auth/organizacao.js:178` | **coberto** | com erro |
| DELETE | `/api/arquivos/{sha256}` | arquivos | — | — | **sem controle** | não se aplica |
| GET | `/api/atividade` | relatorios | `/admin/atividade` | `web/js/auth/atividade.js:46` | **coberto** | com erro |
| GET | `/api/auditoria` | auditoria | `/admin/auditoria` | `web/js/auth/auditoria.js:147`<br>`web/js/auth/auditoria.js:148`<br>`web/js/auth/auditoria.js:150` | **coberto** | com erro |
| GET | `/api/auditoria/config` | auditoria | `/admin/auditoria` | `web/js/auth/auditoria.js:42` | **coberto** | com erro |
| PUT | `/api/auditoria/config` | auditoria | `/admin/auditoria` | `web/js/auth/auditoria.js:68` | **coberto** | com erro |
| GET | `/api/backup/backups` | backup | `/admin/backup` | `web/js/admin/backup.js:94` | **coberto** | com erro |
| GET | `/api/backup/ensaios` | backup | `/admin/backup` | `web/js/admin/backup.js:105`<br>`web/js/admin/backup.js:77` | **coberto** | com erro |
| POST | `/api/camadas/esquema` | camada-esquema | `/construtor-camada` | `web/js/catalogo/camada_esquema.js:175` | **coberto** | com erro |
| POST | `/api/camadas/{camada_id}/vistas` | vista-de-camada | `/vista-de-camada` | `web/js/catalogo/vista_camada.js:102` | **coberto** | com erro |
| GET | `/api/camadas/{id}/campos` | formulario | `/camadas/{id}/formulario`, `/vista-de-camada` | `web/js/catalogo/vista_camada.js:45`<br>`web/js/formulario/construtor.js:41` | **coberto** | com erro |
| POST | `/api/camadas/{id}/edicoes` | edicao | `/sig` | `web/js/mapa/edicao.js:217`<br>`web/js/mapa/edicao.js:229`<br>`web/js/mapa/edicao.js:407`<br>`web/js/mapa/edicao.js:428`<br>`web/js/mapa/edicao.js:522` | **coberto** | com erro |
| GET | `/api/camadas/{id}/erros` | regras | — | — | **sem controle** | não se aplica |
| GET | `/api/camadas/{id}/feicoes` | regras | `/aplicativo`, `/camadas/{id}/dominios`, `/executar` | `web/js/app/fontes.js:6`<br>`web/js/app/fontes.js:80`<br>`web/js/dominios/tela.js:173` | **coberto** | com erro |
| POST | `/api/camadas/{id}/feicoes/dividir` | edicao | `/sig` | `web/js/mapa/edicao.js:266` | **coberto** | com erro |
| POST | `/api/camadas/{id}/feicoes/unir` | edicao | `/sig` | `web/js/mapa/edicao.js:281` | **coberto** | com erro |
| GET | `/api/camadas/{id}/feicoes/{fid}/popup` | mapa-popup | `/sig` | `web/js/mapa/atributos.js:124` | **coberto** | com erro |
| GET | `/api/camadas/{id}/feicoes/{globalid}` | edicao | `/sig` | `web/js/mapa/edicao.js:199` | **coberto** | com erro |
| GET | `/api/camadas/{id}/feicoes/{globalid}/anexos` | edicao | `/sig` | `web/js/mapa/edicao.js:467` | **coberto** | com erro |
| POST | `/api/camadas/{id}/feicoes/{globalid}/anexos` | edicao | `/sig` | `web/js/mapa/edicao.js:495` | **coberto** | com erro |
| GET | `/api/camadas/{id}/feicoes/{globalid}/anexos/{anexo_id}` | edicao | `/sig` | `web/js/mapa/edicao.js:472`<br>`web/js/mapa/edicao.js:477` | **coberto** | com erro |
| DELETE | `/api/camadas/{id}/feicoes/{globalid}/anexos/{anexo_id}` | edicao | — | — | **sem controle** | não se aplica |
| GET | `/api/camadas/{id}/feicoes/{globalid}/historico` | edicao | `/sig` | `web/js/mapa/edicao.js:439` | **coberto** | com erro |
| POST | `/api/camadas/{id}/feicoes/{globalid}/historico/{historico_id}/restaurar` | edicao | `/sig` | `web/js/mapa/edicao.js:449` | **coberto** | com erro |
| GET | `/api/camadas/{id}/formulario` | formulario | `/campo/roteiros/{roteiro_id}`, `/sig` | `web/js/campo/roteiro.js:208`<br>`web/js/mapa/edicao.js:298` | **coberto** | com erro |
| POST | `/api/camadas/{id}/formulario` | formulario | — | — | **sem controle** | não se aplica |
| GET | `/api/camadas/{id}/formulario/versoes` | formulario | `/camadas/{id}/formulario` | `web/js/formulario/construtor.js:45` | **coberto** | com erro |
| POST | `/api/camadas/{id}/formulario/versoes` | formulario | `/camadas/{id}/formulario` | `web/js/formulario/construtor.js:171` | **coberto** | com erro |
| GET | `/api/camadas/{id}/formulario/versoes/{versao}` | formulario | `/camadas/{id}/formulario` | `web/js/formulario/construtor.js:52` | **coberto** | com erro |
| POST | `/api/camadas/{id}/formulario/versoes/{versao}/publicar` | formulario | `/camadas/{id}/formulario` | `web/js/formulario/construtor.js:181` | **coberto** | com erro |
| POST | `/api/camadas/{id}/lote` | edicao | `/sig` | `web/js/mapa/edicao.js:659`<br>`web/js/mapa/edicao.js:668` | **coberto** | com erro |
| GET | `/api/camadas/{id}/regras` | regras | — | — | **sem controle** | não se aplica |
| PUT | `/api/camadas/{id}/regras` | regras | — | — | **sem controle** | não se aplica |
| POST | `/api/camadas/{id}/validar` | regras | — | — | **sem controle** | não se aplica |
| POST | `/api/camadas/{id}/versionar` | versionamento | — | — | **sem controle** | não se aplica |
| GET | `/api/camadas/{id}/versoes` | versionamento | `/versoes` | `web/js/versoes/painel.js:64` | **coberto** | com erro |
| POST | `/api/camadas/{id}/versoes` | versionamento | — | — | **sem controle** | não se aplica |
| GET | `/api/camadas/{id}/versoes/{versao}` | versionamento | `/versoes` | `web/js/versoes/painel.js:188` | **coberto** | com erro |
| DELETE | `/api/camadas/{id}/versoes/{versao}` | versionamento | — | — | **sem controle** | não se aplica |
| GET | `/api/camadas/{id}/versoes/{versao}/conflitos` | versionamento | — | — | **sem controle** | não se aplica |
| POST | `/api/camadas/{id}/versoes/{versao}/conflitos/{globalid}/resolver` | versionamento | — | — | **sem controle** | não se aplica |
| POST | `/api/camadas/{id}/versoes/{versao}/publicar` | versionamento | `/versoes` | `web/js/versoes/painel.js:90` | **coberto** | com erro |
| POST | `/api/camadas/{id}/versoes/{versao}/reconciliar` | versionamento | `/versoes` | `web/js/versoes/painel.js:78` | **coberto** | com erro |
| GET | `/api/camadas/{item_id}/classes` | estatistica | — | — | **sem tela** | não se aplica |
| GET | `/api/camadas/{item_id}/dominios` | dominios | `/camadas/{id}/dominios` | `web/js/dominios/tela.js:41` | **coberto** | com erro |
| POST | `/api/camadas/{item_id}/dominios` | dominios | — | — | **sem controle** | não se aplica |
| DELETE | `/api/camadas/{item_id}/dominios/{ligacao_id}` | dominios | — | — | **sem controle** | não se aplica |
| PUT | `/api/camadas/{item_id}/esquema` | camada-esquema | — | — | **sem controle** | não se aplica |
| GET | `/api/camadas/{item_id}/esquema/campos` | camada-esquema | `/construtor-camada` | `web/js/catalogo/camada_esquema.js:186` | **coberto** | com erro |
| POST | `/api/camadas/{item_id}/esquema/plano` | camada-esquema | — | — | **sem controle** | não se aplica |
| POST | `/api/camadas/{item_id}/estatisticas` | estatistica | — | — | **sem tela** | não se aplica |
| POST | `/api/camadas/{item_id}/feicoes` | feicoes | `/camadas/{id}/dominios` | `web/js/dominios/tela.js:159` | **coberto** | com erro |
| POST | `/api/camadas/{item_id}/grafico` | estatistica | — | — | **sem tela** | não se aplica |
| GET | `/api/camadas/{item_id}/relacionados/{rel}` | relacionamentos | — | — | **sem tela** | não se aplica |
| GET | `/api/camadas/{item_id}/relacionamentos` | relacionamentos | — | — | **sem tela** | não se aplica |
| GET | `/api/camadas/{item_id}/subtipos` | dominios | — | — | **sem controle** | não se aplica |
| PUT | `/api/camadas/{item_id}/subtipos` | dominios | — | — | **sem controle** | não se aplica |
| DELETE | `/api/camadas/{item_id}/subtipos` | dominios | — | — | **sem controle** | não se aplica |
| GET | `/api/camadas/{item_id}/tabela/colunas` | tabela | — | — | **sem tela** | não se aplica |
| POST | `/api/camadas/{item_id}/tabela/estatisticas` | tabela | — | — | **sem tela** | não se aplica |
| POST | `/api/camadas/{item_id}/tabela/linhas` | tabela | — | — | **sem tela** | não se aplica |
| GET | `/api/camadas/{item_id}/tabela/vista` | tabela | — | — | **sem tela** | não se aplica |
| PUT | `/api/camadas/{item_id}/tabela/vista` | tabela | — | — | **sem tela** | não se aplica |
| GET | `/api/campo/camadas/{camada_id}/globalids` | campo | `/campo/filas` | `web/js/campo/filas.js:24` | **coberto** | com erro |
| GET | `/api/campo/filas` | campo | `/campo/filas` | `web/js/campo/filas.js:29` | **coberto** | com erro |
| POST | `/api/campo/filas` | campo | `/campo/filas` | `web/js/campo/filas.js:96` | **coberto** | com erro |
| GET | `/api/campo/filas/{fila_id}` | campo | `/campo/filas/{fila_id}`, `/campo/roteiros/{roteiro_id}` | `web/js/campo/fila.js:34`<br>`web/js/campo/roteiro.js:202` | **coberto** | com erro |
| POST | `/api/campo/filas/{fila_id}/alvos` | campo | — | — | **sem controle** | não se aplica |
| GET | `/api/campo/filas/{fila_id}/alvos.geojson` | campo | — | — | **sem controle** | não se aplica |
| PUT | `/api/campo/filas/{fila_id}/ordem` | campo | — | — | **sem controle** | não se aplica |
| GET | `/api/campo/mapas` | campo | — | — | **sem controle** | não se aplica |
| GET | `/api/campo/roteiros` | campo | — | — | **sem controle** | não se aplica |
| POST | `/api/campo/roteiros` | campo | `/campo/filas/{fila_id}` | `web/js/campo/fila.js:52` | **coberto** | com erro |
| GET | `/api/campo/roteiros/{roteiro_id}` | campo | `/campo/roteiros/{roteiro_id}` | `web/js/campo/roteiro.js:136` | **coberto** | com erro |
| GET | `/api/campo/roteiros/{roteiro_id}/trajeto.geojson` | campo | — | — | **sem controle** | não se aplica |
| POST | `/api/campo/sessao` | campo | — | — | **sem controle** | não se aplica |
| GET | `/api/campo/visitas` | campo | — | — | **sem controle** | não se aplica |
| POST | `/api/campo/visitas` | campo | `/campo/roteiros/{roteiro_id}` | `web/js/campo/roteiro.js:49` | **coberto** | com erro |
| GET | `/api/campo/visitas/{visita_id}` | campo | — | — | **sem controle** | não se aplica |
| POST | `/api/campo/visitas/{visita_id}/fotos` | campo | `/campo/roteiros/{roteiro_id}` | `web/js/campo/roteiro.js:53` | **coberto** | com erro |
| GET | `/api/categorias` | categorias | `/admin/categorias`, `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:137`<br>`web/js/catalogo/categorias_admin.js:57` | **coberto** | com erro |
| PUT | `/api/categorias` | categorias | `/admin/categorias` | `web/js/catalogo/categorias_admin.js:137` | **coberto** | com erro |
| POST | `/api/categorias/importar` | categorias | `/admin/categorias` | `web/js/catalogo/categorias_admin.js:163` | **coberto** | com erro |
| GET | `/api/cena/sol` | cena | `/cena` | `web/js/cena/cena.js:76` | **coberto** | com erro |
| GET | `/api/chamados` | chamados | `/chamados` | `web/js/chamados/chamados.js:162` | **coberto** | com erro |
| POST | `/api/chamados` | chamados | — | — | **sem controle** | não se aplica |
| GET | `/api/chamados/banner` | chamados | `/chamados` | `web/js/chamados/chamados.js:61` | **coberto** | com erro |
| GET | `/api/chamados/{id}` | chamados | `/chamados` | `web/js/chamados/chamados.js:61` | **coberto** | com erro |
| POST | `/api/chamados/{id}/anexos` | chamados | `/chamados` | `web/js/chamados/chamados.js:135` | **coberto** | com erro |
| GET | `/api/chamados/{id}/anexos/{anexo_id}` | chamados | `/chamados` | `web/js/chamados/chamados.js:81` | **coberto** | sem estado de erro |
| POST | `/api/chamados/{id}/comentarios` | chamados | `/chamados` | `web/js/chamados/chamados.js:96` | **coberto** | com erro |
| POST | `/api/chamados/{id}/fechar` | chamados | `/chamados` | `web/js/chamados/chamados.js:109` | **coberto** | com erro |
| GET | `/api/compartilhado/{token}` | compartilhamento | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:120` | **coberto** | com erro |
| GET | `/api/compartilhado/{token}/itens/{id}` | compartilhamento | — | — | **sem controle** | não se aplica |
| GET | `/api/compartilhado/{token}/itens/{id}/miniatura` | compartilhamento | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:121` | **coberto** | com erro |
| POST | `/api/compartilhado/{token}/paineis/{item_id}/fontes/{fonte_id}/dados` | paineis | — | — | **sem tela** | não se aplica |
| GET | `/api/conexoes` | conexoes | `/conexoes`, `/migracao` | `web/js/conexoes/conexoes.js:492`<br>`web/js/migracao/migracao.js:60` | **coberto** | com erro |
| POST | `/api/conexoes` | conexoes | `/conexoes` | `web/js/conexoes/conexoes.js:286` | **coberto** | com erro |
| GET | `/api/conexoes/{id}` | conexoes | `/conexoes` | `web/js/conexoes/conexoes.js:245` | **coberto** | com erro |
| PATCH | `/api/conexoes/{id}` | conexoes | `/conexoes` | `web/js/conexoes/conexoes.js:285` | **coberto** | com erro |
| DELETE | `/api/conexoes/{id}` | conexoes | `/conexoes` | `web/js/conexoes/conexoes.js:154` | **coberto** | com erro |
| GET | `/api/conexoes/{id}/arquivo` | conexoes | — | — | **sem controle** | não se aplica |
| PUT | `/api/conexoes/{id}/arquivo` | conexoes | — | — | **sem controle** | não se aplica |
| POST | `/api/conexoes/{id}/arquivo/sincronizar` | conexoes | — | — | **sem controle** | não se aplica |
| GET | `/api/conexoes/{id}/camadas` | conexoes | `/conexoes` | `web/js/conexoes/conexoes.js:396` | **coberto** | com erro |
| GET | `/api/conexoes/{id}/colecoes` | conexoes | — | — | **sem controle** | não se aplica |
| GET | `/api/conexoes/{id}/colecoes/{colecao}/campos` | conexoes | — | — | **sem controle** | não se aplica |
| GET | `/api/conexoes/{id}/colecoes/{colecao}/feicoes` | conexoes | — | — | **sem controle** | não se aplica |
| POST | `/api/conexoes/{id}/descobrir` | conexoes | `/conexoes` | `web/js/conexoes/conexoes.js:386` | **coberto** | com erro |
| GET | `/api/conexoes/{id}/esri/camadas/{camada}` | esri_rest | — | — | **sem tela** | não se aplica |
| GET | `/api/conexoes/{id}/esri/camadas/{camada}/contagem` | esri_rest | — | — | **sem tela** | não se aplica |
| GET | `/api/conexoes/{id}/esri/camadas/{camada}/feicoes` | esri_rest | — | — | **sem tela** | não se aplica |
| GET | `/api/conexoes/{id}/esri/descricao` | esri_rest | — | — | **sem tela** | não se aplica |
| GET | `/api/conexoes/{id}/esri/imagem` | esri_rest | — | — | **sem tela** | não se aplica |
| GET | `/api/conexoes/{id}/esri/mapa` | esri_rest | — | — | **sem tela** | não se aplica |
| POST | `/api/conexoes/{id}/publicar` | conexoes | `/conexoes` | `web/js/conexoes/conexoes.js:125` | **coberto** | com erro |
| GET | `/api/conexoes/{id}/saude-historico` | conexoes | `/conexoes` | `web/js/conexoes/conexoes.js:98` | **coberto** | com erro |
| POST | `/api/conexoes/{id}/testar` | conexoes | `/conexoes` | `web/js/conexoes/conexoes.js:77` | **coberto** | com erro |
| GET | `/api/conexoes/{id}/tile` | conexoes | `/conexoes` | `web/js/conexoes/conexoes.js:342` | **coberto** | sem estado de erro |
| GET | `/api/conexoes/{id}/tilejson` | conexoes | — | — | **sem controle** | não se aplica |
| GET | `/api/conexoes/{id}/wms/capacidades` | wms_wmts | — | — | **sem tela** | não se aplica |
| GET | `/api/conexoes/{id}/wms/feicao` | wms_wmts | — | — | **sem tela** | não se aplica |
| GET | `/api/conexoes/{id}/wms/mapa` | wms_wmts | — | — | **sem tela** | não se aplica |
| GET | `/api/conexoes/{id}/wmts/capacidades` | wms_wmts | — | — | **sem tela** | não se aplica |
| GET | `/api/conexoes/{id}/wmts/tile-info` | wms_wmts | — | — | **sem tela** | não se aplica |
| GET | `/api/conexoes/{id}/wmts/tile/{tile_matrix_set}/{z}/{x}/{y}` | wms_wmts | — | — | **sem tela** | não se aplica |
| GET | `/api/convites` | convites | `/admin`, `/admin/usuarios` | `web/js/auth/admin.js:68`<br>`web/js/auth/convites.js:38` | **coberto** | com erro |
| POST | `/api/convites` | convites | `/admin/usuarios` | `web/js/auth/convites.js:53` | **coberto** | com erro |
| POST | `/api/convites/aceitar` | convites | `/aceitar-convite` | `web/js/auth/aceitar_convite.js:58` | **coberto** | com erro |
| GET | `/api/convites/resolver` | convites | `/aceitar-convite` | `web/js/auth/aceitar_convite.js:31` | **coberto** | com erro |
| DELETE | `/api/convites/{id}` | convites | `/admin/usuarios` | `web/js/auth/convites.js:25` | **coberto** | com erro |
| GET | `/api/crs` | crs | `/crs` | `web/js/crs/crs.js:64` | **coberto** | com erro |
| POST | `/api/crs/transformar` | crs | `/crs` | `web/js/crs/crs.js:144` | **coberto** | com erro |
| GET | `/api/crs/{epsg}` | crs | `/crs` | `web/js/crs/crs.js:94` | **coberto** | sem estado de erro |
| GET | `/api/crs/{epsg}.proj4` | crs | — | — | **sem controle** | não se aplica |
| POST | `/api/csw/buscar` | conexoes | — | — | **sem controle** | não se aplica |
| POST | `/api/csw/conexoes` | conexoes | — | — | **sem controle** | não se aplica |
| GET | `/api/dominios` | dominios | — | — | **sem controle** | não se aplica |
| POST | `/api/dominios` | dominios | — | — | **sem controle** | não se aplica |
| GET | `/api/dominios-limites` | dominios | — | — | **sem controle** | não se aplica |
| GET | `/api/dominios.csv` | dominios | — | — | **sem controle** | não se aplica |
| POST | `/api/dominios/csv` | dominios | — | — | **sem controle** | não se aplica |
| POST | `/api/dominios/importar` | dominios | — | — | **sem controle** | não se aplica |
| GET | `/api/dominios/{dominio_id}` | dominios | — | — | **sem controle** | não se aplica |
| PUT | `/api/dominios/{dominio_id}` | dominios | — | — | **sem controle** | não se aplica |
| DELETE | `/api/dominios/{dominio_id}` | dominios | — | — | **sem controle** | não se aplica |
| GET | `/api/dominios/{dominio_id}/uso` | dominios | — | — | **sem controle** | não se aplica |
| GET | `/api/endpoints-publicos` | conexoes | — | — | **sem controle** | não se aplica |
| GET | `/api/endpoints-publicos/{id}` | conexoes | — | — | **sem controle** | não se aplica |
| POST | `/api/endpoints-publicos/{id}/adicionar` | conexoes | — | — | **sem controle** | não se aplica |
| GET | `/api/esquemas` | catalogo | — | — | **sem controle** | não se aplica |
| GET | `/api/esquemas/{tipo}` | catalogo | — | — | **sem controle** | não se aplica |
| POST | `/api/estilos/compilar` | estilos | — | — | **sem tela** | não se aplica |
| GET | `/api/eu` | eu | `/`, `/acervo`, `/admin`, `/admin/acervo`, `/admin/atividade`, `/admin/auditoria`, `/admin/backup`, `/admin/categorias`, `/admin/chamados`, `/admin/grupos`, `/admin/inquilinos`, `/admin/log`, `/admin/logins`, `/admin/organizacao`, `/admin/papeis`, `/admin/tokens`, `/admin/usuarios`, `/amc/criterios-feicao`, `/amc/explicacao/{execucao_id}/{unidade_id}`, `/amc/motor`, `/amc/pareto`, `/amc/presets`, `/analise`, `/analise3d`, `/camadas/{id}/dominios`, `/camadas/{id}/formulario`, `/campo/filas`, `/campo/filas/{fila_id}`, `/campo/roteiros/{roteiro_id}`, `/cena`, `/chamados`, `/colecao`, `/coleta`, `/conexoes`, `/construtor`, `/construtor-camada`, `/conta`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/crs`, `/entrar`, `/estilo`, `/estilo-guia`, `/executar`, `/ferramenta`, `/ferramentas`, `/geocodificar`, `/imagens/{id}/ficha`, `/importacoes`, `/mapa`, `/migracao`, `/modelo/{id}`, `/modelos`, `/paineis/{id}`, `/plataforma`, `/rede/medicao/ficha`, `/redes/configuracoes`, `/redes/controladores`, `/redes/diagrama`, `/redes/fluxo`, `/redes/isolamento`, `/redes/simples`, `/redes/tracado`, `/sig`, `/simbolos`, `/sites`, `/tarefas`, `/tarefas/{job_id}`, `/temas`, `/uploads`, `/versoes`, `/videos`, `/vista-de-camada`, `/visualizar` | `web/app.js:45`<br>`web/js/acervo/acervo.js:158`<br>`web/js/amc/criterios_feicao_pagina.js:187`<br>`web/js/amc/explicacao_pagina.js:129`<br>`web/js/amc/motor_pagina.js:853`<br>`web/js/amc/presets.js:292`<br>`web/js/analise/analise.js:170`<br>`web/js/auth/conta.js:91`<br>`web/js/auth/sessao.js:60`<br>`web/js/chamados/chamados.js:184`<br>`web/js/chamados/operador.js:184`<br>`web/js/conexoes/conexoes.js:557`<br>`web/js/crs/crs.js:162`<br>`web/js/estilo/estilo.js:384`<br>`web/js/ferramentas/pagina.js:143`<br>`web/js/jobs/tarefas.js:54`<br>`web/js/migracao/migracao.js:215`<br>`web/js/temas/tela.js:402` | **coberto** | com erro |
| PUT | `/api/eu` | eu | `/conta` | `web/js/auth/conta.js:144` | **coberto** | com erro |
| POST | `/api/eu/2fa/codigos` | eu | `/conta` | `web/js/auth/conta.js:351` | **coberto** | com erro |
| POST | `/api/eu/2fa/confirmar` | eu | `/conta` | `web/js/auth/conta.js:306` | **coberto** | com erro |
| POST | `/api/eu/2fa/desativar` | eu | `/conta` | `web/js/auth/conta.js:337` | **coberto** | com erro |
| POST | `/api/eu/2fa/iniciar` | eu | `/conta` | `web/js/auth/conta.js:293` | **coberto** | com erro |
| GET | `/api/eu/convites` | eu | `/conta` | `web/js/auth/conta.js:406` | **coberto** | com erro |
| POST | `/api/eu/foto` | eu | `/conta` | `web/js/auth/conta.js:191` | **coberto** | com erro |
| DELETE | `/api/eu/foto` | eu | `/conta` | `web/js/auth/conta.js:202` | **coberto** | com erro |
| PUT | `/api/eu/senha` | eu | `/conta` | `web/js/auth/conta.js:232` | **coberto** | com erro |
| GET | `/api/eu/sessoes` | eu | `/conta` | `web/js/auth/conta.js:376` | **coberto** | com erro |
| DELETE | `/api/eu/sessoes` | eu | `/conta` | `web/js/auth/conta.js:384` | **coberto** | com erro |
| DELETE | `/api/eu/sessoes/{id}` | eu | `/conta` | `web/js/auth/conta.js:371` | **coberto** | com erro |
| GET | `/api/eventos` | log | `/admin`, `/admin/acervo`, `/admin/atividade`, `/admin/auditoria`, `/admin/grupos`, `/admin/log`, `/admin/logins`, `/admin/papeis`, `/admin/tokens`, `/admin/usuarios`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/auth/admin.js:125`<br>`web/js/auth/comum.js:67`<br>`web/js/auth/log.js:159` | **coberto** | com erro |
| GET | `/api/eventos/camadas` | vivo | `/paineis/{id}` | `web/js/vivo/assinatura.js:62` | **coberto** | com erro |
| GET | `/api/exportacoes` | exportacao | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:127` | **coberto** | com erro |
| POST | `/api/exportacoes` | exportacao | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:125` | **coberto** | com erro |
| GET | `/api/exportacoes/formatos` | exportacao | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:124`<br>`web/js/catalogo/api.js:126` | **coberto** | com erro |
| GET | `/api/exportacoes/{exportacao_id}` | exportacao | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:124`<br>`web/js/catalogo/api.js:126` | **coberto** | com erro |
| DELETE | `/api/exportacoes/{exportacao_id}` | exportacao | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:128` | **coberto** | com erro |
| GET | `/api/exportacoes/{exportacao_id}/baixar` | exportacao | — | — | **sem controle** | não se aplica |
| GET | `/api/favoritos` | favoritos | — | — | **sem controle** | não se aplica |
| PUT | `/api/favoritos/{item_id}` | favoritos | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:140` | **coberto** | com erro |
| DELETE | `/api/favoritos/{item_id}` | favoritos | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:141` | **coberto** | com erro |
| GET | `/api/ferramentas` | ferramentas | `/analise`, `/ferramentas`, `/tarefas`, `/tarefas/{job_id}` | `web/js/analise/analise.js:141`<br>`web/js/jobs/api.js:52` | **coberto** | com erro |
| POST | `/api/ferramentas/script` | ferramentas | — | — | **sem controle** | não se aplica |
| GET | `/api/ferramentas/script/{id}/execucoes` | ferramentas | — | — | **sem controle** | não se aplica |
| POST | `/api/ferramentas/script/{id}/executar` | ferramentas | `/ferramenta` | `web/js/ferramentas/pagina.js:96` | **coberto** | com erro |
| GET | `/api/ferramentas/script/{id}/formulario` | ferramentas | `/ferramenta` | `web/js/ferramentas/pagina.js:108` | **coberto** | com erro |
| POST | `/api/ferramentas/script/{id}/versao` | ferramentas | — | — | **sem controle** | não se aplica |
| GET | `/api/ferramentas/{nome}` | ferramentas | — | — | **sem controle** | não se aplica |
| POST | `/api/ferramentas/{nome}/executar` | ferramentas | `/analise`, `/ferramentas`, `/tarefas`, `/tarefas/{job_id}` | `web/js/analise/analise.js:124`<br>`web/js/jobs/api.js:53` | **coberto** | com erro |
| GET | `/api/fluxos` | fluxos | — | — | **sem tela** | não se aplica |
| POST | `/api/fluxos` | fluxos | — | — | **sem tela** | não se aplica |
| GET | `/api/fluxos/{id}` | fluxos | — | — | **sem tela** | não se aplica |
| PATCH | `/api/fluxos/{id}` | fluxos | — | — | **sem tela** | não se aplica |
| DELETE | `/api/fluxos/{id}` | fluxos | — | — | **sem tela** | não se aplica |
| GET | `/api/fluxos/{id}/eventos` | fluxos | — | — | **sem tela** | não se aplica |
| DELETE | `/api/fluxos/{id}/eventos` | fluxos | — | — | **sem tela** | não se aplica |
| POST | `/api/fluxos/{id}/simular` | fluxos | — | — | **sem tela** | não se aplica |
| GET | `/api/formularios/equivalencia` | formularios | `/coleta` | `web/js/coleta/tela.js:234` | **coberto** | com erro |
| POST | `/api/formularios/xlsform` | formularios | — | — | **sem controle** | não se aplica |
| GET | `/api/formularios/{id}` | formularios | `/coleta` | `web/js/coleta/tela.js:234` | **coberto** | com erro |
| POST | `/api/formularios/{id}/respostas` | formularios | `/coleta` | `web/js/coleta/tela.js:212` | **coberto** | com erro |
| POST | `/api/foto360` | modelo3d | `/sig` | `web/js/uploads/nucleo.js:219` | **coberto** | com erro |
| GET | `/api/foto360/{item_id}` | modelo3d | `/modelo/{id}` | `web/js/modelo3d/pagina.js:151` | **coberto** | com erro |
| GET | `/api/geocodificador/lote` | geocodificador | — | — | **sem controle** | não se aplica |
| GET | `/api/geocodificador/lote/{item_id}` | geocodificador | — | — | **sem controle** | não se aplica |
| GET | `/api/geocodificador/lote/{item_id}/pendentes` | geocodificador | — | — | **sem controle** | não se aplica |
| PATCH | `/api/geocodificador/lote/{item_id}/pendentes/{fid}` | geocodificador | — | — | **sem controle** | não se aplica |
| POST | `/api/geocodificador/lote/{item_id}/regeocodificar` | geocodificador | — | — | **sem controle** | não se aplica |
| GET | `/api/geocodificar` | geocodificador | `/sig` | `web/js/mapa/busca.js:86`<br>`web/js/sig/sig.js:275` | **coberto** | com erro |
| POST | `/api/geocodificar` | geocodificador | `/geocodificar` | `web/js/geocodificador/geocodificar.js:130` | **coberto** | com erro |
| GET | `/api/geoparquet` | geoparquet | — | — | **sem tela** | não se aplica |
| POST | `/api/geoparquet` | geoparquet | — | — | **sem tela** | não se aplica |
| GET | `/api/geoparquet/{catalogo_item_id}/arquivos` | geoparquet | — | — | **sem tela** | não se aplica |
| GET | `/api/geoparquet/{job_id}` | geoparquet | — | — | **sem tela** | não se aplica |
| GET | `/api/grupos` | grupos | `/admin`, `/admin/grupos`, `/admin/logins`, `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/auth/admin.js:72`<br>`web/js/auth/grupos.js:108`<br>`web/js/auth/logins.js:31`<br>`web/js/catalogo/api.js:149` | **coberto** | com erro |
| POST | `/api/grupos` | grupos | `/admin/grupos` | `web/js/auth/grupos.js:153` | **coberto** | com erro |
| GET | `/api/grupos/{id}` | grupos | `/admin/grupos` | `web/js/auth/grupos.js:165` | **coberto** | com erro |
| PUT | `/api/grupos/{id}` | grupos | `/admin/grupos` | `web/js/auth/grupos.js:201`<br>`web/js/auth/grupos.js:252` | **coberto** | com erro |
| DELETE | `/api/grupos/{id}` | grupos | `/admin/grupos` | `web/js/auth/grupos.js:233` | **coberto** | com erro |
| POST | `/api/grupos/{id}/aceitar` | grupos | `/admin/grupos`, `/conta` | `web/js/auth/conta.js:401`<br>`web/js/auth/grupos.js:93` | **coberto** | com erro |
| POST | `/api/grupos/{id}/entrar` | grupos | `/admin/grupos`, `/conta` | `web/js/auth/conta.js:401`<br>`web/js/auth/grupos.js:93` | **coberto** | com erro |
| GET | `/api/grupos/{id}/membros` | grupos | `/admin/grupos` | `web/js/auth/grupos.js:243`<br>`web/js/auth/grupos.js:289` | **coberto** | com erro |
| POST | `/api/grupos/{id}/membros` | grupos | `/admin/grupos`, `/conta` | `web/js/auth/conta.js:401`<br>`web/js/auth/grupos.js:310`<br>`web/js/auth/grupos.js:93` | **coberto** | com erro |
| PUT | `/api/grupos/{id}/membros/{uid}` | grupos | `/admin/grupos` | `web/js/auth/grupos.js:285` | **coberto** | com erro |
| DELETE | `/api/grupos/{id}/membros/{uid}` | grupos | `/admin/grupos` | `web/js/auth/grupos.js:221`<br>`web/js/auth/grupos.js:284` | **coberto** | com erro |
| POST | `/api/grupos/{id}/membros/{uid}/aprovar` | grupos | `/admin/grupos` | `web/js/auth/grupos.js:283` | **coberto** | com erro |
| POST | `/api/grupos/{id}/recusar` | grupos | `/admin/grupos`, `/conta` | `web/js/auth/conta.js:401`<br>`web/js/auth/grupos.js:93` | **coberto** | com erro |
| GET | `/api/imagens/formatos` | imagens | `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/uploads` | `web/js/catalogo/tipos/raster.js:37`<br>`web/js/uploads/enviar.js:60` | **coberto** | com erro |
| POST | `/api/imagens/ingestoes` | imagens | `/sig` | `web/js/uploads/nucleo.js:195` | **coberto** | com erro |
| GET | `/api/imagens/licencas` | imagens | `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/imagens/{id}/ficha` | `web/js/catalogo/tipos/raster.js:37`<br>`web/js/imagens/ficha.js:91` | **coberto** | com erro |
| POST | `/api/imagens/proveniencia/preencher-pendentes` | imagens | — | — | **sem controle** | não se aplica |
| GET | `/api/imagens/{item_id}` | imagens | `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/imagens/{id}/ficha`, `/uploads` | `web/js/catalogo/tipos/raster.js:37`<br>`web/js/imagens/ficha.js:91`<br>`web/js/uploads/enviar.js:60` | **coberto** | com erro |
| POST | `/api/imagens/{item_id}/conferir` | imagens | `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/tipos/raster.js:109` | **coberto** | com erro |
| GET | `/api/imagens/{item_id}/ficha` | imagens | `/imagens/{id}/ficha` | `web/js/imagens/ficha.js:91` | **coberto** | com erro |
| PUT | `/api/imagens/{item_id}/ficha` | imagens | `/imagens/{id}/ficha` | `web/js/imagens/ficha.js:101` | **coberto** | com erro |
| GET | `/api/imagens/{item_id}/predefinicoes` | imagens-predefinicoes | `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/tipos/raster.js:145` | **coberto** | com erro |
| POST | `/api/imagens/{item_id}/predefinicoes` | imagens-predefinicoes | — | — | **sem controle** | não se aplica |
| PUT | `/api/imagens/{item_id}/predefinicoes/{nome}` | imagens-predefinicoes | — | — | **sem controle** | não se aplica |
| DELETE | `/api/imagens/{item_id}/predefinicoes/{nome}` | imagens-predefinicoes | — | — | **sem controle** | não se aplica |
| POST | `/api/imagens/{item_id}/predefinicoes/{nome}/tornar-padrao` | imagens-predefinicoes | — | — | **sem controle** | não se aplica |
| GET | `/api/imagens/{item_id}/tiles/{z}/{x}/{y}.png` | imagens | — | — | **sem controle** | não se aplica |
| GET | `/api/importacoes` | ingestao | `/importacoes` | `web/js/ingestao/importacoes.js:95` | **coberto** | com erro |
| POST | `/api/importacoes` | ingestao | `/importacoes`, `/sig` | `web/js/ingestao/importacoes.js:220`<br>`web/js/uploads/nucleo.js:158` | **coberto** | com erro |
| GET | `/api/importacoes/formatos` | ingestao | `/importacoes`, `/sig` | `web/js/ingestao/importacoes.js:127`<br>`web/js/ingestao/importacoes.js:188`<br>`web/js/ingestao/importacoes.js:244`<br>`web/js/uploads/nucleo.js:163` | **coberto** | com erro |
| GET | `/api/importacoes/{id}` | ingestao | `/importacoes`, `/sig` | `web/js/ingestao/importacoes.js:127`<br>`web/js/ingestao/importacoes.js:188`<br>`web/js/ingestao/importacoes.js:244`<br>`web/js/uploads/nucleo.js:163` | **coberto** | com erro |
| DELETE | `/api/importacoes/{id}` | ingestao | `/importacoes` | `web/js/ingestao/importacoes.js:349` | **coberto** | com erro |
| PUT | `/api/importacoes/{id}/confirmar` | ingestao | `/importacoes`, `/sig` | `web/js/ingestao/importacoes.js:313`<br>`web/js/uploads/nucleo.js:173`<br>`web/js/uploads/nucleo.js:178` | **coberto** | com erro |
| GET | `/api/inquilino/exportacoes` | exportacao_inquilino | — | — | **sem tela** | não se aplica |
| GET | `/api/inquilino/exportacoes/{exportacao_id}` | exportacao_inquilino | — | — | **sem tela** | não se aplica |
| DELETE | `/api/inquilino/exportacoes/{exportacao_id}` | exportacao_inquilino | — | — | **sem tela** | não se aplica |
| GET | `/api/inquilino/exportacoes/{exportacao_id}/baixar` | exportacao_inquilino | — | — | **sem tela** | não se aplica |
| POST | `/api/inquilino/exportar` | exportacao_inquilino | — | — | **sem tela** | não se aplica |
| GET | `/api/inquilino/exportar/estimativa` | exportacao_inquilino | — | — | **sem tela** | não se aplica |
| GET | `/api/intercambio/exportacoes` | intercambio | — | — | **sem tela** | não se aplica |
| POST | `/api/intercambio/exportacoes` | intercambio | — | — | **sem tela** | não se aplica |
| GET | `/api/intercambio/exportacoes/{id}` | intercambio | — | — | **sem tela** | não se aplica |
| DELETE | `/api/intercambio/exportacoes/{id}` | intercambio | — | — | **sem tela** | não se aplica |
| GET | `/api/intercambio/exportacoes/{id}/baixar` | intercambio | — | — | **sem tela** | não se aplica |
| GET | `/api/intercambio/formatos` | intercambio | — | — | **sem tela** | não se aplica |
| POST | `/api/intercambio/importacoes-lote` | intercambio | — | — | **sem tela** | não se aplica |
| GET | `/api/intercambio/importacoes-lote/{lote_id}` | intercambio | — | — | **sem tela** | não se aplica |
| PUT | `/api/intercambio/importacoes-lote/{lote_id}/confirmar` | intercambio | — | — | **sem tela** | não se aplica |
| POST | `/api/isocrona` | rede | — | — | **sem tela** | não se aplica |
| GET | `/api/itens` | catalogo | `/amc/motor`, `/analise`, `/aplicativo`, `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/importacoes`, `/modelos`, `/paineis/{id}`, `/vista-de-camada` | `web/js/amc/motor_pagina.js:483`<br>`web/js/analise/analise.js:142`<br>`web/js/analise/analise.js:143`<br>`web/js/analise/analise.js:144`<br>`web/js/catalogo/api.js:75`<br>`web/js/catalogo/modelos.js:88`<br>`web/js/catalogo/vista_camada.js:33`<br>`web/js/ingestao/importacoes.js:188`<br>`web/js/widgets/base.js:166` | **coberto** | com erro |
| POST | `/api/itens` | catalogo | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:79` | **coberto** | com erro |
| GET | `/api/itens/facetas` | catalogo | `/aplicativo`, `/cena`, `/colecao`, `/construtor`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/executar`, `/paineis/{id}`, `/redes/simples`, `/sites`, `/visualizar` | `web/js/app/fontes.js:45`<br>`web/js/catalogo/api.js:64`<br>`web/js/catalogo/api.js:76`<br>`web/js/catalogo/api.js:78`<br>`web/js/catalogo/tipos/token_servico.js:41`<br>`web/js/cena/documento.js:76`<br>`web/js/colecao/tela.js:32`<br>`web/js/colecao/tela.js:43`<br>`web/js/editor/tela.js:44`<br>`web/js/executor/executar_tela.js:26`<br>`web/js/rede/simples.js:36`<br>`web/js/site/tela.js:37`<br>`web/js/visualizador/visualizador.js:47`<br>`web/js/widgets/aplicativo.js:38` | **coberto** | com erro |
| POST | `/api/itens/lote` | catalogo | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:83` | **coberto** | com erro |
| GET | `/api/itens/tags` | catalogo | `/aplicativo`, `/cena`, `/colecao`, `/construtor`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/executar`, `/paineis/{id}`, `/redes/simples`, `/sites`, `/visualizar` | `web/js/app/fontes.js:45`<br>`web/js/catalogo/api.js:64`<br>`web/js/catalogo/api.js:77`<br>`web/js/catalogo/api.js:78`<br>`web/js/catalogo/tipos/token_servico.js:41`<br>`web/js/cena/documento.js:76`<br>`web/js/colecao/tela.js:32`<br>`web/js/colecao/tela.js:43`<br>`web/js/editor/tela.js:44`<br>`web/js/executor/executar_tela.js:26`<br>`web/js/rede/simples.js:36`<br>`web/js/site/tela.js:37`<br>`web/js/visualizador/visualizador.js:47`<br>`web/js/widgets/aplicativo.js:38` | **coberto** | com erro |
| POST | `/api/itens/transferir` | catalogo | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:85` | **coberto** | com erro |
| GET | `/api/itens/{id}` | catalogo | `/aplicativo`, `/cena`, `/colecao`, `/construtor`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/executar`, `/paineis/{id}`, `/redes/simples`, `/sites`, `/visualizar` | `web/js/app/fontes.js:45`<br>`web/js/catalogo/api.js:64`<br>`web/js/catalogo/api.js:76`<br>`web/js/catalogo/api.js:77`<br>`web/js/catalogo/api.js:78`<br>`web/js/catalogo/tipos/token_servico.js:41`<br>`web/js/cena/documento.js:76`<br>`web/js/colecao/tela.js:32`<br>`web/js/colecao/tela.js:43`<br>`web/js/editor/tela.js:44`<br>`web/js/executor/executar_tela.js:26`<br>`web/js/rede/simples.js:36`<br>`web/js/site/tela.js:37`<br>`web/js/visualizador/visualizador.js:47`<br>`web/js/widgets/aplicativo.js:38` | **coberto** | com erro |
| PUT | `/api/itens/{id}` | catalogo | `/cena`, `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:80`<br>`web/js/cena/documento.js:87` | **coberto** | com erro |
| PATCH | `/api/itens/{id}` | catalogo | `/colecao`, `/construtor`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}`, `/sites` | `web/js/catalogo/api.js:81`<br>`web/js/catalogo/tipos/token_servico.js:21`<br>`web/js/editor/tela.js:108`<br>`web/js/site/tela.js:62` | **coberto** | com erro |
| DELETE | `/api/itens/{id}` | catalogo | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:82` | **coberto** | com erro |
| GET | `/api/itens/{id}/compartilhamento` | compartilhamento | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:115` | **coberto** | com erro |
| PUT | `/api/itens/{id}/compartilhamento` | compartilhamento | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:116` | **coberto** | com erro |
| GET | `/api/itens/{id}/criado-a-partir-de` | catalogo | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:110` | **coberto** | com erro |
| POST | `/api/itens/{id}/exportar` | ingestao | — | — | **sem controle** | não se aplica |
| GET | `/api/itens/{id}/integridade` | catalogo | — | — | **sem controle** | não se aplica |
| GET | `/api/itens/{id}/links` | compartilhamento | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:117` | **coberto** | com erro |
| POST | `/api/itens/{id}/links` | compartilhamento | `/colecao`, `/construtor`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:118`<br>`web/js/colecao/tela.js:74`<br>`web/js/colecao/tela.js:91`<br>`web/js/editor/tela.js:97` | **coberto** | com erro |
| DELETE | `/api/itens/{id}/links/{lid}` | compartilhamento | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:119`<br>`web/js/colecao/tela.js:73` | **coberto** | com erro |
| GET | `/api/itens/{id}/metadado` | catalogo | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:88` | **coberto** | com erro |
| PUT | `/api/itens/{id}/metadado` | catalogo | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:90` | **coberto** | com erro |
| GET | `/api/itens/{id}/metadado.xml` | catalogo | — | — | **sem controle** | não se aplica |
| POST | `/api/itens/{id}/metadado.xml` | catalogo | — | — | **sem controle** | não se aplica |
| POST | `/api/itens/{id}/metadado/validar` | catalogo | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:89` | **coberto** | com erro |
| GET | `/api/itens/{id}/miniatura` | catalogo | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:93` | **coberto** | com erro |
| POST | `/api/itens/{id}/miniatura` | catalogo | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:97` | **coberto** | com erro |
| DELETE | `/api/itens/{id}/miniatura` | catalogo | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:100` | **coberto** | com erro |
| POST | `/api/itens/{id}/miniatura/gerar` | catalogo | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:99` | **coberto** | com erro |
| POST | `/api/itens/{id}/mover` | catalogo | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:84` | **coberto** | com erro |
| GET | `/api/itens/{id}/ordem-de-exclusao` | catalogo | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:111` | **coberto** | com erro |
| GET | `/api/itens/{id}/pacote` | catalogo | — | — | **sem controle** | não se aplica |
| GET | `/api/itens/{id}/presenca` | presenca | — | — | **sem tela** | não se aplica |
| POST | `/api/itens/{id}/presenca` | presenca | — | — | **sem tela** | não se aplica |
| GET | `/api/itens/{id}/presenca/eventos` | presenca | — | — | **sem tela** | não se aplica |
| GET | `/api/itens/{id}/publicacao` | publicacao | — | — | **sem controle** | não se aplica |
| POST | `/api/itens/{id}/publicacao` | publicacao | `/construtor` | `web/js/editor/tela.js:83` | **coberto** | com erro |
| DELETE | `/api/itens/{id}/publicacao` | publicacao | — | — | **sem controle** | não se aplica |
| GET | `/api/itens/{id}/publicacao/exportacao` | publicacao | — | — | **sem controle** | não se aplica |
| GET | `/api/itens/{id}/publicacao/visualizacoes` | publicacao | — | — | **sem controle** | não se aplica |
| PUT | `/api/itens/{id}/relacoes` | catalogo | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:112` | **coberto** | com erro |
| GET | `/api/itens/{id}/site` | site | `/sites` | `web/js/site/tela.js:96` | **coberto** | com erro |
| PUT | `/api/itens/{id}/site` | site | `/sites` | `web/js/site/tela.js:101` | **coberto** | com erro |
| DELETE | `/api/itens/{id}/site` | site | `/sites` | `web/js/site/tela.js:109` | **coberto** | com erro |
| GET | `/api/itens/{id}/usado-por` | catalogo | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:109` | **coberto** | com erro |
| GET | `/api/itens/{id}/versoes` | catalogo | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:103` | **coberto** | com erro |
| GET | `/api/itens/{id}/versoes/{n}` | catalogo | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:104` | **coberto** | com erro |
| POST | `/api/itens/{id}/versoes/{n}/publicar` | catalogo | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:106` | **coberto** | com erro |
| POST | `/api/itens/{id}/versoes/{n}/restaurar` | catalogo | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:105` | **coberto** | com erro |
| POST | `/api/itens/{item_id}/paineis/fontes/{fonte_id}/dados` | paineis | — | — | **sem tela** | não se aplica |
| GET | `/api/jobs` | jobs | `/ferramentas`, `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:38` | **coberto** | com erro |
| POST | `/api/jobs` | jobs | `/admin/backup`, `/ferramentas`, `/tarefas`, `/tarefas/{job_id}` | `web/js/admin/backup.js:127`<br>`web/js/jobs/api.js:40` | **coberto** | com erro |
| GET | `/api/jobs/resumo` | jobs | `/admin/backup`, `/analise`, `/ferramenta`, `/ferramentas`, `/sig`, `/tarefas`, `/tarefas/{job_id}` | `web/js/admin/backup.js:116`<br>`web/js/analise/analise.js:107`<br>`web/js/ferramentas/pagina.js:75`<br>`web/js/jobs/api.js:39`<br>`web/js/jobs/api.js:45`<br>`web/js/mapa/edicao.js:642`<br>`web/js/uploads/nucleo.js:103` | **coberto** | com erro |
| GET | `/api/jobs/tipos` | jobs | `/admin/backup`, `/analise`, `/ferramenta`, `/ferramentas`, `/sig`, `/tarefas`, `/tarefas/{job_id}` | `web/js/admin/backup.js:116`<br>`web/js/analise/analise.js:107`<br>`web/js/ferramentas/pagina.js:75`<br>`web/js/jobs/api.js:39`<br>`web/js/jobs/api.js:46`<br>`web/js/mapa/edicao.js:642`<br>`web/js/uploads/nucleo.js:103` | **coberto** | com erro |
| GET | `/api/jobs/{job_id}` | jobs | `/admin/backup`, `/analise`, `/ferramenta`, `/ferramentas`, `/sig`, `/tarefas`, `/tarefas/{job_id}` | `web/js/admin/backup.js:116`<br>`web/js/analise/analise.js:107`<br>`web/js/ferramentas/pagina.js:75`<br>`web/js/jobs/api.js:39`<br>`web/js/jobs/api.js:45`<br>`web/js/jobs/api.js:46`<br>`web/js/mapa/edicao.js:642`<br>`web/js/uploads/nucleo.js:103` | **coberto** | com erro |
| POST | `/api/jobs/{job_id}/cancelar` | jobs | `/ferramentas`, `/sig`, `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:41`<br>`web/js/mapa/edicao.js:656` | **coberto** | com erro |
| GET | `/api/jobs/{job_id}/eventos` | jobs | `/ferramentas`, `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/eventos.js:75`<br>`web/js/jobs/eventos.js:76` | **coberto** | sem estado de erro |
| GET | `/api/jobs/{job_id}/log` | jobs | `/ferramentas`, `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:44` | **coberto** | com erro |
| POST | `/api/jobs/{job_id}/repetir` | jobs | `/ferramentas`, `/tarefas`, `/tarefas/{job_id}` | `web/js/jobs/api.js:42` | **coberto** | com erro |
| POST | `/api/layouts/exportar` | layout | — | — | **sem tela** | não se aplica |
| GET | `/api/layouts/modelos` | layout | — | — | **sem tela** | não se aplica |
| GET | `/api/layouts/modelos/{id}` | layout | — | — | **sem tela** | não se aplica |
| POST | `/api/layouts/previa` | layout | — | — | **sem tela** | não se aplica |
| POST | `/api/layouts/validar` | layout | — | — | **sem tela** | não se aplica |
| GET | `/api/lixeira` | lixeira | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:144` | **coberto** | com erro |
| POST | `/api/lixeira/esvaziar` | lixeira | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:146` | **coberto** | com erro |
| POST | `/api/lixeira/{id}/restaurar` | lixeira | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:145` | **coberto** | com erro |
| GET | `/api/log` | log | `/admin`, `/admin/log` | `web/js/auth/admin.js:100`<br>`web/js/auth/log.js:118`<br>`web/js/auth/log.js:120` | **coberto** | com erro |
| GET | `/api/log/nivel` | log | — | — | **sem controle** | não se aplica |
| POST | `/api/log/nivel` | log | — | — | **sem controle** | não se aplica |
| DELETE | `/api/log/nivel` | log | — | — | **sem controle** | não se aplica |
| POST | `/api/login` | login | `/entrar` | `web/js/auth/login.js:208` | **coberto** | com erro |
| POST | `/api/login/2fa` | login | `/entrar` | `web/js/auth/login.js:241` | **coberto** | com erro |
| POST | `/api/login/ldap` | login | `/entrar` | `web/js/auth/login.js:208` | **coberto** | com erro |
| GET | `/api/login/oidc/iniciar` | login | — | — | **sem controle** | não se aplica |
| GET | `/api/login/oidc/retorno` | login | — | — | **sem controle** | não se aplica |
| GET | `/api/login/provedores` | login | `/entrar` | `web/js/auth/login.js:107` | **coberto** | com erro |
| POST | `/api/login/saml/acs` | login | — | `callback ACS do SAML: o navegador chega aqui por um POST que o IdP monta, nunca por chamada da nossa web/` | **sem tela por desenho** | não se aplica |
| GET | `/api/login/saml/iniciar` | login | — | — | **sem controle** | não se aplica |
| GET | `/api/login/saml/metadata` | login | — | — | **sem controle** | não se aplica |
| POST | `/api/logout` | login | `/`, `/acervo`, `/admin`, `/admin/acervo`, `/admin/atividade`, `/admin/auditoria`, `/admin/backup`, `/admin/categorias`, `/admin/chamados`, `/admin/grupos`, `/admin/inquilinos`, `/admin/log`, `/admin/logins`, `/admin/organizacao`, `/admin/papeis`, `/admin/tokens`, `/admin/usuarios`, `/amc/criterios-feicao`, `/amc/explicacao/{execucao_id}/{unidade_id}`, `/amc/motor`, `/amc/pareto`, `/amc/presets`, `/analise`, `/analise3d`, `/camadas/{id}/dominios`, `/camadas/{id}/formulario`, `/campo/filas`, `/campo/filas/{fila_id}`, `/campo/roteiros/{roteiro_id}`, `/cena`, `/chamados`, `/colecao`, `/coleta`, `/conexoes`, `/construtor`, `/construtor-camada`, `/conta`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/crs`, `/entrar`, `/estilo`, `/estilo-guia`, `/executar`, `/ferramenta`, `/ferramentas`, `/geocodificar`, `/imagens/{id}/ficha`, `/importacoes`, `/mapa`, `/migracao`, `/modelo/{id}`, `/modelos`, `/paineis/{id}`, `/plataforma`, `/rede/medicao/ficha`, `/redes/configuracoes`, `/redes/controladores`, `/redes/diagrama`, `/redes/fluxo`, `/redes/isolamento`, `/redes/simples`, `/redes/tracado`, `/sig`, `/simbolos`, `/sites`, `/tarefas`, `/tarefas/{job_id}`, `/temas`, `/uploads`, `/versoes`, `/videos`, `/vista-de-camada`, `/visualizar` | `web/js/auth/sessao.js:75` | **coberto** | sem estado de erro |
| GET | `/api/mapa/camadas` | mapa | `/campo/filas`, `/construtor`, `/executar`, `/redes/simples`, `/sig`, `/versoes` | `web/js/campo/filas.js:18`<br>`web/js/mapa/catalogo.js:30`<br>`web/js/rede/simples.js:31`<br>`web/js/versoes/painel.js:44` | **coberto** | com erro |
| GET | `/api/mapa/camadas/{id}` | mapa | `/cena`, `/construtor`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/executar`, `/sig` | `web/js/catalogo/tipos/camada_vetorial.js:41`<br>`web/js/cena/camadas3d.js:95`<br>`web/js/mapa/catalogo.js:181`<br>`web/js/mapa/edicao.js:197` | **coberto** | com erro |
| GET | `/api/mapa/camadas/{id}/estilo` | mapa | — | — | **sem controle** | não se aplica |
| GET | `/api/mapa/camadas/{id}/feicoes/{fid}` | mapa | — | — | **sem controle** | não se aplica |
| POST | `/api/mapa/camadas/{id}/filtrar` | mapa | — | — | **sem controle** | não se aplica |
| POST | `/api/mapa/camadas/{id}/selecionar` | mapa | — | — | **sem controle** | não se aplica |
| GET | `/api/mapa/camadas/{id}/tilejson` | mapa | — | — | **sem controle** | não se aplica |
| GET | `/api/mapa/camadas/{id}/valores` | mapa | — | — | **sem controle** | não se aplica |
| GET | `/api/mapa/fuso` | mapa-popup | — | — | **sem controle** | não se aplica |
| POST | `/api/mapa/pacotes/importar` | mapa | — | — | **sem controle** | não se aplica |
| POST | `/api/mapa/selecao-espacial` | mapa | — | — | **sem controle** | não se aplica |
| POST | `/api/mapa/{mapa_id}/desenho/promover` | mapa | — | — | **sem controle** | não se aplica |
| GET | `/api/mapas` | mapa | `/sig` | `web/js/sig/sig.js:631`<br>`web/js/sig/sig.js:709` | **coberto** | com erro |
| POST | `/api/mapas` | mapa | `/sig` | `web/js/sig/sig.js:674` | **coberto** | com erro |
| GET | `/api/mapas-base` | mapas-base | — | — | **sem tela** | não se aplica |
| POST | `/api/mapas-base/instalar` | mapas-base | — | — | **sem tela** | não se aplica |
| GET | `/api/mapas-base/osm/{z}/{x}/{y}.png` | mapas-base | — | — | **sem tela** | não se aplica |
| POST | `/api/mapas-base/{id}/tornar-padrao` | mapas-base | — | — | **sem tela** | não se aplica |
| GET | `/api/mapas/{id}` | mapa | — | — | **sem controle** | não se aplica |
| PUT | `/api/mapas/{id}` | mapa | `/sig` | `web/js/mapa/documento.js:29`<br>`web/js/mapa/documento.js:42`<br>`web/js/sig/sig.js:700` | **coberto** | com erro |
| GET | `/api/mapas/{id}/completo` | mapa | `/sig` | `web/js/mapa/documento.js:12` | **coberto** | com erro |
| POST | `/api/matriz` | rede | — | — | **sem tela** | não se aplica |
| GET | `/api/migracao/inventarios` | migracao | `/migracao` | `web/js/migracao/migracao.js:123` | **coberto** | com erro |
| POST | `/api/migracao/inventarios` | migracao | `/migracao` | `web/js/migracao/migracao.js:95` | **coberto** | com erro |
| GET | `/api/migracao/inventarios/{id}` | migracao | `/migracao` | `web/js/migracao/migracao.js:169` | **coberto** | com erro |
| DELETE | `/api/migracao/inventarios/{id}` | migracao | — | — | **sem controle** | não se aplica |
| GET | `/api/migracao/inventarios/{id}/itens` | migracao | `/migracao` | `web/js/migracao/migracao.js:200` | **coberto** | com erro |
| GET | `/api/migracao/inventarios/{id}/relatorio.csv` | migracao | `/migracao` | `web/js/migracao/migracao.js:178` | **coberto** | com erro |
| POST | `/api/modelo3d/ingestoes` | modelo3d | `/sig` | `web/js/uploads/nucleo.js:209` | **coberto** | com erro |
| GET | `/api/modelo3d/{item_id}` | modelo3d | `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/modelo/{id}` | `web/js/catalogo/tipos/modelo3d.js:27`<br>`web/js/modelo3d/pagina.js:151` | **coberto** | com erro |
| GET | `/api/modelos` | catalogo | `/modelos` | `web/js/catalogo/modelos.js:57` | **coberto** | com erro |
| POST | `/api/modelos` | catalogo | — | — | **sem controle** | não se aplica |
| DELETE | `/api/modelos/{id}` | catalogo | `/modelos` | `web/js/catalogo/modelos.js:72` | **coberto** | com erro |
| GET | `/api/modelos/{id}/pacote` | catalogo | `/modelos` | `web/js/catalogo/modelos.js:68` | **coberto** | com erro |
| GET | `/api/modelos3d` | modelos3d | — | — | **sem controle** | não se aplica |
| POST | `/api/modelos3d` | modelos3d | — | — | **sem controle** | não se aplica |
| GET | `/api/modelos3d/{id}` | modelos3d | `/cena` | `web/js/cena/modelospainel.js:29`<br>`web/js/cena/modelospainel.js:4` | **coberto** | com erro |
| DELETE | `/api/modelos3d/{id}` | modelos3d | — | — | **sem controle** | não se aplica |
| GET | `/api/modelos3d/{id}/3dtiles/{caminho}` | modelos3d | `/cena` | `web/js/cena/modelos3d.js:229` | **coberto** | sem estado de erro |
| GET | `/api/modelos3d/{id}/elementos` | modelos3d | — | — | **sem controle** | não se aplica |
| GET | `/api/modelos3d/{id}/elementos/{guid}` | modelos3d | `/cena` | `web/js/cena/modelospainel.js:7`<br>`web/js/cena/modelospainel.js:86` | **coberto** | com erro |
| GET | `/api/modelos3d/{id}/glb` | modelos3d | `/cena` | `web/js/cena/modelos3d.js:228` | **coberto** | sem estado de erro |
| GET | `/api/modo` | modo | `/`, `/acervo`, `/admin`, `/admin/acervo`, `/admin/atividade`, `/admin/auditoria`, `/admin/backup`, `/admin/categorias`, `/admin/chamados`, `/admin/grupos`, `/admin/inquilinos`, `/admin/log`, `/admin/logins`, `/admin/organizacao`, `/admin/papeis`, `/admin/tokens`, `/admin/usuarios`, `/amc/criterios-feicao`, `/amc/explicacao/{execucao_id}/{unidade_id}`, `/amc/motor`, `/amc/pareto`, `/amc/presets`, `/analise`, `/analise3d`, `/camadas/{id}/dominios`, `/camadas/{id}/formulario`, `/campo/filas`, `/campo/filas/{fila_id}`, `/campo/roteiros/{roteiro_id}`, `/cena`, `/chamados`, `/colecao`, `/coleta`, `/conexoes`, `/construtor`, `/construtor-camada`, `/conta`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/crs`, `/entrar`, `/estilo`, `/estilo-guia`, `/executar`, `/ferramenta`, `/ferramentas`, `/geocodificar`, `/imagens/{id}/ficha`, `/importacoes`, `/mapa`, `/migracao`, `/modelo/{id}`, `/modelos`, `/paineis/{id}`, `/plataforma`, `/rede/medicao/ficha`, `/redes/configuracoes`, `/redes/controladores`, `/redes/diagrama`, `/redes/fluxo`, `/redes/isolamento`, `/redes/simples`, `/redes/tracado`, `/sig`, `/simbolos`, `/sites`, `/tarefas`, `/tarefas/{job_id}`, `/temas`, `/uploads`, `/versoes`, `/videos`, `/vista-de-camada`, `/visualizar` | `web/js/base/modo.js:12` | **coberto** | com erro |
| GET | `/api/multiescala/conjuntos` | multiescala | — | — | **sem controle** | não se aplica |
| POST | `/api/multiescala/conjuntos` | multiescala | — | — | **sem controle** | não se aplica |
| GET | `/api/multiescala/conjuntos/{id}` | multiescala | — | — | **sem controle** | não se aplica |
| DELETE | `/api/multiescala/conjuntos/{id}` | multiescala | — | — | **sem controle** | não se aplica |
| POST | `/api/multiescala/conjuntos/{id}/macro` | multiescala | — | — | **sem controle** | não se aplica |
| GET | `/api/multiescala/execucoes` | multiescala | `/amc/pareto` | `web/js/amc/pareto_tela.js:39` | **coberto** | com erro |
| GET | `/api/multiescala/execucoes/{id}` | multiescala | `/amc/pareto` | `web/js/amc/pareto_tela.js:45` | **coberto** | com erro |
| POST | `/api/multiescala/execucoes/{id}/backtest` | multiescala | — | — | **sem controle** | não se aplica |
| POST | `/api/multiescala/execucoes/{id}/corredor` | multiescala | — | — | **sem controle** | não se aplica |
| POST | `/api/multiescala/execucoes/{id}/micro` | multiescala | — | — | **sem controle** | não se aplica |
| POST | `/api/multiescala/execucoes/{id}/regioes` | multiescala | — | — | **sem controle** | não se aplica |
| GET | `/api/multiescala/fatores` | multiescala | — | — | **sem controle** | não se aplica |
| POST | `/api/multiescala/fatores` | multiescala | — | — | **sem controle** | não se aplica |
| GET | `/api/multiescala/fatores/{id}` | multiescala | — | — | **sem controle** | não se aplica |
| DELETE | `/api/multiescala/fatores/{id}` | multiescala | — | — | **sem controle** | não se aplica |
| POST | `/api/multiescala/fatores/{id}/amostras` | multiescala | — | — | **sem controle** | não se aplica |
| GET | `/api/notificacoes` | notificacoes | — | — | **sem tela** | não se aplica |
| GET | `/api/notificacoes/contagem` | notificacoes | — | — | **sem tela** | não se aplica |
| POST | `/api/notificacoes/lidas` | notificacoes | — | — | **sem tela** | não se aplica |
| DELETE | `/api/notificacoes/{id}` | notificacoes | — | — | **sem tela** | não se aplica |
| GET | `/api/objetos/{chave}` | compartilhamento | `/construtor` | `web/js/editor/paleta_narrativa.js:11` | **coberto** | sem estado de erro |
| GET | `/api/odk/pontes` | odk | — | — | **sem tela** | não se aplica |
| POST | `/api/odk/pontes` | odk | — | — | **sem tela** | não se aplica |
| GET | `/api/odk/pontes/{id}` | odk | — | — | **sem tela** | não se aplica |
| GET | `/api/odk/pontes/{id}/entidades/{dataset}` | odk | — | — | **sem tela** | não se aplica |
| POST | `/api/odk/pontes/{id}/sincronizar` | odk | — | — | **sem tela** | não se aplica |
| GET | `/api/org` | org | `/admin`, `/admin/organizacao` | `web/js/auth/admin.js:64`<br>`web/js/auth/organizacao.js:43` | **coberto** | com erro |
| PUT | `/api/org` | org | `/admin/organizacao` | `web/js/auth/organizacao.js:75` | **coberto** | com erro |
| POST | `/api/org/exportar` | ingestao | — | — | **sem controle** | não se aplica |
| GET | `/api/org/ldap` | login | `/admin`, `/admin/organizacao` | `web/js/auth/admin.js:93`<br>`web/js/auth/organizacao.js:311` | **coberto** | com erro |
| PUT | `/api/org/ldap` | login | `/admin/organizacao` | `web/js/auth/organizacao.js:372` | **coberto** | com erro |
| POST | `/api/org/ldap/importar` | login | `/admin/organizacao` | `web/js/auth/organizacao.js:406` | **coberto** | com erro |
| GET | `/api/org/logins` | logins | `/admin/logins` | `web/js/auth/logins.js:120` | **coberto** | com erro |
| PUT | `/api/org/logins/{tipo}/{id}` | logins | `/admin/logins` | `web/js/auth/logins.js:132`<br>`web/js/auth/logins.js:243` | **coberto** | com erro |
| POST | `/api/org/logo` | org | `/admin/organizacao` | `web/js/auth/organizacao.js:203` | **coberto** | com erro |
| DELETE | `/api/org/logo` | org | `/admin/organizacao` | `web/js/auth/organizacao.js:213` | **coberto** | com erro |
| GET | `/api/org/oidc` | login | — | — | **sem controle** | não se aplica |
| POST | `/api/org/oidc` | login | `/admin/logins` | `web/js/auth/logins.js:86` | **coberto** | com erro |
| PUT | `/api/org/oidc/{provedor_id}` | login | — | — | **sem controle** | não se aplica |
| DELETE | `/api/org/oidc/{provedor_id}` | login | — | — | **sem controle** | não se aplica |
| GET | `/api/org/saml` | login | — | — | **sem controle** | não se aplica |
| POST | `/api/org/saml` | login | — | — | **sem controle** | não se aplica |
| PUT | `/api/org/saml/{provedor_id}` | login | — | — | **sem controle** | não se aplica |
| DELETE | `/api/org/saml/{provedor_id}` | login | — | — | **sem controle** | não se aplica |
| GET | `/api/org/smtp` | smtp | `/admin/organizacao` | `web/js/auth/organizacao.js:226` | **coberto** | com erro |
| PUT | `/api/org/smtp` | smtp | `/admin/organizacao` | `web/js/auth/organizacao.js:254` | **coberto** | com erro |
| POST | `/api/org/smtp/testar` | smtp | `/admin/organizacao` | `web/js/auth/organizacao.js:268` | **coberto** | com erro |
| GET | `/api/org/sso/oidc` | login | — | — | **sem controle** | não se aplica |
| PUT | `/api/org/sso/oidc` | login | — | — | **sem controle** | não se aplica |
| GET | `/api/org/sso/saml` | login | — | — | **sem controle** | não se aplica |
| PUT | `/api/org/sso/saml` | login | — | — | **sem controle** | não se aplica |
| PUT | `/api/org/tema` | temas | `/temas` | `web/js/temas/tela.js:326`<br>`web/js/temas/tela.js:342` | **coberto** | com erro |
| GET | `/api/p/{inquilino}/{slug}` | publicacao | — | — | **sem controle** | não se aplica |
| POST | `/api/pacotes/importar` | catalogo | `/modelos` | `web/js/catalogo/modelos.js:131` | **coberto** | com erro |
| POST | `/api/pacotes/verificar` | catalogo | `/modelos` | `web/js/catalogo/modelos.js:96` | **coberto** | com erro |
| GET | `/api/papeis` | usuarios | `/admin`, `/admin/acervo`, `/admin/atividade`, `/admin/auditoria`, `/admin/grupos`, `/admin/log`, `/admin/logins`, `/admin/papeis`, `/admin/tokens`, `/admin/usuarios`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/auth/admin.js:75`<br>`web/js/auth/comum.js:25`<br>`web/js/auth/papeis.js:70` | **coberto** | com erro |
| POST | `/api/papeis` | usuarios | `/admin/papeis` | `web/js/auth/papeis.js:118` | **coberto** | com erro |
| PUT | `/api/papeis/{id}` | usuarios | `/admin/papeis` | `web/js/auth/papeis.js:118` | **coberto** | com erro |
| DELETE | `/api/papeis/{id}` | usuarios | `/admin/papeis` | `web/js/auth/papeis.js:58` | **coberto** | com erro |
| POST | `/api/parcelas/fabrica/analyzeByLSA` | parcelas | — | — | **sem tela** | não se aplica |
| POST | `/api/parcelas/fabrica/applyLSA` | parcelas | — | — | **sem tela** | não se aplica |
| POST | `/api/parcelas/fabrica/assignFeaturesToRecord` | parcelas | — | — | **sem tela** | não se aplica |
| POST | `/api/parcelas/fabrica/build` | parcelas | — | — | **sem tela** | não se aplica |
| POST | `/api/parcelas/fabrica/clip` | parcelas | — | — | **sem tela** | não se aplica |
| POST | `/api/parcelas/fabrica/createSeeds` | parcelas | — | — | **sem tela** | não se aplica |
| POST | `/api/parcelas/fabrica/divide` | parcelas | — | — | **sem tela** | não se aplica |
| POST | `/api/parcelas/fabrica/merge` | parcelas | — | — | **sem tela** | não se aplica |
| POST | `/api/parcelas/fabrica/reconstructFromSeeds` | parcelas | — | — | **sem tela** | não se aplica |
| POST | `/api/parcelas/qualidade` | parcelas | — | — | **sem tela** | não se aplica |
| GET | `/api/pastas` | pastas | — | — | **sem controle** | não se aplica |
| POST | `/api/pastas` | pastas | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:132` | **coberto** | com erro |
| GET | `/api/pastas/arvore` | pastas | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:131` | **coberto** | com erro |
| PUT | `/api/pastas/{id}` | pastas | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:133` | **coberto** | com erro |
| DELETE | `/api/pastas/{id}` | pastas | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:134` | **coberto** | com erro |
| GET | `/api/plataforma/chamados` | chamados | `/admin/chamados` | `web/js/chamados/operador.js:162` | **coberto** | com erro |
| GET | `/api/plataforma/chamados/{id}` | chamados | `/admin/chamados` | `web/js/chamados/operador.js:72` | **coberto** | com erro |
| GET | `/api/plataforma/chamados/{id}/anexos/{anexo_id}` | chamados | `/admin/chamados` | `web/js/chamados/operador.js:86` | **coberto** | com erro |
| POST | `/api/plataforma/chamados/{id}/comentarios` | chamados | `/admin/chamados` | `web/js/chamados/operador.js:97` | **coberto** | com erro |
| POST | `/api/plataforma/chamados/{id}/estado` | chamados | `/admin/chamados` | `web/js/chamados/operador.js:119` | **coberto** | com erro |
| GET | `/api/plataforma/inquilinos` | plataforma | `/admin/inquilinos`, `/plataforma` | `web/js/auth/inquilinos.js:63`<br>`web/js/auth/plataforma.js:74` | **coberto** | com erro |
| POST | `/api/plataforma/inquilinos` | plataforma | `/admin/inquilinos`, `/plataforma` | `web/js/auth/inquilinos.js:152`<br>`web/js/auth/plataforma.js:138` | **coberto** | com erro |
| DELETE | `/api/plataforma/inquilinos/{id}` | plataforma | `/admin/inquilinos`, `/plataforma` | `web/js/auth/inquilinos.js:111`<br>`web/js/auth/plataforma.js:97` | **coberto** | com erro |
| POST | `/api/plataforma/inquilinos/{id}/cotas` | plataforma | `/admin/inquilinos` | `web/js/auth/inquilinos.js:100` | **coberto** | com erro |
| POST | `/api/plataforma/inquilinos/{id}/reativar` | plataforma | `/admin/inquilinos`, `/plataforma` | `web/js/auth/inquilinos.js:100`<br>`web/js/auth/plataforma.js:91` | **coberto** | com erro |
| POST | `/api/plataforma/inquilinos/{id}/suspender` | plataforma | `/admin/inquilinos`, `/plataforma` | `web/js/auth/inquilinos.js:100`<br>`web/js/auth/plataforma.js:199` | **coberto** | com erro |
| GET | `/api/portal/exemplos` | portal | — | — | **sem tela** | não se aplica |
| GET | `/api/privilegios` | usuarios | `/admin/papeis`, `/conta` | `web/js/auth/conta.js:427`<br>`web/js/auth/papeis.js:26` | **coberto** | com erro |
| GET | `/api/publico/itens/{id}` | compartilhamento | — | `leitura de item público por quem recebe o link, sem sessão; a ficha do item mostra o link` | **externo sem exposição** | não se aplica |
| GET | `/api/publico/itens/{id}/miniatura` | compartilhamento | — | `leitura de item público por quem recebe o link, sem sessão; a ficha do item mostra o link` | **externo sem exposição** | não se aplica |
| GET | `/api/publico/wms/{fonte}` | mapa | — | — | **sem controle** | não se aplica |
| GET | `/api/qr.svg` | utilidades | — | — | **sem tela** | não se aplica |
| GET | `/api/rede` | rede de utilidades | `/redes/configuracoes`, `/redes/controladores`, `/redes/diagrama`, `/redes/fluxo`, `/redes/isolamento`, `/redes/tracado`, `/sig` | `web/js/rede/configuracoes.js:24`<br>`web/js/rede/controladores.js:21`<br>`web/js/rede/diagrama.js:66`<br>`web/js/rede/fluxo.js:62`<br>`web/js/rede/isolamento.js:58`<br>`web/js/rede/tracado.js:22`<br>`web/js/sig/sig.js:399`<br>`web/js/sig/sig.js:527` | **coberto** | com erro |
| POST | `/api/rede` | rede de utilidades | — | — | **sem controle** | não se aplica |
| GET | `/api/rede/consumidores/enderecos-sem-rede` | rede | — | — | **sem tela** | não se aplica |
| POST | `/api/rede/consumidores/enderecos-sem-rede` | rede | — | — | **sem tela** | não se aplica |
| POST | `/api/rede/consumidores/jusante/calcular` | rede | — | — | **sem tela** | não se aplica |
| GET | `/api/rede/consumidores/trecho/{id}` | rede | — | — | **sem tela** | não se aplica |
| GET | `/api/rede/consumidores/uc/{id}` | rede | — | — | **sem tela** | não se aplica |
| GET | `/api/rede/medicao/ativos/{ativo}` | rede_medicao | `/rede/medicao/ficha` | `web/js/rede/medicao_ficha.js:99` | **coberto** | com erro |
| PUT | `/api/rede/medicao/ativos/{ativo}` | rede_medicao | — | — | **sem controle** | não se aplica |
| GET | `/api/rede/medicao/ativos/{ativo}/serie` | rede_medicao | `/rede/medicao/ficha` | `web/js/rede/medicao_ficha.js:140` | **coberto** | com erro |
| GET | `/api/rede/medicao/ativos/{ativo}/ultimas` | rede_medicao | `/rede/medicao/ficha` | `web/js/rede/medicao_ficha.js:98` | **coberto** | com erro |
| GET | `/api/rede/medicao/grandezas` | rede_medicao | — | — | **sem controle** | não se aplica |
| GET | `/api/rede/medicao/jusante` | rede_medicao | — | — | **sem controle** | não se aplica |
| POST | `/api/rede/medicao/leituras` | rede_medicao | — | `lote de leituras de sensor/telemetria (item L4-13): publicado por script/logger de campo com escopo rede.medir, não por clique de usuário` | **sem tela por desenho** | não se aplica |
| GET | `/api/rede/pacotes` | rede de utilidades | — | — | **sem controle** | não se aplica |
| GET | `/api/rede/pacotes/{codigo}` | rede de utilidades | `/redes/configuracoes`, `/redes/controladores`, `/redes/diagrama`, `/redes/fluxo`, `/redes/tracado` | `web/js/rede/configuracoes.js:46`<br>`web/js/rede/controladores.js:44`<br>`web/js/rede/diagrama.js:213`<br>`web/js/rede/fluxo.js:80`<br>`web/js/rede/tracado.js:147` | **coberto** | com erro |
| POST | `/api/rede/simples` | rede de utilidades — rede simples | `/redes/simples` | `web/js/rede/simples.js:98` | **coberto** | com erro |
| GET | `/api/rede/{rede_id}` | rede de utilidades | — | — | **sem controle** | não se aplica |
| DELETE | `/api/rede/{rede_id}` | rede de utilidades | — | — | **sem controle** | não se aplica |
| POST | `/api/rede/{rede_id}/applyEdits` | rede de utilidades | — | — | **sem controle** | não se aplica |
| PUT | `/api/rede/{rede_id}/area_sujas/modo` | rede de utilidades | — | — | **sem controle** | não se aplica |
| GET | `/api/rede/{rede_id}/areas_sujas` | rede de utilidades | — | — | **sem controle** | não se aplica |
| GET | `/api/rede/{rede_id}/ativos` | rede de utilidades — identificadores | — | — | **sem controle** | não se aplica |
| POST | `/api/rede/{rede_id}/ativos` | rede de utilidades — identificadores | — | — | **sem controle** | não se aplica |
| GET | `/api/rede/{rede_id}/ativos/{global_id}` | rede de utilidades — identificadores | `/rede/medicao/ficha` | `web/js/rede/medicao_ficha.js:99` | **coberto** | com erro |
| PATCH | `/api/rede/{rede_id}/ativos/{global_id}` | rede de utilidades — identificadores | — | — | **sem controle** | não se aplica |
| GET | `/api/rede/{rede_id}/ativos/{global_id}/renomeacoes` | rede de utilidades — identificadores | — | — | **sem controle** | não se aplica |
| POST | `/api/rede/{rede_id}/atributos/conectividade` | rede de utilidades — atributos | — | — | **sem tela** | não se aplica |
| GET | `/api/rede/{rede_id}/atributos/discrepancias` | rede de utilidades — atributos | — | — | **sem tela** | não se aplica |
| POST | `/api/rede/{rede_id}/atributos/propagar-fase` | rede de utilidades — atributos | — | — | **sem tela** | não se aplica |
| POST | `/api/rede/{rede_id}/atributos/sincronizar` | rede de utilidades — atributos | — | — | **sem tela** | não se aplica |
| POST | `/api/rede/{rede_id}/atributos/substituicoes` | rede de utilidades — atributos | — | — | **sem tela** | não se aplica |
| GET | `/api/rede/{rede_id}/config_tracado` | rede de utilidades — configuração de traçado | `/redes/configuracoes` | `web/js/rede/configuracoes.js:46` | **coberto** | com erro |
| POST | `/api/rede/{rede_id}/config_tracado` | rede de utilidades — configuração de traçado | `/redes/configuracoes` | `web/js/rede/configuracoes.js:103` | **coberto** | com erro |
| GET | `/api/rede/{rede_id}/config_tracado/{config_id}` | rede de utilidades — configuração de traçado | — | — | **sem controle** | não se aplica |
| PUT | `/api/rede/{rede_id}/config_tracado/{config_id}` | rede de utilidades — configuração de traçado | — | — | **sem controle** | não se aplica |
| DELETE | `/api/rede/{rede_id}/config_tracado/{config_id}` | rede de utilidades — configuração de traçado | `/redes/configuracoes` | `web/js/rede/configuracoes.js:70` | **coberto** | com erro |
| POST | `/api/rede/{rede_id}/controlador` | rede de utilidades — controladores e tiers | — | — | **sem controle** | não se aplica |
| GET | `/api/rede/{rede_id}/controlador/{controlador_id}` | rede de utilidades — controladores e tiers | `/redes/controladores` | `web/js/rede/controladores.js:75` | **coberto** | com erro |
| DELETE | `/api/rede/{rede_id}/controlador/{controlador_id}` | rede de utilidades — controladores e tiers | `/redes/controladores` | `web/js/rede/controladores.js:90` | **coberto** | com erro |
| GET | `/api/rede/{rede_id}/controladores` | rede de utilidades — controladores e tiers | — | — | **sem controle** | não se aplica |
| POST | `/api/rede/{rede_id}/controladores/importar` | rede de utilidades — controladores e tiers | — | — | **sem controle** | não se aplica |
| POST | `/api/rede/{rede_id}/diagrama` | rede de utilidades — diagrama | — | — | **sem controle** | não se aplica |
| PUT | `/api/rede/{rede_id}/diagrama-modelo/{codigo}` | rede de utilidades — diagrama | — | — | **sem controle** | não se aplica |
| GET | `/api/rede/{rede_id}/diagrama-modelos` | rede de utilidades — diagrama | — | — | **sem controle** | não se aplica |
| GET | `/api/rede/{rede_id}/diagrama/{diagrama_id}` | rede de utilidades — diagrama | `/redes/diagrama` | `web/js/rede/diagrama.js:202` | **coberto** | com erro |
| DELETE | `/api/rede/{rede_id}/diagrama/{diagrama_id}` | rede de utilidades — diagrama | — | — | **sem controle** | não se aplica |
| GET | `/api/rede/{rede_id}/diagrama/{diagrama_id}/exportar` | rede de utilidades — diagrama | `/redes/diagrama` | `web/js/rede/diagrama.js:195` | **coberto** | com erro |
| POST | `/api/rede/{rede_id}/diagrama/{diagrama_id}/layout` | rede de utilidades — diagrama | `/redes/diagrama` | `web/js/rede/diagrama.js:224` | **coberto** | com erro |
| GET | `/api/rede/{rede_id}/diagramas` | rede de utilidades — diagrama | `/redes/diagrama` | `web/js/rede/diagrama.js:213` | **coberto** | com erro |
| GET | `/api/rede/{rede_id}/epanet` | rede de utilidades — EPANET | — | — | **sem tela** | não se aplica |
| POST | `/api/rede/{rede_id}/epanet` | rede de utilidades — EPANET | — | — | **sem tela** | não se aplica |
| GET | `/api/rede/{rede_id}/epanet/{importacao_id}` | rede de utilidades — EPANET | — | — | **sem tela** | não se aplica |
| GET | `/api/rede/{rede_id}/erros` | rede de utilidades | — | — | **sem controle** | não se aplica |
| GET | `/api/rede/{rede_id}/esgoto/escoamento` | rede de utilidades — gás e esgoto | — | — | **sem tela** | não se aplica |
| GET | `/api/rede/{rede_id}/faixas` | rede de utilidades — identificadores | — | — | **sem controle** | não se aplica |
| POST | `/api/rede/{rede_id}/faixas` | rede de utilidades — identificadores | — | — | **sem controle** | não se aplica |
| DELETE | `/api/rede/{rede_id}/faixas/{faixa_id}` | rede de utilidades — identificadores | — | — | **sem controle** | não se aplica |
| GET | `/api/rede/{rede_id}/feicoes/linhas` | rede de utilidades — topologia | — | — | **sem controle** | não se aplica |
| POST | `/api/rede/{rede_id}/feicoes/linhas` | rede de utilidades — topologia | — | — | **sem controle** | não se aplica |
| POST | `/api/rede/{rede_id}/feicoes/linhas/applyEdits` | rede de utilidades — topologia | — | — | **sem controle** | não se aplica |
| GET | `/api/rede/{rede_id}/feicoes/pontos` | rede de utilidades — topologia | — | — | **sem controle** | não se aplica |
| POST | `/api/rede/{rede_id}/feicoes/pontos` | rede de utilidades — topologia | — | — | **sem controle** | não se aplica |
| POST | `/api/rede/{rede_id}/feicoes/pontos/applyEdits` | rede de utilidades — topologia | — | — | **sem controle** | não se aplica |
| GET | `/api/rede/{rede_id}/gas/pressao` | rede de utilidades — gás e esgoto | — | — | **sem tela** | não se aplica |
| GET | `/api/rede/{rede_id}/importacoes` | rede de utilidades — conector OSM | — | — | **sem tela** | não se aplica |
| POST | `/api/rede/{rede_id}/importar-osm` | rede de utilidades — conector OSM | — | — | **sem tela** | não se aplica |
| POST | `/api/rede/{rede_id}/matpower` | rede de utilidades — MATPOWER | — | — | **sem tela** | não se aplica |
| GET | `/api/rede/{rede_id}/pacote` | rede de utilidades | — | — | **sem controle** | não se aplica |
| POST | `/api/rede/{rede_id}/pacote` | rede de utilidades | — | — | **sem controle** | não se aplica |
| POST | `/api/rede/{rede_id}/promover` | rede de utilidades — rede simples | — | — | **sem controle** | não se aplica |
| GET | `/api/rede/{rede_id}/regras` | rede de utilidades | — | — | **sem controle** | não se aplica |
| GET | `/api/rede/{rede_id}/regras.csv` | rede de utilidades | — | — | **sem controle** | não se aplica |
| POST | `/api/rede/{rede_id}/regras.csv` | rede de utilidades | — | — | **sem controle** | não se aplica |
| PUT | `/api/rede/{rede_id}/regras/ativacao` | rede de utilidades | — | — | **sem controle** | não se aplica |
| GET | `/api/rede/{rede_id}/simples` | rede de utilidades — rede simples | — | — | **sem controle** | não se aplica |
| GET | `/api/rede/{rede_id}/subrede/{nome}/curto` | rede de utilidades — curto-circuito e proteção | — | — | **sem tela** | não se aplica |
| POST | `/api/rede/{rede_id}/subrede/{nome}/curto` | rede de utilidades — curto-circuito e proteção | — | — | **sem tela** | não se aplica |
| GET | `/api/rede/{rede_id}/subrede/{nome}/curto/camada` | rede de utilidades — curto-circuito e proteção | — | — | **sem tela** | não se aplica |
| GET | `/api/rede/{rede_id}/subrede/{nome}/exportar` | rede de utilidades — subredes | `/redes/controladores` | `web/js/rede/controladores.js:63` | **coberto** | sem estado de erro |
| GET | `/api/rede/{rede_id}/subrede/{nome}/fluxo` | rede de utilidades — fluxo de potência | `/redes/fluxo` | `web/js/rede/fluxo.js:150` | **coberto** | com erro |
| POST | `/api/rede/{rede_id}/subrede/{nome}/fluxo` | rede de utilidades — fluxo de potência | — | — | **sem controle** | não se aplica |
| GET | `/api/rede/{rede_id}/subrede/{nome}/fluxo/camada` | rede de utilidades — fluxo de potência | — | — | **sem controle** | não se aplica |
| GET | `/api/rede/{rede_id}/subredes` | rede de utilidades — controladores e tiers | `/redes/controladores`, `/redes/fluxo` | `web/js/rede/controladores.js:44`<br>`web/js/rede/fluxo.js:80` | **coberto** | com erro |
| POST | `/api/rede/{rede_id}/subredes/atualizar` | rede de utilidades — subredes | `/redes/controladores` | `web/js/rede/controladores.js:112` | **coberto** | com erro |
| GET | `/api/rede/{rede_id}/subredes/conferencia` | rede de utilidades — subredes | — | — | **sem controle** | não se aplica |
| GET | `/api/rede/{rede_id}/subredes/resumos` | rede de utilidades — sumário por subrede | — | — | **sem tela** | não se aplica |
| POST | `/api/rede/{rede_id}/subredes/resumos/calcular` | rede de utilidades — sumário por subrede | — | — | **sem tela** | não se aplica |
| POST | `/api/rede/{rede_id}/subredes/{subrede_id}/atualizar` | rede de utilidades — controladores e tiers | `/redes/controladores` | `web/js/rede/controladores.js:83` | **coberto** | com erro |
| POST | `/api/rede/{rede_id}/teksi` | rede de utilidades — gás e esgoto | — | — | **sem tela** | não se aplica |
| PUT | `/api/rede/{rede_id}/tier/{codigo}/propagadores` | rede de utilidades — subredes | — | — | **sem controle** | não se aplica |
| GET | `/api/rede/{rede_id}/tiers` | rede de utilidades — controladores e tiers | — | — | **sem controle** | não se aplica |
| GET | `/api/rede/{rede_id}/topologia` | rede de utilidades — topologia | — | — | **sem controle** | não se aplica |
| GET | `/api/rede/{rede_id}/topologia/alcance` | rede de utilidades — topologia | — | — | **sem controle** | não se aplica |
| GET | `/api/rede/{rede_id}/topologia/areas-sujas` | rede de utilidades — topologia | — | — | **sem controle** | não se aplica |
| GET | `/api/rede/{rede_id}/topologia/arestas` | rede de utilidades — topologia | — | — | **sem controle** | não se aplica |
| POST | `/api/rede/{rede_id}/topologia/habilitar` | rede de utilidades — topologia | — | — | **sem controle** | não se aplica |
| GET | `/api/rede/{rede_id}/topologia/nos` | rede de utilidades — topologia | — | — | **sem controle** | não se aplica |
| GET | `/api/rede/{rede_id}/tracados` | rede de utilidades — resultado de traçado | `/redes/tracado` | `web/js/rede/tracado.js:147` | **coberto** | com erro |
| POST | `/api/rede/{rede_id}/tracados/{execucao_id}/repetir` | rede de utilidades — resultado de traçado | `/redes/tracado` | `web/js/rede/tracado.js:162` | **coberto** | com erro |
| GET | `/api/rede/{rede_id}/tracar` | rede de utilidades | — | — | **sem controle** | não se aplica |
| POST | `/api/rede/{rede_id}/tracar` | rede de utilidades — topologia | `/redes/isolamento`, `/redes/tracado` | `web/js/rede/isolamento.js:112`<br>`web/js/rede/tracado.js:99` | **coberto** | com erro |
| POST | `/api/rede/{rede_id}/tracar/camada` | rede de utilidades — resultado de traçado | `/redes/tracado` | `web/js/rede/tracado.js:119` | **coberto** | com erro |
| POST | `/api/rede/{rede_id}/tracar/exportar` | rede de utilidades — resultado de traçado | — | — | **sem controle** | não se aplica |
| POST | `/api/rede/{rede_id}/validar` | rede de utilidades | — | — | **sem controle** | não se aplica |
| POST | `/api/rede/{rede_id}/validar_extensao` | rede de utilidades | — | — | **sem controle** | não se aplica |
| POST | `/api/relacionamentos` | relacionamentos | — | — | **sem tela** | não se aplica |
| GET | `/api/relacionamentos/{rel_id}` | relacionamentos | — | — | **sem tela** | não se aplica |
| DELETE | `/api/relacionamentos/{rel_id}` | relacionamentos | — | — | **sem tela** | não se aplica |
| POST | `/api/relacionamentos/{rel_id}/desligar` | relacionamentos | — | — | **sem tela** | não se aplica |
| POST | `/api/relacionamentos/{rel_id}/ligar` | relacionamentos | — | — | **sem tela** | não se aplica |
| GET | `/api/relatorios` | relatorios | `/admin/atividade` | `web/js/auth/atividade.js:163` | **coberto** | com erro |
| POST | `/api/relatorios` | relatorios | `/admin/atividade` | `web/js/auth/atividade.js:142` | **coberto** | com erro |
| GET | `/api/relatorios/agendas` | relatorios | `/admin/atividade` | `web/js/auth/atividade.js:214` | **coberto** | com erro |
| POST | `/api/relatorios/agendas` | relatorios | `/admin/atividade` | `web/js/auth/atividade.js:182` | **coberto** | com erro |
| GET | `/api/relatorios/tipos` | relatorios | `/admin/atividade` | `web/js/auth/atividade.js:37` | **coberto** | com erro |
| GET | `/api/relatorios/{job_id}` | relatorios | `/admin/atividade` | `web/js/auth/atividade.js:214`<br>`web/js/auth/atividade.js:37` | **coberto** | com erro |
| GET | `/api/relatorios/{job_id}/csv` | relatorios | `/admin/atividade` | `web/js/auth/atividade.js:156` | **coberto** | com erro |
| POST | `/api/render/mapa` | render | — | — | **sem tela** | não se aplica |
| GET | `/api/render/saude` | render | — | — | **sem tela** | não se aplica |
| POST | `/api/render/token` | render | — | — | **sem tela** | não se aplica |
| GET | `/api/replicas` | replicas | — | — | **sem tela** | não se aplica |
| POST | `/api/replicas` | replicas | — | — | **sem tela** | não se aplica |
| GET | `/api/replicas/{id}` | replicas | — | — | **sem tela** | não se aplica |
| DELETE | `/api/replicas/{id}` | replicas | — | — | **sem tela** | não se aplica |
| GET | `/api/replicas/{id}/pacote` | replicas | — | — | **sem tela** | não se aplica |
| POST | `/api/replicas/{id}/sincronizar` | replicas | — | — | **sem tela** | não se aplica |
| POST | `/api/reverso` | geocodificador | `/geocodificar` | `web/js/geocodificador/geocodificar.js:199` | **coberto** | com erro |
| POST | `/api/rota` | rede | — | — | **sem tela** | não se aplica |
| POST | `/api/senha/redefinir/aplicar` | redefinicao | `/redefinir-senha` | `web/js/auth/redefinir_senha.js:62` | **coberto** | com erro |
| GET | `/api/senha/redefinir/resolver` | redefinicao | `/redefinir-senha` | `web/js/auth/redefinir_senha.js:25` | **coberto** | com erro |
| POST | `/api/senha/redefinir/solicitar` | redefinicao | `/redefinir-senha` | `web/js/auth/redefinir_senha.js:47` | **coberto** | com erro |
| GET | `/api/simbolos` | simbolos | `/simbolos` | `web/js/simbolos/galeria.js:98` | **coberto** | com erro |
| POST | `/api/simbolos` | simbolos | `/simbolos` | `web/js/simbolos/galeria.js:114` | **coberto** | com erro |
| GET | `/api/simbolos/fontes/{fontstack}/{faixa}.pbf` | simbolos | — | — | **sem controle** | não se aplica |
| GET | `/api/simbolos/sprite/{slug}.json` | simbolos | — | — | **sem controle** | não se aplica |
| GET | `/api/simbolos/sprite/{slug}.png` | simbolos | — | — | **sem controle** | não se aplica |
| GET | `/api/simbolos/sprite/{slug}@2x.json` | simbolos | — | — | **sem controle** | não se aplica |
| GET | `/api/simbolos/sprite/{slug}@2x.png` | simbolos | — | — | **sem controle** | não se aplica |
| GET | `/api/sso/oidc/iniciar` | login | — | — | **sem controle** | não se aplica |
| GET | `/api/sso/oidc/logout` | login | — | — | **sem controle** | não se aplica |
| GET | `/api/sso/oidc/retorno` | login | — | — | **sem controle** | não se aplica |
| POST | `/api/sso/saml/acs` | login | — | `callback ACS do SAML (SSO por organização): idem — POST montado pelo IdP` | **sem tela por desenho** | não se aplica |
| GET | `/api/sso/saml/iniciar` | login | — | — | **sem controle** | não se aplica |
| GET | `/api/sso/saml/logout` | login | — | — | **sem controle** | não se aplica |
| GET | `/api/sso/saml/metadata` | login | — | — | **sem controle** | não se aplica |
| GET | `/api/sso/saml/slo` | login | — | `callback de Single Logout do SAML: POST montado pelo IdP, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| POST | `/api/sso/saml/slo` | login | — | `callback de Single Logout do SAML: POST montado pelo IdP, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| GET | `/api/status` | status | `/status` | `web/js/status.js:144` | **coberto** | com erro |
| GET | `/api/sugerir` | geocodificador | `/sig` | `web/js/mapa/busca.js:78`<br>`web/js/sig/sig.js:275` | **coberto** | com erro |
| GET | `/api/telemetria` | telemetria | — | — | **sem tela** | não se aplica |
| PUT | `/api/telemetria` | telemetria | — | — | **sem tela** | não se aplica |
| GET | `/api/telemetria/appliances` | telemetria | — | — | **sem tela** | não se aplica |
| POST | `/api/telemetria/appliances` | telemetria | — | — | **sem tela** | não se aplica |
| DELETE | `/api/telemetria/appliances/{chave}` | telemetria | — | — | **sem tela** | não se aplica |
| POST | `/api/telemetria/enviar` | telemetria | — | — | **sem tela** | não se aplica |
| POST | `/api/telemetria/receber` | telemetria | — | `receptor de telemetria do appliance (item L7-11-c): outra instância da própria aplicação publica aqui com chave própria, x-privilegio publico — não há sessão de usuário no meio` | **sem tela por desenho** | não se aplica |
| GET | `/api/temas` | temas | `/temas` | `web/js/temas/temas.js:16` | **coberto** | com erro |
| GET | `/api/tiles/leituras` | tiles | — | — | **sem controle** | não se aplica |
| GET | `/api/tipos-item` | catalogo | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:72` | **coberto** | com erro |
| GET | `/api/tokens` | tokens | `/admin`, `/admin/log`, `/admin/tokens` | `web/js/auth/admin.js:78`<br>`web/js/auth/log.js:36`<br>`web/js/auth/tokens.js:92` | **coberto** | com erro |
| POST | `/api/tokens` | tokens | `/admin/tokens`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/ferramentas`, `/sig`, `/uploads` | `web/js/auth/tokens.js:163`<br>`web/js/catalogo/tipos/token_servico.js:28`<br>`web/js/jobs/ferramentas.js:427`<br>`web/js/uploads/enviar.js:26`<br>`web/js/uploads/nucleo.js:32` | **coberto** | com erro |
| GET | `/api/tokens/{id}` | tokens | `/admin/tokens` | `web/js/auth/tokens.js:200` | **coberto** | com erro |
| DELETE | `/api/tokens/{id}` | tokens | `/admin/tokens` | `web/js/auth/tokens.js:132` | **coberto** | com erro |
| GET | `/api/tokens/{id}/log` | tokens | `/admin/tokens` | `web/js/auth/tokens.js:194` | **coberto** | com erro |
| POST | `/api/tokens/{id}/renovar` | tokens | `/admin/tokens`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/auth/tokens.js:123`<br>`web/js/catalogo/tipos/token_servico.js:68` | **coberto** | com erro |
| POST | `/api/uploads` | uploads | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}`, `/sig`, `/uploads` | `web/js/catalogo/api.js:153`<br>`web/js/uploads/enviar.js:190`<br>`web/js/uploads/nucleo.js:64` | **coberto** | com erro |
| GET | `/api/uploads/tipos` | uploads | `/sig`, `/uploads` | `web/js/sig/sig.js:553`<br>`web/js/uploads/enviar.js:132`<br>`web/js/uploads/enviar.js:55`<br>`web/js/uploads/nucleo.js:52`<br>`web/js/uploads/nucleo.js:58` | **coberto** | com erro |
| GET | `/api/uploads/{id}` | uploads | `/sig`, `/uploads` | `web/js/sig/sig.js:553`<br>`web/js/uploads/enviar.js:132`<br>`web/js/uploads/enviar.js:55`<br>`web/js/uploads/nucleo.js:52`<br>`web/js/uploads/nucleo.js:58` | **coberto** | com erro |
| DELETE | `/api/uploads/{id}` | uploads | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:156` | **coberto** | com erro |
| POST | `/api/uploads/{id}/concluir` | uploads | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:155` | **coberto** | com erro |
| PUT | `/api/uploads/{id}/partes/{n}` | uploads | `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/catalogo/api.js:154` | **coberto** | com erro |
| GET | `/api/usuarios` | usuarios | `/admin`, `/admin/auditoria`, `/admin/grupos`, `/admin/log`, `/admin/usuarios`, `/colecao`, `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}`, `/paineis/{id}` | `web/js/auth/admin.js:65`<br>`web/js/auth/auditoria.js:38`<br>`web/js/auth/grupos.js:302`<br>`web/js/auth/log.js:35`<br>`web/js/auth/usuarios.js:106`<br>`web/js/catalogo/api.js:150` | **coberto** | com erro |
| POST | `/api/usuarios` | usuarios | `/admin/usuarios` | `web/js/auth/usuarios.js:268` | **coberto** | com erro |
| POST | `/api/usuarios/lote` | usuarios | `/admin/usuarios` | `web/js/auth/usuarios.js:144` | **coberto** | com erro |
| GET | `/api/usuarios/{id}` | usuarios | `/admin/usuarios` | `web/js/auth/usuarios.js:214` | **coberto** | com erro |
| PUT | `/api/usuarios/{id}` | usuarios | `/admin/usuarios` | `web/js/auth/usuarios.js:179`<br>`web/js/auth/usuarios.js:268` | **coberto** | com erro |
| DELETE | `/api/usuarios/{id}` | usuarios | `/admin/usuarios` | `web/js/auth/usuarios.js:185` | **coberto** | com erro |
| POST | `/api/usuarios/{id}/2fa/desativar` | usuarios | `/admin/usuarios` | `web/js/auth/usuarios.js:169` | **coberto** | com erro |
| POST | `/api/usuarios/{id}/desbloquear` | usuarios | `/admin/usuarios` | `web/js/auth/usuarios.js:174` | **coberto** | com erro |
| POST | `/api/usuarios/{id}/desregistrar` | logins | — | — | **sem controle** | não se aplica |
| POST | `/api/usuarios/{id}/senha` | usuarios | `/admin/usuarios` | `web/js/auth/usuarios.js:161` | **coberto** | com erro |
| GET | `/api/versao` | versao | `/` | `web/app.js:16` | **coberto** | com erro |
| GET | `/api/videos` | videos | `/videos` | `web/js/videos.js:20` | **coberto** | com erro |
| GET | `/api/vistas/{vista_id}` | vista-de-camada | `/vista-de-camada` | `web/js/catalogo/vista_camada.js:117` | **coberto** | com erro |
| PUT | `/api/vistas/{vista_id}` | vista-de-camada | — | — | **sem controle** | não se aplica |
| GET | `/api/webhooks` | webhooks | — | — | **sem tela** | não se aplica |
| POST | `/api/webhooks` | webhooks | — | — | **sem tela** | não se aplica |
| GET | `/api/webhooks/{id}` | webhooks | — | — | **sem tela** | não se aplica |
| PATCH | `/api/webhooks/{id}` | webhooks | — | — | **sem tela** | não se aplica |
| DELETE | `/api/webhooks/{id}` | webhooks | — | — | **sem tela** | não se aplica |
| GET | `/api/webhooks/{id}/entregas` | webhooks | — | — | **sem tela** | não se aplica |
| POST | `/api/webhooks/{id}/entregas/{entrega_id}/reenviar` | webhooks | — | — | **sem tela** | não se aplica |
| POST | `/api/webhooks/{id}/reativar` | webhooks | — | — | **sem tela** | não se aplica |
| POST | `/api/webhooks/{id}/rotacionar` | webhooks | — | — | **sem tela** | não se aplica |
| GET | `/api/widgets/externos` | widgets | `/aplicativo` | `web/js/widgets/externos.js:50` | **coberto** | com erro |
| POST | `/api/widgets/externos` | widgets | — | — | **sem controle** | não se aplica |
| GET | `/api/widgets/externos/{nome}` | widgets | — | — | **sem controle** | não se aplica |
| DELETE | `/api/widgets/externos/{nome}` | widgets | — | — | **sem controle** | não se aplica |
| GET | `/api/widgets/externos/{nome}/i18n.json` | widgets | `/aplicativo` | `web/js/widgets/externos.js:32` | **coberto** | com erro |
| GET | `/api/widgets/externos/{nome}/modulo.js` | widgets | `/aplicativo`, `/executar` | `web/js/widgets/externos.js:21`<br>`web/js/widgets/externos.js:63`<br>`web/js/widgets/registro.js:272` | **coberto** | com erro |
| GET | `/csw` | csw | — | — | **sem tela** | não se aplica |
| GET | `/notebooks/{slug}` | notebooks | — | `proxy transparente para o Jupyter do inquilino (item L2-16-b): a UI é a própria interface do Jupyter dentro do iframe, não uma tela nossa em web/ — nunca vai haver chamador nosso para este prefixo` | **sem tela por desenho** | não se aplica |
| GET | `/notebooks/{slug}/` | notebooks | — | `proxy transparente para o Jupyter do inquilino (item L2-16-b): a UI é a própria interface do Jupyter dentro do iframe, não uma tela nossa em web/ — nunca vai haver chamador nosso para este prefixo` | **sem tela por desenho** | não se aplica |
| GET | `/notebooks/{slug}/{caminho}` | notebooks | — | `proxy transparente para o Jupyter do inquilino (item L2-16-b): a UI é a própria interface do Jupyter dentro do iframe, não uma tela nossa em web/ — nunca vai haver chamador nosso para este prefixo` | **sem tela por desenho** | não se aplica |
| POST | `/notebooks/{slug}/{caminho}` | notebooks | — | `proxy transparente para o Jupyter do inquilino (item L2-16-b): a UI é a própria interface do Jupyter dentro do iframe, não uma tela nossa em web/ — nunca vai haver chamador nosso para este prefixo` | **sem tela por desenho** | não se aplica |
| PUT | `/notebooks/{slug}/{caminho}` | notebooks | — | `proxy transparente para o Jupyter do inquilino (item L2-16-b): a UI é a própria interface do Jupyter dentro do iframe, não uma tela nossa em web/ — nunca vai haver chamador nosso para este prefixo` | **sem tela por desenho** | não se aplica |
| PATCH | `/notebooks/{slug}/{caminho}` | notebooks | — | `proxy transparente para o Jupyter do inquilino (item L2-16-b): a UI é a própria interface do Jupyter dentro do iframe, não uma tela nossa em web/ — nunca vai haver chamador nosso para este prefixo` | **sem tela por desenho** | não se aplica |
| DELETE | `/notebooks/{slug}/{caminho}` | notebooks | — | `proxy transparente para o Jupyter do inquilino (item L2-16-b): a UI é a própria interface do Jupyter dentro do iframe, não uma tela nossa em web/ — nunca vai haver chamador nosso para este prefixo` | **sem tela por desenho** | não se aplica |
| GET | `/ogc/features/{item_id}` | ogc-features | — | `OGC API Features (edição WFS-T) para QGIS/cliente OGC; a ficha da camada vetorial (web/js/catalogo/tipos/camada_vetorial.js) e a tela de tokens mostram a URL` | **externo** | não se aplica |
| GET | `/ogc/features/{item_id}/api` | ogc-features | — | `OGC API Features (edição WFS-T) para QGIS/cliente OGC; a ficha da camada vetorial (web/js/catalogo/tipos/camada_vetorial.js) e a tela de tokens mostram a URL` | **externo** | não se aplica |
| GET | `/ogc/features/{item_id}/collections` | ogc-features | — | `OGC API Features (edição WFS-T) para QGIS/cliente OGC; a ficha da camada vetorial (web/js/catalogo/tipos/camada_vetorial.js) e a tela de tokens mostram a URL` | **externo** | não se aplica |
| GET | `/ogc/features/{item_id}/collections/{colecao_id}` | ogc-features | — | `OGC API Features (edição WFS-T) para QGIS/cliente OGC; a ficha da camada vetorial (web/js/catalogo/tipos/camada_vetorial.js) e a tela de tokens mostram a URL` | **externo** | não se aplica |
| GET | `/ogc/features/{item_id}/collections/{colecao_id}/items` | ogc-features | — | `OGC API Features (edição WFS-T) para QGIS/cliente OGC; a ficha da camada vetorial (web/js/catalogo/tipos/camada_vetorial.js) e a tela de tokens mostram a URL` | **externo** | não se aplica |
| POST | `/ogc/features/{item_id}/collections/{colecao_id}/items` | ogc-features | — | `OGC API Features (edição WFS-T) para QGIS/cliente OGC; a ficha da camada vetorial (web/js/catalogo/tipos/camada_vetorial.js) e a tela de tokens mostram a URL` | **externo** | não se aplica |
| GET | `/ogc/features/{item_id}/collections/{colecao_id}/items/{feature_id}` | ogc-features | — | `OGC API Features (edição WFS-T) para QGIS/cliente OGC; a ficha da camada vetorial (web/js/catalogo/tipos/camada_vetorial.js) e a tela de tokens mostram a URL` | **externo** | não se aplica |
| PUT | `/ogc/features/{item_id}/collections/{colecao_id}/items/{feature_id}` | ogc-features | — | `OGC API Features (edição WFS-T) para QGIS/cliente OGC; a ficha da camada vetorial (web/js/catalogo/tipos/camada_vetorial.js) e a tela de tokens mostram a URL` | **externo** | não se aplica |
| PATCH | `/ogc/features/{item_id}/collections/{colecao_id}/items/{feature_id}` | ogc-features | — | `OGC API Features (edição WFS-T) para QGIS/cliente OGC; a ficha da camada vetorial (web/js/catalogo/tipos/camada_vetorial.js) e a tela de tokens mostram a URL` | **externo** | não se aplica |
| DELETE | `/ogc/features/{item_id}/collections/{colecao_id}/items/{feature_id}` | ogc-features | — | `OGC API Features (edição WFS-T) para QGIS/cliente OGC; a ficha da camada vetorial (web/js/catalogo/tipos/camada_vetorial.js) e a tela de tokens mostram a URL` | **externo** | não se aplica |
| GET | `/ogc/features/{item_id}/collections/{colecao_id}/queryables` | ogc-features | — | `OGC API Features (edição WFS-T) para QGIS/cliente OGC; a ficha da camada vetorial (web/js/catalogo/tipos/camada_vetorial.js) e a tela de tokens mostram a URL` | **externo** | não se aplica |
| GET | `/ogc/features/{item_id}/conformance` | ogc-features | — | `OGC API Features (edição WFS-T) para QGIS/cliente OGC; a ficha da camada vetorial (web/js/catalogo/tipos/camada_vetorial.js) e a tela de tokens mostram a URL` | **externo** | não se aplica |
| GET | `/ogc/records` | ogc-records | `/admin/tokens` | `web/js/auth/tokens.js:214` | **coberto** | sem estado de erro |
| GET | `/ogc/records/collections` | ogc-records | — | `OGC API Records para catálogos externos (token catalogo:ler); a ficha do item ou a tela de tokens deve mostrar a URL` | **externo** | não se aplica |
| GET | `/ogc/records/collections/{colecao_id}` | ogc-records | — | `OGC API Records para catálogos externos (token catalogo:ler); a ficha do item ou a tela de tokens deve mostrar a URL` | **externo** | não se aplica |
| GET | `/ogc/records/collections/{colecao_id}/items` | ogc-records | — | `OGC API Records para catálogos externos (token catalogo:ler); a ficha do item ou a tela de tokens deve mostrar a URL` | **externo** | não se aplica |
| GET | `/ogc/records/collections/{colecao_id}/items/{item_id}` | ogc-records | — | `OGC API Records para catálogos externos (token catalogo:ler); a ficha do item ou a tela de tokens deve mostrar a URL` | **externo** | não se aplica |
| GET | `/ogc/records/conformance` | ogc-records | — | `OGC API Records para catálogos externos (token catalogo:ler); a ficha do item ou a tela de tokens deve mostrar a URL` | **externo** | não se aplica |
| GET | `/rest/services/Geocodificador/GeocodeServer` | geocodificador-esri | `/admin/tokens`, `/geocodificar` | `web/js/auth/tokens.js:212`<br>`web/js/geocodificador/geocodificar.js:27` | **coberto** | com erro |
| POST | `/rest/services/Geocodificador/GeocodeServer` | geocodificador-esri | `/geocodificar` | `web/js/geocodificador/geocodificar.js:289` | **coberto** | sem estado de erro |
| GET | `/rest/services/Geocodificador/GeocodeServer/findAddressCandidates` | geocodificador-esri | — | `GeocodeServer compatível com Esri, consumido por Pro/AGOL; a tela de tokens deve mostrar a URL` | **externo** | não se aplica |
| POST | `/rest/services/Geocodificador/GeocodeServer/findAddressCandidates` | geocodificador-esri | `/geocodificar` | `web/js/geocodificador/geocodificar.js:300` | **coberto** | sem estado de erro |
| POST | `/rest/services/Geocodificador/GeocodeServer/geocodeAddresses` | geocodificador-esri | `/geocodificar` | `web/js/geocodificador/geocodificar.js:333` | **coberto** | com erro |
| GET | `/rest/services/Geocodificador/GeocodeServer/reverseGeocode` | geocodificador-esri | — | `GeocodeServer compatível com Esri, consumido por Pro/AGOL; a tela de tokens deve mostrar a URL` | **externo** | não se aplica |
| POST | `/rest/services/Geocodificador/GeocodeServer/reverseGeocode` | geocodificador-esri | `/geocodificar` | `web/js/geocodificador/geocodificar.js:318` | **coberto** | com erro |
| GET | `/rest/services/Geocodificador/GeocodeServer/suggest` | geocodificador-esri | — | `GeocodeServer compatível com Esri, consumido por Pro/AGOL; a tela de tokens deve mostrar a URL` | **externo** | não se aplica |
| GET | `/rest/services/{ferramenta}/GPServer` | ferramentas-esri | — | — | **sem controle** | não se aplica |
| GET | `/rest/services/{ferramenta}/GPServer/{tarefa}` | ferramentas-esri | — | — | **sem controle** | não se aplica |
| GET | `/rest/services/{ferramenta}/GPServer/{tarefa}/execute` | ferramentas-esri | — | — | **sem controle** | não se aplica |
| POST | `/rest/services/{ferramenta}/GPServer/{tarefa}/execute` | ferramentas-esri | `/ferramentas` | `web/js/jobs/ferramentas.js:485` | **coberto** | com erro |
| GET | `/rest/services/{ferramenta}/GPServer/{tarefa}/jobs/{job_id}` | ferramentas-esri | — | — | **sem controle** | não se aplica |
| GET | `/rest/services/{ferramenta}/GPServer/{tarefa}/jobs/{job_id}/cancel` | ferramentas-esri | — | — | **sem controle** | não se aplica |
| POST | `/rest/services/{ferramenta}/GPServer/{tarefa}/jobs/{job_id}/cancel` | ferramentas-esri | `/ferramentas` | `web/js/jobs/ferramentas.js:496` | **coberto** | com erro |
| GET | `/rest/services/{ferramenta}/GPServer/{tarefa}/jobs/{job_id}/results/{parametro}` | ferramentas-esri | — | — | **sem controle** | não se aplica |
| GET | `/rest/services/{ferramenta}/GPServer/{tarefa}/submitJob` | ferramentas-esri | — | — | **sem controle** | não se aplica |
| POST | `/rest/services/{ferramenta}/GPServer/{tarefa}/submitJob` | ferramentas-esri | `/ferramentas` | `web/js/jobs/ferramentas.js:471` | **coberto** | com erro |
| GET | `/rest/services/{item_id}/FeatureServer` | consulta-esri | — | `protocolo FeatureServer da Esri (query/applyEdits/addFeatures/anexos/replica) consumido DIRETO por ArcGIS Pro/Field Maps/AGOL depois que o usuário cola a URL do serviço (mostrada na ficha da camada); não há operação individual para virar botão nosso` | **sem tela por desenho** | não se aplica |
| GET | `/rest/services/{item_id}/FeatureServer/0/queryRelatedRecords` | relacionamentos | — | `protocolo FeatureServer da Esri (query/applyEdits/addFeatures/anexos/replica) consumido DIRETO por ArcGIS Pro/Field Maps/AGOL depois que o usuário cola a URL do serviço (mostrada na ficha da camada); não há operação individual para virar botão nosso` | **sem tela por desenho** | não se aplica |
| POST | `/rest/services/{item_id}/FeatureServer/applyEdits` | edicao-esri | — | `protocolo FeatureServer da Esri (query/applyEdits/addFeatures/anexos/replica) consumido DIRETO por ArcGIS Pro/Field Maps/AGOL depois que o usuário cola a URL do serviço (mostrada na ficha da camada); não há operação individual para virar botão nosso` | **sem tela por desenho** | não se aplica |
| POST | `/rest/services/{item_id}/FeatureServer/createReplica` | replicas-esri | — | `protocolo FeatureServer da Esri (query/applyEdits/addFeatures/anexos/replica) consumido DIRETO por ArcGIS Pro/Field Maps/AGOL depois que o usuário cola a URL do serviço (mostrada na ficha da camada); não há operação individual para virar botão nosso` | **sem tela por desenho** | não se aplica |
| POST | `/rest/services/{item_id}/FeatureServer/extractChanges` | replicas-esri | — | `protocolo FeatureServer da Esri (query/applyEdits/addFeatures/anexos/replica) consumido DIRETO por ArcGIS Pro/Field Maps/AGOL depois que o usuário cola a URL do serviço (mostrada na ficha da camada); não há operação individual para virar botão nosso` | **sem tela por desenho** | não se aplica |
| GET | `/rest/services/{item_id}/FeatureServer/jobs/{job_id}` | replicas-esri | — | `protocolo FeatureServer da Esri (query/applyEdits/addFeatures/anexos/replica) consumido DIRETO por ArcGIS Pro/Field Maps/AGOL depois que o usuário cola a URL do serviço (mostrada na ficha da camada); não há operação individual para virar botão nosso` | **sem tela por desenho** | não se aplica |
| GET | `/rest/services/{item_id}/FeatureServer/replicas` | replicas-esri | `/aplicativo`, `/executar` | `web/js/app/consulta.js:143` | **coberto** | com erro |
| GET | `/rest/services/{item_id}/FeatureServer/replicas/{replica_id}` | replicas-esri | — | `protocolo FeatureServer da Esri (query/applyEdits/addFeatures/anexos/replica) consumido DIRETO por ArcGIS Pro/Field Maps/AGOL depois que o usuário cola a URL do serviço (mostrada na ficha da camada); não há operação individual para virar botão nosso` | **sem tela por desenho** | não se aplica |
| GET | `/rest/services/{item_id}/FeatureServer/replicas/{replica_id}/pacote` | replicas-esri | — | `protocolo FeatureServer da Esri (query/applyEdits/addFeatures/anexos/replica) consumido DIRETO por ArcGIS Pro/Field Maps/AGOL depois que o usuário cola a URL do serviço (mostrada na ficha da camada); não há operação individual para virar botão nosso` | **sem tela por desenho** | não se aplica |
| POST | `/rest/services/{item_id}/FeatureServer/synchronizeReplica` | replicas-esri | — | `protocolo FeatureServer da Esri (query/applyEdits/addFeatures/anexos/replica) consumido DIRETO por ArcGIS Pro/Field Maps/AGOL depois que o usuário cola a URL do serviço (mostrada na ficha da camada); não há operação individual para virar botão nosso` | **sem tela por desenho** | não se aplica |
| POST | `/rest/services/{item_id}/FeatureServer/unRegisterReplica` | replicas-esri | — | `protocolo FeatureServer da Esri (query/applyEdits/addFeatures/anexos/replica) consumido DIRETO por ArcGIS Pro/Field Maps/AGOL depois que o usuário cola a URL do serviço (mostrada na ficha da camada); não há operação individual para virar botão nosso` | **sem tela por desenho** | não se aplica |
| POST | `/rest/services/{item_id}/FeatureServer/uploads/upload` | edicao-esri | — | `protocolo FeatureServer da Esri (query/applyEdits/addFeatures/anexos/replica) consumido DIRETO por ArcGIS Pro/Field Maps/AGOL depois que o usuário cola a URL do serviço (mostrada na ficha da camada); não há operação individual para virar botão nosso` | **sem tela por desenho** | não se aplica |
| GET | `/rest/services/{item_id}/FeatureServer/{camada_id}` | consulta-esri | `/aplicativo`, `/executar` | `web/js/app/consulta.js:143` | **coberto** | com erro |
| POST | `/rest/services/{item_id}/FeatureServer/{camada_id}/addFeatures` | edicao-esri | — | `protocolo FeatureServer da Esri (query/applyEdits/addFeatures/anexos/replica) consumido DIRETO por ArcGIS Pro/Field Maps/AGOL depois que o usuário cola a URL do serviço (mostrada na ficha da camada); não há operação individual para virar botão nosso` | **sem tela por desenho** | não se aplica |
| POST | `/rest/services/{item_id}/FeatureServer/{camada_id}/applyEdits` | edicao-esri | — | `protocolo FeatureServer da Esri (query/applyEdits/addFeatures/anexos/replica) consumido DIRETO por ArcGIS Pro/Field Maps/AGOL depois que o usuário cola a URL do serviço (mostrada na ficha da camada); não há operação individual para virar botão nosso` | **sem tela por desenho** | não se aplica |
| POST | `/rest/services/{item_id}/FeatureServer/{camada_id}/calculate` | edicao-esri | — | `protocolo FeatureServer da Esri (query/applyEdits/addFeatures/anexos/replica) consumido DIRETO por ArcGIS Pro/Field Maps/AGOL depois que o usuário cola a URL do serviço (mostrada na ficha da camada); não há operação individual para virar botão nosso` | **sem tela por desenho** | não se aplica |
| POST | `/rest/services/{item_id}/FeatureServer/{camada_id}/deleteFeatures` | edicao-esri | — | `protocolo FeatureServer da Esri (query/applyEdits/addFeatures/anexos/replica) consumido DIRETO por ArcGIS Pro/Field Maps/AGOL depois que o usuário cola a URL do serviço (mostrada na ficha da camada); não há operação individual para virar botão nosso` | **sem tela por desenho** | não se aplica |
| GET | `/rest/services/{item_id}/FeatureServer/{camada_id}/query` | consulta-esri | `/aplicativo`, `/executar`, `/sig` | `web/js/app/consulta.js:4`<br>`web/js/mapa/tabela_atributos.js:27`<br>`web/js/sig/comparar.js:279`<br>`web/js/sig/comparar.js:322` | **coberto** | com erro |
| POST | `/rest/services/{item_id}/FeatureServer/{camada_id}/query` | consulta-esri | — | `protocolo FeatureServer da Esri (query/applyEdits/addFeatures/anexos/replica) consumido DIRETO por ArcGIS Pro/Field Maps/AGOL depois que o usuário cola a URL do serviço (mostrada na ficha da camada); não há operação individual para virar botão nosso` | **sem tela por desenho** | não se aplica |
| GET | `/rest/services/{item_id}/FeatureServer/{camada_id}/queryAttachments` | edicao-esri | — | `protocolo FeatureServer da Esri (query/applyEdits/addFeatures/anexos/replica) consumido DIRETO por ArcGIS Pro/Field Maps/AGOL depois que o usuário cola a URL do serviço (mostrada na ficha da camada); não há operação individual para virar botão nosso` | **sem tela por desenho** | não se aplica |
| POST | `/rest/services/{item_id}/FeatureServer/{camada_id}/queryAttachments` | edicao-esri | — | `protocolo FeatureServer da Esri (query/applyEdits/addFeatures/anexos/replica) consumido DIRETO por ArcGIS Pro/Field Maps/AGOL depois que o usuário cola a URL do serviço (mostrada na ficha da camada); não há operação individual para virar botão nosso` | **sem tela por desenho** | não se aplica |
| POST | `/rest/services/{item_id}/FeatureServer/{camada_id}/updateFeatures` | edicao-esri | — | `protocolo FeatureServer da Esri (query/applyEdits/addFeatures/anexos/replica) consumido DIRETO por ArcGIS Pro/Field Maps/AGOL depois que o usuário cola a URL do serviço (mostrada na ficha da camada); não há operação individual para virar botão nosso` | **sem tela por desenho** | não se aplica |
| POST | `/rest/services/{item_id}/FeatureServer/{camada_id}/{object_id}/addAttachment` | edicao-esri | — | `protocolo FeatureServer da Esri (query/applyEdits/addFeatures/anexos/replica) consumido DIRETO por ArcGIS Pro/Field Maps/AGOL depois que o usuário cola a URL do serviço (mostrada na ficha da camada); não há operação individual para virar botão nosso` | **sem tela por desenho** | não se aplica |
| GET | `/rest/services/{item_id}/FeatureServer/{camada_id}/{object_id}/attachments` | edicao-esri | — | `protocolo FeatureServer da Esri (query/applyEdits/addFeatures/anexos/replica) consumido DIRETO por ArcGIS Pro/Field Maps/AGOL depois que o usuário cola a URL do serviço (mostrada na ficha da camada); não há operação individual para virar botão nosso` | **sem tela por desenho** | não se aplica |
| GET | `/rest/services/{item_id}/FeatureServer/{camada_id}/{object_id}/attachments/{anexo_numero}` | edicao-esri | — | `protocolo FeatureServer da Esri (query/applyEdits/addFeatures/anexos/replica) consumido DIRETO por ArcGIS Pro/Field Maps/AGOL depois que o usuário cola a URL do serviço (mostrada na ficha da camada); não há operação individual para virar botão nosso` | **sem tela por desenho** | não se aplica |
| POST | `/rest/services/{item_id}/FeatureServer/{camada_id}/{object_id}/deleteAttachments` | edicao-esri | — | `protocolo FeatureServer da Esri (query/applyEdits/addFeatures/anexos/replica) consumido DIRETO por ArcGIS Pro/Field Maps/AGOL depois que o usuário cola a URL do serviço (mostrada na ficha da camada); não há operação individual para virar botão nosso` | **sem tela por desenho** | não se aplica |
| POST | `/rest/services/{item_id}/FeatureServer/{camada_id}/{object_id}/updateAttachment` | edicao-esri | — | `protocolo FeatureServer da Esri (query/applyEdits/addFeatures/anexos/replica) consumido DIRETO por ArcGIS Pro/Field Maps/AGOL depois que o usuário cola a URL do serviço (mostrada na ficha da camada); não há operação individual para virar botão nosso` | **sem tela por desenho** | não se aplica |
| GET | `/rest/services/{item_id}/FeatureServer/{camada}` | featureserver | `/aplicativo`, `/executar` | `web/js/app/consulta.js:143` | **coberto** | com erro |
| GET | `/rest/services/{item_id}/VersionManagementServer` | versionamento-esri | — | `protocolo de versionamento por ramo da Esri (branch versioning), falado só por ArcGIS Pro depois de conectar ao serviço; app/versionamento/rotas_esri.py é fachada, não produto nosso` | **sem tela por desenho** | não se aplica |
| POST | `/rest/services/{item_id}/VersionManagementServer` | versionamento-esri | — | `protocolo de versionamento por ramo da Esri (branch versioning), falado só por ArcGIS Pro depois de conectar ao serviço; app/versionamento/rotas_esri.py é fachada, não produto nosso` | **sem tela por desenho** | não se aplica |
| POST | `/rest/services/{item_id}/VersionManagementServer/create` | versionamento-esri | — | `protocolo de versionamento por ramo da Esri (branch versioning), falado só por ArcGIS Pro depois de conectar ao serviço; app/versionamento/rotas_esri.py é fachada, não produto nosso` | **sem tela por desenho** | não se aplica |
| GET | `/rest/services/{item_id}/VersionManagementServer/versionInfos` | versionamento-esri | — | `protocolo de versionamento por ramo da Esri (branch versioning), falado só por ArcGIS Pro depois de conectar ao serviço; app/versionamento/rotas_esri.py é fachada, não produto nosso` | **sem tela por desenho** | não se aplica |
| POST | `/rest/services/{item_id}/VersionManagementServer/versionInfos` | versionamento-esri | — | `protocolo de versionamento por ramo da Esri (branch versioning), falado só por ArcGIS Pro depois de conectar ao serviço; app/versionamento/rotas_esri.py é fachada, não produto nosso` | **sem tela por desenho** | não se aplica |
| GET | `/rest/services/{item_id}/VersionManagementServer/versions` | versionamento-esri | — | `protocolo de versionamento por ramo da Esri (branch versioning), falado só por ArcGIS Pro depois de conectar ao serviço; app/versionamento/rotas_esri.py é fachada, não produto nosso` | **sem tela por desenho** | não se aplica |
| POST | `/rest/services/{item_id}/VersionManagementServer/versions` | versionamento-esri | — | `protocolo de versionamento por ramo da Esri (branch versioning), falado só por ArcGIS Pro depois de conectar ao serviço; app/versionamento/rotas_esri.py é fachada, não produto nosso` | **sem tela por desenho** | não se aplica |
| GET | `/rest/services/{item_id}/VersionManagementServer/{versao_guid}/conflicts` | versionamento-esri | — | `protocolo de versionamento por ramo da Esri (branch versioning), falado só por ArcGIS Pro depois de conectar ao serviço; app/versionamento/rotas_esri.py é fachada, não produto nosso` | **sem tela por desenho** | não se aplica |
| POST | `/rest/services/{item_id}/VersionManagementServer/{versao_guid}/conflicts` | versionamento-esri | — | `protocolo de versionamento por ramo da Esri (branch versioning), falado só por ArcGIS Pro depois de conectar ao serviço; app/versionamento/rotas_esri.py é fachada, não produto nosso` | **sem tela por desenho** | não se aplica |
| POST | `/rest/services/{item_id}/VersionManagementServer/{versao_guid}/delete` | versionamento-esri | — | `protocolo de versionamento por ramo da Esri (branch versioning), falado só por ArcGIS Pro depois de conectar ao serviço; app/versionamento/rotas_esri.py é fachada, não produto nosso` | **sem tela por desenho** | não se aplica |
| POST | `/rest/services/{item_id}/VersionManagementServer/{versao_guid}/post` | versionamento-esri | — | `protocolo de versionamento por ramo da Esri (branch versioning), falado só por ArcGIS Pro depois de conectar ao serviço; app/versionamento/rotas_esri.py é fachada, não produto nosso` | **sem tela por desenho** | não se aplica |
| POST | `/rest/services/{item_id}/VersionManagementServer/{versao_guid}/reconcile` | versionamento-esri | — | `protocolo de versionamento por ramo da Esri (branch versioning), falado só por ArcGIS Pro depois de conectar ao serviço; app/versionamento/rotas_esri.py é fachada, não produto nosso` | **sem tela por desenho** | não se aplica |
| POST | `/rest/services/{item_id}/VersionManagementServer/{versao_guid}/startEditing` | versionamento-esri | — | `protocolo de versionamento por ramo da Esri (branch versioning), falado só por ArcGIS Pro depois de conectar ao serviço; app/versionamento/rotas_esri.py é fachada, não produto nosso` | **sem tela por desenho** | não se aplica |
| POST | `/rest/services/{item_id}/VersionManagementServer/{versao_guid}/startReading` | versionamento-esri | — | `protocolo de versionamento por ramo da Esri (branch versioning), falado só por ArcGIS Pro depois de conectar ao serviço; app/versionamento/rotas_esri.py é fachada, não produto nosso` | **sem tela por desenho** | não se aplica |
| POST | `/rest/services/{item_id}/VersionManagementServer/{versao_guid}/stopEditing` | versionamento-esri | — | `protocolo de versionamento por ramo da Esri (branch versioning), falado só por ArcGIS Pro depois de conectar ao serviço; app/versionamento/rotas_esri.py é fachada, não produto nosso` | **sem tela por desenho** | não se aplica |
| POST | `/rest/services/{item_id}/VersionManagementServer/{versao_guid}/stopReading` | versionamento-esri | — | `protocolo de versionamento por ramo da Esri (branch versioning), falado só por ArcGIS Pro depois de conectar ao serviço; app/versionamento/rotas_esri.py é fachada, não produto nosso` | **sem tela por desenho** | não se aplica |
| GET | `/rest/services/{servico}/UtilityNetworkServer/unitIdentifiers` | rede de utilidades — fachada Esri unitIdentifiers | — | `fachada unitIdentifiers do Utility Network da Esri, consumida por ArcGIS Pro/Field Maps ao editar a rede de utilidades — mesma categoria do FeatureServer acima` | **sem tela por desenho** | não se aplica |
| POST | `/rest/services/{servico}/UtilityNetworkServer/unitIdentifiers` | rede de utilidades — fachada Esri unitIdentifiers | — | `fachada unitIdentifiers do Utility Network da Esri, consumida por ArcGIS Pro/Field Maps ao editar a rede de utilidades — mesma categoria do FeatureServer acima` | **sem tela por desenho** | não se aplica |
| GET | `/rest/services/{servico}/UtilityNetworkServer/unitIdentifiers/query` | rede de utilidades — fachada Esri unitIdentifiers | — | `fachada unitIdentifiers do Utility Network da Esri, consumida por ArcGIS Pro/Field Maps ao editar a rede de utilidades — mesma categoria do FeatureServer acima` | **sem tela por desenho** | não se aplica |
| POST | `/rest/services/{servico}/UtilityNetworkServer/unitIdentifiers/query` | rede de utilidades — fachada Esri unitIdentifiers | — | `fachada unitIdentifiers do Utility Network da Esri, consumida por ArcGIS Pro/Field Maps ao editar a rede de utilidades — mesma categoria do FeatureServer acima` | **sem tela por desenho** | não se aplica |
| GET | `/rest/services/{servico}/UtilityNetworkServer/unitIdentifiers/reserve` | rede de utilidades — fachada Esri unitIdentifiers | — | `fachada unitIdentifiers do Utility Network da Esri, consumida por ArcGIS Pro/Field Maps ao editar a rede de utilidades — mesma categoria do FeatureServer acima` | **sem tela por desenho** | não se aplica |
| POST | `/rest/services/{servico}/UtilityNetworkServer/unitIdentifiers/reserve` | rede de utilidades — fachada Esri unitIdentifiers | — | `fachada unitIdentifiers do Utility Network da Esri, consumida por ArcGIS Pro/Field Maps ao editar a rede de utilidades — mesma categoria do FeatureServer acima` | **sem tela por desenho** | não se aplica |
| GET | `/saude` | saude | `/` | `web/app.js:27` | **coberto** | com erro |
| GET | `/saude/profunda` | saude | — | — | **sem controle** | não se aplica |
| GET | `/svc/{token}/camadas/{item_id}.csv` | tiles-vetoriais-exportacao | — | — | **sem tela** | não se aplica |
| GET | `/svc/{token}/camadas/{item_id}.fgb` | tiles-vetoriais-exportacao | — | — | **sem tela** | não se aplica |
| GET | `/svc/{token}/camadas/{item_id}.geojson` | tiles-vetoriais-exportacao | — | — | **sem tela** | não se aplica |
| GET | `/svc/{token}/camadas/{item_id}.gpkg` | tiles-vetoriais-exportacao | — | — | **sem tela** | não se aplica |
| GET | `/svc/{token}/camadas/{item_id}.kml` | tiles-vetoriais-exportacao | — | — | **sem tela** | não se aplica |
| GET | `/svc/{token}/cog/{item}/{asset}.tif` | imagens | — | — | **sem controle** | não se aplica |
| GET | `/svc/{token}/mosaico/{alvo}/{z}/{x}/{y}` | tiles | — | — | **sem controle** | não se aplica |
| GET | `/svc/{token}/mosaico/{alvo}/{z}/{x}/{y}.{ext}` | tiles | — | — | **sem controle** | não se aplica |
| GET | `/svc/{token}/mosaico/{mosaico_id}/pegadas` | tiles | — | — | **sem controle** | não se aplica |
| GET | `/svc/{token}/mosaico/{mosaico_id}/tilejson.json` | tiles | — | — | **sem controle** | não se aplica |
| GET | `/svc/{token}/mosaico/{mosaico_id}/wmts` | tiles | — | — | **sem controle** | não se aplica |
| GET | `/svc/{token}/mosaico/{mosaico_id}/wmts/1.0.0/WMTSCapabilities.xml` | tiles | — | — | **sem controle** | não se aplica |
| GET | `/svc/{token}/ogc/tiles` | ogc-tiles | — | — | **sem tela** | não se aplica |
| GET | `/svc/{token}/ogc/tiles/collections` | ogc-tiles | — | — | **sem tela** | não se aplica |
| GET | `/svc/{token}/ogc/tiles/collections/{item}` | ogc-tiles | — | — | **sem tela** | não se aplica |
| GET | `/svc/{token}/ogc/tiles/collections/{item}/map` | ogc-tiles | — | — | **sem tela** | não se aplica |
| GET | `/svc/{token}/ogc/tiles/collections/{item}/map/tiles/{tile_matrix_set_id}` | ogc-tiles | — | — | **sem tela** | não se aplica |
| GET | `/svc/{token}/ogc/tiles/collections/{item}/map/tiles/{tile_matrix_set_id}/{tile_matrix}/{tile_row}/{tile_col}` | ogc-tiles | — | — | **sem tela** | não se aplica |
| GET | `/svc/{token}/ogc/tiles/collections/{item}/map/tiles/{tile_matrix_set_id}/{tile_matrix}/{tile_row}/{tile_col}.{ext}` | ogc-tiles | — | — | **sem tela** | não se aplica |
| GET | `/svc/{token}/ogc/tiles/conformance` | ogc-tiles | — | — | **sem tela** | não se aplica |
| GET | `/svc/{token}/ogc/tiles/tileMatrixSets` | ogc-tiles | — | — | **sem tela** | não se aplica |
| GET | `/svc/{token}/ogc/tiles/tileMatrixSets/{tile_matrix_set_id}` | ogc-tiles | — | — | **sem tela** | não se aplica |
| GET | `/svc/{token}/raster/{item}/estatisticas.json` | tiles | — | — | **sem controle** | não se aplica |
| GET | `/svc/{token}/raster/{item}/info.json` | tiles | — | — | **sem controle** | não se aplica |
| GET | `/svc/{token}/raster/{item}/legenda.json` | tiles | — | — | **sem controle** | não se aplica |
| GET | `/svc/{token}/raster/{item}/legenda.png` | tiles | — | — | **sem controle** | não se aplica |
| GET | `/svc/{token}/raster/{item}/predefinicoes.json` | tiles | — | — | **sem controle** | não se aplica |
| GET | `/svc/{token}/raster/{item}/tilejson.json` | tiles | `/conteudo`, `/conteudo/lixeira`, `/conteudo/{id}` | `web/js/catalogo/tipos/raster.js:57` | **coberto** | com erro |
| GET | `/svc/{token}/raster/{item}/wmts` | tiles | — | — | **sem controle** | não se aplica |
| GET | `/svc/{token}/raster/{item}/wmts/1.0.0/WMTSCapabilities.xml` | tiles | — | — | **sem controle** | não se aplica |
| GET | `/svc/{token}/raster/{item}/{z}/{x}/{y}` | tiles | — | — | **sem controle** | não se aplica |
| GET | `/svc/{token}/raster/{item}/{z}/{x}/{y}.{ext}` | tiles | — | — | **sem controle** | não se aplica |
| GET | `/svc/{token}/rest/generateToken` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| POST | `/svc/{token}/rest/generateToken` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| GET | `/svc/{token}/rest/info` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| POST | `/svc/{token}/rest/info` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| GET | `/svc/{token}/rest/services` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| GET | `/svc/{token}/rest/services/Utilities/Geometry/GeometryServer` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| POST | `/svc/{token}/rest/services/Utilities/Geometry/GeometryServer` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| GET | `/svc/{token}/rest/services/Utilities/Geometry/GeometryServer/areasAndLengths` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| POST | `/svc/{token}/rest/services/Utilities/Geometry/GeometryServer/areasAndLengths` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| GET | `/svc/{token}/rest/services/Utilities/Geometry/GeometryServer/buffer` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| POST | `/svc/{token}/rest/services/Utilities/Geometry/GeometryServer/buffer` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| GET | `/svc/{token}/rest/services/Utilities/Geometry/GeometryServer/convexHull` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| POST | `/svc/{token}/rest/services/Utilities/Geometry/GeometryServer/convexHull` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| GET | `/svc/{token}/rest/services/Utilities/Geometry/GeometryServer/difference` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| POST | `/svc/{token}/rest/services/Utilities/Geometry/GeometryServer/difference` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| GET | `/svc/{token}/rest/services/Utilities/Geometry/GeometryServer/distance` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| POST | `/svc/{token}/rest/services/Utilities/Geometry/GeometryServer/distance` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| GET | `/svc/{token}/rest/services/Utilities/Geometry/GeometryServer/intersect` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| POST | `/svc/{token}/rest/services/Utilities/Geometry/GeometryServer/intersect` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| GET | `/svc/{token}/rest/services/Utilities/Geometry/GeometryServer/lengths` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| POST | `/svc/{token}/rest/services/Utilities/Geometry/GeometryServer/lengths` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| GET | `/svc/{token}/rest/services/Utilities/Geometry/GeometryServer/project` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| POST | `/svc/{token}/rest/services/Utilities/Geometry/GeometryServer/project` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| GET | `/svc/{token}/rest/services/Utilities/Geometry/GeometryServer/simplify` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| POST | `/svc/{token}/rest/services/Utilities/Geometry/GeometryServer/simplify` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| GET | `/svc/{token}/rest/services/Utilities/Geometry/GeometryServer/union` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| POST | `/svc/{token}/rest/services/Utilities/Geometry/GeometryServer/union` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| GET | `/svc/{token}/rest/services/{item_id}/FeatureServer` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| GET | `/svc/{token}/rest/services/{item_id}/FeatureServer/info/itemInfo` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| GET | `/svc/{token}/rest/services/{item_id}/FeatureServer/info/metadata` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| GET | `/svc/{token}/rest/services/{item_id}/FeatureServer/layers` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| GET | `/svc/{token}/rest/services/{item_id}/FeatureServer/{camada_id}` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| GET | `/svc/{token}/rest/services/{item_id}/MapServer` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| GET | `/svc/{token}/rest/services/{item_id}/MapServer/export` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| POST | `/svc/{token}/rest/services/{item_id}/MapServer/export` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| GET | `/svc/{token}/rest/services/{item_id}/MapServer/find` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| POST | `/svc/{token}/rest/services/{item_id}/MapServer/find` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| GET | `/svc/{token}/rest/services/{item_id}/MapServer/generateKml` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| GET | `/svc/{token}/rest/services/{item_id}/MapServer/identify` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| POST | `/svc/{token}/rest/services/{item_id}/MapServer/identify` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| GET | `/svc/{token}/rest/services/{item_id}/MapServer/layers` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| GET | `/svc/{token}/rest/services/{item_id}/MapServer/legend` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| GET | `/svc/{token}/rest/services/{item_id}/MapServer/{camada_id}` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| GET | `/svc/{token}/rest/services/{item_id}/VectorTileServer` | tiles-vetoriais | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| GET | `/svc/{token}/rest/services/{item_id}/VectorTileServer/resources/fonts/{fontstack}/{faixa}.pbf` | tiles-vetoriais | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| GET | `/svc/{token}/rest/services/{item_id}/VectorTileServer/resources/sprites/sprite.json` | tiles-vetoriais | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| GET | `/svc/{token}/rest/services/{item_id}/VectorTileServer/resources/sprites/sprite.png` | tiles-vetoriais | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| GET | `/svc/{token}/rest/services/{item_id}/VectorTileServer/resources/styles/root.json` | tiles-vetoriais | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| GET | `/svc/{token}/rest/services/{item_id}/VectorTileServer/tile/{z}/{y}/{x}.pbf` | tiles-vetoriais | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| GET | `/svc/{token}/rest/services/{item}/ImageServer` | imagens-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| GET | `/svc/{token}/rest/services/{item}/ImageServer/exportImage` | imagens-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| GET | `/svc/{token}/rest/services/{item}/ImageServer/identify` | imagens-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| GET | `/svc/{token}/rest/services/{item}/ImageServer/tile/{level}/{row}/{col}` | imagens-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| GET | `/svc/{token}/rest/services/{pasta}` | consulta-esri | — | `fachada Esri por token (generateToken, info, GeometryServer, MapServer find/identify/export) consumida por widgets ArcGIS JS/Pro externos, nunca pela nossa web/` | **sem tela por desenho** | não se aplica |
| GET | `/svc/{token}/stac/` | stac | — | `catálogo STAC do item raster (mosaico) para cliente STAC/QGIS; a ficha do raster (web/js/catalogo/tipos/raster.js) mostra a URL com o token` | **externo** | não se aplica |
| GET | `/svc/{token}/stac/api` | stac | — | `catálogo STAC do item raster (mosaico) para cliente STAC/QGIS; a ficha do raster (web/js/catalogo/tipos/raster.js) mostra a URL com o token` | **externo** | não se aplica |
| GET | `/svc/{token}/stac/collections` | stac | — | `catálogo STAC do item raster (mosaico) para cliente STAC/QGIS; a ficha do raster (web/js/catalogo/tipos/raster.js) mostra a URL com o token` | **externo** | não se aplica |
| POST | `/svc/{token}/stac/collections` | stac | — | `catálogo STAC do item raster (mosaico) para cliente STAC/QGIS; a ficha do raster (web/js/catalogo/tipos/raster.js) mostra a URL com o token` | **externo** | não se aplica |
| GET | `/svc/{token}/stac/collections/{colecao_id}` | stac | — | `catálogo STAC do item raster (mosaico) para cliente STAC/QGIS; a ficha do raster (web/js/catalogo/tipos/raster.js) mostra a URL com o token` | **externo** | não se aplica |
| GET | `/svc/{token}/stac/collections/{colecao_id}/items` | stac | — | `catálogo STAC do item raster (mosaico) para cliente STAC/QGIS; a ficha do raster (web/js/catalogo/tipos/raster.js) mostra a URL com o token` | **externo** | não se aplica |
| POST | `/svc/{token}/stac/collections/{colecao_id}/items` | stac | — | `catálogo STAC do item raster (mosaico) para cliente STAC/QGIS; a ficha do raster (web/js/catalogo/tipos/raster.js) mostra a URL com o token` | **externo** | não se aplica |
| GET | `/svc/{token}/stac/collections/{colecao_id}/items/{item_id}` | stac | — | `catálogo STAC do item raster (mosaico) para cliente STAC/QGIS; a ficha do raster (web/js/catalogo/tipos/raster.js) mostra a URL com o token` | **externo** | não se aplica |
| GET | `/svc/{token}/stac/collections/{colecao_id}/queryables` | stac | — | `catálogo STAC do item raster (mosaico) para cliente STAC/QGIS; a ficha do raster (web/js/catalogo/tipos/raster.js) mostra a URL com o token` | **externo** | não se aplica |
| GET | `/svc/{token}/stac/conformance` | stac | — | `catálogo STAC do item raster (mosaico) para cliente STAC/QGIS; a ficha do raster (web/js/catalogo/tipos/raster.js) mostra a URL com o token` | **externo** | não se aplica |
| GET | `/svc/{token}/stac/mosaicos` | stac | — | `catálogo STAC do item raster (mosaico) para cliente STAC/QGIS; a ficha do raster (web/js/catalogo/tipos/raster.js) mostra a URL com o token` | **externo** | não se aplica |
| POST | `/svc/{token}/stac/mosaicos` | stac | — | `catálogo STAC do item raster (mosaico) para cliente STAC/QGIS; a ficha do raster (web/js/catalogo/tipos/raster.js) mostra a URL com o token` | **externo** | não se aplica |
| GET | `/svc/{token}/stac/mosaicos/{mosaico_id}` | stac | — | `catálogo STAC do item raster (mosaico) para cliente STAC/QGIS; a ficha do raster (web/js/catalogo/tipos/raster.js) mostra a URL com o token` | **externo** | não se aplica |
| DELETE | `/svc/{token}/stac/mosaicos/{mosaico_id}` | stac | — | `catálogo STAC do item raster (mosaico) para cliente STAC/QGIS; a ficha do raster (web/js/catalogo/tipos/raster.js) mostra a URL com o token` | **externo** | não se aplica |
| GET | `/svc/{token}/stac/queryables` | stac | — | `catálogo STAC do item raster (mosaico) para cliente STAC/QGIS; a ficha do raster (web/js/catalogo/tipos/raster.js) mostra a URL com o token` | **externo** | não se aplica |
| GET | `/svc/{token}/stac/search` | stac | — | `catálogo STAC do item raster (mosaico) para cliente STAC/QGIS; a ficha do raster (web/js/catalogo/tipos/raster.js) mostra a URL com o token` | **externo** | não se aplica |
| POST | `/svc/{token}/stac/search` | stac | — | `catálogo STAC do item raster (mosaico) para cliente STAC/QGIS; a ficha do raster (web/js/catalogo/tipos/raster.js) mostra a URL com o token` | **externo** | não se aplica |
| GET | `/svc/{token}/wms` | wms | — | — | **sem tela** | não se aplica |
| GET | `/tiles/{token}/{item_id}/tilejson.json` | tiles-vetoriais | — | — | **sem tela** | não se aplica |
| GET | `/tiles/{token}/{item_id}/{z}/{x}/{y}.pbf` | tiles-vetoriais | — | — | **sem tela** | não se aplica |
| GET | `/videos/arquivo/{caminho}` | videos | — | — | **sem controle** | não se aplica |
| GET | `/wfs/{item_id}` | wfs | — | — | **sem tela** | não se aplica |
| GET | `/wms/{item_id}` | wms | — | — | **sem tela** | não se aplica |
| GET | `/wmts/{item_id}` | wmts | — | — | **sem tela** | não se aplica |
| GET | `/wmts/{item_id}/rest/WMTSCapabilities.xml` | wmts | — | — | **sem tela** | não se aplica |
| GET | `/wmts/{item_id}/rest/{camada}/{estilo}/{tms}/{z}/{y}/{x}.png` | wmts | — | — | **sem tela** | não se aplica |

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
| `/admin/auditoria` | admin/auditoria.html | sim | sim | sim | sim | sim |
| `/admin/organizacao` | admin/organizacao.html | sim | sim | sim | sim | sim |
| `/status` | status.html | sim | **não** | sim | sim | **não** |
| `/admin/categorias` | admin/categorias.html | sim | sim | sim | sim | sim |
| `/admin/inquilinos` | admin/inquilinos.html | sim | sim | sim | sim | sim |
| `/admin/backup` | admin/backup.html | sim | sim | sim | sim | sim |
| `/conteudo` | conteudo.html | sim | sim | sim | sim | sim |
| `/conteudo/lixeira` | conteudo_lixeira.html | sim | sim | sim | sim | sim |
| `/conteudo/{id}` | conteudo_item.html | sim | sim | sim | sim | sim |
| `/imagens/{id}/ficha` | imagem_ficha.html | sim | **não** | **não** | sim | sim |
| `/mapa` | mapa.html | sim | sim | **não** | sim | sim |
| `/modelo/{id}` | modelo.html | sim | **não** | sim | sim | sim |
| `/sig` | sig.html | sim | sim | sim | sim | sim |
| `/aplicativo` | aplicativo.html | sim | sim | sim | sim | **não** |
| `/paineis/{id}` | painel.html | sim | sim | sim | sim | sim |
| `/render/mapa` | render_mapa.html | sim | **não** | **não** | **não** | **não** |
| `/simbolos` | simbolos.html | sim | **não** | **não** | sim | sim |
| `/analise` | analise.html | sim | **não** | **não** | sim | sim |
| `/cena` | cena.html | sim | sim | **não** | sim | sim |
| `/acervo` | acervo.html | sim | **não** | **não** | sim | sim |
| `/conexoes` | conexoes.html | sim | sim | sim | sim | sim |
| `/chamados` | chamados.html | sim | sim | **não** | sim | sim |
| `/admin/chamados` | admin/chamados.html | sim | sim | **não** | sim | sim |
| `/aceitar-convite` | aceitar_convite.html | sim | **não** | **não** | sim | **não** |
| `/redefinir-senha` | redefinir_senha.html | sim | **não** | **não** | sim | **não** |
| `/campo/filas` | campo_filas.html | sim | sim | sim | sim | sim |
| `/campo/filas/{fila_id}` | campo_fila.html | sim | sim | **não** | sim | sim |
| `/campo/roteiros/{roteiro_id}` | campo_roteiro.html | sim | **não** | **não** | sim | sim |
| `/redes/simples` | redes_simples.html | sim | sim | **não** | sim | sim |
| `/redes/controladores` | redes_controladores.html | sim | **não** | **não** | sim | sim |
| `/redes/configuracoes` | redes_configuracoes.html | sim | **não** | **não** | sim | sim |
| `/redes/diagrama` | redes_diagrama.html | sim | **não** | **não** | sim | sim |
| `/redes/fluxo` | redes_fluxo.html | sim | **não** | **não** | sim | sim |
| `/redes/tracado` | redes_tracado.html | sim | **não** | **não** | sim | sim |
| `/redes/isolamento` | redes_isolamento.html | sim | **não** | **não** | sim | sim |
| `/camadas/{id}/dominios` | camada_dominios.html | sim | sim | **não** | sim | sim |
| `/uploads` | uploads.html | sim | **não** | **não** | sim | sim |
| `/estilo-guia` | estilo_guia.html | sim | sim | sim | sim | sim |
| `/amc/pareto` | amc_pareto.html | sim | **não** | **não** | sim | sim |
| `/construtor` | construtor.html | sim | sim | **não** | sim | sim |
| `/construtor-camada` | construtor_camada.html | sim | **não** | **não** | sim | sim |
| `/vista-de-camada` | vista_camada.html | sim | sim | **não** | sim | sim |
| `/executar` | executar.html | sim | sim | sim | sim | sim |
| `/ferramentas` | ferramentas.html | sim | sim | sim | sim | sim |
| `/plataforma` | plataforma.html | sim | sim | **não** | sim | sim |
| `/migracao` | migracao.html | sim | **não** | **não** | sim | sim |
| `/analise3d` | analise3d.html | sim | **não** | **não** | sim | sim |
| `/admin/atividade` | admin/atividade.html | sim | sim | sim | sim | sim |
| `/temas` | temas.html | sim | **não** | **não** | sim | sim |
| `/colecao` | colecao.html | sim | sim | **não** | sim | sim |
| `/geocodificacoes/{geocodificacao_id}` | geocodificacao.html | sim | **não** | **não** | **não** | **não** |
| `/videos` | videos.html | sim | sim | **não** | sim | sim |
| `/crs` | crs.html | sim | **não** | **não** | sim | sim |
| `/visualizar` | visualizar.html | sim | sim | **não** | sim | sim |
| `/geocodificar` | geocodificar.html | sim | sim | sim | sim | sim |
| `/amc/presets` | amc_presets.html | sim | **não** | **não** | sim | sim |
| `/estilo` | estilo.html | sim | sim | sim | sim | sim |
| `/importacoes` | importacoes.html | sim | sim | sim | sim | sim |
| `/versoes` | versoes.html | sim | **não** | **não** | sim | sim |
| `/admin/logins` | admin/logins.html | sim | sim | sim | sim | sim |
| `/coleta` | coleta.html | sim | **não** | **não** | sim | sim |
| `/ferramenta` | ferramenta.html | sim | **não** | sim | sim | sim |
| `/amc/explicacao/{execucao_id}/{unidade_id}` | amc_explicacao.html | sim | **não** | **não** | sim | sim |
| `/amc/motor` | amc_motor.html | sim | sim | **não** | sim | sim |
| `/amc/criterios-feicao` | amc_criterios_feicao.html | sim | **não** | **não** | sim | sim |
| `/modelos` | modelos.html | sim | sim | **não** | sim | sim |
| `/sites` | sites.html | sim | sim | **não** | sim | sim |
| `/camadas/{id}/formulario` | formulario_construtor.html | sim | **não** | **não** | sim | sim |
| `/rede/medicao/ficha` | rede_medicao_ficha.html | sim | **não** | **não** | sim | sim |
| `/tarefas` | tarefas.html | sim | sim | sim | sim | sim |
| `/tarefas/{job_id}` | tarefas.html | sim | sim | sim | sim | sim |

## Lacunas de escrita (cada grupo vira um item UX-<n> no backlog via `--registrar`)

- **acervo**: POST `/api/acervo/camadas/{camada}/assinatura` (sem controle); DELETE `/api/acervo/camadas/{camada}/assinatura` (sem controle)
- **amc**: POST `/api/amc/conjuntos` (sem controle); DELETE `/api/amc/conjuntos/{conjunto_id}` (sem controle); POST `/api/amc/criterios-feicao/exportar` (sem controle); DELETE `/api/amc/execucoes/{execucao_id}` (sem controle); POST `/api/amc/modelos` (sem controle); POST `/api/amc/modelos/validar` (sem controle); DELETE `/api/amc/modelos/{modelo_id}` (sem controle); POST `/api/amc/pareto` (sem controle); POST `/api/amc/similaridade` (sem controle); POST `/api/amc/similaridade/exportar` (sem controle)
- **arquivos**: POST `/api/arquivos` (sem controle); DELETE `/api/arquivos/{sha256}` (sem controle)
- **camada-esquema**: PUT `/api/camadas/{item_id}/esquema` (sem controle); POST `/api/camadas/{item_id}/esquema/plano` (sem controle)
- **campo**: POST `/api/campo/filas/{fila_id}/alvos` (sem controle); PUT `/api/campo/filas/{fila_id}/ordem` (sem controle); POST `/api/campo/sessao` (sem controle)
- **catalogo**: POST `/api/itens/{id}/metadado.xml` (sem controle); POST `/api/modelos` (sem controle)
- **chamados**: POST `/api/chamados` (sem controle)
- **conexoes**: PUT `/api/conexoes/{id}/arquivo` (sem controle); POST `/api/conexoes/{id}/arquivo/sincronizar` (sem controle); POST `/api/csw/buscar` (sem controle); POST `/api/csw/conexoes` (sem controle); POST `/api/endpoints-publicos/{id}/adicionar` (sem controle)
- **dominios**: POST `/api/camadas/{item_id}/dominios` (sem controle); DELETE `/api/camadas/{item_id}/dominios/{ligacao_id}` (sem controle); PUT `/api/camadas/{item_id}/subtipos` (sem controle); DELETE `/api/camadas/{item_id}/subtipos` (sem controle); POST `/api/dominios` (sem controle); POST `/api/dominios/csv` (sem controle); POST `/api/dominios/importar` (sem controle); PUT `/api/dominios/{dominio_id}` (sem controle); DELETE `/api/dominios/{dominio_id}` (sem controle)
- **edicao**: DELETE `/api/camadas/{id}/feicoes/{globalid}/anexos/{anexo_id}` (sem controle)
- **estatistica**: POST `/api/camadas/{item_id}/estatisticas` (sem tela); POST `/api/camadas/{item_id}/grafico` (sem tela)
- **estilos**: POST `/api/estilos/compilar` (sem tela)
- **exportacao_inquilino**: DELETE `/api/inquilino/exportacoes/{exportacao_id}` (sem tela); POST `/api/inquilino/exportar` (sem tela)
- **ferramentas**: POST `/api/ferramentas/script` (sem controle); POST `/api/ferramentas/script/{id}/versao` (sem controle)
- **fluxos**: POST `/api/fluxos` (sem tela); PATCH `/api/fluxos/{id}` (sem tela); DELETE `/api/fluxos/{id}` (sem tela); DELETE `/api/fluxos/{id}/eventos` (sem tela); POST `/api/fluxos/{id}/simular` (sem tela)
- **formulario**: POST `/api/camadas/{id}/formulario` (sem controle)
- **formularios**: POST `/api/formularios/xlsform` (sem controle)
- **geocodificador**: PATCH `/api/geocodificador/lote/{item_id}/pendentes/{fid}` (sem controle); POST `/api/geocodificador/lote/{item_id}/regeocodificar` (sem controle)
- **geoparquet**: POST `/api/geoparquet` (sem tela)
- **imagens**: POST `/api/imagens/proveniencia/preencher-pendentes` (sem controle)
- **imagens-predefinicoes**: POST `/api/imagens/{item_id}/predefinicoes` (sem controle); PUT `/api/imagens/{item_id}/predefinicoes/{nome}` (sem controle); DELETE `/api/imagens/{item_id}/predefinicoes/{nome}` (sem controle); POST `/api/imagens/{item_id}/predefinicoes/{nome}/tornar-padrao` (sem controle)
- **ingestao**: POST `/api/itens/{id}/exportar` (sem controle); POST `/api/org/exportar` (sem controle)
- **intercambio**: POST `/api/intercambio/exportacoes` (sem tela); DELETE `/api/intercambio/exportacoes/{id}` (sem tela); POST `/api/intercambio/importacoes-lote` (sem tela); PUT `/api/intercambio/importacoes-lote/{lote_id}/confirmar` (sem tela)
- **layout**: POST `/api/layouts/exportar` (sem tela); POST `/api/layouts/previa` (sem tela); POST `/api/layouts/validar` (sem tela)
- **log**: POST `/api/log/nivel` (sem controle); DELETE `/api/log/nivel` (sem controle)
- **login**: PUT `/api/org/oidc/{provedor_id}` (sem controle); DELETE `/api/org/oidc/{provedor_id}` (sem controle); POST `/api/org/saml` (sem controle); PUT `/api/org/saml/{provedor_id}` (sem controle); DELETE `/api/org/saml/{provedor_id}` (sem controle); PUT `/api/org/sso/oidc` (sem controle); PUT `/api/org/sso/saml` (sem controle)
- **logins**: POST `/api/usuarios/{id}/desregistrar` (sem controle)
- **mapa**: POST `/api/anotacoes` (sem controle); PATCH `/api/anotacoes/{id}` (sem controle); DELETE `/api/anotacoes/{id}` (sem controle); POST `/api/mapa/camadas/{id}/filtrar` (sem controle); POST `/api/mapa/camadas/{id}/selecionar` (sem controle); POST `/api/mapa/pacotes/importar` (sem controle); POST `/api/mapa/selecao-espacial` (sem controle); POST `/api/mapa/{mapa_id}/desenho/promover` (sem controle)
- **mapas-base**: POST `/api/mapas-base/instalar` (sem tela); POST `/api/mapas-base/{id}/tornar-padrao` (sem tela)
- **migracao**: DELETE `/api/migracao/inventarios/{id}` (sem controle)
- **modelos3d**: POST `/api/modelos3d` (sem controle); DELETE `/api/modelos3d/{id}` (sem controle)
- **multiescala**: POST `/api/multiescala/conjuntos` (sem controle); DELETE `/api/multiescala/conjuntos/{id}` (sem controle); POST `/api/multiescala/conjuntos/{id}/macro` (sem controle); POST `/api/multiescala/execucoes/{id}/backtest` (sem controle); POST `/api/multiescala/execucoes/{id}/corredor` (sem controle); POST `/api/multiescala/execucoes/{id}/micro` (sem controle); POST `/api/multiescala/execucoes/{id}/regioes` (sem controle); POST `/api/multiescala/fatores` (sem controle); DELETE `/api/multiescala/fatores/{id}` (sem controle); POST `/api/multiescala/fatores/{id}/amostras` (sem controle)
- **notificacoes**: POST `/api/notificacoes/lidas` (sem tela); DELETE `/api/notificacoes/{id}` (sem tela)
- **odk**: POST `/api/odk/pontes` (sem tela); POST `/api/odk/pontes/{id}/sincronizar` (sem tela)
- **paineis**: POST `/api/compartilhado/{token}/paineis/{item_id}/fontes/{fonte_id}/dados` (sem tela); POST `/api/itens/{item_id}/paineis/fontes/{fonte_id}/dados` (sem tela)
- **parcelas**: POST `/api/parcelas/fabrica/analyzeByLSA` (sem tela); POST `/api/parcelas/fabrica/applyLSA` (sem tela); POST `/api/parcelas/fabrica/assignFeaturesToRecord` (sem tela); POST `/api/parcelas/fabrica/build` (sem tela); POST `/api/parcelas/fabrica/clip` (sem tela); POST `/api/parcelas/fabrica/createSeeds` (sem tela); POST `/api/parcelas/fabrica/divide` (sem tela); POST `/api/parcelas/fabrica/merge` (sem tela); POST `/api/parcelas/fabrica/reconstructFromSeeds` (sem tela); POST `/api/parcelas/qualidade` (sem tela)
- **presenca**: POST `/api/itens/{id}/presenca` (sem tela)
- **publicacao**: DELETE `/api/itens/{id}/publicacao` (sem controle)
- **rede**: POST `/api/isocrona` (sem tela); POST `/api/matriz` (sem tela); POST `/api/rede/consumidores/enderecos-sem-rede` (sem tela); POST `/api/rede/consumidores/jusante/calcular` (sem tela); POST `/api/rota` (sem tela)
- **rede de utilidades**: POST `/api/rede` (sem controle); DELETE `/api/rede/{rede_id}` (sem controle); POST `/api/rede/{rede_id}/applyEdits` (sem controle); PUT `/api/rede/{rede_id}/area_sujas/modo` (sem controle); POST `/api/rede/{rede_id}/pacote` (sem controle); POST `/api/rede/{rede_id}/regras.csv` (sem controle); PUT `/api/rede/{rede_id}/regras/ativacao` (sem controle); POST `/api/rede/{rede_id}/validar` (sem controle); POST `/api/rede/{rede_id}/validar_extensao` (sem controle)
- **rede de utilidades — EPANET**: POST `/api/rede/{rede_id}/epanet` (sem tela)
- **rede de utilidades — MATPOWER**: POST `/api/rede/{rede_id}/matpower` (sem tela)
- **rede de utilidades — atributos**: POST `/api/rede/{rede_id}/atributos/conectividade` (sem tela); POST `/api/rede/{rede_id}/atributos/propagar-fase` (sem tela); POST `/api/rede/{rede_id}/atributos/sincronizar` (sem tela); POST `/api/rede/{rede_id}/atributos/substituicoes` (sem tela)
- **rede de utilidades — conector OSM**: POST `/api/rede/{rede_id}/importar-osm` (sem tela)
- **rede de utilidades — configuração de traçado**: PUT `/api/rede/{rede_id}/config_tracado/{config_id}` (sem controle)
- **rede de utilidades — controladores e tiers**: POST `/api/rede/{rede_id}/controlador` (sem controle); POST `/api/rede/{rede_id}/controladores/importar` (sem controle)
- **rede de utilidades — curto-circuito e proteção**: POST `/api/rede/{rede_id}/subrede/{nome}/curto` (sem tela)
- **rede de utilidades — diagrama**: POST `/api/rede/{rede_id}/diagrama` (sem controle); PUT `/api/rede/{rede_id}/diagrama-modelo/{codigo}` (sem controle); DELETE `/api/rede/{rede_id}/diagrama/{diagrama_id}` (sem controle)
- **rede de utilidades — fluxo de potência**: POST `/api/rede/{rede_id}/subrede/{nome}/fluxo` (sem controle)
- **rede de utilidades — gás e esgoto**: POST `/api/rede/{rede_id}/teksi` (sem tela)
- **rede de utilidades — identificadores**: POST `/api/rede/{rede_id}/ativos` (sem controle); PATCH `/api/rede/{rede_id}/ativos/{global_id}` (sem controle); POST `/api/rede/{rede_id}/faixas` (sem controle); DELETE `/api/rede/{rede_id}/faixas/{faixa_id}` (sem controle)
- **rede de utilidades — rede simples**: POST `/api/rede/{rede_id}/promover` (sem controle)
- **rede de utilidades — resultado de traçado**: POST `/api/rede/{rede_id}/tracar/exportar` (sem controle)
- **rede de utilidades — subredes**: PUT `/api/rede/{rede_id}/tier/{codigo}/propagadores` (sem controle)
- **rede de utilidades — sumário por subrede**: POST `/api/rede/{rede_id}/subredes/resumos/calcular` (sem tela)
- **rede de utilidades — topologia**: POST `/api/rede/{rede_id}/feicoes/linhas` (sem controle); POST `/api/rede/{rede_id}/feicoes/linhas/applyEdits` (sem controle); POST `/api/rede/{rede_id}/feicoes/pontos` (sem controle); POST `/api/rede/{rede_id}/feicoes/pontos/applyEdits` (sem controle); POST `/api/rede/{rede_id}/topologia/habilitar` (sem controle)
- **rede_medicao**: PUT `/api/rede/medicao/ativos/{ativo}` (sem controle)
- **regras**: PUT `/api/camadas/{id}/regras` (sem controle); POST `/api/camadas/{id}/validar` (sem controle)
- **relacionamentos**: POST `/api/relacionamentos` (sem tela); DELETE `/api/relacionamentos/{rel_id}` (sem tela); POST `/api/relacionamentos/{rel_id}/desligar` (sem tela); POST `/api/relacionamentos/{rel_id}/ligar` (sem tela)
- **render**: POST `/api/render/mapa` (sem tela); POST `/api/render/token` (sem tela)
- **replicas**: POST `/api/replicas` (sem tela); DELETE `/api/replicas/{id}` (sem tela); POST `/api/replicas/{id}/sincronizar` (sem tela)
- **tabela**: POST `/api/camadas/{item_id}/tabela/estatisticas` (sem tela); POST `/api/camadas/{item_id}/tabela/linhas` (sem tela); PUT `/api/camadas/{item_id}/tabela/vista` (sem tela)
- **telemetria**: PUT `/api/telemetria` (sem tela); POST `/api/telemetria/appliances` (sem tela); DELETE `/api/telemetria/appliances/{chave}` (sem tela); POST `/api/telemetria/enviar` (sem tela)
- **versionamento**: POST `/api/camadas/{id}/versionar` (sem controle); POST `/api/camadas/{id}/versoes` (sem controle); DELETE `/api/camadas/{id}/versoes/{versao}` (sem controle); POST `/api/camadas/{id}/versoes/{versao}/conflitos/{globalid}/resolver` (sem controle)
- **vista-de-camada**: PUT `/api/vistas/{vista_id}` (sem controle)
- **webhooks**: POST `/api/webhooks` (sem tela); PATCH `/api/webhooks/{id}` (sem tela); DELETE `/api/webhooks/{id}` (sem tela); POST `/api/webhooks/{id}/entregas/{entrega_id}/reenviar` (sem tela); POST `/api/webhooks/{id}/reativar` (sem tela); POST `/api/webhooks/{id}/rotacionar` (sem tela)
- **widgets**: POST `/api/widgets/externos` (sem controle); DELETE `/api/widgets/externos/{nome}` (sem controle)

## URLs chamadas pela tela sem rota correspondente na API

- `web/js/auth/plataforma.js:224 POST /api/plataforma/inquilinos/{x}/admins/{x}/2fa/desativar`
- `web/js/auth/plataforma.js:239 GET /api/plataforma/fila`
- `web/js/auth/plataforma.js:288 GET /api/plataforma/eventos`
- `web/js/catalogo/api.js:68 GET /api/openapi.json`
- `web/js/catalogo/tipos/raster.js:3 GET /svc/<token>/raster/<item>/...`
- `web/js/mapa/motor.js:364 GET /api/multiescala/execucoes/{x}/celulas`
- `web/js/mapa/render_layout_entrada.js:25 GET /api/render/layout/estilo`
- `web/js/mapa/tabela.js:90 GET /api/camadas/{x}/tabela`
- `web/js/mapa/tabela_atributos.js:52 GET /api/rede/{x}/feicoes/{x}.geojson`
- `web/js/portal/portal.js:254 GET /api/openapi.json`
- `web/js/rede/medicao_ficha.js:150 GET /api/rede/{x}/feicoes/pontos.geojson`
- `web/js/sig/sig.js:467 GET /api/rede/{x}/feicoes/linhas.geojson`
- `web/js/sig/sig.js:468 GET /api/rede/{x}/feicoes/pontos.geojson`
- `web/js/simbolos/galeria.js:24 GET /api/simbolos/sprite/{x}.json`
- `web/js/simbolos/galeria.js:29 GET /api/simbolos/sprite/{x}.png`

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
| L0-06-e-status | parcial | `/api/status` | rota coberta |
| L0-07-f-console-plataforma | parcial | `/api/plataforma` | rota coberta |
| L0-07-f-console-plataforma | parcial | `/p` | página inexistente |
| L0-08-a-oidc | parcial | `/api/sso` | rota coberta |
| L0-08-b-saml | parcial | `/api/sso/saml/metadata` | rota sem tela |
| L0-09-c-xml-iso-validacao | parcial | `/api/itens/{id}/metadado` | rota coberta |
| L2-01-a-documento-mapa | entregue | `/api/mapas` | rota coberta |
| L2-01-a-documento-mapa | entregue | `/api/mapas/{id}/completo` | rota coberta |
| L2-01-a-documento-mapa | entregue | `/c` | página inexistente |
| L2-02-b-classificacao-servidor | parcial | `/api/camadas/{id}/classes` | rota sem tela |
| L2-03-a-api-edicao-transacional | parcial | `/api/camadas/{id}/edicoes` | rota coberta |
| L2-04-d-featureserver-edicao-anexos | parcial | `/uploads/upload` | página existe |
| L2-04-g-ogc-api-features-crs-cql2 | parcial | `/api` | página inexistente |
| L2-06-d-atualizacao-viva-sse | parcial | `/api/eventos` | rota coberta |
| L2-11-b-geocodificador-brasil | parcial | `/api/geocodificar` | rota coberta |
| L5-05-documento-versoes | entregue | `/api/esquemas` | rota sem tela |
| L5-05-documento-versoes | entregue | `/api/itens/{id}/versoes` | rota coberta |
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
| UX-05-telas-conexoes-uploads-tarefas-compartilhado | parcial | `/c` | página inexistente |
| UX-05-telas-conexoes-uploads-tarefas-compartilhado | parcial | `/conexoes` | página existe |
| UX-05-telas-conexoes-uploads-tarefas-compartilhado | parcial | `/tarefas` | página existe |
| UX-05-telas-conexoes-uploads-tarefas-compartilhado | parcial | `/uploads` | página existe |
| UX-06-tela-administracao-inquilino | parcial | `/api/convites` | rota coberta |
| UX-06-tela-administracao-inquilino | parcial | `/api/cotas` | rota sem tela |
| UX-06-tela-administracao-inquilino | parcial | `/api/grupos` | rota coberta |
| UX-06-tela-administracao-inquilino | parcial | `/api/org` | rota coberta |
| UX-06-tela-administracao-inquilino | parcial | `/api/sso` | rota coberta |
| UX-09-telas-ferramentas-e-tarefas | parcial | `/tarefas` | página existe |
| UX-10-acervo-sem-tela | parcial | `/api/acervo/{fonte_id}/adicionar` | rota coberta |
| UX-11-arquivos-sem-controle | parcial | `/api/arquivos` | rota coberta |
| UX-11-arquivos-sem-controle | parcial | `/api/arquivos/{sha256}` | rota coberta |
| UX-12-categorias-sem-controle | parcial | `/api/categorias` | rota coberta |
| UX-12-categorias-sem-controle | parcial | `/api/categorias/importar` | rota coberta |
| UX-13-conexoes-sem-controle | parcial | `/api/conexoes` | rota coberta |
| UX-13-conexoes-sem-controle | parcial | `/api/conexoes/{id}` | rota coberta |
| UX-14-geocodificador-sem-tela | parcial | `/api/geocodificar` | rota coberta |
| UX-14-geocodificador-sem-tela | parcial | `/api/reverso` | rota coberta |
| UX-16-ingestao-sem-tela | parcial | `/api/importacoes` | rota coberta |
| UX-16-ingestao-sem-tela | parcial | `/api/importacoes/{id}` | rota coberta |
| UX-16-ingestao-sem-tela | parcial | `/api/importacoes/{id}/confirmar` | rota coberta |
| UX-17-login-sem-controle | parcial | `/api/login/ldap` | rota coberta |
| UX-17-login-sem-controle | parcial | `/api/org/ldap` | rota coberta |
| UX-17-login-sem-controle | parcial | `/api/org/ldap/importar` | rota coberta |
| UX-18-plataforma-sem-tela | parcial | `/api/plataforma/inquilinos` | rota coberta |
| UX-18-plataforma-sem-tela | parcial | `/api/plataforma/inquilinos/{id}` | rota coberta |
| UX-18-plataforma-sem-tela | parcial | `/api/plataforma/inquilinos/{id}/reativar` | rota coberta |
| UX-18-plataforma-sem-tela | parcial | `/api/plataforma/inquilinos/{id}/suspender` | rota coberta |
| UX-19-rede-sem-tela | parcial | `/api/isocrona` | rota sem tela |
| UX-19-rede-sem-tela | parcial | `/api/matriz` | rota sem tela |
| UX-19-rede-sem-tela | parcial | `/api/rota` | rota sem tela |
| UX-20-usuarios-sem-controle | parcial | `/api/papeis/{id}` | rota coberta |
| UX-21-multiescala-sem-tela | parcial | `/api/multiescala/conjuntos` | rota sem tela |
| UX-21-multiescala-sem-tela | parcial | `/api/multiescala/conjuntos/{id}` | rota sem tela |
| UX-21-multiescala-sem-tela | parcial | `/api/multiescala/conjuntos/{id}/macro` | rota sem tela |
| UX-21-multiescala-sem-tela | parcial | `/api/multiescala/execucoes/{id}/micro` | rota sem tela |
| UX-21-multiescala-sem-tela | parcial | `/api/multiescala/fatores` | rota sem tela |
| UX-21-multiescala-sem-tela | parcial | `/api/multiescala/fatores/{id}` | rota sem tela |
| UX-21-multiescala-sem-tela | parcial | `/api/multiescala/fatores/{id}/amostras` | rota sem tela |
| UX-23-mapa-sem-controle | parcial | `/api/anotacoes/{id}` | rota sem tela |
| UX-23-mapa-sem-controle | parcial | `/api/mapa/camadas/{id}/filtrar` | rota sem tela |
| UX-23-mapa-sem-controle | parcial | `/api/mapa/camadas/{id}/selecionar` | rota sem tela |
| UX-23-mapa-sem-controle | parcial | `/api/mapa/pacotes/importar` | rota sem tela |
| UX-23-mapa-sem-controle | parcial | `/api/mapa/selecao-espacial` | rota sem tela |

Itens com efeito visível que não citam página nem rota no texto (131; a cobertura deles é conferida pelo e2e do item, não por este cruzamento): L0-02-b-politica-senha-bloqueio, L0-02-c-2fa-totp, L0-02-d-token-servico, L0-02-f-tela-usuarios, L0-02-g-perfil-usuario, L0-02-tenant-auth, L0-03-b-pastas-tags-categorias-classificacao, L0-03-catalogo, L0-03-d-grupos, L0-03-g-detalhe-item-miniatura, L0-04-d-formatos-base, L0-04-e-formatos-cad, L0-04-h-exportar, L0-04-i-fonte-registrada, L0-04-ingest-vetor, L0-05-d-periodicos, L0-05-e-justica-entre-inquilinos, L0-05-jobs, L0-06-c-restore-drill, L0-06-d-exportar-inquilino, L0-07-b-papeis-privilegios, L0-07-d-smtp-convites, L0-07-e-relatorios, L0-08-c-govbr, L0-08-d-ldap, L0-08-e-mapeamento-provisionamento, L0-09-a-procedencia, L0-09-b-editor-iso-mgb, L0-10-eventos-historico, L0-11-arquivos-objetos, L0-12-contrato-api-e-limites, L0-14-identidade-visual, L1-01-b-validacao-e-isolamento-da-entrada, L1-01-d-garage-por-inquilino, L1-01-f-formatos-de-entrada, L1-01-i-ciclo-de-vida-exclusao-e-coleta-de-lixo, L1-01-ingest-raster, L1-01-j-proveniencia-da-imagem-lastro, L2-01-b-martin-tiles-vetoriais, L2-01-c-lista-camadas-legenda, L2-01-e-mapas-base, L2-01-f-navegacao-medicao-coordenadas, L2-01-g-tabela-atributos, L2-01-h-selecao-filtros, L2-01-i-graficos-de-camada, L2-01-j-comparacao-cortina-tempo, L2-01-mapa-web, L2-02-a-modelo-estilo, L2-02-c-editor-simbologia-vetor, L2-02-d-rotulos, L2-02-e-simbolos-sprites-glifos, L2-03-b-ferramentas-geometria, L2-03-c-formulario-atributos-runtime, L2-03-f-edicao-em-lote-calculo-campo, L2-04-b-featureserver-catalogo-metadados, L2-04-c-featureserver-query, L2-04-f-mapserver-identify-legend-geometryserver, L2-04-h-wfs-2-gml, L2-04-j-conformidade-clientes-e-paridade, L2-04-servicos-esri-ogc, L2-05-a-catalogo-ferramentas-gpserver, L2-05-b-vetor-basico, L2-05-c-sobreposicao-agregacao, L2-05-d-grades-densidade-padroes-interpolacao, L2-05-e-raster-basico, L2-05-f-rede-isocrona-rota-ferramentas, L2-06-a-modelo-painel-fontes, L2-06-b-elementos-basicos, L2-06-c-acoes-seletores-filtros-cruzados, L2-07-b-formulario-de-coleta-xlsform, L2-07-campo, L2-07-e-odk-central-ponte, L2-08-a-leitor-portal-inventario, L2-08-migracao-agol, L2-09-3d, L2-09-c-modelos-gltf-ifc-3dtiles, L2-09-d-analise-3d-visibilidade, L2-10-c-linguagem-expressao, L2-10-d-regras-de-atributo, L2-11-a-geocodificacao-csv, L2-13-a-versoes-ramo-reconciliar, L2-16-c-script-vira-ferramenta, L3-01-b-unidades, L3-01-e-combinacao, L3-01-f-explicacao, L3-01-g-tela-motor, L3-01-h-presets, L3-01-i-exportacao-metodo, L3-04-restricoes, L3-05-localizar-regioes, L3-06-criterios-de-feicao, L3-08-pareto, L3-10-corredor-custo-minimo, L3-14-cobertura-dado-ausente, L3-16-desempenho-escala, L4-04-b-atualizar-e-exportar-subrede, L4-15-serie-temporal-da-rede, L4-parcelas-01-modelo-de-parcelas, L4-parcelas-02-fluxos-cogo, L5-01-a-layout-paginas, L5-01-c-widgets-dado, L5-01-d-widgets-pagina-menu, L5-01-e-acoes-configuraveis, L5-04-a-blocos-de-conteudo, L5-04-c-temas-capa-colecao, L5-06-motor-widgets, L5-07-fontes-vistas-mensagens, L5-08-editor-arrasto, L5-09-desfazer-refazer-rascunho, L5-10-temas-marca, L5-11-expressoes-no-navegador, L5-12-acessibilidade-i18n-construtores, L5-15-vista-movel-responsivo, L5-32-vistas-de-camada, L5-36-widgets-personalizados-sdk, L6-01-b-view-so-leitura, L6-01-d-ficha-fonte, L6-01-g-licenca-curada, L6-02-b-wms-wmts, L6-02-c-wfs-ogcapi, L6-02-conectores-vivos, L6-02-d-arcgis-rest-externo, L6-02-l-saude, L6-02-m-catalogo-endpoints-brasil, L7-08-c-sdk-js, L7-11-c-telemetria-opcional, L7-13-a-chamados, L7-20-trilha-auditoria, UX-07-telas-do-construtor-e-aplicativo, UX-08-telas-rede-de-utilidades-e-motor, UX-15-geocodificador-esri-sem-controle
