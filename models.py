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

    # Last seen address (ward/municipality level - district alone is too broad)
    district = db.Column(db.String(100), nullable=True, index=True)
    municipality = db.Column(db.String(150), nullable=True)
    ward_no = db.Column(db.String(20), nullable=True)
    landmark = db.Column(db.String(200), nullable=True)  # tole / nearest known point

    description = db.Column(db.Text, nullable=True)  # clothing, marks, etc.
    photo_filename = db.Column(db.String(300), nullable=True)

    # Reporter (person submitting this report)
    reporter_name = db.Column(db.String(150), nullable=True)
    reporter_relation = db.Column(db.String(100), nullable=True)
    reporter_phone = db.Column(db.String(30), nullable=True)

    # Status: missing, found_safe, rejected, merged
    status = db.Column(db.String(20), nullable=False, default="missing", index=True)
    merged_into_id = db.Column(db.Integer, db.ForeignKey("missing_person.id"), nullable=True)

    found_note = db.Column(db.Text, nullable=True)  # notes when marked found safe

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def full_address(self):
        parts = [p for p in [self.landmark, self.ward_no and f"Ward {self.ward_no}",
                              self.municipality, self.district] if p]
        return ", ".join(parts)

    def to_dict(self):
        return {
            "id": self.id,
            "full_name": self.full_name,
            "age": self.age,
            "gender": self.gender,
            "district": self.district,
            "municipality": self.municipality,
            "ward_no": self.ward_no,
            "landmark": self.landmark,
            "address": self.full_address(),
            "description": self.description,
            "photo_filename": self.photo_filename,
            "reporter_name": self.reporter_name,
            "reporter_relation": self.reporter_relation,
            "reporter_phone": self.reporter_phone,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
