import json
import os
from datetime import datetime, timedelta

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from groq import Groq  # --- NEW: Using the official SDK ---

load_dotenv()

app = Flask(__name__)
CORS(app)

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.json")
with open(SCHEMA_PATH, "r", encoding="utf-8") as schema_file:
    LLM_SCHEMA = json.load(schema_file)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
LLM_TEMPERATURE = 0.2

# --- NEW: Initialize the Groq Client ---
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

mongo_uri = os.getenv("MONGO_URI")
mongo_client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000) if mongo_uri else None
database = mongo_client[os.getenv("MONGO_DB", "campusmoveai")] if mongo_client else None
users = database.users if database is not None else None
trips = database.trips if database is not None else None
chat_history = database.chat_history if database is not None else None

SAMPLE_OPTIONS = [
    {"route_id": "CM-101", "name": "Campus Express", "from": "Hostel", "to": "College", "departure": "08:10", "arrival": "08:35", "duration_minutes": 25, "cost": 10, "crowding": "Low", "available": True, "delay_minutes": 0},
    {"route_id": "CM-204", "name": "North Loop", "from": "Hostel", "to": "College", "departure": "08:25", "arrival": "08:55", "duration_minutes": 30, "cost": 5, "crowding": "Medium", "available": True, "delay_minutes": 0},
    {"route_id": "CM-307", "name": "East Connector", "from": "Hostel", "to": "College", "departure": "08:35", "arrival": "09:05", "duration_minutes": 30, "cost": 0, "crowding": "High", "available": True, "delay_minutes": 0},
]

CREDENTIAL_KEYS = ["name", "usertype", "registration_number"]

@app.route("/")
def home():
    return "<h1>CampusMove AI Backend is Running Successfully!</h1>"

def minutes(value):
    dt = datetime.strptime(value, "%H:%M")
    return dt.hour * 60 + dt.minute

def safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

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
        try:
            if not option.get("available", True): continue
            delay = safe_int(option.get("delay_minutes", 0), 0)
            actual_arrival_dt = datetime.strptime(option["arrival"], "%H:%M") + timedelta(minutes=delay)
            item = {**option, "actual_arrival": actual_arrival_dt.strftime("%H:%M")}
            if minutes(item["actual_arrival"]) <= minutes(required_arrival):
                crowd_penalty = {"Low": 0, "Medium": 2, "High": 5}.get(item.get("crowding"), 3)
                item["score"] = delay * 3 + safe_int(item.get("duration_minutes"), 30) + safe_int(item.get("cost", 0), 0) + crowd_penalty
                eligible.append(item)
        except (KeyError, TypeError, ValueError):
            continue

    if not eligible:
        return {"origin": origin, "destination": destination, "required_arrival": required_arrival, "recommendation": None, "options": [], "message": "No available route reaches the required arrival time."}

    recommendation = min(eligible, key=lambda option: option["score"])
    buffer_minutes = minutes(required_arrival) - minutes(recommendation["actual_arrival"])
    reason = f"{recommendation['name']} arrives at {recommendation['actual_arrival']} with a {buffer_minutes}-minute buffer"
    if recommendation.get("delay_minutes", 0):
        reason += "; this is the best remaining alternative after the delay"

    return {"origin": origin, "destination": destination, "required_arrival": required_arrival, "recommendation": recommendation, "options": eligible, "message": reason + "."}

def route_context_from_message(message):
    text = (message or "").lower()
    return {
        "intent": "route_planning" if any(word in text for word in ["bus", "route", "hostel", "college", "arrive", "delay", "stop", "fastest"]) else "general",
        "contains_delay": "delay" in text,
        "contains_crowding": "crowd" in text or "crowded" in text,
    }

