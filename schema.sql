DROP TABLE IF EXISTS tournaments;
DROP TABLE IF EXISTS players;
DROP TABLE IF EXISTS cups;
DROP TABLE IF EXISTS cup_players;

CREATE TABLE tournaments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT
);

CREATE TABLE players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER,
    name TEXT,

    FOREIGN KEY (tournament_id) REFERENCES tournaments(tournament_id)
);

CREATE TABLE cups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER,

    FOREIGN KEY (tournament_id) REFERENCES tournaments(tournament_id)
);

CREATE TABLE cup_players (
    cup_id INTEGER,
    player_id INTEGER,
    points INTEGER,

    FOREIGN KEY (cup_id) REFERENCES cup(id),
    FOREIGN KEY (player_id) REFERENCES players(id)
);