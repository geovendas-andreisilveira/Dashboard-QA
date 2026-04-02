import streamlit as st
import pandas as pd
from datetime import datetime
import calendar
from jira import JIRA
from streamlit_autorefresh import st_autorefresh
import extra_streamlit_components as stx
import json
import gspread
import time
import io
import urllib.parse
import plotly.express as px
import streamlit.components.v1 as components # 🔥 Para as notificações e Harry Potter

# Configuração da Página
st.set_page_config(page_title="Portal QA - Gold Edition 🏆", layout="wide")

# ==========================================
# 🪄 TEMAS DE HOGWARTS (Cores e Imagens)
# ==========================================
# Usando a URL do ícone original colorido do portal como exemplo.
# Você pode trocar essas URLs abaixo por URLs reais de imagens/gifs que você preferir!
temas_hp = {
    "🏰 Sem Casa (Padrão)": {
        "primaria": "#FF4B4B", "secundaria": "#f0f2f6", "grafico_ok": "#2e7b32", "grafico_erro": "#d4a017",
        "hp_content": {"header_img": "https://cdn-icons-png.flaticon.com/512/1067/1067357.png", "sidebar_gif": "https://cdn-icons-png.flaticon.com/512/1067/1067357.png"} 
    },
    "🦁 Grifinória": {
        "primaria": "#740001", "secundaria": "#D3A625", "grafico_ok": "#740001", "grafico_erro": "#D3A625",
        "hp_content": {"header_img": "https://cdn-icons-png.flaticon.com/512/1067/1067357.png", "sidebar_gif": "https://cdn-icons-png.flaticon.com/512/1067/1067357.png"} 
    },
    "🐍 Sonserina": {
        "primaria": "#1A472A", "secundaria": "#5D5D5D", "grafico_ok": "#1A472A", "grafico_erro": "#aaaaaa",
        "hp_content": {"header_img": "https://cdn-icons-png.flaticon.com/512/1067/1067357.png", "sidebar_gif": "https://cdn-icons-png.flaticon.com/512/1067/1067357.png"} 
    },
    "🦅 Corvinal": {
        "primaria": "#0E1A40", "secundaria": "#946B2D", "grafico_ok": "#0E1A40", "grafico_erro": "#946B2D",
        "hp_content": {"header_img": "https://cdn-icons-png.flaticon.com/512/1067/1067357.png", "sidebar_gif": "https://cdn-icons-png.flaticon.com/512/1067/1067357.png"} 
    },
    "🦡 Lufa-Lufa": {
        "primaria": "#EEB939", "secundaria": "#000000", "grafico_ok": "#EEB939", "grafico_erro": "#555555",
        "hp_content": {"header_img": "https://cdn-icons-png.flaticon.com/512/1067/1067357.png", "sidebar_gif": "https://cdn-icons-png.flaticon.com/512/1067/1067357.png"} 
    }
}

# ==========================================
# ☁️ CONEXÃO COM O GOOGLE SHEETS E JIRA
# ==========================================
@st.cache_resource
def conectar_google_sheets():
    creds_dict = json.loads(st.secrets["google_credentials_json"])
    gc = gspread.service_account_from_dict(creds_dict)
    sh = gc.open("Base_Portal_QA")
    return sh.worksheet("Dados")

try:
    worksheet = conectar_google_sheets()
except Exception as e:
    st.error(f"Erro ao conectar no Google Sheets. Verifique o compartilhamento. Detalhe: {e}")
    st.stop()

def validar_credenciais_jira(servidor, email, token):
    try:
        jira = JIRA(server=servidor, basic_auth=(email, token), max_retries=0, timeout=5)
        jira.myself() 
        return True
    except Exception:
        return False

# ==========================================
# 🍪 LÓGICA DE LOGIN
# ==========================================
cookie_manager = stx.CookieManager()
cookies = cookie_manager.get_all()

if isinstance(cookies, dict):
    cookie_email = cookies.get("jira_email")
    cookie_token = cookies.get("jira_token")
    cookie_servidor = cookies.get("jira_servidor")

    if cookie_email and cookie_token and not st.session_state.get('jira_logado'):
        st.session_state.jira_servidor = str(cookie_servidor).strip('"')
        st.session_state.jira_email = str(cookie_email).strip('"')
        st.session_state.jira_token = str(cookie_token).strip('"')
        st.session_state.jira_logado = True
        st.rerun()

