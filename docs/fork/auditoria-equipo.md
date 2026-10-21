# Auditoría del equipo — prueba real de la Fase 6

_Generada con la skill `vgc-team-audit` (siguiendo `skills/vgc-team-audit/SKILL.md` y sus referencias), los datos de `data/current/` vía `tools/meta_query.py` y la calculadora `tools/damage_calc.py`._

```
Whimsicott @ Focus Sash | Prankster | Timid | Tailwind, Moonblast, Encore, Protect
Kingambit @ Chople Berry | Defiant | Adamant | Protect, Sucker Punch, Kowtow Cleave, Iron Head
Charizard @ Charizardite Y | Blaze | Modest | Protect, Weather Ball, Heat Wave, Solar Beam
Farigiraf @ Sitrus Berry | Armor Tail | Bold | Trick Room, Psychic, Thunderbolt, Helping Hand
Kommo-o @ Life Orb | Soundproof | Modest | Protect, Aura Sphere, Clanging Scales, Draco Meteor
Basculegion @ Mystic Water | Adaptability | Adamant | Wave Crash, Last Respects, Aqua Jet, Protect
```

**Base de datos.**
- **Regulación:** M-C (Regulation Set M-C), del 09-sep-2026 02:00 UTC al 02-dic-2026 01:59 UTC. Mecánica activa: Mega Evolución. No se permiten objetos duplicados (tu equipo cumple).
- **Snapshot:** generado el 21-oct-2026 (0 días), con datos hasta el 19-oct-2026. No es *early meta*.
- **Presencial:** 6 regionales (Baltimore, Frankfurt, Brisbane, Recife, Louisville y Nice), con 4.632 equipos del field completo y 664 de día 2.
- **Online:** 52 torneos de ≥64 jugadores, con 4.997 equipos.
- **Nada nuevo en vivo:** no ha habido regionales posteriores al snapshot. El próximo es Puebla, el 24-oct, y entrará en la actualización automática del lunes.

## Hallazgos principales (Top Findings)

1. **La lluvia es tu peor emparejamiento, y es el arquetipo que ganó Nice.** El 1.º (Fontvieille) y el 4.º (Pio Pero) llevaron Pelipper + Archaludon + Basculegion-F + Golisopod-Mega. Según los emparejamientos de team sheet, Archaludon es la mayor amenaza para tu roster (51,1 % sobre 4.593 partidas).
   - Bajo lluvia, un Archaludon con Electro Shot a +1 hace **OHKO a tu Charizard-Mega-Y (182–214 %)** y **a tu Basculegion (204–241 %)**.
   - Tu Heat Wave con sol solo le quita **55–66 %** a un Archaludon defensivo, que además recupera con Leftovers.
   - Además, Pelipper te quita el sol al entrar.
   - En la práctica: si abres con Charizard contra lluvia, pierdes el turno 1.
2. **Tienes dos modos de control de velocidad y cada uno depende de un único Pokémon.** Tailwind depende de Whimsicott y Trick Room de Farigiraf.
   - Farigiraf es tu slot con peores números: WR presencial 49,8 % y **conversión a día 2 del 12,5 %**, por debajo de la media (~14,3 %). Además, es el único sin Protect; el 62 % de los Farigiraf lo llevan.
   - Cuando un rival le hace Fake Out o lo presiona, el modo Trick Room desaparece.
3. **El set de Kommo-o lleva un movimiento redundante.** Draco Meteor (1,3 % de uso) repite tipo con Clanging Scales (98,7 %), que además es de área.
   - Kommo-o es tu Pokémon con mejores números: WR 54,2 % y **conversión a día 2 del 20,7 %, la mejor del equipo**.
   - Los Kommo-o del field usan Clangorous Soul (71,8 %) o Flamethrower (24,5 %) en ese hueco.
   - Ojo con Mega Floette, que le hace OHKO de sobra (Light of Ruin al 500–592 %).

## Identidad del equipo (Team Identity)

Es **ofensiva de sol con Tailwind**: Whimsicott + Charizard-Mega-Y + Kingambit + Basculegion. Es el mismo núcleo que llevaron **dos top 8 de Nice**, el 5.º (Ko Tsukide) y el 7.º (Piscitelli). Ellos lo completaban con Garchomp y Sneasler; tú lo completas con un plan B de Trick Room (Farigiraf) y un rompedor especial (Kommo-o).

La base es sólida según los datos:
- **Charizard + Kingambit:** tu mejor core, con 55,5 % de WR en presencial (4,1 % de los equipos).
- **Charizard + Farigiraf:** 54,4 % (4,8 %).
- **Basculegion + Kingambit:** 53,1 % (5,1 %).

