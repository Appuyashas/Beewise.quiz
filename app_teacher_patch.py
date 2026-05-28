# ════════════════════════════════════════════════════════════════════
#  QuizBee — Teacher Account Patch
#  Instructions: Find each section in your app.py and replace/add
#  as shown. Each block is clearly labelled.
# ════════════════════════════════════════════════════════════════════


# ── SECTION 1 ─────────────────────────────────────────────────────
# Near the top where ADMIN_CODE is defined, ADD this line below it:
# ──────────────────────────────────────────────────────────────────

ADMIN_CODE   = os.environ.get("ADMIN_CODE",   "ADMIN2025")
TEACHER_CODE = os.environ.get("TEACHER_CODE", "TEACHER2025")   # ← ADD THIS


# ── SECTION 2 ─────────────────────────────────────────────────────
# Inside init_db(), in the migration loop, ADD this entry:
# ──────────────────────────────────────────────────────────────────

for col, defn in [
    ("tab_switches", "INTEGER DEFAULT 0"),
    ("user_ans",     "INTEGER DEFAULT -1"),
    ("correct_ans",  "INTEGER DEFAULT 0"),
    ("avatar",       "TEXT DEFAULT '🐝'"),
    ("streak",       "INTEGER DEFAULT 0"),
    ("last_play",    "TEXT DEFAULT NULL"),
    ("role",         "TEXT DEFAULT 'student'"),   # ← ADD THIS LINE
]:
    try:
        tbl = "users" if col in ("avatar","streak","last_play","role") else \
              "results" if col == "tab_switches" else "answer_log"
        conn.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {defn}")
    except: pass

# Also run this once to migrate existing admins to new role column:
# conn.execute("UPDATE users SET role='admin' WHERE is_admin=1")


# ── SECTION 3 ─────────────────────────────────────────────────────
# Replace your two decorators (require_login, require_admin)
# with these three:
# ──────────────────────────────────────────────────────────────────

