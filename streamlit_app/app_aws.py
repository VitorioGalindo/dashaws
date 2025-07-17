import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import boto3
from streamlit_autorefresh import st_autorefresh
import plotly.graph_objects as go
import json
from datetime import datetime

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
        
        # Adiciona o timeout de conexão para maior robustez
        conn_str = f"postgresql+psycopg2://{user}:{password}@{host}/{dbname}?sslmode=require&connect_timeout=10"
        
        engine = create_engine(conn_str)
        with engine.connect():
            pass
        return engine
    except Exception as e:
        st.error(f"Erro Crítico de Conexão: Não foi possível conectar ao banco. Verifique seus segredos e as regras de firewall do RDS. Detalhes: {e}")
        st.stop()

engine = get_db_engine()

# --- 2. FUNÇÕES DAS PÁGINAS ---

# =================================================================
# PÁGINA 1: CARTEIRA EM TEMPO REAL (RTD)
# =================================================================
def rtd_portfolio_page():
    st.title("📊 Carteira de Ações em Tempo Real (RTD)")
    st_autorefresh(interval=60000, key="rtd_refresher")

    # --- Busca de Dados ---
    try:
        df_config = pd.read_sql("SELECT * FROM portfolio_config", engine)
        df_quotes = pd.read_sql("SELECT * FROM realtime_quotes", engine)
        metrics_resp = pd.read_sql("SELECT * FROM portfolio_metrics", engine)
        df_hist = pd.read_sql("SELECT data, cota, ibov FROM portfolio_history ORDER BY data ASC", engine)
    except Exception as e:
        st.error(f"Erro ao carregar dados do banco de dados: {e}")
        return

    # --- Preparação e Cálculos ---
    metrics = {item['metric_key']: item['metric_value'] for item in metrics_resp.to_dict('records')}
    cota_d1 = metrics.get('cota_d1', 1.0)
    qtd_cotas = metrics.get('quantidade_cotas', 1)
    caixa_bruto = metrics.get('caixa_bruto', 0.0)
    outros = metrics.get('outros', 0.0)
    outras_despesas = metrics.get('outras_despesas', 0.0)

    if df_config.empty:
        st.warning("Carteira vazia. Adicione ativos na aba de 'Gerenciar Ativos e Métricas'.")
    
    df_portfolio = pd.merge(df_config, df_quotes, on='ticker', how='left').fillna(0)
    
    # Cálculos da Tabela Principal
    df_portfolio['posicao_rs'] = df_portfolio['quantidade'] * df_portfolio['last_price']
    df_portfolio['var_dia_perc'] = (df_portfolio['last_price'] / df_portfolio['previous_close'] - 1) if 'previous_close' in df_portfolio and (df_portfolio['previous_close'] > 0).all() else 0
    df_portfolio['contrib_rs'] = (df_portfolio['last_price'] - df_portfolio['previous_close']) * df_portfolio['quantidade']

    # Cálculos do Resumo do Portfólio
    caixa_liquido = caixa_bruto + outros + outras_despesas
    total_acoes = df_portfolio['posicao_rs'].sum()
    patrimonio_liquido = total_acoes + caixa_liquido
    
    # Cálculo do PL do dia anterior para a contribuição percentual
    df_portfolio['posicao_rs_d1'] = df_portfolio['quantidade'] * df_portfolio['previous_close']
    pl_d1 = df_portfolio['posicao_rs_d1'].sum() + caixa_liquido

    df_portfolio['posicao_perc'] = df_portfolio['posicao_rs'] / patrimonio_liquido if patrimonio_liquido != 0 else 0
    df_portfolio['contrib_perc'] = df_portfolio['contrib_rs'] / pl_d1 if pl_d1 != 0 else 0
    df_portfolio['diferenca_perc'] = df_portfolio['posicao_perc'] - df_portfolio['posicao_alvo']
    df_portfolio['ajuste_qtd'] = ((df_portfolio['posicao_alvo'] * patrimonio_liquido - df_portfolio['posicao_rs']) / df_portfolio['last_price']).fillna(0).astype(int)

    posicao_comprada_perc = df_portfolio[df_portfolio['posicao_rs'] > 0]['posicao_perc'].sum()
    posicao_vendida_perc = df_portfolio[df_portfolio['posicao_rs'] < 0]['posicao_perc'].sum()
    net_long = posicao_comprada_perc + posicao_vendida_perc
    exposicao_total = posicao_comprada_perc - abs(posicao_vendida_perc) # Exposição bruta

    cota_atual = patrimonio_liquido / qtd_cotas if qtd_cotas > 0 else 0
    variacao_cota_dia = (cota_atual / cota_d1 - 1) if cota_d1 > 0 else 0

    # --- Renderização do Dashboard ---
    main_cols = st.columns([3, 1])
    with main_cols[0]:
        st.subheader("Composição da Carteira")
        st.dataframe(
            df_portfolio.rename(columns={
                'ticker': 'Ativo', 'last_price': 'Cotação', 'var_dia_perc': 'Var. Dia (%)',
                'contrib_perc': 'Contrib. (%)', 'quantidade': 'Quantidade', 'posicao_rs': 'Posição (R$)',
                'posicao_perc': 'Posição (%)', 'posicao_alvo': 'Posição % Alvo',
                'diferenca_perc': 'Diferença', 'ajuste_qtd': 'Ajuste (Qtd.)'
            })[['Ativo', 'Cotação', 'Var. Dia (%)', 'Contrib. (%)', 'Quantidade', 'Posição (R$)', 'Posição (%)', 'Posição % Alvo', 'Diferença', 'Ajuste (Qtd.)']],
            use_container_width=True,
            column_config={
                "Cotação": st.column_config.NumberColumn(format="R$ %.2f"),
                "Var. Dia (%)": st.column_config.NumberColumn(format="%.2f%%"),
                "Contrib. (%)": st.column_config.NumberColumn(format="%.2f%%"),
                "Posição (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
                "Posição (%)": st.column_config.ProgressColumn(format="%.2f%%", min_value=0, max_value=max(1, df_portfolio['posicao_perc'].max())),
                "Posição % Alvo": st.column_config.NumberColumn(format="%.2f%%"),
                "Diferença": st.column_config.NumberColumn(format="%.2f%%"),
            }
        )
        st.markdown(f"**Caixa Líquido:** `{caixa_liquido:,.2f}` | **Posição Caixa:** `{(caixa_liquido / patrimonio_liquido):.2%}`" if patrimonio_liquido else "")

        st.subheader("Contribuição para Variação Diária")
        df_contrib = df_portfolio[df_portfolio['contrib_rs'] != 0].sort_values(by='contrib_rs', ascending=False)
        fig_contrib = go.Figure(go.Bar(
            x=df_contrib['ticker'], y=df_contrib['contrib_rs'],
            marker_color=['#22c55e' if v > 0 else '#ef4444' for v in df_contrib['contrib_rs']]
        ))
        st.plotly_chart(fig_contrib, use_container_width=True)

        st.subheader("Retorno Acumulado: Cota vs. Ibovespa")
        if not df_hist.empty:
            df_hist['cota_return'] = (df_hist['cota'] / df_hist['cota'].iloc[0]) - 1
            df_hist['ibov_return'] = (df_hist['ibov'] / df_hist['ibov'].iloc[0]) - 1
            fig_hist = go.Figure()
            fig_hist.add_trace(go.Scatter(x=df_hist['data'], y=df_hist['cota_return'] * 100, mode='lines', name='Retorno da Cota'))
            fig_hist.add_trace(go.Scatter(x=df_hist['data'], y=df_hist['ibov_return'] * 100, mode='lines', name='Retorno do Ibovespa'))
            fig_hist.update_yaxes(ticksuffix="%")
            st.plotly_chart(fig_hist, use_container_width=True)
        else:
            st.info("Para exibir o gráfico histórico, popule a tabela 'portfolio_history'.")

    with main_cols[1]:
        st.subheader("Resumo do Portfólio")
        st.metric("Patrimônio Líquido:", f"R$ {patrimonio_liquido:,.2f}")
        st.metric("Valor da Cota:", f"R$ {cota_atual:,.4f}")
        st.metric("Variação do Dia:", f"{variacao_cota_dia:.2%}")
        st.markdown("---")
        st.markdown(f"**Posição Comprada:** `{posicao_comprada_perc:.2%}`")
        st.markdown(f"**Posição Vendida:** `{posicao_vendida_perc:.2%}`")
        st.markdown(f"**Net Long:** `{net_long:.2%}`")
        st.markdown(f"**Exposição Total:** `{exposicao_total:.2%}`")
        st.markdown("---")
        st.markdown(f"**Caixa Bruto:** R$ {caixa_bruto:,.2f}")
        st.markdown(f"**Outros:** R$ {outros:,.2f}")
        st.markdown(f"**Outras Despesas:** R$ {outras_despesas:,.2f}")
        st.markdown(f"**Caixa Líquido:** R$ {caixa_liquido:,.2f}")

        with st.expander("Gerenciar Ativos e Métricas"):
            configure_rtd_portfolio(df_config, metrics)