La identidad es correcta. El problema es que el plan B está poco apoyado, no que el plan A falle.

## Agujeros de emparejamiento (Matchup Holes)

- **Lluvia** (Pelipper 13,6 %, Archaludon 16,7 % y Basculegion-F): pierdes la guerra de climas y tus dos atacantes rápidos caen de un golpe. Tus respuestas son Kommo-o con Aura Sphere (**77–92 %** a Archaludon, 2HKO), Farigiraf con Thunderbolt a Pelipper (4×) y Trick Room, que anula el Swift Swim.
- **Hadas** (Mega Floette 13,2 % de las Megas, Sylveon): castigan a Kommo-o y a Farigiraf, que son sus peores emparejamientos de team sheet (45,2 % y 45,9 %). Tu respuesta limpia es **Kingambit con Iron Head (OHKO a Mega Floette, 117–138 %)**.
- **Incineroar** (33,9 %): aguanta a Charizard (Heat Wave al 22–27 %), pero tu Basculegion con Wave Crash le hace OHKO (176–208 %). Su Intimidate activa a tu Kingambit (Defiant).
- **Sneasler** (38,6 %): incluso con Chople Berry, Close Combat le hace a Kingambit **94–111 % (62,5 % de OHKO)**, y sin la baya le haría un OHKO seguro. Además, Sneasler es más rápido que tu Whimsicott (189 contra 184), aunque el Tailwind con Prankster sale antes por prioridad.

Estos emparejamientos son a nivel de team sheet (qué especies había en cada equipo, no cuáles se sacaron), así que son orientativos.

## Cambios recomendados (Recommended Changes)

De menor a mayor:

1. **Kommo-o: Draco Meteor → Flamethrower** (24,5 % del field). Deja de repetir tipo y daña a aceros comunes como Kingambit (23,7 %) o Gholdengo (25,7 %), que hoy te cuestan. Mantienes Life Orb. Si prefieres el set más ganador del field (45 %), sería Leftovers + Clangorous Soul en lugar de Draco Meteor.
2. **Farigiraf: Helping Hand → Protect.** Así sobrevive al turno 1 contra Fake Out y dobles para poner Trick Room el turno 2. Mantén Psychic para Sneasler (2×) y Thunderbolt para Pelipper (4×).
3. **Plan contra lluvia, en la vista previa:** no abras con Charizard. Abre con Farigiraf + Kommo-o o Kingambit, pon Trick Room, quita a Pelipper con Thunderbolt y presiona a Archaludon con Aura Sphere. Charizard entra después, cuando ya no haya lluvia.
4. **Solo si al probarlo ves que casi nunca usas Trick Room:** Farigiraf → Garchomp. Volverías al arquetipo de los top 8 de Nice, donde Charizard + Garchomp es la pareja de Charizard más común en presencial (10,0 % de los equipos, WR 54,4 %). Llevarlo con Choice Scarf o Focus Sash, porque Life Orb ya la lleva Kommo-o. Es un cambio de identidad, así que lo dejo como último recurso.

## Riesgo residual (Residual Risk)

- La lluvia seguirá siendo incómoda en las partidas donde no puedas montar Trick Room. Esperable: perder ese emparejamiento si te quitan Farigiraf el turno 1.
- Kommo-o y Farigiraf seguirán siendo frágiles contra Mega Floette y Sylveon. Dependes de que Kingambit esté vivo.
- **Supuestos de los cálculos:**
  - Los stat points rivales no salen en las team sheets. He supuesto atacantes con 32 en ataque y 32 en velocidad, y Archaludon defensivo con 32 HP / 32 SpD y naturaleza Calm (o Modest con 32 HP / 32 SpA cuando ataca), y Leftovers.
  - Tus Pokémon llevan 32 en ataque y 32 en velocidad salvo que se indique otra cosa.
  - Con spreads distintos, los números cambian.
- Los datos llegan hasta el 19-oct. La actualización automática del lunes incorporará Puebla (24–25 oct) y lo que pase en online.

## Fuentes

- `data/current/regulation.json` (comprobada el 21-oct-2026; anuncio oficial: https://champions-news.pokemon-home.com/en/page/816.html)
- `data/current/snapshot.json` (generado el 21-oct-2026): VGC History (https://vgchistory.com) para presencial y el API de Limitless para online.
- Cálculos: `tools/damage_calc.py` (`@smogon/calc` 0.12.0, mecánica de Champions).