def require_login(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/")
        return f(*args, **kwargs)
    return decorated

def require_teacher(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("role") not in ("teacher", "admin"):
            flash("Teacher access required.", "error")
            return redirect("/dashboard")
        return f(*args, **kwargs)
    return decorated

def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Admin access required.", "error")
            return redirect("/dashboard")
        return f(*args, **kwargs)
    return decorated


# ── SECTION 4 ─────────────────────────────────────────────────────
# In the login POST handler, update the session setup block.
# Find where session["is_admin"] is set and REPLACE that block:
# ──────────────────────────────────────────────────────────────────

if user:
    session.clear()
    session["user_id"]  = user["id"]
    session["username"] = user["username"]
    session["role"]     = user["role"] if "role" in user.keys() else ("admin" if user["is_admin"] else "student")
    session["is_admin"] = (session["role"] == "admin")      # keep for backward compat
    session["is_teacher"] = (session["role"] == "teacher")
    session["avatar"]   = user["avatar"] or "🐝"
    return redirect("/dashboard")


# ── SECTION 5 ─────────────────────────────────────────────────────
# In the register POST handler, REPLACE the existing role/admin logic.
# Find where admin_code is checked and replace:
# ──────────────────────────────────────────────────────────────────

admin_code   = request.form.get("admin_code","").strip()
teacher_code = request.form.get("teacher_code","").strip()

if admin_code and admin_code == ADMIN_CODE:
    role = "admin"
elif teacher_code and teacher_code == TEACHER_CODE:
    role = "teacher"
else:
    role = "student"

is_admin = 1 if role == "admin" else 0   # keep column for compat

with get_db() as conn:
    conn.execute(
        "INSERT INTO users (username, password, is_admin, role) VALUES (?,?,?,?)",
        (username, hash_pw(password), is_admin, role)
    )


# ── SECTION 6 ─────────────────────────────────────────────────────
# ADD these new teacher routes anywhere after your existing routes.
# Best placed just before the admin routes.
# ──────────────────────────────────────────────────────────────────

@app.route("/teacher")
@require_login
@require_teacher
def teacher_dashboard():
    tid = session["user_id"]
    with get_db() as conn:
        # Classes this teacher owns
        classes = conn.execute(
            "SELECT * FROM classes WHERE admin_id=?", (tid,)
        ).fetchall()

        class_data = []
        for cls in classes:
            # Students in this class
            students = conn.execute("""
                SELECT u.id, u.username, u.avatar, u.streak,
                       COUNT(r.id)              AS games,
                       ROUND(AVG(r.pct),1)      AS avg_pct,
                       MAX(r.pct)               AS best,
                       MAX(r.played_at)         AS last_played
                FROM class_members cm
                JOIN users    u ON u.id = cm.user_id
                LEFT JOIN results r ON r.user_id = u.id
                WHERE cm.class_id=?
                GROUP BY u.id
                ORDER BY avg_pct DESC NULLS LAST
            """, (cls["id"],)).fetchall()
            class_data.append({"cls": cls, "students": students})

    return render_template("teacher_dashboard.html",
                           class_data=class_data,
                           total_classes=len(classes))


@app.route("/teacher/student/<int:uid>")
@require_login
@require_teacher
def teacher_student_view(uid):
    """Teacher can only view students in their own classes."""
    tid = session["user_id"]
    with get_db() as conn:
        # Security: ensure student is in one of teacher's classes
        allowed = conn.execute("""
            SELECT 1 FROM class_members cm
            JOIN classes c ON c.id = cm.class_id
            WHERE cm.user_id=? AND c.admin_id=?
        """, (uid, tid)).fetchone()

        if not allowed:
            flash("You can only view students in your own classes.", "error")
            return redirect("/teacher")

        student = conn.execute(
            "SELECT id, username, avatar, streak FROM users WHERE id=?", (uid,)
        ).fetchone()

        results = conn.execute("""
            SELECT mode, score, total, pct, grade, time_taken,
                   tab_switches, played_at
            FROM results WHERE user_id=?
            ORDER BY played_at DESC LIMIT 50
        """, (uid,)).fetchall()

        stats = conn.execute("""
            SELECT COUNT(*)           AS games,
                   ROUND(AVG(pct),1)  AS avg_pct,
                   MAX(pct)           AS best,
                   MIN(pct)           AS worst
            FROM results WHERE user_id=?
        """, (uid,)).fetchone()

        cat_stats = conn.execute("""
            SELECT al.category,
                   COUNT(*)                                   AS total,
                   SUM(al.user_ans = al.correct_ans)         AS correct,
                   ROUND(100.0*SUM(al.user_ans=al.correct_ans)/COUNT(*),1) AS pct
            FROM answer_log al
            JOIN results r ON r.id = al.result_id
            WHERE r.user_id=?
            GROUP BY al.category
            ORDER BY pct ASC
        """, (uid,)).fetchall()

        earned = conn.execute(
            "SELECT ach_id FROM achievements WHERE user_id=?", (uid,)
        ).fetchall()

    return render_template("student_report.html",
                           student=student, results=results,
                           stats=stats, cat_stats=cat_stats,
                           earned=earned, ach_map={},
                           back_url="/teacher")


@app.route("/teacher/class/create", methods=["POST"])
@require_login
@require_teacher
def teacher_create_class():
    name = request.form.get("name","").strip()
    if not name:
        flash("Class name cannot be empty.", "error")
        return redirect("/teacher")
    import secrets as _sec
    code = _sec.token_hex(3).upper()   # e.g. "A3F9C1"
    with get_db() as conn:
        conn.execute(
            "INSERT INTO classes (name, code, admin_id) VALUES (?,?,?)",
            (name, code, session["user_id"])
        )
    flash(f'Class "{name}" created! Join code: {code}', "success")
    return redirect("/teacher")