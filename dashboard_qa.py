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
# 🗄️ IMPORTAÇÃO DO BANCO DE DADOS
# ==========================================
try:
    import psycopg2
except ImportError:
    st.error("⚠️ Biblioteca 'psycopg2' não encontrada. Adicione 'psycopg2-binary' no seu requirements.txt")

st.set_page_config(page_title="Portal QA - Gold Edition 🏆", layout="wide")

temas_hp = {
    "🏰 Sem Casa (Padrão)": {"primaria": "#FF4B4B", "grafico_ok": "#2e7b32", "grafico_erro": "#d4a017", "img_header": "https://cdn-icons-png.flaticon.com/512/1067/1067357.png"},
    "🦁 Grifinória": {"primaria": "#ff4d4d", "grafico_ok": "#ff4d4d", "grafico_erro": "#ffc107", "img_header": "https://github.com/geovendas-andreisilveira/Dashboard-QA/blob/main/grifinoria.png?raw=true"},
    "🐍 Sonserina": {"primaria": "#4caf50", "grafico_ok": "#4caf50", "grafico_erro": "#e0e0e0", "img_header": "https://github.com/geovendas-andreisilveira/Dashboard-QA/blob/main/sonserina.png?raw=true"},
    "🦅 Corvinal": {"primaria": "#64b5f6", "grafico_ok": "#64b5f6", "grafico_erro": "#ffb300", "img_header": "https://github.com/geovendas-andreisilveira/Dashboard-QA/blob/main/corvinal.png?raw=true"},
    "🦡 Lufa-Lufa": {"primaria": "#ffd54f", "grafico_ok": "#ffd54f", "grafico_erro": "#9e9e9e", "img_header": "https://github.com/geovendas-andreisilveira/Dashboard-QA/blob/main/lufalufa.png?raw=true"}
}

# ==========================================
# ☁️ CONEXÃO SHEETS E JIRA
# ==========================================
@st.cache_resource
def conectar_google_sheets():
    creds_dict = json.loads(st.secrets["google_credentials_json"])
    gc = gspread.service_account_from_dict(creds_dict)
    return gc.open("Base_Portal_QA").worksheet("Dados")

try:
    worksheet = conectar_google_sheets()
except Exception as e:
    st.error(f"Erro no Google Sheets: {e}")
    st.stop()

def validar_credenciais_jira(servidor, email, token):
    try:
        JIRA(server=servidor, basic_auth=(email, token), max_retries=0, timeout=5).myself() 
        return True
    except Exception:
        return False

# ==========================================
# 🗄️ FUNÇÃO DE VERIFICAÇÃO DE BANCO (Sem Cache para checar na hora H)
# ==========================================
def verificar_status_bases(bases_str):
    if not bases_str or bases_str == "Não informada" or str(bases_str).strip() == "" or bases_str == "Nenhum":
        return []
    
    bases = [b.strip() for b in bases_str.replace(';', ',').split(',') if b.strip()]
    resultados = []
    servidores = ["192.168.37.20", "192.168.37.22"]
    
    user_db = st.secrets.get("db_user", "SEU_USER") 
    pass_db = st.secrets.get("db_pass", "SUA_SENHA")

    for base in bases:
        encontrada_ativa = False
        erro_conexao = False
        
        for ip in servidores:
            try:
                conn = psycopg2.connect(host=ip, port="5432", user=user_db, password=pass_db, dbname="postgres", connect_timeout=3)
                conn.autocommit = True
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (base,))
                existe = cursor.fetchone()
                cursor.close()
                conn.close()
                
                if existe:
                    encontrada_ativa = True
                    break
            except Exception:
                erro_conexao = True
        
        if encontrada_ativa:
            resultados.append({"base": base, "status": "Ativa"})
        elif erro_conexao and not encontrada_ativa:
            resultados.append({"base": base, "status": "Erro_Conexao"})
        else:
            resultados.append({"base": base, "status": "Excluida"})
            
    return resultados

# ==========================================
# ⏱️ TEMPO REAL E DADOS
# ==========================================
mes_atual_str = datetime.now().strftime("%Y-%m")

