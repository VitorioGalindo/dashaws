# streamlit_app/app_aws.py (Versão com Debug)
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import boto3
from streamlit_autorefresh import st_autorefresh

# --- CONFIGURAÇÃO DA PÁGINA E CONEXÃO ---
st.set_page_config(layout="wide", page_title="Dashboard Financeiro Unificado")

# Escreve a primeira mensagem assim que o script começa
st.write("1. Script iniciado. Tentando obter a conexão com o banco de dados...")

@st.cache_resource(ttl=300)
def get_db_engine():
    """Conecta-se ao banco de dados usando segredos do SSM Parameter Store."""
    try:
        st.write("2. Dentro da função get_db_engine: Tentando criar o cliente SSM...")
        ssm_client = boto3.client('ssm', region_name='us-east-2')
        st.write("3. Cliente SSM criado. Tentando buscar os segredos...")

        def get_secret(param_name):
            response = ssm_client.get_parameter(Name=param_name, WithDecryption=True)
            return response['Parameter']['Value']

        user = get_secret("/finance-app/db/user")
        password = get_secret("/finance-app/db/password")
        host = get_secret("/finance-app/db/host")
        dbname = "postgres"
        st.write("4. Segredos do banco de dados lidos com sucesso.")
        
        conn_str = f"postgresql+psycopg2://{user}:{password}@{host}/{dbname}?sslmode=require"
        st.write("5. String de conexão criada. Tentando criar a engine do banco...")
        
        engine = create_engine(conn_str)
        
        # Testa a conexão
        with engine.connect() as connection:
            st.write("6. Conexão com o banco de dados TESTADA e bem-sucedida!")
            
        return engine
    except Exception as e:
        st.error(f"ERRO CRÍTICO NA CONEXÃO: {e}")
        st.stop()

# Chama a função de conexão
engine = get_db_engine()

st.write("7. Engine do banco de dados obtida. O script continuará a ser executado.")

# --- FUNÇÃO PRINCIPAL DA PÁGINA ---
def rtd_portfolio_page():
    st.title("📊 Carteira de Ações em Tempo Real")
    st_autorefresh(interval=30000, key="rtd_refresher")
    # ... (o resto da sua lógica de página pode continuar aqui) ...
    st.success("A página foi renderizada completamente!")

# --- Executa a página ---
rtd_portfolio_page()