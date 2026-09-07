# ADR 20260907T1434 — modo somente-leitura/manutenção global e por inquilino (item L7-33-modo-somente-leitura)

Contexto: paridade com o `mode` do ArcGIS Portal for ArcGIS (`READ_ONLY`/`READ_WRITE`, endpoint
`portaladmin/mode`) e o site mode `READ_ONLY` do ArcGIS Server (bloqueia publicação/edição, mantém
serviço); usado pela atualização (L7-14), failover (L7-07-c) e licença vencida (L7-11-a) desta
plataforma, que ainda não existem — este item entrega só o mecanismo e a CLI, os três consumidores
futuros o chamam quando forem construídos.

## D1. Bandeira em `plat.sistema`, nunca em variável de processo

`plat.sistema` (chave/valor jsonb + motivo/quem/quando) e `plat.sistema_trilha` (histórico append-only
de cada ligar/desligar) — migração `20260906T2109_modo_manutencao.sql`. Uma variável de ambiente ou um
arquivo de lock exigiria reiniciar/tocar todo processo (API + worker + réplicas futuras) para propagar;
a bandeira no banco é lida por `plat.modo_ler()` (SECURITY DEFINER, STABLE) a cada requisição de
escrita, sem cache — o efeito é imediato em todos os processos ao mesmo tempo. Escopo: **global vence
sempre**; sem flag global, vale a do inquilino da credencial. `plat.modo_chave()` normaliza a chave
(`modo_manutencao` ou `modo_manutencao:tenant:<id>`) para as duas funções de escrita nunca divergirem.

## D2. Motivo obrigatório nos dois sentidos (ligar E desligar), gravado por SQL, não só pela CLI

`plat.modo_ligar`/`modo_desligar` recusam (`RAISE EXCEPTION`) motivo nulo ou só espaço — checagem no
SQL, não só no `argparse` da CLI (`app/cli.py`), porque a função é `SECURITY DEFINER` e pode em tese ser
chamada por outro caminho no futuro; a casca não pode ser a única guarda. Cada chamada grava uma linha
em `plat.sistema_trilha` (ligar E desligar, nunca só um dos dois) — é a prova de quem mexeu, quando e
por quê, exigida pelo portão do item. Só a role `plat_worker` tem `EXECUTE` nas duas funções (`REVOKE
... FROM PUBLIC, plat_app`): ligar/desligar é operação de infraestrutura, nunca da API — a aplicação
nem tenta.

## D3. Middleware ASGI puro, nunca `@app.middleware("http")`

Mesma decisão e mesmo motivo de `app/limite_corpo.py`: o repositório já mediu que uma exceção lançada
durante a leitura do corpo dentro de `BaseHTTPMiddleware` vira "There was an error parsing the body"
genérico do Starlette em vez do contrato de erro da casa. Este middleware TAMBÉM lê o corpo (a isenção
de `POST /api/jobs` precisa do JSON para decidir o tipo) e precisa devolver a resposta 503 no formato
`corpo_erro` (ADR 0002 seção 14) com certeza — ASGI puro dá controle total sobre isso. O corpo lido é
sempre reproduzido íntegro para a rota via um `receive()` substituto (mesmo padrão de
`LimiteCorpoMiddleware`), nunca perdido.

Instalado em `app/main.py` ANTES de `auth_middleware.instalar(app)`: no empilhamento do Starlette o
middleware acrescentado por último é o mais EXTERNO — instalando o de modo primeiro, ele roda DEPOIS do
de log/sessão na cadeia de pedido, e a escrita bloqueada sai com `X-Req-Id` e uma linha em
`plat.log_acesso` (a recusa fica auditável no mesmo lugar de qualquer outra resposta).

## D4. Duas isenções por desenho, não por lista arbitrária: sistema da própria plataforma, e o tipo de job que só lê

Isentos fixos: `/saude`, `/api/versao` (o par real de monitoramento desta plataforma — a hipótese do
item citava `/status`, que não existe neste código; nenhuma trilha registrou essa rota, ver
`app/main.py`), `/api/modo` (a própria consulta, que a faixa do front lê), e login/logout — entrar e
sair grava linha em `plat.sessao`, mas é escrita de SISTEMA (como a do worker), não do dado do
inquilino; bloquear login deixaria até o operador do lado de fora, e no `READ_ONLY` do ArcGIS Server o
usuário também continua entrando para consultar.

A isenção não trivial é `POST /api/jobs` de um tipo declarado `somente_leitura=True` no registro Python
(`app/jobs/registro.py::tarefa`, campo novo desta sessão) — hoje só `catalogo.exportar_lista`. A marca
é congelada na COLUNA `plat.job.somente_leitura` no momento da criação (não relida do registro depois),
então mudar a declaração de um tipo no futuro nunca reabre a fila para jobs já criados. `somente_leitura`
recusa combinar com `somente_sistema` (item L0-07-d): são eixos ortogonais — um tipo interno nem passa
pela rota, a isenção do modo não lhe diz respeito. Tipo desconhecido, corpo que não é JSON, ou tipo
comum: fecham (503) — a isenção nunca é o caminho padrão.

`plat.job_pegar` ganha a mesma cláusula do lado do SQL: `(j.somente_leitura OR NOT
plat.modo_bloqueia(j.tenant_id))` — sem isso, o job seria aceito na criação mas nunca retirado da fila,
uma isenção que engana. Um job comum já pendente ANTES do modo ligar (por exemplo, atrás de outro na
cota de simultâneos do inquilino) fica retido pela mesma cláusula até desligar; o job já `rodando` no
momento de ligar não é tocado (a cláusula só filtra o que ainda vai ser retirado da fila).

## D5. Front: uma função, chamada de dois lugares, sem estado próprio

`web/js/base/modo.js::aplicarFaixaModo()` consulta `GET /api/modo` (público, sempre 200) e insere/remove
a faixa no topo do `body`; chamada por `exigirSessao` (toda tela autenticada) e por `/entrar` (quem
ainda não tem sessão também precisa ver a manutenção global). O texto da faixa é o MESMO `motivo` que a
API devolve no `detalhe` do 503 — o usuário lê a mesma frase na faixa e na mensagem de bloqueio, nunca
dois textos que podem divergir.

## O que fica de fora desta passagem (nomeado, não escondido)

- **Consumidores** (atualização L7-14, failover L7-07-c, licença vencida L7-11-a): nenhum existe ainda
  nesta plataforma; este item entrega o mecanismo que eles vão chamar, não a automação que liga o modo
  sozinha.
- **Silenciamento de alerta durante o modo** (L7-06-b, cláusula do portão): `app/saude.py::estado_modo()`
  expõe `manutencao.ativo` em `/saude` — é o ponto de leitura que o consumidor de alerta (também ainda
  não construído) vai checar antes de disparar; não há motor de alerta nesta plataforma para provar o
  silenciamento ponta a ponta hoje.
- **Pedido anônimo e modo por inquilino**: sem credencial não há inquilino para resolver — pedido
  anônimo só enxerga o modo GLOBAL (limitação declarada, não bug).
