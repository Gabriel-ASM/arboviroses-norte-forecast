# Resultados da primeira execução completa

Execução local de 12/10/2026. Esta página resume os relatórios corrigidos gerados pelo pipeline; microdados, checkpoints, previsões linha a linha e relatórios completos permanecem em `data/` e `outputs/`, que são ignorados pelo Git.

## Dados e definição operacional

Foram baixados 50 ZIPs anuais oficiais, cerca de 914 MB no total: dengue de 2000 a 2026, chikungunya de 2015 a 2026 e zika de 2016 a 2026. Para manter uma janela comparável entre doenças, o painel e os modelos desta execução usam 2016–2026. Os recursos mais antigos estão preservados localmente, mas não foram incluídos no painel.

O painel contém 450 municípios da Região Norte, identificados com o cadastro territorial do IBGE. A definição principal contabiliza notificações individuais (`tp_not=2`) não descartadas, exclui duplicidades marcadas quando o campo está disponível e aplica a classificação final por doença. Foram agregados os seguintes registros:

| Doença | Registros contabilizados | Residências sem correspondência municipal excluídas | Divergências `SEM_PRI`/data |
| --- | ---: | ---: | ---: |
| Dengue | 392.028 | 10 | 4 |
| Chikungunya | 57.954 | 2 | 0 |
| Zika | 20.729 | 12 | 0 |

Os códigos municipais sem correspondência foram excluídos para não criar localidades artificiais. Não houve semana epidemiológica inválida nem duplicidade sinalizada nos registros contabilizados. O detalhamento restante está em `data/processed/weekly_panel_quality.json`.

## Treinamento e avaliação

Cada doença recebeu um MLP global independente com saída binomial negativa. As entradas cobrem 52 semanas municipais, resumos estaduais, UF, calendário cíclico e embedding municipal. O último dado de entrada fica oito semanas antes da origem. O treino usa alvos até 2024; 2025 orienta early stopping; 2026 é avaliado separadamente até a maturidade da fonte.

O painel tem SHA-256 `df7f3f92f83571b69bdee0b597a66d3198c6a6e61bfe8fc4d70986dca7cac5bd`, registrado também nos três relatórios e checkpoints. A atualização de 10/10/2026 do recurso do ano mais recente, com atraso operacional de oito semanas, limita o teste a 2026-W32. Cada doença tem 95.400 alvos de validação e 57.600 alvos de teste parcial; os alvos incluem quatro horizontes sobrepostos e não são observações independentes.

O treino em CPU, com semente 42 e parada antecipada, selecionou as épocas 3 para dengue, 1 para chikungunya e 2 para zika. A validação passou a agregar a NLL pelo número de alvos válidos, e o WIS foi corrigido para o denominador `K + 0,5`. As métricas abaixo vêm da execução posterior a essas correções.

### Validação de 2025

| Doença | WIS do MLP | Melhor WIS de baseline | Baseline |
| --- | ---: | ---: | --- |
| Dengue | 0,7867 | 1,0597 | Média móvel de 4 semanas |
| Chikungunya | 0,1967 | 0,2176 | Média móvel de 4 semanas |
| Zika | 0,0119 | 0,0138 | Média móvel de 4 semanas |

### Teste parcial de 2026

Em cada célula, o valor do MLP é seguido pelo melhor baseline para **aquela métrica**. O melhor baseline pode variar por métrica.

| Doença | MAE: MLP / baseline | RMSE: MLP / baseline | WIS: MLP / baseline |
| --- | ---: | ---: | ---: |
| Dengue | 2,1647 / 2,1435 | 8,4971 / 9,8300 | 0,9801 / 1,2336 |
| Chikungunya | 0,1720 / 0,1591 | 0,8463 / 1,0527 | 0,0761 / 0,0939 |
| Zika | 0,0346 / 0,0284 | 0,1467 / 0,1627 | 0,0150 / 0,0177 |

O melhor baseline de MAE foi a média móvel de quatro semanas para as três doenças; para RMSE, foi persistência em dengue e média móvel em chikungunya e zika. O WIS do MLP foi menor que o dos baselines avaliados nas três doenças. O MLP não teve o menor MAE em nenhuma delas. A cobertura empírica dos intervalos nominais de 80% ficou acima de 91% no teste parcial, o que pede análise conjunta de cobertura e largura: intervalos largos podem cobrir mais casos e ainda assim ser pouco informativos.

Esses resultados são retrospectivos e dependem dos dados atualmente publicados pelo Sinan. Não comprovam desempenho prospectivo nem superioridade geral. Como 2026 já foi usado para diagnóstico e ajustes do pipeline, reserve novos períodos maduros para a avaliação final das próximas versões.

## Previsões emitidas

A origem mais recente compatível com a maturidade registrada foi 04/10/2026 (semana epidemiológica 40). Foram geradas 1.800 linhas municipais por doença (450 municípios × quatro semanas) e 28 linhas por doença para as sete UFs × quatro semanas. As saídas têm valores finitos e não negativos, com limites inferiores menores ou iguais aos superiores.

| Semana-alvo de 2026 | Dengue: soma esperada nas UFs | Chikungunya: soma esperada nas UFs | Zika: soma esperada nas UFs |
| --- | ---: | ---: | ---: |
| 41 | 637,1 | 26,6 | 6,8 |
| 42 | 641,4 | 28,3 | 7,1 |
| 43 | 684,2 | 26,5 | 6,8 |
| 44 | 703,6 | 28,5 | 7,8 |

As somas são valores esperados das previsões municipais. Os intervalos estaduais atuais usam sorteios municipais independentes e não capturam explicitamente dependência espacial. Como a origem é histórica, estas saídas documentam a execução e não são previsões atualizadas para uso prospectivo.

Arquivos locais:

- `outputs/forecasts/{dengue,chikungunya,zika}_2026-10-04_municipality.csv`
- `outputs/forecasts/{dengue,chikungunya,zika}_2026-10-04_uf.csv`
- `outputs/reports/{dengue,chikungunya,zika}_metrics.json`
- `outputs/models/{dengue,chikungunya,zika}.pt`

O manifesto versionado das fontes e seus hashes está em [initial-run-manifest-2026-10-12.json](initial-run-manifest-2026-10-12.json). Os dicionários utilizados estão em [docs/dictionaries](dictionaries/README.md).
