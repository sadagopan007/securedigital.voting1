from flask import Flask, render_template, request, session, redirect, url_for, jsonify
import random
import hashlib
import time
import os
import csv
import requests as req

app = Flask(__name__)

# ── SECRET KEY ───────────────────────────────────────────────────────
_secret = os.environ.get("SECRET_KEY")
if not _secret:
    import secrets
    _secret = secrets.token_hex(32)
    print("⚠ WARNING: SECRET_KEY not set. Using random key — sessions reset on restart!")

app.secret_key = _secret
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"]   = os.environ.get("FLASK_ENV") == "production"
app.config["SESSION_COOKIE_HTTPONLY"] = True

# ── FIREBASE ─────────────────────────────────────────────────────────
FIREBASE_URL = os.environ.get("FIREBASE_URL")
FIREBASE_KEY = os.environ.get("FIREBASE_KEY")

def fb_get(path):
    try:
        r = req.get(f"{FIREBASE_URL}/{path}.json?auth={FIREBASE_KEY}", timeout=10)
        return r.json() if r.ok else None
    except Exception as e:
        print(f"[fb_get] {path} exception: {e}"); return None

def fb_set(path, data):
    try:
        r = req.put(f"{FIREBASE_URL}/{path}.json?auth={FIREBASE_KEY}", json=data, timeout=10)
        return r.ok
    except Exception as e:
        print(f"[fb_set] {path} exception: {e}"); return False

def fb_push(path, data):
    try:
        r = req.post(f"{FIREBASE_URL}/{path}.json?auth={FIREBASE_KEY}", json=data, timeout=10)
        return r.ok
    except Exception as e:
        print(f"[fb_push] {path} exception: {e}"); return False

def fb_delete(path):
    try:
        r = req.delete(f"{FIREBASE_URL}/{path}.json?auth={FIREBASE_KEY}", timeout=10)
        return r.ok
    except Exception as e:
        print(f"[fb_delete] {path} exception: {e}"); return False

print("✅ Firebase REST client ready!")
print(f"   URL: {FIREBASE_URL}")

# ── VOTER DATABASE ────────────────────────────────────────────────────
def load_voters():
    voters = {}
    try:
        with open("voters.csv", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                voters[row["voter_id"].strip().upper()] = row["aadhaar"].strip()
        print(f"✅ Loaded {len(voters)} voters from voters.csv")
    except FileNotFoundError:
        print("❌ voters.csv not found!")
    return voters

VOTER_DATABASE = load_voters()
login_attempts = {}  # rate-limiting only, not critical state

CANDIDATES = [
    {"id": "A", "name": "Arun Kumar",   "party": "Progressive Alliance", "symbol": "🌟"},
    {"id": "B", "name": "Bhavna Mehta", "party": "United Front",         "symbol": "🔥"},
    {"id": "C", "name": "Chetan Rao",   "party": "People's Party",       "symbol": "🌿"},
]

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin@securevote2024")

def db_voter_voted(voter_id):
    return fb_get(f"votes_cast/{voter_id}") is not None

def db_cast_vote(voter_id, timestamp, vote_hash, candidate_id):
    ok1 = fb_set(f"votes_cast/{voter_id}", {"timestamp": str(timestamp), "hash": vote_hash})
    current = fb_get(f"vote_counts/{candidate_id}") or 0
    ok2 = fb_set(f"vote_counts/{candidate_id}", current + 1)
    return ok1 and ok2

def db_get_vote_counts():
    data = fb_get("vote_counts")
    counts = {c["id"]: 0 for c in CANDIDATES}
    if data:
        for cid in counts:
            counts[cid] = data.get(cid, 0)
    return counts

def db_get_votes_cast():
    data = fb_get("votes_cast")
    return data if data else {}

def db_log_fraud(fraud_type, voter_id):
    fb_push("fraud_log", {"type": fraud_type, "voter_id": voter_id, "time": str(time.time())})

def db_get_fraud_log():
    data = fb_get("fraud_log")
    if not data: return []
    items = list(data.values())
    items.sort(key=lambda x: float(x.get("time", 0)), reverse=True)
    return items[:10]

def db_get_meta():
    data = fb_get("election_meta")
    if not data: return {"voting_ended": False, "trust_score": 100}
    return {"voting_ended": data.get("voting_ended", False), "trust_score": data.get("trust_score", 100)}

def db_set_meta(**kwargs):
    meta = db_get_meta()
    meta.update(kwargs)
    if "trust_score" in meta:
        meta["trust_score"] = max(0, meta["trust_score"])
    fb_set("election_meta", meta)
    return meta

def db_reduce_trust(amount=10):
    meta = db_get_meta()
    db_set_meta(trust_score=meta["trust_score"] - amount)

def db_reset():
    fb_delete("votes_cast")
    fb_delete("vote_counts")
    fb_delete("fraud_log")
    fb_set("election_meta", {"voting_ended": False, "trust_score": 100})
    print("✅ Firebase data cleared!")

def generate_vote_hash(voter_id, candidate, timestamp):
    data = f"{voter_id}{candidate}{timestamp}"
    return hashlib.sha256(data.encode()).hexdigest()[:16].upper()

def get_results():
    return db_get_vote_counts()

# ── ROUTES ────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return redirect(url_for("login"))

@app.route("/login")
def login():
    meta = db_get_meta()
    return render_template("login.html", voting_ended=meta["voting_ended"])

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        if request.form.get("password", "") == ADMIN_PASSWORD:
            session["is_admin"] = True
            session.modified = True
            return redirect(url_for("admin"))
        error = "❌ Incorrect password. Access denied."
    return render_template("admin_login.html", error=error)

@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("admin_login"))

