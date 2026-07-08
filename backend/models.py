from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin


db = SQLAlchemy()


class User(db.Model, UserMixin):
   
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

   
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=True)

   
    role = db.Column(db.String(20), nullable=False, default="user")

   
    is_blacklisted = db.Column(db.Boolean, default=False, nullable=False)

   
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

   
    staff_profile = db.relationship(
        "StaffProfile",
        backref="user",
        uselist=False,          # one-to-one relationship
        cascade="all, delete-orphan"
    )

    
    bookings = db.relationship(
        "Booking",
        backref="user",
        cascade="all, delete-orphan"
    )

    @property
    def display_id(self):
        return f"U{self.id:03d}"

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"


class StaffProfile(db.Model):
    __tablename__ = "staff_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    
    status = db.Column(db.String(20), default="pending")

    # ---- Relationship ----
    # One staff member can be assigned to MANY treks
    assigned_treks = db.relationship("Trek", backref="staff", lazy=True)

    @property
    def display_id(self):
        return f"S{self.id:03d}"

    def __repr__(self):
        return f"<StaffProfile for user_id={self.user_id}>"


class Trek(db.Model):
  
    __tablename__ = "treks"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    location = db.Column(db.String(120), nullable=False)

 
    difficulty = db.Column(db.String(20), nullable=False)

    duration_days = db.Column(db.Integer, nullable=False)

   
    total_slots = db.Column(db.Integer, nullable=False)
    available_slots = db.Column(db.Integer, nullable=False)

   
    staff_id = db.Column(db.Integer, db.ForeignKey("staff_profiles.id"), nullable=True)

  
    status = db.Column(db.String(20), nullable=False, default="Pending")

    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)

    description = db.Column(db.Text, nullable=True)
    image_filename = db.Column(db.String(200), nullable=True)  # optional photo

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    
    bookings = db.relationship(
        "Booking",
        backref="trek",
        cascade="all, delete-orphan"
    )

    @property
    def display_id(self):
        return f"T{self.id:03d}"

    def __repr__(self):
        return f"<Trek {self.name} ({self.status})>"


class Booking(db.Model):
  
    __tablename__ = "bookings"

   
    __table_args__ = (
        db.UniqueConstraint("user_id", "trek_id", name="uq_user_trek"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    trek_id = db.Column(db.Integer, db.ForeignKey("treks.id"), nullable=False)

    booking_date = db.Column(db.DateTime, default=datetime.utcnow)

  
    status = db.Column(db.String(20), nullable=False, default="Booked")

    @property
    def display_id(self):
        return f"B{self.id:03d}"

    def __repr__(self):
        return f"<Booking user_id={self.user_id} trek_id={self.trek_id} ({self.status})>"