def configure_rtd_portfolio(df_config, metrics):
    """Formulário para editar ativos e métricas."""
    st.info("Para adicionar ou remover ativos, edite a tabela e clique em Salvar.")
    edited_df = st.data_editor(
        df_config[['ticker', 'quantidade', 'posicao_alvo']],
        num_rows="dynamic", key="asset_editor"
    )
    if st.button("Salvar Alterações nos Ativos"):
        # Lógica para salvar as mudanças no banco de dados (deleta e insere)
        pass # Adicionar a lógica de escrita aqui

    st.subheader("Editar Métricas Diárias")
    with st.form("metrics_form"):
        # ... (código do formulário de métricas como na resposta anterior) ...
        st.form_submit_button("Atualizar Métricas")

# =================================================================
# DEMAIS PÁGINAS DO DASHBOARD DE ANÁLISE
# =================================================================
def analysis_command_center_page():
    st.title("🚀 Centro de Comando do Portfólio (Análise)")
    st.info("Página em construção. As funcionalidades do seu antigo dashboard de análise serão portadas para cá, lendo do novo banco de dados RDS, que será populado pelo seu Pipeline ETL.")

def detailed_analysis_page():
    st.title("📊 Análise Detalhada da Empresa")
    st.info("Página em construção.")

def comparator_dashboard():
    st.title("⚖️ Comparador de Empresas")
    st.info("Página em construção.")
    
def etl_status_page():
    st.title("⚙️ Status do Pipeline ETL")
    st.info("Esta página mostrará os logs e o status das execuções do seu pipeline na AWS Lambda.")


# --- NAVEGAÇÃO PRINCIPAL ---
st.sidebar.title("Plataforma Financeira")
PAGES = {
    "Carteira em Tempo Real": rtd_portfolio_page,
    "Centro de Comando (Análise)": analysis_command_center_page,
    "Análise Detalhada": detailed_analysis_page,
    "Comparador de Empresas": comparator_dashboard,
    "Status do Pipeline ETL": etl_status_page,
}
selection = st.sidebar.radio("Navegar para", list(PAGES.keys()))
PAGES[selection]()