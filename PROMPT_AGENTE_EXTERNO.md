# Prompt para o programador externo (frente L4–L7)

Cole este arquivo inteiro como primeira mensagem para quem for trabalhar de fora do servidor.
Ele vale junto com `CONTRIBUIR.md` (contrato de ramo) e `RECONSTRUIR.md` (como subir a máquina).
Quem está do lado de dentro do servidor trabalha em L0–L3 e revisa o que chega por ramo.

---

## 1. O que é este sistema

Plataforma SIG própria, em pilha aberta, para substituir o ArcGIS Enterprise: catálogo de itens,
serviços de feição e de imagem, mapas, visualizador, construtor de aplicação, conectores de dado,
motor de análise multicritério e operação (backup, log, homologação, atualização). Roda hoje em
produção interna, com dado real, banco PostgreSQL/PostGIS (schema `plat`), API em FastAPI e
frente em JavaScript sem framework de terceiros. Não é protótipo: o que entra em `master` está no ar.

O plano de construção inteiro está em `laco/estado.json`: **506 itens** em oito linhas (L0 a L7),
cada um com hipótese, portão de pronto literal e refutação escrita antes de o código existir.
Placar em 06/09/2026: 26 entregues, 23 parciais, 30 refutados, 3 turnos rodados.

| linha | tema | entregue | parcial | total |
|---|---|---|---|---|
| L0 | fundação (identidade, catálogo, jobs, limites) | 17 | 11 | 72 |
| L1 | imagens (COG, STAC, mosaico, serviço de imagem) | 0 | 0 | 65 |
| L2 | plataforma (feições, edição, expressão, relações) | 4 | 5 | 100 |
| L3 | motor AMC (análise multicritério explicável) | 0 | 1 | 34 |
| **L4** | **rede de utilidades (topologia, regras, traçado)** | **1** | **0** | **66** |
| **L5** | **construtor de aplicação (builder, popup, formulário)** | **1** | **0** | **61** |
| **L6** | **conectores (fonte externa, procedência, licença)** | **3** | **6** | **32** |
| **L7** | **operação (backup, segredo, auditoria, homologação)** | **0** | **0** | **76** |

## 2. Divisão de frente (é isto que muda com você entrando)

- **Você: L4, L5, L6, L7.** 235 itens, 20 desbloqueados agora.
- **Servidor (a outra frente): L0, L1, L2, L3.** 271 itens.
- Ninguém pega item fora da sua faixa sem combinar antes. Se o seu item precisar de algo de L0–L3,
  escreva a dependência no repasse e siga com o que dá para provar sem ela — não construa o item
  do outro por conta própria.
- Exceção nomeada: **`L6-02-a-modelo-conexao-e-seguranca` está sendo construído no servidor agora
  mesmo** (trabalho ainda não commitado em `app/conexao/`). Não pegue esse. Todos os outros de L6
  estão livres.

## 3. Onde está tudo

```bash
git clone git@github.com:iagrointel/newgis.git
cd newgis
python3 -m venv venv && venv/bin/pip install -r requirements.txt   # GDAL 3.8 do sistema
```

| você quer | leia |
|---|---|
| o plano inteiro, item a item | `laco/estado.json` (campo `backlog`) |
| o contrato de um ramo vindo de fora | `CONTRIBUIR.md` |
| subir o sistema do zero em outra máquina | `RECONSTRUIR.md` |
| como o sistema é por dentro | `ARQUITETURA.md`, `docs/adr/` |
| o que o usuário vê e faz | `MANUAL.md` |
| o que já foi entregue, com número | `CHANGELOG.md`, `tests/medidas/*.json` |
| o que cada item entregue provou | `laco/handoffs/T<turno>/<item>.md` |
| paridade com o ArcGIS, capacidade a capacidade | `docs/PARIDADE.md` |

Ler o portão do seu item:

```bash
venv/bin/python - <<'PY'
import json
d=json.load(open('laco/estado.json'))
for it in d['backlog']:
    if it['id']=='L4-01-b-topologia-derivada':          # troque pelo seu
        print(it['hipotese']); print('---PORTAO---'); print(it['portao_de_pronto'])
        print('---REFUTACAO---'); print(it['refutacao']); print('---DEPENDE DE---', it['dependencias'])
PY
```