if not st.session_state.get('jira_logado', False):
    st.title("🔐 Login - Portal QA")
    st.write("Bem-vindo! Insira suas credenciais do Jira para acessar o painel.")
    
    with st.form("login_form"):
        servidor_input = st.text_input("URL do Jira", value="https://geovendas.atlassian.net")
        email_input = st.text_input("Seu E-mail do Jira")
        token_input = st.text_input("Seu Token de API", type="password")
        lembrar = st.checkbox("Lembrar de mim por 30 dias", value=True)
        submit = st.form_submit_button("Entrar no Painel")
        
        if submit:
            if email_input and token_input:
                with st.spinner("Validando suas credenciais no Jira... Aguarde."):
                    if validar_credenciais_jira(servidor_input, email_input, token_input):
                        if lembrar:
                            cookie_manager.set("jira_servidor", servidor_input, max_age=30*24*60*60, key="set_s")
                            cookie_manager.set("jira_email", email_input, max_age=30*24*60*60, key="set_e")
                            cookie_manager.set("jira_token", token_input, max_age=30*24*60*60, key="set_t")
                            time.sleep(1) 
                        
                        st.session_state.jira_servidor = servidor_input
                        st.session_state.jira_email = email_input
                        st.session_state.jira_token = token_input
                        st.session_state.jira_logado = True
                        st.rerun()
                    else:
                        st.error("❌ Token ou E-mail incorretos! Gere um novo token e tente novamente.")
            else:
                st.warning("Preencha o e-mail e o token para continuar.")
    st.stop()

# ==========================================
# ⏱️ TEMPO REAL E DADOS
# ==========================================
# 🔥 CSS para suavizar a "piscada preta" do autorefresh
st.markdown("""
    <style>
    .stApp { transition: background-color 0.1s ease; }
    </style>
""", unsafe_allow_html=True)

st_autorefresh(interval=60000, limit=None, key="jira_refresh")

mes_atual_str = datetime.now().strftime("%Y-%m")
usuario_atual = st.session_state.jira_email

def carregar_todos_dados():
    records = worksheet.get_all_records()
    if not records:
        return pd.DataFrame(columns=["Task", "Criados", "Sem_Correcao", "Com_Correcao", "Mes", "Label", "Grupo", "Usuario", "Desenvolvedor"])
    df = pd.DataFrame(records)
    df.columns = df.columns.str.strip()
    if "Desenvolvedor" not in df.columns:
        df["Desenvolvedor"] = "Não Informado"
    return df

def salvar_task_no_sheets(task, criados, sem_c, com_c, mes, label, grupo, usuario, desenvolvedor):
    records = worksheet.get_all_records()
    df = pd.DataFrame(records)
    row_idx = None
    if not df.empty and "Task" in df.columns:
        match = df[(df["Task"] == task) & (df["Usuario"] == usuario)]
        if not match.empty:
            row_idx = match.index[0] + 2 
            
    nova_linha = [task, criados, sem_c, com_c, mes, label, grupo, usuario, desenvolvedor]
    
    if row_idx:
        worksheet.update(f"A{row_idx}:I{row_idx}", [nova_linha])
    else:
        worksheet.append_row(nova_linha)

def categorizar_projeto(nome_projeto):
    if not nome_projeto: return "OUTROS"
    nome_upper = str(nome_projeto).upper()
    if "B2B" in nome_upper or "CRM" in nome_upper: return "B2B_CRM"
    elif "FORÇA" in nome_upper or "ANALYTICS" in nome_upper or "FV" in nome_upper or "TÊXTIL" in nome_upper: return "FV_FVT_AN"
    else: return "OUTROS"

@st.cache_data(ttl=55) 
def buscar_tarefas_jira_real(servidor, email, token):
    try:
        jira = JIRA(server=servidor, basic_auth=(email, token), max_retries=1, timeout=15)
        # Trava de Março!
        jql = f'assignee = currentUser() AND updated >= "2026-03-01" ORDER BY updated DESC'
        issues = jira.search_issues(jql, maxResults=100) 
        
        tarefas = []
        for issue in issues:
            if getattr(issue.fields.issuetype, 'subtask', False): continue
            status_atual = str(issue.fields.status).upper()
            area_encontrada = "Desconhecida"
            dev_encontrado = "Não Informado"
            
            for field_name in dir(issue.fields):
                if field_name.startswith("customfield_"):
                    val = getattr(issue.fields, field_name)
                    if val and hasattr(val, 'value'):
                        if any(x in str(val.value) for x in ["B2B", "CRM", "Força", "Analytics", "Têxtil"]):
                            area_encontrada = str(val.value)
                    if val and hasattr(val, 'displayName') and field_name not in ['assignee', 'creator', 'reporter']:
                        dev_encontrado = val.displayName

            tarefas.append({
                "chave": issue.key, "resumo": issue.fields.summary,
                "status": status_atual, "label": area_encontrada, "grupo": categorizar_projeto(area_encontrada),
                "desenvolvedor": dev_encontrado
            })
        return tarefas
    except Exception as e:
        return f"ERRO_AUTH: {str(e)}"

with st.spinner("Sincronizando tarefas e gerando gráficos..."):
    dados_todos_unfiltered = carregar_todos_dados()
    tarefas_jira = buscar_tarefas_jira_real(st.session_state.jira_servidor, st.session_state.jira_email, st.session_state.jira_token)

if isinstance(tarefas_jira, str) and tarefas_jira.startswith("ERRO_AUTH"):
    if isinstance(cookies, dict):
        if "jira_servidor" in cookies: cookie_manager.delete("jira_servidor", key="err_s")
        if "jira_email" in cookies: cookie_manager.delete("jira_email", key="err_e")
        if "jira_token" in cookies: cookie_manager.delete("jira_token", key="err_t")
    st.session_state.clear()
    time.sleep(1)
    st.error(f"⚠️ Não foi possível conectar ao Jira. A sessão expirou ou o token é inválido.")
    st.stop()

