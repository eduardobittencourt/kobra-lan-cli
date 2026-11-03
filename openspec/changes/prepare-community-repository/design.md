# Design

## Context

Ver motivação em `proposal.md`. O projeto usa Python >=3.11, `unittest`, `uv.lock` e `requirements-runtime.txt`. `Tests` chama o workflow reutilizável `Package checks`, que executa testes, build e aceitação Debian 13/Ubuntu 24.04. Actions e uv já possuem versões fixadas. A release reutiliza as mesmas validações; esse contrato deve ser preservado.

README concentra onboarding, protocolo e operação física. Existem `docs/releases.md` e `docs/pairing-security-review.md`, mas ainda não há índice, arquivos de comunidade ou configuração versionada CodeRabbit/Sonar. A revisão de pairing já documenta achados aceitos por compatibilidade de firmware e falso positivo; isso não elimina os riscos descritos.

A consulta ao GitHub em 2026-11-02 encontrou secret scanning e push protection habilitados, atualizações de segurança Dependabot desabilitadas e nenhum ruleset. Estado remoto é mutável e será reconfirmado antes da aplicação. CodeRabbit e Sonar já emitiram análises; conexão existente não prova configuração completa nem cobertura importada.

## Goals / Non-Goals

**Goals:** manter uma entrada curta, caminhos claros para contribuição e critérios de merge verificáveis, com configurações de análise versionadas e uma aprovação obrigatória.

**Non-Goals:** alterar protocolo, confiança TLS, operações físicas, formato de estado ou contrato de distribuição. O trabalho não exige contato com impressora nem publicação de release. Os arquivos públicos serão em inglês, seguindo a documentação existente; os artefatos de planejamento ficam em português.

## Decisions

### 1. Documentação por finalidade, com garantias preservadas

README apresenta propósito, maturidade, compatibilidade qualificada, instalação disponível e exemplos iniciais seguros. `docs/README.md` aponta para onboarding/pairing, uso e segurança operacional, referências de protocolo e releases. Mover conteúdo preservando os avisos de confiança inicial, pinning, proteção de credenciais, dry runs, hashes revisados, marcadores e ausência de repetição automática. Atualizar links consumidores e documentação incluída nos pacotes quando aplicável.

`CONTRIBUTING.md` descreve ambiente reproduzível e checks; `SECURITY.md` define reporte privado e escopo de suporte sem prometer SLA; o código de conduta usa um contato público do mantenedor confirmado na aplicação. `AGENTS.md` público contém mapa do projeto, comandos e regras locais, sem contexto da devbox. Templates pedem versões/modelo/firmware, passos e saídas sanitizadas; vulnerabilidades são direcionadas ao reporte privado. `CODEOWNERS` identifica o mantenedor. Preservar GPL-3.0-only e proveniência.

Alternativa descartada: manter toda a documentação no README, pois dificulta entrada e manutenção. Não criar novos guias para duplicar conteúdo já mantido.

### 2. Estender o CI existente

Adicionar Ruff e coverage às dependências de desenvolvimento declaradas no `pyproject.toml`, regenerando o lock. Manter a exportação de runtime consistente; ferramentas de desenvolvimento não entram no pacote nem no runtime. Adotar lint com regras explícitas e correções mecânicas mínimas; refactors funcionais ficam fora desta change.

Executar a suíte `unittest` sob coverage e gerar XML com caminhos utilizáveis pelo Sonar. Medir também os gates reais de arquivos Python/Debian e importar seus relatórios junto ao XML unitário; scripts executados em outro job precisam de instrumentação própria. As ferramentas de medição usam wheels dev com hashes do lock em diretório isolado do container, sem entrar no runtime distribuído. A cobertura inicial será medida; não inventar um percentual nem excluir código para obter aprovação. Preservar testes offline, build, testes de instalação com hashes e aceitação Debian/Ubuntu. Separar os jobs adicionais quando isso evita acoplar tokens de análise à release. Não duplicar toda a suíte em workflows paralelos.

CodeQL cobre Python e Actions em PR, `main` e agenda, com permissões de escrita de resultados restritas ao job necessário. Configurar Actions com permissões mínimas, referências fixadas por commit e sem executar código de PR com credenciais privilegiadas. Documentar os comandos locais correspondentes.

Dependabot verifica Python e Actions semanalmente, agrupa atualizações menores compatíveis e separa majors. Validar que atualizações preservam `uv.lock`, exportação de runtime e comentários de versão das Actions; documentar regeneração quando o serviço não atualizar algum arquivo derivado.

### 3. Análise Sonar e revisão CodeRabbit versionadas

`.coderabbit.yaml` define revisão incremental, comentários objetivos e instruções por área: confiança/credenciais, protocolo, persistência, execução física, empacotamento e testes. Como escolha inicial, habilitar aprovação automática quando o serviço suportar e suas condições forem satisfeitas, mantendo a possibilidade de aprovação humana. Um check CodeRabbit concluído não substitui um review `APPROVED` elegível no GitHub. Validar schema e comportamento real antes de contar com aprovação do bot.

`sonar-project.properties` identifica o projeto existente, fontes, testes e cobertura. Workflow obtém a versão da mesma fonte do pacote, importa XML e analisa PRs internos e `main` via scanner autenticado. A análise CI é rejeitada pelo Sonar enquanto a automática estiver ativa. Conforme decisão do usuário, preparar e validar a configuração primeiro, registrar o estado anterior e desativar a análise automática imediatamente antes do primeiro scan CI. Confirmar análise e importação de cobertura; restaurar a análise automática se qualquer uma falhar, evitando uma lacuna persistente de análise. Preservar o Quality Gate e conferir o estado atual dos achados documentados em `docs/pairing-security-review.md`; não usar exclusões amplas, supressões ou novas aceitações para tornar o gate verde.

