# Painel de observabilidade é arquivo, não estado da interface

Data: 07/09/2026 · item L7-06-d-paineis · situação: aceito

## Contexto

O Grafana deixa criar e editar painel pela tela, e é assim que a maioria das instalações acaba: o
painel que decide se a plataforma está de pé mora dentro do banco de um contêiner, sem histórico, sem
revisão e sem como reinstalar. O item pede o contrário — painel provisionado por arquivo — e pede
prova de que a interface não é uma porta dos fundos.

## Decisão

1. Cada painel é um JSON versionado em `deploy/grafana/paineis/`, com `uid` FIXO igual ao nome do
   arquivo. O uid é a identidade para o Grafana: é ele que faz subir duas vezes dar o MESMO painel.
2. O provedor (`deploy/grafana/provisioning/dashboards/plat.yml`) vai com `allowUiUpdates: false` e
   `disableDeletion: false`. Medido: com isso o Grafana **recusa** apagar pela tela (400 "provisioned
   dashboard cannot be deleted") e, se o arquivo sai do disco, retira o painel e o traz de volta com o
   mesmo uid quando o arquivo volta.
3. A fonte de dado também é arquivo, com `uid` fixo `plat-prometheus` e `editable: false`. Cada painel
   aponta para ela pelo uid, nunca pelo nome — é o que permite o MESMO arquivo servir no Grafana da
   casa e no do appliance sem edição.
4. Painel só cita métrica que existe, e isso é teste, não disciplina: `tests/api/test_paineis_prometheus.py`
   percorre os JSON, resolve as variáveis como o Grafana resolve e pergunta ao Prometheus.
5. `or vector(0)` é permitido **apenas** onde a ausência de série realmente significa zero (contagem de
   erro, contagem de coisa do inquilino) e há teste que impede o uso fora dessa lista. Onde a ausência
   é notícia — backup que nunca rodou, réplica que sumiu — o painel mostra o vazio.

## Consequências

- Reinstalar a observação é copiar arquivos; não há estado a exportar de lugar nenhum.
- Quem quiser mudar um painel abre um pedido de alteração no repositório. Não dá para "arrumar
  rapidinho na tela": a tela recusa.
- No Grafana da casa os painéis entram pelo provedor `iagrointel` que já existe, numa subpasta, porque
  dois provedores sobre os mesmos arquivos brigam. Usar o nosso provedor lá exige recriar o contêiner
  da casa; no appliance, onde o Grafana é nosso, o provedor deste repositório vale inteiro.
- Métrica que o painel precisa e não existe vira migração e coletor, não um número escrito no painel.
  Foi o que aconteceu com usuários ativos em 24 h, duração e tamanho de backup, e uso por inquilino.
