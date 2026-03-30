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
import plotly.express as px # Gráficos animados
import streamlit.components.v1 as components # 🔥 Para as notificações do Windows/Mac

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
    dados_completos_usuario = dados_todos_unfiltered[dados_todos_unfiltered["Usuario"] == usuario_atual] if not dados_todos_unfiltered.empty else pd.DataFrame()
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
# 👤 AVATAR E NOME DINÂMICO
# ==========================================
avatares = ["🧙‍♂️", "👩‍🎤", "👨‍💻", "👩‍🔬", "🤖"]
cookie_avatar = cookies.get("qa_avatar")

if cookie_avatar in avatares:
    avatar_index = avatares.index(cookie_avatar)
else:
    avatar_index = 0

avatar_exibicao = avatares[avatar_index]

if "@" in usuario_atual:
    nome_exibicao = usuario_atual.split('@')[0].split('.')[0].capitalize()
else:
    nome_exibicao = "Usuário"

st.title(f"📊 Painel de Controle QA - {avatar_exibicao} {nome_exibicao}")

with st.sidebar:
    st.markdown("### Configurações de Perfil")
    
    avatar_escolhido = st.radio("Escolha seu avatar informal:", avatares, index=avatar_index, horizontal=True)
    if avatar_escolhido != cookie_avatar:
         cookie_manager.set("qa_avatar", avatar_escolhido, max_age=30*24*60*60, key="set_a")
         time.sleep(1) 
         st.rerun()

    st.divider()

    # 🔥 BOTÃO DE NOTIFICAÇÕES (NOVIDADE)
    st.markdown("### 🔔 Notificações do Sistema")
    st.caption("Ative para receber alertas no PC quando houver novas tarefas.")
    components.html("""
        <script>
        function pedirPermissao() {
            Notification.requestPermission().then(function(permission) {
                if(permission === 'granted') {
                    new Notification('✅ Tudo pronto!', {
                        body: 'O Portal QA enviará notificações por aqui!',
                        icon: 'https://cdn-icons-png.flaticon.com/512/2097/2097190.png'
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

st.divider()

# ==========================================
# 🛡️ PERMISSÕES (QUEM É O GESTOR?)
# ==========================================
emails_gestores = ["alison", "andrei"]
eh_gestor = any(gestor in usuario_atual.lower() for gestor in emails_gestores)

abas = st.tabs(["👤 Meu Painel (Tarefas e Gráficos)", "👑 Visão da Equipe (Gestão)"]) if eh_gestor else st.tabs(["👤 Meu Painel (Tarefas e Gráficos)"])
tab_pessoal = abas[0]
tab_equipe = abas[1] if eh_gestor else None

# ==========================================
# 👑 ABA 2: VISÃO DA EQUIPE (Apenas Gestores)
# ==========================================
def gerar_tabela_chefe_estilizada(df_grupo):
    if df_grupo.empty: return pd.DataFrame()
    resumo_equipe = df_grupo.groupby("Usuario")[["Criados", "Sem_Correcao", "Com_Correcao"]].sum().reset_index()
    resumo_equipe["QA Responsável"] = resumo_equipe["Usuario"].apply(lambda x: str(x).split('@')[0].split('.')[0].capitalize())
    resumo_equipe = resumo_equipe.rename(columns={"Criados": "Total Cenários Criados", "Sem_Correcao": "Aprovados (Sem Correção)", "Com_Correcao": "Aprovados (Com Correção)"})
    resumo_equipe["% Sucesso Direto"] = (resumo_equipe["Aprovados (Sem Correção)"] / resumo_equipe["Total Cenários Criados"].replace(0, 1)) * 100
    
    total_criados = resumo_equipe["Total Cenários Criados"].sum()
    total_sem = resumo_equipe["Aprovados (Sem Correção)"].sum()
    total_com = resumo_equipe["Aprovados (Com Correção)"].sum()
    taxa_total = (total_sem / total_criados * 100) if total_criados > 0 else 0
    
    linha_total_equipe = pd.DataFrame({
        "QA Responsável": ["TOTAL"], "Total Cenários Criados": [total_criados],
        "Aprovados (Sem Correção)": [total_sem], "Aprovados (Com Correção)": [total_com], "% Sucesso Direto": [taxa_total]
    })
    tabela_final = pd.concat([resumo_equipe, linha_total_equipe], ignore_index=True)
    tabela_final = tabela_final[["QA Responsável", "Total Cenários Criados", "Aprovados (Sem Correção)", "Aprovados (Com Correção)", "% Sucesso Direto"]]
    tabela_final["% Sucesso Direto"] = tabela_final["% Sucesso Direto"].fillna(0).round(1)
    return tabela_final

if tab_equipe:
    with tab_equipe:
        st.header("🏢 Visão de Produtividade da Equipe")
        if not dados_todos_unfiltered.empty:
            col_tit_g, col_filtro_g, col_download_g = st.columns([0.4, 0.3, 0.3])
            
            meses_equipe = sorted(dados_todos_unfiltered["Mes"].unique(), reverse=True)
            col_tit_g.subheader(f"📊 Resumo da Equipe")

            col_filtro_g.write("**Mês de Referência:**")
            mes_selecionado_equipe = col_filtro_g.selectbox("Selecione o Mês da Equipe:", meses_equipe, index=0, label_visibility="collapsed")

            df_mes_equipe = dados_todos_unfiltered[dados_todos_unfiltered["Mes"] == mes_selecionado_equipe]
            
            def gerar_excel_relatorio_equipe():
                output = io.BytesIO()
                writer = pd.ExcelWriter(output, engine='xlsxwriter')
                
                # Aba 1: Dados completos
                df_mes_equipe.to_excel(writer, sheet_name='Detalhes_Equipe', index=False)
                
                # Abas de Ranking QA
                tabela_gestor_fv = gerar_tabela_chefe_estilizada(df_mes_equipe[df_mes_equipe["Grupo"] == "FV_FVT_AN"])
                if not tabela_gestor_fv.empty: tabela_gestor_fv.to_excel(writer, sheet_name='Ranking_QA_FV', index=False)
                
                tabela_gestor_b2b = gerar_tabela_chefe_estilizada(df_mes_equipe[df_mes_equipe["Grupo"] == "B2B_CRM"])
                if not tabela_gestor_b2b.empty: tabela_gestor_b2b.to_excel(writer, sheet_name='Ranking_QA_B2B', index=False)
                
                # 🔥 Aba nova no Excel: Ranking de Devs da Equipe
                df_devs_equipe_excel = df_mes_equipe.groupby(["Grupo", "Desenvolvedor"])[["Criados", "Sem_Correcao", "Com_Correcao"]].sum().reset_index()
                df_devs_equipe_excel["Taxa de Acerto"] = (df_devs_equipe_excel["Sem_Correcao"] / df_devs_equipe_excel["Criados"].replace(0, 1)) * 100
                df_devs_equipe_excel = df_devs_equipe_excel.sort_values(by=["Grupo", "Taxa de Acerto"], ascending=[True, False])
                df_devs_equipe_excel.to_excel(writer, sheet_name='Ranking_Geral_Devs', index=False)

                writer.close()
                return output.getvalue()

            excel_data_equipe = gerar_excel_relatorio_equipe()
            
            col_download_g.write("**Exportar Dados:**")
            col_download_g.download_button(label="📥 Baixar Relatório da Equipe", data=excel_data_equipe, file_name=f"Relatorio_Equipe_QA_{mes_selecionado_equipe}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

            st.divider()
            
            st.subheader("📱 FV - FVT - AN (Visão Geral do Time)")
            tabela_fv = gerar_tabela_chefe_estilizada(df_mes_equipe[df_mes_equipe["Grupo"] == "FV_FVT_AN"])
            if not tabela_fv.empty: st.dataframe(tabela_fv.style.format({"% Sucesso Direto": "{:.1f}%"}), hide_index=True, use_container_width=True)
            else: st.caption("Sem dados para a equipe FV neste mês.")
                
            st.write("")
            st.subheader("🏢 B2B - CRM (Visão Geral do Time)")
            tabela_b2b = gerar_tabela_chefe_estilizada(df_mes_equipe[df_mes_equipe["Grupo"] == "B2B_CRM"])
            if not tabela_b2b.empty: st.dataframe(tabela_b2b.style.format({"% Sucesso Direto": "{:.1f}%"}), hide_index=True, use_container_width=True)
            else: st.caption("Sem dados para a equipe B2B neste mês.")
                
            st.divider()

            # --- 🔥 RANKING GERAL DE DEVS ---
            st.subheader("🚀 Ranking Geral de Desenvolvedores (Toda a Equipe)")
            st.caption("Soma de todos os cenários validados por todos os QAs neste mês, agrupados por Desenvolvedor.")
            
            if not df_mes_equipe.empty:
                df_devs_equipe = df_mes_equipe.groupby(["Grupo", "Desenvolvedor"])[["Criados", "Sem_Correcao", "Com_Correcao"]].sum().reset_index()
                df_devs_equipe["Taxa de Acerto"] = (df_devs_equipe["Sem_Correcao"] / df_devs_equipe["Criados"].replace(0, 1)) * 100
                df_devs_equipe["Taxa de Acerto"] = df_devs_equipe["Taxa de Acerto"].fillna(0).round(1)
                df_devs_equipe = df_devs_equipe.rename(columns={"Grupo": "Área", "Sem_Correcao": "Sem Corr.", "Com_Correcao": "Com Corr."})
                df_devs_equipe = df_devs_equipe.sort_values(by=["Área", "Taxa de Acerto"], ascending=[True, False])
                st.dataframe(df_devs_equipe.style.format({"Taxa de Acerto": "{:.1f}%"}), hide_index=True, use_container_width=True)

            st.divider()

            # --- 🔥 RAIO-X CIRÚRGICO POR DEV (ESTILO ACORDEÃO) ---
            st.subheader("📋 Raio-X Cirúrgico das Tarefas por Dev")
            st.caption("Clique no nome do Desenvolvedor para ver exatamente quais tarefas ele fez, quem foi o QA responsável e os detalhes de acerto.")
            
            if not df_mes_equipe.empty:
                devs_unicos = sorted(df_mes_equipe["Desenvolvedor"].unique())
                
                for dev in devs_unicos:
                    df_dev = df_mes_equipe[df_mes_equipe["Desenvolvedor"] == dev].copy()
                    
                    total_cr_dev = df_dev["Criados"].sum()
                    total_sc_dev = df_dev["Sem_Correcao"].sum()
                    total_cc_dev = df_dev["Com_Correcao"].sum()
                    taxa_final_dev = (total_sc_dev / total_cr_dev * 100) if total_cr_dev > 0 else 0
                    
                    titulo_expander = f"👨‍💻 {dev} | Acerto Final: {taxa_final_dev:.1f}% | Total de Cenários: {total_cr_dev} (✅ {total_sc_dev} Aprovados / ⚠️ {total_cc_dev} Bugs)"
                    
                    with st.expander(titulo_expander, expanded=False):
                        df_detalhe = df_dev[["Task", "Usuario", "Grupo", "Criados", "Sem_Correcao", "Com_Correcao"]].copy()
                        df_detalhe["QA Responsável"] = df_detalhe["Usuario"].apply(lambda x: str(x).split('@')[0].split('.')[0].capitalize())
                        df_detalhe["% da Task"] = (df_detalhe["Sem_Correcao"] / df_detalhe["Criados"].replace(0, 1)) * 100
                        df_detalhe = df_detalhe[["Task", "QA Responsável", "Grupo", "Criados", "Sem_Correcao", "Com_Correcao", "% da Task"]]
                        df_detalhe = df_detalhe.rename(columns={"Sem_Correcao": "Aprovados", "Com_Correcao": "Com Bug"})
                        
                        st.dataframe(df_detalhe.style.format({"% da Task": "{:.1f}%"}), hide_index=True, use_container_width=True)
            else:
                st.caption("Sem dados detalhados para exibir neste mês.")

            st.write("")
            st.info("💡 Apenas usuários com permissão de Gestor podem visualizar esta aba.")
        else:
            st.warning("Nenhum dado foi registrado na nuvem ainda.")

# ------------------------------------------
# 👤 ABA 1: MEU PAINEL
# ------------------------------------------
with tab_pessoal:
    dados_usuario_filling = dados_todos_unfiltered[dados_todos_unfiltered["Usuario"] == usuario_atual] if not dados_todos_unfiltered.empty else pd.DataFrame()

    if not dados_usuario_filling.empty:
        with st.container(border=True):
            col_tit, col_filtro, col_download = st.columns([0.4, 0.3, 0.3])
            col_tit.subheader(f"🏆 Meu Resumo")
            
            meses_disponiveis = sorted(dados_usuario_filling["Mes"].unique(), reverse=True)
            
            col_filtro.write("**Mês:**")
            mes_selecionado_usuario = col_filtro.selectbox("Selecione o Mês:", meses_disponiveis, index=0, label_visibility="collapsed")

            df_mes_usuario = dados_usuario_filling[dados_usuario_filling["Mes"] == mes_selecionado_usuario]
            
            df_devs_excel_user = df_mes_usuario.groupby(["Grupo", "Desenvolvedor"])[["Criados", "Sem_Correcao", "Com_Correcao"]].sum().reset_index()
            df_devs_excel_user["Taxa de Acerto"] = (df_devs_excel_user["Sem_Correcao"] / df_devs_excel_user["Criados"].replace(0, 1)) * 100
            
            def gerar_excel_relatorio_usuario():
                output = io.BytesIO()
                writer = pd.ExcelWriter(output, engine='xlsxwriter')
                df_mes_usuario.to_excel(writer, sheet_name='Cenários Detalhados', index=False)
                df_devs_excel_user.to_excel(writer, sheet_name='Ranking Devs', index=False)
                df_resumo_area_user = df_mes_usuario.groupby("Grupo")[["Criados", "Sem_Correcao", "Com_Correcao"]].sum().reset_index()
                df_resumo_area_user["Taxa de Acerto"] = (df_resumo_area_user["Sem_Correcao"] / df_resumo_area_user["Criados"].replace(0, 1)) * 100
                df_resumo_area_user.to_excel(writer, sheet_name='Resumo Área', index=False)
                writer.close() 
                return output.getvalue()

            excel_data_usuario = gerar_excel_relatorio_usuario()
            
            col_download.write("**Relatório:**")
            col_download.download_button(label="📥 Baixar Meu Excel", data=excel_data_usuario, file_name=f"Relatorio_{nome_exibicao}_{mes_selecionado_usuario}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

        st.write("") 
        df_b2b_usuario = df_mes_usuario[df_mes_usuario["Grupo"] == "B2B_CRM"]
        df_fv_usuario = df_mes_usuario[df_mes_usuario["Grupo"] == "FV_FVT_AN"]

        c1, c2, c3 = st.columns(3)
        total_cr_u = int(df_mes_usuario["Criados"].sum())
        total_sc_u = int(df_mes_usuario["Sem_Correcao"].sum())
        total_cc_u = int(df_mes_usuario["Com_Correcao"].sum())
        
        c1.metric("Total de Cenários (Geral)", total_cr_u)
        c2.metric("Aprovados Direto ✅", total_sc_u)
        c3.metric("Com Correção ⚠️", total_cc_u)
        
        st.write("")
        col_graf_b2b_u, col_graf_fv_u = st.columns(2)
        
        def criar_grafico_donut_animado(df_filtrado, titulo_base):
            if df_filtrado.empty: return None 
            cr = df_filtrado["Criados"].sum()
            sc = df_filtrado["Sem_Correcao"].sum()
            cc = df_filtrado["Com_Correcao"].sum()
            taxa = (sc / cr * 100) if cr > 0 else 0
            
            df_plot = pd.DataFrame({"Status": ["Aprovados ✅", "Com Correção ⚠️"], "Quantidade": [sc, cc]})
            fig = px.pie(df_plot, values='Quantidade', names='Status', hole=0.6,
                         color='Status', color_discrete_map={"Aprovados ✅": "#2e7b32", "Com Correção ⚠️": "#d4a017"})
            
            fig.update_layout(
                title_text=f"<b>{titulo_base}</b><br><span style='font-size:14px; color:gray;'>{taxa:.1f}% de Acerto</span>",
                title_x=0.5, margin=dict(t=60, b=20, l=20, r=20), showlegend=False,
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)"
            )
            fig.update_traces(textposition='inside', textinfo='percent+label', hoverinfo='label+value',
                              marker=dict(line=dict(color='#1E1E1E', width=2)))
            return fig

        with col_graf_b2b_u:
            with st.container(border=True):
                g_b2b_u = criar_grafico_donut_animado(df_b2b_usuario, "🏢 Desempenho B2B")
                if g_b2b_u is not None: st.plotly_chart(g_b2b_u, use_container_width=True)
                else: st.caption("Sem dados de B2B para você neste mês.")

        with col_graf_fv_u:
            with st.container(border=True):
                g_fv_u = criar_grafico_donut_animado(df_fv_usuario, "📱 Desempenho FV")
                if g_fv_u is not None: st.plotly_chart(g_fv_u, use_container_width=True)
                else: st.caption("Sem dados de FV para você neste mês.")

        st.write("")

        with st.container(border=True):
            st.markdown("#### 👨‍💻 Meu Ranking de Qualidade (Por Área e Desenvolvedor)")
            if not df_mes_usuario.empty:
                df_devs_user = df_mes_usuario.groupby(["Grupo", "Desenvolvedor"])[["Criados", "Sem_Correcao", "Com_Correcao"]].sum().reset_index()
                df_devs_user["Taxa de Acerto"] = (df_devs_user["Sem_Correcao"] / df_devs_user["Criados"].replace(0, 1)) * 100
                df_devs_user["Taxa de Acerto"] = df_devs_user["Taxa de Acerto"].fillna(0).round(1)
                df_devs_user = df_devs_user.rename(columns={"Grupo": "Área", "Sem_Correcao": "Sem Corr.", "Com_Correcao": "Com Corr."})
                df_devs_user = df_devs_user.sort_values(by=["Área", "Taxa de Acerto"], ascending=[True, False])
                st.dataframe(df_devs_user.style.format({"Taxa de Acerto": "{:.1f}%"}), hide_index=True, use_container_width=True)
            else:
                st.caption("Sem dados suficientes para gerar seu ranking neste mês.")

        st.write("")
        hoje = datetime.now()
        ultimo_dia = calendar.monthrange(hoje.year, hoje.month)[1]
        dias_para_fim = ultimo_dia - hoje.day
        
        if dias_para_fim <= 5 and mes_selecionado_usuario == mes_atual_str:
            with st.popover("🚨 Fechar Mês e Enviar Relatório ao Gestor"):
                st.markdown(f"Faltam **{dias_para_fim} dias** para fechar {mes_selecionado_usuario}.")
                t_g = (total_sc_u / total_cr_u * 100) if total_cr_u > 0 else 0
                assunto = f"Relatório QA - {nome_exibicao} ({mes_selecionado_usuario})"
                corpo = f"Olá Gestor, tudo bem?\n\nSegue o relatório dos meus testes de {mes_selecionado_usuario}.\n\n📊 Resumo:\nCriados: {total_cr_u}\nAprovados: {total_sc_u}\nErros: {total_cc_u}\nAcerto: {t_g:.1f}%\n\nO Excel completo está em anexo.\nAbraços,\n{nome_exibicao}"
                assunto_url = urllib.parse.quote(assunto)
                corpo_url = urllib.parse.quote(corpo)
                mailto_link = f"mailto:?subject={assunto_url}&body={corpo_url}"
                st.markdown(f'<a href="{mailto_link}" style="display: block; text-align: center; padding: 0.5em 1em; color: white; background-color: #FF4B4B; border-radius: 0.3em; text-decoration: none; font-weight: bold;">📧 Abrir E-mail</a>', unsafe_allow_html=True)
                st.caption("Dica: Baixe seu Excel acima e anexe no e-mail.")
    else:
        st.info("📊 Os gráficos de qualidade aparecerão aqui assim que você registrar a primeira tarefa.")

    st.divider()

    # --- CARDS DE TAREFAS (PESSOAL) ---
    if not dados_usuario_filling.empty and mes_selecionado_usuario != mes_atual_str:
        with st.expander(f"🗄️ Clique aqui para abrir o Histórico de {mes_selecionado_usuario}", expanded=False):
            st.caption("Você está visualizando o arquivo morto. Tarefas de meses passados não podem ser editadas por aqui.")
            t_pesquisa_h = st.text_input(f"🔍 Pesquisar no histórico de {mes_selecionado_usuario}...", "")
            if df_mes_usuario.empty:
                st.info(f"Nenhum dado foi salvo no mês de {mes_selecionado_usuario}.")
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
                        st.success(f"Registrado em {mes_selecionado_usuario} | Criados: **{row['Criados']}** | Sem Corr.: **{row['Sem_Correcao']}** | Com Corr.: **{row['Com_Correcao']}**")
    else:
        st.header(f"📝 Minhas Tarefas para Preencher ({mes_atual_str})")
        t_pesquisa_filling = st.text_input("🔍 Pesquisar tarefa (ex: QUA-1234, Felipe Bogo, Pagamento...)", "")
        t_exibidas = 0
        if 'status_anterior' not in st.session_state: st.session_state.status_anterior = {}
        
        d_salvos_mes_atual = dados_usuario_filling[dados_usuario_filling["Mes"] == mes_atual_str] if not dados_usuario_filling.empty else pd.DataFrame()

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

            l_d_atual = d_salvos_mes_atual[d_salvos_mes_atual["Task"] == c] if not d_salvos_mes_atual.empty else pd.DataFrame()
            j_p_neste_mes = not l_d_atual.empty

            # 🔥 O DISPARO DA NOTIFICAÇÃO NATIVA (WINDOWS/MAC) OCORRE AQUI!
            s_ant = st.session_state.status_anterior.get(c, "DESCONHECIDO")
            if s == "PUBLISHED" and s_ant != "PUBLISHED":
                if not j_p_neste_mes: 
                    st.toast(f"🚀 Tarefa {c} liberada para QA!", icon="🔔")
                    icone_url = "https://cdn-icons-png.flaticon.com/512/2097/2097190.png"
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