Alternativa descartada: manter apenas análise automática, pois o objetivo inclui importar cobertura gerada nos testes. Tokens ficam no armazenamento de secrets apropriado e nunca em arquivos públicos ou logs.

### 4. PRs sem secrets têm um caminho explícito

Testes, lint e empacotamento executam em `pull_request` para forks e Dependabot sem secrets. Não usar `pull_request_target` para checkout/execução do código contribuído, nem consumir artefatos de PRs de origem não confiável em job privilegiado.

Decisão explícita do usuário: manter Sonar pré-merge para colaboradores internos confiáveis. Um PR interno elegível tem head no próprio repositório, associação do autor `OWNER`, `MEMBER` ou `COLLABORATOR`, e nem autor nem ator Dependabot. Código e relatórios da mesma execução desses autores estão dentro da fronteira confiável de edição de workflows/secrets; não há promessa de isolamento contra colaborador malicioso ou conta comprometida. Forks são excluídos mesmo quando o autor é colaborador. Não usar eventos privilegiados nem importação entre repositórios/runs para contornar essa fronteira. Restringir toda análise a `main` foi descartado porque removeria a análise interna pré-merge pretendida.

No primeiro estágio, Sonar é obrigatório no processo de revisão dos PRs internos em que a análise roda, mas seu check externo fica fora do ruleset global se não for emitido para todas as origens. Forks e Dependabot precisam de uma aprovação válida e dos checks universais; ausência de análise Sonar deve ficar explícita, sem declarar um resultado verde fictício. A análise de `main` fornece acompanhamento após merge, com a limitação de não bloquear preventivamente esses PRs.

Somente promover Sonar a check obrigatório global depois de comprovar um caminho suportado, seguro e sem secrets expostos para forks e Dependabot. Se isso não estiver disponível, entregar a política inicial documentada e registrar a promoção como evolução futura, sem bloquear esta change ou criar um check impossível de satisfazer. CodeRabbit segue a mesma regra de disponibilidade para seu check de execução; a exigência de uma aprovação permanece independente.

Alternativa descartada: exigir checks externos que o workflow pula, pois isso impede contribuições legítimas. Uma aprovação humana elegível resolve indisponibilidade de autoaprovação, sem reduzir a contagem exigida.

### 5. Proteções remotas aplicadas após observar os checks

Habilitar reporte privado, alertas e atualizações de segurança Dependabot; preservar secret scanning/push protection. Manter squash e habilitar exclusão de branches após merge. Registrar política e nomes reais dos checks em guia de manutenção, sem versionar dumps privados.

Ruleset de `main`: exigir PR, uma aprovação, invalidar aprovação após novas alterações, resolver discussões e passar checks universais observados. Vincular cada check à aplicação correta quando suportado. Bloquear exclusão e force push e impedir bypass rotineiro do mantenedor/bots. `CODEOWNERS` orienta revisão, sem adicionar exigência separada de aprovação do owner que impediria o único mantenedor de contribuir. Testar aprovação elegível do bot; se não contar, manter a exigência e documentar necessidade de outro revisor elegível.

Ruleset para `v*`: impedir atualização e exclusão de tags existentes, preservando criação de novas tags pelo fluxo autorizado de release. Não criar uma release de teste nem bloquear criação de tags necessária ao workflow existente.

## Risks / Trade-offs

- [Check ausente bloqueia forks] → exigir globalmente apenas checks universais observados e documentar cobertura Sonar limitada por origem.
- [Uma aprovação impede merge do único mantenedor] → validar aprovação elegível do CodeRabbit ou de outro revisor; nunca contar autoaprovação do autor nem remover a exigência para concluir a entrega.
- [Análise privilegiada executa contribuição não confiável] → manter execução de PR sem secrets e recusar atalhos via eventos privilegiados ou artefatos não confiáveis.
- [Lint amplia escopo] → usar configuração inicial pequena, preservar semântica e separar correções funcionais em outra change se necessárias.
- [Mover guias perde avisos ou arquivos do pacote] → revisar links e inclusão nos arquivos distribuídos; rodar gates existentes quando afetados.
- [Configuração de serviço não é suportada pelo plano/permissão atual] → confirmar no serviço e registrar limitação concreta; não marcar tarefa remota como concluída apenas por existir um arquivo local.

## Migration Plan

1. Registrar estado anterior relevante do GitHub/Sonar sem segredos; confirmar aplicação e permissões dos serviços.
2. Preparar documentação e configurações versionadas; validar localmente e em PR antes de exigir novos checks.
3. Desligar análise automática imediatamente antes do primeiro scan CI, confirmar scanner e cobertura; restaurar a automática se análise/importação falhar. Exercitar PR interno, fork e Dependabot, inclusive ausência de secrets e elegibilidade de aprovação.
4. Ativar segurança e rulesets com nomes/apps observados. Confirmar aprovação, discussões, checks e proteção de tags sem publicar release.
5. Registrar resultados e limitações no guia de manutenção. Reversão restaura apenas configurações alteradas a partir do estado anterior e reverte commits necessários; preserva proteções preexistentes, licença, credenciais e estado operacional. Não fazer merge de PRs usados apenas para validação.
