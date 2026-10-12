# Previsão de arboviroses na Região Norte

Pipeline em Python para estimar casos semanais de dengue, chikungunya e zika por município de residência, com agregação opcional por estado. O modelo neural usa PyTorch e produz previsões probabilísticas para as quatro semanas seguintes.

**Estado em 12/10/2026:** código de ingestão, agregação, backtest de baselines, treinamento e previsão implementado. Os microdados não foram baixados neste ambiente e nenhum modelo foi treinado; portanto, ainda não há resultados epidemiológicos nem desempenho comprovado. Os PDFs dos dicionários são a única base epidemiológica versionada no Git.

## Uso

Requer Python 3.11–3.14 e acesso à internet para baixar recursos do Ministério da Saúde e, na primeira preparação, a lista municipal oficial do IBGE. A instalação do PyTorch pode ser grande; use a instalação compatível com o hardware seguindo a [página oficial do PyTorch](https://pytorch.org/get-started/locally/).

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[train]"
```

O download histórico completo pode exigir bastante disco e tráfego. Para começar com período comparável entre as três doenças:

```powershell
arboviroses catalog
arboviroses download --start-year 2016 --end-year 2026
arboviroses prepare
arboviroses fit --epochs 30
arboviroses predict --as-of 2026-10-12
```

Para usar todo o histórico disponível de dengue, inclua os anos anteriores:

```powershell
arboviroses download --diseases dengue --start-year 2000 --end-year 2026
arboviroses prepare --diseases dengue
arboviroses fit --diseases dengue
```

`prepare` mantém o cadastro municipal do IBGE, quando acessível. Se a conexão com o IBGE não estiver disponível, o modo `auto` segue com os municípios observados e registra a limitação. Para exigir o cadastro completo, use `arboviroses prepare --registry-mode required`; para trabalhar apenas offline, use `--registry-mode observed`.

Use `arboviroses predict --level uf` para agregar por estado. Pode filtrar com `--uf PA` ou consultar um município pelo código Sinan de seis dígitos ou IBGE de sete dígitos, por exemplo `--municipality 1501402`.

No treino, os pesos são escolhidos pela perda de validação de 2025 e o teste de 2026 é reportado separadamente. O modelo final é salvo em `outputs/models/`; métricas, em `outputs/reports/`; previsões, em `outputs/forecasts/`. Dados baixados ficam em `data/` e são excluídos do Git.

## O que o pipeline faz

| Etapa | Implementação |
| --- | --- |
| Fonte | Descobre os recursos anuais nos catálogos oficiais e baixa ZIPs CSV, preservando URL, versão e SHA-256 |
| Recorte | Casos de residência em RO, AC, AM, RR, PA, AP e TO |
| Unidade | Município × semana epidemiológica brasileira |
| Definição principal | Registro individual (`tp_not=2`), não descartado (`classi_fin` diferente de `2`) e não marcado como duplicata (`nduplic_n` diferente de `2`) |
| Alvo alternativo | Casos confirmados (`classi_fin=1`) |
| Calendário | `sem_pri` como referência; `dt_sin_pri` como alternativa; semana brasileira de domingo a sábado |
| Contexto | 52 semanas municipais e totais estaduais nas janelas de 1, 4, 12 e 52 semanas, sempre até 8 semanas antes da origem |
| Saídas | Quatro horizontes diretos, com média, intervalos de 80%/95% e probabilidade de pelo menos um caso |
| Geografia nova | Municípios com histórico usam embedding aprendido; município sem caso no treino usa uma categoria compartilhada de desconhecido |

A definição principal segue a nota de casos prováveis dos catálogos do SUS: suspeitos notificados, excluídos os descartados. Valores em branco, ignorados ou inconclusivos não são tratados automaticamente como descartados. Os totais resultantes são notificações registradas; não estimam diretamente todas as infecções ocorridas.

A lista do IBGE permite montar séries zeradas para municípios sem notificação no histórico, desde que a referência esteja disponível. Códigos Sinan de seis dígitos e códigos IBGE de sete dígitos são mantidos em campos separados. Se a referência do IBGE não puder ser obtida, o pipeline não consegue oferecer localidades ausentes de toda a série.

## Modelo e comparação

Cada doença é ajustada em separado. O MLP global compartilha pesos entre municípios, recebe contagens municipais `log1p` das 52 semanas observadas, resumos recentes do estado, indicador da UF, calendário futuro cíclico e embedding municipal. Saídas por horizonte são média e dispersão de uma binomial negativa, treinadas por log-verossimilhança negativa. A parametrização PyTorch é `total_count=r` e `probs=mu/(r+mu)`, cuja média é `mu`.

As referências são persistência, média móvel de quatro semanas e defasagem sazonal de 52 semanas. Elas recebem dispersão estimada no treino para calcular WIS e cobertura. O relatório inclui backtests dessas referências em 2022–2024, validação de 2025 e teste parcial de 2026. O MLP usa early stopping pela perda de 2025. Isso não constitui seleção exaustiva de hiperparâmetros nem validação cruzada da rede.

O relatório por horizonte e UF inclui MAE, RMSE, WIS, cobertura e largura dos intervalos. `--level uf` agrega as médias municipais e simula intervalos de soma sob independência entre municípios; essa hipótese não representa dependência espacial e pode subestimar incerteza estadual.

## Separação temporal e limites

Os alvos são separados pelo ano epidemiológico indicado em `sem_pri`: treino até 2024, validação em 2025 e teste em 2026. Todos os pré-processamentos do modelo usam a janela histórica anterior à origem. A validação/teste rolam semanalmente sem reajustar pesos, podendo usar semanas anteriores já observadas como contexto.

Os arquivos públicos atuais podem conter revisões que não estavam disponíveis em cada data histórica. A API/catálogo não fornece snapshots completos de todas as versões anteriores. O parâmetro padrão de oito semanas é uma aproximação conservadora para atraso de notificação; não reconstrói retrospectivamente o que o Sinan mostrava em 2024 ou 2025. Consequentemente, métricas são retrospectivas e não demonstram desempenho prospectivo.

O teste de 2026 é parcial. O fim elegível é aproximado pela data de atualização do recurso menos oito semanas. Essa regra é configurável com `--lag-weeks`, mas ainda deve ser confrontada com a latência observada. Não use o restante de 2026 como zero nem ajuste o modelo olhando os resultados reservados.

O alvo por início de sintomas pode ser revisado e pode faltar. O pipeline prefere `sem_pri` e, se ela estiver ausente, calcula a semana pela data em início de sintomas. Divergências entre semana e data são contabilizadas no relatório. Municípios sem notificação histórica dependem da lista territorial do IBGE. A base Sinan não fornece todos os preditores ambientais; clima e população ficaram fora desta primeira versão.

## Arquivos

```text
src/arboviroses/       ingestão, calendário, painel, modelo, treino e CLI
docs/                  plano, dicionários e decisões de atributos
data/                  ZIPs e painel local; ignorados pelo Git
outputs/               modelos e previsões; ignorados pelo Git
```

Dicionários originais e hashes: [docs/dictionaries](docs/dictionaries/README.md). Campos e regras: [docs/feature-engineering.md](docs/feature-engineering.md). A proposta metodológica, revisada para refletir a implementação, está em [Texto atual.md](Texto%20atual.md).

## Próximas etapas

1. Baixar um recorte piloto recente e conferir os nomes reais de colunas e formatos anuais.
2. Revisar proporção de registros descartados, duplicatas, códigos não mapeados, falhas de data e divergências `sem_pri`/`dt_sin_pri`.
3. Comparar o critério operacional de casos prováveis com a tabela anual e totais publicados pelo Ministério da Saúde.
4. Ajustar a defasagem com distribuição observada de `dt_notific`/`dt_digita` e, se possível, snapshots arquivados.
5. Rodar os baselines e uma primeira rede em CPU; conferir gráficos e intervalos por UF/doença antes de decisões sobre GPU, TCN ou atributos climáticos.
6. Congelar a seleção após validação de 2025 e emitir a avaliação de 2026 apenas como parcial até a maturação do ano.
