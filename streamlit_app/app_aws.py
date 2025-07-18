# streamlit_app/app_aws.py (Versão Final Unificada e Organizada)

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import boto3
from streamlit_autorefresh import st_autorefresh
import plotly.graph_objects as go
import yfinance as yf

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(layout="wide", page_title="Plataforma Financeira")

# --- 2. FUNÇÕES GLOBAIS (Conexão e Estilo) ---

@st.cache_resource(ttl=300)
def get_db_engine():
    """Conecta-se ao banco de dados usando o st.secrets."""
    try:
        user = st.secrets["database"]["user"]
        password = st.secrets["database"]["password"]
        host = st.secrets["database"]["host"]
        dbname = st.secrets["database"]["dbname"]
        conn_str = f"postgresql+psycopg2://{user}:{password}@{host}/{dbname}?sslmode=require&connect_timeout=10"
        engine = create_engine(conn_str)
        with engine.connect(): pass
        return engine
    except Exception as e:
        st.error(f"Erro Crítico de Conexão: {e}")
        st.stop()

def style_dataframe(df):
    """Aplica formatação e coloração ao DataFrame da carteira."""
    def color_negative_red(val):
        if isinstance(val, (int, float)):
            color = '#ef4444' if val < 0 else '#22c55e'
            return f'color: {color}'
        return ''

    format_dict = {
        'Cotação': 'R$ {:,.2f}',
        'Var. Dia (%)': '{:,.2f}%',
        'Contrib. (%)': '{:,.2f}%',
        'Quantidade': '{:,.0f}',
        'Posição (R$)': 'R$ {:,.2f}',
        'Posição (%)': '{:,.2f}%',
        'Posição % Alvo': '{:,.2f}%',
        'Diferença': '{:,.2f}%',
        'Ajuste (Qtd.)': '{:,.0f}'
    }
    
    styled_df = df.style.format(format_dict, na_rep="").map(
        color_negative_red,
        subset=['Var. Dia (%)', 'Contrib. (%)', 'Diferença', 'Ajuste (Qtd.)']
    )
    return styled_df

def placeholder_page(title):
    """Função genérica para páginas em construção."""
    st.title(title)
    st.info("Página em construção.")

# --- 3. FUNÇÕES DE CADA PÁGINA DO DASHBOARD ---

