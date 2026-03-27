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
import altair as alt
import io

# Configuração da Página
st.set_page_config(page_title="Portal QA 🚀", layout="wide")

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
# 🍪 LÓGICA DE LOGIN ESTILO FACEBOOK
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
st_autorefresh(interval=60000, limit=None, key="jira_refresh")

mes_atual_str = datetime.now().strftime("%Y-%m")
usuario_atual = st.session_state.jira_email

def carregar_dados_usuario():
    records = worksheet.get_all_records()
    if not records:
        return pd.DataFrame(columns=["Task", "Criados", "Sem_Correcao", "Com_Correcao", "Mes", "Label", "Grupo", "Usuario", "Desenvolvedor"])
    
    df = pd.DataFrame(records)
    df.columns = df.columns.str.strip()
    
    if "Desenvolvedor" not in df.columns:
        df["Desenvolvedor"] = "Não Informado"
        
    df_usuario = df[(df["Usuario"] == usuario_atual) & (df["Mes"] == mes_atual_str)]
    return df_usuario

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
        jql = f'assignee = currentUser() AND updated >= startOfMonth() ORDER BY updated DESC'
        issues = jira.search_issues(jql, maxResults=50)
        
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
    dados_salvos = carregar_dados_usuario()
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

# --- CABEÇALHO E LOGOUT ---
st.title(f"📊 Painel de Controle QA - Versão 2.0")

# Movemos o botão de sair para o Menu Lateral (Sidebar) para limpar o topo da tela
with st.sidebar:
    st.markdown("### Configurações da Conta")
    st.write(f"Logado como: `{usuario_atual}`")
    if st.button("🚪 Sair do Sistema", use_container_width=True):
        if isinstance(cookies, dict):
            if "jira_servidor" in cookies: cookie_manager.delete("jira_servidor", key="del_s")
            if "jira_email" in cookies: cookie_manager.delete("jira_email", key="del_e")
            if "jira_token" in cookies: cookie_manager.delete("jira_token", key="del_t")
        st.session_state.clear()
        time.sleep(1.5) 
        st.rerun()

# ==========================================
# 📈 DASHBOARDS E GRÁFICOS VISUAIS
# ==========================================

