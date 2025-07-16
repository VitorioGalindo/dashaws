import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import boto3
from streamlit_autorefresh import st_autorefresh

# --- CONFIGURAÇÃO DA PÁGINA E CONEXÃO ---
st.set_page_config(layout="wide", page_title="Dashboard Financeiro Unificado")

@st.cache_resource(ttl=600)
def get_db_engine():
    """Conecta-se ao banco de dados usando segredos do SSM Parameter Store."""
    try:
        ssm_client = boto3.client('ssm', region_name='sa-east-1')
        def get_secret(param_name):
            response = ssm_client.get_parameter(Name=param_name, WithDecryption=True)
            return response['Parameter']['Value']

        user = get_secret("/finance-app/db/user")
        password = get_secret("/finance-app/db/password")
        host = get_secret("/finance-app/db/host")
        dbname = "postgres"
        
        conn_str = f"postgresql+psycopg2://{user}:{password}@{host}/{dbname}?sslmode=require"
        return create_engine(conn_str)
    except Exception as e:
        st.error(f"Erro Crítico de Conexão: Não foi possível conectar ao banco ou ler os segredos. Verifique as permissões da IAM Role do App Runner. Detalhes: {e}")
        st.stop()

engine = get_db_engine()

# --- FUNÇÕES DAS PÁGINAS ---
def rtd_portfolio_page():
    st.title("📊 Carteira em Tempo Real (RTD)")
    st_autorefresh(interval=20000, key="rtd_refresher")
    
    tab_dashboard, tab_config = st.tabs(["Dashboard", "Configuração da Carteira"])

    with tab_dashboard:
        display_rtd_dashboard()
    with tab_config:
        configure_portfolio()

def display_rtd_dashboard():
    try:
        df_config = pd.read_sql("SELECT * FROM portfolio_config", engine)
        df_quotes = pd.read_sql("SELECT * FROM realtime_quotes", engine)
        
        if df_config.empty:
            st.warning("Carteira vazia. Adicione ativos na aba de 'Configuração'.")
            return
            
        df_portfolio = pd.merge(df_config, df_quotes, on='ticker', how='left').fillna(0)
        df_portfolio['posicao_rs'] = df_portfolio['quantidade'] * df_portfolio['last_price']
        total_pl = df_portfolio['posicao_rs'].sum()

        st.header("Resumo da Carteira")
        st.metric("Patrimônio em Ações", f"R$ {total_pl:,.2f}")
        st.dataframe(df_portfolio[['ticker', 'quantidade', 'last_price', 'posicao_rs']], use_container_width=True)
    except Exception as e:
        st.error(f"Erro ao montar o dashboard: {e}")

def configure_portfolio():
    st.header("Gerenciar Ativos da Carteira")
    try:
        df_config = pd.read_sql("SELECT id, ticker, quantidade FROM portfolio_config", engine, index_col='id')
        edited_df = st.data_editor(df_config, num_rows="dynamic", use_container_width=True)
        if st.button("Salvar Alterações"):
            edited_df.to_sql('portfolio_config', engine, if_exists='replace', index=True, index_label='id')
            st.success("Configuração salva com sucesso!")
            st.rerun()
    except Exception as e:
        st.error(f"Erro ao carregar/salvar configuração: {e}")

# --- NAVEGAÇÃO PRINCIPAL ---
st.sidebar.title("Navegação")
selection = st.sidebar.radio("Ir para", ["Carteira RTD"]) # Adicione outras páginas aqui
if selection == "Carteira RTD":
    rtd_portfolio_page()