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
    "🗡️ Lufa-Lufa": {
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
@st.cache_data(ttl=60) # Cache reduzido para 1 min para checagem rápida de deleção
def verificar_status_bases(bases_str):
    if not bases_str or bases_str == "Não informada" or str(bases_str).strip() == "" or bases_str == "Nenhum":
        return []
    
    bases = [b.strip() for b in bases_str.replace(';', ',').split(',') if b.strip()]
    resultados = []
    servidores = ["192.168.37.20", "192.168.37.22"]
    
    user_db = st.secrets.get("db_user", "SEU_USUARIO_POSTGRES") 
    pass_db = st.secrets.get("db_pass", "SUA_SENHA_POSTGRES")

    for base in bases:
        encontrada_ativa = False
        erro_conexao = False
        
        for ip in servidores:
            try:
                conn = psycopg2.connect(host=ip, port="5432", user=user_db, password=pass_db, dbname="postgres", connect_timeout=2)
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
# ⏱️ TEMPO REAL E DADOS (MAPEAMENTO DE 11 COLUNAS)
# ==========================================
mes_atual_str = datetime.now().strftime("%Y-%m")
usuario_atual = st.session_state.jira_email

def carregar_todos_dados():
    records = worksheet.get_all_records()
    if not records:
        return pd.DataFrame(columns=["Task", "Criados", "Sem_Correcao", "Com_Correcao", "Mes", "Label", "Grupo", "Usuario", "Desenvolvedor", "Base_Dev", "Base_QA"])
    df = pd.DataFrame(records)
    df.columns = df.columns.str.strip()
    
    # Garante retrocompatibilidade se as colunas novas não existirem na planilha antiga
    if "Desenvolvedor" not in df.columns: df["Desenvolvedor"] = "Não Informado"
    if "Base_Dev" not in df.columns: df["Base_Dev"] = "Não informada"
    if "Base_QA" not in df.columns: df["Base_QA"] = "Não informada"
    return df

def salvar_task_no_sheets(task, criados, sem_c, com_c, mes, label, grupo, usuario, desenvolvedor, base_dev, base_qa):
    records = worksheet.get_all_records()
    df = pd.DataFrame(records)
    row_idx = None
    if not df.empty and "Task" in df.columns:
        match = df[(df["Task"] == task) & (df["Usuario"] == usuario)]
        if not match.empty:
            row_idx = match.index[0] + 2 
            
    nova_linha = [task, criados, sem_c, com_c, mes, label, grupo, usuario, desenvolvedor, base_dev, base_qa]
    
    if row_idx:
        worksheet.update(f"A{row_idx}:K{row_idx}", [nova_linha]) # Atualiza as 11 colunas de A até K
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
                    
                    # FILTRO AMPLIADO: Captura qualquer padrão de string que lembre nomenclatura de base de dados
                    if val and isinstance(val, str) and val != "Nenhum":
                        val_str = str(val).lower()
                        if any(x in val_str for x in ["geo", "zcalian", "zteste", "dalari", "manatex", "malaria", "fbr", "kyly"]):
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
# 🍪 COOKIES E INICIALIZAÇÃO DE FLUXO
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
        lembrar = st.checkbox("Lembrar de mim por 30 dias", value=True)
        if st.form_submit_button("Entrar no Painel"):
            if email_input and token_input:
                if validar_credenciais_jira(servidor_input, email_input, token_input):
                    if lembrar:
                        cookie_manager.set("jira_servidor", servidor_input, max_age=30*24*60*60, key="set_s")
                        cookie_manager.set("jira_email", email_input, max_age=30*24*60*60, key="set_e")
                        cookie_manager.set("jira_token", token_input, max_age=30*24*60*60, key="set_t")
                    st.session_state.jira_servidor = servidor_input
                    st.session_state.jira_email = email_input
                    st.session_state.jira_token = token_input
                    st.session_state.jira_logado = True
                    st.rerun()
    st.stop()

with st.spinner("Sincronizando tarefas e gerando gráficos..."):
    dados_todos_unfiltered = carregar_todos_dados()
    tarefas_jira = buscar_tarefas_jira_real(st.session_state.jira_servidor, st.session_state.jira_email, st.session_state.jira_token)

# ==========================================
# 🧙‍♂️ CUSTOMIZAÇÃO VISUAL HOGWARTS
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

st.markdown(f"""
    <div style="display: flex; align-items: center; gap: 20px; margin-bottom: 20px;">
        <img src="{temas_hp[list(temas_hp.keys())[casa_index]]['img_header']}" width="80" class="magia-flutuante">
        <h1 style="margin: 0; padding: 0;">Painel QA - {avatar_exibicao} {nome_exibicao}</h1>
    </div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### 🪄 Personalização")
    if st.radio("Seu avatar informal:", avatares, index=avatar_index, horizontal=True) != cookie_avatar:
         cookie_manager.set("qa_avatar", st.session_state.get('qa_avatar'), max_age=30*24*60*60, key="set_a")
         st.rerun()
    if st.selectbox("Chapéu Seletor (Tema HP):", list(temas_hp.keys()), index=casa_index) != cookie_house:
         cookie_manager.set("qa_house", st.session_state.get('qa_house'), max_age=30*24*60*60, key="set_h")
         st.rerun()
    st.divider()
    if st.button("🔄 Sincronizar Dados", use_container_width=True): st.rerun()

st.divider()

# ==========================================
# 🛡️ ABAS E GERENCIAMENTO DE EXIBIÇÃO
# ==========================================
eh_andrei = "andrei.silveira" in usuario_atual.lower()
abas = st.tabs(["📊 Painel Geral (Visão Unificada)", "🕵️‍♂️ Sala Precisa (Análise de Devs)"]) if eh_andrei else st.tabs(["📊 Painel Geral (Visão Unificada)"])
tab_geral = abas[0]

def renderizar_status_banco_visual(titulo, base_nome):
    if not base_nome or base_nome == "Não informada":
        return
    st.caption(f"**{titulo}:** `{base_nome}`")
    status_list = verificar_status_bases(base_nome)
    for item in status_list:
        if item["status"] == "Excluida":
            st.success(f"🗑️ Base `{item['base']}` foi limpa/excluída com sucesso.")
        elif item["status"] == "Ativa":
            st.error(f"⚠️ ATENÇÃO: A base `{item['base']}` ainda está ATIVA no servidor!")
        else:
            st.warning(f"🔌 Sem resposta do servidor local para a base `{item['base']}`. Certifique-se de rodar o painel localmente.")

# ==========================================
# 📊 ABA 1: PAINEL GERAL E HISTÓRICO COMPLETO
# ==========================================
with tab_geral:
    with st.container(border=True):
        col_filtro, col_excel_meu, col_excel_equipe = st.columns([0.4, 0.3, 0.3])
        meses_disponiveis = sorted(list(dados_todos_unfiltered["Mes"].unique()) if not dados_todos_unfiltered.empty else [mes_atual_str], reverse=True)
        mes_selecionado = col_filtro.selectbox("Selecione o Mês:", meses_disponiveis, index=0)
        df_mes_equipe = dados_todos_unfiltered[dados_todos_unfiltered["Mes"] == mes_selecionado]
        df_mes_usuario = df_mes_equipe[df_mes_equipe["Usuario"] == usuario_atual]
        
    st.markdown(f"### 🏆 Meu Resumo ({mes_selecionado})")
    c1, c2, c3 = st.columns(3)
    c1.metric("Total de Cenários (Meus)", int(df_mes_usuario["Criados"].sum()) if not df_mes_usuario.empty else 0)
    c2.metric("Aprovados Direto ✅", int(df_mes_usuario["Sem_Correcao"].sum()) if not df_mes_usuario.empty else 0)
    c3.metric("Com Correção ⚠️", int(df_mes_usuario["Com_Correcao"].sum()) if not df_mes_usuario.empty else 0)

    st.divider()

    # --- HISTÓRICO DE MESES ANTERIORES COM INSPEÇÃO AUTOMÁTICA ---
    if mes_selecionado != mes_atual_str:
        with st.expander(f"🗄️ Histórico Completo de Tarefas e Bancos de {mes_selecionado}", expanded=True):
            t_pesquisa_h = st.text_input("🔍 Pesquisar no histórico...", "")
            if not df_mes_usuario.empty:
                for idx, row in df_mes_usuario.iterrows():
                    ch, dv, rs = row["Task"], row["Desenvolvedor"], row.get("Resumo", "Tarefa do Histórico")
                    b_dev_h, b_qa_h = row.get("Base_Dev", "Não informada"), row.get("Base_QA", "Não informada")
                    
                    if t_pesquisa_h and t_pesquisa_h.lower() not in ch.lower() and t_pesquisa_h.lower() not in dv.lower(): continue
                    
                    with st.container(border=True):
                        st.markdown(f"### ✅ [{ch}]({st.session_state.jira_servidor}/browse/{ch})")
                        st.write(f"👨‍💻 **Dev:** `{dv}` | Registrado em: `{mes_selecionado}`")
                        st.info(f"📊 Criados: **{row['Criados']}** | Sem Corr.: **{row['Sem_Correcao']}** | Com Corr.: **{row['Com_Correcao']}**")
                        
                        # Monitoramento do histórico
                        if b_dev_h != "Não informada" or b_qa_h != "Não informada":
                            st.markdown("🔍 **Status Atual das Bases Desta Task:**")
                            renderizar_status_banco_visual("Base informada pelo Dev", b_dev_h)
                            renderizar_status_banco_visual("Sua Base de Teste (QA)", b_qa_h)
    else:
        # --- FILA ATUAL DE TRABALHO ---
        st.header(f"📝 Minhas Tarefas do Mês ({mes_atual_str})")
        t_pesquisa_filling = st.text_input("🔍 Pesquisar tarefa ativa...", "")
        t_exibidas = 0
        
        for t_j in tarefas_jira:
            c, s, dv_r, rs = t_j["chave"], t_j["status"], t_j.get("desenvolvedor", "Não Informado"), t_j['resumo']
            base_dev_detectada = t_j.get("base_dados", "Não informada")

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
                
                # Exibição em tempo real das bases ativas/excluídas
                if is_dn:
                    st.markdown("---")
                    st.markdown("🗄️ **Inspeção de Banco de Dados (Tempo Real):**")
                    
                    b_dev_atual = str(l_d_atual['Base_Dev'].iloc[0]) if j_p_neste_mes else base_dev_detectada
                    b_qa_atual = str(l_d_atual['Base_QA'].iloc[0]) if j_p_neste_mes else f"zandreis-{c.lower()}"
                    
                    renderizar_status_banco_visual("Base de Desenvolvimento (Dev)", b_dev_atual)
                    renderizar_status_banco_visual("Sua Base de Teste (QA / QUA)", b_qa_atual)

                st.markdown("---")
                
                if j_p_neste_mes and not st.session_state[e_k]:
                    c_t, c_b = st.columns([0.8, 0.2])
                    c_t.success(f"✅ **Métricas Salvas** | Criados: **{int(l_d_atual['Criados'].iloc[0])}** | Sem Corr.: **{int(l_d_atual['Sem_Correcao'].iloc[0])}** | Com Corr.: **{int(l_d_atual['Com_Correcao'].iloc[0])}**")
                    if c_b.button("✏️ Editar", key=f"btn_edit_{c}", use_container_width=True):
                        st.session_state[e_k] = True
                        st.rerun()
                else:
                    # Modo de Inserção / Edição das métricas e das bases
                    c1, c2, c3, c4 = st.columns([0.15, 0.15, 0.15, 0.55])
                    c_i = c1.number_input("Criados", min_value=0, step=1, value=int(l_d_atual["Criados"].iloc[0]) if j_p_neste_mes else 0, key=f"cr_{c}")
                    s_i = c2.number_input("Sem Correção", min_value=0, step=1, value=int(l_d_atual["Sem_Correcao"].iloc[0]) if j_p_neste_mes else 0, key=f"sc_{c}")
                    cc_i = c3.number_input("Com Correção", min_value=0, step=1, value=int(l_d_atual["Com_Correcao"].iloc[0]) if j_p_neste_mes else 0, key=f"cc_{c}")
                    m_ref_i = c4.selectbox("Mês Referência", [mes_atual_str], index=0, key=f"mes_ref_{c}")
                    
                    # NOVOS CAMPOS: Validação e input manual das duas bases antes de salvar permanentemente
                    col_b1, col_b2 = st.columns(2)
                    b_dev_input = col_b1.text_input("Confirmar Nome da Base do DEV", value=str(l_d_atual['Base_Dev'].iloc[0]) if j_p_neste_mes else base_dev_detectada, key=f"inp_bdev_{c}")
                    b_qa_input = col_b2.text_input("Seu Nome de Base de Teste (QA / QUA / Andrei)", value=str(l_d_atual['Base_QA'].iloc[0]) if j_p_neste_mes else f"zandreis-{c.lower()}", key=f"inp_bqa_{c}")
                    
                    c_b1, c_b2 = st.columns([0.5, 0.5])
                    if c_b1.button("💾 Salvar Registro Completo", key=f"btn_salvar_{c}", use_container_width=True):
                        salvar_task_no_sheets(c, c_i, s_i, cc_i, m_ref_i, t_j['label'], t_j['grupo'], usuario_atual, dv_r, b_dev_input, b_qa_input)
                        st.session_state[e_k] = False 
                        st.rerun()
                    if st.session_state[e_k] and c_b2.button("❌ Cancelar", key=f"btn_cancel_{c}", use_container_width=True):
                        st.session_state[e_k] = False
                        st.rerun()

        if t_exibidas == 0 and not t_pesquisa_filling:
            st.balloons() 
            st.success("🎉 Sensacional! Fila zerada. Nenhuma tarefa aguardando preenchimento no momento!")
