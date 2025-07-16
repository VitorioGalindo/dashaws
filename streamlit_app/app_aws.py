import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import boto3
from streamlit_autorefresh import st_autorefresh

# --- CONFIGURAÇÃO DA PÁGINA E CONEXÃO ---
st.set_page_config(layout="wide", page_title="Dashboard Financeiro")

@st.cache_resource(ttl=300) # Cache por 5 minutos
def get_db_engine():
    """Conecta-se ao banco de dados usando segredos do SSM Parameter Store."""
    try:
        # Substitua pela sua região se for diferente
        ssm_client = boto3.client('ssm', region_name='us-east-2')

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

# --- FUNÇÃO PRINCIPAL DA PÁGINA ---
def rtd_portfolio_page():
    st.title("📊 Carteira de Ações em Tempo Real")
    st_autorefresh(interval=30000, key="rtd_refresher") # Atualiza a cada 30 segundos

    try:
        df_config = pd.read_sql("SELECT * FROM portfolio_config", engine)
        df_quotes = pd.read_sql("SELECT * FROM realtime_quotes", engine)

        if df_config.empty:
            st.warning("Sua carteira está vazia. Adicione ativos no seu banco de dados usando o DBeaver para começar.")
            return

        df_portfolio = pd.merge(df_config, df_quotes, on='ticker', how='left').fillna(0)
        df_portfolio['posicao_rs'] = df_portfolio['quantidade'] * df_portfolio['last_price']
        total_pl = df_portfolio['posicao_rs'].sum()

        st.header("Resumo da Carteira")
        st.metric("Patrimônio Total em Ações", f"R$ {total_pl:,.2f}")

        st.header("Composição")
        st.dataframe(
            df_portfolio[['ticker', 'quantidade', 'last_price', 'posicao_rs', 'updated_at']],
            use_container_width=True,
            column_config={
                "ticker": "Ativo",
                "quantidade": "Quantidade",
                "last_price": st.column_config.NumberColumn("Preço Atual (R$)", format="%.2f"),
                "posicao_rs": st.column_config.NumberColumn("Posição (R$)", format="R$ %.2f"),
                "updated_at": st.column_config.DatetimeColumn("Última Atualização", format="HH:mm:ss")
            }
        )
    except Exception as e:
        st.error(f"Erro ao carregar dados do portfólio: {e}")

# --- Executa a página ---
rtd_portfolio_page()