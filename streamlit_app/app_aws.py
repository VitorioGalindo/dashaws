# streamlit_app/app_aws.py (Versão Final com Correções)

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

# --- 2. FUNÇÕES DAS PÁGINAS ---

def rtd_portfolio_page():
    st.title("📊 Carteira de Ações em Tempo Real")
    st_autorefresh(interval=60000, key="rtd_refresher")

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
    
    # --- Cálculos Principais ---
    df_portfolio['posicao_rs'] = df_portfolio['quantidade'] * df_portfolio['last_price']
    caixa_liquido = caixa_bruto + outros + outras_despesas
    total_acoes = df_portfolio['posicao_rs'].sum()
    patrimonio_liquido = total_acoes + caixa_liquido
    
    # PL do dia anterior para a contribuição percentual
    df_portfolio['posicao_rs_d1'] = df_portfolio['quantidade'] * df_portfolio['previous_close']
    pl_d1 = df_portfolio['posicao_rs_d1'].sum() + caixa_liquido if not df_portfolio.empty else caixa_liquido

    # Cálculos das colunas
    df_portfolio['var_dia_perc'] = ((df_portfolio['last_price'] / df_portfolio['previous_close']) - 1) * 100 if 'previous_close' in df_portfolio and (df_portfolio['previous_close'] > 0).all() else 0
    df_portfolio['contrib_rs'] = (df_portfolio['last_price'] - df_portfolio['previous_close']) * df_portfolio['quantidade']
    df_portfolio['posicao_perc'] = (df_portfolio['posicao_rs'] / patrimonio_liquido) * 100 if patrimonio_liquido != 0 else 0
    df_portfolio['contrib_perc'] = (df_portfolio['contrib_rs'] / pl_d1) * 100 if pl_d1 != 0 else 0
    df_portfolio['diferenca_perc'] = df_portfolio['posicao_perc'] - (df_portfolio['posicao_alvo'] * 100)
    df_portfolio['ajuste_qtd'] = ((df_portfolio['posicao_alvo'] * patrimonio_liquido - df_portfolio['posicao_rs']) / df_portfolio['last_price']).fillna(0).astype(int)

    # Cálculos do Resumo
    posicao_comprada_perc = df_portfolio[df_portfolio['posicao_rs'] > 0]['posicao_perc'].sum()
    posicao_vendida_perc = df_portfolio[df_portfolio['posicao_rs'] < 0]['posicao_perc'].sum()
    net_long = posicao_comprada_perc + posicao_vendida_perc
    exposicao_total = posicao_comprada_perc - posicao_vendida_perc

    cota_atual = patrimonio_liquido / qtd_cotas if qtd_cotas > 0 else 0
    variacao_cota_dia = (cota_atual / cota_d1 - 1) * 100 if cota_d1 > 0 else 0

    # --- Renderização do Dashboard ---
    main_cols = st.columns([3, 1])
    with main_cols[0]:
        st.subheader("Composição da Carteira")
        if not df_portfolio.empty:
            df_display = df_portfolio.rename(columns={'ticker': 'Ativo', 'last_price': 'Cotação', 'var_dia_perc': 'Var. Dia (%)', 'contrib_perc': 'Contrib. (%)', 'quantidade': 'Quantidade', 'posicao_rs': 'Posição (R$)', 'posicao_perc': 'Posição (%)', 'posicao_alvo': 'Posição % Alvo', 'diferenca_perc': 'Diferença', 'ajuste_qtd': 'Ajuste (Qtd.)'})
            df_display['Posição % Alvo'] = df_display['Posição % Alvo'] * 100
            st.dataframe(df_display[['Ativo', 'Cotação', 'Var. Dia (%)', 'Contrib. (%)', 'Quantidade', 'Posição (R$)', 'Posição (%)', 'Posição % Alvo', 'Diferença', 'Ajuste (Qtd.)']], use_container_width=True, hide_index=True)
        st.markdown(f"**Caixa Líquido:** `{caixa_liquido:,.2f}`")
        
        st.subheader("Gráficos")
        chart_cols = st.columns(2)
        with chart_cols[0]:
            st.markdown("###### Contribuição para Variação Diária")
            df_contrib = df_portfolio[df_portfolio['contrib_perc'] != 0].sort_values(by='contrib_perc', ascending=False)
            fig_contrib = go.Figure(go.Bar(x=df_contrib['ticker'], y=df_contrib['contrib_perc'], marker_color=['#22c55e' if v > 0 else '#ef4444' for v in df_contrib['contrib_perc']]))
            fig_contrib.update_yaxes(ticksuffix="%")
            st.plotly_chart(fig_contrib, use_container_width=True)
        with chart_cols[1]:
            st.markdown("###### Retorno Acumulado: Cota vs. Ibovespa")
            if not df_hist.empty:
                df_hist['data'] = pd.to_datetime(df_hist['data'])
                df_hist = df_hist.sort_values(by='data')
                df_hist['cota_return'] = (df_hist['cota'] / df_hist['cota'].iloc[0] - 1) * 100
                df_hist['ibov_return'] = (df_hist['ibov'] / df_hist['ibov'].iloc[0] - 1) * 100
                fig_hist = go.Figure()
                fig_hist.add_trace(go.Scatter(x=df_hist['data'], y=df_hist['cota_return'], mode='lines', name='Retorno da Cota'))
                fig_hist.add_trace(go.Scatter(x=df_hist['data'], y=df_hist['ibov_return'], mode='lines', name='Retorno do Ibovespa'))
                fig_hist.update_yaxes(ticksuffix="%")
                st.plotly_chart(fig_hist, use_container_width=True)
            else:
                st.info("Popule a tabela 'portfolio_history' para ver o gráfico.")

    with main_cols[1]:
        st.subheader("Resumo do Portfólio")
        st.metric("Patrimônio Líquido:", f"R$ {patrimonio_liquido:,.2f}")
        st.metric("Valor da Cota:", f"R$ {cota_atual:,.4f}", f"{variacao_cota_dia:.2f}%")
        st.markdown("---")
        st.markdown(f"**Posição Comprada:** `{posicao_comprada_perc:.2%}`")
        st.markdown(f"**Posição Vendida:** `{posicao_vendida_perc:.2%}`")
        st.markdown(f"**Net Long:** `{net_long:.2%}`")
        st.markdown(f"**Exposição Total:** `{exposicao_total:.2%}`")
        st.markdown("---")
        # ... (código do resumo como antes) ...

        with st.expander("Gerenciar Ativos e Métricas"):
            configure_rtd_portfolio(metrics)