# ==========================================
# 🧙‍♂️ TEMA HP, AVATAR E NOME DINÂMICO
# ==========================================
avatares = ["🧙‍♂️", "👩‍🎤", "👨‍💻", "👩‍🔬", "🤖"]
cookie_avatar = cookies.get("qa_avatar")
avatar_index = avatares.index(cookie_avatar) if cookie_avatar in avatares else 0
avatar_exibicao = avatares[avatar_index]

cookie_house = cookies.get("qa_house")
casa_index = list(temas_hp.keys()).index(cookie_house) if cookie_house in temas_hp else 0

nome_exibicao = usuario_atual.split('@')[0].split('.')[0].capitalize() if "@" in usuario_atual else "Usuário"

cor_primaria = temas_hp[list(temas_hp.keys())[casa_index]]["primaria"]
st.markdown(f"""
    <style>
    div[data-testid="stMetricValue"] {{ color: {cor_primaria}; }}
    .stButton>button {{ border-color: {cor_primaria}; color: {cor_primaria}; }}
    .stButton>button:hover {{ background-color: {cor_primaria}; color: white; }}
    </style>
""", unsafe_allow_html=True)

# 🔥 ADICIONANDO HEADER DE HARRY POTTER COLORIDO
st.write("") # some space
house_header_img = temas_hp[list(temas_hp.keys())[casa_index]]["hp_content"]["header_img"]
st.image(house_header_img, use_container_width=True) # full width banner
st.title(f"📊 Painel de Controle QA - {avatar_exibicao} {nome_exibicao}")

with st.sidebar:
    st.markdown("### 🪄 Personalização")
    
    avatar_escolhido = st.radio("Seu avatar informally:", avatares, index=avatar_index, horizontal=True)
    if avatar_escolhido != cookie_avatar:
         cookie_manager.set("qa_avatar", avatar_escolhido, max_age=30*24*60*60, key="set_a")
         time.sleep(0.5) 
         st.rerun()

    casa_escolhida = st.selectbox("Chapéu Seletor (Tema HP):", list(temas_hp.keys()), index=casa_index)
    if casa_escolhida != cookie_house:
         cookie_manager.set("qa_house", casa_escolhida, max_age=30*24*60*60, key="set_h")
         time.sleep(0.5)
         st.rerun()

    st.divider()

    st.markdown("### 🔔 Notificações do Sistema")
    st.caption("Ative para receber alertas no PC quando houver novas tarefas.")
    components.html("""
        <script>
        function pedirPermissao() {
            Notification.requestPermission().then(function(permission) {
                if(permission === 'granted') {
                    new Notification('✅ Tudo pronto!', {
                        body: 'O Portal QA enviará notificações por aqui!',
                        icon: 'https://cdn-icons-png.flaticon.com/512/1067/1067357.png'
                    });
                }
            });
        }
        </script>
        <button onclick="pedirPermissao()" style="background:#FF4B4B; color:white; border:none; padding:8px 12px; border-radius:5px; cursor:pointer; width:100%; font-weight:bold; font-family:sans-serif;">
            Ativar Notificações no PC
        </button>
    """, height=50)

    st.divider()

    if st.button("🚪 Sair do Sistema", use_container_width=True):
        if isinstance(cookies, dict):
            if "jira_servidor" in cookies: cookie_manager.delete("jira_servidor", key="del_s")
            if "jira_email" in cookies: cookie_manager.delete("jira_email", key="del_e")
            if "jira_token" in cookies: cookie_manager.delete("jira_token", key="del_t")
        st.session_state.clear()
        time.sleep(1.5) 
        st.rerun()
    
    # 🔥 ADICIONANDO GIF/IMAGEM HP NO FINAL DA SIDEBAR COLORIDO
    st.divider()
    house_sidebar_gif = temas_hp[list(temas_hp.keys())[casa_index]]["hp_content"]["sidebar_gif"]
    st.image(house_sidebar_gif, width=200) # smaller image/gif

st.divider()

# ==========================================
# 🛡️ PERMISSÕES E ABAS (Nova Lógica Unificada)
# ==========================================
# O Alison queria tudo numa aba só. Mas para o Andrei, criamos a "Sala Precisa".
eh_andrei = "andrei.silveira" in usuario_atual.lower()

if eh_andrei:
    abas = st.tabs(["📊 Painel Geral (Visão Unificada)", "🕵️‍♂️ Sala Precisa (Análise de Devs)"])
    tab_geral = abas[0]
    tab_andrei = abas[1]
else:
    abas = st.tabs(["📊 Painel Geral (Visão Unificada)"])
    tab_geral = abas[0]
    tab_andrei = None

