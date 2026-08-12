# Manual do Usuário — Nutrição Hospitalar

**São Geraldo Service**  
Módulo: Nutrição Hospitalar  
Público: nutricionistas, equipe de produção, almoxarifado e suporte  
Documento impresso/amigável (este Markdown serve para impressão em PDF pelo navegador ou Word)

---

## Como imprimir este manual

1. Abra o arquivo no Cursor/VS Code ou converta para PDF.
2. No navegador: abrir o `.md` renderizado → **Ctrl+P** → Destino PDF, margens padrão.
3. Use cabeçalho/rodapé com “São Geraldo Service — Nutrição Hospitalar”.

> **Placeholder de captura:** em cada capítulo, o bloco *“O que você vê”* descreve a tela para que a equipe de treinamento possa inserir prints reais depois.

---

## 1. Introdução e acesso

### 1.1 O que este sistema faz

Centraliza o **mapa de produção do dia**, cadastros (pacientes, clínicas, dietas, cardápios, preços), estoque, etiquetas, totalizações e faturamento da nutrição hospitalar.

### 1.2 Como iniciar o aplicativo

1. No servidor/estação, execute o atalho **`iniciar_meuapp.bat`** (na pasta do projeto).
2. O script verifica o MySQL, usa o Python do `.venv` e abre o navegador.
3. Endereços comuns:
   - **HTTP:** `http://127.0.0.1/` (porta 80)
   - **HTTPS:** `https://127.0.0.1/` (porta 443; se ocupada, pode usar 8443)

### 1.3 Login

1. Na tela de login, informe usuário e senha da plataforma.
2. Após o login, você chega ao hub **Sistemas**.
3. Clique no cartão/atalho **Nutrição** (ou use a barra Sistemas · Chamados · **Nutrição**).

**URL direta do módulo:** `http://127.0.0.1/nutricao`

### 1.4 Sair

Use **Logout** na área de conta da plataforma (quando disponível na tela) ou feche a sessão conforme procedimento interno.

---

## 2. Visão geral do menu

O menu lateral esquerdo (ícone ☰ no celular) contém:

| Item | Uso principal |
|---|---|
| Sistemas | Volta ao hub de sistemas |
| **Mapa de Refeições** | Operação do dia (Mapa de Produção) |
| **Cadastro** ▸ | Submenu com pacientes, clínicas, enfermarias, leitos, dietas, grupos, tipos, cardápios, preços, nutricional, dietas líquidas, produtos, fornecedores, etiquetas |
| Estoque | Produtos, unidades, alertas, fornecedores |
| Análise de Custos | Relatórios de custo |
| Mapa U.M.A. | Totalização UMA / impressão |
| Impressão de Etiquetas | Gerar etiquetas do mapa |
| Totalização de Dietas | Totais para produção |
| Faturamento | Relatórios financeiros do período |
| Administração | Usuários do contexto nutricional |
| Auditoria | Módulo de auditoria da plataforma |

Logo e marca: **São Geraldo Service** — tagline *Transformando vidas* — rótulo **Nutrição Hospitalar**.

---

## 3. Mapa de Produção (operação do dia)

### 3.1 O que você vê

- Título **MAPA DE PRODUÇÃO**.
- Campo de busca (leito, prontuário, nome, dieta).
- Filtros **Clínica** e **Enfermaria**.
- Seletor de data (setas ← →).
- Botão **Inserir paciente**.
- Tabela larga com scroll: colunas Adm, Leito, Pront, Nome, Idade, Diagnóstico, Dieta, OBS, flags **D C A M J C**, Saída, observação de etiqueta, Extras, Suplementos, Enteral, Fórmula Infantil, LVE, datas de inclusão/alteração, Motivo, Ações.

**Screenshot placeholder:** *[Inserir print do mapa filtrado por uma clínica]*

### 3.2 Procedimento — visualizar o mapa

