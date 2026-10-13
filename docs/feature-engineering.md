# Campos e engenharia de atributos

Análise preliminar dos dicionários oficiais obtidos em 12/10/2026. O pipeline normaliza nomes de colunas e valida os campos essenciais a cada arquivo anual. Presença documentada não garante cobertura uniforme entre anos.

## Campos utilizados

| Campo | Uso implementado | Regra |
| --- | --- | --- |
| `tp_not` | Selecionar ficha individual | Incluir `2`; outras categorias não entram como casos individuais |
| `id_agravo` | Auditoria da doença | Conferir código do agravo e o arquivo de origem |
| `sem_pri` | Semana do alvo | Referência principal para ano e semana epidemiológica |
| `dt_sin_pri` | Alternativa temporal e auditoria | Usar quando `sem_pri` não puder ser interpretada |
| `id_mn_resi` | Município do alvo | Campo de residência, não município de atendimento/notificação |
| `sg_uf` | Auditoria geográfica | O recorte principal deriva o estado do código municipal de residência |
| `classi_fin` | Definição do caso | Aplicar códigos de descartado, confirmação e outra arbovirose específicos por doença |
| `nduplic_n` | Duplicidade sinalizada | Excluir código `2`, quando o campo existe |
| `dt_notific`, `sem_not`, `nu_ano` | Diagnóstico temporal | Datas de notificação; não substituem a data de sintomas |
| `dt_digita` | Diagnóstico de atraso | Primeira inclusão, não histórico completo de revisão |
| `dt_encerra` | Análise de maturação | Não usar como preditor de caso futuro |
| `nu_idade_n`, `cs_sexo` | Análise descritiva futura | Não entram no MVP; dados de paciente futuro não são conhecidos na origem |
| `evolucao`, `dt_obito` | Desfecho secundário futuro | Excluir dos preditores iniciais |

Os registros que entram no alvo principal devem satisfazer `tp_not=2`, residência em estado do Norte e `nduplic_n != 2`, quando o campo estiver disponível. Para `classi_fin`, o pipeline aceita o código atual (1 confirmado, 2 descartado, 8 inconclusivo) e o esquema combinado (5 descartado, 10 dengue, 11 dengue com sinais de alarme, 12 dengue grave, 13 chikungunya). O alvo de dengue exclui 2, 5 e 13; o de chikungunya exclui 2, 5, 10, 11 e 12; o de zika exclui 2. Valores em branco, 0, 8 e 9 não são convertidos em descartados. Códigos não mapeados interrompem a preparação. A alternativa confirmada usa os códigos positivos específicos de cada doença.

## Distinção entre campos de classificação

`classi_fin` é a classificação final do caso. Os dicionários atuais apresentam 1=confirmado, 2=descartado e 8=inconclusivo; o formulário combinado Dengue/Chikungunya também usa 5=descartado, 10=dengue, 11=dengue com sinais de alarme, 12=dengue grave e 13=chikungunya. Portanto, `classi_fin=13` é uma categoria real do esquema combinado. `clinc_chik` é um campo separado de apresentação clínica, habilitado para registros classificados como chikungunya; ele não substitui a classificação final.

`criterio` também é específico por formulário: por exemplo, o código 3 pode indicar “em investigação” no dicionário de zika e “clínico” em dengue/chikungunya. Não compartilhar recodificadores entre doenças sem validar ano, nome de campo e origem.

`nduplic_n` indica duplicidades identificadas no sistema; o valor 2 significa duplicidade que não deve ser contada. O pipeline exclui essa categoria quando o campo existe e registra quando o campo falta. Ele não tenta identificar duplicidade por combinações de município, data e idade.

## Campos de saída e disponibilidade

O painel preparado contém `disease`, `municipality_code`, `uf`, `epi_year`, `epi_week` e `cases`. Os códigos de município Sinan são preservados com seis dígitos; a referência territorial do IBGE conserva o identificador oficial de sete dígitos e o nome municipal. A semana epidemiológica brasileira começa no domingo e termina no sábado; o código de semana fornecido pelo Sinan tem precedência sobre o cálculo por data.

A janela de atributos e alvos começa em 2016 para manter um período comum e comparável entre doenças. Os arquivos mais antigos têm esquemas e classificações distintos e ficam fora do painel padrão até que exista um mapeamento versionado para eles.

O MLP usa 52 contagens municipais até a semana `origem - lag`, totais estaduais nas janelas de 1, 4, 12 e 52 semanas até o mesmo corte, indicadores da UF, atributos cíclicos para as quatro semanas futuras e embedding municipal. O vocabulário municipal do embedding é formado somente com municípios que têm casos até 2024; demais municípios usam uma categoria compartilhada, evitando criar parâmetros treinados apenas com ocorrências de validação/teste. O contexto estadual permite que municípios sem casos no treino recebam informação temporal das outras localidades do estado. Quando disponível, o cadastro IBGE permite incluir municípios sem qualquer caso observado no painel.

## Defasagens e validação

O atraso padrão é oito semanas. Para uma origem `t`, a entrada termina em `t-8`, enquanto os alvos são `t+1` a `t+4`. Isso preserva o horizonte futuro sem tratar semanas recentes como completas, mas o atraso é apenas aproximação: os recursos públicos atuais não reconstroem todas as versões históricas dos casos.

Todo agregado usa semanas anteriores à origem. Não se interpolam semanas futuras. O painel considera zero a ausência de registros somente dentro de anos cujos recursos foram ingeridos em sequência. Uma lacuna de arquivo anual bloqueia a preparação para evitar que ausência de cobertura vire zero. O número de semanas de maturidade é informado nas métricas.

## Referências nos PDFs locais

| Conteúdo | Dengue | Chikungunya | Zika |
| --- | --- | --- | --- |
| Idade codificada | p. 3 | p. 3 | p. 3 |
| Município de residência | p. 5 | p. 5 | p. 5 |
| Classificação final | p. 12 | p. 11 | p. 6 |
| Duplicidade | p. 21 | p. 18 | p. 5 |

Veja os [originais e o manifesto](dictionaries/README.md). A inspeção dos dicionários orienta o esquema; utilidade preditiva e comparabilidade serão verificadas com os arquivos anuais.
