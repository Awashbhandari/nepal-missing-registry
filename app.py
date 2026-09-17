import os
import uuid
from datetime import datetime

from flask import (
    Flask, render_template, request, redirect, url_for, flash,
    session, jsonify, abort
)
from werkzeug.utils import secure_filename

from models import db, MissingPerson, DnaReference
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
DNA_UPLOAD_FOLDER = os.path.join(app.root_path, "static", "uploads", "dna_reports")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["DNA_UPLOAD_FOLDER"] = DNA_UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 6 * 1024 * 1024  # 6MB hard cap (photo + optional dna doc)

ALLOWED_PHOTO_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
ALLOWED_DNA_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme123")

RELATIONSHIP_OPTIONS = [
    ("parent", "Parent (mother/father)"),
    ("child", "Child"),
    ("sibling", "Full sibling"),
    ("spouse", "Spouse"),
    ("other", "Other relative"),
]

db.init_app(app)

with app.app_context():
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(DNA_UPLOAD_FOLDER, exist_ok=True)
    db.create_all()

PER_PAGE = 20


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _allowed(filename, allowed_set):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_set


def save_photo(file_storage):
    if not file_storage or file_storage.filename == "":
        return None
    if not _allowed(file_storage.filename, ALLOWED_PHOTO_EXTENSIONS):
        return None
    ext = file_storage.filename.rsplit(".", 1)[1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    file_storage.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
    return filename


def save_dna_report(file_storage):
    if not file_storage or file_storage.filename == "":
        return None
    if not _allowed(file_storage.filename, ALLOWED_DNA_EXTENSIONS):
        return None
    ext = file_storage.filename.rsplit(".", 1)[1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    file_storage.save(os.path.join(app.config["DNA_UPLOAD_FOLDER"], filename))
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
        MissingPerson.query.filter(MissingPerson.status.in_(["missing", "found_safe", "identified"]))
        .order_by(MissingPerson.created_at.desc())
        .limit(PER_PAGE)
        .all()
    )
    return render_template("index.html", missing_count=missing_count, found_count=found_count, people=recent)


@app.route("/api/stats")
def api_stats():
    missing_count, found_count = get_counts()
    return jsonify({"missing": missing_count, "found_safe": found_count})


@app.route("/api/live-match")
def api_live_match():
    """
    Called live (debounced) from the report form as the reporter types.
    Shows already-reported people that could match, narrowing the list as
    more fields (gender, district, ward, landmark) are filled in - so the
    reporter can see "is this person already listed?" before submitting.

    Uses broad substring matching (not strict fuzzy scoring) since the name
    may still be partially typed. Matches on LAST SEEN address, since that's
    what disambiguates reports about the same disaster event.
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
        MissingPerson.status.in_(["missing", "found_safe", "identified"]),
        MissingPerson.full_name.ilike(f"%{name}%"),
    )
    if gender:
        query = query.filter(MissingPerson.gender == gender)
    if district:
        query = query.filter(MissingPerson.last_seen_district.ilike(f"%{district}%"))
    if municipality:
        query = query.filter(MissingPerson.last_seen_municipality.ilike(f"%{municipality}%"))
    if ward_no:
        query = query.filter(MissingPerson.last_seen_ward_no.ilike(f"%{ward_no}%"))
    if landmark:
        query = query.filter(MissingPerson.last_seen_landmark.ilike(f"%{landmark}%"))

    results = query.order_by(MissingPerson.created_at.desc()).limit(15).all()
    return jsonify([serialize_person(p) for p in results])


@app.route("/search")
def search():
    q = request.args.get("q", "").strip()
    district = request.args.get("district", "").strip()
    status_filter = request.args.get("status", "").strip()
    dna_filter = request.args.get("dna", "").strip()  # "has" or "missing"
    page = max(int(request.args.get("page", 1)), 1)

    query = MissingPerson.query.filter(MissingPerson.status.in_(["missing", "found_safe", "identified"]))

    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(
                MissingPerson.full_name.ilike(like),
                MissingPerson.last_seen_landmark.ilike(like),
                MissingPerson.last_seen_municipality.ilike(like),
            )
        )
    if district:
        query = query.filter(MissingPerson.last_seen_district.ilike(f"%{district}%"))
    if status_filter in ("missing", "found_safe", "identified"):
        query = query.filter(MissingPerson.status == status_filter)

    query = query.order_by(MissingPerson.created_at.desc())
    all_matching = query.all()  # dna filter applied in python since it's a relationship check

    if dna_filter == "has":
        all_matching = [p for p in all_matching if p.has_dna_reference()]
    elif dna_filter == "missing":
        all_matching = [p for p in all_matching if not p.has_dna_reference()]

    total = len(all_matching)
    start = (page - 1) * PER_PAGE
    people = all_matching[start:start + PER_PAGE]
    has_more = start + PER_PAGE < total

    missing_count, found_count = get_counts()
    return render_template(
        "search.html",
        people=people, q=q, district=district, status_filter=status_filter, dna_filter=dna_filter,
        page=page, has_more=has_more, total=total,
        missing_count=missing_count, found_count=found_count,
    )


@app.route("/report", methods=["GET", "POST"])
def report():
    if request.method == "GET":
        return render_template("report.html", relationship_options=RELATIONSHIP_OPTIONS)

    full_name = request.form.get("full_name", "").strip()
    gender = request.form.get("gender", "").strip()

    if not full_name or not gender:
        flash("Name and gender are required.", "error")
        return render_template("report.html", form=request.form, relationship_options=RELATIONSHIP_OPTIONS)

    age = request.form.get("age", "").strip()
    age = int(age) if age.isdigit() else None

    last_seen_district = request.form.get("last_seen_district", "").strip() or None
    last_seen_municipality = request.form.get("last_seen_municipality", "").strip() or None
    last_seen_ward_no = request.form.get("last_seen_ward_no", "").strip() or None
    last_seen_landmark = request.form.get("last_seen_landmark", "").strip() or None

    home_district = request.form.get("home_district", "").strip() or None
    home_municipality = request.form.get("home_municipality", "").strip() or None
    home_ward_no = request.form.get("home_ward_no", "").strip() or None

    description = request.form.get("description", "").strip() or None
    reporter_name = request.form.get("reporter_name", "").strip() or None
    reporter_relation = request.form.get("reporter_relation", "").strip() or None
    reporter_phone = request.form.get("reporter_phone", "").strip() or None

    # Optional DNA reference fields
    dna_sample_giver = request.form.get("dna_sample_giver", "").strip() or None
    dna_relationship = request.form.get("dna_relationship", "").strip() or None
    dna_lab_name = request.form.get("dna_lab_name", "").strip() or None
    dna_report_ref = request.form.get("dna_report_ref", "").strip() or None
    dna_test_date = request.form.get("dna_test_date", "").strip() or None

    # Check "confirm anyway" flag - set when the reporter has already seen
    # possible duplicates and confirmed this is a genuinely separate person.
    confirmed_new = request.form.get("confirmed_new") == "1"

    if not confirmed_new:
        duplicates = find_possible_duplicates(
            full_name, gender, age, last_seen_district, last_seen_municipality, last_seen_ward_no
        )
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
        last_seen_district=last_seen_district,
        last_seen_municipality=last_seen_municipality,
        last_seen_ward_no=last_seen_ward_no,
        last_seen_landmark=last_seen_landmark,
        home_district=home_district,
        home_municipality=home_municipality,
        home_ward_no=home_ward_no,
        description=description,
        photo_filename=photo_filename,
        reporter_name=reporter_name,
        reporter_relation=reporter_relation,
        reporter_phone=reporter_phone,
        status="missing",
    )
    db.session.add(person)
    db.session.flush()  # get person.id before adding dna reference

    # Only create a DNA reference if the reporter actually filled in the
    # minimum required bits (sample-giver name + relationship)
    if dna_sample_giver and dna_relationship:
        dna_file = save_dna_report(request.files.get("dna_report_file"))
        dna_ref = DnaReference(
            missing_person_id=person.id,
            sample_giver_name=dna_sample_giver,
            relationship_to_missing=dna_relationship,
            lab_name=dna_lab_name,
            report_reference_no=dna_report_ref,
            test_date=dna_test_date,
            report_filename=dna_file,
        )
        db.session.add(dna_ref)

    db.session.commit()

    flash("Report submitted. Thank you.", "success")
    return redirect(url_for("person_detail", person_id=person.id))


@app.route("/person/<int:person_id>")
def person_detail(person_id):
    person = MissingPerson.query.get_or_404(person_id)
    return render_template("person_detail.html", person=person, relationship_options=RELATIONSHIP_OPTIONS)


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


@app.route("/person/<int:person_id>/mark-identified", methods=["GET", "POST"])
def mark_identified(person_id):
    """
    For use by government/forensic/rescue teams after a recovered body has
    been matched to this missing-person record via lab DNA kinship
    comparison done on their own systems. This route only records that
    outcome - it does not perform any DNA comparison itself.
    """
    person = MissingPerson.query.get_or_404(person_id)

    if request.method == "GET":
        return render_template("mark_identified.html", person=person)

    if person.status not in ("missing", "found_safe"):
        flash("This record's status cannot be changed to Identified from its current state.", "error")
        return redirect(url_for("person_detail", person_id=person.id))

    official_name = request.form.get("official_name", "").strip()
    official_org = request.form.get("official_org", "").strip()
    lab_name = request.form.get("lab_name", "").strip()
    note = request.form.get("note", "").strip()

    if not official_name or not official_org:
        flash("Please provide the confirming official's name and organization.", "error")
        return render_template("mark_identified.html", person=person)

    person.status = "identified"
    person.identified_note = (
        f"Confirmed by {official_name} ({official_org})."
        + (f" Lab: {lab_name}." if lab_name else "")
        + (f" {note}" if note else "")
    ).strip()
    person.updated_at = datetime.utcnow()
    db.session.commit()

    flash(f"{person.full_name} has been marked as Identified.", "success")
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
