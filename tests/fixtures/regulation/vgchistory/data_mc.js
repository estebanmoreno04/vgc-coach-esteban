window.VH = function() {
    const FLAGTEXT = [ "AL", "AN" ];
    const REGS = [ {
        id: "M-C",
        label: "Regulation M-C",
        game: "Pokémon Champions",
        tera: false,
        window: "Sep 2026 – present",
        rule: "The current ruleset"
    }, {
        id: "M-B",
        label: "Regulation M-B",
        game: "Pokémon Champions",
        tera: false,
        window: "Jun 2026 – Sep 2026"
    }, {
        id: "I",
        label: "Regulation I",
        game: "Scarlet & Violet",
        tera: true,
        window: "May 2025 – Aug 2025"
    } ];
    const RULESETS = [ "M-B", "M-C" ];
    const T = [ {
        id: "regional-fixture-city-2027",
        name: "Fixture City Regionals 2027",
        dates: "October 17–18, 2026",
        reg: "M-C",
        game: "Pokémon Champions",
        tier: "regional",
        players: 862,
        standings: [ {
            po: 1,
            p: "player-one",
            rec: "15-2",
            team: [ "raichu-mega-x", "golisopod", "archaludon", "pelipper", "basculegion-f", "sneasler" ]
        } ]
    }, {
        id: "regional-older-city-2026",
        name: "Older City Regionals 2026",
        dates: "August 1–2, 2026",
        reg: "M-B",
        game: "Pokémon Champions",
        tier: "regional",
        players: 500,
        standings: [ {
            po: 1,
            p: "player-two",
            rec: "12-2",
            team: [ "garchomp", "incineroar", "rillaboom", "gholdengo", "kingambit", "charizard-mega-y" ]
        } ]
    } ];
    const P = {};
    return { REGS: REGS, T: T, P: P };
}();
