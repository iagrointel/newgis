# ADR 20260908T0628 — pyogrio é dependência declarada da aplicação, com import tardio

Item `L4-01-g-tarefas-import-tardio`. Estado: aceita.

## Contexto

O importador BDGD (item `L4-01-c`) lê o pacote `.gdb` da ANEEL com `pyogrio`, a ligação vetorizada com o
GDAL/OGR. Os dois módulos que abrem arquivo — `app/rede_utilidades/bdgd.py` e
`app/rede_utilidades/tarefas.py` — traziam `import pyogrio` no topo. Como `app/jobs/tipos.py` importa as
tarefas e `app/main.py` importa os tipos, todo `import app.main` passou a exigir o pacote.

Nesta máquina o `pyogrio` estava instalado apenas no site do usuário (`~/.local`), fora da venv. Com
`PYTHONNOUSERSITE=1` — que é como o `install.sh`, o Makefile e a unidade systemd rodam a aplicação — o
import quebrava, e `tests/unit/test_dependencias.py::test_app_main_importa_sem_site_do_usuario` reprovava.
São dois defeitos somados: uma dependência real não declarada, e a subida da API acorrentada ao GDAL.

## Decisão

1. `pyogrio==0.12.1` entra em `requirements.txt`, com o motivo escrito ao lado: é dependência real do job
   `rede.importar_bdgd`, não uma conveniência da suíte. `numpy`, `certifi` e `packaging`, que ele exige,
   já vêm de `/usr/local/lib/python3.12/dist-packages` (o mesmo caso do `shapely`, comentado no topo do
   arquivo, e que continua pendente da mesma decisão do dono sobre a lista fechada de pacotes apt).
2. O import é TARDIO: `bdgd._pyogrio()` importa dentro da chamada, e `tarefas._ler_camadas_do_contrato`
   usa a mesma função. A API sobe sem GDAL; quem depende dele é o worker, no instante em que abre o
   arquivo, e a falta aparece nomeada ali.
3. As duas coisas juntas, e não uma só: declarar sem adiar deixaria a API presa a um pacote de 32 MB que
   ela nunca usa; adiar sem declarar deixaria o job quebrando em produção por falta de dependência.

## Consequências

- `import app.main` volta a passar com `PYTHONNOUSERSITE=1` e passa também com o `pyogrio` bloqueado de
  propósito no `sys.meta_path` — que é a refutação do item: tirar o pacote do site do usuário não pode
  quebrar a importação da aplicação.
- A instalação na venv foi aditiva: `pip install --dry-run` antes, e nenhuma versão de fastapi, starlette,
  pydantic, psycopg2, uvicorn ou rasterio mudou.
- `make seguranca-deps` passa a auditar mais um pacote.
