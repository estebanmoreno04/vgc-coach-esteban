window.VH = function() {
    const MONS = {
        "raichu-mega-x": { name: "Mega Raichu X", base: "raichu", tfrom: "raichu", ps: "Raichu-Mega-X" },
        "raichu-mega-y": { name: "Mega Raichu Y", base: "raichu", tfrom: "raichu", ps: "Raichu-Mega-Y" },
        "charizard-mega-y": { name: "Mega Charizard Y", base: "charizard", tfrom: "charizard", ps: "Charizard-Mega-Y" },
        "charizard-mega-x": { name: "Mega Charizard X", base: "charizard", tfrom: "charizard", ps: "Charizard-Mega-X" },
        "floette-mega": { name: "Mega Floette", base: "floette", tfrom: "floette-eternal", ps: "Floette-Mega" },
        "floette-eternal": { name: "Eternal Flower Floette", base: "floette", ps: "Floette-Eternal" },
        "golisopod-mega": { name: "Mega Golisopod", base: "golisopod", tfrom: "golisopod", ps: "Golisopod-Mega" },
        "gengar-mega": { name: "Mega Gengar", base: "gengar", tfrom: "gengar", ps: "Gengar-Mega" },
        "basculegion-f": { name: "Female Basculegion", base: "basculegion", ps: "Basculegion-F" },
        "kommo-o": { name: "Kommo-o" }
    };
    const REGS = [ { id: "M-C", game: "Pokémon Champions", tera: false, window: "Sep 2026 – present" } ];
    const T = [ {
        id: "regional-alpha-2027",
        name: "Alpha Regionals 2027",
        full: "Alpha Regional Championships 2027",
        city: "Alpha",
        dates: "October 3–4, 2026",
        reg: "M-C",
        game: "Pokémon Champions",
        tier: "regional",
        players: 8,
        division: "Masters",
        standings: []
    }, {
        id: "regional-beta-2027",
        name: "Beta Regionals 2027",
        full: "Beta Regional Championships 2027",
        city: "Beta",
        dates: "October 10–11, 2026",
        reg: "M-C",
        game: "Pokémon Champions",
        tier: "regional",
        players: 4,
        division: "Masters",
        standings: []
    }, {
        id: "regional-older-2026",
        name: "Older Regionals 2026",
        city: "Older",
        dates: "August 1–2, 2026",
        reg: "M-B",
        game: "Pokémon Champions",
        tier: "regional",
        players: 500,
        division: "Masters"
    }, {
        id: "community-cup-2027",
        name: "Community Cup",
        city: "Delta",
        dates: "October 12, 2026",
        reg: "M-C",
        game: "Pokémon Champions",
        tier: "other",
        players: 90,
        division: "Masters"
    }, {
        id: "regional-future-2027",
        name: "Future Regionals 2027",
        city: "Future",
        dates: "November 28–29, 2026",
        reg: "M-C",
        game: "Pokémon Champions",
        tier: "regional",
        players: 0,
        division: "Masters"
    } ];
    return { MONS: MONS, REGS: REGS, T: T };
}();
