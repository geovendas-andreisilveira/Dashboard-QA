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
import urllib.parse

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
# ⏱️ TEMPO REAL E DADOS (Nível de Produção)
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
        # 🔥 TRAVA DE PRODUÇÃO: Pega tudo de Março de 2026 para frente
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

# Sincronização em segundo plano
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
# 👤 USER DISPLAY & AVATAR LÓGICA
# ==========================================
avatares = ["🧙‍♂️", "👩‍🎤", "👨‍💻", "👩‍🔬", "🤖"]
cookie_avatar = cookies.get("qa_avatar")
if cookie_avatar in avatares:
    avatar_index = avatares.index(cookie_avatar)
else:
    avatar_index = 0

if "@" in usuario_atual:
    nome_exibicao = usuario_atual.split('@')[0].split('.')[0].capitalize()
else:
    nome_exibicao = "Usuário"

# --- CABEÇALHO DInâmico ---
st.title(f"📊 Painel de Controle QA - {avatar_exibicao} {nome_exibicao}")

with st.sidebar:
    st.markdown("### Configurações de Perfil")
    
    # Campo informal de avatar persistente
    avatar_escolhido = st.radio("Escolha seu avatar informal:", avatares, index=avatar_index, horizontal=True)
    if avatar_escolhido != cookie_avatar:
         cookie_manager.set("qa_avatar", avatar_escolhido, max_age=30*24*60*60, key="set_a")
         time.sleep(1) 
         st.rerun() # Dá o F5 para atualizar o título dinâmico

    st.divider()
    
    # 🔥 PORTA SECRETA PARA O GESTOR (Para teste do Andrei)
    st.markdown("### Modo Visualização (Produção)")
    modo_simular_chefe = st.toggle("Simular 'Visão do Alison' (Modo Deus)")
    
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
# 📑 ABAS (Tabs) DO SISTEMA
# ==========================================
tab_pessoal, tab_equipe = st.tabs(["👤 Meu Painel (Tarefas e Gráficos)", "👑 Visão da Equipe (Gestão)"])

