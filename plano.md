# Plano metodológico de validação e evolução

Atualizado em 12/10/2026. Este documento registra o que já foi executado e organiza as próximas decisões. A proposta metodológica consolidada está em [Texto atual.md](Texto%20atual.md); os resultados da primeira execução estão em [docs/initial-run-results.md](docs/initial-run-results.md).

## 1. Objetivo e unidade de previsão

Prever notificações de dengue, chikungunya e zika por município de residência e semana epidemiológica na Região Norte, com agregação opcional por estado. Para cada doença, a saída atual cobre quatro semanas, com número esperado de casos, intervalos preditivos e probabilidade de ao menos um caso. A contagem representa registros no Sinan, não todas as infecções nem incidência populacional.

A escolha do objetivo operacional deve preceder a próxima comparação: estimar volume para planejar recursos, detectar ocorrência ou antecipar aumentos são tarefas relacionadas, mas exigem métricas e limites de alerta diferentes.

## 2. Referência já implementada

- Foram obtidos 50 arquivos anuais oficiais e os três dicionários atuais. A janela comparável analisada é 2016–2026, comum às três doenças.
- O painel final contém 450 municípios do Norte e contagens semanais para a definição operacional de casos prováveis. A classificação é específica por doença; categorias de dengue e chikungunya não são intercambiadas.
- O MLP global em PyTorch prevê a distribuição binomial negativa de cada doença. As entradas usam 52 semanas de contagens municipais, resumos estaduais, UF, calendário cíclico e embedding municipal; o corte de entrada fica oito semanas antes da origem.
- Persistência, média móvel de quatro semanas e sazonalidade de 52 semanas servem como baselines. A avaliação inclui backtests desses métodos em 2022–2024, validação em 2025 e teste parcial em 2026.
- As correções desta execução incluem parsing separado para datas ISO e brasileiras, classificação de `CLASSI_FIN` por doença, exclusão de residências sem correspondência municipal, normalização correta do WIS, agregação ponderada da NLL entre lotes e rastreabilidade entre painel, preparação, fontes e checkpoint.

O WIS agora usa o denominador `K + 0,5`, com `K` intervalos centrais. A perda de validação é ponderada pelo total de alvos válidos, em vez de atribuir o mesmo peso a lotes de tamanhos diferentes. Métricas devem ser lidas do relatório da execução corrigida, pois valores de versões anteriores não são diretamente comparáveis.

## 3. Próximas etapas, em ordem

### Etapa A — Reconciliar os dados

1. Comparar contagens por doença, ano e UF com tabulações oficiais do Ministério da Saúde, mantendo iguais a residência, a semana de sintomas e a definição de caso.
2. Revisar os códigos de classificação por versão anual do formulário e documentar qualquer regra adicional antes de mudar a série.
3. Investigar os códigos de residência sem município correspondente e manter a exclusão explícita nos relatórios de qualidade.
4. Auditar fronteiras de arquivos anuais e possíveis sobreposições sem deduplicar por combinações frágeis de município, data ou idade.
5. Preservar hashes e metadados de cada atualização. A data de atualização do arquivo do ano mais recente define a aproximação de maturidade; uma revisão de ano histórico não deve avançar o corte corrente.

**Critério para avançar:** totais e diferenças estão explicados por doença, ano, UF e regra de inclusão. Divergências sem explicação permanecem como bloqueio para interpretação epidemiológica.

### Etapa B — Medir o atraso e fixar a avaliação temporal

1. Estimar a distribuição do atraso entre início de sintomas, notificação e digitação usando `dt_notific` e `dt_digita`, se os campos e datas forem comparáveis.
2. Obter snapshots históricos, quando disponíveis, para medir o que estaria acessível em cada origem. Sem snapshots, tratar testes de defasagem como sensibilidade retrospectiva, não como desempenho operacional.
3. Construir vários cortes cronológicos com treino, validação e teste posteriores em sequência. Recalcular vocabulário municipal, dispersão e qualquer transformação somente com dados anteriores ao respectivo corte.
4. O período de 2026 já foi consultado e usado para corrigir o pipeline. Ele não deve continuar sendo apresentado como teste final intocado; reservar semanas maduras futuras ou outra janela independente para a avaliação final.

**Critério para avançar:** cada previsão identifica a origem, o último dado disponível, os alvos e o atraso efetivo; nenhum atributo usa informação posterior à origem simulada.

### Etapa C — Comparar previsões de forma operacional

