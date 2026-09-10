# Imagem do notebook por inquilino (item L2-16-b-jupyter-por-inquilino-isolado).
# Construída por install.sh (alvo --imagem-notebook) a partir de python:3.12-slim +
# JupyterLab + o SDK `plat` (L2-16-a) + geopandas/rasterio/duckdb/shapely.
# O contêiner NUNCA leva credencial de banco: o único segredo injetado em runtime é o
# token de serviço do usuário (variável PLAT_TOKEN), e a rede é bridge interna sem saída.
FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Usuário sem privilégio: pip install de quem usa o notebook não escreve no sistema
RUN useradd -m -s /bin/bash -u 1000 jovyan

# o contexto deste build é ESTE diretório (deploy/notebook/contexto), não a raiz do repositório:
# o .dockerignore da raiz é de negação total para o build do worker (L0-05-e) e não pode ser
# aberto. install.sh copia pacote/ para cá antes de construir (ver alvo --imagem-notebook).
COPY pacote /tmp/pacote

RUN pip install --no-cache-dir \
        "jupyterlab>=4.0" \
        "geopandas>=1.0" \
        "rasterio>=1.3" \
        "duckdb>=1.0" \
        "shapely>=2.0" \
        "pyproj>=3.6" \
        "requests>=2.31" \
    && pip install --no-cache-dir /tmp/pacote \
    && rm -rf /tmp/pacote

USER jovyan
WORKDIR /home/jovyan
RUN mkdir -p /home/jovyan/trabalho

EXPOSE 8888
# base_url, porta e volume de trabalho são passados no `docker run` (um contêiner por inquilino);
# a autenticação é do PROXY da plataforma (sessão), o Jupyter roda sem token próprio atrás dele.
ENTRYPOINT ["jupyter", "lab", "--no-browser", "--ip=0.0.0.0", "--port=8888", \
            "--ServerApp.token=", "--ServerApp.password=", "--ServerApp.disable_check_xsrf=True", \
            "--ServerApp.allow_remote_access=True", "--ServerApp.quit_button=False"]