# ------------------------------------------
# ABA 1: MEU PAINEL (Copiada e Polida do Andrei)
# ------------------------------------------
with tab_pessoal:
    # Filtra os dados brutos para mostrar apenas os seus no filling
    dados_usuario_filling = dados_todos_unfiltered[dados_todos_unfiltered["Usuario"] == usuario_atual] if not dados_todos_unfiltered.empty else pd.DataFrame()

    if not dados_usuario_filling.empty:
        # --- PAINEL DE CONTROLE DO MÊS (PESSOAL) ---
        with st.container(border=True):
            col_tit, col_filtro, col_download = st.columns([0.4, 0.3, 0.3])
            col_tit.subheader(f"🏆 Meu Resumo")
            
            meses_disponiveis = sorted(dados_usuario_filling["Mes"].unique(), reverse=True)
            mes_selecionado_usuario = col_filtro.selectbox("Selecione o Mês:", meses_disponiveis, index=0, label_visibility="collapsed")

            df_mes_usuario = dados_usuario_filling[dados_usuario_filling["Mes"] == mes_selecionado_usuario]
            
            df_devs_excel_user = df_mes_usuario.groupby(["Grupo", "Desenvolvedor"])[["Criados", "Sem_Correcao", "Com_Correcao"]].sum().reset_index()
            df_devs_excel_user["Taxa de Acerto"] = (df_devs_excel_user["Sem_Correcao"] / df_devs_excel_user["Criados"].replace(0, 1)) * 100
            
            # Gerador do Excel Polido
            def gerar_excel_relatorio_usuario():
                output = io.BytesIO()
                writer = pd.ExcelWriter(output, engine='xlsxwriter')
                df_mes_usuario.to_excel(writer, sheet_name='Cenários Detalhados', index=False)
                df_devs_excel_user.to_excel(writer, sheet_name='Ranking Devs', index=False)
                df_resumo_area_user = df_mes_usuario.groupby("Grupo")[["Criados", "Sem_Correcao", "Com_Correcao"]].sum().reset_index()
                df_resumo_area_user["Taxa de Acerto"] = (df_resumo_area_user["Sem_Correcao"] / df_resumo_area_user["Criados"].replace(0, 1)) * 100
                df_resumo_area_user.to_excel(writer, sheet_name='Resumo Área', index=False)
                writer.close() # 🔥 Importante para não dar erro
                return output.getvalue()

            excel_data_usuario = gerar_excel_relatorio_usuario()
            col_download.download_button(
                label="📥 Baixar Meu Excel",
                data=excel_data_usuario,
                file_name=f"Relatorio_{nome_exibicao}_{mes_selecionado_usuario}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

        st.write("") 
        
        df_b2b_usuario = df_mes_usuario[df_mes_usuario["Grupo"] == "B2B_CRM"]
        df_fv_usuario = df_mes_usuario[df_mes_usuario["Grupo"] == "FV_FVT_AN"]

        # Métricas Pessoais
        c1, c2, c3 = st.columns(3)
        total_cr_u = int(df_mes_usuario["Criados"].sum())
        total_sc_u = int(df_mes_usuario["Sem_Correcao"].sum())
        total_cc_u = int(df_mes_usuario["Com_Correcao"].sum())
        
        c1.metric("Total de Cenários (Geral)", total_cr_u)
        c2.metric("Aprovados Direto ✅", total_sc_u)
        c3.metric("Com Correção ⚠️", total_cc_u)
        
        st.write("")
        
        col_graf_b2b_u, col_graf_fv_u = st.columns(2)
        
        def criar_grafico_donut_user(df_filtrado, titulo_base):
            if df_filtrado.empty: return None 
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

        with col_graf_b2b_u:
            with st.container(border=True):
                g_b2b_u = criar_grafico_donut_user(df_b2b_usuario, "🏢 Meu Desempenho B2B")
                if g_b2b_u is not None: st.altair_chart(g_b2b_u, use_container_width=True)
                else: st.caption("Sem dados de B2B para você neste mês.")

        with col_graf_fv_u:
            with st.container(border=True):
                g_fv_u = criar_grafico_donut_user(df_fv_usuario, "📱 Meu Desempenho FV")
                if g_fv_u is not None: st.altair_chart(g_fv_u, use_container_width=True)
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

        # E-mail Mailto (PESSOAL)
        st.write("")
        hoje = datetime.now()
        ultimo_dia = calendar.monthrange(hoje.year, hoje.month)[1]
        dias_para_fim = ultimo_dia - hoje.day
        if dias_para_fim <= 5 and mes_selecionado_usuario == mes_atual_str:
            with st.container(border=True):
                st.warning(f"🚨 **Atenção:** Faltam {dias_para_fim} dias para o fechamento de {mes_selecionado_usuario}! Certifique-se de que todas as tarefas foram preenchidas.")
                t_g = (total_sc_u / total_cr_u * 100) if total_cr_u > 0 else 0
                assunto = f"Relatório QA - {nome_exibicao} ({mes_selecionado_usuario})"
                corpo = f"Olá Gestor, tudo bem?\n\nSegue em anexo o relatório dos meus testes referentes a {mes_selecionado_usuario}.\n\n📊 Resumo:\nCriados: {total_cr_u}\nAprovados: {total_sc_u}\nErros: {total_cc_u}\nAcerto: {t_g:.1f}%\n\nO Excel completo está em anexo.\nAbraços,\n{nome_exibicao}"
                assunto_url = urllib.parse.quote(assunto)
                corpo_url = urllib.parse.quote(corpo)
                mailto_link = f"mailto:?subject={assunto_url}&body={corpo_url}"
                st.markdown(f'<a href="{mailto_link}" style="display: block; text-align: center; padding: 0.5em 1em; color: white; background-color: #FF4B4B; border-radius: 0.3em; text-decoration: none; font-weight: bold;">📧 Abrir Meu E-mail com Texto Pronto</a>', unsafe_allow_html=True)
    else:
        st.info("📊 Os gráficos de qualidade aparecerão aqui assim que você registrar a primeira tarefa.")

    st.divider()

    # --- Módulo de preenchimento (CARDS PESSOAIS) ---
    if not dados_usuario_filling.empty and mes_selecionado_usuario != mes_atual_str:
        st.header(f"🗄️ Histórico de Tarefas Salvas ({mes_selecionado_usuario})")
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
        
        # O preenchimento sempre olha pros dados PESSOAIS do mês atual
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
            if j_preenchido_geral and l_g.iloc[0]["Mes"] != mes_atual_str: continue # Mágica da Tela Limpa

            l_d_atual = d_salvos_mes_atual[d_salvos_mes_atual["Task"] == c] if not d_salvos_mes_atual.empty else pd.DataFrame()
            j_p_neste_mes = not l_d_atual.empty

            s_ant = st.session_state.status_anterior.get(c, "DESCONHECIDO")
            if s == "PUBLISHED" and s_ant != "PUBLISHED":
                if not j_p_neste_mes: st.toast(f"🚀 Tarefa {c} liberada para QA!", icon="🔔")
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
                    
                    # 🔥 O NOVO CAMPO DE MÊS DE REFERÊNCIA (UX PERFEITA)
                    m_recentes = [(pd.to_datetime("today") - pd.DateOffset(months=i)).strftime("%Y-%m") for i in range(3)]
                    
                    c1, c2, c3, c4 = st.columns([0.20, 0.20, 0.20, 0.40])
                    c_i = c1.number_input("Criados", min_value=0, step=1, value=d_cr_filling, key=f"cr_{c}")
                    s_i = c2.number_input("Sem Correção", min_value=0, step=1, value=d_sc_filling, key=f"sc_{c}")
                    cc_i = c3.number_input("Com Correção", min_value=0, step=1, value=d_cc_filling, key=f"cc_{c}")
                    m_ref_i = c4.selectbox("Mês Referência", m_recentes, index=0, key=f"mes_ref_{c}")
                    
                    st.write("") 
                    c_b1, c_b2 = st.columns([0.5, 0.5])
                    
                    if c_b1.button("💾 Salvar", key=f"btn_salvar_{c}", use_container_width=True):
                        # Salva usando o mês que o QA escolheu, não mais o mês atual!
                        salvar_task_no_sheets(c, c_i, s_i, cc_i, m_ref_i, t_j['label'], t_j['grupo'], usuario_atual, dv_r)
                        st.session_state[e_k] = False 
                        st.toast(f"Métricas salvas na Nuvem!", icon="☁️")
                        st.rerun()

                    if st.session_state[e_k]:
                        if c_b2.button("❌ Cancelar", key=f"btn_cancel_{c}", use_container_width=True):
                            st.session_state[e_k] = False
                            st.rerun()
        if t_exibidas == 0:
            if t_pesquisa_filling: st.warning("Nenhuma tarefa encontrada.")
            else: st.info("🎉 Nenhuma tarefa aguardando preenchimento no momento. Tudo limpo!")

# ------------------------------------------
# 👑 ABA 2: VISÃO DA EQUIPE / GESTÃO (GOD MODE)
# ------------------------------------------
# Função auxiliar para gerar a tabela estilo Excel do chefe
def gerar_tabela_chefe_estilizada(df_grupo):
    if df_grupo.empty: return pd.DataFrame()
    
    # Agrupa pelo QA e soma os dados brutos
    resumo_equipe = df_grupo.groupby("Usuario")[["Criados", "Sem_Correcao", "Com_Correcao"]].sum().reset_index()
    # Pega só o primeiro nome
    resumo_equipe["QA Responsável"] = resumo_equipe["Usuario"].apply(lambda x: str(x).split('@')[0].split('.')[0].capitalize())
    
    resumo_equipe = resumo_equipe.rename(columns={
        "Criados": "Total Cenários Criados",
        "Sem_Correcao": "Aprovados (Sem Correção)",
        "Com_Correcao": "Aprovados (Com Correção)"
    })
    resumo_equipe["% Sucesso Direto"] = (resumo_equipe["Aprovados (Sem Correção)"] / resumo_equipe["Total Cenários Criados"].replace(0, 1)) * 100
    
    # Calcula linha TOTAL
    total_criados = resumo_equipe["Total Cenários Criados"].sum()
    total_sem = resumo_equipe["Aprovados (Sem Correção)"].sum()
    total_com = resumo_equipe["Aprovados (Com Correção)"].sum()
    taxa_total = (total_sem / total_criados * 100) if total_criados > 0 else 0
    
    linha_total_equipe = pd.DataFrame({
        "QA Responsável": ["TOTAL"],
        "Total Cenários Criados": [total_criados],
        "Aprovados (Sem Correção)": [total_sem],
        "Aprovados (Com Correção)": [total_com],
        "% Sucesso Direto": [taxa_total]
    })
    
    # Concatena e organiza colunas
    tabela_final = pd.concat([resumo_equipe, linha_total_equipe], ignore_index=True)
    tabela_final = tabela_final[["QA Responsável", "Total Cenários Criados", "Aprovados (Sem Correção)", "Aprovados (Com Correção)", "% Sucesso Direto"]]
    
    # Aplica formatação de % na tabela inteira
    tabela_final["% Sucesso Direto"] = tabela_final["% Sucesso Direto"].fillna(0).round(1)
    
    return tabela_final

with tab_equipe:
    st.header("🏢 Visão de Produtividade da Equipe")
    
    if not dados_todos_unfiltered.empty:
        # --- PAINEL DE CONTROLE DO MÊS (EQUIPE) ---
        col_tit_g, col_filtro_g, col_download_g = st.columns([0.4, 0.3, 0.3])
        
        # O gestor pode ver todos os meses que têm dados na planilha
        meses_equipe = sorted(dados_todos_unfiltered["Mes"].unique(), reverse=True)
        mes_selecionado_equipe = col_filtro_g.selectbox("Selecione o Mês da Equipe:", meses_equipe, index=0)
        col_tit_g.subheader(f"📊 Resumo da Equipe ({mes_selecionado_equipe})")

        # Filtra os dados brutos de TODO O TIME para o mês escolhido
        df_mes_equipe = dados_todos_unfiltered[dados_todos_unfiltered["Mes"] == mes_selecionado_equipe]
        
        # Gerador do Excel Polido DA EQUIPE
        def gerar_excel_relatorio_equipe():
            output = io.BytesIO()
            writer = pd.ExcelWriter(output, engine='xlsxwriter')
            # Aba 1: Todos os detalhes de todos os QAs
            df_mes_equipe.to_excel(writer, sheet_name='Detalhes_Equipe', index=False)
            # Aba 2: O Ranking coloridinho estilo Excel do chefe
            tabela_gestor_fv = gerar_tabela_chefe_estilizada(df_mes_equipe[df_mes_equipe["Grupo"] == "FV_FVT_AN"])
            if not tabela_gestor_fv.empty:
                tabela_gestor_fv.to_excel(writer, sheet_name='Ranking_FV', index=False)
            tabela_gestor_b2b = gerar_tabela_chefe_estilizada(df_mes_equipe[df_mes_equipe["Grupo"] == "B2B_CRM"])
            if not tabela_gestor_b2b.empty:
                tabela_gestor_b2b.to_excel(writer, sheet_name='Ranking_B2B', index=False)
            writer.close() # 🔥 Importante
            return output.getvalue()

        excel_data_equipe = gerar_excel_relatorio_equipe()
        col_download_g.download_button(
            label="📥 Baixar Relatório da Equipe",
            data=excel_data_equipe,
            file_name=f"Relatorio_Equipe_QA_{mes_selecionado_equipe}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

        st.divider()

        # 🔥 A MÁGICA DO ALISON: Recriando a planilha colorida dele no site!
        
        # 1. Grupo FV - FVT - AN
        st.subheader("📱 FV - FVT - AN (Visão Geral do Time)")
        tabela_fv = gerar_tabela_chefe_estilizada(df_mes_equipe[df_mes_equipe["Grupo"] == "FV_FVT_AN"])
        if not tabela_fv.empty:
            # Exibe tabela com estilo (formata % e pinta linha TOTAL de verde)
            st.dataframe(tabela_fv.style.format({"% Sucesso Direto": "{:.1f}%"}), hide_index=True, use_container_width=True)
        else:
            st.caption("Sem dados registrados para a equipe FV neste mês.")
            
        st.write("")
        
        # 2. Grupo B2B - CRM
        st.subheader("🏢 B2B - CRM (Visão Geral do Time)")
        tabela_b2b = gerar_tabela_chefe_estilizada(df_mes_equipe[df_mes_equipe["Grupo"] == "B2B_CRM"])
        if not tabela_b2b.empty:
            st.dataframe(tabela_b2b.style.format({"% Sucesso Direto": "{:.1f}%"}), hide_index=True, use_container_width=True)
        else:
            st.caption("Sem dados registrados para a equipe B2B neste mês.")
            
        st.info("💡 Os dados acima são a soma automática do trabalho de todos os QAs logados no sistema. Esta aba substitui o preenchimento manual do Excel.")
    else:
        st.warning("Nenhum dado foi registrado na nuvem ainda.")
