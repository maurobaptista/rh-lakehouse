import os
import io
import json
import random
from faker import Faker
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import psycopg2
from supabase import create_client, Client
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv
import pandas as pd
from deltalake import DeltaTable, write_deltalake

# Carregar variáveis de ambiente do .env
load_dotenv()

fake = Faker(['pt_PT'])

# Configurações das credenciais
NEON_CONN_STRING = os.getenv("NEON_DB_URL")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET")
AZURE_CONN_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")

# Inicializar clientes
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
azure_blob_service = BlobServiceClient.from_connection_string(AZURE_CONN_STRING)

# =====================================================================
# 1. Preparar a tabela no Neon PostgreSQL
# =====================================================================
conn = psycopg2.connect(NEON_CONN_STRING)
cur = conn.cursor()

cur.execute("""
    CREATE TABLE IF NOT EXISTS candidatos (
        id_candidato VARCHAR(50) PRIMARY KEY,
        nome VARCHAR(100),
        email VARCHAR(100) UNIQUE,
        telefone VARCHAR(20),
        cargo_atual VARCHAR(100),
        salario_pretendido_kz NUMERIC,
        cidade VARCHAR(50),
        caminho_cv_supabase VARCHAR(255),
        caminho_avatar_azure VARCHAR(255),
        data_registo TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    ALTER TABLE candidatos 
    ADD COLUMN IF NOT EXISTS bi VARCHAR(20) UNIQUE,
    ADD COLUMN IF NOT EXISTS nivel_academico VARCHAR(50),
    ADD COLUMN IF NOT EXISTS data_nascimento DATE,
    ADD COLUMN IF NOT EXISTS ja_trabalhou BOOLEAN,
    ADD COLUMN IF NOT EXISTS formacao_academica VARCHAR(100),
    ADD COLUMN IF NOT EXISTS genero VARCHAR(20);
""")
conn.commit()

# =====================================================================
# 2. Configurações de Geração e Injeção
# =====================================================================
NUM_CANDIDATOS = 100
niveis = ['Ensino Médio', 'Licenciatura', 'Mestrado', 'Doutoramento']
formacoes = ['Engenharia Informática', 'Gestão de Empresas', 'Direito', 'Contabilidade', 'Recursos Humanos', 'Economia', 'Medicina', 'Nenhuma']
generos = ['Masculino', 'Feminino']
logs_acesso = []

print(f"A iniciar o carregamento de {NUM_CANDIDATOS} perfis (com dados nulos aleatórios) para Neon, Supabase e Azure...")

