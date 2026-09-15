"""Integração com o ArcGIS Online do CLIENTE (item L2-08-migracao-agol): o inquilino mantém a conta AGOL dele,
a plataforma publica uma cópia de uma camada vetorial hospedada como hosted feature layer nessa conta —
mesmo desenho já em operação no script de publicação AGOL do SIG anterior (generateToken -> addItem
-> publish -> overwrite nas rodadas seguintes), portado aqui por inquilino (a credencial cifrada mora em
`plat.tenant.config->'agol'`, mesmo padrão de `app/correio/cifra.py`/`config.py` para o SMTP por inquilino)."""