if not dados_salvos.empty:
    
    # --- PAINEL DE CONTROLE DO MÊS (FILTRO E DOWNLOAD) ---
    with st.container(border=True):
        col_tit, col_filtro, col_download = st.columns([0.4, 0.3, 0.3])
        col_tit.subheader(f"🏆 Resumo do Mês")
        
        meses_disponiveis = sorted(dados_salvos["Mes"].unique(), reverse=True)
        mes_selecionado = col_filtro.selectbox("Selecione o Mês:", meses_disponiveis, index=0, label_visibility="collapsed")

        # Filtra os dados SOMENTE para o mês selecionado
        df_mes = dados_salvos[dados_salvos["Mes"] == mes_selecionado]
        
        # Gera o Excel dinâmico do mês selecionado
        df_devs_excel = df_mes.groupby(["Grupo", "Desenvolvedor"])[["Criados", "Sem_Correcao", "Com_Correcao"]].sum().reset_index()
        df_devs_excel["Taxa de Acerto"] = (df_devs_excel["Sem_Correcao"] / df_devs_excel["Criados"].replace(0, 1)) * 100
        
        import io
        def gerar_excel_relatorio():
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_devs_excel.to_excel(writer, sheet_name='Ranking Devs', index=False)
                df_resumo_area = df_mes.groupby("Grupo")[["Criados", "Sem_Correcao", "Com_Correcao"]].sum().reset_index()
                df_resumo_area["Taxa de Acerto"] = (df_resumo_area["Sem_Correcao"] / df_resumo_area["Criados"].replace(0, 1)) * 100
                df_resumo_area.to_excel(writer, sheet_name='Resumo Área', index=False)
                df_mes.to_excel(writer, sheet_name='Dados Completos', index=False)
            return output.getvalue()

        excel_data = gerar_excel_relatorio()
        col_download.download_button(
            label="📥 Baixar Excel do Mês",
            data=excel_data,
            file_name=f"Relatorio_QA_{mes_selecionado}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

    st.write("") # Espaço para respirar
    
    df_b2b = df_mes[df_mes["Grupo"] == "B2B_CRM"]
    df_fv = df_mes[df_mes["Grupo"] == "FV_FVT_AN"]

    # --- MÉTRICAS GERAIS EM UM CARD ---
    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        total_cr = int(df_mes["Criados"].sum())
        total_sc = int(df_mes["Sem_Correcao"].sum())
        total_cc = int(df_mes["Com_Correcao"].sum())
        
        c1.metric("Total de Cenários (Geral)", total_cr)
        c2.metric("Aprovados Direto ✅", total_sc)
        c3.metric("Com Correção ⚠️", total_cc)
    
    st.write("")
    
    # --- GRÁFICOS DE DONUT (Com porcentagem por Categoria no Título!) ---
    col_graf_b2b, col_graf_fv = st.columns(2)
    
    def criar_grafico_donut(df_filtrado, titulo_base):
        if df_filtrado.empty:
            return None, titulo_base + " (Sem dados)"
        
        cr = df_filtrado["Criados"].sum()
        sc = df_filtrado["Sem_Correcao"].sum()
        cc = df_filtrado["Com_Correcao"].sum()
        
        taxa = (sc / cr * 100) if cr > 0 else 0
        titulo_com_taxa = f"{titulo_base} - {taxa:.1f}% de Acerto"
        
        source = pd.DataFrame({"Status": ["Aprovados ✅", "Com Correção ⚠️"], "Quantidade": [sc, cc]})
        chart = alt.Chart(source).mark_arc(innerRadius=40).encode(
            theta=alt.Theta(field="Quantidade", type="quantitative"),
            color=alt.Color(field="Status", type="nominal", scale=alt.Scale(domain=["Aprovados ✅", "Com Correção ⚠️"], range=["#2e7b32", "#d4a017"])),
            tooltip=['Status', 'Quantidade']
        ).properties(title=titulo_com_taxa, height=220)
        return chart

    with col_graf_b2b:
        with st.container(border=True):
            grafico_b2b = criar_grafico_donut(df_b2b, "🏢 B2B CRM")
            if grafico_b2b: st.altair_chart(grafico_b2b, use_container_width=True)
            else: st.caption("Sem dados para B2B.")

    with col_graf_fv:
        with st.container(border=True):
            grafico_fv = criar_grafico_donut(df_fv, "📱 FV - FVT - AN")
            if grafico_fv: st.altair_chart(grafico_fv, use_container_width=True)
            else: st.caption("Sem dados para FV.")

    st.write("")

    # --- RANKING DE QUALIDADE EM UM CARD ---
    with st.container(border=True):
        st.markdown("#### 👨‍💻 Ranking de Qualidade (Por Área e Desenvolvedor)")
        
        df_devs = df_mes.groupby(["Grupo", "Desenvolvedor"])[["Criados", "Sem_Correcao", "Com_Correcao"]].sum().reset_index()
        df_devs["Taxa de Acerto"] = (df_devs["Sem_Correcao"] / df_devs["Criados"].replace(0, 1)) * 100
        df_devs["Taxa de Acerto"] = df_devs["Taxa de Acerto"].fillna(0).round(1)
        
        df_devs = df_devs.rename(columns={"Grupo": "Área", "Sem_Correcao": "Sem Corr.", "Com_Correcao": "Com Corr."})
        df_devs = df_devs.sort_values(by=["Área", "Taxa de Acerto"], ascending=[True, False])
        
        st.dataframe(
            df_devs.style.format({"Taxa de Acerto": "{:.1f}%"}),
            hide_index=True, use_container_width=True
        )

else:
    st.info("📊 Os gráficos de qualidade aparecerão aqui assim que você registrar a primeira tarefa.")

st.divider()

# ==========================================
# 📝 TAREFAS E PREENCHIMENTO COM PESQUISA E UX MELHORADO
# ==========================================
st.header("📝 Tarefas para Preencher (Mês Atual)")

termo_pesquisa = st.text_input("🔍 Pesquisar tarefa (ex: QUA-1234, Felipe Bogo, Pagamento...)", "")

tarefas_exibidas = 0

if 'status_anterior' not in st.session_state:
    st.session_state.status_anterior = {}

for tarefa in tarefas_jira:
    chave, status = tarefa["chave"], tarefa["status"]
    dev_responsavel = tarefa.get("desenvolvedor", "Não Informado")
    resumo = tarefa['resumo']
    
    if termo_pesquisa:
        termo = termo_pesquisa.lower()
        if termo not in chave.lower() and termo not in dev_responsavel.lower() and termo not in resumo.lower():
            continue 
    
    linha_dado = dados_salvos[dados_salvos["Task"] == chave]
    ja_preenchido = not linha_dado.empty
    
    status_anterior = st.session_state.status_anterior.get(chave, "DESCONHECIDO")
    if status == "PUBLISHED" and status_anterior != "PUBLISHED":
        if not ja_preenchido: st.toast(f"🚀 Tarefa {chave} liberada para QA!", icon="🔔")
        else: st.toast(f"⚠️ Tarefa {chave} retornou! Revise as métricas.", icon="👀")
    st.session_state.status_anterior[chave] = status

    is_done = status in ["DONE", "PUBLISHED", "CONCLUÍDO", "ENTREGUE"]
    if not is_done and not ja_preenchido: continue 

    tarefas_exibidas += 1
    edit_key = f"edit_{chave}"
    if edit_key not in st.session_state: st.session_state[edit_key] = False

    with st.container(border=True):
        st.subheader(f"{chave} - {resumo}")
        st.write(f"**Status:** `{status}` | **Área:** {tarefa['label']} | 👨‍💻 **Dev:** `{dev_responsavel}`")

        if ja_preenchido and not st.session_state[edit_key]:
            cr, sc, cc = int(linha_dado["Criados"].iloc[0]), int(linha_dado["Sem_Correcao"].iloc[0]), int(linha_dado["Com_Correcao"].iloc[0])
            c_texto, c_botao = st.columns([0.8, 0.2])
            c_texto.success(f"✅ **Registrado** | Criados: **{cr}** | Sem Corr.: **{sc}** | Com Corr.: **{cc}**")
            
            c_botao.write("") 
            if c_botao.button("✏️ Editar", key=f"btn_edit_{chave}", use_container_width=True, disabled=not is_done):
                st.session_state[edit_key] = True
                st.rerun()

        else:
            def_cr = int(linha_dado["Criados"].iloc[0]) if ja_preenchido else 0
            def_sc = int(linha_dado["Sem_Correcao"].iloc[0]) if ja_preenchido else 0
            def_cc = int(linha_dado["Com_Correcao"].iloc[0]) if ja_preenchido else 0

            c1, c2, c3, c4 = st.columns([0.25, 0.25, 0.25, 0.25])
            
            criados_input = c1.number_input("Criados", min_value=0, step=1, value=def_cr, key=f"cr_{chave}")
            sem_corr_input = c2.number_input("Sem Correção", min_value=0, step=1, value=def_sc, key=f"sc_{chave}")
            com_corr_input = c3.number_input("Com Correção", min_value=0, step=1, value=def_cc, key=f"cc_{chave}")
            
            c4.write("") 
            c4.write("") 
            col_btn1, col_btn2 = c4.columns(2)
            
            if col_btn1.button("💾 Salvar", key=f"btn_salvar_{chave}", use_container_width=True):
                salvar_task_no_sheets(chave, criados_input, sem_corr_input, com_corr_input, mes_atual_str, tarefa['label'], tarefa['grupo'], usuario_atual, dev_responsavel)
                st.session_state[edit_key] = False 
                st.toast(f"Métricas da {chave} salvas na Nuvem!", icon="☁️")
                st.rerun()

            if st.session_state[edit_key]:
                if col_btn2.button("❌ Cancelar", key=f"btn_cancel_{chave}", use_container_width=True):
                    st.session_state[edit_key] = False
                    st.rerun()

if tarefas_exibidas == 0:
    if termo_pesquisa:
        st.warning("Nenhuma tarefa encontrada com essa pesquisa.")
    else:
        st.info("🎉 Nenhuma tarefa aguardando preenchimento no momento. Tudo limpo!")
