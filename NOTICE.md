# Proveniência

Este cliente foi escrito como uma implementação pequena e independente do protocolo LAN usado pela Kobra X. Não inclui o KX-Bridge nem emula sua API Moonraker.

Referências lidas durante a implementação:

- `kobrax_client.py`, `bridge_endpoints.py` e `bridge_ams.py` do KX-Bridge, por viewit e contribuidores, GPLv3; commit `f0ce700fbcc9b3aed54f1a142b4e0318bc11638e`. Informaram os tópicos/payloads MQTT, campos multipart e cabeçalhos de interoperabilidade HTTP.
- Código instalado de `stribor/anycubic_kobrax` 0.1.6. Informou o formato das credenciais/certificado por dispositivo e os campos de estado. Nenhum arquivo da integração foi incorporado ao projeto.
- MQTT 3.1.1: framing de CONNECT, SUBSCRIBE, PUBLISH QoS 0/1 e DISCONNECT.

Por opção, este projeto usa GPL-3.0-only. Não distribui credenciais, tokens ou certificados Anycubic. Não é afiliado à Anycubic nem fornece garantias de compatibilidade com firmware não testado.
