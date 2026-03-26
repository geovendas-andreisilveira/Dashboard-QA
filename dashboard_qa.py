import streamlit as st
import pandas as pd
from datetime import datetime
import calendar
from jira import JIRA
from streamlit_autorefresh import st_autorefresh
import extra_streamlit_components as stx
import json
import os

# Configuração da Página
st.set_page_config(page_title="Portal QA 🚀", layout="wide")

# ==========================================
# 🍪 GERENCIADOR DE COOKIES (Lembrar Login)
# ==========================================
cookie_manager = stx.CookieManager()

# Tenta ler o cookie salvo no navegador
cookie_servidor = cookie_manager.get(cookie="jira_servidor")
cookie_email = cookie_manager.get(cookie="jira_email")
cookie_token = cookie_manager.get(cookie="jira_token")

# Se tiver cookie, joga pra sessão e loga automático!
if cookie_email and cookie_token and 'jira_logado' not in st.session_state:
    st.session_state.jira_servidor = cookie_servidor
    st.session_state.jira_email = cookie_email
    st.session_state.jira_token = cookie_token
    st.session_state.jira_logado = True

# ==========================================
# 🔐 TELA DE LOGIN
# ==========================================
if 'jira_logado' not in st.session_state:
    st.title("🔐 Login - Portal QA")
    st.write("Bem-vindo! Insira suas credenciais do Jira para acessar o painel de cenários.")
    
    with st.form("login_form"):
        servidor_input = st.text_input("URL do Jira", value="https://geovendas.atlassian.net")
        email_input = st.text_input("Seu E-mail do Jira")
        token_input = st.text_input("Seu Token de API", type="password")
        lembrar = st.checkbox("Lembrar de mim por 30 dias", value=True)
        submit = st.form_submit_button("Entrar no Painel")
        
        if submit:
            if email_input and token_input:
                if lembrar:
                    # Grava os cookies no navegador por 30 dias
                    cookie_manager.set("jira_servidor", servidor_input, max_age=30*24*60*60)
                    cookie_manager.set("jira_email", email_input, max_age=30*24*60*60)
                    cookie_manager.set("jira_token", token_input, max_age=30*24*60*60)
                
                st.session_state.jira_servidor = servidor_input
                st.session_state.jira_email = email_input
                st.session_state.jira_token = token_input
                st.session_state.jira_logado = True
                st.rerun()
            else:
                st.error("Preencha o e-mail e o token para continuar.")
    st.stop() # Trava aqui até logar!

# ==========================================
# ⏱️ TEMPO REAL (Atualiza a cada 60s)
# ==========================================
st_autorefresh(interval=60000, limit=None, key="jira_refresh")

# ==========================================
# ☁️ BANCO DE DADOS (Google Sheets Fake p/ agora, CSV real p/ teste)
# ==========================================
# NOTA PARA A NUVEM: Quando configurarmos o Google Sheets, vamos trocar isso!
ARQUIVO_DADOS = f'cenarios_{st.session_state.jira_email}.csv' 

def carregar_dados():
    if os.path.exists(ARQUIVO_DADOS):
        return pd.read_csv(ARQUIVO_DADOS)
    return pd.DataFrame(columns=["Task", "Criados", "Sem_Correcao", "Com_Correcao", "Mes", "Label", "Grupo"])

def salvar_dados(df):
    df.to_csv(ARQUIVO_DADOS, index=False)

def categorizar_projeto(nome_projeto):
    if not nome_projeto: return "OUTROS"
    nome_upper = str(nome_projeto).upper()
    if "B2B" in nome_upper or "CRM" in nome_upper: return "B2B_CRM"
    elif "FORÇA" in nome_upper or "ANALYTICS" in nome_upper or "FV" in nome_upper or "TÊXTIL" in nome_upper: return "FV_FVT_AN"
    else: return "OUTROS"

# ==========================================
# 🔌 CONEXÃO JIRA
# ==========================================
@st.cache_data(ttl=55) 
def buscar_tarefas_jira_real(servidor, email, token):
    try:
        jira = JIRA(server=servidor, basic_auth=(email, token))
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
        st.error("Erro de credenciais do Jira. Deslogue e tente novamente.")
        return []

dados_salvos = carregar_dados()
tarefas_jira = buscar_tarefas_jira_real(st.session_state.jira_servidor, st.session_state.jira_email, st.session_state.jira_token)

