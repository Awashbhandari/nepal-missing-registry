import os
import uuid
from datetime import datetime

from flask import (
    Flask, render_template, request, redirect, url_for, flash,
    session, jsonify, abort
)
from werkzeug.utils import secure_filename

from models import db, MissingPerson
from duplicate_check import find_possible_duplicates

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")

# Database: SQLite locally, Postgres (e.g. Supabase) in production via DATABASE_URL
db_url = os.environ.get("DATABASE_URL", "sqlite:///registry.db")
if db_url.startswith("postgres://"):  # Render/Supabase sometimes give the old scheme
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

UPLOAD_FOLDER = os.path.join(app.root_path, "static", "uploads")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 3 * 1024 * 1024  # 3MB hard cap (photo should be pre-compressed client-side)
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme123")

db.init_app(app)

with app.app_context():
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    db.create_all()

PER_PAGE = 20


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_photo(file_storage):
    if not file_storage or file_storage.filename == "":
        return None
    if not allowed_file(file_storage.filename):
        return None
    ext = file_storage.filename.rsplit(".", 1)[1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    file_storage.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
    return filename


def get_counts():
    missing_count = MissingPerson.query.filter_by(status="missing").count()
    found_count = MissingPerson.query.filter_by(status="found_safe").count()
    return missing_count, found_count


def serialize_person(p):
    data = p.to_dict()
    data["photo_url"] = url_for("static", filename=f"uploads/{p.photo_filename}") if p.photo_filename else None
    data["detail_url"] = url_for("person_detail", person_id=p.id)
    return data


def require_admin():
    if not session.get("is_admin"):
        abort(403)


# ---------------------------------------------------------------------------
# Public routes
# ---------------------------------------------------------------------------
@app.route("/")
def home():
    missing_count, found_count = get_counts()
    recent = (
        MissingPerson.query.filter(MissingPerson.status.in_(["missing", "found_safe"]))
        .order_by(MissingPerson.created_at.desc())
        .limit(PER_PAGE)
        .all()
    )
    return render_template("index.html", missing_count=missing_count, found_count=found_count, people=recent)


@app.route("/api/stats")
def api_stats():
    missing_count, found_count = get_counts()
    return jsonify({"missing": missing_count, "found_safe": found_count})


@app.route("/search")
def search():
    q = request.args.get("q", "").strip()
    district = request.args.get("district", "").strip()
    status_filter = request.args.get("status", "").strip()
    page = max(int(request.args.get("page", 1)), 1)

    query = MissingPerson.query.filter(MissingPerson.status.in_(["missing", "found_safe"]))

    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(
                MissingPerson.full_name.ilike(like),
                MissingPerson.landmark.ilike(like),
                MissingPerson.municipality.ilike(like),
            )
        )
    if district:
        query = query.filter(MissingPerson.district.ilike(f"%{district}%"))
    if status_filter in ("missing", "found_safe"):
        query = query.filter(MissingPerson.status == status_filter)

    query = query.order_by(MissingPerson.created_at.desc())
    total = query.count()
    people = query.offset((page - 1) * PER_PAGE).limit(PER_PAGE).all()
    has_more = page * PER_PAGE < total

    missing_count, found_count = get_counts()
    return render_template(
        "search.html",
        people=people, q=q, district=district, status_filter=status_filter,
        page=page, has_more=has_more, total=total,
        missing_count=missing_count, found_count=found_count,
    )


@app.route("/api/live-match")
def api_live_match():
    """
    Called live (debounced) from the report form as the reporter types.
    Shows already-reported people that could match, narrowing the list as
    more fields (gender, district, ward, landmark) are filled in - so the
    reporter can see "is this person already listed?" before submitting.

    Uses broad substring matching (not strict fuzzy scoring) since the name
    may still be partially typed.
    """
    name = request.args.get("full_name", "").strip()
    gender = request.args.get("gender", "").strip()
    district = request.args.get("district", "").strip()
    municipality = request.args.get("municipality", "").strip()
    ward_no = request.args.get("ward_no", "").strip()
    landmark = request.args.get("landmark", "").strip()

    if len(name) < 2:
        return jsonify([])

    query = MissingPerson.query.filter(
        MissingPerson.status.in_(["missing", "found_safe"]),
        MissingPerson.full_name.ilike(f"%{name}%"),
    )
    if gender:
        query = query.filter(MissingPerson.gender == gender)
    if district:
        query = query.filter(MissingPerson.district.ilike(f"%{district}%"))
    if municipality:
        query = query.filter(MissingPerson.municipality.ilike(f"%{municipality}%"))
    if ward_no:
        query = query.filter(MissingPerson.ward_no.ilike(f"%{ward_no}%"))
    if landmark:
        query = query.filter(MissingPerson.landmark.ilike(f"%{landmark}%"))

    results = query.order_by(MissingPerson.created_at.desc()).limit(15).all()
    return jsonify([serialize_person(p) for p in results])


