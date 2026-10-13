# Resultados do retreino orientado por WAPE

Execução local em 12/10/2026, usando os dados, painel e arquivos brutos já presentes no repositório. O ajuste gerou novos checkpoints e previsões, sem baixar dados. Os artefatos completos ficam em `outputs/`, fora do Git.

## O que significa a porcentagem

A métrica principal é a **WAPE** (*weighted absolute percentage error*):

`WAPE (%) = 100 × soma(|casos observados − casos previstos|) / soma(casos observados)`

O cálculo usa a contagem esperada (`mu`, campo `expected_cases`) em cada par de previsão. Para este recorte, prever sempre zero tem WAPE de 100%. Assim, 86,5% indica que a soma dos erros absolutos é 86,5% do volume observado; 100,5% indica erro total ligeiramente maior que o controle sempre zero. A WAPE não é o percentual de municípios errados, nem o percentual de previsões corretas, e pode passar de 100%.

| Doença | WAPE do modelo | WAPE de sempre zero | Diferença para sempre zero | MAE por par | Casos observados nos pares |
| --- | ---: | ---: | ---: | ---: | ---: |
| Dengue | **86,5%** | 100,0% | 13,5 p.p. menor | 1,7084 | 113.696 |
| Chikungunya | **100,5%** | 100,0% | 0,5 p.p. maior | 0,1153 | 6.608 |
| Zika | **100,1%** | 100,0% | 0,1 p.p. maior | 0,0163 | 940 |

O denominador soma casos por par município-semana-horizonte. Há 57.600 pares por doença, equivalentes a 14.400 município-semanas únicas avaliadas quatro vezes, uma por horizonte. Por isso, os totais da última coluna são quatro vezes os casos das semanas únicas: 28.424 para dengue, 1.652 para chikungunya e 235 para zika. Pares repetidos não são observações independentes.

Visto como comparação simples, dengue tem menos erro agregado que o controle sempre zero. Chikungunya e zika ficam muito perto de 100%, portanto praticamente empatam com esse controle neste teste; os valores arredondados ficam ligeiramente acima dele. Isso não mede detecção de surtos nem ocorrência por município.

## Como o treino usa a métrica

O treino usa alvos até 2024, escolhe a época pela WAPE de 2025 e mede o teste parcial de 2026 até a semana epidemiológica 32. O modelo aprende principalmente com erro absoluto mascarado, normalizado pelo volume médio observado no treino. Esse cálculo em minibatches aproxima a WAPE de treino; a seleção de época e a métrica publicada calculam WAPE de forma agregada. A log-verossimilhança negativa binomial recebe peso auxiliar de 0,05 para conservar uma distribuição e produzir intervalos preditivos.

| Doença | Melhor época | WAPE da validação de 2025 | WAPE do teste parcial de 2026 |
| --- | ---: | ---: | ---: |
| Dengue | 2 | 81,24% | 86,55% |
| Chikungunya | 4 | 95,85% | 100,48% |
| Zika | 3 | 100,10% | 100,08% |

A WAPE é um erro absoluto agregado normalizado pelo volume. Em dados com muitos zeros, ela pode favorecer previsões muito pequenas para doenças esparsas; por isso, um valor perto de 100% deve ser lido junto com probabilidades de ocorrência, detecção de aumentos, intervalos e métricas por horizonte. MAPE simples não foi adotada porque é indefinida onde o observado é zero.

O teste de 2026 é parcial e já foi consultado durante o desenvolvimento; as fontes públicas podem conter revisões posteriores. Os números são um diagnóstico retrospectivo, não uma avaliação independente ou garantia prospectiva.

## Dados e definição operacional

O painel e os modelos usam a janela comparável de 2016–2026 e 450 municípios da Região Norte. Foram preservados localmente 50 arquivos anuais oficiais; anos anteriores a 2016 não entram no modelo porque exigem harmonização histórica de formulários e classificações.

A definição principal contabiliza notificações individuais (`tp_not=2`) não descartadas, exclui duplicidades marcadas quando o campo está disponível e aplica a classificação final específica por doença.

| Doença | Registros no painel | Residências sem correspondência municipal excluídas | Divergências `SEM_PRI`/data |
| --- | ---: | ---: | ---: |
| Dengue | 392.028 | 10 | 4 |
| Chikungunya | 57.954 | 2 | 0 |
| Zika | 20.729 | 12 | 0 |

O painel tem SHA-256 `df7f3f92f83571b69bdee0b597a66d3198c6a6e61bfe8fc4d70986dca7cac5bd`. Casos são notificações registradas no Sinan; não equivalem a todas as infecções ocorridas.

## Previsões municipais e estaduais

Com os novos checkpoints, foram emitidas previsões para a origem de 04/10/2026 (semana epidemiológica 40), para as semanas 41–44. Os arquivos contêm 1.800 linhas municipais por doença (450 municípios × quatro horizontes) e 28 linhas por doença para as sete UFs × quatro semanas.

| Semana-alvo de 2026 | Dengue: soma esperada nas UFs | Chikungunya: soma esperada nas UFs | Zika: soma esperada nas UFs |
| --- | ---: | ---: | ---: |
| 41 | 198,7479 | 1,2999 | 0,0071 |
| 42 | 205,5976 | 1,5677 | 0,0066 |
| 43 | 210,9578 | 1,4001 | 0,0062 |
| 44 | 194,0206 | 1,5412 | 0,0066 |

Os números são médias esperadas agregadas, não contagens inteiras observadas. As previsões de chikungunya e zika são muito pequenas, coerentes com uma rede que, sob perda absoluta, se aproxima da solução sempre zero em alvos esparsos. Não interprete isso como ausência garantida de casos. Os intervalos por UF simulam independência entre municípios e podem subestimar a incerteza espacial. A origem é histórica; esses arquivos documentam uma rodada e não são previsões atuais.

O resumo de uma linha por doença está em `outputs/reports/disease_wape_summary.csv`. Os relatórios JSON contêm WAPE geral e por horizonte/UF, MAE, RMSE, WIS, cobertura, largura dos intervalos e backtests dos baselines. Checkpoints ficam em `outputs/models/`; previsões municipais e por UF, em `outputs/forecasts/`.

## Formulação segura para divulgação

> No teste retrospectivo parcial até a semana epidemiológica 32 de 2026, a WAPE foi 86,5% para dengue, 100,5% para chikungunya e 100,1% para zika. A WAPE compara a soma dos erros absolutos ao volume observado; 100% corresponde ao controle sempre prever zero. O teste já foi consultado durante o desenvolvimento e não é uma avaliação independente.

O manifesto de fontes e hashes está em [initial-run-manifest-2026-10-12.json](initial-run-manifest-2026-10-12.json). Os dicionários utilizados estão em [dictionaries](dictionaries/README.md).
