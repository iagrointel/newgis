"""Exportação COMPLETA do inquilino (item L0-06-d-exportar-inquilino): "escrow prático" da spec 17.4 — o
cliente sai com um pacote em formato aberto (GeoPackage + JSON + zip de arquivos + manifesto sha256), sem
depender de nós. Reaproveita `app.exportacao.motor` (item L0-04-h-exportar) para a parte que já foi medida
(RLS dentro do ogr2ogr, conversão que o GDAL não faz); este pacote acrescenta só o que é do INQUILINO INTEIRO:
catálogo (itens/pastas/grupos/compartilhamentos/relações/usuários sem hash de senha), um GeoPackage com todas
as camadas hospedadas e o zip dos arquivos do bucket.

`motor.py` (monta o pacote), `tarefas.py` (job `inquilino.exportar`), `rotas.py` (a API) e `importar.py`
(recria itens com os mesmos uuids num inquilino novo — a prova de portabilidade do portão de pronto)."""