@app.route("/report", methods=["GET", "POST"])
def report():
    if request.method == "GET":
        return render_template("report.html")

    full_name = request.form.get("full_name", "").strip()
    gender = request.form.get("gender", "").strip()

    if not full_name or not gender:
        flash("Name and gender are required.", "error")
        return render_template("report.html", form=request.form)

    age = request.form.get("age", "").strip()
    age = int(age) if age.isdigit() else None
    district = request.form.get("district", "").strip() or None
    municipality = request.form.get("municipality", "").strip() or None
    ward_no = request.form.get("ward_no", "").strip() or None
    landmark = request.form.get("landmark", "").strip() or None
    description = request.form.get("description", "").strip() or None
    reporter_name = request.form.get("reporter_name", "").strip() or None
    reporter_relation = request.form.get("reporter_relation", "").strip() or None
    reporter_phone = request.form.get("reporter_phone", "").strip() or None

    # Check "confirm anyway" flag - set when the reporter has already seen
    # possible duplicates and confirmed this is a genuinely separate person.
    confirmed_new = request.form.get("confirmed_new") == "1"

    if not confirmed_new:
        duplicates = find_possible_duplicates(full_name, gender, age, district, municipality, ward_no)
        if duplicates:
            return render_template(
                "possible_duplicates.html",
                duplicates=duplicates,
                form=request.form,
            )

    photo_filename = save_photo(request.files.get("photo"))

    person = MissingPerson(
        full_name=full_name,
        age=age,
        gender=gender,
        district=district,
        municipality=municipality,
        ward_no=ward_no,
        landmark=landmark,
        description=description,
        photo_filename=photo_filename,
        reporter_name=reporter_name,
        reporter_relation=reporter_relation,
        reporter_phone=reporter_phone,
        status="missing",
    )
    db.session.add(person)
    db.session.commit()

    flash("Report submitted. Thank you.", "success")
    return redirect(url_for("person_detail", person_id=person.id))


@app.route("/person/<int:person_id>")
def person_detail(person_id):
    person = MissingPerson.query.get_or_404(person_id)
    return render_template("person_detail.html", person=person)


@app.route("/person/<int:person_id>/mark-found", methods=["GET", "POST"])
def mark_found(person_id):
    person = MissingPerson.query.get_or_404(person_id)

    if request.method == "GET":
        return render_template("mark_found.html", person=person)

    if person.status != "missing":
        flash("This record is not currently marked missing.", "error")
        return redirect(url_for("person_detail", person_id=person.id))

    confirmer_name = request.form.get("confirmer_name", "").strip()
    confirmer_phone = request.form.get("confirmer_phone", "").strip()
    note = request.form.get("note", "").strip()

    if not confirmer_name or not confirmer_phone:
        flash("Please provide your name and phone number to confirm.", "error")
        return render_template("mark_found.html", person=person)

    person.status = "found_safe"
    person.found_note = f"Confirmed by {confirmer_name} ({confirmer_phone}). {note}".strip()
    person.updated_at = datetime.utcnow()
    db.session.commit()

    flash(f"{person.full_name} has been marked as Found Safe.", "success")
    return redirect(url_for("person_detail", person_id=person.id))


# ---------------------------------------------------------------------------
# Admin (simple password-based moderation)
# ---------------------------------------------------------------------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect(url_for("admin_dashboard"))
        flash("Incorrect password.", "error")
    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("home"))


@app.route("/admin")
def admin_dashboard():
    require_admin()
    people = MissingPerson.query.order_by(MissingPerson.created_at.desc()).limit(200).all()
    missing_count, found_count = get_counts()
    return render_template("admin.html", people=people, missing_count=missing_count, found_count=found_count)


@app.route("/admin/person/<int:person_id>/reject", methods=["POST"])
def admin_reject(person_id):
    require_admin()
    person = MissingPerson.query.get_or_404(person_id)
    person.status = "rejected"
    db.session.commit()
    flash("Record rejected/hidden.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/person/<int:person_id>/restore", methods=["POST"])
def admin_restore(person_id):
    require_admin()
    person = MissingPerson.query.get_or_404(person_id)
    person.status = "missing"
    db.session.commit()
    flash("Record restored to missing.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/person/<int:person_id>/merge/<int:target_id>", methods=["POST"])
def admin_merge(person_id, target_id):
    require_admin()
    person = MissingPerson.query.get_or_404(person_id)
    target = MissingPerson.query.get_or_404(target_id)
    person.status = "merged"
    person.merged_into_id = target.id
    db.session.commit()
    flash(f"Merged '{person.full_name}' into record #{target.id}.", "success")
    return redirect(url_for("admin_dashboard"))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
