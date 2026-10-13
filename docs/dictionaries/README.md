# Dicionários oficiais do Sinan

Originais do Ministério da Saúde, obtidos em 12/10/2026 sem alteração. Os catálogos indicavam atualização dos recursos de dicionário em 14/07/2025; essa data não comprova compatibilidade com todos os anos da série.

| Doença | Arquivo local | Download oficial | Páginas |
| --- | --- | --- | --- |
| Dengue | [PDF](dic_dados_dengue.pdf) | [Fonte](https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SINAN/Dengue/dic_dados_dengue.pdf) | 22 |
| Chikungunya | [PDF](dic_dados_chikungunya.pdf) | [Fonte](https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SINAN/Chikungunya/dic_dados_chikungunya.pdf) | 19 |
| Zika | [PDF](dic_dados_zika.pdf) | [Fonte](https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SINAN/Zikavirus/dic_dados_zika.pdf) | 8 |

O [manifesto](manifest.json) registra catálogos, URLs diretas, data de obtenção, tamanhos e SHA-256. Os microdados atuais ficam em `data/raw/`, fora do Git. Consulte a [análise dos campos](../feature-engineering.md): os PDFs atuais não cobrem por si só todos os códigos históricos; o [dicionário online combinado Dengue/Chikungunya de 2015](https://portalsinan.saude.gov.br/images/documentos/Agravos/Dengue/DIC_DADOS_ONLINE.pdf) documenta `CLASSI_FIN=5` como descartado, `10`–`12` como categorias de dengue e `13` como chikungunya.

Os documentos mantêm autoria e condições de uso da fonte; não são documentação autoral do projeto.
