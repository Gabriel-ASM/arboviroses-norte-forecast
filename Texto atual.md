# Proposta metodológica

## Objetivo

Este projeto implementa um pipeline para estimar a ocorrência registrada de dengue, chikungunya e zika nos sete estados da Região Norte do Brasil: Acre, Amapá, Amazonas, Pará, Rondônia, Roraima e Tocantins. A unidade inicial de análise é o município de residência por semana epidemiológica. Para cada doença, o sistema produz previsões diretas para as quatro semanas seguintes, com média esperada, intervalos preditivos de 80% e 95% e probabilidade de pelo menos um caso. As saídas municipais podem ser consultadas individualmente ou agregadas por estado.

O objeto previsto são notificações registradas no Sinan, não todas as infecções ocorridas. A incidência por população não foi incorporada nesta versão, pois depende de acrescentar e versionar denominadores municipais compatíveis.

## Fontes e preparação

A ingestão consulta os catálogos do Portal de Dados Abertos do SUS e baixa recursos anuais em CSV compactado, com escolha de Parquet quando não houver CSV. O manifesto local registra URL, identificador do recurso, atualização e hash SHA-256. Os arquivos brutos ficam fora do Git. Para identificar municípios sem notificações históricas, o pipeline mantém uma lista territorial dos municípios da Região Norte obtida pela API de Localidades do IBGE; se ela estiver indisponível, o modo automático registra a limitação e usa apenas municípios observados.

O recorte geográfico utiliza residência (`id_mn_resi`), e a data-base do desfecho é a semana de primeiros sintomas (`sem_pri`). Quando o código de semana não pode ser interpretado, o pipeline calcula a semana a partir de `dt_sin_pri`. A semana epidemiológica brasileira começa no domingo e termina no sábado. Divergências entre o campo de semana e a data são contabilizadas. Códigos municipais do Sinan com seis dígitos permanecem separados dos códigos oficiais IBGE de sete dígitos.

A definição operacional principal de casos prováveis inclui notificações individuais (`tp_not=2`), exclui casos descartados (`classi_fin=2`) e remove duplicidades marcadas pelo próprio sistema (`nduplic_n=2`), quando esse campo está disponível. Valores ignorados, inconclusivos ou em branco não são convertidos em descartados. Como alternativa, o pipeline permite contar somente casos confirmados (`classi_fin=1`). Essas regras devem ser confrontadas com esquemas e totais publicados para cada ano antes da interpretação epidemiológica. Os dicionários, a procedência e as decisões sobre os campos estão registrados no repositório.

Os recursos anuais precisam formar uma sequência sem lacunas entre o primeiro e o último ano baixado. Essa validação evita converter ausência de arquivo em zero. Uma vez estabelecida a cobertura anual, as observações são agregadas em município × doença × ano/semana epidemiológica. As semanas sem registros são representadas como zero dentro do período coberto.

## Atributos e previsões

Para uma origem de previsão `t`, o modelo recebe até 52 contagens semanais cujo fim está oito semanas antes da origem (`t-8`). Os quatro alvos correspondem às semanas `t+1` a `t+4`. Essa defasagem reduz o uso de semanas recentes ainda incompletas, sem deslocar os períodos-alvo para trás. A configuração de oito semanas é uma aproximação conservadora e ajustável, não uma estimativa de atraso validada empiricamente.

Os atributos incluem contagens municipais históricas transformadas por `log1p`, totais estaduais em janelas passadas de 1, 4, 12 e 52 semanas, indicadores da UF, variáveis cíclicas do calendário futuro e embedding municipal. Municípios com casos no período de treino têm vetor geográfico aprendido; os demais usam uma categoria compartilhada de desconhecido e recebem contexto temporal agregado do estado. O pipeline não incorpora nesta etapa clima, população, mobilidade, sinais clínicos ou atributos individuais.

A base principal do modelo é uma rede MLP global por doença, com camadas ocultas de 128 e 64 unidades e dropout de 0,1. O compartilhamento entre municípios permite aprender padrões temporais comuns. Uma saída por horizonte parametriza a média `mu` e a dispersão `r` de uma binomial negativa. Na convenção do PyTorch, usa-se `total_count=r` e `probs=mu/(r+mu)`, o que resulta em média `mu` e variância `mu + mu²/r`. O treinamento minimiza a log-verossimilhança negativa. A época é selecionada por early stopping na validação de 2025.

As previsões de referência são persistência da última contagem disponível, média móvel de quatro semanas e defasagem sazonal de 52 semanas. O código calcula backtests dessas referências para 2022–2024. Esses backtests ainda não foram executados sobre os microdados.

## Avaliação temporal

A divisão é cronológica e se aplica aos períodos-alvo: treino até 2024, validação em 2025 e teste em 2026. Os exemplos usam alvos futuros diretos; nenhum alvo de validação ou teste participa da perda de treino. As previsões podem ser avaliadas em origem móvel, usando semanas anteriores que já seriam conhecidas naquela origem, sem reajustar os pesos durante o teste.

As métricas implementadas são MAE, RMSE, WIS, cobertura e largura média dos intervalos por horizonte e UF. A avaliação inclui os baselines e é desagregada por doença. Para a agregação estadual, somam-se as médias municipais e simulam-se intervalos pela soma de sorteios municipais independentes. Como arboviroses podem ser espacialmente correlacionadas, essa hipótese pode subestimar a incerteza estadual; os intervalos agregados precisam dessa ressalva.

O teste de 2026 é parcial. A data de maturidade é aproximada pela última atualização registrada no recurso menos oito semanas. Os catálogos públicos podem apresentar séries revisadas, sem snapshots completos do que estava disponível em cada origem histórica. A defasagem reduz a exposição a notificações recentes, mas não reproduz todas as revisões do Sinan. Assim, os resultados futuros serão retrospectivos; não devem ser apresentados como demonstração de desempenho prospectivo.

## Escopo da implementação e estado dos resultados

Foram implementados os comandos para consultar o catálogo, baixar os arquivos anuais, construir o painel semanal, registrar indicadores de qualidade, treinar os baselines e o MLP, avaliar os splits e emitir previsões municipais ou estaduais. Os parâmetros e dados locais ficam fora do repositório.

Até esta revisão, os microdados ainda não foram baixados e nenhum treinamento foi realizado. Portanto, não há arquitetura empiricamente escolhida, hiperparâmetros validados, métricas, duração de treino ou evidência de superioridade sobre os baselines. A etapa seguinte é executar um recorte piloto, conferir os esquemas reais dos arquivos, reconciliar as definições de casos e, só então, rodar a avaliação temporal completa. A implementação e as instruções atualizadas estão no [README do projeto](README.md).
