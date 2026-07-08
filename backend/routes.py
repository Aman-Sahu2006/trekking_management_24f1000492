"""
routes.py
---------
This file contains ALL the routes (URLs) of our application, organized
into 4 "blueprints" (groups of related routes):

    auth_bp  -> login, register, logout, home page          (no /prefix)
    admin_bp -> everything the Admin can do                  (/admin/...)
    staff_bp -> everything Trek Staff can do                 (/staff/...)
    user_bp  -> everything a Trekker (normal user) can do    (/user/...)

We use Flask-Login's @login_required decorator to make sure only logged-in
people can visit certain pages, and a custom @role_required decorator
(defined below) to make sure people can only visit pages meant for
their OWN role (e.g. a normal user cannot open Admin pages).
"""

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

from backend.models import db, User, StaffProfile, Trek, Booking


# =========================================================================
#  HELPER: role_required decorator
# =========================================================================
def role_required(*allowed_roles):
    """
    This is a custom decorator (a function that wraps another function)
    that checks if the logged-in user's role is allowed to see this page.

    Usage example:
        @role_required("admin")
        def some_admin_only_page():
            ...

    If the user's role is not in allowed_roles, we show a 403 Forbidden
    error page instead of letting them in.
    """
    def decorator(view_function):
        @wraps(view_function)
        def wrapped_view(*args, **kwargs):
            if current_user.role not in allowed_roles:
                abort(403)  # 403 = "Forbidden" HTTP error
            return view_function(*args, **kwargs)
        return wrapped_view
    return decorator


# =========================================================================
#  BLUEPRINT 1: AUTH (login / register / logout / home)
# =========================================================================
auth_bp = Blueprint("auth", __name__, template_folder="../templates/auth")


