# 🏔️ Peak Mist — Trekking Management App

A full-stack Flask web application for managing the end-to-end lifecycle of treks — from listing and staff assignment by admins, to discovery and booking by trekkers, to on-ground participant management by trek staff.

Built with **Flask**, **SQLAlchemy**, **Flask-Login**, **Jinja2**, and **Bootstrap**, backed by a local **SQLite** database.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Default Admin Login](#default-admin-login)
- [User Roles & Workflows](#user-roles--workflows)
- [Database Schema](#database-schema)
- [Application Routes](#application-routes)
- [Key Business Rules](#key-business-rules)
- [Running Tests](#running-tests)
- [Reading the Codebase](#reading-the-codebase)
- [Future Scope](#future-scope)
- [License](#license)

---

## Overview

Peak Mist solves the coordination problem trekking organizations face when running multiple treks with different staff, schedules, and slot capacities. Instead of manually tracking bookings and assignments, three role-specific dashboards handle everything:

- **Admin** creates and manages treks, approves trek staff, and monitors bookings and analytics.
- **Trek Staff** manage the treks assigned to them and view/manage participants.
- **Trekkers (Users)** browse available treks, book a slot, track their trek history, cancel bookings, and calculate their BMI.

The app is fully **server-rendered** — every route returns a complete HTML page via Jinja2 templates, rather than exposing a JSON API.

---

## Features

**Admin**
- Create, edit, and manage treks (dates, difficulty, slots, description, safety info, photos)
- Assign trek staff to specific treks
- Approve or reject trek-staff registration requests
- View and manage all trekker accounts, including blacklisting
- View all bookings across all treks
- Search users, staff, treks, and bookings by human-readable display ID (e.g. `U001`, `T003`, `S002`, `B010`)
- View aggregate analytics on bookings and trek activity

**Trek Staff**
- Self-register (subject to admin approval before first login)
- View treks assigned to them
- Update trek status/details for treks they manage
- View and manage the list of participants booked on their treks
- Edit their own profile

**Trekker (User)**
- Self-register and log in
- Browse all open treks
- Book a trek (blocked automatically once slots are full or the trek isn't Open)
- Cancel a booking (slot is returned, history preserved)
- View past trek history
- Calculate and track BMI over time
- Edit their own profile

**Cross-cutting**
- Role-based access control on every route via a custom decorator
- Secure password hashing (Werkzeug)
- Blacklist enforcement at login
- Duplicate-booking prevention (one active booking per user per trek)

---

## Tech Stack

| Layer              | Technology                          |
|--------------------|--------------------------------------|
| Backend framework  | Flask 3.0                            |
| ORM / Database     | Flask-SQLAlchemy 3.1, SQLite         |
| Auth & sessions    | Flask-Login 0.6                      |
| Templating         | Jinja2                               |
| Frontend styling   | Bootstrap + custom CSS               |
| Testing            | Pytest                               |

See [`requirements.txt`](./requirements.txt) for exact pinned versions.

---

## Project Structure

```
app.py                    # App factory — registers blueprints, seeds the default Admin account
backend/
    models.py             # All SQLAlchemy models (User, Trek, Booking, StaffProfile, ...)
    routes.py             # All route logic, organized into 4 sections: Auth, Admin, Staff, User
static/
    css/styles.css        # Custom styling layered on top of Bootstrap
    upload/                # Uploaded trek photos are stored here
templates/
    base.html               # Shared layout for public pages (home / login / register)
    layout_dashboard.html   # Shared layout for logged-in pages (includes sidebar nav)
    auth/                   # Home, login, register (user), register (staff)
    admin/                  # All Admin-facing pages
    staff/                  # All Trek Staff-facing pages
    user/                   # All Trekker-facing pages
tests/
    test_display_ids.py    # Tests for the human-readable display-ID generation logic
instance/
    trekking.db             # SQLite database file — auto-created on first run, not committed to git
requirements.txt
README.md
```

---

## Getting Started

### Prerequisites
- Python 3.10+

### Installation

1. **Clone or extract the project**, then open a terminal in the project's root folder (the one containing `app.py`).

2. **Create a virtual environment** (recommended):
   ```bash
   python -m venv venv
   ```
   Activate it:
   - Windows: `venv\Scripts\activate`
   - macOS/Linux: `source venv/bin/activate`

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the app:**
   ```bash
   python app.py
   ```

5. **Open your browser** and navigate to:
   ```
   http://127.0.0.1:5000
   ```

That's it — the SQLite database (`instance/trekking.db`) and the default Admin account are created **automatically** on first run. There's no manual database setup step.

---

## Default Admin Login

```
Username: admin
Password: admin123
```

There is no Admin self-registration page by design — Admin is expected to pre-exist. Change this password by editing the seeding logic in `app.py` or by building a dedicated "change password" feature.

---

## User Roles & Workflows

| Role         | How they get an account                                          | Where they log in                    |
|--------------|--------------------------------------------------------------------|----------------------------------------|
| Admin        | Pre-seeded automatically on first run                              | Login page → "Admin"                  |
| Trek Staff   | Self-register, then **must be approved by Admin**                  | Login page → "Trek Staff"             |
| Trekker/User | Self-register via the Register page                                | Login page → "Trekker (User)"         |

### Trek Staff approval workflow

1. A prospective staff member clicks **"Want to join as Trek Staff? Register here"** on the login page and submits the registration form.
2. Their account is created with `StaffProfile.status = "pending"`.
3. If they attempt to log in before approval, they're blocked with: *"Your staff account is awaiting admin approval."*
4. Admin sees a pending-request count on their dashboard and a **Pending Approval Requests** table (with Approve/Reject actions) on the Manage Staff page.
5. **Approve** → status becomes `"active"`; the staff member can now log in and access their dashboard.
6. **Reject** → status becomes `"rejected"`; the account record is kept (not deleted) but login remains blocked with a rejection message.

Admin does **not** create staff accounts directly — self-registration plus approval is the only path to an active Trek Staff account.

---

## Database Schema

**Tables**

| Table              | Purpose                                                                                   |
|---------------------|---------------------------------------------------------------------------------------------|
| `users`             | Account credentials & core profile (username, password hash, role, blacklist flag)         |
| `user_profiles`     | Extended trekker details — age, weight, height, address                                     |
| `staff_profiles`    | Links a user to their staff role; tracks approval status (`pending` / `active` / `rejected`)|
| `staff_details`     | Additional staff info, e.g. years of experience                                             |
| `treks`             | Trek listings — name, location, difficulty, duration, slots, status, dates, staff assigned  |
| `bookings`          | Links a user to a trek with status (`Booked` / `Cancelled`); unique per user+trek           |
| `bmi_calculations`  | Historical BMI readings logged per user                                                     |

**Relationships**

- One-to-one: `users` ↔ `user_profiles`
- One-to-one: `users` → `staff_profiles` (staff accounts only)
- One-to-one: `staff_profiles` → `staff_details`
- One-to-many: `staff_profiles` → `treks` (a staff member can be assigned multiple treks)
- One-to-many: `users` → `bookings`
- One-to-many: `treks` → `bookings`
- One-to-many: `users` → `bmi_calculations`

A ready-to-import SQL DDL script matching this schema (for tools like [drawdb.app](https://drawdb.app) or dbdiagram.io) is available separately as `trekking_app_schema.sql`.

---

## Application Routes

Since the app is server-rendered, routes return full HTML pages. Grouped by blueprint:

**Auth**
| Route | Method | Description |
|---|---|---|
| `/` | GET | Public home page |
| `/login` | GET, POST | Login for all three roles |
| `/register` | GET, POST | Trekker self-registration |
| `/register-staff` | GET, POST | Trek staff self-registration (pending admin approval) |
| `/logout` | GET | Ends the session |

**Admin**
| Route | Method | Description |
|---|---|---|
| `/admin/dashboard` | GET | Overview stats & pending approvals |
| `/admin/treks` | GET | List all treks |
| `/admin/treks/add` | GET, POST | Create a trek |
| `/admin/treks/<id>/edit` | GET, POST | Edit a trek |
| `/admin/treks/<id>/assign-staff` | POST | Assign staff to a trek |
| `/admin/staff` | GET | List staff & pending requests |
| `/admin/staff/<id>/approve` | POST | Approve a staff request |
| `/admin/staff/<id>/reject` | POST | Reject a staff request |
| `/admin/users` | GET | List trekkers |
| `/admin/blacklist/<id>` | POST | Toggle blacklist status |
| `/admin/bookings` | GET | List all bookings |
| `/admin/search` | GET | Search by display ID |
| `/admin/analytics` | GET | Aggregate analytics |

**Staff**
| Route | Method | Description |
|---|---|---|
| `/staff/dashboard` | GET | Staff overview |
| `/staff/assigned-treks` | GET | Treks assigned to this staff member |
| `/staff/treks/<id>/manage` | GET, POST | Update trek (only if assigned) |
| `/staff/treks/<id>/participants` | GET | View booked trekkers |
| `/staff/profile/edit` | GET, POST | Edit own profile |

**User**
| Route | Method | Description |
|---|---|---|
| `/user/dashboard` | GET | Trekker overview |
| `/user/treks` | GET | Browse available treks |
| `/user/treks/<id>/book` | GET, POST | Book a trek |
| `/user/bookings/<id>/cancel` | POST | Cancel a booking |
| `/user/history` | GET | Past trek history |
| `/user/profile/edit` | GET, POST | Edit own profile |

---

## Key Business Rules

- A trek can only be booked while its status is **Open**.
- Booking is blocked once `available_slots` reaches **0** — no overbooking.
- Only the **staff member assigned** to a trek can manage it; others get a Forbidden error.
- Cancelling a booking does **not** delete it — status changes to `Cancelled` so history is preserved, and the slot is returned to the trek.
- **Blacklisted** users/staff are blocked at login.
- Newly self-registered staff **cannot log in** until an Admin approves their request.

---

## Running Tests

```bash
pytest tests/
```

Current test coverage focuses on the human-readable display-ID generation logic (e.g. formatting `U001`, `T001`, `S001`, `B001`).

---

## Reading the Codebase

Recommended reading order for anyone new to the code:

1. `backend/models.py` — understand the database tables first.
2. `app.py` — see how the app is assembled and how blueprints are registered.
3. `backend/routes.py` — organized top-to-bottom into 4 labeled sections: Auth, Admin, Staff, User.
4. `templates/` — mostly plain HTML + Bootstrap with small `{{ }}` / `{% %}` Jinja tags for dynamic data.

---

## Future Scope

- Email notifications for booking confirmation, cancellation, and staff approval
- Payment gateway integration for paid treks
- CSV/PDF export of bookings and analytics
- Trek reviews and ratings from past participants
- REST API layer for a future mobile app

---