# Função auxiliar da Tabela de Gestão
def gerar_tabela_chefe_estilizada(df_grupo):
    if df_grupo.empty: return pd.DataFrame()
    resumo_equipe = df_grupo.groupby("Usuario")[["Criados", "Sem_Correcao", "Com_Correcao"]].sum().reset_index()
    resumo_equipe["QA Responsável"] = resumo_equipe["Usuario"].apply(lambda x: str(x).split('@')[0].split('.')[0].capitalize())
    resumo_equipe = resumo_equipe.rename(columns={"Criados": "Total Cenários", "Sem_Correcao": "Aprovados", "Com_Correcao": "Com Erro"})
    resumo_equipe["% Sucesso"] = (resumo_equipe["Aprovados"] / resumo_equipe["Total Cenários"].replace(0, 1)) * 100
    
    total_criados = resumo_equipe["Total Cenários"].sum()
    total_sem = resumo_equipe["Aprovados"].sum()
    total_com = resumo_equipe["Com Erro"].sum()
    taxa_total = (total_sem / total_criados * 100) if total_criados > 0 else 0
    
    linha_total_equipe = pd.DataFrame({
        "QA Responsável": ["TOTAL DA ÁREA"], "Total Cenários": [total_criados],
        "Aprovados": [total_sem], "Com Erro": [total_com], "% Sucesso": [taxa_total]
    })
    tabela_final = pd.concat([resumo_equipe, linha_total_equipe], ignore_index=True)
    tabela_final = tabela_final[["QA Responsável", "Total Cenários", "Aprovados", "Com Erro", "% Sucesso"]]
    tabela_final["% Sucesso"] = tabela_final["% Sucesso"].fillna(0).round(1)
    return tabela_final

# 🔥 NOVA FUNÇÃO DE GRÁFICO: BARRAS COMPARATIVAS EQUIPE x PESSOAL
def criar_grafico_barras_comparativo(df_mes_area, titulo_base, cor_principal):
    if df_mes_area.empty: return None

    # Agrupa dados por QA para o comparativo
    resumo_qa = df_mes_area.groupby("Usuario")[["Criados", "Sem_Correcao", "Com_Correcao"]].sum().reset_index()
    
    # Adiciona média e total da equipe para contexto
    avg_team = resumo_qa.mean(numeric_only=True).to_frame().T
    avg_team["Usuario"] = "MÉDIA DA EQUIPE"
    total_team = resumo_qa.sum(numeric_only=True).to_frame().T
    total_team["Usuario"] = "TOTAL DA EQUIPE"

    # Combina tudo numa tabela para plotar
    resumo_comparativo = pd.concat([resumo_qa, avg_team, total_team], ignore_index=True)

    # Melt data for grouped bar chart
    resumo_comparativo_long = pd.melt(resumo_comparativo, id_vars=["Usuario"], value_vars=["Criados", "Sem_Correcao", "Com_Correcao"], var_name="Métrica", value_name="Quantidade")

    # Custom sorting to make sure standard metrics are together
    metrics_order = {"Criados": 1, "Sem_Correcao": 2, "Com_Correcao": 3}
    resumo_comparativo_long["Metrics_sort"] = resumo_comparativo_long["Métrica"].map(metrics_order)
    resumo_comparativo_long = resumo_comparativo_long.sort_values(by=["Metrics_sort", "Usuario"]).reset_index(drop=True)
    
    # Deixa o nome mais limpo
    resumo_comparativo_long["QA"] = resumo_comparativo_long["Usuario"].apply(lambda x: x.split('@')[0].split('.')[0].capitalize() if '@' in str(x) else str(x))

    # Cria o gráfico de barras empilhadas/agrupadas
    fig = px.bar(resumo_comparativo_long, x="QA", y="Quantidade", color="Métrica", barmode="group",
                category_orders={"Métrica": ["Criados", "Sem_Correcao", "Com_Correcao"]},
                color_discrete_map={"Criados": "#c0c0c0", "Sem_Correcao": cor_principal, "Com_Correcao": "#d4a017"},
                title=f"<b>{titulo_base}</b><br><span style='font-size:14px; color:gray;'>Média QA vs Área</span>")
    
    # Update layout for cleaner look, good space for names
    fig.update_layout(
        xaxis_title="QA Responsável",
        yaxis_title="Quantidade de Cenários",
        legend_title="Métrica",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=30, b=20, l=20, r=20),
        height=300
    )
    
    # Rotaciona os nomes do eixo X se forem muitos
    if len(resumo_comparativo["Usuario"].unique()) > 6:
        fig.update_xaxes(tickangle=45)
    
    return fig