@auth_bp.route("/")
def home():
    """The public landing page, shown before anyone logs in."""
    return render_template("auth/home.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """
    Shows the login form (GET) and processes login attempts (POST).
    The form has a role dropdown (admin/staff/user) + username + password.
    """
    if request.method == "POST":
        role = request.form.get("role")
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        # Look for a user with this exact username AND role.
        # This means the same username cannot accidentally log in as
        # the wrong role even if it existed in another role (usernames
        # are unique across the whole table anyway, but checking role
        # too makes the intent crystal clear).
        user = User.query.filter_by(username=username, role=role).first()

        if user is None or not check_password_hash(user.password_hash, password):
            flash("Invalid username, password, or role selected.", "danger")
            return redirect(url_for("auth.login"))

        if user.is_blacklisted:
            flash("Your account has been blacklisted. Contact admin.", "danger")
            return redirect(url_for("auth.login"))

        # ---- Staff approval check ----
        # A staff account exists as soon as they self-register, but they
        # cannot log in until Admin approves their StaffProfile.
        if user.role == "staff":
            if user.staff_profile is None or user.staff_profile.status == "pending":
                flash("Your staff account is awaiting admin approval. Please check back later.", "warning")
                return redirect(url_for("auth.login"))
            if user.staff_profile.status == "rejected":
                flash("Your staff registration request was rejected by the admin.", "danger")
                return redirect(url_for("auth.login"))

        # Log the user in (Flask-Login creates the session cookie for us)
        login_user(user)
        flash(f"Welcome back, {user.full_name}!", "success")

        # Send each role to their own dashboard
        if user.role == "admin":
            return redirect(url_for("admin.dashboard"))
        elif user.role == "staff":
            return redirect(url_for("staff.dashboard"))
        else:
            return redirect(url_for("user.dashboard"))

    # GET request -> just show the login page
    return render_template("auth/login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """
    Registration page - ONLY for Trekkers (normal users).
    Admin already exists, and Staff accounts can only be created by
    Admin (see admin_bp below), so this form never has a role dropdown.
    """
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        # ---- Basic validation ----
        if not full_name or not username or not email or not password:
            flash("Please fill in all required fields.", "danger")
            return redirect(url_for("auth.register"))

        # ---- Password confirmation check ----
        # The form has two password fields; both must match before we
        # create the account, otherwise a typo could lock the user out.
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

        # ---- Create the new trekker account ----
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


@auth_bp.route("/register-staff", methods=["GET", "POST"])
def register_staff():
    """
    Registration page for Trek Staff.

    Unlike trekker registration, a staff account created here is NOT
    immediately usable - their StaffProfile is created with
    status="pending", and the login route blocks them until an Admin
    approves the request (see admin.approve_staff / admin.reject_staff).
    """
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        # ---- Basic validation ----
        if not full_name or not username or not email or not password:
            flash("Please fill in all required fields.", "danger")
            return redirect(url_for("auth.register_staff"))

        # ---- Password confirmation check ----
        if password != confirm_password:
            flash("Password and Confirm Password do not match.", "danger")
            return redirect(url_for("auth.register_staff"))

        if User.query.filter_by(username=username).first():
            flash("That username is already taken. Please choose another.", "danger")
            return redirect(url_for("auth.register_staff"))

        if User.query.filter_by(email=email).first():
            flash("That email is already registered.", "danger")
            return redirect(url_for("auth.register_staff"))

        # ---- Create the new staff account, but mark it "pending" ----
        new_staff_user = User(
            full_name=full_name,
            username=username,
            email=email,
            phone=phone,
            password_hash=generate_password_hash(password),
            role="staff",
        )
        db.session.add(new_staff_user)
        db.session.flush()  # makes new_staff_user.id available before commit

        new_staff_profile = StaffProfile(user_id=new_staff_user.id, status="pending")
        db.session.add(new_staff_profile)
        db.session.commit()

        flash("Your staff registration request has been submitted. Please wait for admin approval before logging in.", "info")
        return redirect(url_for("auth.login"))

    return render_template("auth/register_staff.html")


@auth_bp.route("/logout")
@login_required
def logout():
    """Logs the current user out and sends them back to the home page."""
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.home"))


# =========================================================================
#  BLUEPRINT 2: ADMIN
#  Every route here is prefixed with /admin (set in app.py) and protected
#  so only logged-in users with role="admin" can access it.
# =========================================================================
admin_bp = Blueprint("admin", __name__, template_folder="../templates/admin")


@admin_bp.route("/dashboard")
@login_required
@role_required("admin")
def dashboard():
    """
    Admin dashboard - shows the 3 summary numbers required by the spec:
    total treks, total users + staff, total bookings.

    "Total staff" here only counts ACTIVE (approved) staff, since
    pending/rejected accounts aren't really working staff yet. Pending
    requests are surfaced separately so the admin notices them.
    """
    total_treks = Trek.query.count()
    total_users = User.query.filter_by(role="user").count()

    all_staff_users = User.query.filter_by(role="staff").all()
    total_staff = sum(1 for s in all_staff_users if s.staff_profile and s.staff_profile.status == "active")
    pending_staff_count = sum(1 for s in all_staff_users if s.staff_profile and s.staff_profile.status == "pending")

    total_bookings = Booking.query.count()

    # ---- Recent Bookings (wireframe screen 3) ----
    # Show the 5 most recently made bookings, newest first, so the admin
    # gets a quick at-a-glance view without leaving the dashboard.
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


# ---------------------- TREK MANAGEMENT (Admin) -------------------------

@admin_bp.route("/treks")
@login_required
@role_required("admin")
def treks():
    """Shows the full list of all treks in the system."""
    all_treks = Trek.query.order_by(Trek.created_at.desc()).all()
    return render_template("admin/treks.html", treks=all_treks)


@admin_bp.route("/treks/add", methods=["GET", "POST"])
@login_required
@role_required("admin")
def add_trek():
    """Form to create a brand new trek."""
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        location = request.form.get("location", "").strip()
        difficulty = request.form.get("difficulty")
        duration_days = request.form.get("duration_days", type=int)
        total_slots = request.form.get("total_slots", type=int)
        start_date_str = request.form.get("start_date")
        end_date_str = request.form.get("end_date")
        description = request.form.get("description", "").strip()

        # ---- Basic validation ----
        if not name or not location or not difficulty:
            flash("Please fill in all required fields.", "danger")
            return redirect(url_for("admin.add_trek"))

        if not total_slots or total_slots <= 0:
            flash("Total slots must be a positive number.", "danger")
            return redirect(url_for("admin.add_trek"))

        # Convert the date strings (from an HTML date input) into real dates
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()

        # Handle an optional uploaded image
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
            available_slots=total_slots,  # all slots are free when first created
            start_date=start_date,
            end_date=end_date,
            description=description,
            image_filename=image_filename,
            status="Pending",  # new treks always start as Pending
        )
        db.session.add(new_trek)
        db.session.commit()

        flash(f'Trek "{name}" created successfully.', "success")
        return redirect(url_for("admin.treks"))

    return render_template("admin/edit_trek.html", trek=None)


@admin_bp.route("/treks/<int:trek_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("admin")
def edit_trek(trek_id):
    """Form to edit an existing trek's details."""
    trek = Trek.query.get_or_404(trek_id)

    if request.method == "POST":
        trek.name = request.form.get("name", "").strip()
        trek.location = request.form.get("location", "").strip()
        trek.difficulty = request.form.get("difficulty")
        trek.duration_days = request.form.get("duration_days", type=int)

        new_total_slots = request.form.get("total_slots", type=int)
        # If admin increases total slots, give the extra slots to available_slots too.
        # If they decrease it, reduce available_slots by the same amount (but not below 0).
        slot_difference = new_total_slots - trek.total_slots
        trek.total_slots = new_total_slots
        trek.available_slots = max(0, trek.available_slots + slot_difference)

        trek.start_date = datetime.strptime(request.form.get("start_date"), "%Y-%m-%d").date()
        trek.end_date = datetime.strptime(request.form.get("end_date"), "%Y-%m-%d").date()
        trek.description = request.form.get("description", "").strip()

        image_file = request.files.get("image")
        if image_file and image_file.filename:
            image_filename = secure_filename(image_file.filename)
            image_file.save(os.path.join("static", "upload", image_filename))
            trek.image_filename = image_filename

        db.session.commit()
        flash("Trek updated successfully.", "success")
        return redirect(url_for("admin.treks"))

    return render_template("admin/edit_trek.html", trek=trek)


@admin_bp.route("/treks/<int:trek_id>/delete", methods=["POST"])
@login_required
@role_required("admin")
def delete_trek(trek_id):
    """Deletes a trek completely (and its bookings, via cascade)."""
    trek = Trek.query.get_or_404(trek_id)
    db.session.delete(trek)
    db.session.commit()
    flash("Trek deleted.", "info")
    return redirect(url_for("admin.treks"))


@admin_bp.route("/treks/<int:trek_id>")
@login_required
@role_required("admin")
def trek_details(trek_id):
    """Read-only detailed view of one trek, including its bookings."""
    trek = Trek.query.get_or_404(trek_id)
    # All staff accounts, so the template can show an "assign staff" dropdown
    all_staff = User.query.filter_by(role="staff").all()
    return render_template("admin/trek_details.html", trek=trek, all_staff=all_staff)


@admin_bp.route("/treks/<int:trek_id>/assign-staff", methods=["POST"])
@login_required
@role_required("admin")
def assign_staff(trek_id):
    """
    Assigns a staff member to a trek. We expect a "staff_profile_id"
    field from a dropdown on the edit_trek.html page.
    """
    trek = Trek.query.get_or_404(trek_id)
    staff_profile_id = request.form.get("staff_profile_id", type=int)

    trek.staff_id = staff_profile_id
    # Once staff is assigned, move the trek from Pending to Approved
    if trek.status == "Pending":
        trek.status = "Approved"

    db.session.commit()
    flash("Staff assigned to trek.", "success")
    return redirect(url_for("admin.trek_details", trek_id=trek.id))


# ---------------------- STAFF MANAGEMENT (Admin) -------------------------

@admin_bp.route("/staff")
@login_required
@role_required("admin")
def staff_list():
    """
    Shows trek staff, split into two groups:
        - pending_staff : self-registered, waiting for admin approval
        - active_staff  : already approved, can log in and work normally
    Rejected staff are not shown in either list by default, but are
    still kept in the database (status="rejected") as a record.
    """
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


@admin_bp.route("/staff/<int:user_id>/approve", methods=["POST"])
@login_required
@role_required("admin")
def approve_staff(user_id):
    """Approves a pending staff registration request, letting them log in."""
    staff_user = User.query.filter_by(id=user_id, role="staff").first_or_404()

    if staff_user.staff_profile is None:
        # Safety net: this shouldn't normally happen, but if a staff user
        # somehow has no profile row, create one instead of crashing.
        staff_user.staff_profile = StaffProfile(user_id=staff_user.id)

    staff_user.staff_profile.status = "active"
    db.session.commit()

    flash(f"{staff_user.full_name} has been approved and can now log in.", "success")
    return redirect(url_for("admin.staff_list"))


@admin_bp.route("/staff/<int:user_id>/reject", methods=["POST"])
@login_required
@role_required("admin")
def reject_staff(user_id):
    """
    Rejects a pending staff registration request. We keep the account
    and profile in the database with status="rejected" (a record),
    rather than deleting it, as requested.
    """
    staff_user = User.query.filter_by(id=user_id, role="staff").first_or_404()

    if staff_user.staff_profile is None:
        staff_user.staff_profile = StaffProfile(user_id=staff_user.id)

    staff_user.staff_profile.status = "rejected"
    db.session.commit()

    flash(f"{staff_user.full_name}'s staff request has been rejected.", "info")
    return redirect(url_for("admin.staff_list"))


@admin_bp.route("/staff/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("admin")
def edit_staff(user_id):
    """Edit an existing staff member's basic info."""
    staff_user = User.query.filter_by(id=user_id, role="staff").first_or_404()

    if request.method == "POST":
        staff_user.full_name = request.form.get("full_name", "").strip()
        staff_user.email = request.form.get("email", "").strip()
        staff_user.phone = request.form.get("phone", "").strip()

        db.session.commit()
        flash("Staff details updated.", "success")
        return redirect(url_for("admin.staff_list"))

    return render_template("admin/edit_staff.html", staff=staff_user)


@admin_bp.route("/staff/<int:user_id>/remove", methods=["POST"])
@login_required
@role_required("admin")
def remove_staff(user_id):
    """Removes a staff member's account completely."""
    staff_user = User.query.filter_by(id=user_id, role="staff").first_or_404()
    db.session.delete(staff_user)
    db.session.commit()
    flash("Staff member removed.", "info")
    return redirect(url_for("admin.staff_list"))


@admin_bp.route("/staff/<int:user_id>")
@login_required
@role_required("admin")
def staff_detail(user_id):
    """Read-only detailed view of one staff member and their assigned treks."""
    staff_user = User.query.filter_by(id=user_id, role="staff").first_or_404()
    return render_template("admin/staff_detail.html", staff=staff_user)


# ---------------------- USER MANAGEMENT (Admin) -------------------------

@admin_bp.route("/users")
@login_required
@role_required("admin")
def users_list():
    """Shows the list of all registered trekkers."""
    all_users = User.query.filter_by(role="user").all()
    return render_template("admin/users.html", users=all_users)


@admin_bp.route("/users/<int:user_id>")
@login_required
@role_required("admin")
def user_detail(user_id):
    """Read-only detailed view of one trekker, including their booking history."""
    target_user = User.query.filter_by(id=user_id, role="user").first_or_404()
    return render_template("admin/user_detail.html", user=target_user)


@admin_bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("admin")
def edit_user(user_id):
    """Admin can edit a trekker's basic profile info if needed."""
    target_user = User.query.filter_by(id=user_id, role="user").first_or_404()

    if request.method == "POST":
        target_user.full_name = request.form.get("full_name", "").strip()
        target_user.email = request.form.get("email", "").strip()
        target_user.phone = request.form.get("phone", "").strip()

        db.session.commit()
        flash("User details updated.", "success")
        return redirect(url_for("admin.users_list"))

    return render_template("admin/edit_user.html", user=target_user)


# ---------------------- BLACKLIST (works for BOTH staff and users) ------

@admin_bp.route("/blacklist/<int:user_id>", methods=["POST"])
@login_required
@role_required("admin")
def toggle_blacklist(user_id):
    """
    Toggles the blacklist status of any account (staff or user).
    A blacklisted account cannot log in (checked in the login route).
    """
    target_user = User.query.get_or_404(user_id)
    target_user.is_blacklisted = not target_user.is_blacklisted
    db.session.commit()

    if target_user.is_blacklisted:
        flash(f"{target_user.full_name} has been blacklisted.", "warning")
    else:
        flash(f"{target_user.full_name} has been un-blacklisted.", "success")

    # Send the admin back to wherever made sense for that role
    if target_user.role == "staff":
        return redirect(url_for("admin.staff_detail", user_id=target_user.id))
    return redirect(url_for("admin.user_detail", user_id=target_user.id))


# ---------------------- BOOKINGS (Admin) ----------------------------------
# This section was missing compared to the original wireframe, which shows
# a dedicated "Bookings" page in the Admin sidebar (screen 3) plus a
# "Recent Bookings" table on the Dashboard with a "View All Bookings ->"
# link. We add both here.

@admin_bp.route("/bookings")
@login_required
@role_required("admin")
def bookings_list():
    """
    Shows EVERY booking in the system (across all users and treks),
    matching wireframe screen 3's "Bookings" nav item.

    Supports an optional status filter (Booked / Cancelled / Completed)
    via a query string, e.g. /admin/bookings?status=Booked
    """
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


@admin_bp.route("/bookings/<int:booking_id>")
@login_required
@role_required("admin")
def booking_detail(booking_id):
    """Read-only detailed view of one booking (who booked, which trek, status)."""
    booking = Booking.query.get_or_404(booking_id)
    return render_template("admin/booking_detail.html", booking=booking)


# ---------------------- SEARCH (Admin) -----------------------------------

@admin_bp.route("/search")
@login_required
@role_required("admin")
def search():
    """
    Lets the admin search treks, staff, or users by name or ID.
    The search box and a dropdown (what to search: trek/staff/user)
    are both on the same search.html page.
    """
    query_text = request.args.get("q", "").strip()
    search_type = request.args.get("type", "trek")  # trek / staff / user

    results = []
    if query_text:
        if search_type == "trek":
            # Search by trek name, OR by ID if the query is a number
            results = Trek.query.filter(
                (Trek.name.ilike(f"%{query_text}%")) |
                (Trek.id == query_text if query_text.isdigit() else False)
            ).all()
        elif search_type == "staff":
            results = User.query.filter(
                User.role == "staff",
                (User.full_name.ilike(f"%{query_text}%")) |
                (User.id == query_text if query_text.isdigit() else False)
            ).all()
        elif search_type == "user":
            results = User.query.filter(
                User.role == "user",
                (User.full_name.ilike(f"%{query_text}%")) |
                (User.id == query_text if query_text.isdigit() else False)
            ).all()

    return render_template(
        "admin/search.html",
        results=results,
        query_text=query_text,
        search_type=search_type,
    )


# ---------------------- ANALYTICS (Admin) ---------------------------------

@admin_bp.route("/analytics")
@login_required
@role_required("admin")
def analytics():
    """
    Simple statistics page: most popular treks (by booking count) and
    a breakdown of bookings by status. Bootstrap + plain HTML/CSS only,
    so we pass plain numbers to the template and draw simple bar charts
    using CSS widths rather than a JS charting library.
    """
    # Count bookings per trek, find the most popular ones
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

    return render_template(
        "admin/analytics.html",
        treks_with_counts=treks_with_counts,
        booked_count=booked_count,
        cancelled_count=cancelled_count,
        completed_count=completed_count,
    )


# =========================================================================
#  BLUEPRINT 3: STAFF
#  Every route here is prefixed with /staff and protected so only
#  logged-in users with role="staff" can access it.
# =========================================================================
staff_bp = Blueprint("staff", __name__, template_folder="../templates/staff")


def get_current_staff_profile():
    """
    Small helper: gets the StaffProfile row that belongs to the
    currently logged-in staff USER. Every staff route needs this,
    so we avoid repeating the same query everywhere.
    """
    return StaffProfile.query.filter_by(user_id=current_user.id).first()


@staff_bp.route("/dashboard")
@login_required
@role_required("staff")
def dashboard():
    """
    Staff dashboard - shows treks assigned to this staff member, plus
    the number of registered users per assigned trek.
    """
    staff_profile = get_current_staff_profile()
    assigned_treks = staff_profile.assigned_treks if staff_profile else []

    # Build a simple dict: {trek_id: number_of_bookings}
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


@staff_bp.route("/assigned-treks")
@login_required
@role_required("staff")
def assigned_treks():
    """Full list view of all treks assigned to this staff member."""
    staff_profile = get_current_staff_profile()
    treks_list = staff_profile.assigned_treks if staff_profile else []
    return render_template("staff/assigned_treks.html", treks=treks_list)


def verify_staff_owns_trek(trek):
    """
    Security helper: makes sure the trek really belongs to the
    currently logged-in staff member. This enforces the spec rule
    "Ensure only assigned staff can manage a trek."
    If not, we show a 403 Forbidden error.
    """
    staff_profile = get_current_staff_profile()
    if staff_profile is None or trek.staff_id != staff_profile.id:
        abort(403)


@staff_bp.route("/treks/<int:trek_id>")
@login_required
@role_required("staff")
def trek_details(trek_id):
    """Detailed view of one trek assigned to this staff member."""
    trek = Trek.query.get_or_404(trek_id)
    verify_staff_owns_trek(trek)
    return render_template("staff/trek_details.html", trek=trek)


@staff_bp.route("/treks/<int:trek_id>/manage", methods=["GET", "POST"])
@login_required
@role_required("staff")
def trek_management(trek_id):
    """
    Lets staff update slots and status (Open/Closed) for a trek they manage.
    Also where they can mark a trek as Completed once it's finished.
    """
    trek = Trek.query.get_or_404(trek_id)
    verify_staff_owns_trek(trek)

    if request.method == "POST":
        new_status = request.form.get("status")
        new_available_slots = request.form.get("available_slots", type=int)

        # Staff can only choose from these statuses (not Pending - that's admin's job)
        allowed_statuses = ["Approved", "Open", "Closed", "Completed"]
        if new_status in allowed_statuses:
            trek.status = new_status

        # Make sure available_slots never goes negative or above total_slots
        if new_available_slots is not None:
            trek.available_slots = max(0, min(new_available_slots, trek.total_slots))

        db.session.commit()
        flash("Trek details updated.", "success")
        return redirect(url_for("staff.trek_management", trek_id=trek.id))

    return render_template("staff/trek_management.html", trek=trek)


@staff_bp.route("/treks/<int:trek_id>/participants")
@login_required
@role_required("staff")
def participants(trek_id):
    """Shows the list of users who booked this trek."""
    trek = Trek.query.get_or_404(trek_id)
    verify_staff_owns_trek(trek)

    trek_bookings = Booking.query.filter_by(trek_id=trek.id).all()
    return render_template("staff/participants.html", trek=trek, bookings=trek_bookings)


@staff_bp.route("/profile/edit", methods=["GET", "POST"])
@login_required
@role_required("staff")
def edit_profile():
    """Lets a staff member edit their own contact details."""
    if request.method == "POST":
        current_user.full_name = request.form.get("full_name", "").strip()
        current_user.email = request.form.get("email", "").strip()
        current_user.phone = request.form.get("phone", "").strip()

        db.session.commit()
        flash("Profile updated successfully.", "success")
        return redirect(url_for("staff.dashboard"))

    return render_template("staff/edit_profile.html", staff=current_user)


# =========================================================================
#  BLUEPRINT 4: USER (Trekker)
#  Every route here is prefixed with /user and protected so only
#  logged-in users with role="user" can access it.
# =========================================================================
user_bp = Blueprint("user", __name__, template_folder="../templates/user")


@user_bp.route("/dashboard")
@login_required
@role_required("user")
def dashboard():
    """
    Trekker dashboard - shows a quick summary: available treks they
    could book, their currently booked treks, and trek statuses.
    """
    open_treks = Trek.query.filter_by(status="Open").all()
    my_bookings = Booking.query.filter_by(user_id=current_user.id, status="Booked").all()

    return render_template(
        "user/dashboard.html",
        open_treks=open_treks,
        my_bookings=my_bookings,
    )


@user_bp.route("/treks")
@login_required
@role_required("user")
def available_treks():
    """
    Shows all OPEN treks (the only ones users are allowed to book),
    with optional search/filter by difficulty and location.
    Spec rule: "Allow users to book only if trek status is Open."
    """
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


@user_bp.route("/treks/<int:trek_id>")
@login_required
@role_required("user")
def trek_details(trek_id):
    """Detailed view of a single trek before booking it."""
    trek = Trek.query.get_or_404(trek_id)
    # Check if this user has already booked this trek (to avoid duplicate bookings)
    existing_booking = Booking.query.filter_by(
        user_id=current_user.id, trek_id=trek.id, status="Booked"
    ).first()
    return render_template(
        "user/trek_details.html", trek=trek, existing_booking=existing_booking
    )


@user_bp.route("/treks/<int:trek_id>/book", methods=["GET", "POST"])
@login_required
@role_required("user")
def book_trek(trek_id):
    """
    Books a trek for the current user.

    Important business rules enforced here:
        1. Trek must be "Open" status to be booked.
        2. Trek must have available_slots > 0 (no overbooking).
        3. A user cannot book the same trek twice while already booked.
    """
    trek = Trek.query.get_or_404(trek_id)

    if request.method == "POST":
        # ---- Rule 1: trek must be Open ----
        if trek.status != "Open":
            flash("This trek is not open for booking.", "danger")
            return redirect(url_for("user.trek_details", trek_id=trek.id))

        # ---- Rule 2: prevent overbooking ----
        if trek.available_slots <= 0:
            flash("Sorry, this trek is fully booked. No slots available.", "danger")
            return redirect(url_for("user.trek_details", trek_id=trek.id))

        # ---- Rule 3: no duplicate active booking ----
        already_booked = Booking.query.filter_by(
            user_id=current_user.id, trek_id=trek.id, status="Booked"
        ).first()
        if already_booked:
            flash("You have already booked this trek.", "warning")
            return redirect(url_for("user.trek_details", trek_id=trek.id))

        # ---- All checks passed: create the booking ----
        new_booking = Booking(
            user_id=current_user.id,
            trek_id=trek.id,
            status="Booked",
        )
        trek.available_slots -= 1  # one less slot available now

        db.session.add(new_booking)
        db.session.commit()

        flash(f'Trek "{trek.name}" booked successfully!', "success")
        return redirect(url_for("user.booking_details", booking_id=new_booking.id))

    return render_template("user/book_trek.html", trek=trek)


@user_bp.route("/bookings/<int:booking_id>")
@login_required
@role_required("user")
def booking_details(booking_id):
    """Shows the details/status of one specific booking."""
    booking = Booking.query.get_or_404(booking_id)

    # Make sure users can only view their OWN bookings
    if booking.user_id != current_user.id:
        abort(403)

    return render_template("user/booking_details.html", booking=booking)


@user_bp.route("/bookings/<int:booking_id>/cancel", methods=["POST"])
@login_required
@role_required("user")
def cancel_booking(booking_id):
    """
    Cancels a booking. We keep the Booking row (status="Cancelled")
    instead of deleting it, so the user's full history is preserved,
    as required by the spec ("Maintain complete booking history").
    """
    booking = Booking.query.get_or_404(booking_id)

    if booking.user_id != current_user.id:
        abort(403)

    if booking.status == "Booked":
        booking.status = "Cancelled"
        # Give the slot back to the trek since this user is no longer going
        booking.trek.available_slots += 1
        db.session.commit()
        flash("Booking cancelled.", "info")

    return redirect(url_for("user.trek_history"))


@user_bp.route("/history")
@login_required
@role_required("user")
def trek_history():
    """Shows the full booking history (Booked / Cancelled / Completed) for this user."""
    all_bookings = Booking.query.filter_by(user_id=current_user.id).order_by(
        Booking.booking_date.desc()
    ).all()
    return render_template("user/trek_history.html", bookings=all_bookings)


@user_bp.route("/history/<int:booking_id>")
@login_required
@role_required("user")
def history_details(booking_id):
    """Detailed read-only view of one past booking record."""
    booking = Booking.query.get_or_404(booking_id)

    if booking.user_id != current_user.id:
        abort(403)

    return render_template("user/history_details.html", booking=booking)


@user_bp.route("/profile/edit", methods=["GET", "POST"])
@login_required
@role_required("user")
def edit_profile():
    """Lets a trekker edit their own profile details."""
    if request.method == "POST":
        current_user.full_name = request.form.get("full_name", "").strip()
        current_user.email = request.form.get("email", "").strip()
        current_user.phone = request.form.get("phone", "").strip()

        db.session.commit()
        flash("Profile updated successfully.", "success")
        return redirect(url_for("user.dashboard"))

    return render_template("user/edit_profile.html", user=current_user)
