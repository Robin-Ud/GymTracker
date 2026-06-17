#!/usr/bin/env python3
"""GymTracker — rastreador de treinos no terminal. Puro Python, zero dependências."""

from __future__ import annotations

import atexit
import csv
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import date, datetime
from pathlib import Path

# ── Test mode setup (must come before all path constants) ─────────────────────

_SCRIPT_DIR = Path(__file__).parent
TEST_MODE   = "--test" in sys.argv

if TEST_MODE:
    _test_dir = Path(tempfile.mkdtemp(prefix="gymtracker_test_"))
    shutil.copy2(_SCRIPT_DIR / "configs.json", _test_dir / "configs.json")
    shutil.copytree(_SCRIPT_DIR / "programas", _test_dir / "programas")
    (_test_dir / "treinos").mkdir()
    if (_SCRIPT_DIR / "treinos").exists():
        for _f in (_SCRIPT_DIR / "treinos").glob("*.csv"):
            shutil.copy2(_f, _test_dir / "treinos" / _f.name)
    BASE_DIR = _test_dir

    def _test_cleanup() -> None:
        print()
        for _csv in sorted((BASE_DIR / "treinos").glob("*.csv")):
            _orig = _SCRIPT_DIR / "treinos" / _csv.name
            added: list[str] = []
            if _orig.exists():
                res = subprocess.run(
                    ["diff", str(_orig), str(_csv)], capture_output=True, text=True
                )
                added = [ln[2:] for ln in res.stdout.splitlines() if ln.startswith("> ")]
            else:
                with open(_csv, encoding="utf-8") as _fh:
                    added = list(_fh)[1:]
            if added:
                print(f"[teste] adicionado em {_csv.name}:")
                for ln in added[:15]:
                    print(f"  {ln.rstrip()}")
        try:
            keep = input("\n[teste] manter arquivos? [s/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            keep = "n"
        if keep == "s":
            print(f"[teste] mantido em: {BASE_DIR}")
        else:
            shutil.rmtree(BASE_DIR, ignore_errors=True)
            print("[teste] limpo.")

    atexit.register(_test_cleanup)
else:
    BASE_DIR = _SCRIPT_DIR

# ── Constants ─────────────────────────────────────────────────────────────────

CONFIGS_PATH  = BASE_DIR / "configs.json"
PROGRAMAS_DIR = BASE_DIR / "programas"
TREINOS_DIR   = BASE_DIR / "treinos"

CSV_HEADER = [
    "data", "semana_treino", "fase", "treino",
    "prs", "sono", "estresse",
    "exercicio", "serie", "reps_feitas", "peso_kg",
    "rir", "session_rpe", "detalhes",
]

SONO_OPTS     = {"o": "ótimo", "b": "bom", "r": "regular", "p": "ruim"}
ESTRESSE_OPTS = {"b": "baixo", "m": "médio", "a": "alto"}

# ── Terminal width ────────────────────────────────────────────────────────────

_COLS = min(shutil.get_terminal_size((60, 24)).columns, 60)
SEP   = "─" * _COLS


# ── I/O helpers ───────────────────────────────────────────────────────────────

def load_config() -> dict:
    with open(CONFIGS_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_config(cfg: dict) -> None:
    with open(CONFIGS_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def load_programa(nome: str) -> dict:
    with open(PROGRAMAS_DIR / f"{nome}.json", encoding="utf-8") as f:
        return json.load(f)


def csv_path_for(d: date) -> Path:
    return TREINOS_DIR / f"treinos_{d.year}.csv"


def all_csv_paths() -> list[Path]:
    return sorted(TREINOS_DIR.glob("*.csv")) if TREINOS_DIR.exists() else []


def parse_date(s: str) -> date:
    return datetime.strptime(s, "%d/%m/%y").date()


def fmt(d: date) -> str:
    return d.strftime("%d/%m/%y")


def ask(prompt: str, default: str = "") -> str:
    try:
        val = input(prompt).strip()
        return val if val else default
    except (EOFError, KeyboardInterrupt):
        print()
        return default


# ── Display helpers ───────────────────────────────────────────────────────────

def sep() -> None:
    print(SEP)


def dots(done: int, total: int) -> str:
    return "●" * done + "○" * (total - done)


# ── Weight suggestion ─────────────────────────────────────────────────────────

def _last_session_ex(ex_nome: str) -> dict | None:
    """Return stats from the most recent logged session containing this exercise."""
    all_rows: list[dict] = []
    for p in all_csv_paths():
        with open(p, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["exercicio"] == ex_nome:
                    all_rows.append(r)
    if not all_rows:
        return None

    last = all_rows[-1]
    sess = [
        r for r in all_rows
        if r["data"] == last["data"] and r["treino"] == last["treino"]
    ]
    pesos = [float(r["peso_kg"]) for r in sess if float(r.get("peso_kg", 0)) > 0]
    rirs: list[float] = []
    for r in sess:
        try:
            rirs.append(float(r["rir"]))
        except (ValueError, KeyError):
            pass
    return {
        "data":      last["data"],
        "avg_peso":  sum(pesos) / len(pesos) if pesos else 0.0,
        "avg_rir":   sum(rirs) / len(rirs) if rirs else None,
    }


def suggest_peso(ex_nome: str, rir_alvo: int) -> tuple[float | None, str]:
    """Return (suggested_kg or None, description)."""
    stats = _last_session_ex(ex_nome)
    if not stats or stats["avg_peso"] == 0:
        return None, "primeira vez — comece conservador"

    peso = stats["avg_peso"]
    rir_m = stats["avg_rir"]

    if rir_m is None:
        return peso, f"última: {peso:.1f} kg em {stats['data']}"

    diff = rir_m - rir_alvo

    if diff >= 3:
        return peso + 5.0,  f"última {peso:.1f} kg · RIR {rir_m:.1f} muito fácil → +5 kg"
    if diff >= 1.5:
        return peso + 2.5,  f"última {peso:.1f} kg · RIR {rir_m:.1f} fácil → +2.5 kg"
    if diff >= 0.5:
        return peso + 2.5,  f"última {peso:.1f} kg · RIR {rir_m:.1f} levemente fácil → +2.5 kg"
    if diff >= -0.5:
        return peso,        f"última {peso:.1f} kg · RIR {rir_m:.1f} OK → manter"
    if diff >= -1.5:
        return peso,        f"última {peso:.1f} kg · RIR {rir_m:.1f} no limite → manter/-2.5"
    return max(0.0, peso - 2.5), f"última {peso:.1f} kg · RIR {rir_m:.1f} pesado → -2.5 kg"


# ── Set feedback ──────────────────────────────────────────────────────────────

def set_feedback(rir_val: int | str, rir_alvo: int) -> str:
    try:
        diff = int(rir_val) - rir_alvo
    except (ValueError, TypeError):
        return ""
    if diff >= 4:  return "→ Muito fácil! Aumente 5 kg na próxima série"
    if diff >= 2:  return "→ Fácil. Aumente 2.5 kg na próxima série"
    if diff == 1:  return "→ Levemente fácil — OK para esta fase"
    if diff == 0:  return "✓ RIR perfeito"
    if diff == -1: return "→ Um pouco pesado. Mantenha na próxima"
    return             "→ Pesado! Reduza 2.5 kg na próxima série"


# ── Entrada de série (peso/reps/rir navegável) ──────────────────────────────────

CAMPO_INFO = {
    "peso":  {"label": "peso (kg)", "caster": lambda s: float(s.replace(",", ".")), "min": 0, "max": 500},
    "reps":  {"label": "reps",      "caster": int,                                  "min": 0, "max": 200},
    "rir":   {"label": "RIR",       "caster": int,                                  "min": 0, "max": 10},
    "tempo": {"label": "tempo (s)", "caster": int,                                  "min": 0, "max": 600},
}


def is_exercicio_tempo(reps_alvo: str) -> bool:
    return reps_alvo.strip().lower().endswith("s")


def capturar_obs(obs_atual: str) -> str:
    if obs_atual:
        print(f"   Obs atual: {obs_atual}")
    nova = ask("   Obs (adicionar): ", "")
    if nova:
        return f"{obs_atual}; {nova}" if obs_atual else nova
    return obs_atual


# ── Peso corporal ────────────────────────────────────────────────────────────

def ask_peso_corporal() -> float | None:
    prompt = " Peso corporal (kg, ↵ pula): "
    while True:
        raw = ask(prompt, "")
        if not raw:
            return None
        try:
            valor = float(raw.replace(",", "."))
            if 30 <= valor <= 300:
                return valor
        except ValueError:
            pass
        prompt = " Valor inválido. Peso corporal (kg, ↵ pula): "


def registrar_peso_corporal(data_str: str, horario: str, peso_kg: float, refeicao: str) -> None:
    path = TREINOS_DIR / "peso_corporal.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    novo = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["data", "horario", "peso_kg", "refeicao"])
        if novo:
            writer.writeheader()
        writer.writerow({"data": data_str, "horario": horario, "peso_kg": peso_kg, "refeicao": refeicao})


# ── Descanso (cronômetro passivo) ───────────────────────────────────────────────

def parse_descanso(s: str) -> int:
    """Parse '60-90' or '90' into a single rest duration in seconds."""
    nums = [int(p) for p in s.replace("s", "").split("-") if p.strip().isdigit()]
    return sum(nums) // len(nums) if nums else 60


def iniciar_descanso(segundos: int) -> dict:
    """Start a passive rest stopwatch in the background. Never blocks input —
    RIR (current set) and peso (next set) prompts keep working normally while
    this counts; the real elapsed time is only read back via finalizar_descanso."""
    stop_event = threading.Event()
    inicio = time.time()

    def _avisar() -> None:
        if not stop_event.wait(segundos):
            sys.stdout.write(f"\n   ⏰ já se passaram {segundos}s de descanso\n")
            sys.stdout.flush()

    threading.Thread(target=_avisar, daemon=True).start()
    return {"inicio": inicio, "stop_event": stop_event}


def finalizar_descanso(cronometro: dict) -> float:
    cronometro["stop_event"].set()
    return time.time() - cronometro["inicio"]


def fmt_mmss(segundos: float) -> str:
    m, s = divmod(int(segundos), 60)
    return f"{m}min{s:02d}s" if m else f"{s}s"


def avaliacao_descanso(real: float, alvo: int) -> str:
    diff = real - alvo
    if diff <= 5:
        return "  ✓ dentro do alvo"
    if diff <= 30:
        return "  → um pouco acima do alvo"
    return "  → muito acima do alvo, ficou se distraindo?"


# ── Program / phase helpers ───────────────────────────────────────────────────

def get_fase_idx(prog: dict, semana_treino: int) -> tuple[int, int]:
    acumulado = 0
    for i, fase in enumerate(prog["fases"]):
        acumulado += fase["semanas"]
        if semana_treino <= acumulado:
            return i, semana_treino - (acumulado - fase["semanas"])
    ultimo = len(prog["fases"]) - 1
    return ultimo, prog["fases"][ultimo]["semanas"]


def check_deload(fase: dict, semana_na_fase: int) -> bool:
    iv = fase.get("deload_a_cada_semanas", 0)
    return iv > 0 and semana_na_fase % iv == 0


def programa_concluido(prog: dict, semana_treino: int) -> bool:
    return semana_treino > sum(f["semanas"] for f in prog["fases"])


def get_proximo_treino(csv_path: Path, semana_treino: int) -> str:
    if not csv_path.exists():
        return "A"
    feitos: set[str] = set()
    ultimo = "B"
    with open(csv_path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            ultimo = r.get("treino", "B")
            if int(r.get("semana_treino", 0)) == semana_treino:
                feitos.add(r.get("treino", ""))
    if "A" not in feitos: return "A"
    if "B" not in feitos: return "B"
    return "B" if ultimo == "A" else "A"


# ── Week progression ──────────────────────────────────────────────────────────

def count_sessions_week(csv_path: Path, semana_treino: int) -> int:
    if not csv_path.exists():
        return 0
    pares: set[tuple[str, str]] = set()
    with open(csv_path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if int(r.get("semana_treino", 0)) == semana_treino:
                pares.add((r["data"], r["treino"]))
    return len(pares)


def check_missed_weeks(cfg: dict, prog: dict, fase_idx: int, csv_path: Path) -> str | None:
    if not cfg.get("ultima_sessao"):
        return None
    hoje  = date.today()
    ini   = parse_date(cfg.get("semana_treino_inicio", cfg["ultima_sessao"]))
    dias  = (hoje - ini).days
    if dias <= 7:
        return None

    fase = prog["fases"][fase_idx]
    if count_sessions_week(csv_path, cfg["semana_treino"]) >= fase.get("frequencia_semanal", 2):
        return None

    novas = dias // 7
    total = cfg.get("semanas_perdidas", 0) + novas
    cfg["semana_treino_inicio"] = fmt(hoje)

    if total >= 2:
        if fase_idx > 0:
            antes = sum(f["semanas"] for f in prog["fases"][: fase_idx - 1])
            cfg["semana_treino"] = antes + 1
        else:
            cfg["semana_treino"] = 1
        cfg["semanas_perdidas"] = 0
        save_config(cfg)
        nova = prog["fases"][get_fase_idx(prog, cfg["semana_treino"])[0]]
        return f"[!] {total} semanas incompletas → Fase {nova['numero']}: {nova['nome']}"

    cfg["semanas_perdidas"] = total
    save_config(cfg)
    return f"[!] Semana incompleta ({total}/2 para retrogradar)"


def update_week_progress(
    cfg: dict, prog: dict, fase_idx: int, csv_path: Path, data_reg: date
) -> str | None:
    semana = cfg["semana_treino"]
    freq   = prog["fases"][fase_idx].get("frequencia_semanal", 2)
    if count_sessions_week(csv_path, semana) < freq:
        return None

    cfg["semana_treino"]        += 1
    cfg["semanas_perdidas"]      = 0
    cfg["semana_treino_inicio"]  = fmt(data_reg)
    save_config(cfg)

    new_fi, semana_na_fase = get_fase_idx(prog, cfg["semana_treino"])
    if new_fi > fase_idx:
        nova = prog["fases"][new_fi]
        return (
            f"Semana {semana} completa! → Fase {nova['numero']}: {nova['nome']}\n"
            f"RIR alvo: {nova.get('rir_alvo','?')}  ·  "
            f"Descanso: {nova.get('descanso_segundos','?')}s"
        )
    return f"Semana {semana} completa! → semana {semana_na_fase} da fase atual"


# ── Registrar treino ──────────────────────────────────────────────────────────

def registrar_treino(cfg: dict, prog: dict, fase_idx: int, tipo: str, data_reg: date) -> None:
    fase      = prog["fases"][fase_idx]
    exercicios = fase.get("treinos", {}).get(tipo, [])
    if not exercicios:
        print(f" Nenhum exercício definido para Treino {tipo} nesta fase.")
        return

    semana      = cfg["semana_treino"]
    rir_alvo    = fase.get("rir_alvo", 4)
    descanso    = fase.get("descanso_segundos", "60-90")
    descanso_seg = parse_descanso(descanso)

    print()
    sep()
    print(f" Treino {tipo}  ·  {fase['nome']}  ·  {fmt(data_reg)}")
    print(f" RIR alvo: {rir_alvo}  ·  Descanso: {descanso}s")
    sep()

    # ── Peso corporal (antes de beber água) ─────────────────────────────────────
    print()
    peso_corp = ask_peso_corporal()
    if peso_corp is not None:
        horario  = datetime.now().strftime("%H:%M")
        refeicao = ask(" Refeição antes (ex: jejum, 2h atrás, ↵ pula): ", "")
        registrar_peso_corporal(fmt(data_reg), horario, peso_corp, refeicao)

    # ── Pré-treino ────────────────────────────────────────────────────────────
    print()
    prs_str  = ask(" PRS       (0–10, ↵ pula): ", "")
    prs      = int(prs_str) if prs_str.isdigit() else ""
    if prs != "" and int(prs) <= 3:
        print(" [!] PRS baixo — considere reduzir volume ou intensidade.")

    sono_r   = ask(" Sono      (o b r p,   ↵ pula): ", "").lower()
    sono     = SONO_OPTS.get(sono_r, sono_r) if sono_r else ""

    est_r    = ask(" Estresse  (b m a,     ↵ pula): ", "").lower()
    estresse = ESTRESSE_OPTS.get(est_r, est_r) if est_r else ""
    print()

    rows: list[dict] = []

    pendentes = list(exercicios)
    total     = len(exercicios)

    while pendentes:
        sep()
        print(f" Pendentes ({len(pendentes)}/{total} restantes):")
        for i, ex in enumerate(pendentes, 1):
            print(f"  {i}. {ex['exercicio']}  ·  {ex.get('series',3)} × {ex.get('reps_alvo','8-12')}")
        print()
        escolha = ask(" Qual fazer agora (número): ")
        try:
            idx = int(escolha) - 1
            assert 0 <= idx < len(pendentes)
        except (ValueError, AssertionError):
            print(" Opção inválida.")
            continue

        ex          = pendentes.pop(idx)
        nome_ex     = ex["exercicio"]
        series_alvo = ex.get("series", 3)
        reps_alvo   = ex.get("reps_alvo", "8-12")
        musculo     = ex.get("musculo", "")

        sep()
        print(f" {nome_ex}  ·  {series_alvo} × {reps_alvo}")

        eh_tempo = is_exercicio_tempo(reps_alvo)
        if eh_tempo:
            peso_sug = None
        else:
            peso_sug, sug_msg = suggest_peso(nome_ex, rir_alvo)
            if peso_sug is not None:
                print(f" ↳ Sugerido: {peso_sug:.1f} kg  ({sug_msg})")
            else:
                print(f" ↳ {sug_msg}")
        print()

        campos = ("tempo",) if eh_tempo else ("peso", "reps", "rir")
        sets_data: list[dict] = [dict.fromkeys(campos) for _ in range(series_alvo)]
        row_idx_by_set: list[int | None] = [None] * series_alvo
        obs_draft  = ""
        cronometro = None
        s_idx, f_idx = 0, 0

        while s_idx < series_alvo:
            campo = campos[f_idx]
            s = s_idx + 1

            if f_idx == 0:
                print(f"   Série {s}/{series_alvo}")
            if f_idx == 0 and cronometro is not None:
                real = finalizar_descanso(cronometro)
                cronometro = None
                print(f"   ↳ Descanso real: {fmt_mmss(real)} (alvo {descanso_seg}s){avaliacao_descanso(real, descanso_seg)}")

            info = CAMPO_INFO[campo]
            default_val = sets_data[s_idx - 1][campo] if s_idx > 0 else None
            sufixo = f" [{default_val}]" if default_val is not None else ""
            raw = ask(f"     {info['label']}{sufixo} (- corrige, obs anota): ", "").strip()

            if raw == "-":
                if cronometro is not None:
                    cronometro["stop_event"].set()
                    cronometro = None
                if f_idx == 0:
                    if s_idx == 0:
                        print(" Não há nada anterior pra corrigir.")
                        continue
                    s_idx -= 1
                    f_idx = len(campos) - 1
                else:
                    f_idx -= 1
                continue

            if raw.lower() == "obs":
                obs_draft = capturar_obs(obs_draft)
                continue

            if raw == "":
                if default_val is None:
                    print(" Valor obrigatório — digite algo.")
                    continue
                valor = default_val
            else:
                try:
                    valor = info["caster"](raw)
                    if not (info["min"] <= valor <= info["max"]):
                        raise ValueError
                except ValueError:
                    print(" Valor inválido — tente novamente.")
                    continue

            sets_data[s_idx][campo] = valor

            if campo in ("reps", "tempo") and s_idx + 1 < series_alvo:
                cronometro = iniciar_descanso(descanso_seg)

            if f_idx < len(campos) - 1:
                f_idx += 1
                continue

            # série completa
            if eh_tempo:
                reps_feitas, peso_kg, rir_val = sets_data[s_idx]["tempo"], 0.0, ""
            else:
                reps_feitas = sets_data[s_idx]["reps"]
                peso_kg     = sets_data[s_idx]["peso"]
                rir_val     = sets_data[s_idx]["rir"]
                fb = set_feedback(rir_val, rir_alvo)
                if fb:
                    print(f"   {fb}")
            print()

            row = {
                "data":          fmt(data_reg),
                "semana_treino": semana,
                "fase":          fase["numero"],
                "treino":        tipo,
                "prs":           prs,
                "sono":          sono,
                "estresse":      estresse,
                "exercicio":     nome_ex,
                "serie":         s,
                "reps_feitas":   reps_feitas,
                "peso_kg":       peso_kg,
                "rir":           rir_val,
                "session_rpe":   "",
                "detalhes":      musculo,
            }
            if row_idx_by_set[s_idx] is None:
                rows.append(row)
                row_idx_by_set[s_idx] = len(rows) - 1
            else:
                rows[row_idx_by_set[s_idx]] = row

            s_idx += 1
            f_idx = 0

        if obs_draft:
            print(f" Obs anotadas: {obs_draft}")
        extra = ask(" Obs (opcional, enter mantém): ", "")
        obs_final = f"{obs_draft}; {extra}" if (obs_draft and extra) else (extra or obs_draft)
        if obs_final:
            rows[-1]["detalhes"] = obs_final
        print()

    # ── Session RPE ───────────────────────────────────────────────────────────
    sep()
    srpe = ask(" Session RPE  (0–10, ↵ pula): ", "")
    if srpe.isdigit():
        for r in rows:
            r["session_rpe"] = int(srpe)

    # ── Gravar CSV ────────────────────────────────────────────────────────────
    csv_path = csv_path_for(data_reg)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    novo = not csv_path.exists()
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
        if novo:
            writer.writeheader()
        writer.writerows(rows)

    cfg["ultima_sessao"] = fmt(data_reg)
    if not cfg.get("semana_treino_inicio"):
        cfg["semana_treino_inicio"] = fmt(data_reg)
    save_config(cfg)

    volume  = sum(r["reps_feitas"] * r["peso_kg"] for r in rows)
    rirs    = [r["rir"] for r in rows if isinstance(r["rir"], int)]
    avg_rir = sum(rirs) / len(rirs) if rirs else None

    semana_msg = update_week_progress(cfg, prog, fase_idx, csv_path, data_reg)

    print()
    sep()
    print(f" Treino {tipo} concluído  ·  {fmt(data_reg)}")
    sep()
    print(f" {'Séries':<12}{len(rows)}  ·  Volume: {volume:.0f} kg·rep")
    if avg_rir is not None:
        diff = avg_rir - rir_alvo
        if diff > 1.5:   assessment = "→ treino fácil — aumente cargas no próximo"
        elif diff > 0.5: assessment = "→ levemente fácil — considere +2.5 kg"
        elif diff >= -0.5: assessment = "✓ no alvo"
        elif diff >= -1.5: assessment = "→ treino pesado — mantenha as cargas"
        else:              assessment = "→ muito pesado — considere reduzir"
        print(f" {'RIR médio':<12}{avg_rir:.1f}  (alvo {rir_alvo})  {assessment}")
    srpe = rows[0].get("session_rpe", "")
    if srpe != "":
        print(f" {'Session RPE':<12}{srpe}")
    if semana_msg:
        print()
        for ln in semana_msg.splitlines():
            print(f" {ln}")
    sep()


# ── Análise de progresso ──────────────────────────────────────────────────────

def analise_progresso(data_ref: date) -> None:
    csv_path = csv_path_for(data_ref)
    if not csv_path.exists():
        print("\n Nenhum dado registrado ainda.")
        return

    with open(csv_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print("\n Nenhum dado registrado ainda.")
        return

    sets_mus: dict[str, dict[int, int]] = {}
    carga_ex: dict[str, list[tuple[str, float]]] = {}

    for r in rows:
        ex      = r["exercicio"]
        musculo = r.get("detalhes") or ex
        semana  = int(r["semana_treino"])
        try:
            peso = float(r["peso_kg"])
        except (ValueError, KeyError):
            peso = 0.0
        sets_mus.setdefault(musculo, {}).setdefault(semana, 0)
        sets_mus[musculo][semana] += 1
        if peso > 0:
            carga_ex.setdefault(ex, []).append((r["data"], peso))

    semanas = sorted({s for v in sets_mus.values() for s in v})

    print()
    sep()
    print(" Volume  (sets · músculo · semana de treino)")
    sep()
    cw = max(4, *(len(str(s)) + 3 for s in semanas))
    print(f" {'Músculo':<26}" + "".join(f" S{s:<{cw-2}}" for s in semanas))
    print(" " + "─" * (_COLS - 1))
    for mus, dados in sorted(sets_mus.items()):
        print(f" {mus:<26}" + "".join(f" {dados.get(s,0):<{cw-1}}" for s in semanas))

    print()
    sep()
    print(" Progressão de carga por exercício")
    sep()
    for ex, reg in sorted(carga_ex.items()):
        pesos = [p for _, p in reg]
        delta = pesos[-1] - pesos[0]
        sinal = "+" if delta >= 0 else ""
        print(f" {ex:<36}  {pesos[0]:.1f} → {pesos[-1]:.1f} kg  ({sinal}{delta:.1f})")
    sep()


# ── Ver programa ──────────────────────────────────────────────────────────────

def ver_programa(prog: dict, fase_idx: int) -> None:
    fase  = prog["fases"][fase_idx]
    total = len(prog["fases"])
    print()
    sep()
    print(f" Fase {fase['numero']}/{total}  ·  {fase['nome']}")
    print(f" {fase.get('split','')}"
          f"  ·  {fase['semanas']} semanas  ·  {fase.get('frequencia_semanal',2)}x/sem")
    print(f" RIR alvo: {fase.get('rir_alvo','?')}  ·  RPE alvo: {fase.get('rpe_alvo','?')}")
    if fase.get("nota"):
        print(f" {fase['nota']}")
    sep()
    for tipo, exercicios in fase.get("treinos", {}).items():
        print(f" Treino {tipo}")
        for ex in exercicios:
            peso_sug, _ = suggest_peso(ex["exercicio"], fase.get("rir_alvo", 4))
            sug = f"  [{peso_sug:.1f} kg]" if peso_sug else ""
            print(
                f"   {ex['exercicio']:<40}"
                f"  {ex.get('series',3)}×{ex.get('reps_alvo','?')}"
                f"{sug}"
            )
        print()
    sep()


# ── Menu principal ────────────────────────────────────────────────────────────

def menu_principal() -> None:
    data_atual = date.today()

    while True:
        cfg  = load_config()
        prog = load_programa(cfg["programa_ativo"])
        csv_path = csv_path_for(data_atual)

        fase_idx, semana_na_fase = get_fase_idx(prog, cfg["semana_treino"])
        fase   = prog["fases"][fase_idx]
        freq   = fase.get("frequencia_semanal", 2)
        n_sess = count_sessions_week(csv_path, cfg["semana_treino"])
        proximo = get_proximo_treino(csv_path, cfg["semana_treino"])
        deload  = check_deload(fase, semana_na_fase)
        fim     = programa_concluido(prog, cfg["semana_treino"])

        aviso = check_missed_weeks(cfg, prog, fase_idx, csv_path)
        cfg = load_config()  # reload after potential mutation
        fase_idx, semana_na_fase = get_fase_idx(prog, cfg["semana_treino"])
        fase = prog["fases"][fase_idx]

        print()
        sep()
        titulo = f" GymTracker  ·  {cfg['atleta']}"
        if TEST_MODE:
            titulo += " " * max(1, _COLS - len(titulo) - 7) + "[TESTE]"
        print(titulo)
        sep()
        print(f" {'Programa':<10}{prog['nome']}")
        print(f" {'Fase':<10}{fase['numero']}/7  ·  {fase['nome']}  ·  Sem {semana_na_fase}")
        print(f" {'Sessões':<10}{dots(n_sess, freq)}  {n_sess}/{freq}  ·  RIR alvo: {fase.get('rir_alvo','?')}")
        print(f" {'Próximo':<10}Treino {proximo}  ·  {fmt(data_atual)}")

        if aviso or deload or fim:
            print()
        if aviso:
            print(f" {aviso}")
        if deload:
            print(f" [DELOAD] 50% do volume — mantenha a carga")
        if fim:
            print(f" [!] Programa concluído!")

        sep()
        print(" 0  análise de progresso")
        print(" 1  registrar treino")
        print(" 2  ver programa")
        print(" 3  alterar programa")
        print(" 4  alterar data")
        print(" 9  sair")
        sep()

        opcao = ask("\nOpção: ")

        if opcao == "0":
            analise_progresso(data_atual)

        elif opcao == "1":
            registrar_treino(cfg, prog, fase_idx, proximo, data_atual)
            break

        elif opcao == "2":
            ver_programa(prog, fase_idx)

        elif opcao == "3":
            progs = sorted(p.stem for p in PROGRAMAS_DIR.glob("*.json"))
            print()
            sep()
            print(" Programas disponíveis")
            sep()
            for i, p in enumerate(progs, 1):
                marker = "  ←" if p == cfg["programa_ativo"] else ""
                print(f" {i}  {p}{marker}")
            sep()
            escolha = ask("\nNúmero: ")
            try:
                cfg["programa_ativo"] = progs[int(escolha) - 1]
                save_config(cfg)
                print(f" Programa: {cfg['programa_ativo']}")
            except (ValueError, IndexError):
                print(" Opção inválida.")

        elif opcao == "4":
            nova = ask(" Data (DD/MM/AA): ")
            try:
                data_atual = parse_date(nova)
                print(f" Data: {fmt(data_atual)}")
            except ValueError:
                print(" Formato inválido. Ex: 15/05/26")

        elif opcao == "9":
            break


if __name__ == "__main__":
    menu_principal()
