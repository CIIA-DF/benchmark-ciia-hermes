# Guia e Regras de Design System: Portal de Documentação (CIIA-DF / NIAUnDF)

Este documento define os princípios de interface e padrões de código para o portal de documentação do Benchmark SEI. O objetivo é assegurar uma interface limpa, sóbria e editorial, eliminando clichês visuais gerados por IA.

---

## 1. Princípios de Identidade Visual

- **Institucional e Técnico:** A documentação representa um laboratório de inteligência artificial governamental e acadêmico. Evitar estética "gamer", "cyberpunk" ou "terminal fictício".
- **Sem Falsos Componentes:** Nunca simular janelas de sistema operacional (ex.: três botões coloridos de macOS) dentro do conteúdo da documentação. O container do documento deve ser limpo e focado no texto.
- **Tipografia em Primeiro Lugar:** Hierarquia visual clara através de pesos, entrelinha confortável (1.6 a 1.7) e kerning ajustado (`tracking-tight` em títulos).
- **Cores Sóbrias com Acentos Funcionais:** Fundo neutro escuro (Zinc/Slate escuro), sem tons azul-marinho super saturados de fundo. As cores de marca (ciano e azul do CIIA) devem ser usadas como toques pontuais de destaque (links, borda de seleção, badge ativo).

---

## 2. Paleta de Cores e Tokens

### Dark Mode (Padrão)
- **Background Principal:** `#090d16` ou `#0b0f19` (Neutro Slate Profundo)
- **Superfície / Sidebar:** `#0e1424`
- **Superfície de Cards / Leitor:** `#111827` (Slate 900)
- **Bordas Sutis:** `rgba(255, 255, 255, 0.08)` ou `slate-800`
- **Texto Principal:** `#f8fafc` (Slate 50)
- **Texto Secundário / Corpo:** `#94a3b8` (Slate 400) e `#cbd5e1` (Slate 300)
- **Accent Principal (CIIA):** `#06b6d4` (Cyan 500) e `#0284c7` (Sky 600)

---

## 3. Tipografia

- **Fonte Principal (Sans):** Inter ou Geist Sans.
- **Fonte Mono:** JetBrains Mono ou Roboto Mono.
- **Títulos (H1, H2, H3):**
  - Sem gradientes neon no texto corrido.
  - H1: `text-2xl md:text-3xl font-semibold tracking-tight text-slate-100`.
  - H2: `text-xl md:text-2xl font-semibold tracking-tight text-slate-200 mt-8 mb-4`.
  - H3: `text-lg font-medium text-slate-200 mt-6 mb-3`.
- **Corpo:** `text-[15px] leading-relaxed text-slate-300 font-normal`.

---

## 4. Componentes e Markdown

- **Callouts / Alerts:** Devem ter borda lateral sutil de 2px a 3px com fundo translúcido (ex.: `bg-cyan-950/20 border-l-2 border-cyan-500`), sem ícones gigantes ou sombras exageradas.
- **Código Inline:** `font-mono text-[13px] px-1.5 py-0.5 rounded bg-slate-800/60 text-cyan-300 border border-slate-700/50`.
- **Blocos de Código:** Superfície sólida `#090d16`, cantos levemente arredondados (`rounded-lg`), sem sombras coloridas.
- **Tabelas:** Linhas horizontais limpas, cabeçalho sutilmente destacado com `bg-slate-800/40`, células com bom espaçamento (`py-3 px-4`).