def carregar_todos_dados():
    records = worksheet.get_all_records()
    if not records:
        return pd.DataFrame(columns=["Task", "Criados", "Sem_Correcao", "Com_Correcao", "Mes", "Label", "Grupo", "Usuario", "Desenvolvedor"])
    df = pd.DataFrame(records)
    df.columns = df.columns.str.strip()
    if "Desenvolvedor" not in df.columns: df["Desenvolvedor"] = "Não Informado"
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
                    if val and hasattr(val, 'value'):
                        if any(x in str(val.value) for x in ["B2B", "CRM", "Força", "Analytics", "Têxtil"]):
                            area_encontrada = str(val.value)
                    if val and hasattr(val, 'displayName') and field_name not in ['assignee', 'creator', 'reporter']:
                        dev_encontrado = val.displayName
                    
                    # 🔍 CAPTURA A BASE DIRETAMENTE DO CAMPO DO JIRA
                    if val and isinstance(val, str) and len(str(val)) < 80:
                        val_str = str(val).lower()
                        # Procura padrões de nomes de base que vocês usam (baseado na sua print)
                        if any(x in val_str for x in ["geo", "zcalian", "zelian", "zteste", "dalari", "manatex", "fbr"]):
                            base_dados_encontrada = str(val)

            tarefas.append({
                "chave": issue.key, "resumo": issue.fields.summary,
                "status": status_atual, "label": area_encontrada, "grupo": categorizar_projeto(area_encontrada),
                "desenvolvedor": dev_encontrado,
                "base_dados": base_dados_encontrada 
            })
        return tarefas
    except Exception as e:
        return f"ERRO_AUTH: {str(e)}"

# ==========================================
# 🍪 LOGIN E SESSÃO
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
    with st.form("login_form"):
        servidor_input = st.text_input("URL do Jira", value="https://geovendas.atlassian.net")
        email_input = st.text_input("Seu E-mail do Jira")
        token_input = st.text_input("Seu Token de API", type="password")
        if st.form_submit_button("Entrar no Painel"):
            if email_input and token_input and validar_credenciais_jira(servidor_input, email_input, token_input):
                cookie_manager.set("jira_servidor", servidor_input, max_age=30*24*60*60)
                cookie_manager.set("jira_email", email_input, max_age=30*24*60*60)
                cookie_manager.set("jira_token", token_input, max_age=30*24*60*60)
                st.session_state.update({"jira_servidor": servidor_input, "jira_email": email_input, "jira_token": token_input, "jira_logado": True})
                st.rerun()
            else:
                st.error("Credenciais inválidas.")
    st.stop()

usuario_atual = st.session_state.jira_email

with st.spinner("Sincronizando tarefas e gerando gráficos..."):
    dados_todos_unfiltered = carregar_todos_dados()
    tarefas_jira = buscar_tarefas_jira_real(st.session_state.jira_servidor, st.session_state.jira_email, st.session_state.jira_token)

# ==========================================
# 🧙‍♂️ VISUAL E INTERFACE
# ==========================================
avatares = ["🧙‍♂️", "👩‍🎤", "👨‍💻", "👩‍🔬", "🤖"]
avatar_index = avatares.index(cookies.get("qa_avatar")) if cookies.get("qa_avatar") in avatares else 0
casa_index = list(temas_hp.keys()).index(cookies.get("qa_house")) if cookies.get("qa_house") in temas_hp else 0
cor_primaria = temas_hp[list(temas_hp.keys())[casa_index]]["primaria"]

