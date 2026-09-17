from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class MissingPerson(db.Model):
    __tablename__ = "missing_person"

    id = db.Column(db.Integer, primary_key=True)

    # Person details (name + gender are the only required fields - everything
    # else may be unknown in the chaos right after a disaster)
    full_name = db.Column(db.String(150), nullable=False)
    age = db.Column(db.Integer, nullable=True)  # approximate age is fine
    gender = db.Column(db.String(20), nullable=False)  # male/female/other

    # Where they were LAST SEEN / went missing (ward/municipality level -
    # district alone is far too broad after a large disaster)
    last_seen_district = db.Column(db.String(100), nullable=True, index=True)
    last_seen_municipality = db.Column(db.String(150), nullable=True)
    last_seen_ward_no = db.Column(db.String(20), nullable=True)
    last_seen_landmark = db.Column(db.String(200), nullable=True)  # tole / nearest known point

    # Their HOME address (separate from where they went missing - useful for
    # reunification and for authorities trying to reach the family)
    home_district = db.Column(db.String(100), nullable=True)
    home_municipality = db.Column(db.String(150), nullable=True)
    home_ward_no = db.Column(db.String(20), nullable=True)

    description = db.Column(db.Text, nullable=True)  # clothing, marks, etc.
    photo_filename = db.Column(db.String(300), nullable=True)

    # Reporter (person submitting this report)
    reporter_name = db.Column(db.String(150), nullable=True)
    reporter_relation = db.Column(db.String(100), nullable=True)
    reporter_phone = db.Column(db.String(30), nullable=True)

    # Status: missing, found_safe, identified, rejected, merged
    # "identified" = a body has been matched via lab DNA kinship comparison
    # and confirmed deceased - distinct from "found_safe".
    status = db.Column(db.String(20), nullable=False, default="missing", index=True)
    merged_into_id = db.Column(db.Integer, db.ForeignKey("missing_person.id"), nullable=True)

    found_note = db.Column(db.Text, nullable=True)       # notes when marked found safe
    identified_note = db.Column(db.Text, nullable=True)  # notes when marked identified

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    dna_references = db.relationship(
        "DnaReference", backref="missing_person", lazy=True,
        cascade="all, delete-orphan"
    )

    def full_address(self):
        """Where the person was last seen - shown in listings/search."""
        parts = [p for p in [
            self.last_seen_landmark,
            self.last_seen_ward_no and f"Ward {self.last_seen_ward_no}",
            self.last_seen_municipality,
            self.last_seen_district,
        ] if p]
        return ", ".join(parts)

    def home_address(self):
        """The person's home address, separate from where they went missing."""
        parts = [p for p in [
            self.home_ward_no and f"Ward {self.home_ward_no}",
            self.home_municipality,
            self.home_district,
        ] if p]
        return ", ".join(parts)

    def has_dna_reference(self):
        return len(self.dna_references) > 0

    def to_dict(self):
        return {
            "id": self.id,
            "full_name": self.full_name,
            "age": self.age,
            "gender": self.gender,
            "last_seen_district": self.last_seen_district,
            "last_seen_municipality": self.last_seen_municipality,
            "last_seen_ward_no": self.last_seen_ward_no,
            "last_seen_landmark": self.last_seen_landmark,
            "home_district": self.home_district,
            "home_municipality": self.home_municipality,
            "home_ward_no": self.home_ward_no,
            "address": self.full_address(),
            "home_address": self.home_address(),
            "description": self.description,
            "photo_filename": self.photo_filename,
            "reporter_name": self.reporter_name,
            "reporter_relation": self.reporter_relation,
            "reporter_phone": self.reporter_phone,
            "status": self.status,
            "has_dna_reference": self.has_dna_reference(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class DnaReference(db.Model):
    """
    A reference DNA sample/report from a RELATIVE of the missing person
    (the missing person themselves can't be sampled - they're missing).

    This stores lab-issued reference metadata and an uploaded copy of the
    lab report. Actual kinship comparison against a recovered body's own
    lab report is done by the forensic lab/government team using their own
    certified software - this site only stores and surfaces the reference
    so the right report reaches the right team.
    """
    __tablename__ = "dna_reference"

    id = db.Column(db.Integer, primary_key=True)
    missing_person_id = db.Column(db.Integer, db.ForeignKey("missing_person.id"), nullable=False)

    sample_giver_name = db.Column(db.String(150), nullable=False)
    # Relationship to the missing person - matters a lot for match strength:
    # parent/child > full sibling > more distant relatives
    relationship_to_missing = db.Column(db.String(50), nullable=False)

    lab_name = db.Column(db.String(200), nullable=True)
    report_reference_no = db.Column(db.String(100), nullable=True)
    test_date = db.Column(db.String(50), nullable=True)  # free text, e.g. "2026-08-15"

    report_filename = db.Column(db.String(300), nullable=True)  # uploaded lab report file

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "missing_person_id": self.missing_person_id,
            "sample_giver_name": self.sample_giver_name,
            "relationship_to_missing": self.relationship_to_missing,
            "lab_name": self.lab_name,
            "report_reference_no": self.report_reference_no,
            "test_date": self.test_date,
            "report_filename": self.report_filename,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
