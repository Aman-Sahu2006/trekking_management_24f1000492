from functools import wraps
from datetime import datetime

from flask import (
    Blueprint, render_template, redirect, url_for,
    request, flash, abort
)
from flask_login import (
    login_user, logout_user, login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os

from backend.models import (
    db, User, StaffProfile, Trek, Booking, BMICalculation,
    UserProfile, StaffDetails,
)


def role_required(*allowed_roles):
    def decorator(view_function):
        @wraps(view_function)
        def wrapped_view(*args, **kwargs):
            if current_user.role not in allowed_roles:
                abort(403)
            return view_function(*args, **kwargs)
        return wrapped_view
    return decorator


# ============================================================
# AUTH ROUTES START (login, register, logout)
# ============================================================
auth_bp = Blueprint("auth", __name__, template_folder="../templates/auth")


# home
@auth_bp.route("/")
def home():
    return render_template("auth/home.html")


# login
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        role = request.form.get("role")
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username, role=role).first()

        if user is None or not check_password_hash(user.password_hash, password):
            flash("Invalid username, password, or role selected.", "danger")
            return redirect(url_for("auth.login"))

        if user.is_blacklisted:
            flash("Your account has been blacklisted. Contact admin.", "danger")
            return redirect(url_for("auth.login"))


        if user.role == "staff":
            if user.staff_profile is None or user.staff_profile.status == "pending":
                flash("Your staff account is awaiting admin approval. Please check back later.", "warning")
                return redirect(url_for("auth.login"))
            if user.staff_profile.status == "rejected":
                flash("Your staff registration request was rejected by the admin.", "danger")
                return redirect(url_for("auth.login"))

        login_user(user)
        flash(f"Welcome back, {user.full_name}!", "success")


        if user.role == "admin":
            return redirect(url_for("admin.dashboard"))
        elif user.role == "staff":
            return redirect(url_for("staff.dashboard"))
        else:
            return redirect(url_for("user.dashboard"))


    return render_template("auth/login.html")


# register
@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not full_name or not username or not email or not password:
            flash("Please fill in all required fields.", "danger")
            return redirect(url_for("auth.register"))

        if password != confirm_password:
            flash("Password and Confirm Password do not match.", "danger")
            return redirect(url_for("auth.register"))

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash("That username is already taken. Please choose another.", "danger")
            return redirect(url_for("auth.register"))

        existing_email = User.query.filter_by(email=email).first()
        if existing_email:
            flash("That email is already registered.", "danger")
            return redirect(url_for("auth.register"))

        new_user = User(
            full_name=full_name,
            username=username,
            email=email,
            phone=phone,
            password_hash=generate_password_hash(password),
            role="user",
        )
        db.session.add(new_user)
        db.session.commit()

        flash("Registration successful! You can now log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html")


# register staff
@auth_bp.route("/register-staff", methods=["GET", "POST"])
def register_staff():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not full_name or not username or not email or not password:
            flash("Please fill in all required fields.", "danger")
            return redirect(url_for("auth.register_staff"))

        if password != confirm_password:
            flash("Password and Confirm Password do not match.", "danger")
            return redirect(url_for("auth.register_staff"))

        if User.query.filter_by(username=username).first():
            flash("That username is already taken. Please choose another.", "danger")
            return redirect(url_for("auth.register_staff"))

        if User.query.filter_by(email=email).first():
            flash("That email is already registered.", "danger")
            return redirect(url_for("auth.register_staff"))

        new_staff_user = User(
            full_name=full_name,
            username=username,
            email=email,
            phone=phone,
            password_hash=generate_password_hash(password),
            role="staff",
        )
        db.session.add(new_staff_user)
        db.session.flush()

        new_staff_profile = StaffProfile(user_id=new_staff_user.id, status="pending")
        db.session.add(new_staff_profile)
        db.session.commit()

        flash("Your staff registration request has been submitted. Please wait for admin approval before logging in.", "info")
        return redirect(url_for("auth.login"))

    return render_template("auth/register_staff.html")


