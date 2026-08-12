# Resumo Completo — Nutrição Hospitalar

**São Geraldo Service**  
Módulo: Nutrição Hospitalar  
Documento para leitura técnica e executiva  
Versão de referência: código atual do projeto `meuapp`

---

## 1. O que é

O módulo **Nutrição Hospitalar** do **São Geraldo Service** concentra a operação diária da produção de refeições hospitalares: mapa do dia por clínica/enfermaria, cadastros clínicos e nutricionais, cardápios, precificação, estoque, etiquetas, totalizações e faturamento.

Ele faz parte da plataforma web MeuApp (Flask + MySQL), ao lado de Chamados, Pesagem e Auditoria. A identidade visual da marca usa azul institucional (`#1B4F9C` / `#0D2B5C`) e acento lima (`#A8C53A`).

---

## 2. Problema que resolve

| Antes (cenário típico) | Com o módulo |
|---|---|
| Planilhas e listas soltas por turno | Mapa único do dia com persistência automática |
| Perda de histórico ao “apagar” paciente | Saída com motivo + usuário; linha permanece no histórico |
| Preços e dietas inconsistentes entre equipes | Grade dieta × tipo de refeição (Funcionário / Paciente / Acompanhante) |
| Etiquetas e totais manuais | Impressão e relatórios a partir do mapa |
| Dados nutricionais dispersos | Tabelas locais + importação FoodData Central (FDC) |

---

## 3. Acesso e disponibilidade

| Item | Detalhe |
|---|---|
| Atalho de início | `iniciar_meuapp.bat` (sobe MySQL84 se necessário, usa `.venv`, abre o navegador) |
| HTTP | Porta **80** — `http://127.0.0.1/` |
| HTTPS | Porta **443** (fallback 8443 se ocupada) — certificado local; cookies compatíveis com HTTP e HTTPS |
| Login | Tela `/login`; após autenticação, hub **Sistemas** (`/`) com atalho para Nutrição |
| Hub do módulo | `/nutricao` — **Mapa de Produção** (entrada principal) |
| Alternância | Barra superior: Sistemas · Chamados · Nutrição |
| Auditoria | Link no menu lateral para o módulo de Auditoria da plataforma |

> Observação: rotas de Nutrição usam sessão do usuário logado (nome gravado em alterações do mapa). O login da plataforma é o ponto de entrada padrão.

---

## 4. Arquitetura (visão resumida)

```
Browser (templates_nutricao + CSS/JS)
        │
        ▼
Flask Blueprint `nutricao`  (routes_nutricao.py)
        │
        ├─ nutricao_service.py   (regras: mapa do dia, preços, FDC, faturamento, etiquetas…)
        ├─ models_nutricao.py    (tabelas `nut_*` no MySQL)
        └─ seeds / import FDC    (catálogo inicial e FoodData Central)
```

**Persistência do mapa:** `garantir_mapa_do_dia` copia linhas ativas dia a dia. Pacientes baixados com **motivo de saída** não reaparecem nos dias seguintes. Inclusão nova é sempre explícita (botão/API de inserir).

---

## 5. Menu e módulos

### 5.1 Operação do dia

| Tela | Rota | Função |
|---|---|---|
| **Mapa de Refeições / Produção** | `/nutricao` | Grade do dia: Adm, Leito, Pront, Nome, Idade, Diagnóstico, Dieta, OBS, flags **D C A M J C**, Saída, obs. etiqueta, Extras, Suplementos, Enteral, Fórm. Infantil, LVE, inclusão, última alteração, motivo, ações |
| Mapa U.M.A. | `/nutricao/relatorio-mapa-uma` | Totalização UMA (enteral etc.) com impressão |
| Impressão de Etiquetas | `/nutricao/impressao-etiquetas` | Etiquetas a partir do mapa por horário / clínica / enfermaria |
| Totalização de Dietas | `/nutricao/totalizacao-dietas` | Contagem/agrupamento para produção |
| Faturamento | `/nutricao/faturamento` | Espelhos e totais por período; exportar / imprimir |
| Análise de Custos | `/nutricao/relatorios` | Visão de custos (tela de análise) |
| Estoque | `/nutricao/estoque` | Produtos, grupos, unidades, fornecedores, alertas |
| Administração | `/nutricao/admin` | Usuários do contexto nutricional (tela administrativa) |

