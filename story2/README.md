# Twilight Battle — Modo História (LÖVE2D)

Reescrita do modo história de `templates/game/story.html` em **Lua + LÖVE2D**.
O projeto é autônomo: não depende do Flask, Socket.IO ou de qualquer biblioteca
externa. Todos os dados do jogo original (raças, locais, itens, criaturas,
receitas, NPCs, missões, encontros, clima e conquistas) foram convertidos para
tabelas Lua em `src/data/`.

> Estado atual: jogável de ponta a ponta — criação de personagem, mapa, viagens,
> inventário/equipamento, baú, NPCs e lojas, missões, sobrevivência, sono,
> clima, estações de trabalho, mina, combate e final da campanha.
> Ainda não há áudio nem integração online.

---

## Como rodar

Requisito: **LÖVE 11.4 ou superior**.

```bash
# na raiz do repositório
love story2

# ou dentro da pasta
cd story2 && love .
```

No Debian/Ubuntu: `sudo apt install love`.
Em outras plataformas: https://love2d.org/

A janela é redimensionável. A resolução virtual é **1280×720** com letterbox;
F11 alterna tela cheia. O save fica na pasta de saves do LÖVE, com a identidade
`twilight-story2` (definida em `conf.lua`).

---

## Controles

| Ação | Controle |
| --- | --- |
| Interagir | mouse (botões, itens, mapa, modais) |
| Usar/equipar item | clique no slot |
| Mover item | arrastar entre slots (ou para o equipamento) |
| Rolar listas/registro | roda do mouse |
| Mapa completo | `M` ou botão **Mapa** |
| Diário | `J` ou botão **Diário** |
| Perfil | `P` |
| Menu | `Esc` ou botão **Menu** |
| Fechar modal | `Esc` ou **X** |
| Tela cheia | `F11` |

Atalhos de teclado não funcionam enquanto um modal está aberto (exceto `Esc`).

---

## O que foi portado

- **Criação de personagem** — 4 raças (elfo, mago, centauro, ninfa), nome,
  gênero, idade, biografia, atributos e habilidade racial.
- **Mapa-múndi** — 43 nós vetoriais com estradas derivadas das ações de
  movimento, descoberta de locais, mapa grande com zoom/arraste e viagem
  apenas entre locais adjacentes.
- **52 locais** com descrições e 123 ações distintas (andar, conversar, comprar,
  explorar, minerar, dormir, abrir baú etc.).
- **Inventário** de 18 slots, stacks de 64, organização automática, uso de
  comida/bebida, livros, estações e contêineres.
- **Equipamento** em 6 slots (capacete, peitoral, calças, botas, mão principal e
  secundária), com bônus de ataque/defesa, durabilidade e absorção de dano por
  peça (mesma ordem do original).
- **Combate por turnos** — ataque corpo a corpo, arco e flechas, golpes básicos,
  golpes de arma, habilidades aprendidas por nível, habilidade racial, esquiva,
  contra-ataque, fuga, drops, EXP, ouro, bestiário e morte.
- **Sobrevivência** — fome, sede e sanidade; penalidades de sanidade afetam dano
  e podem fazer magias falharem; dormir restaura mana/vida e avança o tempo.
- **Tempo, calendário e clima** — ciclo dia/noite, 60 dias por estação, 4
  estações, anos, clima com bônus de encontro.
- **Missões** — as 5 missões do original (`royal_hunt`, `main_two_crowns`,
  `carpenter_wood`, `weaver_cloth`, `pedro_map`), com estágios de conversa,
  abate, coleta, entrega e visita; quadro de missões e diário.
- **NPCs** — 23 NPCs com tópicos de conversa, lojas, venda de itens e despedida.
- **Estações** — bancada, tear, moinho, fornalha (com fila e combustível),
  bigorna (reparo e reforço até +5), saco de dormir; mesa de alquimia existe,
  mas o modo original não traz receitas para ela.
- **Mina** — galerias de profundidade 1–3, picareta, tochas/combustível,
  minigame de timing, minérios por profundidade e encontros ao descer.
- **Conquistas** — as 26 conquistas de `systems.js`, verificadas após os eventos.
- **Final** — ao derrotar o Mago Negro, o jogador escolhe entre restaurar a
  Aurora ou assumir o Crepúsculo.
- **Save local** em JSON, autosave a cada 45 s, backup do save anterior e save
  ao sair/perder o foco (sem nuvem).

---

## Arquitetura

