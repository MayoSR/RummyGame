from flask import Flask, request, render_template
import random
import string
from flask_socketio import SocketIO, join_room, leave_room, send, emit
import json
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)


ongoing_games = {}


class Card(object):

    NUMBER_MAP = {"11": "J", "12": "Q", "13": "K"}

    def __init__(self, suit, number):

        self.suit = suit
        self.number = str(
            number) if number <= 10 else Card.NUMBER_MAP[str(number)]
        self.img = suit[0].lower(
        ) + "_" + str(number) if number <= 10 else Card.NUMBER_MAP[str(number)]


class User(object):

    def __init__(self, name):
        self.name = name
        self.cards = []

    def setCards(self, cards):
        self.cards = cards

    def log_cards(self):
        for i in self.cards:
            print(i.suit, i.number)

    def getCardsAsJSON(self):
        return [{"suit": i.suit, "number": i.number, "img": i.img} for i in self.cards]


class GameSetup(object):

    def __init__(self):
        self.gameStub = ''.join(random.choice(
            string.ascii_letters + string.digits) for x in range(6))
        self.gameURL = "http://localhost:5000/" + self.gameStub
        self.room_name = self.gameStub
        self.user_sid_map = {}
        ongoing_games[self.gameStub] = self
        self.deck = []
        self.users = []
        self.user_map = {}

    def setClientSID(self, uname, sid):
        self.user_sid_map[uname] = sid

    def setUserCards(self):
        self.generateCards()
        for i in self.users:
            i.setCards(self.return10cards(i))

    def addUser(self, uobj):
        self.users.append(uobj)
        return uobj

    def share_link(self):
        return self.gameURL

    def generateCards(self):

        for k in range(2):
            for i in ["Diamond", "Heart", "Clove", "Spade"]:
                for j in range(1, 14):
                    self.deck.append(Card(i, j))
        random.shuffle(self.deck)

    def return10cards(self, obj):
        return [self.deck.pop() for i in range(10)]


@app.route("/")
def default_home():
    return render_template("index.html", creator=True)


@app.route("/<server>")
def joining_home(server):
    return render_template("index.html", serverhex="http://localhost:5000/start/"+server, creator=False)


@app.route("/start/<server>", methods=["POST"])
def join_game(server):
    game = ongoing_games[server]
    uobj = game.addUser(User(request.form["uname"]))
    game.user_map[request.form["uname"]] = uobj
    return render_template("waitingpage.html", share_link=game.share_link(), share_stub=game.gameStub, lobby_leader=False, uname=request.form["uname"])


@app.route("/start", methods=["POST"])
def start_game():
    game = GameSetup()
    uobj = game.addUser(User(request.form["uname"]))
    game.user_map[request.form["uname"]] = uobj
    return render_template("waitingpage.html", share_link=game.share_link(), share_stub=game.gameStub, lobby_leader=True, uname=request.form["uname"])


@socketio.on('join')
def on_join(data):
    username = data['username']
    room = data['room']
    ongoing_games[room].setClientSID(username, request.sid)
    join_room(room)
    udata = "-".join([i.name for i in ongoing_games[room].users])
    send(udata, room=room)


@app.route("/stop")
def stop_server():
    socketio.emit("delete_vars")
    socketio.stop()


@app.route("/starting/<server>")
def starting_state(server):
    game = ongoing_games[server]
    game.setUserCards()
    socketio.send("redirect", room=server)
    return "Loading..."


@socketio.on('start_game')
def begin(data):
    room = data['room']
    emit("starting_game", room=room)


@app.route("/rummy/<server>")
def game_state(server):
    return render_template("playfield.html")


@socketio.on('loaded')
def game_state_loaded(data):
    room = data['room']
    username = data['username']
    game = ongoing_games[room]
    game.setUserCards()
    game.user_sid_map[username] = request.sid
    emit("distribute_cards", json.dumps(
            {"cards": game.user_map[username].getCardsAsJSON()}), room=game.user_sid_map[username])
        


if __name__ == "__main__":
    socketio.run(app)
