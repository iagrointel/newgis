"""Catálogo de conteúdo (ADR 0004): itens, tipos com JSON Schema, versões, relações, compartilhamento, busca, pastas,
categorias, favoritos, lixeira, transferência de dono, miniaturas e jobs. `item_legivel` é o gancho que a criação de
token (app/auth/escopos.py) usa para validar `camada:ler:<uuid>` e `tiles:ler:<uuid>`."""

from app.catalogo.comum import item_legivel

__all__ = ["item_legivel"]
