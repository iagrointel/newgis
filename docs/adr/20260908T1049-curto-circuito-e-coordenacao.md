# Curto-circuito por barra e coordenação simples: premissa declarada, radial, sem motor novo

Data: 2026-09-08. Item `L4-27-curto-circuito-e-protecao`. Papéis: redes, backend, testador.

## Contexto

O item pede corrente de curto-circuito por barra e verificação de coordenação do dispositivo a montante,
com as premissas declaradas. O `L4_CONCEITO.md` (C12) já decidira que pandapower é o motor de referência
para rede equilibrada e curto-circuito, e o item L4-05-c entregou o CONECTOR: a subrede sai num arquivo
que o pandapower lê. A pergunta deste item é outra: de onde sai o número que a plataforma MOSTRA.

## Decisão

1. **O cálculo é da casa, não de biblioteca importada em tempo de execução.** A plataforma não importa
   pandapower (é a regra do `requirements.txt`, herdada do item L4-05-c: o pacote entra só na suíte). A
   corrente sai de aritmética de sequências sobre o mesmo modelo em memória que os exportadores montam:
   impedância acumulada da fonte até a barra, `Ik3 = c·Un/(√3·|Z1|)` e `Ik1 = √3·c·Un/|2·Z1+Z0|`. É a
   forma da IEC 60909 e do estudo de falta do OpenDSS. Quem quiser o motor completo já tem a porta: o
   exportador pandapower, que este item não toca.
   Alternativa recusada: chamar pandapower no processo da API. Custa uma dependência pesada no caminho
   quente, para resolver uma rede radial cuja resposta é uma soma ao longo de um caminho.
2. **Uma leitura do banco, um modelo.** `opendss.montar_da_subrede` já decide barra, trecho,
   transformador e chave. O curto reusa esse modelo inteiro. Duas regras de conversão para a mesma rede
   seria a forma de o número do mapa discordar do número do arquivo exportado.
3. **Premissa é dado de primeira classe, não configuração escondida.** `plat.rede_curto_execucao` guarda
   as premissas ao lado do resultado, e toda leitura (tabela e camada) as devolve. Sem isso a corrente é
   um número solto, ilegível seis meses depois.
4. **Fonte de impedância nula é recusada.** Não há valor padrão razoável para a potência de curto de uma
   subestação, então não se inventa um: `422`, com o nome do que falta. Corrente infinita não é resultado.
5. **Radial, com o laço declarado.** A impedância é a soma ao longo do caminho de menor impedância até a
   fonte. Onde há malha a corrente sai subestimada, e o resultado carrega o aviso `rede_com_laco` com
   quantos trechos ficaram fora da árvore. Alternativa recusada por ora: montar e inverter a matriz de
   admitância — é o motor completo, é outro item, e prometê-lo aqui seria promessa sem medida.
6. **Sequência zero: razão declarada, e o delta do transformador bloqueia.** O cadastro não traz
   sequência zero. A razão sobre a sequência positiva é premissa (padrão 3,0 na linha, 1,0 na fonte), e ao
   descer pelo transformador delta-estrela o acumulado de sequência zero é zerado, porque o delta bloqueia.
   Está escrito no código porque, para outra ligação, estaria errado.
7. **Sem faixa cadastrada, o veredito é `sem_dado`.** A BDGD não tem campo de faixa de interrupção. Faixa
   suposta faria o painel dizer "coordenado" sobre dado que não existe. No alimentador real medido, 191 de
   192 barras saíram `sem_dado` — e é esse o retrato honesto do cadastro.
8. **Geometria não é copiada.** A camada lê o ponto de `plat.rede_topo_no` pelo identificador escondido no
   nome da barra. Copiar a coordenada criaria uma segunda verdade que envelhece sozinha.

## Consequências

- Toda saída deste item vai para fora com a ressalva "triagem: sinal, não prova" e com as premissas ao
  lado; `docs/PARIDADE.md` registra a capacidade como "além da paridade", nunca como paridade.
- Quem precisar de malha, desequilíbrio ou impedância real de condutor usa o exportador (OpenDSS para
  desequilibrado, pandapower para curto de norma) — a porta já existe e continua sendo a resposta.
- `opendss.montar_da_subrede` passou a devolver, em cada chave, os atributos da feição e as barras em que
  ela caiu depois da fusão. É acréscimo de chave no dicionário; nenhum consumidor existente lê por posição.