### 5.2 Cadastros (submenu)

| Cadastro | Conteúdo principal |
|---|---|
| Pacientes | Nome, sexo, nascimento, prontuário, clínica, leito, dieta, diagnóstico, antropometria, saída |
| Clínicas | Nome, centro de custo, vínculo com enfermarias |
| Enfermarias | Nome, flag nutriz, leitos associados |
| Leitos | Número/nome por enfermaria |
| Dietas | Nome, categoria (básica, enteral, fórmula, LVE, suplemento…), grupo visual |
| Grupos de Dietas | Agrupamento (ex.: DIETAS ORAIS, LACTÁRIO) com ordem |
| Tipos de Refeição | Nome, sigla, ordem, **hora limite** (HH:MM) |
| Cardápios | Lista por dieta; popup (ícone maçã); dieta **travada** no formulário; abas Grandes / Pequenas / Líquidas |
| Preços das Refeições | Matriz **Dieta × Tipo**; colunas Funcionário / Paciente / Acompanhante |
| Nutricional | Tabelas, alimentos, macros e nutrientes/100g; **Importa Tabela** (ZIP/JSON FDC) |
| Dietas Líquidas | Pratos líquidos por grupos (principal, sobremesa, bebida…) |
| Produtos | Cadastro detalhado (também refletido no Estoque) |
| Fornecedores | Dados cadastrais e comerciais |
| Etiquetas | Modelos de folha, margens, campos (Dieta / Fórmula) |

---

## 6. Mapa de Produção — núcleo operacional

### 6.1 Fluxo do usuário

1. Abrir `/nutricao`.
2. Escolher **Clínica** e/ou **Enfermaria** (a grade inicia vazia até o filtro — mensagem: *“Selecione clínica e/ou enfermaria para ver o mapa”*).
3. Navegar a data (← →).
4. Inserir paciente (cadastro existente + clínica, enfermaria e leito obrigatórios).
5. Marcar flags de refeição (D/C/A/M/J/C), editar campos complementares.
6. Usar menu de contexto (substituições de cardápio, importação de extras/suplementos etc.).
7. Em alta/óbito/transferência: **Excluir/saída** com motivo obrigatório (e hospital destino na transferência).

### 6.2 Regras de negócio relevantes

- **Persistência dia a dia:** linhas ativas são propagadas automaticamente.
- **Baixa (saída):** soft-delete — mantém histórico; `motivo_saida` + `usuario_alteracao`; impede cópia futura.
- Motivos aceitos na API: Alta médica, Óbito, Transferência.
- **Avisos de alta:** se paciente com saída aparece em mapas posteriores, diálogo para manter ou excluir.
- **Substituições:** cardápio padrão da dieta × refeição, pares remover/adicionar e justificativa; importação do dia anterior.
- Scroll horizontal/vertical na grade larga; busca por leito, prontuário, nome, dieta.

### 6.3 Rastreabilidade

- `usuario_alteracao` + `data_atualizacao` em cada linha.
- Coluna “Última alteração” no formato `usuário — dd/mm/aa HH:MM:SS`.
- Integração com módulo **Auditoria** da plataforma (menu lateral).

---

## 7. Precificação e faturamento

- **Preços:** modelo canônico `NutPrecoDietaTipo` (dieta × tipo de refeição) com `valor_empresa` (UI: Funcionário), `valor_paciente`, `valor_acompanhante`.
- Grade editável com opção de replicar valor nas três colunas.
- **Faturamento:** período De/Até; tipos de relatório (espelho 1ª/2ª página, totais, fórmulas/enterais, complementares); opções por grupo de clínica e sintético; **Exportar** e **Imprimir**.
- Totais se apoiam no mapa do período (`relatorio_faturamento` + `garantir_mapa_do_dia`).

---

## 8. Estoque e cadeia de suprimentos