# logout
@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.home"))


# ============================================================
# ADMIN ROUTES START (dashboard, treks, staff, users, bookings)
# ============================================================
admin_bp = Blueprint("admin", __name__, template_folder="../templates/admin")


# admin dashboard
@admin_bp.route("/dashboard")
@login_required
@role_required("admin")
def dashboard():
    total_treks = Trek.query.count()
    total_users = User.query.filter_by(role="user").count()

    all_staff_users = User.query.filter_by(role="staff").all()
    total_staff = sum(1 for s in all_staff_users if s.staff_profile and s.staff_profile.status == "active")
    pending_staff_count = sum(1 for s in all_staff_users if s.staff_profile and s.staff_profile.status == "pending")

    total_bookings = Booking.query.count()


    recent_bookings = Booking.query.order_by(Booking.booking_date.desc()).limit(5).all()

    return render_template(
        "admin/dashboard.html",
        total_treks=total_treks,
        total_users=total_users,
        total_staff=total_staff,
        total_bookings=total_bookings,
        pending_staff_count=pending_staff_count,
        recent_bookings=recent_bookings,
    )


# admin treks list
@admin_bp.route("/treks")
@login_required
@role_required("admin")
def treks():
    all_treks = Trek.query.order_by(Trek.created_at.desc()).all()
    return render_template("admin/treks.html", treks=all_treks)


# add trek
@admin_bp.route("/treks/add", methods=["GET", "POST"])
@login_required
@role_required("admin")
def add_trek():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        location = request.form.get("location", "").strip()
        difficulty = request.form.get("difficulty")
        duration_days = request.form.get("duration_days", type=int)
        total_slots = request.form.get("total_slots", type=int)
        start_date_str = request.form.get("start_date")
        end_date_str = request.form.get("end_date")
        description = request.form.get("description", "").strip()
        safety_info = request.form.get("safety_info", "").strip()

        if not name or not location or not difficulty:
            flash("Please fill in all required fields.", "danger")
            return redirect(url_for("admin.add_trek"))

        if not total_slots or total_slots <= 0:
            flash("Total slots must be a positive number.", "danger")
            return redirect(url_for("admin.add_trek"))


        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()


        image_filename = None
        image_file = request.files.get("image")
        if image_file and image_file.filename:
            image_filename = secure_filename(image_file.filename)
            image_file.save(os.path.join("static", "upload", image_filename))

        new_trek = Trek(
            name=name,
            location=location,
            difficulty=difficulty,
            duration_days=duration_days,
            total_slots=total_slots,
            available_slots=total_slots,
            start_date=start_date,
            end_date=end_date,
            description=description,
            safety_info=safety_info,
            image_filename=image_filename,
            status="Pending",
        )
        db.session.add(new_trek)
        db.session.commit()

        flash(f'Trek "{name}" created successfully.', "success")
        return redirect(url_for("admin.treks"))

    return render_template("admin/edit_trek.html", trek=None)