st.markdown(f"""
    <style>
    div[data-testid="stMetricValue"] {{ color: {cor_primaria}; text-shadow: 0px 0px 10px {cor_primaria}80; }}
    .stButton>button {{ border-color: {cor_primaria}; color: {cor_primaria}; }}
    .stButton>button:hover {{ background-color: {cor_primaria}; color: white; box-shadow: 0px 0px 10px {cor_primaria}; }}
    </style>
    <div style="display: flex; align-items: center; gap: 20px; margin-bottom: 20px;">
        <img src="{temas_hp[list(temas_hp.keys())[casa_index]]['img_header']}" width="80">
        <h1 style="margin: 0;">Painel QA - {avatares[avatar_index]} {usuario_atual.split('@')[0].capitalize()}</h1>
    </div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### 🪄 Personalização")
    if st.radio("Seu avatar informal:", avatares, index=avatar_index, horizontal=True) != cookies.get("qa_avatar"):
         cookie_manager.set("qa_avatar", st.session_state.get('qa_avatar'), max_age=30*24*60*60); st.rerun()
    if st.selectbox("Chapéu Seletor (Tema HP):", list(temas_hp.keys()), index=casa_index) != cookies.get("qa_house"):
         cookie_manager.set("qa_house", st.session_state.get('qa_house'), max_age=30*24*60*60); st.rerun()
    st.divider()
    if st.button("🔄 Sincronizar Dados", use_container_width=True): st.rerun()

st.divider()

# ==========================================
# 📊 ABA 1: PAINEL GERAL (FILA DE TAREFAS)
# ==========================================
tab_geral = st.tabs(["📊 Painel Geral (Visão Unificada)", "🕵️‍♂️ Sala Precisa (Análise de Devs)"])[0] if "andrei" in usuario_atual else st.tabs(["📊 Painel Geral"])[0]

with tab_geral:
    st.header(f"📝 Minhas Tarefas do Mês ({mes_atual_str})")
    df_mes_usuario = dados_todos_unfiltered[(dados_todos_unfiltered["Mes"] == mes_atual_str) & (dados_todos_unfiltered["Usuario"] == usuario_atual)] if not dados_todos_unfiltered.empty else pd.DataFrame()
    t_exibidas = 0
    
    for t_j in tarefas_jira:
        c, s, dv_r, rs = t_j["chave"], t_j["status"], t_j.get("desenvolvedor", "Não Informado"), t_j['resumo']
        b_dados_jira = t_j.get("base_dados", "Não informada") # Base puxada automaticamente do Jira
        
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
            
            if b_dados_jira != "Não informada":
                st.caption(f"🗄️ *Base identificada no Jira:* `{b_dados_jira}`")

            st.markdown("---")
            
            if j_p_neste_mes and not st.session_state[e_k]:
                c_t, c_b = st.columns([0.8, 0.2])
                c_t.success(f"✅ **Métricas Salvas** | Criados: **{int(l_d_atual['Criados'].iloc[0])}** | Sem Corr.: **{int(l_d_atual['Sem_Correcao'].iloc[0])}** | Com Corr.: **{int(l_d_atual['Com_Correcao'].iloc[0])}**")
                if c_b.button("✏️ Editar", key=f"btn_edit_{c}", use_container_width=True):
                    st.session_state[e_k] = True
                    st.rerun()
            else:
                c1, c2, c3 = st.columns([0.33, 0.33, 0.34])
                c_i = c1.number_input("Criados", min_value=0, step=1, value=int(l_d_atual["Criados"].iloc[0]) if j_p_neste_mes else 0, key=f"cr_{c}")
                s_i = c2.number_input("Sem Correção", min_value=0, step=1, value=int(l_d_atual["Sem_Correcao"].iloc[0]) if j_p_neste_mes else 0, key=f"sc_{c}")
                cc_i = c3.number_input("Com Correção", min_value=0, step=1, value=int(l_d_atual["Com_Correcao"].iloc[0]) if j_p_neste_mes else 0, key=f"cc_{c}")
                
                c_b1, c_b2 = st.columns([0.5, 0.5])
                
                # O BOTÃO MÁGICO: Salva os dados e checa o banco ao mesmo tempo
                if c_b1.button("💾 Salvar", key=f"btn_salvar_{c}", use_container_width=True):
                    # 1. Salva a tarefa no Google Sheets
                    salvar_task_no_sheets(c, c_i, s_i, cc_i, mes_atual_str, t_j['label'], t_j['grupo'], usuario_atual, dv_r)
                    
                    # 2. Faz a checagem do banco de dados na hora
                    if b_dados_jira != "Não informada":
                        status_bases = verificar_status_bases(b_dados_jira)
                        
                        bases_ativas = [b['base'] for b in status_bases if b['status'] == 'Ativa']
                        falha_conexao = any(b['status'] == 'Erro_Conexao' for b in status_bases)
                        
                        if bases_ativas:
                            # Mostra o alerta (Pop-up lateral que sobe na tela)
                            st.toast(f"🚨 ALERTA: As bases {', '.join(bases_ativas)} AINDA ESTÃO ATIVAS!", icon="⚠️")
                        elif falha_conexao:
                            st.toast(f"🔌 Falha de rede: Não consegui acessar o servidor local para checar a base.", icon="📡")
                        else:
                            st.toast(f"✅ Sucesso! Bases limpas e métricas salvas.", icon="🎉")
                    else:
                        st.toast("💾 Métricas salvas! Nenhuma base detectada.", icon="✅")

                    st.session_state[e_k] = False 
                    time.sleep(2) # Pequena pausa para você conseguir ler o pop-up (Toast)
                    st.rerun()
                    
                if st.session_state[e_k] and c_b2.button("❌ Cancelar", key=f"btn_cancel_{c}", use_container_width=True):
                    st.session_state[e_k] = False
                    st.rerun()

    if t_exibidas == 0:
        st.balloons() 
        st.success("🎉 Sensacional! Fila zerada. Nenhuma tarefa aguardando preenchimento no momento!")
