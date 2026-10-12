# Previsão de arboviroses na Região Norte

Planejamento de previsões de dengue, chikungunya e zika com dados do Sinan/SUS e modelos em PyTorch.

**Situação em 12/10/2026: planejamento.** Apenas os três dicionários oficiais foram baixados. Não há microdados, código de modelagem, treinamento ou resultados. As configurações abaixo são hipóteses de trabalho a validar.

## 1. Objetivo e granularidade

Estimar quantos casos são esperados em uma localização e período futuros, usando somente informações disponíveis na data de emissão da previsão.

| Dimensão | Proposta inicial |
| --- | --- |
| Estados | Acre, Amapá, Amazonas, Pará, Rondônia, Roraima e Tocantins |
| Localização | Município de residência, com agregação por UF |
| Frequência | Semana epidemiológica |
| Alvo | Casos prováveis por doença, município e semana de primeiros sintomas |
| Horizontes | Cada uma das próximas 1, 2, 3 e 4 semanas |
| Saídas | Média, intervalos preditivos de 80%/95% e probabilidade de pelo menos um caso |
| Treino | Histórico disponível e comparável até 2024 |
| Validação | 2025 |
| Teste reservado | 2026, inicialmente parcial |

Município × semana é a proposta para a granularidade X. Para séries esparsas, comparar município × mês ou UF × semana com critérios definidos no treino/validação. Mudar a granularidade exige reconstruir alvos, atributos, horizontes e avaliação. Bairro, coordenada e ponto arbitrário não estão garantidos pelas fontes.

Ocorrência significa casos registrados, não todas as infecções reais. Incidência por 100 mil habitantes depende de denominadores populacionais compatíveis. Probabilidade de surto exige definição própria; não equivale à probabilidade de qualquer caso.

## 2. Fontes e cobertura

