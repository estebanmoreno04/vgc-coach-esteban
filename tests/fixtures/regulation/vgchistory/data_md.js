window.VH = function() {
    const REGS = [ {
        id: "M-D",
        label: "Regulation M-D",
        game: "Pokémon Champions",
        tera: false,
        window: "Dec 2026 – present",
        rule: "The current ruleset"
    }, {
        id: "M-C",
        label: "Regulation M-C",
        game: "Pokémon Champions",
        tera: false,
        window: "Sep 2026 – Dec 2026"
    } ];
    const T = [ {
        id: "regional-fixture-town-2027",
        name: "Fixture Town Regionals 2027",
        dates: "December 5–6, 2026",
        reg: "M-D",
        game: "Pokémon Champions",
        tier: "regional",
        players: 700,
        standings: [ {
            po: 1,
            p: "player-three",
            rec: "14-2",
            team: [ "heatran-mega", "rillaboom", "incineroar", "sneasler", "garchomp", "gholdengo" ]
        } ]
    } ];
    const P = {};
    return { REGS: REGS, T: T, P: P };
}();