# --- CABEÇALHO E LOGOUT ---
col_titulo, col_sair = st.columns([0.85, 0.15])
col_titulo.title(f"📊 Painel de Controle QA")

if col_sair.button("🚪 Sair", use_container_width=True):
    # Limpa os cookies
    cookie_manager.delete("jira_servidor")
    cookie_manager.delete("jira_email")
    cookie_manager.delete("jira_token")
    for key in list(st.session_state.keys()): del st.session_state[key]
    st.rerun()

# ==========================================
# 📊 DASHBOARDS
# ==========================================
if not dados_salvos.empty:
    df_b2b = dados_salvos[dados_salvos["Grupo"] == "B2B_CRM"]
    df_fv = dados_salvos[dados_salvos["Grupo"] == "FV_FVT_AN"]
else:
    df_b2b = df_fv = pd.DataFrame()

st.header("🏆 Visão Geral do Mês")
c1, c2, c3 = st.columns(3)
c1.metric("Total de Cenários", int(dados_salvos["Criados"].sum()) if not dados_salvos.empty else 0)
c2.metric("Aprovados (Direto) ✅", int(dados_salvos["Sem_Correcao"].sum()) if not dados_salvos.empty else 0)
c3.metric("Aprovados (Com Correção) ⚠️", int(dados_salvos["Com_Correcao"].sum()) if not dados_salvos.empty else 0)

st.divider()

col_esq, col_dir = st.columns(2)
with col_esq:
    st.subheader("🏢 B2B - CRM")
    if not df_b2b.empty: st.write(f"**Criados:** {int(df_b2b['Criados'].sum())} | **Sem Corr:** {int(df_b2b['Sem_Correcao'].sum())} | **Com Corr:** {int(df_b2b['Com_Correcao'].sum())}")
    else: st.caption("Nenhum cenário salvo.")
with col_dir:
    st.subheader("📱 FV - FVT - AN")
    if not df_fv.empty: st.write(f"**Criados:** {int(df_fv['Criados'].sum())} | **Sem Corr:** {int(df_fv['Sem_Correcao'].sum())} | **Com Corr:** {int(df_fv['Com_Correcao'].sum())}")
    else: st.caption("Nenhum cenário salvo.")

st.divider()

# ==========================================
# 📝 TAREFAS E NOTIFICAÇÕES WEB
# ==========================================
st.header("📝 Tarefas para Preencher")
tarefas_exibidas = 0
mes_atual_str = datetime.now().strftime("%Y-%m")

if 'status_anterior' not in st.session_state:
    st.session_state.status_anterior = {}

for tarefa in tarefas_jira:
    chave, status = tarefa["chave"], tarefa["status"]
    linha_dado = dados_salvos[dados_salvos["Task"] == chave]
    ja_preenchido = not linha_dado.empty
    
    # 🔔 Notificações Nativas do Site (Sem depender do Windows)
    status_anterior = st.session_state.status_anterior.get(chave, "DESCONHECIDO")
    if status == "PUBLISHED" and status_anterior != "PUBLISHED":
        if not ja_preenchido:
            st.toast(f"🚀 **{chave} Publicada!** Preencha as métricas.", icon="🔔")
        else:
            st.toast(f"⚠️ **{chave} republicada!** Realize alterações se preciso!", icon="👀")
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
                dados_salvos = dados_salvos[dados_salvos["Task"] != chave]
                novo_dado = pd.DataFrame([{"Task": chave, "Criados": criados_input, "Sem_Correcao": sem_corr_input, "Com_Correcao": com_corr_input, "Mes": mes_atual_str, "Label": tarefa['label'], "Grupo": tarefa['grupo']}])
                dados_atualizados = pd.concat([dados_salvos, novo_dado], ignore_index=True)
                salvar_dados(dados_atualizados) # Salva
                st.session_state[edit_key] = False 
                st.toast(f"Métricas da {chave} salvas com sucesso!", icon="✅")
                st.rerun()

            if st.session_state[edit_key]:
                if col_btn2.button("❌ Cancelar", key=f"btn_cancel_{chave}", use_container_width=True):
                    st.session_state[edit_key] = False
                    st.rerun()

if tarefas_exibidas == 0:
    st.info("🎉 Nenhuma tarefa aguardando preenchimento no momento. Tudo limpo!")