1. Abra **Mapa de Refeições**.
2. Selecione uma **Clínica** (ou “Todas”).
3. Selecione uma **Enfermaria** (habilitada após a clínica; ou “Todas”).
4. Ajuste a **data** se não for o dia corrente.
5. A grade carrega as linhas ativas daquele dia/filtros.

> **Importante:** até filtrar, a mensagem central é: *“Selecione clínica e/ou enfermaria para ver o mapa”*. Isso é esperado — o mapa não “some”; ele espera o filtro.

### 3.3 Procedimento — inserir paciente no mapa

1. Clique **Inserir paciente**.
2. Busque/selecione um paciente **já cadastrado**.
3. Informe **Clínica**, **Enfermaria** e **Leito** (obrigatórios).
4. Confirme dieta, flags de refeição e demais campos se necessário.
5. Salve. O paciente passa a persistir nos dias seguintes até uma saída com motivo.

### 3.4 Procedimento — marcar refeições (flags)

Nas colunas **D C A M J C**, clique para ligar/desligar Desjejum, Colação, Almoço, Merenda, Jantar e Ceia. A alteração é gravada e aparece em **Última alteração** com o usuário da sessão.

### 3.5 Procedimento — exclusão / saída (alta, óbito, transferência)

1. Na linha, use a ação de **sair/excluir** do mapa.
2. Escolha o **motivo**:
   - Alta médica  
   - Óbito  
   - Transferência (informe o **hospital de destino**)
3. Confirme.

**Efeito:** a linha não é apagada do histórico; fica com motivo e usuário. O paciente **não volta** automaticamente nos dias seguintes. Para recolocá-lo, use novamente **Inserir paciente**.

### 3.6 Substituições de cardápio

1. Clique com o botão direito (menu de contexto) → **Substituições**.
2. Escolha a aba da refeição (Desjejum…Ceia).
3. Veja o cardápio padrão da dieta; monte pares Remover / Adicionar.
4. Preencha a **Justificativa**.
5. Salve. É possível importar substituições do dia anterior.

### 3.7 Avisos de alta

Se o sistema detectar paciente com alta ainda presente em mapas futuros, abre um diálogo listando os casos. Marque quem deve ser excluído (padrão: todos) ou use **Manter todos** / **Excluir todos**, depois **OK**.

### 3.8 Dicas do mapa

- Use a busca da barra para achar leito/nome rapidamente.
- Role a tabela horizontalmente para ver Extras, Enteral, LVE etc.
- Menu de contexto traz atalhos (carregar pacientes, transferir leito, importar extras/suplementos, guia de atalhos).

---

## 4. Pacientes

### O que você vê

Lista de pacientes com busca; formulário modal para novo/editar (nome, sexo, nascimento, prontuário, clínica, leito, dieta, diagnóstico, observações, admissão, peso/altura).

**Screenshot placeholder:** *[Lista de pacientes]*

### Procedimento

1. Menu **Cadastro → Pacientes**.
2. **Novo:** preencha pelo menos o nome; salve.
3. **Editar:** altere dados; se houver linha no mapa de hoje, o snapshot é sincronizado.
4. **Desativar:** remove da lista ativa (soft). Inclusão no mapa do dia é feita pelo mapa (**Inserir paciente**), não automaticamente pelo cadastro (salvo opção explícita `adicionar_mapa` via API).

---

## 5. Clínicas, Enfermarias e Leitos

### 5.1 Clínicas

- Cadastro de nome e centro de custo.
- Vincule enfermarias à clínica (associação N:N).

### 5.2 Enfermarias

- Nome, flag **Nutriz**, ativo/inativo.
- Leitos vinculados à enfermaria.

### 5.3 Leitos

- Número e nome do leito por enfermaria.
- Usados na inserção no mapa e nos filtros.

**Ordem recomendada de cadastro:** Clínicas → Enfermarias → Leitos → Pacientes → Mapa.

---

## 6. Dietas e Grupos de Dietas

### 6.1 Dietas

1. **Cadastro → Dietas**.
2. Informe nome, categoria (básica, enteral, fórmula, LVE, suplemento…) e grupo visual.
3. Ative/desative conforme uso clínico.