def call_llm(credentials, user_message, route_plan, route_context):
    if not groq_client:
        return {
            "answer": "LLM API key is missing. Please set GROQ_API_KEY in .env.",
            "intent": route_context["intent"],
            "explanation": "Fell back because no LLM key is configured.",
            "next_action": "Set GROQ_API_KEY and restart the backend.",
            "suggested_departure": route_plan.get("recommendation", {}).get("departure") if route_plan.get("recommendation") else "08:00",
            "confidence": 0.35,
        }

    schema_instruction = json.dumps(LLM_SCHEMA, ensure_ascii=True)
    system_prompt = (
        "You are CampusMoveAI, an intelligent campus mobility planner. "
        "Always return strict JSON following the provided schema. "
        "Use the route plan context when available and keep responses practical."
    )

    user_prompt = {
        "credentials": credentials,
        "question": user_message,
        "route_plan": route_plan,
        "route_context": route_context,
    }

    try:
        # --- NEW: Using the official Groq SDK for a guaranteed connection ---
        chat_completion = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "system", "content": "Schema contract: " + schema_instruction},
                {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=True)},
            ],
            model=GROQ_MODEL,
            temperature=LLM_TEMPERATURE,
            response_format={"type": "json_object"}
        )
        
        content = chat_completion.choices[0].message.content
        parsed = json.loads(content)
        
        return {
            "answer": parsed.get("answer", "I am ready to help with your campus trip."),
            "intent": parsed.get("intent", route_context["intent"]),
            "explanation": parsed.get("explanation", ""),
            "next_action": parsed.get("next_action", "Share destination and arrival time."),
            "suggested_departure": parsed.get("suggested_departure", "08:00"),
            "confidence": float(parsed.get("confidence", 0.6)),
        }
    except Exception as error:
        print(f"\n--- GROQ SDK ERROR ---\n{error}\n----------------------\n")
        return {
            "answer": f"[API ERROR] Groq failed: {error}",
            "intent": route_context["intent"],
            "explanation": f"LLM failed: {error}",
            "next_action": "Check terminal for details.",
            "suggested_departure": route_plan.get("recommendation", {}).get("departure") if route_plan.get("recommendation") else "08:00",
            "confidence": 0.0,
        }

def parse_credentials_from_message(message):
    parts = [part.strip() for part in str(message).split("|")]
    if len(parts) < 3: return None
    usertype_raw = parts[1].lower()
    if usertype_raw == "student": usertype = "Student"
    elif usertype_raw == "employee": usertype = "Employee"
    else: return None
    if not parts[0] or not parts[2]: return None
    return {"name": parts[0], "usertype": usertype, "registration_number": parts[2]}

def upsert_user_if_ready(chat_id, credentials):
    if users is None: return
    if not all(credentials.get(key) for key in CREDENTIAL_KEYS): return
    try:
        users.update_one(
            {"registration_number": credentials["registration_number"]},
            {"$set": {"name": credentials["name"], "usertype": credentials["usertype"], "registration_number": credentials["registration_number"], "chat_id": chat_id, "updated_at": datetime.utcnow()}},
            upsert=True,
        )
    except PyMongoError: pass

def credential_status(chat_id):
    status = {"complete": False, "credentials": {"name": "", "usertype": "", "registration_number": ""}}
    if chat_history is None: return status
    try:
        doc = chat_history.find_one({"chat_id": chat_id, "entry_type": "session_meta"}, {"_id": 0, "credentials": 1})
        if not doc: return status
        creds = doc.get("credentials", status["credentials"])
        complete = all(str(creds.get(key, "")).strip() for key in CREDENTIAL_KEYS)
        return {"complete": complete, "credentials": creds}
    except PyMongoError: return status

def save_credentials(chat_id, credentials):
    if chat_history is None: return
    try:
        chat_history.update_one(
            {"chat_id": chat_id, "entry_type": "session_meta"},
            {"$set": {"chat_id": chat_id, "entry_type": "session_meta", "credentials": {"name": credentials.get("name", "").strip(), "usertype": credentials.get("usertype", "").strip(), "registration_number": credentials.get("registration_number", "").strip()}, "updated_at": datetime.utcnow()}},
            upsert=True,
        )
    except PyMongoError: pass

@app.get("/api/health")
def health():
    try:
        if mongo_client is None: raise RuntimeError("MONGO_URI is not configured")
        mongo_client.admin.command("ping")
        return jsonify({"status": "ok", "database": "connected", "llm_key_configured": bool(GROQ_API_KEY)})
    except (PyMongoError, RuntimeError) as error:
        return jsonify({"status": "degraded", "database": "unavailable", "llm_key_configured": bool(GROQ_API_KEY), "detail": str(error)}), 503

