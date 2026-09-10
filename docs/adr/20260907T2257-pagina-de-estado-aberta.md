# Página de estado da instalação: aberta, agregada e com histórico no banco (item L0-06-e-status)

Data: 2026-09-07. Estado: aceito.

## Contexto

O item pede uma página `/status` e um `GET /api/status` que digam, sem sessão, como está a instalação:
serviços, migrações, fila, última cópia de segurança, último ensaio de restauração, espaço em disco e no
armazenamento de objetos, certificado, 90 dias de histórico com percentual de disponibilidade do mês e o log
de correções. Já existiam `/saude` (item L0-06 original) e `/saude/profunda` (L7-34, sondas por componente com
versão anônima e versão de superadmin).

## Decisões

1. **Reusar as sondas do `/saude/profunda`, não escrever outras.** `app/status.py` importa `_sondar`,
   `_servico_simples`, `_disco`, `_certificado` e `pior_estado`. Duas listas de sondas divergiriam em uma
   semana, e a página diria uma coisa enquanto o health check diz outra.

2. **A resposta é só agregado.** Sem versão da aplicação, sem `git_sha`, sem alvo `host:porta`, sem nome de
   volume, sem slug de inquilino, sem nome de bucket. O detalhe continua atrás de sessão de superadmin, no
   `/saude/profunda`. O log de correções, que vem do CHANGELOG escrito para dentro de casa, passa por uma
   higienização (trecho de código, caminho, número de versão e nome de dependência viram reticências) e a
   frase que só sobra em pedaços não entra. Isto não é zelo teórico: o teste de vazamento reprovou de verdade
   na primeira rodada, por causa de uma frase do CHANGELOG que citava a biblioteca de acesso ao banco.

3. **Cache de 30 s no processo, não no CDN.** A página é aberta e o mesmo retrato serve a todo mundo; sem
   cache, cada visita abriria conexão de banco e sondaria seis serviços. Medido: 1.000 pedidos em 20 conexões
   levaram 1,07 s, todos servidos do cache, nenhuma consulta ao banco. O cabeçalho continua `no-store` — quem
   guarda o retrato é o processo, que sabe quando ele venceu; proxy nenhum guarda.

4. **O histórico mora no banco, medido pelo mesmo código que a página serve.** O periódico `status.amostrar`
   (a cada 5 minutos) chama `retrato()` e grava uma linha por serviço em `plat.status_amostra`; o percentual do
   mês é recalculado dessas linhas a cada pedido, por `plat.status_disponibilidade`. Nada de contador acumulado
   em memória, que ninguém consegue auditar depois. `ausente` (subsistema que não existe nesta topologia) fica
   fora do denominador: não é queda.

5. **`estado` geral olha só os serviços.** Disco cheio e certificado a vencer aparecem na página com o seu
   próprio estado, mas não derrubam o `200` para `503` — a rota também serve de sonda de balanceador, e um
   disco a 5 % livre não é motivo para tirar a instalação do balanceamento. O `/saude/profunda` continua sendo
   o lugar onde qualquer componente degradado vira `503`.

6. **Espaço no armazenamento de objetos por `GetClusterStatistics`, não por bucket.** A primeira versão somava
   `GetBucketInfo` de cada bucket: 200 chamadas, 5.272,8 ms por retrato, medido. A chamada única do Garage
   devolve buckets, objetos, tamanho e espaço livre e derrubou o retrato inteiro para 92 ms. O relatório vem em
   texto e traz o nome da máquina de armazenamento junto — por isso só os números são extraídos, e o texto
   nunca é repassado.

7. **`X-Robots-Tag: noindex, nofollow` passou a valer para TODA página servida por `app/paginas.py`**, não só
   para `/status`. Todas já traziam a meta `noindex` no HTML; a meta só vale para quem interpreta o HTML.

## Consequências

- O campo do ensaio de restauração responde `indisponivel` com a razão enquanto `plat.backup_drill_status()`
  (item L0-06-c) não estiver em master; quando entrar, a mesma chamada passa a responder sozinha.
- Quem acrescentar um serviço à instalação precisa acrescentá-lo a `SERVICOS_AMOSTRADOS` para que ele entre no
  histórico; serviço fora dessa lista aparece no `/saude/profunda` mas não na disponibilidade do mês.
