from flask import Flask
from flask import render_template
from flask import request, redirect
import sqlite3
from markupsafe import escape
import itertools
import formencode

app = Flask(__name__)


def get_db_connection():
    connection = sqlite3.connect("database.db")
    connection.row_factory = sqlite3.Row
    return connection


@app.route("/")
def tournaments_overview():
    connection = get_db_connection()

    tournaments2 = []

    tournaments = connection.execute("SELECT id, name FROM tournaments;").fetchall()
    for tournament in tournaments:
        players = connection.execute("SELECT name FROM players WHERE tournament_id = ?;",
                                     (tournament["id"],)).fetchall()
        tournaments2.append({
            "id": tournament["id"],
            "name": tournament["name"],
            "players": [player["name"] for player in players]
        })

    return render_template("tournaments_overview.html", tournaments=tournaments2)


@app.route("/new")
def new_tournament():
    return render_template("new_tournament.html")


@app.route("/tournament/<id>")
def tournament(id):
    id = escape(id)

    connection = get_db_connection()

    name = connection.execute("SELECT name FROM tournaments WHERE id = ?", (id,)).fetchone()[0]

    ranking = connection.execute("""
    SELECT MIN(p.name) player_name, SUM(cp.points) player_points
    FROM cups c, cup_players cp, players p
    WHERE 1=1
        AND c.tournament_id = ?
        AND cp.cup_id = c.id
        AND cp.player_id = p.id
    GROUP BY 
        p.id
    ORDER BY
        player_points DESC    
    """, (id,)).fetchall()

    ranking = [{"place": place + 1, "name": player["player_name"],
                "points": 0 if player["player_points"] is None else player["player_points"]} for place, player in
               enumerate(ranking)]

    cup_players = connection.execute("""
    SELECT c.id as cup_id, p.name player_name, p.id player_id, cp.points player_points
    FROM cups c, cup_players cp, players p 
    WHERE c.tournament_id = ? AND c.id = cp.cup_id AND cp.player_id = p.id 
    ORDER BY cup_id, player_points DESC;""",
                                     (id,)).fetchall()

    cups = []
    cup = None
    last_cup_id = None
    is_next = None
    for cup_player in cup_players:
        if cup_player["cup_id"] != last_cup_id:
            if is_next is None:
                if cup_player["player_points"] is None:
                    is_next = True

            cups.append({
                "is_next": False if is_next is None else is_next,
                "id": cup_player["cup_id"],
                "players": []
            })
            cup = cups[-1]
            last_cup_id = cup_player["cup_id"]
            if is_next:
                is_next = False

        cup["players"].append({
            "name": cup_player["player_name"],
            "id": cup_player["player_id"],
            "points": cup_player["player_points"]
        })

    return render_template("tournament.html", name=name, ranking=ranking, cups=cups)


@app.route("/create_new_tournament", methods=['GET', 'POST'])
def create_new_tournament():
    tournament_name = request.form["tournament_name"]
    players = request.form.getlist("player")

    print(f"Form: {request.form}\n")

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("INSERT INTO tournaments (name) VALUES (?)", (tournament_name,)).fetchone()
    tournament_id = cursor.lastrowid

    player_ids = []
    for player in players:
        cursor.execute("INSERT INTO players (name, tournament_id) VALUES (?, ?)", (player, tournament_id)).fetchone()
        player_ids.append(cursor.lastrowid)

    num_players_in_cup = min(len(player_ids), 4)

    for cup in itertools.combinations(player_ids, num_players_in_cup):
        print(f"Cup: {cup}")
        cursor.execute("INSERT INTO cups (tournament_id) VALUES (?)", (tournament_id,)).fetchone()
        cup_id = cursor.lastrowid
        for player_id in cup:
            cursor.execute("INSERT INTO cup_players (cup_id, player_id) VALUES (?, ?)", (cup_id, player_id))

    connection.commit()

    return redirect(f"/tournament/{tournament_id}")


@app.route("/submit_cup", methods=['GET', 'POST'])
def submit_cup():
    form = formencode.variabledecode.variable_decode(request.form.to_dict())

    print(form)

    cup_id = form["cup_id"]

    connection = get_db_connection()

    for player_id, points in form["players"].items():
        print(cup_id, player_id, points)
        connection.execute("UPDATE cup_players SET points = ? WHERE cup_id = ? AND player_id = ?",
                           (points, cup_id, player_id)).fetchall()

    connection.commit()

    tournament_id = connection.execute("SELECT tournament_id FROM cups WHERE id = ?", (cup_id,)).fetchone()[
        "tournament_id"]

    return redirect(f"/tournament/{tournament_id}")


if __name__ == "__main__":
    tournaments_overview()
