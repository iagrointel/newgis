"""Notebook por inquilino (item L2-16-b-jupyter-por-inquilino-isolado): um contêiner JupyterLab
por inquilino, sob demanda, com limite de CPU/RAM, rede docker interna sem saída, token de
serviço do usuário como único segredo, encerramento por ociosidade e proxy autenticado pela
sessão da plataforma em /notebooks/<inquilino>/. O gateway da API para os contêineres vive na
própria rede interna (o firewall desta máquina derruba todo o tráfego contêiner → host, medido:
ufw INPUT DROP; por isso a API é servida num socket unix e bombeada para dentro da rede por
`nsenter` — ver app/notebooks/gateway.py e docs/PARIDADE.md)."""
