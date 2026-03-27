# 🚀 Portal de Controle QA 

Bem-vindos ao novo Portal de Controle QA! 🎉 
Demos adeus ao preenchimento manual de planilhas e à caça interminável de tarefas no Jira. Este portal foi desenvolvido para automatizar a coleta de métricas de qualidade, gerar dashboards interativos e consolidar a produtividade do nosso time em tempo real.

---

## 🛠️ Como Acessar (Primeiro Login)

O sistema utiliza a API do Jira para puxar as suas tarefas automaticamente. Para entrar, você precisa gerar um **Token de API pessoal** (não use a sua senha normal de login da empresa).

1. Acesse o seu Jira no navegador.
2. Vá em **Configurações da Conta** (Account Settings) > **Segurança** (Security) > **Criar e gerenciar tokens de API**.
3. Clique em **Criar token de API**, dê um nome (ex: "Portal QA") e copie o código gerado.
4. Acesse o [Link do nosso Portal QA] e preencha:
   * **URL do Jira:** `https://geovendas.atlassian.net` (Padrão)
   * **Seu E-mail:** O mesmo e-mail que você usa no Jira.
   * **Token de API:** O código que você acabou de copiar.
   * *Dica:* Deixe a caixa "Lembrar de mim" marcada. O sistema usa *cookies* seguros e vai manter você logado por 30 dias.

---

## 📊 Como Funciona o "Meu Painel"

Assim que você logar, cairá no seu painel pessoal. Os dados aqui são **seus** e ninguém mais da equipe (exceto a gestão) tem acesso a eles.

### 1. Resumo do Mês e Gráficos
Você verá o total de cenários testados no mês, divididos entre **Aprovados Direto** (sem bugs) e **Com Correção** (com retornos). Os gráficos de rosca (animados) separam a sua performance por área (B2B e FV) e também geram o seu Ranking de Qualidade pessoal.
* **Baixar Meu Excel:** A qualquer momento, clique no botão de download para gerar um `.xlsx` detalhado com todos os seus cenários para backup próprio.

### 2. Preenchimento de Tarefas (A Mágica)
O sistema lê automaticamente o seu Jira e exibe cards com todas as tarefas que você moveu para os status finais (`DONE`, `PUBLISHED`, `CONCLUÍDO`, etc.) **a partir de 01/03/2026**.

**Como registrar:**
* Preencha os campos `Criados`, `Sem Correção` e `Com Correção`.
* **⚠️ Atenção ao Mês de Referência:** O sistema sugere o mês atual, mas se você estiver preenchendo uma tarefa atrasada (ex: fechou em Março, mas está preenchendo dia 02 de Abril), **mude o seletor para o mês correto** antes de salvar!
* Clique em **💾 Salvar Métricas**. A tarefa sumirá da sua tela de pendências e irá para a nuvem.

*Nota técnica (Edge Cases):* Se o gestor reabrir a tarefa e você fechá-la de novo no Jira, **ela não aparecerá duplicada** na sua tela. O sistema cruza os dados com o nosso banco em nuvem (Google Sheets) para blindar as suas métricas contra duplicidade.

### 3. Máquina do Tempo (Arquivo Morto)
Esqueceu quantos bugs achou mês passado? Basta ir no seletor de mês lá no topo e escolher um mês anterior (ex: `2026-02`). A tela vai se transformar no modo de leitura (Arquivo Morto). Suas tarefas salvas vão aparecer bloqueadas, mas com links diretos para o Jira caso queira consultar o escopo.

---

## 🚨 Fechamento de Mês Automatizado

Nos últimos 5 dias do mês, um botão flutuante vermelho aparecerá na tela: **"🚨 Fechar Mês e Enviar Relatório ao Gestor"**.

1. Certifique-se de que zerou a sua fila de tarefas (a tela tem que soltar balões! 🎈).
2. Clique no botão de Baixar Excel do seu painel.
3. Clique no botão flutuante e depois em **"📧 Abrir E-mail"**.
4. O seu Outlook/Gmail vai abrir sozinho com o texto mastigado e as métricas calculadas. Basta anexar o Excel e enviar!

*(Importante: Caso o e-mail abra uma aba em branco no navegador, configure o seu Windows/Mac para associar links `mailto:` ao seu aplicativo de e-mail favorito).*

---

## 👑 Modo Gestor (Visão da Equipe)

Se o seu e-mail tiver permissão de Gestão (Alison/Andrei), uma segunda aba chamada **"Visão da Equipe (Gestão)"** aparecerá no topo do site.

* Esta aba **substitui a antiga planilha manual do Excel**.
* Ela compila automaticamente os dados de todos os QAs logados no sistema (Carla, Pablo, Andrei, Alison) e gera a tabela de resultados da equipe inteira.
* O gestor pode filtrar por meses anteriores e exportar o "Relatório da Equipe" em um clique. Tudo em tempo real.

---
*Dúvidas, sugestões ou bugs? Fale com o Andrei Silveira* 🚀
