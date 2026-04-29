# 🔥 Firebase Setup & Database Guide
## Secure Digital Voting System

---

## HOW TO VIEW YOUR FIREBASE DATABASE

### Step 1 — Open Firebase Console
Go to: **https://console.firebase.google.com**
→ Sign in with your Google account
→ Select your project (e.g. `securedigital-voting`)

### Step 2 — Open Realtime Database
In the left sidebar:
```
Build → Realtime Database
```
You'll see the live JSON tree of all your data.

### Step 3 — Navigating the Tree
Click the **▶ arrows** to expand nodes.
You can also edit values directly in the console (for admin use only).

---

## DATABASE STRUCTURE (After Fix)

```
your-project-default-rtdb/
│
├── votes_cast/                    ← WHO voted (NOT who they voted FOR)
│   ├── VOTER001/
│   │   ├── timestamp: "1700000000.5"
│   │   └── hash: "A1B2C3D4E5F6G7H8"
│   ├── VOTER002/
│   │   ├── timestamp: "1700000045.2"
│   │   └── hash: "Z9Y8X7W6V5U4T3S2"
│   └── ...
│
├── vote_counts/                   ← Anonymous tallies ONLY
│   ├── A: 5                       (integer — no voter names)
│   ├── B: 3
│   └── C: 2
│
├── fraud_log/                     ← Suspicious activity alerts
│   ├── -NxAbc123/
│   │   ├── type: "double_vote_attempt"
│   │   ├── voter_id: "VOTER007"
│   │   └── time: "1700000099.1"
│   └── ...
│
└── election_meta/                 ← Election state (persists across restarts)
    ├── voting_ended: false
    └── trust_score: 85
```

---

## WHY THIS STRUCTURE IS ETHICAL & SECURE

| Old (BROKEN) Structure | New (FIXED) Structure |
|---|---|
| `votes/VOTER001/candidate: "A"` ❌ | `votes_cast/VOTER001/hash: "..."` ✅ |
| Anyone with DB access knows who each person voted for | Candidate is NEVER stored with voter ID |
| Violates secret ballot principle | Secret ballot fully preserved |
| Illegal under election privacy laws | Compliant |

The **vote_counts/** node only stores numbers — there is no way to trace a number back to any voter.

---

## ENVIRONMENT VARIABLES TO SET

In your hosting platform (Render / Railway / Heroku):

| Variable | Value | Notes |
|---|---|---|
| `FIREBASE_URL` | `https://your-project-default-rtdb.firebaseio.com` | From Firebase Console → Project Settings |
| `FIREBASE_KEY` | Your Web API Key | Firebase Console → Project Settings → General → Web API Key |
| `SECRET_KEY` | Any long random string | e.g. `openssl rand -hex 32` |
| `ADMIN_PASSWORD` | Your chosen admin password | Default: `admin@securevote2024` — CHANGE THIS! |
| `FLASK_ENV` | `production` | Enables secure cookies over HTTPS |

---

## FIREBASE SECURITY RULES

In Firebase Console → Realtime Database → Rules, paste:

```json
{
  "rules": {
    "votes_cast": {
      ".read": "auth != null",
      "$voter_id": {
        ".write": "auth != null && !data.exists()"
      }
    },
    "vote_counts": {
      ".read": "auth != null",
      ".write": "auth != null"
    },
    "fraud_log": {
      ".read": "auth != null",
      ".write": "auth != null"
    },
    "election_meta": {
      ".read": "auth != null",
      ".write": "auth != null"
    }
  }
}
```

> For a demo/hackathon, you can temporarily use `"auth": null` (open rules),
> but always lock down before any real use.

---

## QUICK REFERENCE: WHAT YOU CAN SEE IN FIREBASE CONSOLE

| Node | What you see | Privacy status |
|---|---|---|
| `votes_cast/` | List of voter IDs + their hash/timestamp | ✅ Safe — no candidate info |
| `vote_counts/` | A=5, B=3, C=2 | ✅ Safe — fully anonymous |
| `fraud_log/` | Suspicious voter IDs + fraud type | ⚠ Admin only |
| `election_meta/` | voting_ended, trust_score | ✅ Safe |

---

## ACCESSING FIREBASE REST API DIRECTLY (for testing)

```bash
# View all vote counts
curl "https://YOUR-PROJECT.firebaseio.com/vote_counts.json?auth=YOUR_KEY"

# View all votes cast (no candidate info)
curl "https://YOUR-PROJECT.firebaseio.com/votes_cast.json?auth=YOUR_KEY"

# View election meta
curl "https://YOUR-PROJECT.firebaseio.com/election_meta.json?auth=YOUR_KEY"
```