# ==========================================
# 📊 ABA 1: PAINEL GERAL (Tudo Numa Tela Só)
# ==========================================
with tab_geral:
    # --- FILTRO MESTRE E EXCEL NO TOPO ---
    with st.container(border=True):
        col_filtro, col_excel_meu, col_excel_equipe = st.columns([0.4, 0.3, 0.3])
        
        meses_disponiveis = list(dados_todos_unfiltered["Mes"].unique())
        if mes_atual_str not in meses_disponiveis:
            meses_disponiveis.append(mes_atual_str)
        meses_disponiveis = sorted(meses_disponiveis, reverse=True)
        
        col_filtro.write("**Mês de Referência:**")
        mes_selecionado = col_filtro.selectbox("Selecione o Mês:", meses_disponiveis, index=0, label_visibility="collapsed")

        # Filtrando os dados baseados no mês mestre
        df_mes_equipe = dados_todos_unfiltered[dados_todos_unfiltered["Mes"] == mes_selecionado]
        df_mes_usuario = df_mes_equipe[df_mes_equipe["Usuario"] == usuario_atual]
        
        # 🔥 GERADOR DE EXCEL INDIVIDUAL POTENCIALIZADO COM RESUMOS 🔥
        def gerar_excel_meu():
            output = io.BytesIO()
            writer = pd.ExcelWriter(output, engine='xlsxwriter')
            if not df_mes_usuario.empty:
                df_mes_usuario.to_excel(writer, sheet_name='Cenários Detalhados', index=False)
                
                # Resumo B2B Individual
                df_b2b_usuario = df_mes_usuario[df_mes_usuario["Grupo"] == "B2B_CRM"]
                if not df_b2b_usuario.empty:
                    resumo_b2b_individual = df_b2b_usuario.groupby("Desenvolvedor")[["Criados", "Sem_Correcao", "Com_Correcao"]].sum().reset_index()
                    resumo_b2b_individual["% Acerto"] = (resumo_b2b_individual["Sem_Correcao"] / resumo_b2b_individual["Criados"].replace(0, 1)) * 100
                    resumo_b2b_individual["% Acerto"] = resumo_b2b_individual["% Acerto"].fillna(0).round(1)
                    resumo_b2b_individual.to_excel(writer, sheet_name='Resumo B2B Individual', index=False)
                
                # Resumo FV Individual
                df_fv_usuario = df_mes_usuario[df_mes_usuario["Grupo"] == "FV_FVT_AN"]
                if not df_fv_usuario.empty:
                    resumo_fv_individual = df_fv_usuario.groupby("Desenvolvedor")[["Criados", "Sem_Correcao", "Com_Correcao"]].sum().reset_index()
                    resumo_fv_individual["% Acerto"] = (resumo_fv_individual["Sem_Correcao"] / resumo_fv_individual["Criados"].replace(0, 1)) * 100
                    resumo_fv_individual["% Acerto"] = resumo_fv_individual["% Acerto"].fillna(0).round(1)
                    resumo_fv_individual.to_excel(writer, sheet_name='Resumo FV Individual', index=False)
            else:
                pd.DataFrame({"Aviso": ["Sem dados salvos neste mês."]}).to_excel(writer, sheet_name='Aviso', index=False)
            writer.close() 
            return output.getvalue()

        # GERADOR DE EXCEL EQUIPE (Como sempre)
        def gerar_excel_equipe():
            output = io.BytesIO()
            writer = pd.ExcelWriter(output, engine='xlsxwriter')
            if not df_mes_equipe.empty:
                df_mes_equipe.to_excel(writer, sheet_name='Cenários da Equipe', index=False)
                tabela_gestor_fv = gerar_tabela_chefe_estilizada(df_mes_equipe[df_mes_equipe["Grupo"] == "FV_FVT_AN"])
                if not tabela_gestor_fv.empty: tabela_gestor_fv.to_excel(writer, sheet_name='Ranking_QA_FV', index=False)
                tabela_gestor_b2b = gerar_tabela_chefe_estilizada(df_mes_equipe[df_mes_equipe["Grupo"] == "B2B_CRM"])
                if not tabela_gestor_b2b.empty: tabela_gestor_b2b.to_excel(writer, sheet_name='Ranking_QA_B2B', index=False)
            else:
                pd.DataFrame({"Aviso": ["Sem dados salvos neste mês."]}).to_excel(writer, sheet_name='Aviso', index=False)
            writer.close()
            return output.getvalue()

        col_excel_meu.write("**Relatório Individual:**")
        col_excel_meu.download_button(label="📥 Baixar Meu Excel", data=gerar_excel_meu(), file_name=f"Meu_Relatorio_{mes_selecionado}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

        col_excel_equipe.write("**Relatório da Equipe:**")
        col_excel_equipe.download_button(label="📥 Baixar Excel da Equipe", data=gerar_excel_equipe(), file_name=f"Relatorio_Equipe_{mes_selecionado}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

    # --- 1. MÉTRICAS PESSOAIS NO TOPO (Como sempre) ---
    st.write("")
    st.markdown(f"### 🏆 Meu Resumo ({mes_selecionado})")
    
    total_cr_u = int(df_mes_usuario["Criados"].sum()) if not df_mes_usuario.empty else 0
    total_sc_u = int(df_mes_usuario["Sem_Correcao"].sum()) if not df_mes_usuario.empty else 0
    total_cc_u = int(df_mes_usuario["Com_Correcao"].sum()) if not df_mes_usuario.empty else 0
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Total de Cenários (Meus)", total_cr_u)
    c2.metric("Aprovados Direto ✅", total_sc_u)
    c3.metric("Com Correção ⚠️", total_cc_u)

    st.divider()

    # --- 2. LAYOUT LADO A LADO (Planilha Gestão x Novo Gráfico Barras Comparativo) ---
    st.markdown(f"### 🏢 Gestão & Comparativo de Qualidade ({mes_selecionado})")
    st.caption("Visão consolidada da equipe (esquerda) vs. Desempenho Pessoal no comparativo de média (direita)")

    # B2B Section
    col_b2b_tabela, col_b2b_grafico = st.columns([0.6, 0.4])
    with col_b2b_tabela:
        st.markdown("**📊 Equipe B2B - CRM (Produtividade)**")
        tabela_b2b = gerar_tabela_chefe_estilizada(df_mes_equipe[df_mes_equipe["Grupo"] == "B2B_CRM"])
        if not tabela_b2b.empty: st.dataframe(tabela_b2b.style.format({"% Sucesso": "{:.1f}%"}), hide_index=True, use_container_width=True)
        else: st.caption("Sem dados para a equipe B2B neste mês.")

    with col_b2b_grafico:
        with st.container(border=True):
            # 🔥 NOVO GRÁFICO COMPARATIVO B2B 🔥
            g_b2b_comp = criar_grafico_barras_comparativo(df_mes_equipe[df_mes_equipe["Grupo"] == "B2B_CRM"], "Comparativo Qualidade B2B", cor_primaria)
            if g_b2b_comp is not None: st.plotly_chart(g_b2b_comp, use_container_width=True)
            else: st.caption("Sem dados de B2B para o comparativo.")

    st.write("")

    # FV Section
    col_fv_tabela, col_fv_grafico = st.columns([0.6, 0.4])
    with col_fv_tabela:
        st.markdown("**📱 Equipe FV - FVT - AN (Produtividade)**")
        tabela_fv = gerar_tabela_chefe_estilizada(df_mes_equipe[df_mes_equipe["Grupo"] == "FV_FVT_AN"])
        if not tabela_fv.empty: st.dataframe(tabela_fv.style.format({"% Sucesso": "{:.1f}%"}), hide_index=True, use_container_width=True)
        else: st.caption("Sem dados para a equipe FV neste mês.")

    with col_fv_grafico:
        with st.container(border=True):
            # 🔥 NOVO GRÁFICO COMPARATIVO FV 🔥
            g_fv_comp = criar_grafico_barras_comparativo(df_mes_equipe[df_mes_equipe["Grupo"] == "FV_FVT_AN"], "Comparativo Qualidade FV", cor_primaria)
            if g_fv_comp is not None: st.plotly_chart(g_fv_comp, use_container_width=True)
            else: st.caption("Sem dados de FV para o comparativo.")

    st.divider()

    # --- 3. AÇÕES FINAIS (E-mail e Histórico) (Como sempre) ---
    hoje = datetime.now()
    ultimo_dia = calendar.monthrange(hoje.year, hoje.month)[1]
    dias_para_fim = ultimo_dia - hoje.day
    
    if dias_para_fim <= 5 and mes_selecionado == mes_atual_str:
        with st.popover("🚨 Fechar Mês e Enviar Relatório ao Gestor"):
            st.markdown(f"Faltam **{dias_para_fim} dias** para fechar {mes_selecionado}.")
            t_g = (total_sc_u / total_cr_u * 100) if total_cr_u > 0 else 0
            assunto = f"Relatório QA - {nome_exibicao} ({mes_selecionado})"
            corpo = f"Olá Gestor, tudo bem?\n\nSegue o relatório dos meus testes de {mes_selecionado}.\n\n📊 Resumo:\nCriados: {total_cr_u}\nAprovados: {total_sc_u}\nErros: {total_cc_u}\nAcerto: {t_g:.1f}%\n\nO Excel completo está em anexo.\nAbraços,\n{nome_exibicao}"
            assunto_url = urllib.parse.quote(assunto)
            corpo_url = urllib.parse.quote(corpo)
            mailto_link = f"mailto:?subject={assunto_url}&body={corpo_url}"
            st.markdown(f'<a href="{mailto_link}" style="display: block; text-align: center; padding: 0.5em 1em; color: white; background-color: {cor_primaria}; border-radius: 0.3em; text-decoration: none; font-weight: bold;">📧 Abrir E-mail</a>', unsafe_allow_html=True)
            st.caption("Dica: Baixe seu Excel acima e anexe no e-mail.")

    # --- 4. CARDS DE TAREFAS (Sempre no final) ---
    if mes_selecionado != mes_atual_str:
        # 🔥 HISTÓRICO ESCONDIDO NUM EXPANDER (Deixa a tela limpa)
        with st.expander(f"🗄️ Clique aqui para abrir o Histórico de {mes_selecionado}", expanded=False):
            st.caption("Você está visualizando o arquivo morto. Tarefas de meses passados não podem ser editadas por aqui.")
            t_pesquisa_h = st.text_input(f"🔍 Pesquisar no histórico de {mes_selecionado}...", "")
            if df_mes_usuario.empty:
                st.info(f"Nenhum dado foi salvo por você no mês de {mes_selecionado}.")
            else:
                for idx, row in df_mes_usuario.iterrows():
                    ch, dv = row["Task"], row["Desenvolvedor"]
                    if t_pesquisa_h:
                        tm = t_pesquisa_h.lower()
                        if tm not in ch.lower() and tm not in dv.lower(): continue
                    with st.container(border=True):
                        l_t = f"{st.session_state.jira_servidor}/browse/{ch}"
                        st.markdown(f"### ✅ [{ch}]({l_t})")
                        st.write(f"**Área:** {row['Label']} | 👨‍💻 **Dev:** `{dv}`")
                        st.success(f"Registrado em {mes_selecionado} | Criados: **{row['Criados']}** | Sem Corr.: **{row['Sem_Correcao']}** | Com Corr.: **{row['Com_Correcao']}**")
    else:
        st.header(f"📝 Minhas Tarefas para Preencher ({mes_atual_str})")
        t_pesquisa_filling = st.text_input("🔍 Pesquisar tarefa (ex: QUA-1234, Felipe Bogo, Pagamento...)", "")
        t_exibidas = 0
        if 'status_anterior' not in st.session_state: st.session_state.status_anterior = {}
        
        for t_j in tarefas_jira:
            c, s = t_j["chave"], t_j["status"]
            dv_r = t_j.get("desenvolvedor", "Não Informado")
            rs = t_j['resumo']
            if t_pesquisa_filling:
                tm_p = t_pesquisa_filling.lower()
                if tm_p not in c.lower() and tm_p not in dv_r.lower() and tm_p not in rs.lower(): continue 
            
            l_g = dados_todos_unfiltered[(dados_todos_unfiltered["Task"] == c) & (dados_todos_unfiltered["Usuario"] == usuario_atual)] if not dados_todos_unfiltered.empty else pd.DataFrame()
            j_preenchido_geral = not l_g.empty
            if j_preenchido_geral and l_g.iloc[0]["Mes"] != mes_atual_str: continue 

            l_d_atual = df_mes_usuario[df_mes_usuario["Task"] == c] if not df_mes_usuario.empty else pd.DataFrame()
            j_p_neste_mes = not l_d_atual.empty

            # 🔥 O DISPARO DA NOTIFICAÇÃO NATIVA OCORRE AQUI!
            s_ant = st.session_state.status_anterior.get(c, "DESCONHECIDO")
            if s == "PUBLISHED" and s_ant != "PUBLISHED":
                if not j_p_neste_mes: 
                    st.toast(f"🚀 Tarefa {c} liberada para QA!", icon="🔔")
                    icone_url = "https://cdn-icons-png.flaticon.com/512/1067/1067357.png"
                    components.html(f"""
                        <script>
                        if (Notification.permission === 'granted') {{
                            new Notification('Portal QA - Nova Tarefa!', {{
                                body: 'A tarefa {c} está pronta para ser testada.\\nResumo: {rs}',
                                icon: '{icone_url}'
                            }});
                        }}
                        </script>
                    """, height=0, width=0)
            st.session_state.status_anterior[c] = s

            is_dn = s in ["DONE", "PUBLISHED", "CONCLUÍDO", "ENTREGUE"]
            if not is_dn and not j_p_neste_mes: continue 
            t_exibidas += 1
            e_k = f"edit_{c}"
            if e_k not in st.session_state: st.session_state[e_k] = False

            with st.container(border=True):
                l_ta = f"{st.session_state.jira_servidor}/browse/{c}"
                st.markdown(f"### [{c}]({l_ta}) - {rs}")
                st.write(f"**Status:** `{s}` | **Área:** {t_j['label']} | 👨‍💻 **Dev:** `{dv_r}`")

                if j_p_neste_mes and not st.session_state[e_k]:
                    c_f_r, s_f_c, c_f_c = int(l_d_atual["Criados"].iloc[0]), int(l_d_atual["Sem_Correcao"].iloc[0]), int(l_d_atual["Com_Correcao"].iloc[0])
                    c_t, c_b = st.columns([0.8, 0.2])
                    c_t.success(f"✅ **Registrado** | Criados: **{c_f_r}** | Sem Corr.: **{s_f_c}** | Com Corr.: **{c_f_c}**")
                    c_b.write("") 
                    if c_b.button("✏️ Editar", key=f"btn_edit_{c}", use_container_width=True, disabled=not is_dn):
                        st.session_state[e_k] = True
                        st.rerun()
                else:
                    d_cr_filling = int(l_d_atual["Criados"].iloc[0]) if j_p_neste_mes else 0
                    d_sc_filling = int(l_d_atual["Sem_Correcao"].iloc[0]) if j_p_neste_mes else 0
                    d_cc_filling = int(l_d_atual["Com_Correcao"].iloc[0]) if j_p_neste_mes else 0
                    
                    m_recentes = [(pd.to_datetime("today") - pd.DateOffset(months=i)).strftime("%Y-%m") for i in range(3)]
                    c1, c2, c3, c4 = st.columns([0.20, 0.20, 0.20, 0.40])
                    c_i = c1.number_input("Criados", min_value=0, step=1, value=d_cr_filling, key=f"cr_{c}")
                    s_i = c2.number_input("Sem Correção", min_value=0, step=1, value=d_sc_filling, key=f"sc_{c}")
                    cc_i = c3.number_input("Com Correção", min_value=0, step=1, value=d_cc_filling, key=f"cc_{c}")
                    m_ref_i = c4.selectbox("Mês Referência", m_recentes, index=0, key=f"mes_ref_{c}")
                    
                    st.write("") 
                    c_b1, c_b2 = st.columns([0.5, 0.5])
                    
                    if c_b1.button("💾 Salvar", key=f"btn_salvar_{c}", use_container_width=True):
                        salvar_task_no_sheets(c, c_i, s_i, cc_i, m_ref_i, t_j['label'], t_j['grupo'], usuario_atual, dv_r)
                        st.session_state[e_k] = False 
                        st.toast(f"Métricas salvas na Nuvem!", icon="☁️")
                        st.rerun()

                    if st.session_state[e_k]:
                        if c_b2.button("❌ Cancelar", key=f"btn_cancel_{c}", use_container_width=True):
                            st.session_state[e_k] = False
                            st.rerun()

        if t_exibidas == 0:
            if t_pesquisa_filling: 
                st.warning("Nenhuma tarefa encontrada na sua pesquisa.")
            else: 
                st.balloons() 
                st.success("🎉 Sensacional! Fila zerada. Nenhuma tarefa aguardando preenchimento no momento!")

# ==========================================
# 🕵️‍♂️ ABA 2: SALA PRECISA (Andrei - Gerenciamento)
# ==========================================
# Esta aba é a mesma da última versão, pois o Alison dispensou, mas você quer ter o controle.
if tab_andrei:
    with tab_andrei:
        st.header("Análise Profunda e Sala Precisa dos Devs")
        st.caption("Esta aba é visível apenas para a engenharia de qualidade (Andrei Vinicius).")
        
        if not dados_todos_unfiltered.empty:
            meses_dev = list(dados_todos_unfiltered["Mes"].unique())
            if mes_atual_str not in meses_dev: meses_dev.append(mes_atual_str)
            mes_dev_selecionado = st.selectbox("Selecione o Mês para Análise:", sorted(meses_dev, reverse=True))
            
            df_mes_dev = dados_todos_unfiltered[dados_todos_unfiltered["Mes"] == mes_dev_selecionado]
            
            st.subheader("🚀 Ranking Geral de Desenvolvedores")
            if not df_mes_dev.empty:
                df_devs_equipe = df_mes_dev.groupby(["Grupo", "Desenvolvedor"])[["Criados", "Sem_Correcao", "Com_Correcao"]].sum().reset_index()
                df_devs_equipe["Taxa de Acerto"] = (df_devs_equipe["Sem_Correcao"] / df_devs_equipe["Criados"].replace(0, 1)) * 100
                df_devs_equipe["Taxa de Acerto"] = df_devs_equipe["Taxa de Acerto"].fillna(0).round(1)
                df_devs_equipe = df_devs_equipe.rename(columns={"Grupo": "Área", "Sem_Correcao": "Sem Corr.", "Com_Correcao": "Com Corr."})
                df_devs_equipe = df_devs_equipe.sort_values(by=["Área", "Taxa de Acerto"], ascending=[True, False])
                st.dataframe(df_devs_equipe.style.format({"Taxa de Acerto": "{:.1f}%"}), hide_index=True, use_container_width=True)

            st.divider()

            st.subheader("📋 Raio-X Cirúrgico (Quem testou o quê?)")
            if not df_mes_dev.empty:
                devs_unicos = sorted(df_mes_dev["Desenvolvedor"].unique())
                for dev in devs_unicos:
                    df_dev = df_mes_dev[df_mes_dev["Desenvolvedor"] == dev].copy()
                    total_cr_dev = df_dev["Criados"].sum()
                    total_sc_dev = df_dev["Sem_Correcao"].sum()
                    total_cc_dev = df_dev["Com_Correcao"].sum()
                    taxa_final_dev = (total_sc_dev / total_cr_dev * 100) if total_cr_dev > 0 else 0
                    
                    titulo_expander = f"👨‍💻 {dev} | Acerto Final: {taxa_final_dev:.1f}% | Total de Cenários: {total_cr_dev} (✅ {total_sc_dev} / ⚠️ {total_cc_dev})"
                    
                    with st.expander(titulo_expander, expanded=False):
                        df_detalhe = df_dev[["Task", "Usuario", "Grupo", "Criados", "Sem_Correcao", "Com_Correcao"]].copy()
                        df_detalhe["QA Responsável"] = df_detalhe["Usuario"].apply(lambda x: str(x).split('@')[0].split('.')[0].capitalize())
                        df_detalhe["% da Task"] = (df_detalhe["Sem_Correcao"] / df_detalhe["Criados"].replace(0, 1)) * 100
                        df_detalhe = df_detalhe[["Task", "QA Responsável", "Grupo", "Criados", "Sem_Correcao", "Com_Correcao", "% da Task"]]
                        df_detalhe = df_detalhe.rename(columns={"Sem_Correcao": "Aprovados", "Com_Correcao": "Com Bug"})
                        st.dataframe(df_detalhe.style.format({"% da Task": "{:.1f}%"}), hide_index=True, use_container_width=True)
            else:
                st.caption("Sem dados detalhados para exibir neste mês.")
        else:
            st.warning("Nenhum dado registrado na nuvem.")
