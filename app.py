import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date
# import locale -> REMOVIDO: Não vamos mais usar esta biblioteca
import io
import json
import os
from streamlit_gsheets import GSheetsConnection

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Dashboard de Vendas Interativo", page_icon="📊", layout="wide")

# NOVO: Função própria para formatar moeda, que não depende do sistema operativo
def formatar_moeda_br(valor):
    """Formata um número para o padrão de moeda brasileiro (R$ 1.234,50)."""
    if valor is None:
        valor = 0.0
    # Formata com separador de milhar americano (,) e duas casas decimais (.)
    valor_formatado = f"{valor:,.2f}"
    # Troca temporariamente a vírgula por um placeholder
    valor_formatado = valor_formatado.replace(",", "X")
    # Troca o ponto decimal por uma vírgula
    valor_formatado = valor_formatado.replace(".", ",")
    # Troca o placeholder pelo ponto de milhar
    valor_formatado = valor_formatado.replace("X", ".")
    return f"R$ {valor_formatado}"

# --- FUNÇÕES DE CONFIGURAÇÃO (para regras de negócio) ---
CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {"premiacao_loja": 1000.0, "bonus_por_dia": 25.0}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'w') as f: json.dump(DEFAULT_CONFIG, f, indent=4)
    with open(CONFIG_FILE, 'r') as f: return json.load(f)

def save_config(config_data):
    with open(CONFIG_FILE, 'w') as f: json.dump(config_data, f, indent=4)

# --- NAVEGAÇÃO PRINCIPAL ---
st.sidebar.title("Navegação")
page = st.sidebar.radio("Selecione a página:", ["Dashboard", "⚙️ Administração"])
config = load_config()

