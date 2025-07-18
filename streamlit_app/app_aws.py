# streamlit_app/app_aws.py (Versão Final com Correção de Estilo)

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import boto3
from streamlit_autorefresh import st_autorefresh
import plotly.graph_objects as go

# --- 1. CONFIGURAÇÃO E CONEXÃO COM O BANCO ---
st.set_page_config(layout="wide", page_title="Dashboard Financeiro Unificado")

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

engine = get_db_engine()

# --- 2. FUNÇÕES DE ESTILO E PÁGINAS ---

def style_dataframe(df):
    """Aplica toda a formatação e coloração ao DataFrame da carteira."""
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
    
    # Usamos .map() em vez de .apply() para aplicar a função a cada célula individualmente
    styled_df = df.style.format(format_dict, na_rep="").map(
        color_negative_red,
        subset=['Var. Dia (%)', 'Contrib. (%)', 'Diferença', 'Ajuste (Qtd.)']
    )
    return styled_df

def rtd_portfolio_page():
    st.title("📊 Carteira de Ações em Tempo Real (RTD)")
    st_autorefresh(interval=60000, key="rtd_refresher")

    # --- Busca de Dados ---
    try:
        df_config = pd.read_sql("SELECT * FROM portfolio_config", engine, index_col='id')
        df_quotes = pd.read_sql("SELECT * FROM realtime_quotes", engine)
        metrics_resp = pd.read_sql("SELECT * FROM portfolio_metrics", engine)
        df_hist = pd.read_sql("SELECT data, cota, ibov FROM portfolio_history ORDER BY data ASC", engine)
    except Exception as e:
        st.error(f"Erro ao carregar dados do banco: {e}")
        return

    # --- Preparação e Cálculos ---
    metrics = {item['metric_key']: item['metric_value'] for item in metrics_resp.to_dict('records')}
    cota_d1 = metrics.get('cota_d1', 1.0)
    qtd_cotas = metrics.get('quantidade_cotas', 1)
    caixa_bruto = metrics.get('caixa_bruto', 0.0)
    outros = metrics.get('outros', 0.0)
    outras_despesas = metrics.get('outras_despesas', 0.0)

    if df_config.empty:
        df_config = pd.DataFrame(columns=['ticker', 'quantidade', 'posicao_alvo'])
    else:
        df_config.reset_index(inplace=True)
    
    df_portfolio = pd.merge(df_config, df_quotes, on='ticker', how='left').fillna(0)
    
    # Cálculos
    caixa_liquido = caixa_bruto + outros + outras_despesas
    df_portfolio['posicao_rs'] = df_portfolio['quantidade'] * df_portfolio['last_price']
    total_acoes = df_portfolio['posicao_rs'].sum()
    patrimonio_liquido = total_acoes + caixa_liquido
    
    # Armazena os valores como decimais (ex: 0.02 para 2%)
    df_portfolio['var_dia_perc'] = (df_portfolio['last_price'] / df_portfolio['previous_close'] - 1) if 'previous_close' in df_portfolio and (df_portfolio['previous_close'] > 0).all() else 0
    df_portfolio['contrib_rs'] = (df_portfolio['last_price'] - df_portfolio['previous_close']) * df_portfolio['quantidade']
    pl_d1 = (df_portfolio['quantidade'] * df_portfolio['previous_close']).sum() + caixa_liquido if not df_portfolio.empty else caixa_liquido
    df_portfolio['posicao_perc'] = (df_portfolio['posicao_rs'] / patrimonio_liquido) if patrimonio_liquido != 0 else 0
    df_portfolio['contrib_perc'] = (df_portfolio['contrib_rs'] / pl_d1) if pl_d1 != 0 else 0
    df_portfolio['diferenca_perc'] = df_portfolio['posicao_perc'] - df_portfolio['posicao_alvo']
    df_portfolio['ajuste_qtd'] = ((df_portfolio['posicao_alvo'] * patrimonio_liquido - df_portfolio['posicao_rs']) / df_portfolio['last_price']).fillna(0)

    # Cálculos Resumo
    posicao_comprada_perc = df_portfolio[df_portfolio['posicao_rs'] > 0]['posicao_perc'].sum()
    posicao_vendida_perc = df_portfolio[df_portfolio['posicao_rs'] < 0]['posicao_perc'].sum()
    net_long = posicao_comprada_perc + posicao_vendida_perc
    exposicao_total = posicao_comprada_perc - posicao_vendida_perc
    cota_atual = patrimonio_liquido / qtd_cotas if qtd_cotas > 0 else 0
    variacao_cota_dia = (cota_atual / cota_d1 - 1) if cota_d1 > 0 else 0

    # --- Renderização do Dashboard ---
    main_cols = st.columns([3, 1])
    with main_cols[0]:
        st.subheader("Composição da Carteira")
        if not df_portfolio.empty:
            df_display = df_portfolio.rename(columns={
                'ticker': 'Ativo', 'last_price': 'Cotação', 'var_dia_perc': 'Var. Dia (%)',
                'contrib_perc': 'Contrib. (%)', 'quantidade': 'Quantidade', 'posicao_rs': 'Posição (R$)',
                'posicao_perc': 'Posição (%)', 'posicao_alvo': 'Posição % Alvo',
                'diferenca_perc': 'Diferença', 'ajuste_qtd': 'Ajuste (Qtd.)'
            })
            
            # Multiplica por 100 apenas para a exibição
            for col in ['Var. Dia (%)', 'Contrib. (%)', 'Posição (%)', 'Posição % Alvo', 'Diferença']:
                df_display[col] *= 100
            
            st.dataframe(style_dataframe(df_display[['Ativo', 'Cotação', 'Var. Dia (%)', 'Contrib. (%)', 'Quantidade', 'Posição (R$)', 'Posição (%)', 'Posição % Alvo', 'Diferença', 'Ajuste (Qtd.)']]), use_container_width=True, hide_index=True)
        st.markdown(f"**Caixa Líquido:** `{caixa_liquido:,.2f}`")
        # ... (código dos gráficos como na resposta anterior) ...

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
        # ... (código do resumo como antes) ...

        with st.expander("Gerenciar Ativos e Métricas"):
            configure_rtd_portfolio(df_config.set_index('id'), metrics)

