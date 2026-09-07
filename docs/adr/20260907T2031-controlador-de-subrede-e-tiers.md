# Controlador de subrede e tiers (item L4-04-a-controladores-e-tiers)

Data: 2026-09-07. Estado: aceito nesta passagem.

## Contexto

O modelo de rede já tinha tier (`plat.rede_tier`, com `ordem` e `tipo` hierarquico/particionado) e categoria
de rede (`plat.rede_categoria`) desde o pacote de ativos, e topologia derivada (`plat.rede_topo_no`, com um nó
por terminal de dispositivo) desde o item L4-01-b. Faltava dizer ONDE cada subrede começa: o controlador.

## Decisões

1. **A âncora do controlador é a feição de ponto mais o número do terminal, nunca o nó de topologia.**
   `topologia.habilitar()` apaga e refaz `plat.rede_topo_no` inteiro a cada construção; uma chave estrangeira
   para o nó levaria todo controlador junto na primeira reconstrução. O nó corrente é resolvido na leitura
   (`origem_id`/`terminal_num`), e a ficha mostra `no_id` nulo quando a âncora não tem nó — sinal honesto de
   que a topologia precisa ser reconstruída, em vez de um controlador que some.

2. **Nome do controlador e nome da subrede são campos diferentes.** A fonte diz "a unique name for the
   controller in the tier must be provided" e, ao mesmo tempo, "both radial and mesh subnetworks support
   multiple subnetwork controllers". Logo o que não pode repetir dentro do tier é o nome do CONTROLADOR;
   a SUBREDE é a linha de `plat.rede_subrede` que reúne um ou mais deles. No caso comum de um controlador só,
   os dois nomes coincidem, e é isso que a marcação automática faz.

3. **A categoria que habilita o controlador é `controlador`, e o pacote elétrico foi ampliado.** A regra é a
   da Esri: só um tipo de ativo com a categoria de rede atribuída pode controlar uma subrede. No pacote
   `eletrica-br` a categoria `controlador` só estava em regulador de tensão, banco de capacitores e religador;
   os ativos que de fato controlam uma subrede na distribuição — subestação, disjuntor de saída e transformador
   de distribuição — não a tinham. Eles passaram a tê-la (a categoria continua com as anteriores, nada foi
   removido) e a descrição da categoria foi reescrita para dizer as duas coisas que ela significa. Sem isso a
   regra literal do portão ("controlador só em tipo de ativo com categoria `controlador`") e a marcação a
   partir da BDGD seriam incompatíveis entre si.

4. **A subrede nasce suja.** Ciclo de vida igual ao da fonte: a subrede fica suja quando é criada ou quando
   um controlador dela muda, e só vira limpa quando `POST .../subredes/{id}/atualizar` refaz o traçado e grava
   o resumo. Além do estado gravado, a leitura devolve `suja` sempre que existir área suja aberta na rede
   (edição depois da última construção da topologia) — os dois valores aparecem lado a lado (`estado` e
   `estado_gravado`) para que ninguém confunda "o registro está limpo" com "o chão está limpo".

5. **A marcação automática nunca inventa terminal.** `POST .../controladores/importar` prefere sempre o
   terminal de um dispositivo real. O nó de cabeça, usado quando o arquivo não traz o equipamento de saída da
   subestação, é uma CONVENÇÃO declarada (nó do alimentador mais próximo do centróide dos trechos de média
   tensão da mesma subestação, proxy da posição dela) e fica gravado com `origem='no_de_cabeca'`, para que
   nenhuma leitura o confunda com um terminal lido do arquivo.

## O que ficou de fora

- **Grupo de tier (tier group).** O modelo vai de domínio direto a tier. A fonte exige grupo de tier em
  domínio hierárquico e o dispensa em domínio particionado (elétrica e telecom) — o pacote entregue é
  justamente o caso dispensado, mas água e gás hierárquicos precisariam do nível intermediário. Lacuna
  nomeada em `docs/PARIDADE.md`; nenhum item da linha L4 a cobre hoje.
- **`papel` (fonte/sumidouro) ainda não muda o traçado.** O campo é gravado e exposto; o sentido do traçado
  continua vindo da direção de fluxo declarada no trecho (item L4-18).
- **Camada `SubnetLine`.** O resultado do traçado da subrede é devolvido na resposta de `atualizar` e não é
  materializado como camada.