```
story2/
├── conf.lua                  # janela 1280x720, identidade do save
├── main.lua                  # load/update/draw, escala, input global
├── assets/
│   ├── fonts/                # DejaVu Sans/Bold/Mono + licença
│   └── images/Map.png        # arte original (não usada pelo mapa vetorial)
├── src/
│   ├── core/                 # util, json, text, theme, scale, ui
│   ├── data/                 # dados convertidos + init.lua (ajustes manuais)
│   ├── game/
│   │   ├── state.lua         # estado global, save/load, nível, morte
│   │   ├── inventory.lua     # itens, stacks, equipamento, dano em armadura
│   │   ├── survival.lua      # fome, sede, sanidade
│   │   ├── time.lua          # ciclo, calendário, clima, sono
│   │   ├── quests.lua        # motor de missões
│   │   ├── combat.lua        # golpes, habilidades, encontros, drops
│   │   ├── craft.lua         # bancada, tear, moinho, fornalha, bigorna
│   │   ├── npc.lua           # conversa, lojas, venda
│   │   ├── actions.lua       # despacho das ações de localização
│   │   ├── achievements.lua  # 26 conquistas
│   │   └── minigame.lua      # minigame de timing (picareta/machado)
│   └── screens/
│       ├── manager.lua       # troca de telas
│       ├── title.lua         # tela-título
│       ├── creation.lua      # criação de personagem
│       ├── game.lua          # HUD, inventário, local, combate, registro
│       ├── map.lua           # mapa vetorial (pequeno e tela cheia)
│       └── modals.lua        # NPC, baú, estações, missões, diário, mina...
└── tests/
    ├── smoke.lua             # testes de lógica + smoke test de desenho
    └── actions_coverage.lua  # confere se todas as ações têm implementação
```

### Dados

Os arquivos em `src/data/` são **gerados** a partir do modo história original
(`templates/game/story.html`, `static/js/story/systems.js` e `quests.js`) e não
devem ser editados à mão. Ajustes e conteúdo adicional ficam em
`src/data/init.lua`:

- itens/locais/nós extras (milho, Pico do Dragão, Terras Selvagens, Cidadela...);
- tabelas de nutrição, álcool, combustível e fontes de água;
- correções de ações do cemitério/floresta;
- movimento `goNorthForestEdge` (definido só em `systems.js`);
- rebalanceamento do dragão (1500 de vida, 180 de ataque etc.);
- helpers `DB.isOutdoor`, `DB.walkOptions`, `DB.localInteractions`,
  `DB.worldEdges`;
- injeção de `id` em itens, criaturas, locais, NPCs e missões.

O conversor usado na geração não faz parte do jogo (ficava em `/tmp`); para
regenerar os dados é preciso reexecutar o pipeline a partir do HTML/JS original.

---

## Save

Local do arquivo (LÖVE `identity = twilight-story2`):

- Linux: `~/.local/share/love/twilight-story2/save.json`
- Windows: `%APPDATA%\LOVE\twilight-story2\save.json`
- macOS: `~/Library/Application Support/LOVE/twilight-story2/save.json`

O save é JSON legível. Progresso de missão, itens, equipamento, baú, estações
montadas, clima, calendário, conquistas e bestiário são persistidos. O save é
apagado quando o personagem morre.

---

## Testes

Sem LÖVE instalado, os testes usam um mock mínimo da API e validam lógica e
desenho:

```bash
cd story2
lua5.4 tests/smoke.lua
lua5.4 tests/actions_coverage.lua
```

O `smoke.lua` cobre criação, stacks, equipamento, dano em armadura, fome,
missões, combate, craft, fornalha, lojas, viagem, save/load (inclusive missão
ativa), minigame, abertura/desenho de todos os modais, cliques reais em botões,
uso de item, baú, compra em NPC, combate e o ciclo completo de `main.lua`.
O `actions_coverage.lua` percorre todas as ações de todos os locais e falha se
alguma cair no aviso “Ação ainda não portada”.

Validação de sintaxe (Lua 5.1, compatível com LuaJIT do LÖVE):

```bash
find . -name '*.lua' -exec luac -p {} \;
```

---

## Diferenças em relação ao original

- O mapa é **vetorial** (nós/estradas/cores), não a imagem `Map.png`. A imagem
  foi mantida em `assets/images/` como referência, mas não cobre o sul do mapa.
- A mina é uma interface de galerias com minigame, não o labirinto em canvas do
  `mining.js`; a progressão (profundidade, tochas, minérios, perigos) foi
  preservada.
- A biblioteca implementa cartão, empréstimo, devolução e reputação de forma
  simplificada; o controle de datas de vencimento do original não foi portado.
- O diário de livro permite título e uma linha de conteúdo (o editor multilinhas
  do original não foi replicado).
- Mesa de alquimia não tem receitas porque o modo original também não as define.
- Não há áudio, animações de sprites, partículas nem integração HTTP/nuvem.
- Emojis são removidos na renderização porque a fonte DejaVu empacotada não tem
  glifos de emoji; os textos continuam legíveis.

---

## Créditos e licenças

- Conteúdo e regras: modo história original de Twilight Battle.
- Fontes: DejaVu Sans (licença em `assets/fonts/LICENSE-DejaVu.txt`).
- `assets/images/Map.png`: arte do projeto original.
