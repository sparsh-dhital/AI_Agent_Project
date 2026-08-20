import os
from datetime import datetime, timedelta

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
from pymongo import MongoClient
from pymongo.errors import PyMongoError

load_dotenv()

app = Flask(__name__)
CORS(app)

# --- ADDED: Home route to prevent 404 errors on the main page ---
@app.route("/")
def home():
    return "<h1>CampusMove AI Backend is Running Successfully!</h1><p>Visit <a href='/api/routes'>/api/routes</a> to see your bus data.</p>"
# -----------------------------------------------------------------

mongo_uri = os.getenv("MONGO_URI")
mongo_client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000) if mongo_uri else None
database = mongo_client[os.getenv("MONGO_DB", "campusmoveai")] if mongo_client else None
users = database.users if database is not None else None
trips = database.trips if database is not None else None

SAMPLE_OPTIONS = [
    {
        "route_id": "CM-101",
        "name": "Campus Express",
        "from": "Hostel",
        "to": "College",
        "departure": "08:10",
        "arrival": "08:35",
        "duration_minutes": 25,
        "cost": 10,
        "crowding": "Low",
        "available": True,
        "delay_minutes": 0,
    },
    {
        "route_id": "CM-204",
        "name": "North Loop",
        "from": "Hostel",
        "to": "College",
        "departure": "08:25",
        "arrival": "08:55",
        "duration_minutes": 30,
        "cost": 5,
        "crowding": "Medium",
        "available": True,
        "delay_minutes": 0,
    },
    {
        "route_id": "CM-307",
        "name": "East Connector",
        "from": "Hostel",
        "to": "College",
        "departure": "08:35",
        "arrival": "09:05",
        "duration_minutes": 30,
        "cost": 0,
        "crowding": "High",
        "available": True,
        "delay_minutes": 0,
    },
]


def minutes(value):
    return datetime.strptime(value, "%H:%M").hour * 60 + datetime.strptime(value, "%H:%M").minute


def get_options(origin, destination):
    if trips is None:
        return SAMPLE_OPTIONS.copy()
    try:
        options = list(trips.find({"from": origin, "to": destination}, {"_id": 0}))
        return options or SAMPLE_OPTIONS.copy()
    except PyMongoError:
        return SAMPLE_OPTIONS.copy()


def plan_trip(payload):
    origin = payload.get("origin", "Hostel").strip()
    destination = payload.get("destination", "College").strip()
    required_arrival = payload.get("required_arrival", "09:00")
    options = get_options(origin, destination)
    eligible = []

    for option in options:
        if not option.get("available", True):
            continue
        delay = int(option.get("delay_minutes", 0))
        actual_arrival = datetime.strptime(option["arrival"], "%H:%M") + timedelta(minutes=delay)
        option = {**option, "actual_arrival": actual_arrival.strftime("%H:%M")}
        if actual_arrival.hour * 60 + actual_arrival.minute <= minutes(required_arrival):
            convenience_penalty = {"Low": 0, "Medium": 2, "High": 5}.get(option.get("crowding"), 3)
            option["score"] = delay * 3 + option["duration_minutes"] + option["cost"] + convenience_penalty
            eligible.append(option)

    if not eligible:
        return {"origin": origin, "destination": destination, "required_arrival": required_arrival, "recommendation": None, "options": [], "message": "No available route reaches the required arrival time."}

    recommendation = min(eligible, key=lambda option: option["score"])
    buffer = minutes(required_arrival) - minutes(recommendation["actual_arrival"])
    reason = f"{recommendation['name']} arrives at {recommendation['actual_arrival']} with a {buffer}-minute buffer"
    if recommendation.get("delay_minutes", 0):
        reason += "; this is the best remaining alternative after the delay"
    return {"origin": origin, "destination": destination, "required_arrival": required_arrival, "recommendation": recommendation, "options": eligible, "message": reason + "."}


@app.get("/api/health")
def health():
    try:
        if mongo_client is None:
            raise RuntimeError("MONGO_URI is not configured")
        mongo_client.admin.command("ping")
        return jsonify({"status": "ok", "database": "connected"})
    except (PyMongoError, RuntimeError) as error:
        return jsonify({"status": "degraded", "database": "unavailable", "detail": str(error)}), 503