- Locais de estoque, grupos de produto, unidades de medida (flags para nutrientes, UMA, estoque, pratos).
- Produtos: código, descrição, quantidades, preços médio/último, min/max, líquido, flag FC.
- Fornecedores: endereço, CNPJ, contato, faturamento em dias, etc.
- Tela Estoque com abas: Produtos, Fornecedores, Movimentações, Alertas, Unidades.

---

## 9. Qualidade da informação nutricional

- Tabelas de nutrientes locais (`NutTabelaNutrientes` → `NutAlimento` → `NutAlimentoNutriente`).
- Campos de macros (calorias e quantidades), glúten, fenilalanina, NPU, referência de consumo.
- Importação **USDA FoodData Central** via ZIP/JSON (`import_tabela_fdc` / `nutricao_fdc_import.py`), com `fdc_id` único por tabela.
- Cardápios e dietas líquidas alimentam a produção e as substituições do mapa.

---

## 10. Etiquetas e impressão

- Cadastro de modelos (folha carta/A4, orientação, margens, colunas, fonte, campos).
- Impressão filtrada por horário de refeição, data, grupo/clínica/enfermaria; opção de só alterações a partir de um horário; incluir nome da enfermaria.

---

## 11. Segurança e governança (visão diretoria)

| Tema | Situação no produto |
|---|---|
| Autenticação | Login da plataforma São Geraldo Service |
| Transporte | HTTP + HTTPS locais (certificado autoassinado com fluxo de confiança documentado na app) |
| Rastreio operacional | Usuário e timestamp nas alterações do mapa; motivo de saída obrigatório |
| Auditoria | Módulo dedicado linkado no menu |
| Backup | Responsabilidade operacional (MySQL); recomenda-se rotina de backup do banco — não é tela do módulo |
| Padronização | Dietas, tipos, preços e cardápios centralizados |

---

## 12. Benefícios para a diretoria

1. **Controle operacional** — um mapa oficial do dia por unidade.
2. **Padronização** — dietas, horários (com hora limite), cardápios e preços alinhados.
3. **Histórico e compliance** — saídas justificadas; alterações atribuídas a usuário.
4. **Visibilidade financeira** — faturamento e preços por perfil (funcionário/paciente/acompanhante).
5. **Qualidade assistencial** — dados nutricionais estruturados e etiquetas consistentes.
6. **Disponibilidade** — atalho único (`iniciar_meuapp.bat`) e acesso HTTP/HTTPS na rede local.

---

## 13. Roadmap leve (próximos passos sugeridos)

Itens já presentes no código como parcial/mock ou “em breve” — úteis para planejamento, sem compromisso de prazo:

- Aprofundar movimentações de estoque e alertas em tempo real.
- Ampliar utilitários (totalização direta, autorizações de substituição) além dos fluxos já no mapa.
- Endurecer `login_required` em todas as rotas do blueprint, se ainda não unificado.
- Relatórios gerenciais consolidados (custos × mapa × faturamento) para painel executivo.
- Integração HIS/PEP (prontuário/leito) quando a instituição priorizar.

---

## 14. Glossário rápido

| Termo | Significado |
|---|---|
| Mapa de Produção | Grade diária de pacientes × refeições |
| Flags D C A M J C | Desjejum, Colação, Almoço, Merenda, Jantar, Ceia |
| Hora limite | Horário cadastrado no tipo de refeição (corte operacional) |
| U.M.A. | Relatório/totalização de unidades (ex.: enteral) |
| FDC | FoodData Central (base nutricional USDA) |
| Baixa / saída | Remoção lógica do mapa com motivo (não apaga histórico) |

---

## 15. Referência de arquivos no repositório

| Arquivo | Papel |
|---|---|
| `routes_nutricao.py` | Rotas e APIs |
| `models_nutricao.py` | Modelos ORM `nut_*` |
| `nutricao_service.py` | Regras de negócio |
| `templates_nutricao/` | UI |
| `nutricao_fdc_import.py` | Import FDC |
| `iniciar_meuapp.bat` | Inicialização local |
| `app.py` | Dual HTTP/HTTPS, registro do blueprint |

---

*Documento gerado para apresentação à diretoria e onboarding técnico. Marca: São Geraldo Service — Nutrição Hospitalar.*
