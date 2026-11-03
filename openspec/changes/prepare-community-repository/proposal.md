# Proposal

## Why

O Kobra LAN CLI precisa de uma entrada clara para colaboradores e de políticas reproduzíveis de manutenção, segurança e revisão antes de ampliar sua divulgação. O projeto já possui testes e empacotamento; falta consolidar a apresentação pública, versionar a configuração dos serviços de análise e definir os critérios de merge.

## What Changes

- Reorganizar README e guias com um índice em `docs/README.md`, preservando limites de compatibilidade, segurança, maturidade e distribuição.
- Adicionar orientações públicas de contribuição e agentes, política de segurança, código de conduta, responsáveis e templates de issues/PRs.
- Preservar GPL-3.0-only, `LICENSE`, `NOTICE.md` e atribuições; conferir consistência nos documentos e metadados.
- Configurar Dependabot para Python e GitHub Actions, lint, cobertura dos testes offline e CodeQL, mantendo os checks de empacotamento existentes.
- Versionar CodeRabbit e SonarQube Cloud, com revisão orientada aos riscos do cliente LAN e análise Sonar via CI com cobertura e versão do pacote.
- Consolidar segurança e manutenção no GitHub: reporte privado, alertas e atualizações de segurança, permissões mínimas e proteção de branches/tags.
- Exigir PR, uma aprovação válida, resolução das discussões e checks verificados para merge em `main`. Validar contribuições de forks e Dependabot antes de tornar checks obrigatórios.

## Capabilities

### New Capabilities

Nenhuma. Esta change organiza documentação, tooling e governança do repositório, sem adicionar comportamento ao cliente. Usa `skip_specs: true`.

### Modified Capabilities

Nenhuma. Os contratos de `printer-pairing` e `release-distribution` permanecem vigentes.

## Impact

Afeta README, documentação pública, arquivos de comunidade, `.github/`, configuração CodeRabbit/Sonar, dependências de desenvolvimento e configurações remotas do GitHub/Sonar. Preserva o fluxo de release, a versão como fonte única, os testes offline e as garantias de segurança do cliente.

Não inclui funcionalidades da CLI, suporte a novos modelos/firmwares, publicação de pacotes, migração de instalações, operação de impressora real ou mudança de licença. Ajustes remotos serão registrados com estado anterior e verificação posterior, sem segredos versionados.
