# Geral

Pilha de Logs

# Temporadas

Cosmeticos
Passes de Temporadas
Afetar o modo historia
Mudar cartas de inicio de batalha

# Social

Amigos
Guildas

# Jogabilidade

Tutorial Interativo
Balanceamento inicial
Modo espectador
Anti-Cheat

## Armaduras

Capacete/Peitoral/Calças/Botas das Trevas
Capacete/Peitoral/Calças/Botas de escamas de Dragão
Capacete/Peitoral/Calças/Botas Sagrada da Fênix

## Armas

Facão
Faca de Ritual Antiga
Cutelo
Lança
Lança do Caçador de Dragões
Mjölnir
Martelo meteoro
Machado
Katana
Espada
Espada Excalibur
Espada da Justiça
Lâmina das Almas Maldita
Lâmina da Destruição
Lâmina do Abismo
Lâmina do Tempo
Tchaco
Cajado do Profeta

# Modo Historia

Criar Lore base
Bots
Desafios diarios
Mundo aberto
Modos de dificuldade
Conquistas
Experiência
Capitulos
Raça
Duelos
Sistema de carregar & salvar
Atributo de sorte
Habilidades
Poções
Alimentos
Livre Comercio
Loot boxes
Missões principais -> Progressão
Missões secundarias
Mestres
Facções de Bots
Recrutar NPCs
Craftings
Modo pós-morte
Arena de Monstros
Eventos da temporada -> local
Jornada da Fênix/Apofis
Baús domesticos



Boa, agora você tá pensando como dev de verdade 😎
Vou te montar um **roadmap claro e evolutivo**, tipo como se fosse um projeto real de jogo.

---

# 🗺️ ROADMAP – *Twilight Battle*

## 🟢 FASE 1 — Polimento (curto prazo)

> Deixar o jogo sólido e “jogável de verdade”

### ✅ Objetivo:

Corrigir base e melhorar experiência

### 🔧 O que fazer:

**1. Sistema de Save (essencial)**

* Salvar `gameState` no `localStorage`
* Auto-save ao morrer / trocar de área
* Botão “continuar”

---

**2. Balanceamento básico**

* Ajustar:

  * dano dos inimigos
  * custo dos itens
  * drop rate
* Evitar:

  * ficar OP muito rápido
  * ou morrer impossível

---

**3. Feedback visual**

* Animação simples no combate:

  * tremida na tela ao tomar dano
  * cor vermelha ao perder vida
* Highlight no inimigo

---

**4. Logs melhores**

* Separar por cor:

  * dano → vermelho
  * cura → verde
  * loot → amarelo

---

## 🟡 FASE 2 — Gameplay de verdade

> Aqui o jogo começa a ficar viciante

### ⚔️ 1. Habilidades por raça

Você já TEM isso definido, só falta usar.

Exemplo:

* Elfo → chance de esquiva
* Mago → magia (ataque especial)
* Centauro → ataque crítico
* Ninfa → cura passiva

👉 Isso muda completamente o combate

---

### 📈 2. Sistema de Level

* A cada level:

  * +vida OU
  * +skill
* Mostrar barra de XP

---

### 🧠 3. Combate mais profundo

Adicionar:

* crítico (%)
* defesa reduzindo dano real
* habilidades com cooldown

---

### 🎒 4. Itens mais interessantes

* Raridade:

  * comum
  * raro
  * épico
* Itens com efeitos:

  * +crit chance
  * +vida máxima
  * lifesteal

---

## 🟠 FASE 3 — Conteúdo (expansão)

### 🗺️ 1. Novas áreas

* Caverna
* Deserto
* Torre sombria
* Dungeon

---

### 👹 2. Bosses

* inimigos únicos
* habilidades especiais
* loot melhor

Ex:

* Dragão → ataque em área
* Necromante → invoca mobs

---

### 📜 3. Sistema de missões (de verdade)

* matar X inimigos
* coletar itens
* recompensa fixa

---

### 🎲 4. Eventos aleatórios

Tipo:

* “Você encontrou um viajante”
* “Uma armadilha!”
* “Baú amaldiçoado”

👉 Isso dá replay infinito

---

## 🔵 FASE 4 — Identidade do jogo (nível indie)

### 💀 1. Modo Roguelike (RECOMENDO MUITO)

Você já começou isso sem perceber.

* morte = perde tudo
* mas desbloqueia:

  * novas raças
  * bônus permanentes

---

### 🧬 2. Progressão global

* moedas permanentes
* upgrades fora da run

---

### 🎭 3. Lore / história

* diálogos melhores
* eventos narrativos
* escolhas

---

## 🔴 FASE 5 — Técnica (nível programadora)

Agora entra o lado que vai te fazer evoluir MUITO:

### 🧱 1. Refatorar código

* separar em arquivos:

  * `gameState.js`
  * `combat.js`
  * `ui.js`
  * `items.js`

---

### 🧩 2. Sistema modular

* funções menores
* evitar repetição

---

### ⚙️ 3. Melhorar arquitetura

* talvez usar classes:

  * `Player`
  * `Enemy`
  * `Item`

---

### 💾 4. Persistência melhor

* versionamento de save
* evitar save quebrado

---

## 🟣 FASE EXTRA (se quiser ir além)

* Sons 🎵
* Música de fundo
* Animações com canvas
* Transformar em app (Electron ou PWA)
* Multiplayer (bem avançado)

---

# 🧠 Dica mais importante

👉 NÃO tenta fazer tudo de uma vez

Faz assim:

1. Save system
2. Habilidades
3. Level
4. Conteúdo

---

Se quiser, posso te fazer:

* um **checklist passo a passo**
* ou começar contigo tipo:
  👉 “vamos implementar habilidades agora”

Só falar 👍
