from flask import Flask, request, render_template
import random
import string
from flask_socketio import SocketIO, join_room, leave_room, send, emit
import json
import time
import base64
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)


ongoing_games = {}


class Card(object):

    NUMBER_MAP = {"11": "J", "12": "Q", "13": "K"}

    def __init__(self, suit, number):
        self.id = ''.join(random.choice(string.digits) for x in range(6))
        self.suit = suit
        self.number = str(
            number) if number <= 10 else Card.NUMBER_MAP[str(number)]
        self.img = suit[0].lower(
        ) + "_" + str(number) if number <= 10 else Card.NUMBER_MAP[str(number)]

    def log_card(self):
        print(self.suit+" "+str(self.number))


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
        return [{"id": i.id, "suit": i.suit, "number": i.number, "img": i.img} for i in self.cards]

    def remove_card(self, card_id):
        idx = -1
        for i in enumerate(self.cards):
            if i[1].id == card_id:
                idx = i[0]
        return self.cards.pop(idx)


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
        self.cur_usr = 0
        self.user_map = {}
        self.top_card = None
        self.game_started = False
        self.game_start=False

    def get_next_player(self):
        self.cur_usr = (self.cur_usr + 1) % len(self.users)
        return self.users[self.cur_usr]

    def log_deck(self):
        for i in self.deck:
            print(i.suit, i.number)

    def getTopCard(self):
        return self.deck.pop()

    def convertToJSON(self, card):
        return {"id": card.id, "suit": card.suit, "number": card.number, "img": card.img, "status": "valid"}

    def setClientSID(self, uname, sid):
        self.user_sid_map[uname] = sid

    def setUserCards(self):
        self.generateCards()
        for i in self.users:
            i.setCards(self.return10cards(i))
        card = self.getTopCard()
        self.top_card = card

    def addUser(self, uobj):
        self.users.append(uobj)
        return uobj

    def share_link(self):
        return self.gameURL

    def generateCards(self):

        for k in range(2):
            for i in ["diamond", "heart", "club", "spade"]:
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
    socketio.send("redirect", room=server)
    return "Loading..."


@socketio.on('start_game')
def begin(data):
    room = data['room']
    game = ongoing_games[room]
    game.setUserCards()
    emit("starting_game", room=room)


@app.route("/rummy/<server>")
def game_state(server):
    return render_template("playfield.html")


@socketio.on('discard')
def discard(data):
    room = data["room"]
    username = data['username']
    card_id = data["id"]
    game = ongoing_games[room]
    if game.users[game.cur_usr].name == username:
        game.top_card = game.user_map[username].remove_card(card_id)
        emit("top_card", json.dumps(game.convertToJSON(game.top_card)), room=room)
    else:
        emit("not_your_turn", room=game.user_sid_map[username])


@app.route("/top", methods=["POST"])
def top_deck():
    data = request.get_json()
    room = data["room"]
    username = data['username']
    game = ongoing_games[room]
    print(game.cur_usr)
    if game.users[game.cur_usr].name == username:
        card = game.getTopCard()
        game.user_map[username].cards.append(card)
        return game.convertToJSON(card)
    else:
        return {"status": "invalid"}


@socketio.on('take_discarded_card')
def take_discard_card(data):
    room = data["room"]
    username = data['username']
    game = ongoing_games[room]
    game.user_map[username].cards.append(game.top_card)
    emit("top_card", json.dumps({"id": -1, "suit": "heart", "number": 20, "img": "xyz", "status": "valid"}), room=room)
    emit("add_to_user_deck", json.dumps(game.convertToJSON(game.top_card)), room=game.user_sid_map[username])
    
@socketio.on('turn_complete')
def take_discard_card(data):
    room = data["room"]
    username = data['username']
    game = ongoing_games[room]
    next_name = game.get_next_player().name
    emit("next_turn",json.dumps({"turn" : game.users[game.cur_usr].name }), room=room)
    
@socketio.on('winner')
def winner(data):
    room = data["room"]
    username = data['username']
    game = ongoing_games[room]
    emit("winner_user",json.dumps({"username":username,"cards":game.user_map[username].getCardsAsJSON()}), room=room)

@socketio.on('loaded')
def game_state_loaded(data):

    room = data['room']
    username = data['username']
    game = ongoing_games[room]
    emit("top_card", json.dumps(game.convertToJSON(game.top_card)), room=room)
    game.user_sid_map[username] = request.sid
    emit("distribute_cards", json.dumps(
        {"cards": game.user_map[username].getCardsAsJSON()}), room=game.user_sid_map[username])
    emit("next_turn",json.dumps({"turn" : game.users[game.cur_usr].name }), room=room)
    game.game_start = True


if __name__ == "__main__":

    socketio.run(app, debug=True,host='0.0.0.0')
