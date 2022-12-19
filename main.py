from flask import Flask
from flask import render_template
from flask import request, redirect
import sqlite3
from markupsafe import escape
from wtforms import Form, HiddenField, StringField, FieldList, IntegerField, validators
import itertools
import formencode

app = Flask(__name__)


class TestForm(Form):
    foo = StringField('Foo', [validators.Length(min=1, max=5)])
    subs = FieldList(
        StringField()
    )


class CupForm(Form):
    players = FieldList(IntegerField())

    def init(cup_id):
        form = CupForm(
            {"cup_id": cup_id, "players": }
        )

    def __init__(self, cup_id):
        super().__init__()
        self.cup_id = HiddenField("cup_id")
        self.cup_id.data = cup_id

        connection = get_db_connection()
        cup_players = connection.execute("""
        SELECT 
            p.name player_name,
            p.id player_id
        FROM
            cup_players cp, players p  
        WHERE 1=1                        
            AND cp.cup_id = ?
            AND cp.player_id = p.id
        ORDER BY
            player_id ASC            
        """, (cup_id, )).fetchall()

        for cup_player in cup_players:
            player_id = cup_player["player_id"]
            self.players.append_entry()
            self.players[-1].label = cup_player["player_name"]
            self.players[-1].id = f"player_points.{player_id}"


def get_db_connection():
    connection = sqlite3.connect("database.db")
    connection.row_factory = sqlite3.Row
    return connection


@app.route("/test", methods=["GET", "POST"])
def test():
    form = formencode.variabledecode.variable_decode(request.form)
    print(form)
    form2 = TestForm(request.form)

    if request.method == "POST":
        for id, val in form["player"].items():
            form2.subs.append_entry(val)
            form2.subs.entries[-1].label = val

        if form2.validate():
            print("Validated")
        else:
            print("Invalid")
    else:
        form2.subs.append_entry()
        form2.subs.entries[-1].label = "Moritz"
        form2.subs.entries[-1].name = "player.12"

        form2.subs.append_entry()
        form2.subs.entries[-1].label = "Papeng"
        form2.subs.entries[-1].name = "player.7"

    return render_template("test.html", form=form2)


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


def get_next_cup(tournament_id):
    connection = get_db_connection()

    return connection.execute("""
    SELECT MIN(cp.cup_id) cup_id
    FROM tournaments t, cups c, cup_players cp
    WHERE 1=1 
        AND t.id = ?
        AND t.id = c.tournament_id
        AND c.id = cp.cup_id
        AND cp.points is NULL
    ORDER BY
        c.id ASC
    LIMIT 1                
    """, (tournament_id,)).fetchone()["cup_id"]


@app.route("/tournament/<tournament_id>")
def tournament(tournament_id):
    tournament_id = escape(tournament_id)

    connection = get_db_connection()

    name = connection.execute("SELECT name FROM tournaments WHERE id = ?", (tournament_id,)).fetchone()[0]

    # Calculate the current ranking
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
    """, (tournament_id,)).fetchall()

    ranking = [{"place": place + 1, "name": player["player_name"],
                "points": 0 if player["player_points"] is None else player["player_points"]} for place, player in
               enumerate(ranking)]

    # Calculate the "Next Cup" form
    next_cup_id = get_next_cup(tournament_id)
    next_cup_form = CupForm(next_cup_id)

    # Calculate the list of cups
    cup_ids = connection.execute("""
    SELECT
        c.id cup_id
    FROM
        cups c
    WHERE 1=1
        AND c.tournament_id = ?
    ORDER BY
        c.id ASC        
    """, (tournament_id, )).fetchall()
    cup_ids = [entry["cup_id"] for entry in cup_ids]
    cups = []
    for cup_id in cup_ids:
        cup = {
            "is_next": next_cup_id == cup_id,
            "id": cup_id
        }

        cup_players = connection.execute("""
        SELECT 
            p.name player_name, p.id player_id, cp.points player_points
        FROM 
            cups c, cup_players cp, players p 
        WHERE 1=1
            AND c.id = ?
            AND cp.cup_id = c.id
            AND cp.player_id = p.id 
        ORDER BY 
            player_id ASC
        """, (cup_id, )).fetchall()

        cup["players"] = [{
            "name": cup_player["player_name"],
            "id": cup_player["player_id"],
            "points": cup_player["player_points"]
        } for cup_player in cup_players]

        cups.append(cup)

    return render_template("tournament.html", name=name, ranking=ranking, cups=cups, next_cup_form=next_cup_form)


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


@app.route("/submit_cup", methods=['POST'])
def submit_cup():
    form = formencode.variabledecode.variable_decode(request.form)
    form = CupForm(form)

    connection = get_db_connection()

    tournament_id = connection.execute("SELECT tournament_id FROM cups WHERE id = ?", (form.cup_id,)).fetchone()[
        "tournament_id"]

    if request.method == "POST" and form.validate():
        for player in form.players:
            connection.execute("UPDATE cup_players SET points = ? WHERE cup_id = ? AND player_id = ?",
                               (player.data, form.cup_id, player.id)).fetchall()

        connection.commit()

    return redirect(f"/tournament/{tournament_id}")


if __name__ == "__main__":
    tournaments_overview()