# =================================================================
# PÁGINA 1: CARTEIRA EM TEMPO REAL (RTD)
# =================================================================
def rtd_portfolio_page():
    st.title("📊 Carteira de Ações em Tempo Real (RTD)")
    st_autorefresh(interval=60000, key="rtd_refresher")

    # (O código completo e funcional da página RTD vai aqui)
    # ... (código detalhado abaixo)
    try:
        df_config = pd.read_sql("SELECT * FROM portfolio_config", engine, index_col='id')
        df_quotes = pd.read_sql("SELECT * FROM realtime_quotes", engine)
        metrics_resp = pd.read_sql("SELECT * FROM portfolio_metrics", engine)
        df_hist = pd.read_sql("SELECT data, cota, ibov FROM portfolio_history ORDER BY data ASC", engine)
    except Exception as e:
        st.error(f"Erro ao carregar dados do banco: {e}")
        return

    metrics = {item['metric_key']: item['metric_value'] for item in metrics_resp.to_dict('records')}
    cota_d1 = metrics.get('cota_d1', 1.0)
    qtd_cotas = metrics.get('quantidade_cotas', 1)
    caixa_bruto = metrics.get('caixa_bruto', 0.0)
    outros = metrics.get('outros', 0.0)
    outras_despesas = metrics.get('outras_despesas', 0.0)

    if not df_config.empty:
        df_config.reset_index(inplace=True)
    
    df_portfolio = pd.merge(df_config, df_quotes, on='ticker', how='left').fillna(0)
    
    caixa_liquido = caixa_bruto + outros + outras_despesas
    df_portfolio['posicao_rs'] = df_portfolio['quantidade'] * df_portfolio['last_price']
    total_acoes = df_portfolio['posicao_rs'].sum()
    patrimonio_liquido = total_acoes + caixa_liquido
    
    df_portfolio['posicao_rs_d1'] = df_portfolio['quantidade'] * df_portfolio['previous_close']
    pl_d1 = df_portfolio['posicao_rs_d1'].sum() + caixa_liquido if not df_portfolio.empty else caixa_liquido
    
    df_portfolio['var_dia_perc'] = (df_portfolio['last_price'] / df_portfolio['previous_close'] - 1) * 100 if 'previous_close' in df_portfolio and (df_portfolio['previous_close'] > 0).all() else 0
    df_portfolio['contrib_rs'] = (df_portfolio['last_price'] - df_portfolio['previous_close']) * df_portfolio['quantidade']
    df_portfolio['posicao_perc'] = (df_portfolio['posicao_rs'] / patrimonio_liquido) * 100 if patrimonio_liquido != 0 else 0
    df_portfolio['contrib_perc'] = (df_portfolio['contrib_rs'] / pl_d1) * 100 if pl_d1 != 0 else 0
    df_portfolio['posicao_alvo_perc'] = df_portfolio['posicao_alvo'] * 100
    df_portfolio['diferenca_perc'] = df_portfolio['posicao_perc'] - df_portfolio['posicao_alvo_perc']
    df_portfolio['ajuste_qtd'] = ((df_portfolio['posicao_alvo'] * patrimonio_liquido - df_portfolio['posicao_rs']) / df_portfolio['last_price']).fillna(0)

    posicao_comprada_perc = (df_portfolio[df_portfolio['posicao_rs'] > 0]['posicao_rs'].sum() / patrimonio_liquido) if patrimonio_liquido != 0 else 0
    posicao_vendida_perc = (df_portfolio[df_portfolio['posicao_rs'] < 0]['posicao_rs'].sum() / patrimonio_liquido) if patrimonio_liquido != 0 else 0
    net_long = posicao_comprada_perc + posicao_vendida_perc
    exposicao_total = posicao_comprada_perc - posicao_vendida_perc
    cota_atual = patrimonio_liquido / qtd_cotas if qtd_cotas > 0 else 0
    variacao_cota_dia = (cota_atual / cota_d1 - 1) if cota_d1 > 0 else 0

    main_cols = st.columns([3, 1])
    with main_cols[0]:
        st.subheader("Composição da Carteira")
        if not df_portfolio.empty:
            df_display = df_portfolio.rename(columns={'ticker': 'Ativo', 'last_price': 'Cotação', 'var_dia_perc': 'Var. Dia (%)', 'contrib_perc': 'Contrib. (%)', 'quantidade': 'Quantidade', 'posicao_rs': 'Posição (R$)', 'posicao_perc': 'Posição (%)', 'posicao_alvo_perc': 'Posição % Alvo', 'diferenca_perc': 'Diferença', 'ajuste_qtd': 'Ajuste (Qtd.)'})
            st.dataframe(style_dataframe(df_display[['Ativo', 'Cotação', 'Var. Dia (%)', 'Contrib. (%)', 'Quantidade', 'Posição (R$)', 'Posição (%)', 'Posição % Alvo', 'Diferença', 'Ajuste (Qtd.)']]), use_container_width=True, hide_index=True)
        st.markdown(f"**Caixa Líquido:** `{caixa_liquido:,.2f}`")
        
        st.subheader("Gráficos")
        chart_cols = st.columns(2)
        with chart_cols[0]:
            st.markdown("###### Contribuição para Variação Diária")
            df_contrib = df_portfolio[df_portfolio['contrib_rs'] != 0].sort_values(by='contrib_rs', ascending=False)
            if not df_contrib.empty:
                fig_contrib = go.Figure(go.Bar(x=df_contrib['ticker'], y=df_contrib['contrib_rs'], marker_color=['#22c55e' if v > 0 else '#ef4444' for v in df_contrib['contrib_rs']]))
                st.plotly_chart(fig_contrib, use_container_width=True)
        with chart_cols[1]:
            st.markdown("###### Retorno Acumulado: Cota vs. Ibovespa")
            if not df_hist.empty:
                df_hist['data'] = pd.to_datetime(df_hist['data'])
                df_hist = df_hist.sort_values(by='data')
                df_hist['cota_return'] = (df_hist['cota'] / df_hist['cota'].iloc[0] - 1)
                df_hist['ibov_return'] = (df_hist['ibov'] / df_hist['ibov'].iloc[0] - 1)
                fig_hist = go.Figure()
                fig_hist.add_trace(go.Scatter(x=df_hist['data'], y=df_hist['cota_return'], mode='lines', name='Retorno da Cota'))
                fig_hist.add_trace(go.Scatter(x=df_hist['data'], y=df_hist['ibov_return'], mode='lines', name='Retorno do Ibovespa'))
                fig_hist.update_layout(yaxis_tickformat=".2%")
                st.plotly_chart(fig_hist, use_container_width=True)

    with main_cols[1]:
        st.subheader("Resumo do Portfólio")
        st.metric("Patrimônio Líquido:", f"R$ {patrimonio_liquido:,.2f}")
        st.metric("Valor da Cota:", f"R$ {cota_atual:,.4f}", f"{variacao_cota_dia:.2%}")
        st.markdown("---")
        st.markdown(f"**Posição Comprada:** `{posicao_comprada_perc:.2%}`")
        st.markdown(f"**Posição Vendida:** `{posicao_vendida_perc:.2%}`")
        st.markdown(f"**Net Long:** `{net_long:.2%}`")
        st.markdown(f"**Exposição Total:** `{exposicao_total:.2%}`")
        st.markdown("---")
        with st.expander("Gerenciar Ativos e Métricas"):
            configure_rtd_portfolio(df_config, metrics)
            
