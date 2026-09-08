# FASE 2 — painel vivo e supervisor (06/09/2026)

Entregues três arquivos. O gerador de prompt (`prompt_item.py`) já existia e não foi tocado.

| arquivo | o que é |
|---|---|
| `laco/painel_vivo.py` | coletor: grava `laco/vivo/agora.json` |
| `laco/vivo/painel.html` | página única que lê o `agora.json` |
| `laco/supervisor.py` | laço que lança e reconcilia agentes |

## 1. `painel_vivo.py`

Grava `vivo/agora.json` com: placar; itens em movimento (estado, tentativas, agente e há quanto
tempo, último commit, bloqueio, dependências abertas); agentes vivos; fila de merge; commits por
hora nas últimas 24 h; achados de adversário abertos; recursos.

Cadência por preço da fonte, não por gosto:

| fonte | cadência | por quê |
|---|---|---|
| recursos (`/proc`, `statvfs`) | 5 s | leitura local, custo desprezível |
| `estado.json` | só quando o `mtime` muda | arquivo de 1,07 MB, relido à toa custaria mais que tudo o resto junto |
| `git log` dos worktrees | 30 s | 11 árvores, cada uma com `rev-list` e `status` |
| conexões do Postgres | 15 s | UMA conexão psycopg2 mantida aberta (`application_name=painel_vivo`), com queda para `sudo -u postgres psql` se ela cair |

Escrita atômica (temporário no mesmo diretório mais `os.replace`), como em `marcar_item.py`.
`--uma-vez` colhe uma vez. `--servir` sobe servidor mínimo em 127.0.0.1:8159 servindo só
`laco/vivo/`, com `Cache-Control: no-store` e `X-Robots-Tag: noindex`.
Instância única sob `flock laco/.painel.lock`: o painel não pode disputar recurso.

Medido: primeira volta 0,64 s; `agora.json` com 34 KB; processo em 31,7 MB de RSS e 0,5 % de uma
CPU; a porta 8159 aparece em `ss -ltn` só em 127.0.0.1.

Itens: o arquivo não carrega os 506. Carrega os 71 que estão em movimento (tudo que não é
`pendente`, mais qualquer item com agente ou com bloqueio). O resto entra agregado por linha.

## 2. `vivo/painel.html`

Uma página, sem compilação, sem biblioteca externa, sem emoji, tudo em português. Fundo escuro,
fonte de largura fixa, sete seções: progresso por linha L0 a L7 (barra empilhada entregue /
parcial / refutado / tentando), agentes vivos com tempo decorrido e última linha do log, achados
de adversário abertos em vermelho, fila de merge (commits à frente do master, arquivos, arquivos
não commitados, arquivos quentes em vermelho), itens em movimento, commits por hora em barras e
últimos commits. Recarrega o `agora.json` a cada 5 s.

A faixa de recursos fica amarela quando a memória disponível cai abaixo de 4 GB ou as conexões
passam de 70 de 100, e vermelha abaixo de 2 GB, acima de 90 conexões ou com o disco de `/` em
98 %. Se o `agora.json` tiver mais de 30 s, a página escreve COLETOR PARADO no cabeçalho — o
painel não finge que o dado é de agora.

Conferência estrutural (o Chrome sem cabeça quebra nesta máquina): toda chave `d.<campo>` lida
pelo JavaScript existe no `agora.json` e todo `#id` usado tem elemento correspondente no HTML.

## 3. `supervisor.py`

Volta a cada 20 s: colhe processos, reconcilia mortos, publica o instantâneo, lança até o teto.
Instância única sob `flock laco/.supervisor.lock`.

**Adoção.** O registro de cada agente (`vivo/agentes/<id>.json`) guarda pid E `starttime` do
campo 22 de `/proc/<pid>/stat`. Vivo só quando os dois batem, porque o núcleo recicla número de
processo. Testado: um registro com pid de processo vivo e `starttime` errado foi classificado como
morto, e um com os dois certos foi adotado.

