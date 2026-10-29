🏗️ Plataforma de Recrutamento: RH Lakehouse Automatizado

🎯 Objetivo do Projeto

Este projeto consiste no desenvolvimento de uma Arquitetura de Dados Moderna e 100% Automatizada (Data Lakehouse) para uma plataforma de recrutamento fictícia.

O principal desafio foi desenhar um fluxo de dados de ponta a ponta implementando a clássica Arquitetura Medallion (Bronze, Silver, Gold), mas mantendo um foco rigoroso em baixo custo e alta eficiência. Para isso, substituí as ferramentas tradicionais de processamento de Big Data por uma abordagem Serverless e Lean na fase de validação (PoC).

Para provar a resiliência do sistema, o pipeline foi sujeito a um teste de stress com a injeção de dezenas de perfis sintéticos propositadamente carregados de anomalias e dados nulos (Missing Values).

🗺️ Arquitetura de Dados


(Substitui o texto acima pelo link da tua imagem gerada)

🛠️ Stack Tecnológico

Fontes Operacionais (OLTP): Neon (PostgreSQL) e Supabase

Orquestração & Ingestão: Azure Data Factory (ADF)

Data Lake: Azure Data Lake Storage Gen2 (ADLS Gen2) / Blob Storage

Processamento / Compute: GitHub Actions (CI/CD como motor Serverless)

Transformação & Limpeza: Python, Pandas, Delta Lake (deltalake)

Consumo & Visualização: Power BI Service

⚙️ O Fluxo de Vida dos Dados (Medallion Architecture)

Todo o pipeline funciona de forma cronometrada durante a madrugada, sem intervenção humana:

Fontes de Dados: Os dados estruturados (candidaturas, logs, auditorias) nascem no Neon e os dados não estruturados (ficheiros, currículos) no Supabase.

Camada Bronze (Ingestão - 01:00 AM): O Azure Data Factory acorda através de um Schedule Trigger, extrai os dados em bruto e guarda-os no formato original no Azure Data Lake, garantindo a imutabilidade do histórico.

Camadas Silver e Gold (Transformação - 01:30 AM): O coração da arquitetura. O GitHub Actions provisiona um runner Ubuntu, liga-se ao Azure, executa o script seeder_cloud.py (Pandas) para limpar/tratar as anomalias, e grava o modelo dimensional analítico (Tabelas Fato e Dimensão) no formato Delta Lake.

Modelagem e Serviço (02:00 AM): O modelo semântico do Power BI Service liga-se diretamente ao Data Lake (Camada Gold) e faz o seu Scheduled Refresh, entregando os dashboards atualizados aos gestores de RH.

💡 A "Magia": GitHub Actions como Motor de ETL

A decisão arquitetural mais interessante deste projeto foi utilizar o GitHub Actions não apenas como CI/CD, mas como Motor de Processamento de Dados.
Em vez de provisionar clusters de Azure Databricks ou Spark (o que geraria custos fixos elevados para o volume de dados atual), o GitHub Actions atua de forma efémera: cria a máquina, corre o código Python pesado, grava os ficheiros Delta no Azure e desliga-se. Um verdadeiro Serverless ETL.

🚀 Escalabilidade: Visão Enterprise (Big Data)

O isolamento das camadas garante que este projeto está pronto a escalar. Se a plataforma de recrutamento precisasse de processar terabytes de dados diários, o upgrade estrutural seria focado apenas nas ferramentas, não na lógica:

Motor de Compute: Substituição do GitHub Actions/Pandas por Azure Databricks com PySpark para processamento massivamente paralelo.

Streaming: Adição de Azure Event Hubs ou Kafka ao lado do ADF para processamento de eventos de candidaturas em tempo real.

Governança: Integração do Microsoft Purview (catálogo e linhagem) e Great Expectations (observabilidade de dados) para bloquear anomalias antes da camada Gold.

📁 Estrutura do Repositório

.github/workflows/etl_pipeline.yml: Pipeline de orquestração do GitHub Actions.

scripts/seeder_cloud.py: Script principal em Python de extração, limpeza (Pandas) e gravação (Delta Lake).

requirements.txt: Dependências do projeto.

