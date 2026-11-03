# Tasks

## 1. Preparar a configuração e sua recuperação

- [x] 1.1 Reconfirmar configurações GitHub, aplicações CodeRabbit/Sonar e modo de análise Sonar; registrar estado anterior relevante sem segredos em `~/research/kobra-lan-cli/prepare-community-repository`, com evidência suficiente para restaurar apenas o que esta change alterar.
- [x] 1.2 Criar guia público de manutenção com política pretendida, responsáveis, comandos de inspeção e recuperação; verificar que não contém contexto privado da devbox ou credenciais.

## 2. Organizar a documentação e a comunidade

- [x] 2.1 Enxugar README e criar `docs/README.md` e guias necessários, preservando avisos e exemplos atuais; verificar links, compatibilidade qualificada, maturidade experimental e distinção entre canais disponíveis e planejados.
- [x] 2.2 Adicionar `CONTRIBUTING.md` e `AGENTS.md` público com mapa, ambiente reproduzível, verificações e regras para segredos/estado/ações físicas; verificar comandos contra as ferramentas reais do projeto e ausência de instruções da devbox.
- [x] 2.3 Adicionar `SECURITY.md`, código de conduta com contato confirmado, `CODEOWNERS`, formulário de bug, pedido de funcionalidade, relato de compatibilidade e template de PR; validar estrutura YAML, responsáveis e direcionamento de vulnerabilidades ao canal privado.
- [x] 2.4 Conferir licença, atribuições, metadados e consumidores dos caminhos alterados, inclusive `MANIFEST.in` e empacotamento Debian; verificar consistência GPL-3.0-only e executar gates de arquivos distribuídos se forem afetados.

## 3. Estender verificações e manutenção de dependências

- [x] 3.1 Declarar Ruff e coverage como dependências de desenvolvimento, atualizar `uv.lock` e conferir exportação de runtime; verificar `uv sync --locked` e que ferramentas de desenvolvimento não entram nas dependências runtime distribuídas.
- [x] 3.2 Configurar lint inicial com correções mecânicas mínimas e documentar comando em `CONTRIBUTING.md`; verificar lint e suíte offline sem alterar contratos da CLI.
- [x] 3.3 Executar `unittest` com coverage no CI existente e gerar XML; conferir importabilidade dos caminhos, ausência de acesso à impressora e preservação dos jobs de build/aceitação e do workflow reutilizado pela release.
- [x] 3.4 Adicionar CodeQL para Python/Actions e conferir permissões mínimas e Actions fixadas por commit; validar workflows com actionlint e confirmar análise real sem conceder secrets a código de forks.
- [ ] 3.5 Configurar Dependabot semanal para Python/Actions com grupos de atualizações menores e majors separadas; validar configuração e documentar a atualização de lock/exportações, verificando os arquivos produzidos no primeiro PR disponível.
- [x] 3.6 Habilitar alertas, atualizações de segurança e reporte privado no GitHub; confirmar via API a configuração efetiva e preservar secret scanning/push protection preexistentes.

## 4. Versionar e validar os serviços de revisão

- [ ] 4.1 Criar `.coderabbit.yaml` com revisão incremental, instruções por área e autoaprovação conforme design; validar schema e observar em PR se o serviço emite review `APPROVED` elegível, documentando alternativa humana se necessário.
- [x] 4.2 Criar configuração Sonar e scanner CI com versão da fonte única e relatório de cobertura; desativar a análise automática imediatamente antes do primeiro scan CI, confirmar análise real e importação de cobertura no projeto existente e restaurar a análise automática se o scan ou a importação falhar, registrando o procedimento no guia de manutenção.
- [x] 4.3 Conferir achados e Quality Gate atuais contra `docs/pairing-security-review.md`; registrar divergências e evidência de cobertura importada, sem reduzir o gate, excluir código para aprovar ou aceitar novos achados automaticamente.
- [ ] 4.4 Exercitar PR interno, fork e Dependabot; registrar checks emitidos, ausência de secrets nas origens não confiáveis e aprovação elegível. Conferir que eventos privilegiados não executam código nem artefatos não confiáveis e documentar quando Sonar não roda.

## 5. Aplicar e comprovar as regras de contribuição

- [ ] 5.1 Definir a lista de checks obrigatórios a partir dos nomes/apps efetivamente observados em todas as origens; verificar que nenhum check pulado em forks/Dependabot entra no ruleset global e registrar a condição para futura promoção do Sonar.
- [ ] 5.2 Aplicar ruleset de `main` exigindo PR, uma aprovação válida, invalidação de aprovações após mudanças, discussões resolvidas e checks universais; conferir via API e estado de merge de PRs que o autor não se autoaprova e não existe bypass rotineiro.
- [x] 5.3 Proteger tags `v*` contra atualização/exclusão preservando criação autorizada; verificar regras por API e compatibilidade com o workflow de release, sem publicar versão nem alterar tags existentes.
- [x] 5.4 Consolidar squash e exclusão de branches após merge; verificar configurações efetivas e atualizar o guia de manutenção com critérios de merge, limitações por origem e recuperação.

## 6. Verificar a integração final

- [ ] 6.1 Confirmar em um mesmo estado de código o resultado de lint, testes com cobertura, CodeQL, Sonar aplicável, build e aceitação Debian/Ubuntu; registrar SHAs e resultados sem operar impressora ou publicar release.
- [ ] 6.2 Revisar a experiência completa de contribuição contra os arquivos públicos e regras efetivas; verificar que uma aprovação é obrigatória e que forks/Dependabot têm caminho viável de merge, registrando limitações concretas de serviços antes de considerar a change concluída.

## Evidências e pendências de validação

As análises reais de CodeQL e a importação dos relatórios Sonar no commit
`8dab9f95429c804587179b9fe2f785a35a864573` estão vinculadas no
[guia público de manutenção](../../../docs/maintenance.md#recorded-internal-validation).
O scanner e o Quality Gate passaram; não houve redução do gate ou novas aceitações.

A tarefa 2.4 foi reconfirmada no commit `fef7206` pelo run Tests 41561551442:
compressão Markdown corrigida, links verificados no pacote real e aceitação nas
duas distribuições. A validação final 6.1 deve cobrir o estado final do código. As tarefas dependentes de forks/Dependabot/aprovação continuam abertas;
o usuário informou que não consegue testar forks.