@app.route("/admin")
def admin():
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))
    meta        = db_get_meta()
    votes_cast  = db_get_votes_cast()
    fraud_log   = db_get_fraud_log()
    results     = get_results()
    total_votes = len(votes_cast)
    results_with_names = [
        {**c, "votes": results[c["id"]],
         "pct": round(results[c["id"]] / total_votes * 100) if total_votes else 0}
        for c in CANDIDATES
    ]
    return render_template("admin.html",
                           candidates=results_with_names,
                           total_votes=total_votes,
                           trust_score=meta["trust_score"],
                           fraud_log=fraud_log,
                           votes=votes_cast,
                           voting_ended=meta["voting_ended"])

@app.route("/end_voting", methods=["POST"])
def end_voting():
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))
    db_set_meta(voting_ended=True)
    return redirect(url_for("admin"))

# ── VOTER FLOW ────────────────────────────────────────────────────────
@app.route("/send_otp", methods=["POST"])
def send_otp():
    meta = db_get_meta()
    if meta["voting_ended"]:
        return render_template("login.html", voting_ended=True,
            error="⚠ Voting has ended. No more votes accepted.")

    voter_id = request.form.get("voter_id", "").strip().upper()
    aadhaar  = request.form.get("aadhaar", "").strip()

    if not voter_id or not aadhaar:
        return render_template("login.html", voting_ended=False, error="Please fill all fields.")

    if len(aadhaar) != 12 or not aadhaar.isdigit():
        return render_template("login.html", voting_ended=False, error="Aadhaar must be 12 digits.")

    if voter_id not in VOTER_DATABASE:
        db_log_fraud("unregistered_voter", voter_id); db_reduce_trust(10)
        return render_template("login.html", voting_ended=False,
            error="⚠ Voter ID not found. This attempt has been flagged.", alert=True)

    if VOTER_DATABASE[voter_id] != aadhaar:
        db_log_fraud("aadhaar_mismatch", voter_id); db_reduce_trust(10)
        return render_template("login.html", voting_ended=False,
            error="⚠ Aadhaar does not match. This attempt has been flagged.", alert=True)

    if db_voter_voted(voter_id):
        db_log_fraud("double_vote_attempt", voter_id); db_reduce_trust(10)
        return render_template("login.html", voting_ended=False,
            error="⚠ This Voter ID has already voted. Attempt flagged.", alert=True)

    attempts = login_attempts.get(voter_id, 0)
    if attempts >= 5:
        db_log_fraud("brute_force", voter_id); db_reduce_trust(15)
        return render_template("login.html", voting_ended=False,
            error="⚠ Too many attempts. Contact election office.", alert=True)

    otp = random.randint(100000, 999999)

    # ══════════════════════════════════════════════════════════════════════
    # ROOT CAUSE FIX — store OTP in the Flask session COOKIE, not a dict.
    #
    # The old code stored OTP in otp_storage = {} — a plain Python dict
    # that lives in one worker's memory. Gunicorn starts multiple worker
    # processes. Each worker has its own separate memory space:
    #
    #   Worker 1  handles POST /send_otp  → saves OTP in Worker 1's dict
    #   Worker 2  handles POST /verify_otp → Worker 2's dict is EMPTY
    #                                      → "Session expired" error
    #
    # Storing OTP in session[] puts it in a signed cookie that the browser
    # sends back on every request — it reaches whichever worker handles it.
    # ══════════════════════════════════════════════════════════════════════
    session["pending_voter_id"] = voter_id
    session["pending_otp"]      = str(otp)
    session["otp_expires_at"]   = time.time() + 300
    session["authenticated"]    = False
    session.modified            = True

    login_attempts[voter_id] = attempts + 1

    # ⚠ PRODUCTION: Replace otp_demo with real SMS/email delivery!
    print(f"\n{'='*40}\n  OTP for {voter_id}: {otp}\n{'='*40}\n")
    return render_template("otp.html", voter_id=voter_id, otp_demo=otp)