| Doença | Catálogo oficial | Recurso agregado anunciado |
| --- | --- | --- |
| Dengue | [Sinan/Dengue](https://dadosabertos.saude.gov.br/dataset/arboviroses-dengue) | 2000–2026 |
| Chikungunya | [Sinan/Febre de Chikungunya](https://dadosabertos.saude.gov.br/dataset/arboviroses-febre-de-chikungunya) | 2015–2026 |
| Zika | [Sinan/Vírus Zika](https://dadosabertos.saude.gov.br/dataset/arboviroses-zika-virus) | 2016–2026 |

Consulta em 12/10/2026. Há também recursos anuais anteriores em alguns catálogos. A listagem não comprova cobertura completa nem comparabilidade: inventariar versões, esquemas e disponibilidade por ano/UF na próxima etapa. Anos anteriores à cobertura não são zeros.

Começar com modelos separados por doença, aproveitando o histórico válido de cada uma. Comparar uma janela comum desde 2016 e, para dengue, histórico completo versus recente, usando validação temporal. Mudanças de sistema e definição podem reduzir a utilidade de anos antigos.

Os [dicionários originais](docs/dictionaries/README.md) têm URLs e hashes registrados. A [análise dos campos](docs/feature-engineering.md) orienta o feature engineering. Campo documentado não garante sua presença em todos os arquivos anuais.

## 3. Alvo, recorte e painel

1. Conferir o agravo e o tipo de registro. Quando aplicável, selecionar notificações individuais (`tp_not=2`); não contar registros de surtos ou agregados como indivíduos.
2. Filtrar a UF de residência (`sg_uf`) e agrupar por município de residência (`id_mn_resi`). Não substituir residência por local de atendimento/notificação.
3. Construir o alvo com `dt_sin_pri`/`sem_pri`. Registrar perdas por data ausente. Uma série por `dt_notific` será um alvo alternativo identificado separadamente.
4. Aplicar a definição oficial de casos prováveis, com mapeamento por doença/ano/versão. Os catálogos descrevem suspeitos notificados excluídos os descartados; conferir os códigos e o tratamento de ignorados/inconclusivos antes de operacionalizar a regra.
5. Deduplicar apenas com identificadores e regras justificáveis. Município, idade e data iguais não provam que duas notificações são da mesma pessoa.
6. Criar a grade município × semana × doença com cobertura explícita. Preencher zero somente quando a fonte estiver completa e a ausência de registros representar ausência de casos. Preservar desconhecidos e mascará-los na função de perda.

Contrato futuro: `disease`, `municipality_code`, `uf`, `week_start`, `epidemiological_year`, `epidemiological_week`, `target_count`, `coverage_status`, `available_as_of`, `source_snapshot`.

Preservar códigos geográficos como texto. Compatibilizar os códigos municipais de 6 dígitos do Sinan com os de 7 dígitos do IBGE mediante tabela oficial. Adotar o calendário epidemiológico brasileiro; não assumir equivalência com semana ISO. Para os splits, atribuir cada semana ao ano civil de sua data final: todo alvo de treino termina até 31/12/2024, e uma semana que cruza a virada pertence ao bloco seguinte. Preservar também o ano epidemiológico original e documentar diferenças.

## 4. Protocolo temporal e vazamento

A separação solicitada é um **holdout temporal**, não validação cruzada aleatória. Fazer backtests com origem móvel dentro do período até 2024: por exemplo, treino até 2021/avaliação em 2022, expandindo depois para avaliar 2023 e 2024, conforme cobertura.

Usar 2025 para arquitetura, hiperparâmetros, early stopping, janela histórica e calibração. Congelar tudo antes de consultar métricas de 2026. Na configuração principal, manter os pesos ajustados com alvos até 2024. Eventual reajuste até 2025 será outro experimento, explicitamente identificado.

Cada amostra tem uma origem e quatro alvos futuros. Remover ou mascarar horizontes que cruzem o limite do bloco: nenhum alvo de 2025 pode contribuir para a perda de treino. O contexto pode cruzar a fronteira; prever janeiro de 2025 pode usar observações anteriores de 2024. Em avaliação sequencial, semanas anteriores de validação/teste podem entrar como contexto somente se já disponíveis na origem, sem reajustar pesos no teste.

Imputadores, escalas, seleção de variáveis e vocabulários aprendidos são ajustados no treino de cada fold. Médias móveis, agregados espaciais e dados de outras doenças devem respeitar a disponibilidade na origem. Não interpolar com observações futuras.

### Atrasos, revisões e teste de 2026

Uma extração atual pode conter correções desconhecidas nas origens históricas. Dividir por ano não elimina esse vazamento. `dt_notific` e `dt_digita` não recuperam o histórico de revisões; a digitação documenta a primeira inclusão, não todas as atualizações nem a publicação no portal.

Preferir snapshots históricos para reconstruir o conhecimento disponível em cada origem. Se não existirem, declarar avaliação retrospectiva com dados revisados, usar defasagens conservadoras e análise de sensibilidade. Isso não comprova desempenho prospectivo. Nowcasting, se necessário, será uma etapa separada, ajustada sem o teste.

Em 12/10/2026, o ano de teste não terminou. Avaliar apenas semanas encerradas e maduras segundo regra de atraso definida antes do teste. Informar data da extração, última semana elegível, número de semanas e revisões. Não preencher meses futuros com zero. A avaliação anual final depende da consolidação; resultados parciais não devem orientar a seleção do modelo reservado.

## 5. Engenharia de atributos

O MVP usará histórico de casos, calendário e identificação geográfica. Ver [matriz de campos e inconsistências](docs/feature-engineering.md).

| Grupo | Proposta | Restrição |
| --- | --- | --- |
| Histórico | Defasagens de 1, 2, 3, 4, 8, 12, 26 e 52 semanas | Somente valores disponíveis na origem |
| Tendência | Médias/somas em 4, 8 e 12 semanas; diferenças absolutas | Janelas passadas, sem média centrada |
| Sazonalidade | Seno/cosseno e indicadores do calendário | Regra explícita para semana 53 |
| Localização | Embeddings de município e UF | Vocabulário de treino e categoria desconhecida |
| Qualidade | Máscaras de ausência, cobertura e atraso observado | Não usar qualidade conhecida apenas posteriormente |
| Espaço | Histórico estadual e de vizinhos | Extensão posterior, sempre defasada |
| Outras doenças | Contagens históricas cruzadas | Extensão com cobertura/latência compatíveis |

População IBGE, clima e território ficam para uma segunda etapa, sem download agora. Registrar versão e latência se incorporados. Usar clima passado ou previsões arquivadas disponíveis na origem; nunca clima futuro realizado. Exigir ablações em 2025 para justificar cada grupo adicional.

## 6. Caminho em PyTorch

1. **Baselines:** persistência, média móvel e sazonal ingênuo com calendário alinhado, inclusive semana 53. Acrescentar regressão Poisson/binomial negativa com calendário e defasagens.
2. **Primeiro neural:** MLP global por doença, compartilhando parâmetros entre municípios, com atributos históricos e embeddings. Comparar com os baselines antes de aumentar a complexidade.
3. **Candidato temporal:** TCN causal global por doença, janela de 52 semanas, quatro previsões diretas. Ponto de partida: três blocos, 32 canais, kernel 3, dilatações 1/2/4, dropout 0,1 e agregação do histórico sem acesso posterior à origem. Comparar janela de 26 semanas. Esses números não foram selecionados experimentalmente.
4. **Extensões:** GRU, compartilhamento entre doenças e grafos espaciais somente após ganho demonstrado na validação.

Propor saída binomial negativa com média positiva `mu` e dispersão positiva `r`, por horizonte: `Var(Y)=mu+mu²/r`. Minimizar log-verossimilhança negativa com máscara de alvos válidos. Na [NegativeBinomial do PyTorch](https://docs.pytorch.org/docs/stable/distributions.html#negativebinomial), conferir a parametrização na implementação: `total_count=r`, `probs=mu/(r+mu)`. Aplicar transformações positivas e estabilidade numérica. Comparar Poisson; inflação de zeros somente se justificada em 2025.

Derivar `P(Y>0)` e intervalos da distribuição, avaliando calibração. Somar médias municipais gera a média estadual; somar quantis municipais não gera intervalo estadual válido. Intervalos por UF exigem trajetórias com dependência adequada ou modelo estadual próprio.

Planejar Python, PyTorch, processamento tabular e Parquet. Fixar versões e sementes na implementação; registrar configuração, snapshot, hardware, duração, melhor época e checkpoint. Começar em CPU e medir antes de decidir GPU. Nenhuma instalação ou infraestrutura é necessária nesta entrega.

## 7. Avaliação e decisão

| Aspecto | Métrica |
| --- | --- |
| Contagem | MAE e RMSE por horizonte/doença |
| Escala | MASE quando denominador sazonal for não nulo; informar exclusões |
| Distribuição | Log-verossimilhança e WIS com quantis predefinidos |
| Intervalos | Cobertura e largura de 80%/95% |
| Qualquer caso | Brier score e calibração; PR-AUC quando ambas as classes existirem |
| Heterogeneidade | Município, UF, doença, volume histórico e períodos de pico |

Relatar médias macro municipais e resultados ponderados por volume. Não usar MAPE como principal métrica em séries com zeros. Incluir semanas sem casos e a previsão constante zero como referência para doenças raras. Examinar magnitude e data dos picos. Para incerteza das diferenças, usar reamostragem em blocos temporais que preserve dependências.

Selecionar por WIS médio macro em 2025, acompanhado de MAE e calibração por doença/horizonte, com quantis e amostras elegíveis iguais entre modelos. O neural deve demonstrar melhora consistente sobre o melhor baseline. Não há ganho prometido.

## 8. Roteiro de implementação posterior

| Etapa | Entrega | Condição para avançar |
| --- | --- | --- |
| Inventário | Recursos por doença/ano, esquemas e versões | Resolver classificação/cobertura sem métricas de 2026 |
| Ingestão | Download seletivo, hashes e recorte do Norte | Rastreabilidade, sem duplicar formatos da mesma base |
| Qualidade | Datas, geografia, duplicatas, cobertura, revisões | Distinguir zero de ausência e registrar exclusões |
| Painel | Município × semana × doença | Conferir totais com fonte e explicar diferenças |
| Baselines | Backtests e resultados de 2025 | Verificar fronteiras e disponibilidade dos atributos |
| PyTorch | MLP, TCN, logs e ablações | Selecionar e congelar em 2025 |
| Teste | Relatório de 2026 parcial/consolidado | Declarar maturidade e não selecionar pelo teste |
| Consulta | Previsão por local, doença, origem e horizonte | Retornar incerteza, versão e cobertura |

Contrato de consulta planejado: entrada com doença, código geográfico, nível territorial, frequência, data de emissão e horizonte; saída com período-alvo, média, intervalos, probabilidade, versão e corte dos dados. Rejeitar granularidades não treinadas e informar histórico insuficiente. Não é diagnóstico individual.

Na implementação, testar calendários/viradas de ano, fronteiras de alvos, códigos de residência, ausência versus zero, distribuição e indisponibilidade de dados futuros. Estrutura futura sugerida: `src/ingestion`, `src/features`, `src/models`, `src/evaluation`, `configs` e `tests`. Não foram criados módulos fictícios nesta etapa.

## 9. Conteúdo e continuidade

- [Texto atual.md](Texto%20atual.md): proposta metodológica revisada.
- [docs/feature-engineering.md](docs/feature-engineering.md): campos e decisões iniciais.
- [docs/dictionaries/README.md](docs/dictionaries/README.md): PDFs oficiais e procedência.
- `docs/dictionaries/manifest.json`: URLs, data, tamanhos e hashes SHA-256.
- `links.txt`: referências originais.

O próximo trabalho começa pelo inventário de esquemas e pela resolução das classificações; depois, download e preparação. Os PDFs são mantidos sem alteração e atribuídos ao Ministério da Saúde. Conferir termos dos recursos antes de futura redistribuição. Microdados, credenciais e artefatos de treinamento ficam fora do Git.
