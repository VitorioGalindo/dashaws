# streamlit_app/app_aws.py (Versão Final e Unificada)

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import boto3
from streamlit_autorefresh import st_autorefresh
import json
from datetime import datetime, timedelta

# --- 1. CONFIGURAÇÃO DA PÁGINA E CONEXÃO COM O BANCO ---

st.set_page_config(layout="wide", page_title="Dashboard Financeiro Unificado")

@st.cache_resource(ttl=300) # Cache por 5 minutos
def get_db_engine():
    """Conecta-se ao banco de dados usando o st.secrets."""
    try:
        user = st.secrets["database"]["user"]
        password = st.secrets["database"]["password"]
        host = st.secrets["database"]["host"]
        dbname = st.secrets["database"]["dbname"]
        conn_str = f"postgresql+psycopg2://{user}:{password}@{host}/{dbname}?sslmode=require&connect_timeout=10"
        engine = create_engine(conn_str)
        with engine.connect():
            pass
        return engine
    except Exception as e:
        st.error(f"Erro Crítico de Conexão: Não foi possível conectar ao banco. Detalhes: {e}")
        st.stop()

engine = get_db_engine()

# --- 2. FUNÇÕES DAS PÁGINAS ---

# =================================================================
# PÁGINA 1: CARTEIRA EM TEMPO REAL (RTD)
# =================================================================
def rtd_portfolio_page():
    st.title("📊 Carteira em Tempo Real (RTD)")
    st_autorefresh(interval=30000, key="rtd_refresher")
    
    tab_dashboard, tab_config = st.tabs(["Dashboard", "Gerenciar Ativos e Métricas"])

    with tab_dashboard:
        display_rtd_dashboard()
    with tab_config:
        configure_rtd_portfolio()

def display_rtd_dashboard():
    """Exibe o dashboard da carteira em tempo real."""
    try:
        df_config = pd.read_sql("SELECT * FROM portfolio_config", engine)
        df_quotes = pd.read_sql("SELECT * FROM realtime_quotes", engine)
        metrics_resp = pd.read_sql("SELECT * FROM portfolio_metrics", engine)
        
        caixa_bruto = metrics_resp[metrics_resp['metric_key'] == 'caixa_bruto']['metric_value'].iloc[0] if 'caixa_bruto' in metrics_resp['metric_key'].values else 0
        cota_d1 = metrics_resp[metrics_resp['metric_key'] == 'cota_d1']['metric_value'].iloc[0] if 'cota_d1' in metrics_resp['metric_key'].values else 1
        qtd_cotas = metrics_resp[metrics_resp['metric_key'] == 'qtd_cotas']['metric_value'].iloc[0] if 'qtd_cotas' in metrics_resp['metric_key'].values else 1

        if df_config.empty:
            st.warning("Carteira vazia. Adicione ativos na aba de 'Gerenciar Ativos'.")
            return
            
        df_portfolio = pd.merge(df_config, df_quotes, on='ticker', how='left').fillna(0)
        
        # Cálculos
        df_portfolio['posicao_rs'] = df_portfolio['quantidade'] * df_portfolio['last_price']
        df_portfolio['variacao_dia_perc'] = (df_portfolio['last_price'] / df_portfolio['previous_close'] - 1) if 'previous_close' in df_portfolio and df_portfolio['previous_close'].all() > 0 else 0
        
        total_acoes = df_portfolio['posicao_rs'].sum()
        patrimonio_liquido = total_acoes + caixa_bruto
        cota_atual = patrimonio_liquido / qtd_cotas if qtd_cotas > 0 else 0
        variacao_cota_dia = (cota_atual / cota_d1 - 1) if cota_d1 > 0 else 0
        
        st.header("Resumo da Carteira")
        cols = st.columns(4)
        cols[0].metric("Patrimônio em Ações", f"R$ {total_acoes:,.2f}")
        cols[1].metric("Caixa", f"R$ {caixa_bruto:,.2f}")
        cols[2].metric("Patrimônio Total", f"R$ {patrimonio_liquido:,.2f}")
        cols[3].metric("Variação da Cota (Dia)", f"{variacao_cota_dia:.2%}", delta_color="inverse")
        
        st.header("Composição da Carteira")
        st.dataframe(
            df_portfolio[['ticker', 'quantidade', 'last_price', 'posicao_rs', 'variacao_dia_perc', 'updated_at']],
            use_container_width=True
        )
    except Exception as e:
        st.error(f"Erro ao montar o dashboard: {e}")