@app.route("/verify_otp", methods=["POST"])
def verify_otp():
    voter_id    = request.form.get("voter_id", "").strip().upper()
    entered_otp = request.form.get("otp", "").strip()
    meta        = db_get_meta()

    # Read OTP from session cookie — works across all Gunicorn workers
    pending_id = session.get("pending_voter_id", "")
    stored_otp = session.get("pending_otp", "")
    expires_at = session.get("otp_expires_at", 0)

    if not stored_otp or pending_id != voter_id:
        return render_template("login.html", voting_ended=meta["voting_ended"],
                               error="Session expired. Please login again.")

    if time.time() > expires_at:
        session.pop("pending_voter_id", None)
        session.pop("pending_otp", None)
        session.pop("otp_expires_at", None)
        session.modified = True
        return render_template("login.html", voting_ended=meta["voting_ended"],
                               error="OTP expired. Please login again.")

    if stored_otp != entered_otp:
        db_log_fraud("wrong_otp", voter_id); db_reduce_trust(5)
        return render_template("otp.html", voter_id=voter_id,
                               error="Wrong OTP. Try again.", otp_demo=int(stored_otp))

    # ✅ OTP verified — clear OTP keys, grant voter session
    session.pop("pending_voter_id", None)
    session.pop("pending_otp", None)
    session.pop("otp_expires_at", None)
    session.pop("is_admin", None)
    session["voter_id"]      = voter_id
    session["authenticated"] = True
    session.modified         = True
    return redirect(url_for("vote"))


@app.route("/vote")
def vote():
    voter_id = session.get("voter_id")
    if not voter_id or not session.get("authenticated"):
        return redirect(url_for("login"))
    if db_voter_voted(voter_id):
        return redirect(url_for("success"))
    return render_template("vote.html", voter_id=voter_id, candidates=CANDIDATES)

@app.route("/cast_vote", methods=["POST"])
def cast_vote():
    voter_id  = session.get("voter_id")
    if not voter_id or not session.get("authenticated"):
        return redirect(url_for("login"))

    candidate = request.form.get("candidate")

    if db_voter_voted(voter_id):
        db_log_fraud("double_vote", voter_id); db_reduce_trust(10)
        return render_template("vote.html", voter_id=voter_id, candidates=CANDIDATES,
                               error="Fraud detected! You already voted.")

    if candidate not in [c["id"] for c in CANDIDATES]:
        return render_template("vote.html", voter_id=voter_id, candidates=CANDIDATES,
                               error="Invalid candidate selected.")

    timestamp = time.time()
    vote_hash = generate_vote_hash(voter_id, candidate, timestamp)
    ok        = db_cast_vote(voter_id, timestamp, vote_hash, candidate)

    if not ok:
        return render_template("vote.html", voter_id=voter_id, candidates=CANDIDATES,
                               error="Database error. Please try again.")

    session["vote_hash"]     = vote_hash
    session["voted_for"]     = candidate
    session["authenticated"] = False
    session.modified         = True
    return redirect(url_for("success"))

@app.route("/success")
def success():
    candidate_id = session.get("voted_for")
    vote_hash    = session.get("vote_hash", "N/A")
    if not candidate_id:
        return redirect(url_for("login"))
    candidate = next((c for c in CANDIDATES if c["id"] == candidate_id), None)
    return render_template("success.html", vote_hash=vote_hash, candidate=candidate)

@app.route("/api/results")
def api_results():
    meta = db_get_meta()
    if not meta["voting_ended"]:
        return jsonify({"error": "Voting is still in progress. Results available after voting ends."}), 403
    return jsonify({
        "results":      get_results(),
        "total":        len(db_get_votes_cast()),
        "trust_score":  meta["trust_score"],
        "fraud_events": len(db_get_fraud_log()),
        "voting_ended": meta["voting_ended"]
    })

@app.route("/reset")
def reset():
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))
    global login_attempts
    db_reset()
    login_attempts = {}
    # Keep is_admin so the redirect to /admin succeeds
    session.pop("voter_id", None)
    session.pop("authenticated", None)
    session.pop("voted_for", None)
    session.pop("vote_hash", None)
    session.pop("pending_voter_id", None)
    session.pop("pending_otp", None)
    session.pop("otp_expires_at", None)
    session.modified = True
    return redirect(url_for("admin"))

# NOTE: /database route REMOVED — it was exposing all Aadhaar numbers publicly!

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