Listar o que está desbloqueado na sua faixa (dependências já entregues):

```bash
venv/bin/python - <<'PY'
import json
d=json.load(open('laco/estado.json')); b=d['backlog']
ok={i['id'] for i in b if i.get('estado') in ('entregue','parcial')}
for it in sorted(b,key=lambda i:(i.get('prioridade',9),i['id'])):
    if it['linha'][:2] in ('L4','L5','L6','L7') and it.get('estado') in ('pendente','refutado') \
       and not [x for x in it.get('dependencias',[]) if x not in ok]:
        print(it['linha'][:2], 'p%s'%it.get('prioridade'), it.get('tamanho'), it['id'])
PY
```

## 4. Por onde começar (o difícil, que é o que você pediu)

Em ordem de valor. Os dois primeiros são o coração da linha de rede de utilidades e é onde o
ArcGIS cobra caro; ninguém no Brasil entrega isso em pilha aberta.

1. **`L4-01-b-topologia-derivada`** (grande, prioridade 1) — as camadas de rede continuam camadas
   normais e editáveis; a topologia é um índice DERIVADO (`plat.rede_topo_*`), reconstruído por
   `POST /api/v1/rede/{id}/topologia/habilitar`. O portão exige construir a topologia da rede de
   teste (44.268 trechos de média tensão, 29.244 de baixa, 26.581 ramais, 5.481 transformadores,
   60.549 postes) com tempo medido; contagem de nós, arestas, nós órfãos e arestas sem nó gravada
   e conferida contra o arquivo de origem; tolerância de coincidência como parâmetro da rede;
   RLS e índice espacial na tabela de topologia; **um ponto a 0,04 m de um vértice conecta e a
   0,06 m não conecta** (teste); e `docs/rede/TOPOLOGIA.md` com a paridade contra *enable topology*.
   O adversário vai deslocar um vértice em 0,10 m, contar nós de grau 1 e cruzar dois trechos sem
   nó para conferir que **cruzar não é conectar**.
2. **`L4-03-a-regras-de-conectividade`** (médio, prioridade 1) — regras como linhas de tabela
   (`plat.rede_regra`), pacote elétrica-BR com **≥ 40 regras**, `applyEdits` que liga média tensão
   direto a unidade consumidora de baixa é recusado com código e mensagem que **cita a regra**,
   exportação e reimportação de CSV dá o mesmo conjunto, **"sem regra = proibido" é o padrão**,
   ≥ 20 casos em pytest, paridade escrita.
3. **`L7-19-segredos-e-certificados`** (médio) — tirar segredo do `.env` em texto e passar para
   `LoadCredential=` do systemd.
4. **`L7-20-trilha-auditoria`** (médio) — `plat.auditoria` append-only, sem UPDATE nem DELETE para
   `plat_app`, com gatilho que impede alteração.
5. **`L4-06-d-categorias-e-restricoes`**, **`L6-01-e-assinatura-e-uso`**, **`L7-31-ambiente-homologacao`**,
   **`L7-33-modo-somente-leitura`**, **`L7-03-f-dependencias-cve`**, **`L7-16-assinatura-pacote`** — os
   pequenos, bons para o primeiro ramo se você quiser calibrar o processo antes do L4-01-b.

## 5. Como entregar (contrato curto; o longo está em CONTRIBUIR.md)

1. Um ramo por item, criado de `master`, nome **`wt/<id-do-item>`**. Nunca commite em `master`.
2. Commit em **português**, sem emoji, `git add <arquivo>` explícito — nunca `git add -A`.
   Rodapé obrigatório em todo commit: `Item: <id-do-item>`.
3. **O portão é literal.** Cada cláusula vira teste automatizado ou medida gravada em
   `tests/medidas/<id-do-item>.json`, com o comando que gerou o número dentro do próprio JSON.
   Cláusula que você não provou fica escrita como fronteira no repasse — **nunca como entregue**.
4. Repasse em `laco/handoffs/T3/<id-do-item>.md`: o que foi construído (arquivos), cláusula → prova
   (comando e saída), o que ficou de fora e por quê, limitações honestas, comandos para o adversário
   reproduzir, lista dos commits. Sem isso o ramo não é avaliado.
