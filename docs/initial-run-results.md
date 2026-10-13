# Resultados do retreino e índice de erro por doença

Execução local em 12/10/2026. Os arquivos de dados, checkpoints, previsões completas e relatórios detalhados ficam em `data/` e `outputs/`, ignorados pelo Git. Esta página registra o novo critério de seleção e os resultados do retreino.

## Um número por doença

O resumo principal é a **redução do erro absoluto médio (MAE) frente a uma referência simples**. A referência escolhida para cada doença foi “sempre prever zero”, que teve o menor MAE agregado nos backtests de 2022–2024. Ela funciona como controle de séries esparsas; não é uma recomendação para vigilância operacional.

| Doença | Redução do MAE | MAE do MLP | MAE de “sempre zero” |
| --- | ---: | ---: | ---: |
| Dengue | **13,8%** | 1,701 | 1,974 |
| Chikungunya | **4,8%** | 0,1092 | 0,1147 |
| Zika | **0,0%** | 0,01632 | 0,01632 |

A conta é `100 × (1 − MAE do MLP / MAE da referência)`. Valor positivo indica redução de erro; zero indica empate; valor negativo indica aumento. O CSV de resumo arredonda o resultado a uma casa decimal. Esses valores **não são percentual de acerto**, não medem a proporção de surtos detectados e não significam que cada município foi previsto corretamente.

Para a binomial negativa, o MLP fornece uma distribuição. O índice usa a **mediana prevista** como valor pontual, porque ela é adequada à perda absoluta. Para planejar totais esperados, continua disponível a média da distribuição. No relatório JSON, `point_mae` é o MAE da mediana e `mae` é o MAE da média.

O ganho é pequeno em termos absolutos para chikungunya: cerca de 0,0055 caso por par município-semana-horizonte. Para zika, a mediana do modelo praticamente empata com “sempre zero”. Isso é especialmente relevante porque 95,1% dos alvos de chikungunya e 98,5% dos de zika não tiveram casos no recorte avaliado.

## Dados e definição operacional

Foram baixados 50 ZIPs anuais oficiais, cerca de 914 MB: dengue de 2000 a 2026, chikungunya de 2015 a 2026 e zika de 2016 a 2026. Para manter uma janela comum às três doenças, o painel e os modelos usam 2016–2026. O painel cobre 450 municípios da Região Norte. Os arquivos anteriores a 2016 foram preservados localmente, mas não entram nesta versão comparável.

A definição principal contabiliza notificações individuais (`tp_not=2`) não descartadas, exclui duplicidades marcadas quando o campo está disponível e aplica a classificação final específica por doença.

| Doença | Registros no painel | Residências sem correspondência municipal excluídas | Divergências `SEM_PRI`/data |
| --- | ---: | ---: | ---: |
| Dengue | 392.028 | 10 | 4 |
| Chikungunya | 57.954 | 2 | 0 |
| Zika | 20.729 | 12 | 0 |

O painel tem SHA-256 `df7f3f92f83571b69bdee0b597a66d3198c6a6e61bfe8fc4d70986dca7cac5bd`. Casos são notificações registradas no Sinan; não equivalem a todas as infecções ocorridas.

## Treino e avaliação

Cada doença tem um MLP global separado. A rede é treinada pela log-verossimilhança negativa da binomial negativa, e a época é selecionada pelo MAE da mediana na validação de 2025. O treino usa alvos até 2024; 2025 orienta a escolha da época; o teste parcial de 2026 vai até 2026-W32. O corte considera uma defasagem operacional de oito semanas em relação à atualização da fonte.

O retreino em CPU, com semente 42, escolheu as épocas 9 para dengue, 2 para chikungunya e 1 para zika. Foram comparadas quatro referências: sempre zero, persistência, média móvel de quatro semanas e sazonalidade de 52 semanas. A seleção da referência usa apenas o MAE agregado dos backtests de 2022–2024; “sempre zero” venceu para as três doenças. O teste de 2026 não foi usado para escolher a referência.

| Doença | MAE da mediana do MLP | MAE de sempre zero | MAE da média do MLP | RMSE da média | WIS do MLP |
| --- | ---: | ---: | ---: | ---: | ---: |
| Dengue | 1,7012 | 1,9739 | 2,0993 | 8,1485 | 0,9861 |
| Chikungunya | 0,1092 | 0,1147 | 0,1910 | 0,8513 | 0,0770 |
| Zika | 0,01632 | 0,01632 | 0,04277 | 0,1466 | 0,0151 |

A média prevista responde ao total esperado, mas pode ter MAE maior que a mediana. O índice resume o valor pontual; o MAE da média, RMSE e WIS continuam registrados para que a distribuição e os totais também possam ser analisados.

O teste parcial contém 14.400 município-semanas únicas (450 municípios × 32 semanas), com 28.424 notificações de dengue, 1.652 de chikungunya e 235 de zika. Cada município-semana pode aparecer quatro vezes, uma por horizonte de previsão, somando 57.600 pares previsão-alvo por doença. Esses pares se sobrepõem e não são observações independentes; o índice não vem acompanhado de intervalo de confiança.

Os resultados são retrospectivos. Os arquivos públicos podem incorporar revisões que não estavam disponíveis em cada data histórica, e 2026 já foi consultado durante o desenvolvimento. Portanto, os números não representam uma avaliação final independente nem comprovam desempenho prospectivo. Reserve períodos futuros ainda não examinados para essa conclusão.

## Previsões municipais e estaduais

Com os checkpoints retreinados, foram emitidas previsões para a origem de 04/10/2026, semana epidemiológica 40, compatível com a maturidade então registrada. Foram geradas 1.800 linhas municipais por doença (450 municípios × quatro horizontes) e 28 linhas por doença para as sete UFs × quatro semanas.

| Semana-alvo de 2026 | Dengue: soma esperada nas UFs | Chikungunya: soma esperada nas UFs | Zika: soma esperada nas UFs |
| --- | ---: | ---: | ---: |
| 41 | 520,4 | 29,9 | 7,1 |
| 42 | 544,1 | 31,0 | 7,4 |
| 43 | 552,1 | 31,4 | 7,9 |
| 44 | 597,2 | 30,1 | 7,6 |

As somas são médias esperadas das previsões municipais. Os intervalos estaduais simulam sorteios municipais independentes e não capturam explicitamente a dependência espacial. Como a origem é histórica, essas saídas documentam a rodada e não são previsões atuais.

O resumo local de uma linha por doença está em `outputs/reports/disease_skill_summary.csv`. Os relatórios JSON incluem os MAEs, WIS, cobertura, largura de intervalo, backtests e recortes por horizonte e UF. Os checkpoints novos ficam em `outputs/models/`; as previsões municipais e estaduais, em `outputs/forecasts/`.

## Frase segura para divulgação

> No teste retrospectivo parcial até a semana epidemiológica 32 de 2026, o MLP reduziu o MAE da mediana em 13,8% para dengue e 4,8% para chikungunya frente ao controle “sempre zero”; para zika, o resultado arredondado foi 0,0%. O teste já foi consultado durante o desenvolvimento e não é uma avaliação independente.

O manifesto versionado das fontes e seus hashes está em [initial-run-manifest-2026-10-12.json](initial-run-manifest-2026-10-12.json). Os dicionários utilizados estão em [docs/dictionaries](dictionaries/README.md).