def configure_rtd_portfolio(metrics):
    st.subheader("Editar Métricas Diárias")
    with st.form("metrics_form"):
        cota_d1_val = st.number_input("Cota D-1", value=float(metrics.get('cota_d1', 1.0)))
        qtd_cotas_val = st.number_input("Quantidade de Cotas", value=int(metrics.get('quantidade_cotas', 1)))
        caixa_val = st.number_input("Caixa Bruto", value=float(metrics.get('caixa_bruto', 0.0)))
        outros_val = st.number_input("Outros", value=float(metrics.get('outros', 0.0)))
        outras_despesas_val = st.number_input("Outras Despesas", value=float(metrics.get('outras_despesas', 0.0)))
        
        save_metrics_button = st.form_submit_button("Atualizar Métricas")
        
        if save_metrics_button:
            try:
                metrics_to_upsert = [
                    {"metric_key": "cota_d1", "metric_value": cota_d1_val},
                    {"metric_key": "quantidade_cotas", "metric_value": qtd_cotas_val},
                    {"metric_key": "caixa_bruto", "metric_value": caixa_val},
                    {"metric_key": "outros", "metric_value": outros_val},
                    {"metric_key": "outras_despesas", "metric_value": outras_despesas_val}
                ]
                with engine.connect() as conn:
                    for item in metrics_to_upsert:
                        conn.execute(text("""
                            INSERT INTO portfolio_metrics (metric_key, metric_value) VALUES (:k, :v)
                            ON CONFLICT (metric_key) DO UPDATE SET metric_value = :v;
                        """), {"k": item['metric_key'], "v": item['metric_value']})
                    conn.commit()
                st.success("Métricas salvas!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar métricas: {e}")

# --- NAVEGAÇÃO PRINCIPAL ---
st.sidebar.title("Plataforma Financeira")
# ... (seu código de navegação com as outras páginas)
rtd_portfolio_page()