# VGC Coach (fork de Esteban)

> **Aviso de fork.** Este repositorio es un fork de [NoahJenkins/vgc-coach](https://github.com/NoahJenkins/vgc-coach), mantenido por [estebanmoreno04](https://github.com/estebanmoreno04) bajo la misma licencia [Apache-2.0](./LICENSE). Los archivos cambiados respecto al original están listados en [FORK_CHANGES.md](./FORK_CHANGES.md), y cada archivo modificado lleva su propio aviso. Créditos de datos: [VGC History](https://vgchistory.com), [Limitless](https://limitlesstcg.com) y [Pikalytics](https://www.pikalytics.com).

VGC Coach es un coach de **Pokémon Champions VGC** que vive dentro de tu asistente de IA (Claude Code, Codex u OpenCode). Le preguntas en lenguaje normal y te ayuda a:
- investigar el meta;
- construir y auditar equipos;
- planificar leads;
- revisar partidas;
- hacer cálculos de daño.

## Qué añade este fork

- **Detecta sola la regulación vigente.** `tools/resolve_regulation.py` la deduce de las noticias oficiales del juego y de fuentes de la comunidad. Ningún ID de regulación está escrito en el código, las skills ni la configuración. Cuando la regulación cambia, los datos anteriores se archivan en `data/archive/` y ya no se usan.
- **Meta de torneos presenciales primero.** `tools/build_snapshot.py` descarga los regionales, internacionales y mundiales de la regulación activa, más los torneos online de ≥64 jugadores como complemento. A partir de ahí calcula:
  - uso presencial, online y total;
  - win rate;
  - % de uso en día 2 y conversión a día 2;
  - Megas;
  - parejas y tríos;
  - sets habituales;
  - emparejamientos según las team sheets;
  - equipos del top cut.
- **Las skills leen esos datos.** Siempre dicen qué regulación usan y de cuándo son los datos, y avisan si están desactualizados.
- **Calculadora exacta** con [`@smogon/calc`](https://github.com/smogon/damage-calc) y la mecánica de Champions: daño, KO, supervivencia y velocidad.
- **Actualización automática cada lunes** con una GitHub Action. Si cambia la regulación, abre un issue para avisarte.

## Instalación

### 1. Requisitos

Necesitas `git`, Python 3.12 y Node.js (LTS). En Windows:

```powershell
winget install --id Git.Git -e
winget install --id Python.Python.3.12 -e
winget install --id OpenJS.NodeJS.LTS -e
```

En macOS: `brew install git python node`. En Debian/Ubuntu: `sudo apt install -y git python3 python3-venv nodejs npm`.

### 2. Clonar y preparar

```bash
git clone https://github.com/estebanmoreno04/vgc-coach-esteban.git
cd vgc-coach-esteban
python -m venv .venv
```

Activa el venv (en Windows `.venv\Scripts\activate`; en macOS/Linux `source .venv/bin/activate`) e instala las dependencias:

```bash
pip install -r tools/requirements-data.txt
cd tools/calc && npm ci && cd ../..
```

### 3. Usarlo en Claude Code

**Opción A: desde el marketplace del fork** (se actualiza solo con los datos de cada lunes):

```bash
claude plugin marketplace add estebanmoreno04/vgc-coach-esteban --sparse .claude-plugin plugins
claude plugin install vgc-coach-claude@vgc-coach
```

Para recibir los datos nuevos: `claude plugin marketplace update vgc-coach` y `claude plugin update vgc-coach-claude@vgc-coach`. Después, una vez, haz `npm ci` en la carpeta `tools/calc` del plugin instalado si quieres la calculadora exacta.

**Opción B: desde tu copia local** (recomendada en Windows):

```bash
claude --plugin-dir ./plugins/vgc-coach-claude
```

> **Windows:** git descarga los enlaces de `.claude/skills/` como ficheros de texto salvo que actives los symlinks (Modo de desarrollador + `git config core.symlinks true`). Por eso, en Windows, usa el plugin (opción A o B) en lugar de abrir el repo tal cual.

Codex y OpenCode también están soportados: [docs/runtime/codex.md](./docs/runtime/codex.md) y [docs/runtime/opencode.md](./docs/runtime/opencode.md).

## Uso

Pídeselo en lenguaje normal, por ejemplo:

- "¿Qué está dominando en los regionales presenciales?"
- "Audita este equipo para el próximo regional", y pegas el equipo en formato Showdown o `Nombre @ Objeto | Habilidad | Naturaleza | Movimiento, ...`.
- "Planifícame los leads contra lluvia y Trick Room."
- "¿Charizard-Mega-Y con Heat Wave bajo sol hace OHKO a Kingambit con 32 HP?"
- "Actualiza los datos y dime qué ha cambiado", que lanza `vgc-refresh`.

### Skills

| Skill | Para qué |
|---|---|
| `vgc-meta-research` | Foto del meta actual (presencial primero), cores, tendencias y huecos anti-meta |
| `vgc-team-builder` | Un equipo práctico alrededor de una idea; modo `battle-ready` con spreads |
| `vgc-team-audit` | Auditoría: hallazgos primero, cambios mínimos, riesgo residual |
| `vgc-lead-planner` | Leads por emparejamiento, objetivos a preservar, prioridades del turno 1 |
| `vgc-opponent-scout` | Preparación contra un rival a partir de información pública |
| `vgc-battle-review` | Revisión de partidas: errores reales frente a varianza |
| `vgc-calcs-assistant` | Cálculos exactos (daño, KO, supervivencia, velocidad) orientados a decisiones |
| `vgc-format-verifier` | Comprueba la regulación, las mecánicas y la legalidad antes de entrenar |
| `vgc-source-verifier` | Comprueba si una afirmación sobre el meta está bien respaldada |
| `vgc-practice-journal` | Convierte notas de práctica en cambios para la próxima sesión |
| `vgc-refresh` | Actualiza la regulación y los torneos, y resume los cambios |

### Comandos útiles

En Windows usa `python` o `py -3` en lugar de `python3`:

```bash
python3 tools/meta_query.py status                  # regulación activa y antigüedad de los datos
python3 tools/meta_query.py usage --top 20          # uso presencial (--segment online|total)
python3 tools/meta_query.py pokemon "Kingambit"     # uso, Megas, sets, compañeros, emparejamientos
python3 tools/meta_query.py top-cut --species Sneasler
python3 tools/meta_query.py team --file equipo.txt  # tu equipo frente al meta
python3 tools/damage_calc.py --request-file calc.json --pretty
python3 tools/vgc_refresh.py                        # actualizar y ver qué ha cambiado
python3 tools/run_weekly.py                         # lo mismo que la Action semanal, con validación
```

## Actualización automática

`.github/workflows/weekly-refresh.yml` se ejecuta **cada lunes a las 06:00 UTC**, es decir, a las 07:00 en Madrid en invierno y a las 08:00 en verano, después de los regionales del fin de semana. También se puede lanzar a mano: **Actions → Weekly Data Refresh → Run workflow**.

Hace lo siguiente:
1. detecta la regulación;
2. descarga los torneos nuevos;
3. reconstruye el snapshot, los plugins y los datos de la web;
4. valida;
5. si hay cambios, hace commit;
6. si ha cambiado la regulación, **abre un issue**.

En local, `python3 tools/run_weekly.py` hace exactamente lo mismo.

## Arquitectura

```
Fuentes oficiales y de la comunidad
        │
        ▼
tools/resolve_regulation.py ──► data/current/regulation.json   (regulación, ventana, mecánicas, timers, URL oficial)
        │                        (si cambia: data/current → data/archive/<anterior>/)
        ▼
tools/build_snapshot.py ──────► data/current/snapshot.json     (+ events/, processed_events.json, pokedex.json)
        │
        ▼
tools/vgc_data/query.py ◄── tools/meta_query.py ◄── skills/*/SKILL.md
tools/damage_calc.py ──► tools/calc/calc.mjs (@smogon/calc, mecánica de Champions)
tools/vgc_refresh.py / tools/run_weekly.py / .github/workflows/weekly-refresh.yml
```

- **`skills/`** es la fuente de verdad de las skills, y `plugins/` contiene los paquetes generados con `python3 tools/build_plugins.py build`. No se editan a mano.
- **`config/vgc-data.yaml`** contiene las fuentes y los parámetros, sin ninguna regulación escrita.
- **`docs/skills/shared/references/current-data.md`** explica cómo leen las skills los datos actuales.
- **`docs/fork/`** guarda el progreso del fork y la auditoría de ejemplo.

### Fuentes

| Fuente | Uso | Acceso |
|---|---|---|
| Noticias oficiales del juego (`champions-news.pokemon-home.com`) | Regulación, fechas exactas, mecánicas, timers | Automático, como mucho una vez por semana |
| VGC History | Torneos presenciales: field completo, team sheets, emparejamientos | Automático (los datos se pueden reutilizar con crédito) |
| limitlessvgc.com | Respaldo presencial (equipos de día 2) | Automático, con caché |
| API de Limitless | Torneos online de ≥64 jugadores | Automático (API documentada) |
| Pikalytics | Sets y señal de regulación | Automático (endpoints para agentes) |
| Victory Road | Fechas de regulación y contexto | Automático |
| pokemon.com, RK9, pokedata.ovh, pokemon-zone, Champions Lab, championsmeta, pokebase | — | **Solo navegación manual** (sus términos o su robots.txt no permiten automatizar, o no están disponibles) |

Todo el acceso automático respeta robots.txt, espera entre peticiones e identifica al cliente.

## Validación

```bash
python3 tools/validate.py --scope core   # tests + chequeos de registry, frescura, battle-state y plugins
python3 tools/validate.py                # además la web (requiere pnpm)
```

La CI de GitHub ejecuta la validación en cada push. En Windows, algunos tests del proyecto original se saltan con el motivo indicado: los que necesitan procesos POSIX, crear symlinks o una carpeta temporal en la misma unidad que el repo. En la CI se ejecutan todos.

## Límites conocidos

- Los emparejamientos son a nivel de team sheet: cuentan qué especies había en cada equipo, no cuáles se sacaron. Son orientativos.
- Las team sheets no publican los stat points, así que en los cálculos contra rivales son un supuesto declarado.
- Con pocos torneos de una regulación nueva, el snapshot se marca `early_meta` y las skills lo avisan.

## Próximamente

- **Coach para amigos sin Claude Code:** una página de chat publicada en claude.ai donde cada persona pregunta con su propia cuenta de Claude (gratuita o de pago), usando los mismos datos.

## Licencia y créditos

Apache-2.0 (ver [LICENSE](./LICENSE)). El proyecto original es obra de [Noah Jenkins](https://github.com/NoahJenkins/vgc-coach), y este fork conserva su licencia y su arquitectura. Los datos de torneos pertenecen a sus respectivas fuentes, citadas arriba. Pokémon y sus nombres son marcas de Nintendo, Game Freak, Creatures y The Pokémon Company; este proyecto no está afiliado a ellas.

Más información: [CONTRIBUTING.md](./CONTRIBUTING.md), [SECURITY.md](./SECURITY.md), [AGENTS.md](./AGENTS.md) y [RELEASE_NOTES.md](./RELEASE_NOTES.md).