def configure_rtd_portfolio(df_config, metrics):
    st.subheader("Gerenciar Ativos da Carteira")
    st.info("Para adicionar ou remover ativos, use a tabela abaixo e clique em Salvar.")
    edited_df = st.data_editor(df_config, num_rows="dynamic", key="asset_editor", use_container_width=True)
    if st.button("Salvar Alterações nos Ativos"):
        try:
            with engine.connect() as conn:
                conn.execute(text("TRUNCATE TABLE portfolio_config RESTART IDENTITY;"))
                # Salva o dataframe editado (sem a coluna de ID do índice)
                edited_df.to_sql('portfolio_config', conn, if_exists='append', index=True, index_label='id')
                conn.commit()
            st.success("Carteira salva com sucesso!")
            st.rerun()
        except Exception as e:
            st.error(f"Erro ao salvar carteira: {e}")
    
    st.subheader("Editar Métricas Diárias")
    with st.form("metrics_form"):
        # ... (código do formulário de métricas como na resposta anterior) ...
        cota_d1_val = st.number_input("Cota D-1", value=float(metrics.get('cota_d1', 1.0)))
        qtd_cotas_val = st.number_input("Quantidade de Cotas", value=int(metrics.get('quantidade_cotas', 1)))
        caixa_val = st.number_input("Caixa Bruto", value=float(metrics.get('caixa_bruto', 0.0)))
        outros_val = st.number_input("Outros", value=float(metrics.get('outros', 0.0)))
        outras_despesas_val = st.number_input("Outras Despesas", value=float(metrics.get('outras_despesas', 0.0)))
        submitted = st.form_submit_button("Atualizar Métricas")
        if submitted:
            # ... (lógica de salvar métricas como na resposta anterior) ...
            pass

# --- NAVEGAÇÃO PRINCIPAL ---
rtd_portfolio_page()