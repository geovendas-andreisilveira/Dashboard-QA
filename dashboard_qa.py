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

# Configuração da Página
st.set_page_config(page_title="Portal QA 🚀", layout="wide")

# ==========================================
# ☁️ CONEXÃO COM O GOOGLE SHEETS
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

# ==========================================
# 🛡️ FUNÇÃO DE VALIDAÇÃO DO JIRA (O Segurança)
# ==========================================
def validar_credenciais_jira(servidor, email, token):
    try:
        # max_retries=0 e timeout=5 impedem o sistema de travar se o token for falso
        jira = JIRA(server=servidor, basic_auth=(email, token), max_retries=0, timeout=5)
        jira.myself() # Tenta bater no servidor para ver quem é você
        return True
    except Exception:
        return False # Se der qualquer erro (token falso, sem internet), ele barra.

# ==========================================
# 🍪 GERENCIADOR DE COOKIES E LOGIN
# ==========================================
cookie_manager = stx.CookieManager()
cookies = cookie_manager.get_all()

if cookies:
    cookie_email = cookies.get("jira_email")
    cookie_token = cookies.get("jira_token")
    cookie_servidor = cookies.get("jira_servidor")

    if cookie_email and cookie_token and 'jira_logado' not in st.session_state:
        # 🔥 A VACINA DO COOKIE: Tira qualquer aspas invisível do começo ou fim
        st.session_state.jira_servidor = str(cookie_servidor).strip('"')
        st.session_state.jira_email = str(cookie_email).strip('"')
        st.session_state.jira_token = str(cookie_token).strip('"')
        st.session_state.jira_logado = True
        st.rerun()

# Se NÃO estiver logado, mostra a tela de Login
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
                # 🔥 MÁGICA 1: Spinner de carregamento visual
                with st.spinner("Validando suas credenciais no Jira... Aguarde."):
                    # 🔥 MÁGICA 2: Valida ANTES de salvar o cookie
                    if validar_credenciais_jira(servidor_input, email_input, token_input):
                        if lembrar:
                            cookie_manager.set("jira_servidor", servidor_input, max_age=30*24*60*60, key="set_s")
                            cookie_manager.set("jira_email", email_input, max_age=30*24*60*60, key="set_e")
                            cookie_manager.set("jira_token", token_input, max_age=30*24*60*60, key="set_t")
                            time.sleep(0.5) 
                        
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
# ⏱️ TEMPO REAL (Atualiza a cada 60s)
# ==========================================
st_autorefresh(interval=60000, limit=None, key="jira_refresh")

# ==========================================
# ⚙️ FUNÇÕES DE DADOS
# ==========================================
mes_atual_str = datetime.now().strftime("%Y-%m")
usuario_atual = st.session_state.jira_email

def carregar_dados_usuario():
    records = worksheet.get_all_records()
    if not records:
        return pd.DataFrame(columns=["Task", "Criados", "Sem_Correcao", "Com_Correcao", "Mes", "Label", "Grupo", "Usuario"])
    
    df = pd.DataFrame(records)
    df.columns = df.columns.str.strip()
    df_usuario = df[(df["Usuario"] == usuario_atual) & (df["Mes"] == mes_atual_str)]
    return df_usuario

def salvar_task_no_sheets(task, criados, sem_c, com_c, mes, label, grupo, usuario):
    records = worksheet.get_all_records()
    df = pd.DataFrame(records)
    
    row_idx = None
    if not df.empty and "Task" in df.columns:
        match = df[(df["Task"] == task) & (df["Usuario"] == usuario)]
        if not match.empty:
            row_idx = match.index[0] + 2 
            
    nova_linha = [task, criados, sem_c, com_c, mes, label, grupo, usuario]
    
    if row_idx:
        worksheet.update(f"A{row_idx}:H{row_idx}", [nova_linha])
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
        # Aumentei o timeout para 15s pra dar tempo de respirar se o Jira tiver lento
        jira = JIRA(server=servidor, basic_auth=(email, token), max_retries=1, timeout=15)
        jql = f'assignee = currentUser() AND updated >= startOfMonth() ORDER BY updated DESC'
        issues = jira.search_issues(jql, maxResults=50)
        
        tarefas = []
        for issue in issues:
            if getattr(issue.fields.issuetype, 'subtask', False): continue
            status_atual = str(issue.fields.status).upper()
            area_encontrada = "Desconhecida"
            
            for field_name in dir(issue.fields):
                if field_name.startswith("customfield_"):
                    val = getattr(issue.fields, field_name)
                    if val and hasattr(val, 'value'):
                        if any(x in str(val.value) for x in ["B2B", "CRM", "Força", "Analytics", "Têxtil"]):
                            area_encontrada = str(val.value)
                            break
            tarefas.append({
                "chave": issue.key, "resumo": issue.fields.summary,
                "status": status_atual, "label": area_encontrada, "grupo": categorizar_projeto(area_encontrada)
            })
        return tarefas
    except Exception as e:
        # 🔥 Agora ele devolve o erro REAL do Jira pra gente saber o que aconteceu
        return f"ERRO_AUTH: {str(e)}"

