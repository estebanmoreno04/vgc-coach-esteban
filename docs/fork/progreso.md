# Progreso del fork — VGC Coach (Esteban)

_Actualizado: 21 de octubre de 2026 (tras la Fase 5). Fork de [NoahJenkins/vgc-coach](https://github.com/NoahJenkins/vgc-coach) (Apache-2.0) en `E:\VGC\vgc-coach-esteban`._

## Objetivo

Un coach de Pokémon Champions VGC que **siempre trabaja con la regulación vigente y cambia solo de regulación** sin tocar código ni configuración, centrado en el **meta de torneos presenciales** (regionales europeos con open team lists).

## Estado de las fases

| Fase | Qué es | Estado | Commit |
|---|---|---|---|
| 0 | Auditoría del repo e investigación de fuentes | ✅ Hecha | — |
| 1 | Resolver de regulación | ✅ Hecha | `565a7c9` |
| 2 | Pipeline de meta (snapshot) | ✅ Hecha | `85379f3` |
| 3 | Skills adaptadas + `vgc-refresh` + consultas | ✅ Hecha | `2d3bfe1` |
| 4 | Calculadora de daño (`@smogon/calc`) | ✅ Hecha | `19736aa` (4a), `f430c36` (4b) |
| 5 | GitHub Action semanal (lunes, hora de Madrid) | ✅ Hecha | `23edff3` |
| 6 | Prueba de aceptación (cambio de regulación simulado + auditoría de tu equipo) | ⏸️ Pendiente | — |
| 7 (extra) | Coach para amigos sin Claude Code | ⏸️ Pendiente | — |

Todo está **subido a GitHub** (fork `estebanmoreno04/vgc-coach-esteban`, rama `main`). Los commits usan tu email privado de GitHub (`145461032+estebanmoreno04@users.noreply.github.com`), no tu Gmail.

## Cómo funciona ahora

```
Fuentes ──► tools/resolve_regulation.py ──► data/current/regulation.json
                                                  │
Torneos ──► tools/build_snapshot.py ─────► data/current/snapshot.json
                                                  │
                     tools/meta_query.py  ◄───────┘  (lo usan las skills)
                     tools/vgc_refresh.py  (resolver + pipeline + plugins + resumen de cambios)
                     tools/damage_calc.py  (calc exacta con @smogon/calc)
```

### 1. Resolver de regulación
- Consulta 5 fuentes:
  1. noticias oficiales del juego (`champions-news.pokemon-home.com`, como mucho una vez por semana);
  2. VGC History;
  3. API de Limitless;
  4. Victory Road;
  5. Pikalytics.
- **Reglas:**
  - si la ventana oficial contiene la fecha de hoy, gana;
  - si no, hace falta consenso: al menos 2 fuentes y mayoría;
  - si las fuentes no coinciden, mantiene la regulación anterior con `confidence: low`;
  - si caen todas, mantiene la última conocida y la marca `stale`.
- Una regulación anunciada pero aún no activa se guarda como `next_regulation`.
- **Si cambia la regulación**, todo `data/current/` pasa a `data/archive/<regulación anterior>/` y no vuelve a usarse.
- Ningún ID de regulación está escrito en código, prompts ni config. Un test-guardia lo comprueba.

### 2. Pipeline de meta
- **Presencial primero:** VGC History (field completo, récords, team sheets y emparejamientos ronda a ronda), con limitlessvgc.com como respaldo.
- **Online como complemento:** API de Limitless, solo torneos de ≥64 jugadores de las últimas 4 semanas.
- **Qué calcula:**
  - uso presencial, online y total;
  - win rate;
  - % de uso en día 2 y conversión a día 2;
  - Megas;
  - parejas y tríos;
  - sets habituales;
  - emparejamientos según las team sheets;
  - equipos del top cut.
- La descarga es incremental: guarda cada evento comprimido y no repite los ya procesados.

### 3. Skills
- `vgc-meta-research`, `vgc-team-builder`, `vgc-team-audit`, `vgc-lead-planner`, `vgc-opponent-scout` y `vgc-format-verifier`:
  - leen `data/current` primero;
  - dicen siempre la regulación y la antigüedad de los datos;
  - avisan y proponen refrescar si el snapshot tiene más de 7 días o es *early meta*;
  - nunca usan `data/archive/`.
- **Skill nueva `vgc-refresh`:** actualiza todo y resume los eventos nuevos, quién sube y quién baja en uso, y los equipos nuevos en top cut.

### 4. Calculadora
- `tools/damage_calc.py` con `@smogon/calc` 0.12.0 y la mecánica de Champions.
- Calcula **daño, KO, supervivencia y velocidad exactos**, verificados contra el cálculo a mano.
- La calc de Pikalytics de Noah queda como respaldo.

## Fuentes (decisiones aprobadas)

| Fuente | Uso |
|---|---|
| Noticias oficiales del juego (JSON) | Regulación, fechas exactas, mecánicas, timers (lectura semanal) |
| VGC History | Principal presencial (permite reutilizar los datos con crédito) |
| limitlessvgc.com | Respaldo presencial (equipos de día 2) |
| API de Limitless | Online (≥64 jugadores) |
| Pikalytics | Sets complementarios y señal de regulación |
| Victory Road | Fechas de regulación (editorial) |
| pokemon.com, RK9, pokedata.ovh, pokemon-zone, Champions Lab, championsmeta, pokebase | **Solo navegación manual** |

## Datos reales actuales (regulación M-C)

- **Presencial:** 6 regionales (Baltimore, Frankfurt, Brisbane, Recife, Louisville y Nice), con 4.632 equipos del field completo y 664 de día 2.
- **Online:** 52 torneos, con 4.997 equipos.
- **Top 5 de uso presencial:**
  1. Rillaboom: 50,9 %
  2. Sneasler: 38,6 %
  3. Incineroar: 33,9 %
  4. Raichu: 27,7 %
  5. Garchomp: 26,7 %

## Actualización automática (Fase 5)

- **Cuándo:** cada lunes a las 06:00 UTC (07:00 en Madrid en invierno, 08:00 en verano), con la Action **Weekly Data Refresh**.
- **A mano:** pestaña **Actions** del repo → "Weekly Data Refresh" → "Run workflow".
- **Qué hace:**
  1. detecta la regulación;
  2. descarga los torneos nuevos;
  3. reconstruye el snapshot, los plugins y los datos de la web;
  4. valida;
  5. si hay cambios, hace commit;
  6. si ha cambiado la regulación, **abre un issue** para avisarte.
- **En local, con un comando:** `python tools/run_weekly.py`.

## Comandos útiles

En Windows, usa `python` o `py -3` en lugar de `python3`, y activa antes el venv (`.venv`).

```bash
python tools/meta_query.py status                 # regulación y antigüedad de los datos
python tools/meta_query.py usage --top 20         # uso presencial (--segment online|total)
python tools/meta_query.py pokemon "Kingambit"    # ficha completa de un Pokémon
python tools/meta_query.py team --file equipo.txt # tu equipo frente al meta
python tools/vgc_refresh.py                       # actualizar todo y ver qué ha cambiado
python tools/damage_calc.py --request-file calc.json --pretty
```

## Cosas a tener en cuenta

1. **Skills en Windows:** git ha descargado los enlaces de `.claude/skills/` como ficheros de texto. Para usar las skills en Claude Code, hay que usar el plugin generado (`plugins/vgc-coach-claude`). Lo dejaremos montado en la Fase 6.
2. **Tests:** hay 13 tests de Noah que fallan solo en Windows (symlinks, procesos POSIX y temporales en otra unidad). En la CI de GitHub (Linux) **todo pasa**: Plugin Package CI y Site CI en verde tras el push del 21-oct.
3. **Identidad de git:** el repo está configurado con tu email privado de GitHub (noreply), así que tu Gmail no aparece en el historial público. Queda una rama local `backup-before-email-rewrite` con los commits antiguos; se puede borrar.
4. **Emparejamientos:** son a nivel de team sheet (qué especies había en cada equipo, no cuáles se sacaron), así que se presentan como orientativos.
5. **Stat points del rival:** no salen en las team sheets; en los cálculos contra rivales son una suposición.
6. **Tamaño del repo:** crece ~2 MB por regulación por los eventos guardados. Al cambiar de regulación se archivan.

## Próximos pasos

- **Fase 6:**
  - simulación del cambio de regulación con fixtures (a una "M-D" ficticia) sin tocar código;
  - prueba real con `vgc-team-audit` y tu equipo (Whimsicott, Kingambit, Charizard-Y, Farigiraf, Kommo-o, Basculegion);
  - README final.
- **Fase 7 (extra, decidida):** coach gratuito para tus amigos. Será una página de chat publicada en claude.ai donde cada persona pregunta con su propia cuenta de Claude, dentro de sus límites (gratuita = menos, de pago = más). A ti no te cuesta nada. Antes hay que verificar que funciona con cuentas gratuitas e invitados.

## Dónde mirar

- Lista de archivos cambiados respecto al original: [`FORK_CHANGES.md`](../../FORK_CHANGES.md)
- Cómo leen las skills los datos actuales: [`docs/skills/shared/references/current-data.md`](../skills/shared/references/current-data.md)
- Configuración del pipeline (sin regulaciones): [`config/vgc-data.yaml`](../../config/vgc-data.yaml)
