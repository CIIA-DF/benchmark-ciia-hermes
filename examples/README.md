# Dados fictícios

[process.json](process.json) e [document.json](document.json) são sintéticos e não foram exportados de processo real. O SHA-256 do documento é calculado ao ler os bytes, sem hash fixo copiado manualmente.

A exportação é marcada partial para exercitar a limitação de cobertura. IDs sintéticos e corpus synthetic-v1 permitem repetir a demo sem duplicação. Alterações no conteúdo exigem nova versão do corpus se a versão anterior já foi ingerida.

Execute `uv run --locked python -m scripts.dev demo`. Novas fixtures devem manter declaração explícita de origem fictícia.
