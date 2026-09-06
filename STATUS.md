# Status da corrida — 06/09/2026 17:50 UTC

Gerado de `laco/estado.json` pelo supervisor. `#` provado (portão passou e adversário não refutou) · `~` parcial (cláusula pendente nomeada) · `!` refutado pelo adversário, conserto em curso · `.` não iniciado.

**22 provados · 17 parciais · 39 refutados · 428 na fila · 506 itens**

```
L0 fundação              #######~~~!!!!!!!!!!!!!!!!..............   12/72
L1 imagens               !.......................................    0/65
L2 plataforma            ##~~....................................    4/100
L3 motor multicritério   ~!......................................    0/34
L4 rede de utilidades    #.......................................    1/66
L5 construtores          #.......................................    1/61
L6 conectores            #####~~~~~~~~!..........................    4/32
L7 operação              !!!!....................................    0/75
```

## Como um item vira "provado"

```
FABLE dirige · elege itens · junta os ramos · arbitra
   |
   +--> SONNET constrói ou conserta em worktree próprio, base de banco própria
   |          |  commit no ramo wt/<item>
   v          v
FILA DE JUNÇÃO  lote de 6-11 ramos · suíte inteira uma vez por lote · bisseção acha o culpado
   |
   v
ADVERSÁRIO  agente separado que não viu a construção · suposições transversais da linha primeiro
   |         · achado vira teste xfail(strict=True)
   +--> achou? volta para SONNET consertar --> fila --> até o adversário não achar nada
```

## Leitura honesta

O vermelho não é trabalho perdido. São itens que estavam marcados como prontos e caíram quando um adversário independente os verificou: de 60 itens declarados entregues ou parciais no início de 06/09, só 8 tinham laudo; dos verificados, 7 em 8 caíram, com achados de segurança reais (validação de imagem que saía para a rede, segredo de banco vazando para processo filho, cadeia de assinatura de pacote que aceitava chave de terceiro, segredo de armazenamento igual em produção e homologação). Cada conserto entra com o teste do ataque junto.

O padrão que explica quase tudo o que caiu: **o que é protegido por linha aguentou todos os ataques; o que é recurso partilhado (fila, trinco, schema de dados, contador de cota, porta, nome de tarefa agendada, permissão de função) não tinha dimensão de inquilino nenhuma.**

## Onde está cada coisa

- `PLANO_DA_CORRIDA.md` — o plano aprovado pelo dono (tiro único, repartição por modelo, fases).
- `docs/adr/` — decisões de arquitetura, uma por arquivo.
- `CHANGELOG.md` — o que mudou, por item.
- `db/migracoes/` — migrações; as novas usam carimbo de tempo (`YYYYMMDDTHHMM_<nome>.sql`), o legado numérico é imutável.
- Ramos `wt/<item>` — um worktree por item; entram em `master` só pela fila de junção.
