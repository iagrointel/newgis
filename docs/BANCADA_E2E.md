# Bancada de e2e numa trilha

Durante a madrugada de 18/09/2026 o gerente recusou **três** itens dizendo "o e2e não fecha nesta
máquina". Estava errado nas três: a máquina nunca foi o problema, a bancada é que estava incompleta.
Cada peça que faltava produzia um sintoma diferente, e nenhum deles apontava para a causa.

| sintoma | peça que faltava |
|---|---|
| `Skipped: https://trilha-<nome>.invalido não resolve` | `PLAT_URL_PUBLICA` apontando para a bancada |
| `Timeout: waiting for #lista-camadas li` | camadas semeadas (`scripts/mapa_demo_camadas.py`) |
| `progresso não subiu na tela: [] (estado pendente)` | worker da trilha consumindo a fila |
| `ErroConfiguracao: PLAT_URL_PUBLICA inválida: deve começar com https://` | servidor **TLS** |
| `[SSL: CERTIFICATE_VERIFY_FAILED] self-signed` | âncoras de certificado repassadas ao pytest |
| `403 origem_invalida` ao clicar em salvar | `Origin` do navegador ≠ `PLAT_URL_PUBLICA` (ver `tests/e2e/apoio.py`) |

## A receita inteira

```bash
cd /home/dev/plataforma/enterprise
bash /home/dev/plataforma/laco/trilha_ambiente.sh <trilha>
set -a; source /home/dev/plataforma/laco/var/trilha/<trilha>.env; set +a
bash /home/dev/plataforma/laco/migrar_trilha.sh <trilha> /home/dev/plataforma/enterprise

# camadas: sem elas todo e2e que liga camada salta por falta de alvo
MAPA_DEMO_N=5000 venv/bin/python scripts/mapa_demo_camadas.py

# certificado com SAN de IP (sem o SAN, o navegador recusa)
D=$(mktemp -d)
openssl req -x509 -newkey rsa:2048 -nodes -keyout $D/t.key -out $D/t.crt -days 2 \
  -subj "/CN=127.0.0.1" -addext "subjectAltName=IP:127.0.0.1"

# servidor TLS + worker, em portas SUAS
PLAT_URL_PUBLICA=https://127.0.0.1:8393 \
  venv/bin/python scripts/servir_local.py --porta 8393 --cert $D/t.crt --chave $D/t.key &
PLAT_WORKER_URL=http://127.0.0.1:8394 venv/bin/python -m app.jobs.worker &

SSL_CERT_FILE=$D/t.crt REQUESTS_CA_BUNDLE=$D/t.crt NODE_EXTRA_CA_CERTS=$D/t.crt \
PLAT_URL_PUBLICA=https://127.0.0.1:8393 \
  bash /home/dev/plataforma/laco/roda_teste.sh tests/e2e/<alvo>.py -q
```

## Armadilhas medidas

- `MAPA_DEMO_N` **reduzido**: o milhão de pontos é da cláusula de desempenho de L2-01-mapa-web, não
  destes e2e, e o disco desta máquina está a 91 %.
- O worker precisa de `PLAT_WORKER_URL` com **porta própria**: sem isso ele bate na porta de saúde do
  worker de produção e morre com `Address already in use`.
- `laco/roda_teste.sh` repassa uma lista fechada de variáveis. `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE` e
  `NODE_EXTRA_CA_CERTS` foram acrescentadas em 18/09 justamente por causa desta bancada — sem elas o
  pytest não confia no certificado e os casos **pulam**, o que antes passava por "e2e quebrado".
- Ao terminar, mate só os **seus** processos e confira: `systemctl is-active plat-api plat-worker`
  tem de dar `active active`. `pkill -f "app.jobs.worker"` casa também o worker de produção.

## Resultado medido em 18/09/2026

Com a bancada completa, na trilha `prova403a` contra master: `test_l201k_desenho` + `test_mapa_desenho`
11/11 · `test_exportar_mapa` 3/3 · `test_tarefas` 8/8 — todos com **zero pulos**, e os três itens que
estavam recusados por "limite da máquina" foram promovidos com prova.

## Adendo 18/09/2026: e2e que faz o SERVIDOR abrir um navegador não roda no TLS autoassinado

O e2e de fidelidade do motor de render (`tests/e2e/test_render_fidelidade.py`) é o primeiro caso em que o
navegador não é só o do pytest: `POST /api/render/mapa` faz o chromium do POOL, **dentro do processo do
servidor**, navegar até `/render/mapa`. Esse navegador não conhece a âncora de certificado da bancada, e as
três variáveis (`SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`, `NODE_EXTRA_CA_CERTS`) não o alcançam:

| sintoma | causa |
|---|---|
| `POST /api/render/mapa` devolve **500** e o log do servidor mostra `Page.goto: net::ERR_CERT_AUTHORITY_INVALID` | o pool do render abrindo a própria página por TLS autoassinado |

Para essa classe de teste a bancada sobe em **HTTP** (`venv/bin/python scripts/servir_local.py --porta
85NN`, sem `--cert`) e o pytest recebe `--base-url http://127.0.0.1:85NN`. A escrita feita pela PÁGINA
volta a esbarrar na guarda de CSRF, e a saída é a que já existe: `escrita_do_navegador_sem_origin(page)`
(tests/e2e/apoio.py). Afrouxar a verificação de certificado do motor seria mexer no produto para o teste
passar, e por isso não foi feito.