@app.get("/api/chats")
def get_all_chats():
    if chat_history is None: return jsonify([])
    pipeline = [
        {"$sort": {"timestamp": 1}},
        {"$group": {"_id": "$chat_id", "title": {"$first": "$user_message"}, "last_updated": {"$last": "$timestamp"}}},
        {"$sort": {"last_updated": -1}},
    ]
    chats = list(chat_history.aggregate(pipeline))
    return jsonify([{"chat_id": item["_id"], "title": item["title"]} for item in chats])

@app.get("/api/chats/<chat_id>")
def get_chat(chat_id):
    if chat_history is None: return jsonify([])
    history = list(chat_history.find({"chat_id": chat_id, "entry_type": {"$ne": "session_meta"}}, {"_id": 0}).sort("timestamp", 1))
    return jsonify(history)

@app.post("/api/chat")
def chat():
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message", "")).strip()
    chat_id = str(payload.get("chat_id", "default_chat"))

    if not message: return jsonify({"error": "message is required"}), 400

    try:
        current_status = credential_status(chat_id)
        was_complete = bool(current_status.get("complete"))
        current_creds = current_status["credentials"]

        provided_credentials = payload.get("credentials") or {}
        parsed_from_message = parse_credentials_from_message(message)
        if parsed_from_message: provided_credentials = {**provided_credentials, **parsed_from_message}

        next_credentials = {
            "name": str(provided_credentials.get("name", current_creds.get("name", ""))).strip(),
            "usertype": str(provided_credentials.get("usertype", current_creds.get("usertype", ""))).strip(),
            "registration_number": str(provided_credentials.get("registration_number", current_creds.get("registration_number", ""))).strip(),
        }

        if not all(next_credentials.get(key) for key in CREDENTIAL_KEYS):
            save_credentials(chat_id, next_credentials)
            return jsonify({"answer": "Before trip planning, please send credentials in this format: Name | Student/Employee | RegistrationNumber/EmpID", "needs_credentials": True, "credential_format": "Name | Usertype | RegistrationNumber/EmpID", "plan": None})

        if next_credentials["usertype"] not in ("Student", "Employee"):
            return jsonify({"answer": "Invalid usertype. Please enter Student or Employee.", "needs_credentials": True, "plan": None})

        save_credentials(chat_id, next_credentials)
        upsert_user_if_ready(chat_id, next_credentials)

        if not was_complete:
            acknowledgement = f"Welcome {next_credentials['name']} ({next_credentials['usertype']}). Credentials recorded. You can now ask your trip question."
            if chat_history is not None:
                try: chat_history.insert_one({"chat_id": chat_id, "entry_type": "message", "user_message": message, "bot_response": acknowledgement, "plan": None, "credentials": next_credentials, "timestamp": datetime.utcnow()})
                except PyMongoError: pass
            return jsonify({"answer": acknowledgement, "plan": None, "needs_credentials": False})

        route_plan = plan_trip(payload)
        route_context = route_context_from_message(message)
        llm_result = call_llm(next_credentials, message, route_plan, route_context)

        response_payload = {
            "answer": llm_result["answer"],
            "plan": route_plan,
            "needs_credentials": False,
            "llm": {"intent": llm_result["intent"], "explanation": llm_result["explanation"], "next_action": llm_result["next_action"], "suggested_departure": llm_result["suggested_departure"], "confidence": llm_result["confidence"], "temperature": LLM_TEMPERATURE, "model": GROQ_MODEL}
        }

        if chat_history is not None:
            try: chat_history.insert_one({"chat_id": chat_id, "entry_type": "message", "user_message": message, "bot_response": response_payload["answer"], "plan": route_plan.get("recommendation"), "llm": response_payload["llm"], "credentials": next_credentials, "timestamp": datetime.utcnow()})
            except PyMongoError: pass

        return jsonify(response_payload)
    except Exception as error:
        return jsonify({"answer": f"I hit a runtime issue while processing your request: {error}", "needs_credentials": False, "plan": None}), 200

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=True)