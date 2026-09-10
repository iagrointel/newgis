# Ordem entre rota de segmento fixo e rota parametrizada

Estado: aceito (item L0-04-k-rota-formatos-encoberta, setembro de 2026)

## Contexto

O roteador testa as rotas na ordem em que foram declaradas, e um segmento `{param}` casa qualquer segmento
sem barra. `GET /api/importacoes/formatos` estava declarada depois de `GET /api/importacoes/{id}`: toda
chamada a `/formatos` era atendida pela outra rota, que lia `formatos` como identificador e respondia 404
`importacao_inexistente`. O caso em `tests/api/cruzado_casos.py` declarava 200 e o defeito passou meses sem
ser visto porque a suíte cruzada aceita 404 como resposta legítima de rota de recurso alheio.

## Decisão

1. Em cada arquivo de rotas, a rota de segmento fixo é declarada ANTES da rota parametrizada do mesmo
   prefixo. É a única forma de a fixa ser alcançável; não há configuração de prioridade a ajustar.
2. `tests/unit/test_rotas_sombreamento.py` varre a aplicação viva inteira e reprova qualquer par com essa
   inversão, nomeando as duas rotas e o método. A varredura acha as rotas achatando os nós de router
   incluído (`effective_candidates`): a partir do FastAPI 0.138 `app.routes` guarda um nó por router, e um
   `getattr(r, "path")` cru enxerga 3 rotas onde há 236 — foi assim que `tests/api/test_versionamento.py`
   passou a varrer quase nada sem ninguém notar.
3. A rota de formatos passou a exigir sessão ou token autenticado (`autenticado(escopo_token="catalogo:ler")`),
   sem privilégio nenhum, que é o que ela já declarava no OpenAPI (`x-auth: S/T`, `x-privilegio: proprio`).
   Enquanto estava encoberta ninguém percebia a divergência entre a declaração e o comportamento; alcançável
   e anônima, ela quebrava a varredura cruzada de inquilino.

## Consequências

Rota nova de segmento fixo abaixo de um prefixo que já tem `{id}` precisa ser declarada acima dela, senão a
varredura reprova o lote. A varredura é de unidade (não sobe banco nem servidor) e custa uma importação da
aplicação.
