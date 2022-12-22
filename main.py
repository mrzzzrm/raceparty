from flask import Flask
from flask import render_template
from flask import request, redirect
import sqlite3
from markupsafe import escape
from wtforms import Form, HiddenField, StringField, FieldList, IntegerField, validators
import itertools
import formencode
import math

app = Flask(__name__)


class TestForm(Form):
    foo = StringField('Foo', [validators.Length(min=1, max=5)])
    subs = FieldList(
        StringField()
    )


def from_post(post):
    form = CupForm()
    form.cup_id.data = post["cup_id"]

    for player_id, points in post["players"].items():
        form.players.append_entry()
        form.players.entries[-1].data = int(points)

    return form


def from_cup_id(cup_id):
    form = CupForm()
    form.cup_id.data = cup_id

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
    """, (cup_id,)).fetchall()

    for cup_player in cup_players:
        player_id = cup_player["player_id"]
        form.players.append_entry()
        form.players[-1].label = cup_player["player_name"]
        form.players[-1].name = f"players.{player_id}"

    return form


class CupForm(Form):
    cup_id = HiddenField()
    players = FieldList(IntegerField(validators=[validators.NumberRange(0, 60)]))


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
            "players": ", ".join([player["name"] for player in players])
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

    ordering = request.args.get('ordering')
    ordering = ordering if ordering in ("player_points", "player_points_per_cup") else "player_points"

    # Calculate the current ranking
    ranking = connection.execute(f"""
    SELECT *, 
        RANK() OVER (ORDER BY {ordering} DESC) player_place FROM (
    SELECT 
        MIN(p.name) player_name, 
        SUM(cp.points) player_points, 
        AVG(cp.points) player_points_per_cup,
        COUNT(cp.points) player_num_cups
    FROM cups c, cup_players cp, players p
    WHERE 1=1
        AND c.tournament_id = ?
        AND cp.cup_id = c.id
        AND cp.player_id = p.id
    GROUP BY 
        p.id
    )
    ORDER BY
        player_place ASC    
    """, (tournament_id,)).fetchall()

    ranking = [{"place": player["player_place"] if idx == 0 or ranking[idx - 1]["player_place"] != player[
        "player_place"] else "",
                "name": player["player_name"],
                "points": 0 if player["player_points"] is None else player["player_points"],
                "points_per_cup": "{:.2f}".format(player["player_points_per_cup"] or 0),
                "num_cups": player["player_num_cups"]
                } for idx, player in
               enumerate(ranking)]

    # Calculate the "Next Cup" form
    next_cup_id = get_next_cup(tournament_id)
    if next_cup_id is not None:
        next_cup_form = from_cup_id(next_cup_id)
    else:
        next_cup_form = None

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
    """, (tournament_id,)).fetchall()
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
        """, (cup_id,)).fetchall()

        cup["players"] = [{
            "name": cup_player["player_name"],
            "id": cup_player["player_id"],
            "points": cup_player["player_points"]
        } for cup_player in cup_players]

        cups.append(cup)

    num_cups_done = connection.execute("""
    SELECT COUNT(*) num_cups
    FROM cups c
    WHERE 1=1 
        AND c.tournament_id = ?
        AND NOT EXISTS (
            SELECT * FROM cup_players cp WHERE cp.cup_id = c.id AND cp.points is NULL 
        )        
    """, (tournament_id,)).fetchone()["num_cups"]
    num_cups = len(cups)

    return render_template("tournament.html", name=name, ranking=ranking, cups=cups, next_cup_form=next_cup_form,
                           num_cups_done=num_cups_done, num_cups=num_cups)


def create_cups(player_ids, max_num_players_in_cup):
    num_players_in_cup = min(len(player_ids), max_num_players_in_cup)

    cups = [cup for cup in itertools.combinations(player_ids, num_players_in_cup)]

    def rate(cups):
        num_races = {player: 0 for player in player_ids}
        for cup in cups:
            for player in cup:
                num_races[player] += 1
        min_races = min(num_races.values())
        max_races = max(num_races.values())
        # return max_races - min_races
        return sum([(num_races[player] - min_races) ** 2 for player in player_ids])

    for i in range(1, len(cups)):
        min_rating = None
        for j in range(i, len(cups)):
            cups[i], cups[j] = cups[j], cups[i]
            rating = rate(cups[0:i + 1])
            if min_rating is not None and rating > min_rating:
                cups[i], cups[j] = cups[j], cups[i]
            else:
                min_rating = rating
        print("Min Rating: ", cups[0:i + 1], min_rating)

    return cups


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

    for cup in create_cups(player_ids, 4):
        cursor.execute("INSERT INTO cups (tournament_id) VALUES (?)", (tournament_id,)).fetchone()
        cup_id = cursor.lastrowid
        for player_id in cup:
            cursor.execute("INSERT INTO cup_players (cup_id, player_id) VALUES (?, ?)", (cup_id, player_id))

    connection.commit()

    return redirect(f"/tournament/{tournament_id}")


@app.route("/submit_cup", methods=['POST'])
def submit_cup():
    form2 = formencode.variabledecode.variable_decode(request.form)
    print(form2)
    form = from_post(form2)

    connection = get_db_connection()

    tournament_id = connection.execute("SELECT tournament_id FROM cups WHERE id = ?", (form.cup_id.data,)).fetchone()[
        "tournament_id"]

    if form.validate():
        for player_id, player_points in form2["players"].items():
            connection.execute("UPDATE cup_players SET points = ? WHERE cup_id = ? AND player_id = ?",
                               (player_points, form.cup_id.data, player_id)).fetchall()
        connection.commit()
    else:
        "Invalid form"

    return redirect(f"/tournament/{tournament_id}")


def is_valid(player_ids, cups):
    cups_per_player = {player: 0 for player in player_ids}
    for cup in cups:
        for player in cup:
            cups_per_player[player] += 1
    return min(cups_per_player.values()) == max(cups_per_player.values())


def create_cups2(player_ids, num_cups, cup_capacity):
    candidate_cups = [cup for cup in itertools.combinations(player_ids, cup_capacity)]
    num_players = len(player_ids)
    num_cups = min(num_cups, len(candidate_cups))
    num_slots = num_cups * cup_capacity
    num_slots_per_player = math.floor(num_slots / num_players)
    num_slots = num_slots_per_player * num_players
    num_full_cups = math.floor(num_slots / cup_capacity)

    full_cups = []
    num_cups_by_player = {player_id: 0 for player_id in player_ids}

    for c in range(0, num_full_cups):
        best_candidate = None
        best_candidate_penalty = None

        for candidate_cup in candidate_cups:
            for player_id in candidate_cup:
                num_cups_by_player[player_id] += 1
            penalty = max(num_cups_by_player.values()) - min(num_cups_by_player.values())
            if best_candidate_penalty is None or penalty < best_candidate_penalty:
                best_candidate = candidate_cup
                best_candidate_penalty = penalty
            for player_id in candidate_cup:
                num_cups_by_player[player_id] -= 1

        full_cups.append(best_candidate)
        candidate_cups.remove(best_candidate)

    assert max(num_cups_by_player.values()) == min(num_cups_by_player.values())





if __name__ == "__main__":
    player_ids = [0, 1, 2, 3, 4, 5, 6]
    cups = create_cups2([0, 1, 2, 3, 4, 5], num_cups=6, cup_capacity=4)