# --- PÁGINA DO DASHBOARD ---
if page == "Dashboard":
    st.title("📊 Dashboard de Vendas Interativo")
    with st.expander("ℹ️ Ajuda e Detalhes do Dashboard", expanded=False):
        st.markdown("""
        **Como usar este painel:**
        - **1. Fonte de Dados:** A aplicação lê os dados automaticamente da sua Planilha Google configurada.
        - **2. Aplique os Filtros:** Na barra lateral, pode filtrar os dados por Loja e por um período de Data. Use o botão 'Resetar Filtros' para voltar ao estado inicial.
        - **3. Análise Interativa:** Todos os cartões de KPI e gráficos são atualizados automaticamente com base nos seus filtros.
        - **4. Exporte os Dados:** Abaixo dos gráficos, encontrará um botão para baixar os dados filtrados em Excel. Para exportar para PDF, use o botão na barra lateral.
        """)
    st.markdown("""
    <style>
    @media print {
        .stSidebar, [data-testid="stToolbar"], footer, .stExpander, .stSlider, .stButton { display: none !important; }
        .main .block-container { padding: 2rem !important; }
    }
    </style>
    """, unsafe_allow_html=True)
    st.markdown("---")

    # --- CARREGAMENTO AUTOMÁTICO DOS DADOS ---
    with st.spinner("A conectar com a Planilha Google e a carregar os dados..."):
        try:
            conn = st.connection("gsheets", type=GSheetsConnection)
            df_vendas = conn.read(worksheet="LOJAS", usecols=list(range(4)), ttl="10m")
            df_vendedores = conn.read(worksheet="VENDEDORES", usecols=list(range(4)), ttl="10m")
            df_vendas.dropna(how="all", inplace=True)
            df_vendedores.dropna(how="all", inplace=True)
            df_vendas['Data'] = pd.to_datetime(df_vendas['Data'])
            df_vendedores['Data'] = pd.to_datetime(df_vendedores['Data'])
        except Exception as e:
            st.error(f"❌ Erro ao conectar ou ler a Planilha Google.")
            st.error("Verifique se o URL em 'secrets.toml' está correto e se a planilha foi partilhada com o email da conta de serviço.")
            st.exception(e)
            st.stop()

    # --- O RESTO DA APLICAÇÃO ---
    min_data_geral, max_data_geral = df_vendas['Data'].min().date(), df_vendas['Data'].max().date()
    def resetar_filtros():
        st.session_state.loja_selecionada = "Todas as Lojas"
        st.session_state.data_selecionada = (min_data_geral, max_data_geral)
    if 'loja_selecionada' not in st.session_state:
        resetar_filtros()
    st.sidebar.header("Filtros")
    st.sidebar.button("🔄 Resetar Filtros", on_click=resetar_filtros)
    lista_lojas = df_vendas['Loja'].unique().tolist()
    lista_lojas.insert(0, "Todas as Lojas")
    st.sidebar.selectbox("Selecione a Loja", lista_lojas, key='loja_selecionada')
    st.sidebar.date_input("Selecione o Período", key='data_selecionada')
    st.sidebar.markdown("---")
    if st.sidebar.button('📄 Exportar para PDF'):
        st.markdown('<script>window.print();</script>', unsafe_allow_html=True)

    loja_sel = st.session_state.loja_selecionada
    datas_selecionadas = st.session_state.data_selecionada
    if len(datas_selecionadas) != 2:
        st.warning("🗓️ Por favor, selecione uma data de **início** e de **fim** para continuar.")
        st.stop()
    data_ini, data_fim = datas_selecionadas
    df_vendas_por_data = df_vendas[(df_vendas['Data'].dt.date >= data_ini) & (df_vendas['Data'].dt.date <= data_fim)]
    df_vendedores_por_data = df_vendedores[(df_vendedores['Data'].dt.date >= data_ini) & (df_vendedores['Data'].dt.date <= data_fim)]
    if loja_sel != "Todas as Lojas":
        df_vendas_final = df_vendas_por_data[df_vendas_por_data['Loja'] == loja_sel]
        df_vendedores_final = df_vendedores_por_data[df_vendedores_por_data['Loja'] == loja_sel]
    else:
        df_vendas_final = df_vendas_por_data
        df_vendedores_final = df_vendedores_por_data

    st.header(f"Resultados para: {loja_sel}")
    meta_total = df_vendas_final['Meta'].sum()
    venda_acumulada = df_vendas_final['Venda Realizada'].sum()
    percentual_meta = (venda_acumulada / meta_total) * 100 if meta_total > 0 else 0
    dias_meta_batida = df_vendas_final[df_vendas_final['Venda Realizada'] >= df_vendas_final['Meta']].shape[0]
    premiacao_loja = config["premiacao_loja"] if venda_acumulada >= meta_total and meta_total > 0 else 0.0
    bonus_meta = dias_meta_batida * config["bonus_por_dia"]
    premiacao_total = premiacao_loja + bonus_meta
    col1, col2, col3 = st.columns(3); col4, col5, col6 = st.columns(3)
    # ALTERADO: Usa a nova função formatar_moeda_br em vez de locale.currency
    with col1: st.metric(label="🎯 Meta", value=formatar_moeda_br(meta_total))
    with col2: st.metric(label="💰 Venda Acumulada", value=formatar_moeda_br(venda_acumulada))
    with col3: st.metric(label="📈 % da Meta", value=f"{percentual_meta:.2f}%")
    with col4: st.metric(label="🏆 Dias de Meta Batida", value=f"{dias_meta_batida} dias")
    with col5: st.metric(label="🎁 Premiação da Loja", value=formatar_moeda_br(premiacao_loja), help=f"Valor configurado: {formatar_moeda_br(config['premiacao_loja'])}")
    with col6: st.metric(label="🎉 Bónus Meta Batida", value=formatar_moeda_br(bonus_meta), help=f"Valor configurado: {formatar_moeda_br(config['bonus_por_dia'])} por dia")
    
    st.markdown("---")
    # ... [O restante do código de Gráficos e Admin permanece o mesmo] ...
    st.header("Análises Visuais")
    graph_col1, graph_col2 = st.columns(2)
    with graph_col1:
        metas_vendas_loja = df_vendas_por_data.groupby('Loja')[['Meta', 'Venda Realizada']].sum().reset_index()
        cores_vendas = ['green' if row['Venda Realizada'] >= row['Meta'] else 'red' for index, row in metas_vendas_loja.iterrows()]
        fig_vendas_loja = go.Figure()
        fig_vendas_loja.add_trace(go.Bar(x=metas_vendas_loja['Loja'], y=metas_vendas_loja['Meta'], name='Meta', marker_color='lightslategrey', text=metas_vendas_loja['Meta'], texttemplate='R$ %{text:,.2f}', textposition='auto'))
        fig_vendas_loja.add_trace(go.Bar(x=metas_vendas_loja['Loja'], y=metas_vendas_loja['Venda Realizada'], name='Venda Realizada', marker_color=cores_vendas, text=metas_vendas_loja['Venda Realizada'], texttemplate='R$ %{text:,.2f}', textposition='auto'))
        fig_vendas_loja.update_layout(barmode='group', title_text='Meta vs. Venda Realizada por Loja', xaxis_title='Loja', yaxis_title='Valor (R$)', legend_title_text=None, yaxis_tickformat=",.0f")
        st.plotly_chart(fig_vendas_loja, use_container_width=True)
    with graph_col2:
        vendas_por_vendedor = df_vendedores_final.groupby('Vendedor')['Venda Realizada'].sum().reset_index().sort_values('Venda Realizada', ascending=False)
        total_vendedores = len(vendas_por_vendedor)
        if total_vendedores > 0:
            valor_padrao = min(10, total_vendedores)
            num_vendedores_para_mostrar = st.slider("Selecione quantos vendedores de topo deseja exibir:", 1, total_vendedores, valor_padrao)
            vendas_por_vendedor_top_n = vendas_por_vendedor.head(num_vendedores_para_mostrar)
            if not vendas_por_vendedor_top_n.empty:
                cores_podio = ['gold', 'silver', '#CD7F32']; cores_grafico = [cores_podio[i] if i < 3 else 'red' for i in range(len(vendas_por_vendedor_top_n))]
                fig_vendas_vendedor = px.bar(vendas_por_vendedor_top_n, x='Venda Realizada', y='Vendedor', orientation='h', title=f'Top {len(vendas_por_vendedor_top_n)} Vendedores em {loja_sel}', text_auto=True, labels={'Venda Realizada': 'Venda (R$)', 'Vendedor': 'Vendedores'})
                fig_vendas_vendedor.update_traces(marker_color=cores_grafico, texttemplate='R$ %{x:,.2f}'); fig_vendas_vendedor.update_layout(showlegend=False, yaxis_autorange="reversed")
                st.plotly_chart(fig_vendas_vendedor, use_container_width=True)
    st.markdown("---")
    if loja_sel != "Todas as Lojas":
        st.header(f"Desempenho Diário para: {loja_sel}")
        df_detalhe_loja = df_vendas_final.sort_values('Data')
        cores_diario = ['green' if row['Venda Realizada'] >= row['Meta'] else 'red' for index, row in df_detalhe_loja.iterrows()]
        fig_detalhe = go.Figure()
        fig_detalhe.add_trace(go.Bar(x=df_detalhe_loja['Data'], y=df_detalhe_loja['Meta'], name='Meta', marker_color='lightslategrey', text=df_detalhe_loja['Meta'], texttemplate='R$ %{text:,.2f}', textposition='auto'))
        fig_detalhe.add_trace(go.Bar(x=df_detalhe_loja['Data'], y=df_detalhe_loja['Venda Realizada'], name='Venda Realizada', marker_color=cores_diario, text=df_detalhe_loja['Venda Realizada'], texttemplate='R$ %{text:,.2f}', textposition='auto'))
        fig_detalhe.update_layout(barmode='group', xaxis_title='Data', yaxis_title='Valor (R$)')
        st.plotly_chart(fig_detalhe, use_container_width=True)
    st.header("Distribuição da Premiação entre Vendedores")
    if premiacao_total > 0 and venda_acumulada > 0:
        vendas_por_vendedor_dist = df_vendedores_final.groupby('Vendedor')['Venda Realizada'].sum().reset_index()
        vendas_por_vendedor_dist['% da Venda'] = (vendas_por_vendedor_dist['Venda Realizada'] / venda_acumulada)
        vendas_por_vendedor_dist['Valor da Premiação'] = vendas_por_vendedor_dist['% da Venda'] * premiacao_total
        vendas_por_vendedor_premiados = vendas_por_vendedor_dist[vendas_por_vendedor_dist['Valor da Premiação'] > 0].sort_values('Valor da Premiação', ascending=False)
        fig_premiacao = px.bar(vendas_por_vendedor_premiados, x='Vendedor', y='Valor da Premiação', title='Premiação por Vendedor', text_auto=True, labels={'Valor da Premiação': 'Prémio (R$)', 'Vendedor': 'Vendedores'})
        fig_premiacao.update_traces(texttemplate='R$ %{y:,.2f}', marker_color='#0083B8')
        st.plotly_chart(fig_premiacao, use_container_width=True)
    else:
        st.info("Não há premiações a serem distribuídas para o período/loja selecionado(a).")
    st.markdown("---")
    @st.cache_data
    def para_excel(df1, df2):
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df1.to_excel(writer, index=False, sheet_name='Vendas_Filtradas'); df2.to_excel(writer, index=False, sheet_name='Vendedores_Filtrados')
        return output.getvalue()
    if not df_vendas_final.empty:
        nome_ficheiro = f"relatorio_{str(loja_sel).replace(' ', '_')}_{date.today()}.xlsx"
        st.download_button(label="📥 Baixar Dados Filtrados para Excel", data=para_excel(df_vendas_final, df_vendedores_final), file_name=nome_ficheiro, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# --- PÁGINA DE ADMINISTRAÇÃO ---
elif page == "⚙️ Administração":
    st.title("⚙️ Painel de Administração")
    st.markdown("---")
    st.subheader("Configuração das Regras de Premiação")
    current_config = load_config()
    with st.form(key="config_form"):
        new_premio_loja = st.number_input("Valor da Premiação da Loja (R$)", min_value=0.0, value=current_config["premiacao_loja"], step=50.0, format="%.2f", help="Valor do prémio se a loja atingir a meta do período.")
        new_bonus_dia = st.number_input("Valor do Bónus por Dia de Meta Batida (R$)", min_value=0.0, value=current_config["bonus_por_dia"], step=1.0, format="%.2f", help="Valor a ser pago por cada dia em que a meta diária foi superada.")
        submitted = st.form_submit_button("💾 Salvar Alterações")
        if submitted:
            new_config = {"premiacao_loja": new_premio_loja, "bonus_por_dia": new_bonus_dia}
            save_config(new_config)
            st.success("Configurações salvas com sucesso! O dashboard usará estes novos valores na próxima vez que for atualizado.")