for i in range(1, NUM_CANDIDATOS + 1):
    cand_id = fake.uuid4()[:8]
    nome = fake.name()
    email = fake.unique.email()
    telefone = f"+244 9{random.randint(10000000, 99999999)}"
    cargo = fake.job()
    salario = round(random.uniform(300000, 1800000), 2)
    
    # 20% de probabilidade de não preencher a cidade
    cidade = random.choice(["Luanda", "Benguela", "Huambo", "Lubango", "Cabinda"]) if random.random() > 0.2 else None
    
    bi = str(fake.random_number(digits=14, fix_len=True)) + "LA" + str(fake.random_number(digits=3, fix_len=True))
    nivel_academico = random.choice(niveis)
    formacao_academica = random.choice(formacoes) if nivel_academico != 'Ensino Médio' else 'Ensino Geral'

    # Campos com probabilidade de falha no preenchimento (NULLs)
    genero = random.choice(generos) if random.random() > 0.15 else None # 15% sem género
    data_nascimento = fake.date_of_birth(minimum_age=18, maximum_age=60) if random.random() > 0.1 else None # 10% sem data
    ja_trabalhou = random.choice([True, False]) if random.random() > 0.25 else None # 25% sem resposta

    # 1. Gerar PDF (Lidar com cidade Nula para não quebrar o PDF)
    buffer_pdf = io.BytesIO()
    c = canvas.Canvas(buffer_pdf, pagesize=letter)
    c.drawString(100, 750, f"CURRÍCULO PROFISSIONAL: {nome}")
    c.drawString(100, 720, f"Cargo: {cargo}")
    
    cidade_display = cidade if cidade else "Não especificada"
    c.drawString(100, 690, f"Localidade: {cidade_display}, Angola")
    c.drawString(100, 660, f"Nível Académico: {nivel_academico}")
    c.drawString(100, 640, f"Formação Académica: {formacao_academica}")
    c.save()
    pdf_bytes = buffer_pdf.getvalue()
    
    caminho_pdf_supabase = f"cvs/cv_{cand_id}.pdf"
    supabase.storage.from_(SUPABASE_BUCKET).upload(
        path=caminho_pdf_supabase,
        file=pdf_bytes,
        file_options={"content-type": "application/pdf"}
    )

    # 2. Enviar metadados de Média para o Azure Blob
    avatar_blob_name = f"avatars/{cand_id}_avatar.txt"
    media_client = azure_blob_service.get_blob_client(container="uploadthing-media", blob=avatar_blob_name)
    media_client.upload_blob(f"IMG_ID={cand_id} | STATUS=UPLOADED | SIZE=1024KB", overwrite=True)

    # 3. Gerar registos de Log de Segurança
    for _ in range(random.randint(2, 5)):
        logs_acesso.append({
            "log_id": fake.uuid4(),
            "id_candidato": cand_id,
            "ip_origem": fake.ipv4(),
            "evento": random.choice(["LOGIN_SUCCESS", "VIEW_PROFILE", "SUBMIT_APPLICATION", "CHAMADA_ENTREVISTA"]),
            "timestamp": fake.date_time_this_year().isoformat()
        })

    # 4. Inserir na base central (Neon PostgreSQL) - O driver converte 'None' para 'NULL' no SQL
    cur.execute("""
        INSERT INTO candidatos 
        (id_candidato, nome, email, telefone, cargo_atual, salario_pretendido_kz, cidade, caminho_cv_supabase, caminho_avatar_azure, bi, nivel_academico, data_nascimento, ja_trabalhou, formacao_academica, genero)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (email) DO NOTHING;
    """, (
        cand_id, nome, email, telefone, cargo, salario, cidade,
        f"{SUPABASE_BUCKET}/{caminho_pdf_supabase}",
        f"uploadthing-media/{avatar_blob_name}",
        bi, nivel_academico, data_nascimento, ja_trabalhou, formacao_academica, genero
    ))

conn.commit()

# 5. Enviar os Logs de Auditoria consolidados
logs_client = azure_blob_service.get_blob_client(container="microsoft-audit-logs", blob="security_audit_logs.json")
logs_client.upload_blob(json.dumps(logs_acesso, indent=4), overwrite=True)

cur.close()
conn.close()

print(f"✅ Concluído com sucesso! {NUM_CANDIDATOS} candidatos injetados (alguns com dados em falta).")

# =====================================================================
# CAMADA SILVER: Leitura da Bronze, Limpeza e Gravação em Delta Lake
# =====================================================================
def processar_camada_silver():
    print("\n--- A iniciar processamento da Camada Silver ---")

    # 1. Descarregar os dados brutos da Bronze usando o cliente já inicializado
    container_bronze = "bronze"
    # Nome exato do ficheiro no Azure com o caminho da pasta
    nome_blob_bronze = "neon_candidatos/\"public\".\"candidatos\".txt"

    try:
        blob_client = azure_blob_service.get_blob_client(
            container=container_bronze, blob=nome_blob_bronze
        )
        dados_bytes = blob_client.download_blob().readall()
        df = pd.read_csv(io.BytesIO(dados_bytes))
        print(f"Sucesso: {len(df)} registos lidos da pasta Bronze.")
    except Exception as e:
        print(f"Erro ao ler da Bronze ({nome_blob_bronze}): {e}")
        print("A tentar ler diretamente da base Neon como fallback...")
        
        # Reabrir uma nova conexão apenas para este fallback para evitar o erro "connection closed"
        import psycopg2
        import os
        conn_fallback = psycopg2.connect(os.getenv("NEON_DB_URL"))
        df = pd.read_sql("SELECT * FROM candidatos", conn_fallback)
        conn_fallback.close()
        print(f"Sucesso: {len(df)} registos lidos diretamente do Neon PostgreSQL.")

    # 2. Regras de Limpeza e Transformação (Silver)
    # Remoção de duplicados com base no ID
    if "id" in df.columns:
        df = df.drop_duplicates(subset=["id"], keep="last")

    # Limpeza de campos de texto
    if "email" in df.columns:
        df["email"] = df["email"].astype(str).str.strip().str.lower()
    if "nome" in df.columns:
        df["nome"] = df["nome"].astype(str).str.strip()

    # Conversão de tipos de data
    if "created_at" in df.columns:
        df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")

    # Metadados de auditoria da camada Silver
    df["silver_processed_at"] = pd.Timestamp.now('UTC')

    # 3. Gravar na Camada Silver em formato DELTA LAKE
    print("A preparar credenciais para o Delta Lake...")
    
    # Extrair o AccountName e AccountKey diretamente da Connection String
    conn_dict = dict(item.split("=", 1) for item in AZURE_CONN_STRING.split(";") if "=" in item)
    conta_azure = conn_dict.get("AccountName", "adlsanalyticsmauro01")
    chave_azure = conn_dict.get("AccountKey")

    # Caminho oficial do Azure Data Lake (abfss)
    caminho_silver = f"abfss://silver@{conta_azure}.dfs.core.windows.net/candidatos_delta"
    
    # Passar as credenciais separadas (resolve o erro "Account must be specified")
    storage_options = {
        "azure_storage_account_name": conta_azure,
        "azure_storage_access_key": chave_azure
    }

    print("A gravar tabela Delta no contentor Silver...")
    write_deltalake(
        table_or_uri=caminho_silver,
        data=df,
        mode="overwrite",
        storage_options=storage_options,
    )

    print("Camada Silver Delta concluída com sucesso!")