### 6.2 Grupos de Dietas

Organizam a listagem (ex.: DIETAS ORAIS, NUTRIÇÃO ENTERAL, LACTÁRIO) com ordem de exibição.

**Screenshot placeholder:** *[Tela de dietas agrupadas]*

---

## 7. Tipos de Refeição (hora limite)

### O que você vê

Tabela com Sigla, Nome, **Hora limite**, Ativo e ações.

### Procedimento

1. **Cadastro → Tipos de Refeição**.
2. Crie ou edite (ex.: DESJEJUM / D, hora limite `07:30`).
3. A hora limite padroniza o corte operacional daquele horário.
4. Tipos alimentam a grade de **Preços das Refeições** e as flags do mapa.

---

## 8. Cardápios

### O que você vê

Lista de dietas com coluna **Cardápio** (ícone de maçã), checkbox Ativo e botões Editar/Excluir.

### Procedimento

1. **Cadastro → Cardápios**.
2. Clique na **maçã** (ou Editar) da dieta desejada.
3. No popup:
   - A dieta aparece **travada** (somente leitura) — você edita o cardápio daquela dieta, sem trocar o nome por engano.
   - Abas: **Grandes refeições**, **Pequenas refeições**, **Dietas líquidas**.
   - Informe dia do mês, horários (checkboxes), itens/pratos, V.N.T., custo se aplicável.
4. **Salvar**.

**Screenshot placeholder:** *[Popup do cardápio com ícone maçã e dieta travada]*

---

## 9. Preços das Refeições

### O que você vê

Grade: linhas = dietas (agrupadas); colunas = siglas dos tipos (D, C, A…); seletor **Coluna em edição**: Funcionário / Paciente / Acompanhante; opção **Replicar valor nas 3 colunas**.

### Procedimento

1. **Cadastro → Preços das Refeições**.
2. Escolha a coluna (Funcionário, Paciente ou Acompanhante).
3. Digite o valor na célula dieta × tipo.
4. Use filtro de dieta para achar itens longos.
5. **Adicionar valor à dieta** quando precisar completar a matriz.

Esses preços sustentam o **Faturamento**.

---

## 10. Nutricional (tabela de nutrientes e FDC)

### O que você vê

Seletor de tabela; botões Cria/Edita Tabelas e **Importa Tabela**; navegação de alimentos; campos de calorias/quantidades; grade de nutrientes (100g/100ml).

### Procedimento — editar alimento

1. **Cadastro → Nutricional**.
2. Selecione a tabela.
3. Busque o alimento ou navegue (primeiro/anterior/próximo/último).
4. **Editar** → altere macros/nutrientes → **Salvar**.

### Procedimento — importar FoodData Central (FDC)

1. Clique **Importa Tabela**.
2. Escolha arquivo **ZIP** ou **JSON** no formato FoodData Central.
3. Aguarde o processamento; novos alimentos entram com `fdc_id` na tabela selecionada/criada.

**Screenshot placeholder:** *[Diálogo de importação FDC]*

---

## 11. Dietas Líquidas

Cadastro de pratos líquidos com grupos (principal, sobremesa, outros, bebida, gelado, extra) e fator de conversão. Usados nas abas de cardápio líquido e produção.

---

## 12. Estoque, Produtos e Fornecedores

### 12.1 Estoque

Abas: **Produtos**, **Fornecedores**, **Movimentações**, **Alertas**, **Unidades de medida**.

### 12.2 Produtos (também em Cadastro → Produtos)

Informe estoque, grupo, código, descrição, quantidade, unidade, preços, min/max, quantidade líquida, flag FC.

### 12.3 Fornecedores

Nome, endereço, município, UF, CEP, CNPJ, IE, telefone, e-mail, prazo de faturamento, site, observação.

### 12.4 Unidades de medida

Código, descrição, conversão e flags (nutrientes, UMA, estoque, pratos).

**Screenshot placeholder:** *[Aba Produtos do Estoque]*

---

## 13. Etiquetas e Impressão

