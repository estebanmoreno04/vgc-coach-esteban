# Coach para amigos (página en claude.ai)

Fase 7 del fork. Una página de chat publicada como artefacto de claude.ai. Cada persona que la abre pregunta con **su propia cuenta de Claude**, así que el uso cuenta para sus límites (cuenta gratuita = menos mensajes, de pago = más) y a ti no te cuesta nada.

**URL:** https://claude.ai/artifact/TqpcPXEVGe6RwuLU9geSAn

## Qué hace

- **Chat:** Claude responde con los datos del snapshot de la regulación vigente, presencial primero y online como complemento. Tiene 10 funciones de consulta dentro de la página: estado, uso, tendencia (últimos regionales frente a los anteriores), un regional concreto, ficha de un Pokémon (con su uso en cada regional), emparejamientos, top cut, auditoría de equipo (pegado en formato Showdown), cálculo de daño y comparación de velocidad (`@smogon/calc` 0.12.0 con mecánicas de Champions).
- **Meta:** cuatro recuadros: uso general (presencial, online o total, con Megas), tendencia (qué sube y qué baja en los últimos regionales), torneos presenciales y torneos online. Cada recuadro abre su sección, y cada torneo (regional u online) se abre por separado con su uso, Megas y mejores equipos. La tendencia incluye una gráfica con el uso de cada Pokémon en los últimos 5 regionales: por defecto los 20 más usados, con color para 8 de ellos; se pueden añadir o quitar Pokémon y darles o quitarles color, y al pasar el ratón por una línea dice cuál es. Los Pokémon llevan su sprite (de Pokémon Showdown).
- Cada respuesta indica en qué datos se basa. Si los datos tienen más de 7 días o la regulación es muy nueva, la página lo avisa.
- Selector de modo: Rápido / Equilibrado / A fondo (A fondo gasta más límite).
- El coach usa sets contrastados: para amenazas, enfrentamientos y cálculos se basa en los movimientos y objetos que aparecen en equipos presenciales de día 2, y el cálculo de daño avisa si un movimiento nunca ha llegado a día 2 con ese Pokémon.
- Cada visita empieza con el chat limpio. Las conversaciones anteriores se guardan solo en el navegador de cada persona y se abren desde **Historial**; **Nuevo chat** empieza otra.

## Cómo compartirla

1. Abre la URL, pulsa **Compartir** arriba a la derecha y da acceso a tus amigos (por email o con enlace, según lo que permita tu cuenta).
2. La primera vez que alguien pregunta, claude.ai le pide permiso para "Usar Claude" con su cuenta. Tiene que aceptar.
3. Necesitan iniciar sesión en claude.ai. Si alguien no puede preguntar (el botón no responde o sale "no disponible"), es que su cuenta o su forma de acceso no permite usar Claude desde artefactos: dímelo y lo revisamos.

## Cómo actualizarla

La página lleva dentro una copia de los datos y **no se actualiza sola**. La GitHub Action semanal actualiza `data/current/`, pero la página hay que volver a publicarla:

1. `git pull` para traer los datos nuevos (o `python tools/vgc_refresh.py`).
2. `python tools/fetch_sprites.py` (descarga solo los sprites que falten, a `data/cache/sprites`, que no se sube a git).
3. `python tools/build_coach_page.py` (genera `.artifacts/coach/coach.html`).
4. En Claude Code: "republica `.artifacts/coach/coach.html` en https://claude.ai/artifact/TqpcPXEVGe6RwuLU9geSAn". Se mantiene la misma URL y los mismos permisos.

Cuando cambie la regulación, el mismo proceso publica los datos de la nueva; la página no nombra ninguna regulación en su código.

## Archivos

- `tools/build_coach_page.py`: exporta un resumen compacto de `data/current` y lo inserta en la plantilla.
- `tools/coach_page/template.html`: la página (chat, hoja de meta, estilos).
- `tools/fetch_sprites.py`: descarga y guarda en caché los sprites de Pokémon Showdown.
- `tools/coach_page/core.js`: consultas, auditoría, cálculos e instrucciones del coach (mismo comportamiento que `tools/vgc_data/query.py`).
- `tests/test_coach_page.py`, `tests/coach_core_harness.cjs`: tests con fixtures (el de Node se salta si no está instalado).
