window.VH = function() {
    const MONS = {
        "raichu-mega-x": { name: "Mega Raichu X", base: "raichu", tfrom: "raichu", ps: "Raichu-Mega-X" },
        "floette-mega": { name: "Mega Floette", base: "floette", tfrom: "floette-eternal", ps: "Floette-Mega" },
        "floette-eternal": { name: "Eternal Flower Floette", base: "floette", ps: "Floette-Eternal" }
    };
    const T = [ {
        id: "regional-gamma-2027",
        name: "Gamma Regionals 2027",
        full: "Gamma Regional Championships 2027",
        city: "Gamma",
        dates: "October 17–18, 2026",
        reg: "M-C",
        game: "Pokémon Champions",
        tier: "regional",
        players: 2,
        division: "Masters"
    } ];
    return { MONS: MONS, T: T };
}();