# =====================================================================
# EXECUTAR A FUNÇÃO DA CAMADA SILVER (A linha que faltava!)
# =====================================================================
processar_camada_silver()

# =====================================================================
# CAMADA GOLD: Construção do Data Warehouse Relacional
# =====================================================================
def processar_camada_gold():
    print("\n--- A iniciar construção do Data Warehouse (Camada Gold) ---")

    # 1. Preparar credenciais
    conn_dict = dict(item.split("=", 1) for item in AZURE_CONN_STRING.split(";") if "=" in item)
    conta_azure = conn_dict.get("AccountName", "adlsanalyticsmauro01")
    chave_azure = conn_dict.get("AccountKey")

    storage_options = {
        "azure_storage_account_name": conta_azure,
        "azure_storage_access_key": chave_azure
    }

    # 2. Criar a DIMENSÃO (dim_candidatos) - Lê da Silver
    print("A processar Tabela Dimensão: dim_candidatos...")
    caminho_silver = f"abfss://silver@{conta_azure}.dfs.core.windows.net/candidatos_delta"
    dt_silver = DeltaTable(caminho_silver, storage_options=storage_options)
    dim_candidatos = dt_silver.to_pandas()
    dim_candidatos['dw_atualizado_em'] = pd.Timestamp.now('UTC')

    # 3. Criar os FACTOS (fact_logs) - Lê o JSON da Bronze
    print("A processar Tabela de Factos: fact_logs...")
    try:
        logs_client = azure_blob_service.get_blob_client(
            container="microsoft-audit-logs", blob="security_audit_logs.json"
        )
        logs_bytes = logs_client.download_blob().readall()
        fact_logs = pd.read_json(io.BytesIO(logs_bytes))
        fact_logs['dw_atualizado_em'] = pd.Timestamp.now('UTC')
    except Exception as e:
        print(f"Erro ao ler os logs JSON: {e}")
        fact_logs = pd.DataFrame()

    # 4. Gravar o Modelo Relacional na Camada Gold (Delta Lake)
    print("A gravar as tabelas do Data Warehouse no contentor Gold...")
    
    # Gravar a Dimensão
    caminho_gold_dim = f"abfss://gold@{conta_azure}.dfs.core.windows.net/dim_candidatos_delta"
    write_deltalake(
        table_or_uri=caminho_gold_dim,
        data=dim_candidatos,
        mode="overwrite",
        storage_options=storage_options,
    )
    
    # Gravar os Factos
    if not fact_logs.empty:
        caminho_gold_fact = f"abfss://gold@{conta_azure}.dfs.core.windows.net/fact_logs_delta"
        write_deltalake(
            table_or_uri=caminho_gold_fact,
            data=fact_logs,
            mode="overwrite",
            storage_options=storage_options,
        )

    print("Data Warehouse concluído com sucesso!")

# Executar a função do DW
processar_camada_gold()