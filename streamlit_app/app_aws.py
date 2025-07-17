# streamlit_app/app_aws.py (Versão Final com Timeout)

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
from streamlit_autorefresh import st_autorefresh

# --- CONFIGURAÇÃO DA PÁGINA E CONEXÃO ---
st.set_page_config(layout="wide", page_title="Dashboard Financeiro")

@st.cache_resource(ttl=300)
def get_db_engine():
    """Conecta-se ao banco de dados usando o st.secrets."""
    try:
        user = st.secrets["database"]["user"]
        password = st.secrets["database"]["password"]
        host = st.secrets["database"]["host"]
        dbname = st.secrets["database"]["dbname"]
        
        # ADIÇÃO DO PARÂMETRO DE TIMEOUT
        conn_str = f"postgresql+psycopg2://{user}:{password}@{host}/{dbname}?sslmode=require&connect_timeout=10"
        
        engine = create_engine(conn_str)
        
        # Teste de conexão
        with engine.connect() as connection:
            pass # A conexão bem-sucedida já é um teste
            
        return engine
    except Exception as e:
        st.error(f"Erro Crítico de Conexão: Não foi possível conectar ao banco. Verifique seus segredos e regras de firewall. Detalhes: {e}")
        st.stop()

engine = get_db_engine()

# --- FUNÇÃO PRINCIPAL DA PÁGINA ---
def rtd_portfolio_page():
    st.title("📊 Carteira de Ações em Tempo Real")
    st_autorefresh(interval=30000, key="rtd_refresher")

    try:
        df_config = pd.read_sql("SELECT * FROM portfolio_config", engine)
        df_quotes = pd.read_sql("SELECT * FROM realtime_quotes", engine)
        
        if df_config.empty:
            st.warning("Carteira vazia. Adicione ativos no seu banco de dados usando o DBeaver para começar.")
            st.stop()
            
        df_portfolio = pd.merge(df_config, df_quotes, on='ticker', how='left').fillna(0)
        
        if 'quantidade' in df_portfolio.columns and 'last_price' in df_portfolio.columns:
            df_portfolio['posicao_rs'] = df_portfolio['quantidade'] * df_portfolio['last_price']
            total_pl = df_portfolio['posicao_rs'].sum()
        else:
            total_pl = 0

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
        st.error(f"Erro ao carregar dados do portfólio do banco de dados: {e}")

# --- Executa a página ---
rtd_portfolio_page()
