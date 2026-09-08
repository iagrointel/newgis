# Fontes, vistas e barramento de mensagens do app (item L5-07-fontes-vistas-mensagens)

Data: 08/09/2026. Estado: aceito. Par: `laco/decomposicao/L5_CONCEITO.md` D4 (fontes/vistas/CQL2) e D5
(barramento); ADR `20260907T1930-motor-de-widgets` (L5-06, base) e `20260907T0302-editor-de-arrasto-compartilhado`.

## Decisões

1. **Modelo em três listas do `corpo`** (`fontes`, `vistas`, `mensagens`), esquema 3 do documento `app`
   (migração `20260908T1040`; v2 migra na leitura com listas vazias). Widget liga a vista por
   `configuracao.vista`; vista liga a fonte por `fonte`; mensagem liga por ids de widget ou vista. Nada por posição.
2. **Toda regra em código puro sem DOM, duas vezes**: `web/js/app/{cql2,modelo,vistas,barramento,estado_url}.js`
   (navegador e node) e `app/app_modelo/validar.py` (servidor). O teste de unidade roda os dois sobre os mesmos
   corpos e exige as mesmas listas de erro; a API recusa (422 `modelo_invalido`) exatamente o que o construtor recusa.
3. **Filtro é CQL2-JSON** (D4). O navegador avalia em memória (todas as feições da fonte carregadas; o portão
   mede 10 mil) e aceita CQL2-text na entrada. `s_intersects` no navegador é por envelope; interseção exata é
   do servidor (L2-04-g), que compila o mesmo JSON para SQL.
4. **Barramento = EventTarget + volta com corte** (D5). Um gatilho de fora abre uma volta; cada mensagem roda
   no máximo uma vez por volta; a segunda passagem é cortada com `aviso` `ciclo_cortado`. Relação entre fontes
   resolvida no barramento: mesma_fonte passa ids/filtro; atributo vira `in` no campo do alvo com os valores da
   origem; espacial vira `s_intersects` com o envelope da origem. Latência medida por gatilho (`p95()`).
5. **Estado na URL por vista** (`v.<id>` = base64url de {f, s}), restaurado ANTES de o barramento ouvir as
   vistas — senão o estado restaurado redispararia as mensagens ao abrir.
6. **Widget de mapa desenha a vista em SVG.** Projeção do envelope da vista para a caixa do widget; clique,
   seleção (shift acumula), extensão (`zoom`/`pan` emitem `extensao_mudou`), `popup` (`<dialog>`), `piscar`.
   MapLibre por baixo e simbologia são o L5-01-b; este renderizador continua sendo a camada de dado do widget.
7. **Painel "Dados e mensagens" no construtor** (`web/js/app/painel_dados.js`): coleções vivem fora do editor de
   nós (que troca o objeto do documento a cada edição) e entram no corpo na gravação; recusa antes de inserir,
   com a regra nomeada em `#mensagem-erro`; erro do modelo bloqueia o Salvar.

## Fora deste item
Seguir feição ao vivo (Dashboards "follow feature"), fonte de fluxo (L2-14-a), CQL2 espacial exato no navegador,
edição de mensagens existentes (só adicionar/remover), i18n do painel (L5-12 cobre os construtores de uma vez).
