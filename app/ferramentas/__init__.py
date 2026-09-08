"""Ferramentas geoespaciais executadas por job (item L2-16-a-sdk-python-geo): cada ferramenta é um tipo de job
(`app/jobs/registro.py`) que recebe parâmetros e devolve resultado — e, quando o resultado é um dado reutilizável,
vira item `ferramenta_resultado` do catálogo com procedência. O SDK (`pacote/plat`) chama por `POST /api/jobs`."""