# Mostra o spinner visual de carregamento
with st.spinner("Sincronizando tarefas com o Jira..."):
    dados_salvos = carregar_dados_usuario()
    tarefas_jira = buscar_tarefas_jira_real(st.session_state.jira_servidor, st.session_state.jira_email, st.session_state.jira_token)

# Se o Jira rejeitou a conexão ou deu timeout
if isinstance(tarefas_jira, str) and tarefas_jira.startswith("ERRO_AUTH"):
    if isinstance(cookies, dict):
        if "jira_servidor" in cookies: cookie_manager.delete("jira_servidor", key="auto_err_s")
        if "jira_email" in cookies: cookie_manager.delete("jira_email", key="auto_err_e")
        if "jira_token" in cookies: cookie_manager.delete("jira_token", key="auto_err_t")
    
    for key in list(st.session_state.keys()): del st.session_state[key]
    
    time.sleep(0.5)
    # 🔥 Exibe na tela o MOTIVO exato do erro!
    st.error(f"⚠️ Não foi possível conectar ao Jira. \nDetalhe do Erro: {tarefas_jira}")
    st.stop()

# --- CABEÇALHO E LOGOUT ---
col_titulo, col_sair = st.columns([0.85, 0.15])
col_titulo.title(f"📊 Painel de Controle QA")

if col_sair.button("🚪 Sair", use_container_width=True):
    # Trava de segurança: só tenta apagar o cookie se ele realmente existir!
    if isinstance(cookies, dict):
        if "jira_servidor" in cookies: cookie_manager.delete("jira_servidor", key="del_s")
        if "jira_email" in cookies: cookie_manager.delete("jira_email", key="del_e")
        if "jira_token" in cookies: cookie_manager.delete("jira_token", key="del_t")
    
    # Limpa a memória da sessão do Python
    for key in list(st.session_state.keys()): del st.session_state[key]
    
    time.sleep(0.5)
    st.rerun()

# ==========================================
# 📊 DASHBOARDS DO MÊS
# ==========================================
if not dados_salvos.empty:
    df_b2b = dados_salvos[dados_salvos["Grupo"] == "B2B_CRM"]
    df_fv = dados_salvos[dados_salvos["Grupo"] == "FV_FVT_AN"]
else:
    df_b2b = df_fv = pd.DataFrame()

st.header(f"🏆 Visão Geral ({mes_atual_str})")
c1, c2, c3 = st.columns(3)
c1.metric("Total de Cenários", int(dados_salvos["Criados"].sum()) if not dados_salvos.empty else 0)
c2.metric("Aprovados (Direto) ✅", int(dados_salvos["Sem_Correcao"].sum()) if not dados_salvos.empty else 0)
c3.metric("Aprovados (Com Correção) ⚠️", int(dados_salvos["Com_Correcao"].sum()) if not dados_salvos.empty else 0)
st.divider()

col_esq, col_dir = st.columns(2)
with col_esq:
    st.subheader("🏢 B2B - CRM")
    if not df_b2b.empty: st.write(f"**Criados:** {int(df_b2b['Criados'].sum())} | **Sem Corr:** {int(df_b2b['Sem_Correcao'].sum())} | **Com Corr:** {int(df_b2b['Com_Correcao'].sum())}")
    else: st.caption("Nenhum cenário salvo neste mês.")
