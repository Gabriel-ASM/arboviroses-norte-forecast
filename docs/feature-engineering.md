# Campos e engenharia de atributos

Análise preliminar dos três dicionários oficiais obtidos em 12/10/2026. Nomes aparecem em minúsculas nos PDFs; normalizar nomes recebidos e conferir esquema por ano. Não foram medidas completude, correlação ou importância preditiva sem os dados.

## Matriz de decisão

| Campo | Uso | Regra |
| --- | --- | --- |
| `tp_not` | Seleção de notificações individuais | Código 2 nos três PDFs; conferir exportação |
| `id_agravo` | Identificação da doença | Conferir CID e origem do arquivo |
| `dt_sin_pri`, `sem_pri` | Eixo temporal do alvo | Evento não equivale à disponibilidade |
| `dt_notific`, `sem_not`, `nu_ano` | Auditoria e alvo alternativo | Ano de notificação pode diferir do ano de sintomas |
| `sg_uf`, `id_mn_resi` | Recorte e agrupamento | Residência; códigos como texto |
| `sg_uf_not`, `id_municip` | Fluxo de notificação | Não substituir residência silenciosamente |
| `classi_fin` | Definição do desfecho | Versionar mapeamento; nunca atributo de caso futuro |
| `criterio` | Sensibilidade da definição | Não compartilhar códigos entre doenças sem conferência |
| `dt_digita` | Proxy de primeira entrada | Não captura revisões nem publicação no portal |
| `dt_encerra` | Maturação | Não simular conhecimento passado com encerramento futuro |
| `nu_idade_n` | Composição histórica opcional | Idade codificada com unidade; não interpretar diretamente como anos |
| `cs_sexo` | Composição histórica opcional | Preservar ignorados; somente agregados já conhecidos |
| `evolucao`, `dt_obito` | Desfechos secundários | Excluir dos preditores iniciais |

Características do paciente futuro não são entradas conhecidas da previsão municipal. Proporções demográficas históricas só entram após avaliar cobertura e ganho. Campos clínicos, exames, internação e encerramento ficam fora do MVP pela disponibilidade tardia e heterogeneidade.

## Inconsistência documental a resolver

Dengue (p. 12) e chikungunya (p. 11) apresentam em `classi_fin`: 1=confirmado, 2=descartado, 8=inconclusivo e branco/0/9=ignorado. Entretanto, regras próximas referem-se a “Classificação=13 Chikungunya”. O catálogo de dengue também menciona categorias clínicas específicas. Portanto, não assumir codificação uniforme em toda a série.

Zika (p. 6) apresenta 1=confirmado, 2=descartado e 9=ignorado. Em `criterio`, zika lista 3=em investigação, enquanto dengue/chikungunya listam 3=clínico. Um recodificador compartilhado sem versão produziria erros.

Na ingestão, levantar valores por doença/ano, conferir documentação histórica e resolver divergências com fontes oficiais antes de gerar o alvo. Criar mapeamento versionado. Códigos desconhecidos devem bloquear a geração até decisão explícita. Nulos/ignorados não são automaticamente descartados nem confirmados. Documentar o tratamento de inconclusivos e ignorados na definição de casos prováveis.

## Atributos derivados

Na origem `t`, usar somente o conjunto disponível até `t`. Definir a semana mais recente utilizável conforme atraso/maturidade; registrar sua distância até o alvo. Uma observação atrasada várias semanas não deve ser chamada de última semana observada sem indicar a defasagem.

- Contagens defasadas em 1, 2, 3, 4, 8, 12, 26 e 52 semanas; `log1p` opcional na entrada, alvo na escala de contagem.
- Médias/somas de 4, 8 e 12 semanas, deslocadas antes do cálculo e com máscaras de cobertura.
- Diferenças absolutas de janelas para tendência; evitar razões com denominador zero.
- Calendário futuro conhecido, com tratamento de semana 53.
- Embeddings de município/UF, categoria desconhecida e fallback documentado.
- Máscaras de ausência e quantidade de semanas observadas.

Não interpolar com futuro nem padronizar usando a série completa. Modelos globais compartilham informação entre municípios; ainda assim, informar quando o histórico local for insuficiente.

## Páginas dos originais

| Conteúdo | Dengue | Chikungunya | Zika |
| --- | --- | --- | --- |
| Idade codificada | 3 | 3 | 3 |
| Município de residência | 5 | 5 | 5 |
| Classificação final | 12 | 11 | 6 |
| Primeira digitação | 21 | 19 | 8 |

Ver [originais e manifesto](dictionaries/README.md). A inspeção orienta o esquema; utilidade preditiva será medida em backtests e ablações.