def configure_rtd_portfolio(df_config, metrics):
    st.subheader("Gerenciar Ativos da Carteira")
    edited_df = st.data_editor(df_config[['ticker', 'quantidade', 'posicao_alvo']], num_rows="dynamic", key="asset_editor", use_container_width=True)
    if st.button("Salvar Carteira"):
        try:
            with engine.connect() as conn:
                conn.execute(text("TRUNCATE TABLE portfolio_config RESTART IDENTITY;"))
                edited_df.to_sql('portfolio_config', conn, if_exists='append', index=False)
                conn.commit()
            st.success("Carteira salva com sucesso!")
            st.rerun()
        except Exception as e:
            st.error(f"Erro ao salvar carteira: {e}")
    
    st.subheader("Editar Métricas Diárias")
    with st.form("metrics_form"):
        # ... (código do formulário de métricas) ...
        submitted = st.form_submit_button("Atualizar Métricas")
        if submitted:
            # ... (lógica de salvar métricas) ...
            pass

# =================================================================
# PÁGINA 2: Visão Geral da Empresa (Overview)
# =================================================================
def visao_geral_empresa_page():
    st.title("Visão Geral da Empresa (Overview)")

    # --- Widget de Seleção de Ativo ---
    # Usaremos uma lista de exemplo por enquanto. No futuro, podemos popular isso do banco.
    lista_tickers = ["HAPV3.SA", "PETR4.SA", "VALE3.SA", "ITUB4.SA", "NFLX"]
    ticker_selecionado = st.selectbox("Pesquisar por Ações, ETFs, Notícias e mais", options=lista_tickers)

    if not ticker_selecionado:
        st.info("Por favor, selecione um ativo para começar a análise.")
        return

    try:
        # --- Busca de Dados em Tempo Real com yfinance ---
        ticker_data = yf.Ticker(ticker_selecionado)
        info = ticker_data.info
        hist = ticker_data.history(period="1y")
    except Exception as e:
        st.error(f"Não foi possível buscar os dados para {ticker_selecionado}. Verifique o ticker. Erro: {e}")
        return

    # --- Cabeçalho com Informações Principais ---
    nome_empresa = info.get('longName', ticker_selecionado)
    preco_atual = info.get('currentPrice', 0)
    variacao_dia = info.get('regularMarketChange', 0)
    variacao_perc = info.get('regularMarketChangePercent', 0) * 100
    
    st.subheader(nome_empresa)
    cols_header = st.columns(4)
    with cols_header[0]:
        st.metric("Preço Atual", f"{info.get('currency', '')} {preco_atual:,.2f}", f"{variacao_dia:,.2f} ({variacao_perc:.2f}%)")
    with cols_header[1]:
        st.metric("Capitalização de Mercado", f"{info.get('marketCap', 0) / 1e9:,.2f} Bi")
    with cols_header[2]:
        st.metric("P/L", f"{info.get('trailingPE', 0):,.2f}")
    with cols_header[3]:
        st.metric("DY (12M)", f"{info.get('dividendYield', 0) * 100:,.2f}%")

    st.markdown("---")
    
    # --- Layout Principal ---
    cols_main = st.columns([2, 1]) # Coluna esquerda maior para gráficos e dados

    with cols_main[0]:
        # --- Gráfico de Preços ---
        st.subheader("Gráfico de Preços (1 Ano)")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=hist.index, y=hist['Close'], mode='lines', name='Fechamento'))
        st.plotly_chart(fig, use_container_width=True)

        # --- Resumo: Dados Históricos ---
        st.subheader("Dados Históricos (Fundamentalistas)")
        st.info("Esta seção será preenchida com os dados do balanço, DRE, etc., que virão da página 'Dados Históricos'.")
        # Exemplo de como poderia ser:
        # df_dre = pd.read_sql(f"SELECT * FROM dre_table WHERE ticker = '{ticker_selecionado}'", engine)
        # st.dataframe(df_dre.head(3))
        st.button("Ver Análise Histórica Completa →", key="btn_hist")


    with cols_main[1]:
        # --- Resumo: Radar de Insiders ---
        st.subheader("Radar de Insiders (CVM 44)")
        try:
            # Tenta buscar dados do nosso banco. Se não encontrar, mostra a mensagem.
            df_insiders = pd.read_sql(f"SELECT * FROM transacoes WHERE nome_companhia ILIKE '%{nome_empresa.split(' ')[0]}%' ORDER BY data DESC LIMIT 5", engine)
            if not df_insiders.empty:
                st.dataframe(df_insiders[['data', 'descricao', 'categoria', 'valor']], hide_index=True)
            else:
                 st.info(f"Nenhum dado de insider encontrado para '{nome_empresa}' no banco de dados. Execute o pipeline ETL.")
        except Exception as e:
            st.warning(f"Não foi possível buscar dados de insiders. O pipeline ETL precisa ser executado. Erro: {e}")
        st.button("Ver Radar de Insiders Completo →", key="btn_insider")

        # --- Resumo: Documentos e Notícias ---
        st.subheader("Documentos e Notícias")
        st.info("Aqui entrará um resumo dos últimos fatos relevantes e notícias da empresa.")
        st.button("Ver Todas as Notícias e Documentos →", key="btn_news")

        st.subheader("Dados do Sell Side")
        st.info("Aqui entrará um resumo das recomendações de analistas (preço-alvo, etc.).")
        st.button("Ver Dados Completos do Sell Side →", key="btn_sellside")


# --- 4. NAVEGAÇÃO PRINCIPAL ---
st.sidebar.title("Plataforma Financeira")

PAGES = {
    "Carteira em Tempo Real": rtd_portfolio_page,
    "Visão Geral da Empresa (Overview)": visao_geral_empresa_page,
    "Dados Históricos": lambda: placeholder_page("📂 Dados Históricos"),
    "Comparador de Empresas": lambda: placeholder_page("⚖️ Comparador de Empresas"),
    "Radar de Insiders (CVM 44)": lambda: placeholder_page("📡 Radar de Insiders (CVM 44)"),
    "Pesquisa (Research/Estudos)": lambda: placeholder_page("🔬 Pesquisa (Research/Estudos)"),
    # Adicione as outras novas páginas aqui como placeholders
}

selection = st.sidebar.radio("Navegar para", list(PAGES.keys()))

page_function = PAGES[selection]
page_function()