5. Migração nova: `db/migracoes/YYYYMMDDTHHMM_<nome>.sql` (carimbo de tempo, para não colidir com
   quem numera em sequência do outro lado), idempotente (`IF NOT EXISTS`), **RLS por inquilino em
   toda tabela com `tenant_id`**, e `REVOKE ... FROM PUBLIC` antes de qualquer `GRANT EXECUTE`.
   Nunca renomeie migração que já existe.
6. Antes de abrir o ramo para revisão, tem de passar na sua máquina:
   `venv/bin/pytest tests/unit tests/api -q` · `venv/bin/ruff check app tests` ·
   `make sem-marcador` (varredura dos marcadores de pendência listados em `tests/marcadores.regex` —
   qualquer ocorrência reprova).
7. Empurre: `git push -u origin wt/<id-do-item>`. O servidor puxa sozinho (`laco/puxa_github.sh`),
   cria o worktree, põe na fila de junção, roda a suíte inteira em lote e só então junta em `master`.
   Se o lote quebrar, a bisseção devolve o ramo culpado com o registro do erro.

## 6. Regras duras (custaram caro; não são estilo, são reprovação)

- **Sem enchimento.** Marcador de pendência no código (a lista exata está em `tests/marcadores.regex`),
  simulação no lugar da coisa, botão que não faz nada, rota que devolve dado fixo: erro de build.
  A varredura roda sozinha em `make sem-marcador`.
- **Sem nome de cliente, de parceiro ou de pessoa** em código, dado, teste ou documento. Use
  "SIG de teste interno", "cooperativa de teste". Já houve um commit só para tirar a última ocorrência.
- **Sem segredo no repositório.** Chave, senha, DSN, token: nada. `.env.exemplo` lista as chaves.
- **Todo recurso partilhado tem dimensão de inquilino ou de ambiente**: fila, trinco, contador,
  porta, tarefa agendada, permissão, cache. Foi assim que quase tudo caiu em 06/09/2026.
- **Quem constrói não aprova.** Um adversário independente, que não vê o seu raciocínio, ataca o
  item com a instrução de derrubá-lo. O padrão da resposta dele é "achei problema". O que ele achar
  vira teste `xfail(strict=True)` e o item volta para conserto. Escreva prevendo isso.
- **Número em documento sai de JSON gerado por script**, nunca digitado à mão.
- **Paridade com o ArcGIS só do que foi testado.** Comparação contra Pro ou ArcGIS Online reais
  depende de credencial do parceiro (decisão em aberto) e fica escrita como pendente, nunca feito.
- **Idioma do código, dos testes e dos documentos é português** (nome de função, mensagem de erro,
  código de erro), como o resto do repositório.
- Toda funcionalidade visível tem teste ponta a ponta em Playwright com captura salva.
- Se você rodar pytest DENTRO do servidor algum dia, sempre sob
  `flock /home/dev/plataforma/laco/.pytest.lock`. Na sua máquina não precisa.

## 7. Como a revisão funciona do meu lado

A cada ramo `wt/<id>` que você empurrar, eu leio nesta ordem e respondo no repasse do ramo:

1. `laco/handoffs/T3/<id>.md` — cláusula por cláusula: o comando existe? roda? a saída é a que está escrita?
2. `tests/medidas/<id>.json` — o número bate com o que o documento afirma? o comando dentro do JSON reproduz?
3. `git diff master...wt/<id>` — arquivo por arquivo: enchimento, segredo, nome de cliente, recurso
   partilhado sem inquilino, migração fora do padrão, `git add -A` disfarçado.
4. A suíte inteira, em lote, no servidor.
5. Adversário independente, em contexto próprio, contra a refutação escrita no item.

Reprovação não é rejeição do ramo: volta com o achado escrito e vira teste. O que eu não aceito é
cláusula marcada como provada sem o comando que a prova, e número em documento que não saiu de script.

## 8. O que perguntar antes de decidir sozinho

Publicação externa, contato com cliente, DNS público, preço e nome público do produto são atos do
dono, não do programador. Se o seu item esbarrar em um deles, pare e escreva a pendência no repasse.
Decisões em aberto ficam registradas em `laco/estado.json`, campo `decisoes_do_dono`.