**Teto efetivo** = menor entre memória `(disponível − 3500 MB) / 250 MB`, conexões (zero acima de
70 de 100), cota e rendimento, nunca acima de 8. Rendimento: com dois ou mais agentes vivos e
nenhum commit no repositório há 45 min, o teto para de crescer.

**Cota.** É falha correlacionada: derruba todos ao mesmo tempo. Detecção: saída em menos de 3 min
com o log casando `429|rate limit|usage limit|session limit|quota`. Ao detectar, pausa tudo
(teto zero) e volta com espera de 5, 10, 20, 40 e 60 min; ao fim da espera entra em fase de teste
com teto 1 e só reabre a corrida quando o agente de teste passa de 6 min vivo. Morte por cota e
morte por falta de memória não contam tentativa contra o item. Testado em modo seco: um registro
com log de 429 e 90 s de vida levou o teto a zero e a pausa a 5 min.

**Veneno.** Três tentativas com causa que não é cota nem falta de memória e o item vira
`pendencia_declarada`, sai da fila e leva junto o fecho transitivo de quem dependia dele.

⚠ Achado que mudou o desenho: um único item envenenado arrasta muita coisa. Com
`L2-01-mapa-web` como raiz, o arrasto é de **177 dos 506 itens** (35 %) — `L7-05-producao-final`
sozinho depende de 23 itens da cascata. Gravar isso no `estado.json` sem ninguém decidir seria
apagar um terço do backlog. Regra adotada: acima de 25 itens, todos saem da fila (ficam na memória
do supervisor, em `vivo/supervisor.json`), mas só as raízes são gravadas no `estado.json`, e o
supervisor escreve um aviso dizendo que o cancelamento em massa é decisão do dono.

**Arquivo quente por arrendamento** (`vivo/leases/`): um agente por vez em `app/main.py`,
`app/jobs/tipos.py`, `CHANGELOG.md`, `docs/PARIDADE.md`, `MANUAL.md`, `ARQUITETURA.md`,
`install.sh`, `docs/openapi.json`, `tests/api/cruzado_casos.py`, `tests/api/eventos_esperados.py`.
O arrendamento só é pedido quando o texto do próprio item cita o arquivo. Se todo item pedisse o
`CHANGELOG.md`, a corrida inteira viraria uma fila de um agente — o critério é o texto do item,
não a suposição.

**Lançamento.** `/home/dev/.local/bin/claude -p "$(cat vivo/prompts/<item>.md)"
--dangerously-skip-permissions`, um por volta (ou seja, um a cada 20 s) mais uma variação
aleatória de 0 a 6 s, com `start_new_session=True` para o agente sobreviver à morte do supervisor.
Registro em `vivo/agentes/<id>.json` com pid, starttime, item, início, log, tentativa e
arrendamentos. Log em `vivo/logs/<id>.log`. Se o prompt não existir, é gerado com `prompt_item.py`.

**Escrita no `estado.json`** só através do `marcar_item.py`, que já trava em `.estado.lock`:
`tentando` ao lançar, `pendente` quando o agente morre sem entregar, `pendencia_declarada` no
veneno. `--sem-estado` desliga isso; `--seco` desliga tudo.

## Como ligar

    python3 /home/dev/plataforma/laco/painel_vivo.py --servir &      # painel em 127.0.0.1:8159
    python3 /home/dev/plataforma/laco/supervisor.py --seco           # ver a decisão
    python3 /home/dev/plataforma/laco/supervisor.py --teto 4         # ligar de verdade

O supervisor NÃO ficou ligado. Entregue testado em modo seco.

## Limitações honestas

- O supervisor lança um construtor por item. Não lança adversário; `sem_adversario.py` continua
  sendo a fila de ataque, à mão.
- A causa da morte é lida do fim do log (8 KB) e da duração. Agente que morre calado e sem log vira
  causa "outra" e conta tentativa — é o lado conservador do erro, mas é um erro possível.
- O sinal de rendimento olha o commit mais novo de qualquer ramo do repositório, não commit por
  agente. Um agente produtivo mascara três parados.
- `laco/` não é repositório git, então não há commit destes arquivos. Quem versiona é
  `plataforma/enterprise`, e estes três arquivos são ferramenta do laço, não produto.