def configure_rtd_portfolio():
    """Página para editar a configuração da carteira RTD."""
    st.header("Gerenciar Ativos e Métricas")

    st.subheader("Ativos da Carteira")
    try:
        df_config = pd.read_sql("SELECT id, ticker, quantidade, posicao_alvo FROM portfolio_config", engine, index_col='id')
    except:
        df_config = pd.DataFrame(columns=['ticker', 'quantidade', 'posicao_alvo'])

    with st.form("asset_form"):
        edited_df = st.data_editor(df_config, num_rows="dynamic", use_container_width=True)
        save_assets_button = st.form_submit_button("Salvar Alterações nos Ativos")
        
        if save_assets_button:
            try:
                # Usar um método de upsert mais seguro
                with engine.connect() as conn:
                    conn.execute(text("TRUNCATE TABLE portfolio_config RESTART IDENTITY;"))
                    edited_df.to_sql('portfolio_config', conn, if_exists='append', index=True, index_label='id')
                    conn.commit()
                st.success("Configuração de ativos salva com sucesso!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar ativos: {e}")
    
    st.subheader("Métricas Gerais")
    try:
        metrics_resp = pd.read_sql("SELECT * FROM portfolio_metrics", engine)
        metrics_data = {item['metric_key']: item['metric_value'] for item in metrics_resp.to_dict('records')}
    except:
        metrics_data = {}

    with st.form("metrics_form"):
        cota_d1 = st.number_input("Cota do Dia Anterior (D-1)", value=float(metrics_data.get('cota_d1', 1.0)), format="%.4f")
        qtd_cotas = st.number_input("Quantidade de Cotas", value=int(metrics_data.get('qtd_cotas', 1)), step=1)
        caixa = st.number_input("Caixa Bruto", value=float(metrics_data.get('caixa_bruto', 0.0)), format="%.2f")
        save_metrics_button = st.form_submit_button("Salvar Métricas")
        
        if save_metrics_button:
            try:
                metrics_to_upsert = [
                    {"metric_key": "cota_d1", "metric_value": cota_d1},
                    {"metric_key": "qtd_cotas", "metric_value": qtd_cotas},
                    {"metric_key": "caixa_bruto", "metric_value": caixa}
                ]
                with engine.connect() as conn:
                    for item in metrics_to_upsert:
                        conn.execute(text("""
                            INSERT INTO portfolio_metrics (metric_key, metric_value)
                            VALUES (:metric_key, :metric_value)
                            ON CONFLICT (metric_key) DO UPDATE
                            SET metric_value = EXCLUDED.metric_value;
                        """), item)
                    conn.commit()
                st.success("Métricas salvas com sucesso!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar métricas: {e}")

# =================================================================
# PÁGINA 2: CENTRO DE COMANDO (ANÁLISE)
# =================================================================
def analysis_command_center_page():
    st.title("🚀 Centro de Comando do Portfólio (Análise)")
    st.markdown("Esta página será a recriação da sua antiga página de análise de portfólio.")
    st.info("Página em construção. A lógica do seu antigo dashboard de análise será portada para cá, lendo do novo banco de dados RDS.")
    # A lógica da sua antiga página `portfolio_dashboard` do app V7.5 virá aqui.
    # Terá que ser adaptada para ler os dados das tabelas `market_info`, `cvm_reports`, etc.,
    # que serão populadas pelo nosso pipeline ETL na AWS Lambda.

# =================================================================
# PÁGINA 3: ANÁLISE DETALHADA
# =================================================================
def detailed_analysis_page():
    st.title("📊 Análise Detalhada da Empresa")
    st.info("Página em construção. A lógica da sua antiga página de análise detalhada virá aqui.")
    # A lógica completa da sua antiga página `detailed_analysis` virá aqui.
    # As funções como `calculate_valuation_metrics` e as leituras de
    # demonstrativos financeiros lerão os dados do RDS.
    
# Adicione aqui as outras funções de página do seu app V7.5 (Comparador, Análise Setorial, etc.)


# --- NAVEGAÇÃO PRINCIPAL ---
st.sidebar.title("Plataforma Financeira")
PAGES = {
    "Carteira em Tempo Real": rtd_portfolio_page,
    "Centro de Comando (Análise)": analysis_command_center_page,
    "Análise Detalhada": detailed_analysis_page,
    # Adicione os nomes das outras páginas aqui
}
selection = st.sidebar.radio("Ir para", list(PAGES.keys()))
PAGES[selection]()