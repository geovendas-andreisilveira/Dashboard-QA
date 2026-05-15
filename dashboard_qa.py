import streamlit as st
import pandas as pd
from datetime import datetime
import calendar
from jira import JIRA
import extra_streamlit_components as stx
import json
import gspread
import time
import io
import urllib.parse
import plotly.express as px
import streamlit.components.v1 as components

# ==========================================
# 🗄️ NOVA IMPORTAÇÃO DO BANCO DE DADOS
# ==========================================
try:
    import psycopg2
except ImportError:
    st.error("⚠️ Biblioteca 'psycopg2' não encontrada. Adicione 'psycopg2-binary' no seu requirements.txt")

# Configuração da Página
st.set_page_config(page_title="Portal QA - Gold Edition 🏆", layout="wide")

# ==========================================
# 🪄 TEMAS DE HOGWARTS E IMAGENS
# ==========================================
temas_hp = {
    "🏰 Sem Casa (Padrão)": {
        "primaria": "#FF4B4B", "grafico_ok": "#2e7b32", "grafico_erro": "#d4a017",
        "img_header": "https://cdn-icons-png.flaticon.com/512/1067/1067357.png" 
    },
    "🦁 Grifinória": {
        "primaria": "#ff4d4d", "grafico_ok": "#ff4d4d", "grafico_erro": "#ffc107",
        "img_header": "https://github.com/geovendas-andreisilveira/Dashboard-QA/blob/main/grifinoria.png?raw=true"
    },
    "🐍 Sonserina": {
        "primaria": "#4caf50", "grafico_ok": "#4caf50", "grafico_erro": "#e0e0e0",
        "img_header": "https://github.com/geovendas-andreisilveira/Dashboard-QA/blob/main/sonserina.png?raw=true"
    },
    "🦅 Corvinal": {
        "primaria": "#64b5f6", "grafico_ok": "#64b5f6", "grafico_erro": "#ffb300",
        "img_header": "https://github.com/geovendas-andreisilveira/Dashboard-QA/blob/main/corvinal.png?raw=true"
    },
    "🦡 Lufa-Lufa": {
        "primaria": "#ffd54f", "grafico_ok": "#ffd54f", "grafico_erro": "#9e9e9e",
        "img_header": "https://github.com/geovendas-andreisilveira/Dashboard-QA/blob/main/lufalufa.png?raw=true"
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
# 🗄️ LÓGICA DE VERIFICAÇÃO DE BASES POSTGRESQL
# ==========================================
@st.cache_data(ttl=300) # Cache de 5 min para não sobrecarregar o DBeaver/Servidor
def verificar_status_bases(bases_str):
    if not bases_str or bases_str == "Não informada" or str(bases_str).strip() == "":
        return []
    
    # Divide caso tenha mais de uma base (ex: zteste-122, zteste-123)
    bases = [b.strip() for b in bases_str.replace(';', ',').split(',') if b.strip()]
    resultados = []
    
    # Servidores capturados da sua imagem do DBeaver
    servidores = ["192.168.37.20", "192.168.37.22"]
    
    # ! IMPORTANTE: Puxe isso do st.secrets ou coloque chumbado (apenas usuário de LEITURA)
    user_db = st.secrets.get("db_user", "SEU_USUARIO_POSTGRES") 
    pass_db = st.secrets.get("db_pass", "SUA_SENHA_POSTGRES")

    for base in bases:
        encontrada_ativa = False
        erro_conexao = False
        
        for ip in servidores:
            try:
                # Conecta no banco 'postgres' padrão para checar se o banco alvo existe na lista
                conn = psycopg2.connect(host=ip, port="5432", user=user_db, password=pass_db, dbname="postgres", connect_timeout=3)
                conn.autocommit = True
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (base,))
                existe = cursor.fetchone()
                cursor.close()
                conn.close()
                
                if existe:
                    encontrada_ativa = True
                    break # Achou a base ativa neste servidor, não precisa checar o outro
            except Exception as e:
                erro_conexao = True
        
        if encontrada_ativa:
            resultados.append({"base": base, "status": "Ativa"})
        elif erro_conexao and not encontrada_ativa:
            resultados.append({"base": base, "status": "Erro_Conexao"})
        else:
            resultados.append({"base": base, "status": "Excluida"})
            
    return resultados

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
        jql = f'assignee = currentUser() AND updated >= "2026-03-01" ORDER BY updated DESC'
        issues = jira.search_issues(jql, maxResults=100) 
        
        tarefas = []
        for issue in issues:
            if getattr(issue.fields.issuetype, 'subtask', False): continue
            status_atual = str(issue.fields.status).upper()
            area_encontrada = "Desconhecida"
            dev_encontrado = "Não Informado"
            base_dados_encontrada = "Não informada"
            
            for field_name in dir(issue.fields):
                if field_name.startswith("customfield_"):
                    val = getattr(issue.fields, field_name)
                    # Busca labels e Devs
                    if val and hasattr(val, 'value'):
                        if any(x in str(val.value) for x in ["B2B", "CRM", "Força", "Analytics", "Têxtil"]):
                            area_encontrada = str(val.value)
                    if val and hasattr(val, 'displayName') and field_name not in ['assignee', 'creator', 'reporter']:
                        dev_encontrado = val.displayName
                    
                    # NOVA LÓGICA: Busca o nome da Base de Dados (Campo Texto)
                    if val and isinstance(val, str):
                        val_str = str(val).lower()
                        # Procura por padrões comuns que vocês usam nas bases
                        if "zcalian" in val_str or "zteste" in val_str or "dalari" in val_str:
                            base_dados_encontrada = str(val)

            tarefas.append({
                "chave": issue.key, "resumo": issue.fields.summary,
                "status": status_atual, "label": area_encontrada, "grupo": categorizar_projeto(area_encontrada),
                "desenvolvedor": dev_encontrado,
                "base_dados": base_dados_encontrada # Salva a base atrelada a task
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
# 🧙‍♂️ TEMA HP E INTERFACE (Mantidos iguais)
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
    div[data-testid="stMetricValue"] {{ color: {cor_primaria}; text-shadow: 0px 0px 10px {cor_primaria}80; }}
    .stButton>button {{ border-color: {cor_primaria}; color: {cor_primaria}; }}
    .stButton>button:hover {{ background-color: {cor_primaria}; color: white; box-shadow: 0px 0px 10px {cor_primaria}; }}
    @keyframes float {{ 0% {{ transform: translateY(0px); }} 50% {{ transform: translateY(-10px); }} 100% {{ transform: translateY(0px); }} }}
    .magia-flutuante {{ animation: float 3s ease-in-out infinite; }}
    </style>
""", unsafe_allow_html=True)

img_header_url = temas_hp[list(temas_hp.keys())[casa_index]]["img_header"]
st.markdown(f"""
    <div style="display: flex; align-items: center; gap: 20px; margin-bottom: 20px;">
        <img src="{img_header_url}" width="80" class="magia-flutuante">
        <h1 style="margin: 0; padding: 0;">Painel QA - {avatar_exibicao} {nome_exibicao}</h1>
    </div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### 🪄 Personalização")
    avatar_escolhido = st.radio("Seu avatar informal:", avatares, index=avatar_index, horizontal=True)
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
    if st.button("🔄 Sincronizar Dados", use_container_width=True): st.rerun()
    st.divider()

    if st.button("🚪 Sair do Sistema", use_container_width=True):
        if isinstance(cookies, dict):
            if "jira_servidor" in cookies: cookie_manager.delete("jira_servidor", key="del_s")
            if "jira_email" in cookies: cookie_manager.delete("jira_email", key="del_e")
            if "jira_token" in cookies: cookie_manager.delete("jira_token", key="del_t")
        st.session_state.clear()
        time.sleep(1.5) 
        st.rerun()

st.divider()

# ==========================================
# 🛡️ PERMISSÕES E ABAS 
# ==========================================
eh_andrei = "andrei.silveira" in usuario_atual.lower()
if eh_andrei:
    abas = st.tabs(["📊 Painel Geral (Visão Unificada)", "🕵️‍♂️ Sala Precisa (Análise de Devs)"])
    tab_geral, tab_andrei = abas[0], abas[1]
else:
    abas = st.tabs(["📊 Painel Geral (Visão Unificada)"])
    tab_geral, tab_andrei = abas[0], None

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
    
    linha_total_equipe = pd.DataFrame({"QA Responsável": ["TOTAL DA ÁREA"], "Total Cenários": [total_criados], "Aprovados": [total_sem], "Com Erro": [total_com], "% Sucesso": [taxa_total]})
    tabela_final = pd.concat([resumo_equipe, linha_total_equipe], ignore_index=True)
    tabela_final = tabela_final[["QA Responsável", "Total Cenários", "Aprovados", "Com Erro", "% Sucesso"]]
    tabela_final["% Sucesso"] = tabela_final["% Sucesso"].fillna(0).round(1)
    return tabela_final

def criar_grafico_donut_limpo(df_filtrado, titulo_base):
    if df_filtrado.empty: return None 
    cr, sc, cc = df_filtrado["Criados"].sum(), df_filtrado["Sem_Correcao"].sum(), df_filtrado["Com_Correcao"].sum()
    taxa = (sc / cr * 100) if cr > 0 else 0
    c_ok, c_erro = temas_hp[list(temas_hp.keys())[casa_index]]["grafico_ok"], temas_hp[list(temas_hp.keys())[casa_index]]["grafico_erro"]
    
    df_plot = pd.DataFrame({"Status": ["Aprovados ✅", "Com Correção ⚠️"], "Quantidade": [sc, cc]})
    fig = px.pie(df_plot, values='Quantidade', names='Status', hole=0.65, color='Status', color_discrete_map={"Aprovados ✅": c_ok, "Com Correção ⚠️": c_erro})
    fig.update_layout(title_text=f"<b>{titulo_base}</b><br><span style='font-size:18px; color:{c_ok};'><b>{taxa:.1f}%</b></span>", title_x=0.5, margin=dict(t=50, b=10, l=10, r=10), showlegend=False, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=220)
    fig.update_traces(textposition='inside', textinfo='percent', hoverinfo='label+value', marker=dict(line=dict(color='#1E1E1E', width=1)))
    return fig

# ==========================================
# 📊 ABA 1: PAINEL GERAL
# ==========================================
with tab_geral:
    with st.container(border=True):
        col_filtro, col_excel_meu, col_excel_equipe = st.columns([0.4, 0.3, 0.3])
        meses_disponiveis = list(dados_todos_unfiltered["Mes"].unique()) if not dados_todos_unfiltered.empty else []
        if mes_atual_str not in meses_disponiveis: meses_disponiveis.append(mes_atual_str)
        meses_disponiveis = sorted(meses_disponiveis, reverse=True)
        
        col_filtro.write("**Mês de Referência:**")
        mes_selecionado = col_filtro.selectbox("Selecione o Mês:", meses_disponiveis, index=0, label_visibility="collapsed")
        df_mes_equipe = dados_todos_unfiltered[dados_todos_unfiltered["Mes"] == mes_selecionado]
        df_mes_usuario = df_mes_equipe[df_mes_equipe["Usuario"] == usuario_atual]
        
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

    if mes_selecionado != mes_atual_str:
        with st.expander(f"🗄️ Histórico de {mes_selecionado}", expanded=False):
            t_pesquisa_h = st.text_input(f"🔍 Pesquisar no histórico...", "")
            if not df_mes_usuario.empty:
                for idx, row in df_mes_usuario.iterrows():
                    ch, dv = row["Task"], row["Desenvolvedor"]
                    if t_pesquisa_h and t_pesquisa_h.lower() not in ch.lower() and t_pesquisa_h.lower() not in dv.lower(): continue
                    with st.container(border=True):
                        st.markdown(f"### ✅ [{ch}]({st.session_state.jira_servidor}/browse/{ch})")
                        st.success(f"Registrado | Criados: **{row['Criados']}** | Sem Corr.: **{row['Sem_Correcao']}**")
    else:
        st.header(f"📝 Minhas Tarefas ({mes_atual_str})")
        t_pesquisa_filling = st.text_input("🔍 Pesquisar tarefa (ex: QUA-1234, Bogo...)", "")
        t_exibidas = 0
        
        for t_j in tarefas_jira:
            c, s, dv_r, rs = t_j["chave"], t_j["status"], t_j.get("desenvolvedor", "Não Informado"), t_j['resumo']
            b_dados = t_j.get("base_dados", "Não informada") # Pega a base extraída

            if t_pesquisa_filling and t_pesquisa_filling.lower() not in c.lower() and t_pesquisa_filling.lower() not in dv_r.lower() and t_pesquisa_filling.lower() not in rs.lower(): continue 
            
            l_g = dados_todos_unfiltered[(dados_todos_unfiltered["Task"] == c) & (dados_todos_unfiltered["Usuario"] == usuario_atual)] if not dados_todos_unfiltered.empty else pd.DataFrame()
            if not l_g.empty and l_g.iloc[0]["Mes"] != mes_atual_str: continue 

            l_d_atual = df_mes_usuario[df_mes_usuario["Task"] == c] if not df_mes_usuario.empty else pd.DataFrame()
            j_p_neste_mes = not l_d_atual.empty

            is_dn = s in ["DONE", "PUBLISHED", "CONCLUÍDO", "ENTREGUE"]
            if not is_dn and not j_p_neste_mes: continue 
            
            t_exibidas += 1
            e_k = f"edit_{c}"
            if e_k not in st.session_state: st.session_state[e_k] = False

            with st.container(border=True):
                st.markdown(f"### [{c}]({st.session_state.jira_servidor}/browse/{c}) - {rs}")
                st.write(f"**Status:** `{s}` | **Área:** {t_j['label']} | 👨‍💻 **Dev:** `{dv_r}`")
                
                # ==========================================
                # 🔥 AQUI ENTRA A VERIFICAÇÃO VISUAL DA BASE
                # ==========================================
                if is_dn and b_dados != "Não informada":
                    st.markdown("---")
                    st.markdown("🗄️ **Inspeção Automática de Banco de Dados:**")
                    status_das_bases = verificar_status_bases(b_dados)
                    
                    for item in status_das_bases:
                        if item["status"] == "Excluida":
                            st.success(f"✅ Base **{item['base']}** foi EXCLUÍDA dos servidores.")
                        elif item["status"] == "Ativa":
                            st.error(f"⚠️ ALERTA: A base **{item['base']}** AINDA ESTÁ ATIVA nos servidores!")
                        else:
                            st.warning(f"🔌 Falha ao conectar nos servidores para verificar a base **{item['base']}**.")

                st.markdown("---")
                
                if j_p_neste_mes and not st.session_state[e_k]:
                    c_t, c_b = st.columns([0.8, 0.2])
                    c_t.success(f"✅ **Registrado** | Criados: **{int(l_d_atual['Criados'].iloc[0])}** | Sem Corr.: **{int(l_d_atual['Sem_Correcao'].iloc[0])}** | Com Corr.: **{int(l_d_atual['Com_Correcao'].iloc[0])}**")
                    if c_b.button("✏️ Editar", key=f"btn_edit_{c}", use_container_width=True, disabled=not is_dn):
                        st.session_state[e_k] = True
                        st.rerun()
                else:
                    d_cr_filling = int(l_d_atual["Criados"].iloc[0]) if j_p_neste_mes else 0
                    d_sc_filling = int(l_d_atual["Sem_Correcao"].iloc[0]) if j_p_neste_mes else 0
                    d_cc_filling = int(l_d_atual["Com_Correcao"].iloc[0]) if j_p_neste_mes else 0
                    
                    c1, c2, c3, c4 = st.columns([0.20, 0.20, 0.20, 0.40])
                    c_i = c1.number_input("Criados", min_value=0, step=1, value=d_cr_filling, key=f"cr_{c}")
                    s_i = c2.number_input("Sem Correção", min_value=0, step=1, value=d_sc_filling, key=f"sc_{c}")
                    cc_i = c3.number_input("Com Correção", min_value=0, step=1, value=d_cc_filling, key=f"cc_{c}")
                    m_ref_i = c4.selectbox("Mês Referência", [(pd.to_datetime("today") - pd.DateOffset(months=i)).strftime("%Y-%m") for i in range(3)], index=0, key=f"mes_ref_{c}")
                    
                    c_b1, c_b2 = st.columns([0.5, 0.5])
                    if c_b1.button("💾 Salvar", key=f"btn_salvar_{c}", use_container_width=True):
                        salvar_task_no_sheets(c, c_i, s_i, cc_i, m_ref_i, t_j['label'], t_j['grupo'], usuario_atual, dv_r)
                        st.session_state[e_k] = False 
                        st.rerun()
                    if st.session_state[e_k] and c_b2.button("❌ Cancelar", key=f"btn_cancel_{c}", use_container_width=True):
                        st.session_state[e_k] = False
                        st.rerun()

        if t_exibidas == 0 and not t_pesquisa_filling:
            st.balloons() 
            st.success("🎉 Sensacional! Fila zerada. Nenhuma tarefa aguardando preenchimento no momento!")

# ==========================================
# 🕵️‍♂️ ABA 2: SALA PRECISA (Mantida original)
# ==========================================
if tab_andrei:
    with tab_andrei:
        st.header("Análise Profunda e Sala Precisa dos Devs")
        st.caption("Aba exclusiva para Andrei.")
        if not dados_todos_unfiltered.empty:
            meses_dev = list(dados_todos_unfiltered["Mes"].unique())
            if mes_atual_str not in meses_dev: meses_dev.append(mes_atual_str)
            mes_dev_selecionado = st.selectbox("Selecione o Mês para Análise:", sorted(meses_dev, reverse=True))
            df_mes_dev = dados_todos_unfiltered[dados_todos_unfiltered["Mes"] == mes_dev_selecionado]
            
            st.subheader("🚀 Ranking Geral de Desenvolvedores")
            if not df_mes_dev.empty:
                df_devs_equipe = df_mes_dev.groupby(["Grupo", "Desenvolvedor"])[["Criados", "Sem_Correcao", "Com_Correcao"]].sum().reset_index()
                df_devs_equipe["Taxa de Acerto"] = (df_devs_equipe["Sem_Correcao"] / df_devs_equipe["Criados"].replace(0, 1)) * 100
                st.dataframe(df_devs_equipe.style.format({"Taxa de Acerto": "{:.1f}%"}), hide_index=True, use_container_width=True)
        else:
            st.warning("Nenhum dado registrado na nuvem.")
