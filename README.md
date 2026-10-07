# Kobra LAN CLI

Cliente LAN direto para Anycubic Kobra X, com saída JSON e foco em automação por CLI/agentes. O fatiamento é feito separadamente pelo Anycubic Slicer Next oficial. Este cliente preserva os bytes do G-code e não usa KX-Bridge, Moonraker, desktop ou Home Assistant em runtime.

**Estado:** upload validado em hardware Kobra X / firmware 2.0.2.2. Início de impressão experimental: testes offline e plano conferido por consultas reais; nenhum comando de início foi enviado no desenvolvimento desta versão. Uso do arquivo local com `url=""` ainda exige validação física.

## Execução

Python padrão >=3.11, sem dependências pip ou daemon. O launcher Linux usa `/usr/bin/python3`.

```sh
git clone https://github.com/eduardobittencourt/kobra-lan-cli.git
cd kobra-lan-cli
./kobra-lan --help
./kobra-lan status
./kobra-lan files
./kobra-lan inspect /caminho/modelo.gcode --name agent-modelo.gcode
./kobra-lan upload /caminho/modelo.gcode --name agent-modelo.gcode
# Upload real: mesmo arquivo e SHA-256 revisados na simulação
./kobra-lan upload /caminho/modelo.gcode --name agent-modelo.gcode --sha256 HASH --execute
./kobra-lan file agent-modelo.gcode
```

`upload` é simulação local até receber `--execute` e o hash revisado. Nunca inicia impressão. Retorno JSON; códigos 0 (sucesso), 2 (protocolo/validação), 3 (configuração/rede). `--config` e `--state-dir` são opções globais, antes do subcomando.

## Configuração privada

Configuração em `~/.config/kobra-lan/config.json`, modo 0600, diretório 0700. Campos:

- `host`: IPv4 LAN da impressora; `type_id`: 20030; `printer_id`: identidade retornada pelo provisionamento LAN.
- `mqtt_username`, `mqtt_password`: credenciais LAN por dispositivo.
- `client_cert`, `client_key`: caminhos dos arquivos PEM privados (0600).
- `tls_sha256`: SHA-256 do certificado DER do servidor MQTT, obtido por um caminho confiável.
- `mqtt_port`: 9883; `http_port`: 18910 (opcionais, esses são os padrões).

Credenciais/certificado são obtidos pelo provisionamento LAN Anycubic; podem ser importados de uma integração existente. O cliente não inclui ferramenta pública de pareamento nem certificados/credenciais de terceiros. Não versionar config, chaves, tokens ou recibos. Conexões verificam o pin TLS **antes** de enviar usuário/senha MQTT; não atualizar o pin automaticamente se houver divergência. A confiança inicial precisa ser estabelecida pelo operador. Não é validação por CA pública.

A sessão/token de upload vem de `info/report`. URLs com token não são impressas nem gravadas nos recibos. O destino é limitado ao host/porta configurados e `/gcode_upload?s=...`. A implementação se baseia em interoperabilidade comunitária, não em SDK oficialmente suportado pela Anycubic.

## Início experimental

O plano padrão apenas consulta a impressora. Exige arquivo já enviado, slot **1..4** (numeração humana), material compatível, uma única cor/paint index 0 e os quatro slots internos. ACE externo e multicolorido não são suportados nesta versão.

```sh
./kobra-lan start /caminho/modelo.gcode --name agent-modelo.gcode --slot 1 \
  --auto-leveling on --vibration-compensation off --flow-calibration off
```

As três opções de preparação são obrigatórias: o exemplo não afirma reproduzir os padrões da interface gráfica. O JSON mostra o payload e `plan_sha256`. Alterar arquivo, slot ou opções altera o hash. O plano contém `experimental=true` e `hardware_start_validated=false`.

Execução futura é explicitamente solicitada adicionando `--execute --plan-sha256 HASH_DO_PLANO` aos mesmos argumentos. Isso é uma ação física: só fazê-la quando houver autorização para imprimir e a impressora estiver preparada. Exige recibo de upload verificado desta CLI, reconfere arquivo/estado/material e registra uma reserva persistente antes de publicar **um único** MQTT `print/start`. Não faz novo upload. ACK recebido não é tratado como prova de impressão física; o cliente consulta depois o projeto ativo e distingue confirmação de estado incerto. Nunca repete o comando automaticamente.

## Garantias e limites

- Upload atualmente qualificado somente para modelo 20030 / firmware 2.0.2.2, G-code Next e perfil Kobra X. Exige estado livre e nenhum projeto ativo.
- Hash e multipart usam os mesmos bytes em memória. Sem tradução de G-code, sem `print=true`, sem redirecionamento HTTP.
- Reserva exclusiva/fsync por dispositivo e hash em `~/.local/share/kobra-lan/uploads/`. Upload e início têm marcadores separados. A segunda tentativa é bloqueada após sucesso ou timeout, inclusive entre processos/reinícios.
- Em resposta ambígua, consultar estado/arquivos/recibos. Não apagar marcadores para reenviar cegamente. Outro diretório de estado ou outro programa não compartilha a proteção; repetir intencionalmente a mesma peça exige revisão operacional.
- Arquivos remotos não são sobrescritos. Nomes ASCII seguros, `.gcode` até 128 MiB.
- Verificação remota por nome/tamanho/camadas/modelo. Os endpoints usados não forneceram checksum dos bytes armazenados: `remote_byte_hash_verified=false` explicita que não houve download/hash independente da cópia interna.
- Firmware 2.0.2.2 envia ACK correlacionado, seguido de report com outro msgid. Consultas são síncronas e aceitam report fresco após ACK. Ociosa, a impressora não produz report para `print/query`; status usa `info/report`.
- Não existe bloqueio transacional com outro computador entre consulta e ação. Credenciais/pin podem mudar após firmware/modo LAN; reavaliar o provisionamento.

## Testes

```sh
/usr/bin/python3 -m unittest discover -s tests -v
```

27 testes offline cobrem preservação multipart, framing MQTT, TLS pin, correlação de respostas, hash, simulação, arquivo existente, estado ocupado, mapeamento de slot/material, plano revisado, recibo de upload, ACK versus confirmação e timeout sem replay. Nenhum teste automatizado acessa impressoras reais.

Validação manual de upload: um único POST real de um Autodesk FDM Test gerado pelo Next 2.0.0.3, 6.856.570 bytes, 460 camadas, HTTP 200/code 200; listagem e metadados confirmaram 1h44m09s e aproximadamente 31,74 g. A impressora permaneceu livre e sem aquecimento. Isso não valida a qualidade física nem o início experimental.

## Licença e referências

GPL-3.0-only. Implementação independente baseada nas referências de protocolo [KX-Bridge](https://gitea.it-drui.de/viewit/KX-Bridge-Release), commit `f0ce700fbcc9b3aed54f1a142b4e0318bc11638e`, e [integração HA Anycubic Kobra X](https://github.com/stribor/anycubic_kobrax), versão 0.1.6. Nenhum módulo desses projetos é importado em runtime. Veja [NOTICE.md](NOTICE.md) e [LICENSE](LICENSE).