with col_dir:
    st.subheader("📱 FV - FVT - AN")
    if not df_fv.empty: st.write(f"**Criados:** {int(df_fv['Criados'].sum())} | **Sem Corr:** {int(df_fv['Sem_Correcao'].sum())} | **Com Corr:** {int(df_fv['Com_Correcao'].sum())}")
    else: st.caption("Nenhum cenário salvo neste mês.")
st.divider()

# ==========================================
# 📝 TAREFAS E NOTIFICAÇÕES WEB
# ==========================================
st.header("📝 Tarefas para Preencher")
tarefas_exibidas = 0

if 'status_anterior' not in st.session_state:
    st.session_state.status_anterior = {}

for tarefa in tarefas_jira:
    chave, status = tarefa["chave"], tarefa["status"]
    linha_dado = dados_salvos[dados_salvos["Task"] == chave]
    ja_preenchido = not linha_dado.empty
    
    status_anterior = st.session_state.status_anterior.get(chave, "DESCONHECIDO")
    if status == "PUBLISHED" and status_anterior != "PUBLISHED":
        if not ja_preenchido: st.toast(f"🚀 **{chave} Publicada!** Preencha as métricas.", icon="🔔")
        else: st.toast(f"⚠️ **{chave} republicada!** Realize alterações se preciso!", icon="👀")
    st.session_state.status_anterior[chave] = status

    is_done = status in ["DONE", "PUBLISHED", "CONCLUÍDO", "ENTREGUE"]
    if not is_done and not ja_preenchido: continue 

    tarefas_exibidas += 1
    edit_key = f"edit_{chave}"
    if edit_key not in st.session_state: st.session_state[edit_key] = False

    with st.container(border=True):
        st.subheader(f"{chave} - {tarefa['resumo']}")
        st.write(f"**Status no Jira:** `{status}` | **Área:** {tarefa['label']} ({tarefa['grupo']})")

        if ja_preenchido and not st.session_state[edit_key]:
            cr, sc, cc = int(linha_dado["Criados"].iloc[0]), int(linha_dado["Sem_Correcao"].iloc[0]), int(linha_dado["Com_Correcao"].iloc[0])
            c_texto, c_botao = st.columns([0.8, 0.2])
            c_texto.success(f"✅ **Registrado** | Criados: **{cr}** | Sem Correção: **{sc}** | Com Correção: **{cc}**")
            if c_botao.button("✏️ Editar", key=f"btn_edit_{chave}", use_container_width=True, disabled=not is_done):
                st.session_state[edit_key] = True
                st.rerun()

        else:
            def_cr = int(linha_dado["Criados"].iloc[0]) if ja_preenchido else 0
            def_sc = int(linha_dado["Sem_Correcao"].iloc[0]) if ja_preenchido else 0
            def_cc = int(linha_dado["Com_Correcao"].iloc[0]) if ja_preenchido else 0

            c1, c2, c3, c4 = st.columns(4)
            criados_input = c1.number_input("Criados", min_value=0, step=1, value=def_cr, key=f"cr_{chave}")
            sem_corr_input = c2.number_input("Sem Correção", min_value=0, step=1, value=def_sc, key=f"sc_{chave}")
            com_corr_input = c3.number_input("Com Correção", min_value=0, step=1, value=def_cc, key=f"cc_{chave}")
            
            st.write("") 
            col_btn1, col_btn2 = c4.columns(2)
            
            if col_btn1.button("💾 Salvar", key=f"btn_salvar_{chave}", use_container_width=True):
                salvar_task_no_sheets(chave, criados_input, sem_corr_input, com_corr_input, mes_atual_str, tarefa['label'], tarefa['grupo'], usuario_atual)
                st.session_state[edit_key] = False 
                st.toast(f"Métricas da {chave} salvas na Nuvem!", icon="☁️")
                st.rerun()

            if st.session_state[edit_key]:
                if col_btn2.button("❌ Cancelar", key=f"btn_cancel_{chave}", use_container_width=True):
                    st.session_state[edit_key] = False
                    st.rerun()

if tarefas_exibidas == 0:
    st.info("🎉 Nenhuma tarefa aguardando preenchimento no momento. Tudo limpo!")