# edit trek
@admin_bp.route("/treks/<int:trek_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("admin")
def edit_trek(trek_id):
    trek = Trek.query.get_or_404(trek_id)

    if request.method == "POST":
        trek.name = request.form.get("name", "").strip()
        trek.location = request.form.get("location", "").strip()
        trek.difficulty = request.form.get("difficulty")
        trek.duration_days = request.form.get("duration_days", type=int)

        new_total_slots = request.form.get("total_slots", type=int)

        slot_difference = new_total_slots - trek.total_slots
        trek.total_slots = new_total_slots
        trek.available_slots = max(0, trek.available_slots + slot_difference)

        trek.start_date = datetime.strptime(request.form.get("start_date"), "%Y-%m-%d").date()
        trek.end_date = datetime.strptime(request.form.get("end_date"), "%Y-%m-%d").date()
        trek.description = request.form.get("description", "").strip()
        trek.safety_info = request.form.get("safety_info", "").strip()

        image_file = request.files.get("image")
        if image_file and image_file.filename:
            image_filename = secure_filename(image_file.filename)
            image_file.save(os.path.join("static", "upload", image_filename))
            trek.image_filename = image_filename

        db.session.commit()
        flash("Trek updated successfully.", "success")
        return redirect(url_for("admin.treks"))

    return render_template("admin/edit_trek.html", trek=trek)


# delete trek
@admin_bp.route("/treks/<int:trek_id>/delete", methods=["POST"])
@login_required
@role_required("admin")
def delete_trek(trek_id):
    trek = Trek.query.get_or_404(trek_id)
    db.session.delete(trek)
    db.session.commit()
    flash("Trek deleted.", "info")
    return redirect(url_for("admin.treks"))


# admin trek details
@admin_bp.route("/treks/<int:trek_id>")
@login_required
@role_required("admin")
def trek_details(trek_id):
    trek = Trek.query.get_or_404(trek_id)
    all_staff = [
        s for s in User.query.filter_by(role="staff").all()
        if s.staff_profile and s.staff_profile.status == "active" and not s.is_blacklisted
    ]
    return render_template("admin/trek_details.html", trek=trek, all_staff=all_staff)


# assign staff
@admin_bp.route("/treks/<int:trek_id>/assign-staff", methods=["POST"])
@login_required
@role_required("admin")
def assign_staff(trek_id):
    trek = Trek.query.get_or_404(trek_id)
    staff_profile_id = request.form.get("staff_profile_id", type=int)

    staff_profile = StaffProfile.query.get(staff_profile_id)
    if staff_profile is None or staff_profile.status != "active":
        flash("You can only assign staff members who have been approved.", "danger")
        return redirect(url_for("admin.trek_details", trek_id=trek.id))

    if staff_profile.user and staff_profile.user.is_blacklisted:
        flash("You cannot assign a blacklisted staff member.", "danger")
        return redirect(url_for("admin.trek_details", trek_id=trek.id))

    trek.staff_id = staff_profile_id

    if trek.status == "Pending":
        trek.status = "Approved"

    db.session.commit()
    flash("Staff assigned to trek.", "success")
    return redirect(url_for("admin.trek_details", trek_id=trek.id))


# staff list
@admin_bp.route("/staff")
@login_required
@role_required("admin")
def staff_list():
    all_staff = User.query.filter_by(role="staff").all()

    pending_staff = [s for s in all_staff if s.staff_profile and s.staff_profile.status == "pending"]
    active_staff = [s for s in all_staff if s.staff_profile and s.staff_profile.status == "active"]
    rejected_staff = [s for s in all_staff if s.staff_profile and s.staff_profile.status == "rejected"]

    return render_template(
        "admin/staff.html",
        pending_staff=pending_staff,
        active_staff=active_staff,
        rejected_staff=rejected_staff,
    )


# approve staff
@admin_bp.route("/staff/<int:user_id>/approve", methods=["POST"])
@login_required
@role_required("admin")
def approve_staff(user_id):
    staff_user = User.query.filter_by(id=user_id, role="staff").first_or_404()

    if staff_user.staff_profile is None:
        staff_user.staff_profile = StaffProfile(user_id=staff_user.id)

    staff_user.staff_profile.status = "active"
    db.session.commit()

    flash(f"{staff_user.full_name} has been approved and can now log in.", "success")
    return redirect(url_for("admin.staff_list"))


# reject staff
@admin_bp.route("/staff/<int:user_id>/reject", methods=["POST"])
@login_required
@role_required("admin")
def reject_staff(user_id):
    staff_user = User.query.filter_by(id=user_id, role="staff").first_or_404()

    if staff_user.staff_profile is None:
        staff_user.staff_profile = StaffProfile(user_id=staff_user.id)

    staff_user.staff_profile.status = "rejected"
    db.session.commit()

    flash(f"{staff_user.full_name}'s staff request has been rejected.", "info")
    return redirect(url_for("admin.staff_list"))


# edit staff
@admin_bp.route("/staff/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("admin")
def edit_staff(user_id):
    staff_user = User.query.filter_by(id=user_id, role="staff").first_or_404()

    if request.method == "POST":
        new_username = request.form.get("username", "").strip()

        if not new_username:
            flash("Username cannot be empty.", "danger")
            return redirect(url_for("admin.edit_staff", user_id=staff_user.id))

        existing = User.query.filter(
            User.username == new_username, User.id != staff_user.id
        ).first()
        if existing:
            flash("That username is already taken. Please choose another.", "danger")
            return redirect(url_for("admin.edit_staff", user_id=staff_user.id))

        staff_user.username = new_username
        staff_user.full_name = request.form.get("full_name", "").strip()
        staff_user.email = request.form.get("email", "").strip()
        staff_user.phone = request.form.get("phone", "").strip()

        db.session.commit()
        flash("Staff details updated.", "success")
        return redirect(url_for("admin.staff_list"))

    return render_template("admin/edit_staff.html", staff=staff_user)


# remove staff
@admin_bp.route("/staff/<int:user_id>/remove", methods=["POST"])
@login_required
@role_required("admin")
def remove_staff(user_id):
    staff_user = User.query.filter_by(id=user_id, role="staff").first_or_404()
    db.session.delete(staff_user)
    db.session.commit()
    flash("Staff member removed.", "info")
    return redirect(url_for("admin.staff_list"))


# staff detail
@admin_bp.route("/staff/<int:user_id>")
@login_required
@role_required("admin")
def staff_detail(user_id):
    staff_user = User.query.filter_by(id=user_id, role="staff").first_or_404()
    return render_template("admin/staff_detail.html", staff=staff_user)


def _assign_scoped_user_ids(users):
    """Give each plain 'user' role User a display id scoped to just that
    role (U001, U002, ...), rather than their raw shared-table id. The
    users table also holds admins and staff, so raw ids don't start at 1
    for the first real trekker."""
    ordered = User.query.filter_by(role="user").order_by(User.id).all()
    rank_by_id = {u.id: i for i, u in enumerate(ordered, start=1)}
    for u in users:
        u.scoped_display_id = f"U{rank_by_id.get(u.id, 0):03d}"
    return users


# users list
@admin_bp.route("/users")
@login_required
@role_required("admin")
def users_list():
    all_users = User.query.filter_by(role="user").order_by(User.id).all()
    _assign_scoped_user_ids(all_users)
    return render_template("admin/users.html", users=all_users)


# user detail
@admin_bp.route("/users/<int:user_id>")
@login_required
@role_required("admin")
def user_detail(user_id):
    target_user = User.query.filter_by(id=user_id, role="user").first_or_404()
    _assign_scoped_user_ids([target_user])
    return render_template("admin/user_detail.html", user=target_user)


# edit user
@admin_bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("admin")
def edit_user(user_id):
    target_user = User.query.filter_by(id=user_id, role="user").first_or_404()

    if request.method == "POST":
        new_username = request.form.get("username", "").strip()

        if not new_username:
            flash("Username cannot be empty.", "danger")
            return redirect(url_for("admin.edit_user", user_id=target_user.id))

        existing = User.query.filter(
            User.username == new_username, User.id != target_user.id
        ).first()
        if existing:
            flash("That username is already taken. Please choose another.", "danger")
            return redirect(url_for("admin.edit_user", user_id=target_user.id))

        target_user.username = new_username
        target_user.full_name = request.form.get("full_name", "").strip()
        target_user.email = request.form.get("email", "").strip()
        target_user.phone = request.form.get("phone", "").strip()

        db.session.commit()
        flash("User details updated.", "success")
        return redirect(url_for("admin.users_list"))

    return render_template("admin/edit_user.html", user=target_user)


# toggle blacklist
@admin_bp.route("/blacklist/<int:user_id>", methods=["POST"])
@login_required
@role_required("admin")
def toggle_blacklist(user_id):
    target_user = User.query.get_or_404(user_id)
    target_user.is_blacklisted = not target_user.is_blacklisted
    db.session.commit()

    if target_user.is_blacklisted:
        flash(f"{target_user.full_name} has been blacklisted.", "warning")
    else:
        flash(f"{target_user.full_name} has been un-blacklisted.", "success")


    if target_user.role == "staff":
        return redirect(url_for("admin.staff_detail", user_id=target_user.id))
    return redirect(url_for("admin.user_detail", user_id=target_user.id))


# ------------------------------------------------------------
# BOOKING (ADMIN VIEW) ROUTES START (list + detail, admin-side)
# ------------------------------------------------------------
# bookings list
@admin_bp.route("/bookings")
@login_required
@role_required("admin")
def bookings_list():
    status_filter = request.args.get("status", "").strip()

    query = Booking.query.order_by(Booking.booking_date.desc())
    if status_filter:
        query = query.filter(Booking.status == status_filter)

    all_bookings = query.all()

    return render_template(
        "admin/bookings.html",
        bookings=all_bookings,
        status_filter=status_filter,
    )


# booking detail
@admin_bp.route("/bookings/<int:booking_id>")
@login_required
@role_required("admin")
def booking_detail(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    return render_template("admin/booking_detail.html", booking=booking)


def _match_display_id(query_text, prefix):
    """Parse a query like 'S007', 's7' or a bare '7' into the numeric id
    it refers to. Returns None if query_text doesn't look like an id
    reference for the given prefix at all."""
    text = query_text.strip().upper()
    if text.startswith(prefix):
        text = text[len(prefix):]
    if text.isdigit():
        return int(text)
    return None


# ------------------------------------------------------------
# SEARCH ROUTES START (admin search across treks/staff/users)
# ------------------------------------------------------------
# admin search
@admin_bp.route("/search")
@login_required
@role_required("admin")
def search():
    query_text = request.args.get("q", "").strip()
    search_type = request.args.get("type", "trek")

    results = []
    if query_text:
        if search_type == "trek":
            trek_id = _match_display_id(query_text, "T")
            name_filter = Trek.name.ilike(f"%{query_text}%")
            id_filter = (Trek.id == trek_id) if trek_id is not None else False
            results = Trek.query.filter(name_filter | id_filter).all()

        elif search_type == "staff":
            # A staff member's displayed id (S001, S002, ...) is based on
            # their StaffProfile.id, not their shared User.id, so the
            # search has to join through StaffProfile rather than
            # matching User.id directly.
            staff_id = _match_display_id(query_text, "S")
            name_filter = User.full_name.ilike(f"%{query_text}%")
            id_filter = (StaffProfile.id == staff_id) if staff_id is not None else False
            results = (
                User.query
                .join(StaffProfile, User.staff_profile)
                .filter(User.role == "staff")
                .filter(name_filter | id_filter)
                .all()
            )

        elif search_type == "user":
            ordered_users = User.query.filter_by(role="user").order_by(User.id).all()
            _assign_scoped_user_ids(ordered_users)

            scoped_id = _match_display_id(query_text, "U")
            name_needle = query_text.lower()
            results = [
                u for i, u in enumerate(ordered_users, start=1)
                if name_needle in u.full_name.lower() or (scoped_id is not None and scoped_id == i)
            ]

    return render_template(
        "admin/search.html",
        results=results,
        query_text=query_text,
        search_type=search_type,
    )


# ------------------------------------------------------------
# ANALYTICS ROUTES START (dashboard charts / stats for admin)
# ------------------------------------------------------------
# analytics
@admin_bp.route("/analytics")
@login_required
@role_required("admin")
def analytics():
    treks_with_counts = (
        db.session.query(Trek, db.func.count(Booking.id).label("booking_count"))
        .outerjoin(Booking, Booking.trek_id == Trek.id)
        .group_by(Trek.id)
        .order_by(db.func.count(Booking.id).desc())
        .all()
    )

    booked_count = Booking.query.filter_by(status="Booked").count()
    cancelled_count = Booking.query.filter_by(status="Cancelled").count()
    completed_count = Booking.query.filter_by(status="Completed").count()

    # Bookings grouped by calendar month (YYYY-MM), most recent 6 months,
    # shown oldest -> newest so the bar chart reads left to right in time order.
    month_key = db.func.strftime("%Y-%m", Booking.booking_date)
    monthly_rows = (
        db.session.query(month_key.label("month_key"), db.func.count(Booking.id).label("count"))
        .group_by("month_key")
        .order_by(db.desc("month_key"))
        .limit(6)
        .all()
    )
    monthly_rows = list(reversed(monthly_rows))
    monthly_bookings = [
        {"label": datetime.strptime(row.month_key, "%Y-%m").strftime("%b %Y"), "count": row.count}
        for row in monthly_rows
    ]

    return render_template(
        "admin/analytics.html",
        treks_with_counts=treks_with_counts,
        booked_count=booked_count,
        cancelled_count=cancelled_count,
        completed_count=completed_count,
        monthly_bookings=monthly_bookings,
    )


# ============================================================
# STAFF ROUTES START (dashboard, assigned treks, trek management)
# ============================================================
staff_bp = Blueprint("staff", __name__, template_folder="../templates/staff")


def get_current_staff_profile():
    return StaffProfile.query.filter_by(user_id=current_user.id).first()


# staff dashboard
@staff_bp.route("/dashboard")
@login_required
@role_required("staff")
def dashboard():
    staff_profile = get_current_staff_profile()
    assigned_treks = staff_profile.assigned_treks if staff_profile else []


    booking_counts = {}
    for trek in assigned_treks:
        booking_counts[trek.id] = Booking.query.filter_by(
            trek_id=trek.id, status="Booked"
        ).count()

    return render_template(
        "staff/dashboard.html",
        assigned_treks=assigned_treks,
        booking_counts=booking_counts,
    )


# assigned treks
@staff_bp.route("/assigned-treks")
@login_required
@role_required("staff")
def assigned_treks():
    staff_profile = get_current_staff_profile()
    treks_list = staff_profile.assigned_treks if staff_profile else []
    return render_template("staff/assigned_treks.html", treks=treks_list)


def verify_staff_owns_trek(trek):
    staff_profile = get_current_staff_profile()
    if staff_profile is None or trek.staff_id != staff_profile.id:
        abort(403)


# staff trek details
@staff_bp.route("/treks/<int:trek_id>")
@login_required
@role_required("staff")
def trek_details(trek_id):
    trek = Trek.query.get_or_404(trek_id)
    verify_staff_owns_trek(trek)
    return render_template("staff/trek_details.html", trek=trek)


# trek management
@staff_bp.route("/treks/<int:trek_id>/manage", methods=["GET", "POST"])
@login_required
@role_required("staff")
def trek_management(trek_id):
    trek = Trek.query.get_or_404(trek_id)
    verify_staff_owns_trek(trek)

    if request.method == "POST":
        new_status = request.form.get("status")
        new_available_slots = request.form.get("available_slots", type=int)


        allowed_statuses = ["Approved", "Open", "Closed", "Started", "Completed"]
        if new_status in allowed_statuses:
            trek.status = new_status


        if new_available_slots is not None:
            trek.available_slots = max(0, min(new_available_slots, trek.total_slots))

        db.session.commit()
        flash("Trek details updated.", "success")
        return redirect(url_for("staff.trek_management", trek_id=trek.id))

    return render_template("staff/trek_management.html", trek=trek)


# participants
@staff_bp.route("/treks/<int:trek_id>/participants")
@login_required
@role_required("staff")
def participants(trek_id):
    trek = Trek.query.get_or_404(trek_id)
    verify_staff_owns_trek(trek)

    trek_bookings = Booking.query.filter_by(trek_id=trek.id).all()
    return render_template("staff/participants.html", trek=trek, bookings=trek_bookings)


# staff edit profile
@staff_bp.route("/profile/edit", methods=["GET", "POST"])
@login_required
@role_required("staff")
def edit_profile():
    if request.method == "POST":
        new_username = request.form.get("username", "").strip()

        if not new_username:
            flash("Username cannot be empty.", "danger")
            return redirect(url_for("staff.edit_profile"))

        existing = User.query.filter(
            User.username == new_username, User.id != current_user.id
        ).first()
        if existing:
            flash("That username is already taken. Please choose another.", "danger")
            return redirect(url_for("staff.edit_profile"))

        current_user.username = new_username
        current_user.full_name = request.form.get("full_name", "").strip()
        current_user.email = request.form.get("email", "").strip()
        current_user.phone = request.form.get("phone", "").strip()

        if current_user.staff_profile is not None:
            details = current_user.staff_profile.details
            if details is None:
                details = StaffDetails(staff_id=current_user.staff_profile.id)
                db.session.add(details)

            details.experience_years = request.form.get("experience_years", type=int)

        db.session.commit()
        flash("Profile updated successfully.", "success")
        return redirect(url_for("staff.dashboard"))

    return render_template("staff/edit_profile.html", staff=current_user)


# ============================================================
# USER ROUTES START (dashboard, browsing treks, bookings, history)
# ============================================================
user_bp = Blueprint("user", __name__, template_folder="../templates/user")


# user dashboard
@user_bp.route("/dashboard")
@login_required
@role_required("user")
def dashboard():
    open_treks = Trek.query.filter_by(status="Open").all()
    my_bookings = Booking.query.filter_by(user_id=current_user.id, status="Booked").all()

    return render_template(
        "user/dashboard.html",
        open_treks=open_treks,
        my_bookings=my_bookings,
    )


# available treks
@user_bp.route("/treks")
@login_required
@role_required("user")
def available_treks():
    difficulty_filter = request.args.get("difficulty", "")
    location_filter = request.args.get("location", "").strip()
    search_text = request.args.get("q", "").strip()

    query = Trek.query.filter_by(status="Open")

    if difficulty_filter:
        query = query.filter(Trek.difficulty == difficulty_filter)

    if location_filter:
        query = query.filter(Trek.location.ilike(f"%{location_filter}%"))

    if search_text:
        query = query.filter(Trek.name.ilike(f"%{search_text}%"))

    treks_list = query.all()

    return render_template(
        "user/available_treks.html",
        treks=treks_list,
        difficulty_filter=difficulty_filter,
        location_filter=location_filter,
        search_text=search_text,
    )


# user trek details
@user_bp.route("/treks/<int:trek_id>")
@login_required
@role_required("user")
def trek_details(trek_id):
    trek = Trek.query.get_or_404(trek_id)
    existing_booking = Booking.query.filter_by(
        user_id=current_user.id, trek_id=trek.id, status="Booked"
    ).first()

    bmi_weight = request.args.get("weight", type=float)
    bmi_height = request.args.get("height", type=float)

    bmi_value = None
    bmi_category = None

    # --------------------------------------------------------
    # BMI ROUTES/LOGIC START (calculate + log BMI on trek page)
    # --------------------------------------------------------
    if bmi_weight and bmi_height and bmi_weight > 0 and bmi_height > 0:
        height_m = bmi_height / 100
        bmi_value = round(bmi_weight / (height_m * height_m), 1)

        if bmi_value < 16.5:
            bmi_category = "Severely Underweight"
        elif bmi_value < 18.5:
            bmi_category = "Underweight"
        elif bmi_value < 25:
            bmi_category = "Normal"
        elif bmi_value < 30:
            bmi_category = "Overweight"
        else:
            bmi_category = "Obese"

        db.session.add(BMICalculation(
            user_id=current_user.id,
            height_cm=bmi_height,
            weight_kg=bmi_weight,
            bmi_value=bmi_value,
        ))
        db.session.commit()

    recent_bmi_checks = (
        BMICalculation.query
        .filter_by(user_id=current_user.id)
        .order_by(BMICalculation.calculated_at.desc())
        .limit(5)
        .all()
    )

    return render_template(
        "user/trek_details.html",
        trek=trek,
        existing_booking=existing_booking,
        bmi_weight=bmi_weight,
        bmi_height=bmi_height,
        bmi_value=bmi_value,
        bmi_category=bmi_category,
        recent_bmi_checks=recent_bmi_checks,
    )


# book trek
@user_bp.route("/treks/<int:trek_id>/book", methods=["GET", "POST"])
@login_required
@role_required("user")
def book_trek(trek_id):
    trek = Trek.query.get_or_404(trek_id)

    if request.method == "POST":

        if trek.status != "Open":
            flash("This trek is not open for booking.", "danger")
            return redirect(url_for("user.trek_details", trek_id=trek.id))


        if trek.available_slots <= 0:
            flash("Sorry, this trek is fully booked. No slots available.", "danger")
            return redirect(url_for("user.trek_details", trek_id=trek.id))


        already_booked = Booking.query.filter_by(
            user_id=current_user.id, trek_id=trek.id, status="Booked"
        ).first()
        if already_booked:
            flash("You have already booked this trek.", "warning")
            return redirect(url_for("user.trek_details", trek_id=trek.id))


        new_booking = Booking(
            user_id=current_user.id,
            trek_id=trek.id,
            status="Booked",
        )
        trek.available_slots -= 1

        db.session.add(new_booking)
        db.session.commit()

        flash(f'Trek "{trek.name}" booked successfully!', "success")
        return redirect(url_for("user.booking_details", booking_id=new_booking.id))

    return render_template("user/book_trek.html", trek=trek)


# booking details
@user_bp.route("/bookings/<int:booking_id>")
@login_required
@role_required("user")
def booking_details(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    if booking.user_id != current_user.id:
        abort(403)

    return render_template("user/booking_details.html", booking=booking)


# cancel booking
@user_bp.route("/bookings/<int:booking_id>/cancel", methods=["POST"])
@login_required
@role_required("user")
def cancel_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    if booking.user_id != current_user.id:
        abort(403)

    if booking.status == "Booked":
        booking.status = "Cancelled"
        booking.trek.available_slots += 1
        db.session.commit()
        flash("Booking cancelled.", "info")

    return redirect(url_for("user.trek_history"))


# trek history
@user_bp.route("/history")
@login_required
@role_required("user")
def trek_history():
    all_bookings = Booking.query.filter_by(user_id=current_user.id).order_by(
        Booking.booking_date.desc()
    ).all()
    return render_template("user/trek_history.html", bookings=all_bookings)


# history details
@user_bp.route("/history/<int:booking_id>")
@login_required
@role_required("user")
def history_details(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    if booking.user_id != current_user.id:
        abort(403)

    return render_template("user/history_details.html", booking=booking)


# user edit profile
@user_bp.route("/profile/edit", methods=["GET", "POST"])
@login_required
@role_required("user")
def edit_profile():
    if request.method == "POST":
        new_username = request.form.get("username", "").strip()

        if not new_username:
            flash("Username cannot be empty.", "danger")
            return redirect(url_for("user.edit_profile"))

        existing = User.query.filter(
            User.username == new_username, User.id != current_user.id
        ).first()
        if existing:
            flash("That username is already taken. Please choose another.", "danger")
            return redirect(url_for("user.edit_profile"))

        current_user.username = new_username
        current_user.full_name = request.form.get("full_name", "").strip()
        current_user.email = request.form.get("email", "").strip()
        current_user.phone = request.form.get("phone", "").strip()

        profile = current_user.profile
        if profile is None:
            profile = UserProfile(user_id=current_user.id)
            db.session.add(profile)

        profile.age = request.form.get("age", type=int)
        profile.weight_kg = request.form.get("weight_kg", type=float)
        profile.height_cm = request.form.get("height_cm", type=float)

        profile.address_country = request.form.get("address_country", "").strip()
        profile.address_state = request.form.get("address_state", "").strip()
        profile.address_city = request.form.get("address_city", "").strip()

        db.session.commit()
        flash("Profile updated successfully.", "success")
        return redirect(url_for("user.dashboard"))

    return render_template("user/edit_profile.html", user=current_user)