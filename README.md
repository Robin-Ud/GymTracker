# GymTracker

Rastreador de treinos no terminal — puro Python, zero dependências.

---

## O que é

GymTracker registra séries, cargas e RIR diretamente no terminal. Os dados ficam em um CSV local append-only. A progressão de fases é controlada por **sessões concluídas**, não por calendário — a semana só avança quando você completa os treinos. Se semanas consecutivas forem perdidas, o script retrograde automaticamente para a fase anterior.

## Funcionalidades

- Menu interativo no terminal
- Plano periodizado de 7 fases (52 semanas) integrando musculação e BJJ
- Sugestão de carga por exercício baseada no histórico e RIR médio da última sessão
- Feedback imediato após cada série (RIR realizado vs. alvo)
- Check-in pré-treino: PRS, sono, estresse
- Semana avança apenas ao completar as sessões exigidas pela fase
- Retrograde automático após 2+ semanas incompletas consecutivas
- Deload automático configurável por fase no JSON
- Modo teste isolado em `/tmp` — dados reais intocados
- Apenas stdlib Python — sem `pip install` nenhum

## Instalação

```bash
git clone <repo>
cd GymTracker
chmod +x gymtracker.sh gymtracker_test.sh
./gymtracker.sh
```

Alias opcional no `.bashrc` para rodar de qualquer lugar:

```bash
alias gym='~/GymTracker/gymtracker.sh'
```

**Requisito:** Python 3.10+

## Uso

```bash
./gymtracker.sh          # uso normal — git pull antes, push depois (se remoto configurado)
./gymtracker_test.sh     # modo teste em /tmp, mostra diff ao sair
python3 gymtracker.py --test  # equivalente ao acima
```

```
────────────────────────────────────────────────────────────
 GymTracker  ·  Matheus
────────────────────────────────────────────────────────────
 Programa  Plano de 1 Ano — Musculação + BJJ
 Fase      1/7  ·  Adaptação/Hábito  ·  Sem 1
 Sessões   ○○  0/2  ·  RIR alvo: 4
 Próximo   Treino A  ·  18/05/26
────────────────────────────────────────────────────────────
 0  análise de progresso
 1  registrar treino
 2  ver programa
 3  alterar programa
 4  alterar data
 9  sair
────────────────────────────────────────────────────────────
```

Durante o registro de treino, o script sugere carga antes de cada exercício e dá feedback imediato após cada série:

```
────────────────────────────────────────────────────────────
 [1/5]  Agachamento ou Leg Press  ·  3 × 8-12
 ↳ Sugerido: 62.5 kg  (última 60.0 kg · RIR 6.0 fácil → +2.5 kg)

   Série 1/3
     peso (kg) : 62.5
     reps      : 10
     RIR   (4) : 4
   ✓ RIR perfeito
```

## Estrutura de dados

Cada série vira uma linha em `pessoal/treinos/treinos_AAAA.csv`:

| Coluna | Descrição |
|--------|-----------|
| `data` | Data (DD/MM/AA) |
| `semana_treino` | Semana de treino (avança por sessões, não calendário) |
| `fase` | Número da fase (1–7) |
| `treino` | A ou B |
| `prs` | Perceived Recovery Status pré-treino (0–10) |
| `sono` | Qualidade do sono (ótimo/bom/regular/ruim) |
| `estresse` | Nível de estresse (baixo/médio/alto) |
| `exercicio` | Nome do exercício |
| `serie` | Número da série |
| `reps_feitas` | Repetições executadas |
| `peso_kg` | Carga em kg |
| `rir` | Repetições na reserva |
| `session_rpe` | RPE geral da sessão (pós-treino, 0–10) |
| `detalhes` | Músculo-alvo ou observação livre |

## Configuração

`pessoal/configs.json` — estado persistido entre sessões (na primeira vez é copiado de `exemplo/configs.json`):

```json
{
  "atleta": "Atleta",
  "programa_ativo": "longo_prazo_bjj",
  "semana_treino": 1,
  "semana_treino_inicio": "18/05/26",
  "semanas_perdidas": 0,
  "ultima_sessao": null
}
```

`programas/<nome>.json` — define fases, exercícios e parâmetros:

```json
{
  "nome": "Plano de 1 Ano — Musculação + BJJ",
  "fases": [
    {
      "numero": 1,
      "nome": "Adaptação/Hábito",
      "semanas": 4,
      "frequencia_semanal": 2,
      "rir_alvo": 4,
      "rpe_alvo": 6,
      "deload_a_cada_semanas": 0,
      "descanso_segundos": "60-90",
      "treinos": {
        "A": [
          {"exercicio": "Agachamento", "musculo": "quadriceps", "series": 3, "reps_alvo": "8-12"}
        ],
        "B": [...]
      }
    }
  ]
}
```

Para adicionar um programa novo: crie `programas/<nome>.json` seguindo a estrutura acima e selecione pela opção `3` do menu.

## Estrutura do projeto

```
gymtracker.py          ← script único
gymtracker.sh          ← wrapper (git pull do código; pull/push do pessoal/ se ele for um clone git)
gymtracker_test.sh     ← modo teste isolado em /tmp
exemplo/configs.json   ← estado inicial (copiado pro pessoal/ na primeira vez)
programas/
  longo_prazo_bjj.json ← plano de 7 fases, 52 semanas
pessoal/               ← seus dados, fora do git (pode ser um clone de um repo privado seu)
  configs.json         ← estado e configuração global
  treinos/
    treinos_2026.csv   ← registros append-only
```