### 13.1 Cadastro de Etiquetas

Defina modelo: tamanho de folha, orientação, margens, colunas, altura, fonte e campos (tipo Dieta ou Fórmula).

### 13.2 Impressão de Etiquetas

1. Menu **Impressão de Etiquetas**.
2. Escolha o **horário** (Desjejum…Ceia) e a **data**.
3. Modo: Mapa de Refeições.
4. Imprimir por: Grupo de Clínica / Clínica / Enfermaria + filtro.
5. Opcional: só etiquetas alteradas a partir de um horário; incluir nome da enfermaria.
6. Gere a visualização/impressão.

---

## 14. Mapa U.M.A. e Totalização de Dietas

### Mapa U.M.A.

Gera totais (ex.: enteral) por clínica/filtro e horários, com versão para impressão.

### Totalização de Dietas

Consolida quantidades por dieta/grupo para apoiar a produção; disponível impressão.

---

## 15. Faturamento

1. Menu **Faturamento**.
2. Informe período **De** / **Até**.
3. Escolha o tipo (espelho 1ª/2ª página, totais, fórmulas/enterais, complementares).
4. Opções: por grupo de clínica; sintético.
5. **Exportar** ou **Imprimir**.

Os valores usam o mapa do período e a grade de preços.

---

## 16. Análise de Custos, Administração e Auditoria

- **Análise de Custos:** tela de relatórios/custos do módulo.
- **Administração:** gestão de usuários do contexto nutricional (listagem, novo usuário).
- **Auditoria:** abre o módulo de auditoria da plataforma para rastreio institucional.

---

## 17. Dicas e FAQ

### Por que o mapa abre vazio?

Porque é necessário selecionar **clínica e/ou enfermaria**. Isso evita carregar a grade inteira sem contexto e reduz erro operacional.

### Excluí um paciente e ele sumiu nos próximos dias. É bug?

Não. A saída com **motivo** impede a cópia automática. Reinsira pelo botão **Inserir paciente** se ele retornar.

### Posso apagar uma linha sem motivo?

Não pelo fluxo oficial de saída. Motivo (e hospital na transferência) é obrigatório — garante rastreabilidade.

### O que é “hora limite” no tipo de refeição?

Horário de corte cadastrado (HH:MM) para aquele tipo (ex.: Desjejum até 07:30). Usado na padronização operacional.

### Como importo a tabela nutricional americana?

Em **Cadastro → Nutricional → Importa Tabela**, envie ZIP/JSON do **FoodData Central**.

### A dieta no cardápio não deixa editar o nome

Correto: no popup do cardápio a dieta fica **travada**. Para renomear dieta, use **Cadastro → Dietas**.

### HTTP ou HTTPS?

Ambos podem estar ativos. Em HTTPS local pode ser necessário confiar no certificado (há páginas de ajuda/instalação na própria aplicação).

### Como paro o sistema?

Feche a janela do `iniciar_meuapp.bat` ou use o script `parar_meuapp.bat` se disponível na pasta do projeto.

---

## 18. Fluxo rápido do dia (checklist)

1. [ ] Iniciar app (`iniciar_meuapp.bat`) e fazer login  
2. [ ] Abrir **Mapa de Refeições**  
3. [ ] Filtrar clínica/enfermaria e confirmar data  
4. [ ] Inserir novos pacientes / ajustar dietas e flags  
5. [ ] Registrar saídas com motivo  
6. [ ] (Opcional) Substituições e avisos de alta  
7. [ ] Imprimir etiquetas do horário  
8. [ ] Conferir totalização / Mapa U.M.A.  
9. [ ] Ao fim do período: faturamento  

---

## 19. Suporte

Dúvidas de uso: equipe de Nutrição + TI São Geraldo Service.  
Dúvidas técnicas do MeuApp: engenharia (contato interno do projeto).

---

*São Geraldo Service — Nutrição Hospitalar — Manual do Usuário*  
*Este arquivo é a versão canônica para impressão; prints reais podem ser anexados nos placeholders.*