Comparar todos os candidatos nos mesmos municípios, origens, alvos, horizontes e snapshots. Publicar métricas gerais e por horizonte, UF, escala histórica da localidade e períodos de aumento, sem formar grupos a partir do resultado futuro na avaliação de seleção.

- **Erro de contagem:** MAE da média e da mediana, RMSE e viés. A média responde ao objetivo quadrático e compõe totais esperados; a mediana é o resumo apropriado para perda absoluta.
- **Erro relativo ao volume:** WAPE por grupo, com aviso explícito quando a soma observada for zero; MASE somente com escala sazonal calculada no treino.
- **Ocorrência:** Brier e calibração para `P(Y > 0)`. Precisão, sensibilidade e falsos alertas usam limites escolhidos na validação.
- **Eventos e picos:** probabilidade de ultrapassar limiares definidos antes da avaliação, detecção de aumentos e erro de magnitude nos picos.
- **Distribuição:** WIS, cobertura e largura dos intervalos. Uma cobertura alta sem considerar a largura pode premiar intervalos pouco informativos.
- **Totais estaduais:** avaliar diretamente as somas observadas e previstas por UF. Intervalos agregados atuais simulam independência municipal e podem subestimar a incerteza por dependência espacial.

Inclua um baseline sempre zero para diagnóstico de séries esparsas, sem tratá-lo como solução aceitável para vigilância. Faixas de escala e limiares precisam vir apenas do treino/validação, não dos alvos de teste.

**Critério para aprovar um modelo:** definir previamente a métrica principal e as margens operacionais; o ganho deve se repetir em cortes temporais e sementes e não pode esconder deterioração relevante em surtos, falsos alertas, calibração ou totais estaduais. Reamostrar blocos temporais pareados para a incerteza das diferenças; as previsões municipais e horizontes sobrepostos não são observações independentes.

### Etapa D — Testar melhorias em experimentos isolados

1. Estabelecer referência com regressão de contagem e sazonalidade, além dos baselines atuais. Só acrescentar modelos de árvores se houver ganho consistente e vantagem operacional.
2. Fazer ablações de tendências recentes, semanas desde o último caso, proporção recente de zeros, sazonalidade plurianual e informação de municípios vizinhos disponível na origem.
3. Avaliar população municipal como exposição somente com denominadores versionados e temporalmente compatíveis; manter métricas de contagem para planejamento.
4. Incluir clima apenas com fonte, cobertura e disponibilidade histórica no momento de cada previsão. Não usar clima futuro observado em backtests; previsões meteorológicas requerem arquivos históricos de previsão.
5. Comparar a binomial negativa atual com modelos hurdle ou zero-inflacionados apenas se os diagnósticos mostrarem que a distribuição atual não representa a ocorrência. Muitos zeros, por si só, não provam excesso de zeros.
6. Investigar dependência espacial e calibrar intervalos estaduais antes de usar incerteza agregada para decisões.

Alterar um conjunto de fatores por vez, guardar configurações e artefatos e comparar com a mesma janela de avaliação. Uma correção de métrica ou qualidade de dado não é, por si só, ganho preditivo.

### Etapa E — Avaliar prospectivamente

Arquivar previsões datadas antes que os alvos ocorram, junto com os hashes do painel, das fontes e do checkpoint. Atualizar previsões sem sobrescrever versões anteriores. A avaliação prospectiva começa quando houver uma sequência suficiente de origens arquivadas e resultados maduros.

## 4. Limites conhecidos da referência atual

- O teste de 2026 é parcial e retrospectivo; os arquivos públicos podem refletir revisões posteriores aos períodos avaliados.
- O atraso padrão de oito semanas é uma aproximação conservadora, não uma estimativa validada para todas as doenças, estados e épocas.
- Os atributos são históricos e territoriais; clima, população, mobilidade e sinais clínicos não fazem parte do modelo atual.
- Os intervalos por UF pressupõem independência entre sorteios municipais. A soma das médias municipais é um total esperado, mas a incerteza associada requer validação espacial.
- As previsões com origem em 04/10/2026 para as semanas 41–44 são o artefato da primeira execução; não representam uma emissão atualizada para uso prospectivo.

## 5. Referências

- [Bracher et al. — avaliação de previsões epidêmicas intervalares](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1008618): definição do WIS e avaliação probabilística.
- [Ministério da Saúde / Sinan — calendário epidemiológico 2025](https://portalsinan.saude.gov.br/sistemas-auxiliares/sinan-relatorios/43-institucional/175-calendario-epidemiologico-2025): calendário de referência e semana 53 de 2025.