@app.post("/api/users")
def register_user():
    payload = request.get_json(silent=True) or {}
    required = ("name", "usertype", "registration_number")
    if any(not str(payload.get(field, "")).strip() for field in required):
        return jsonify({"error": "name, usertype, and registration_number are required"}), 400
    if payload["usertype"] not in ("Student", "Employee"):
        return jsonify({"error": "usertype must be Student or Employee"}), 400
    user = {"name": payload["name"].strip(), "usertype": payload["usertype"], "registration_number": payload["registration_number"].strip(), "updated_at": datetime.utcnow()}
    try:
        users.update_one({"registration_number": user["registration_number"]}, {"$set": user}, upsert=True)
        return jsonify({"message": "User registered", "user": {key: value for key, value in user.items() if key != "updated_at"}}), 201
    except (AttributeError, PyMongoError):
        return jsonify({"error": "MongoDB is unavailable"}), 503


@app.post("/api/plan")
def create_plan():
    payload = request.get_json(silent=True) or {}
    result = plan_trip(payload)
    try:
        if trips is not None:
            trips.insert_one({"type": "trip_request", "request": payload, "result": result, "created_at": datetime.utcnow()})
    except PyMongoError:
        pass
    return jsonify(result)


@app.get("/api/routes")
def list_routes():
    if trips is None:
        return jsonify(SAMPLE_OPTIONS)
    try:
        routes = list(trips.find({"route_id": {"$exists": True}}, {"_id": 0}))
        return jsonify(routes or SAMPLE_OPTIONS)
    except PyMongoError:
        return jsonify(SAMPLE_OPTIONS)


@app.post("/api/routes")
def add_route():
    route = request.get_json(silent=True) or {}
    required = ("route_id", "name", "from", "to", "departure", "arrival", "duration_minutes")
    if any(field not in route for field in required):
        return jsonify({"error": "route_id, name, from, to, departure, arrival, and duration_minutes are required"}), 400
    route.setdefault("available", True)
    route.setdefault("delay_minutes", 0)
    route.setdefault("cost", 0)
    route.setdefault("crowding", "Medium")
    if trips is None:
        return jsonify({"route": route, "message": "Route accepted for demo mode; MongoDB is unavailable"}), 201
    try:
        trips.update_one({"route_id": route["route_id"]}, {"$set": route}, upsert=True)
        return jsonify({"route": route, "message": "Route saved"}), 201
    except PyMongoError:
        return jsonify({"error": "MongoDB is unavailable"}), 503


@app.patch("/api/routes/<route_id>/delay")
def update_delay(route_id):
    payload = request.get_json(silent=True) or {}
    delay_minutes = int(payload.get("delay_minutes", 0))
    available = payload.get("available", True)
    if trips is None:
        return jsonify({"route_id": route_id, "delay_minutes": delay_minutes, "available": available, "message": "Delay accepted for demo mode"})
    try:
        result = trips.update_one({"route_id": route_id}, {"$set": {"delay_minutes": delay_minutes, "available": available}})
        if not result.matched_count:
            return jsonify({"error": "Route not found"}), 404
        return jsonify({"route_id": route_id, "delay_minutes": delay_minutes, "available": available})
    except PyMongoError:
        return jsonify({"error": "MongoDB is unavailable"}), 503


@app.post("/api/chat")
def chat():
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message", "")).strip()
    if not message:
        return jsonify({"error": "message is required"}), 400
    lowered = message.lower()
    if any(term in lowered for term in ("bus", "route", "hostel", "college", "arrive", "delay")):
        result = plan_trip(payload)
        recommendation = result.get("recommendation")
        answer = result["message"] if recommendation else result["message"]
        if recommendation:
            answer += f" Take {recommendation['name']} from {recommendation['from']} at {recommendation['departure']}."
        return jsonify({"answer": answer, "plan": result})
    return jsonify({"answer": "I can plan a campus trip. Send your origin, destination, and required arrival time, for example: Hostel to College by 09:00 AM."})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=True)