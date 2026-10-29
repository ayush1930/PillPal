# PillPal — Semester 1 Django web application

Semester 1 uses Django views, forms, templates, ORM, sessions, authentication, CSRF protection and SQLite. CSS, SVG icons, fonts and the chosen homepage image are local. JavaScript only handles browser interactions such as navigation, profile tabs, upload labels and displayed totals. Search submits a normal GET form; create/edit actions submit POST forms and return HTML or redirects.


## Project structure

```text
backend/
  manage.py
  requirements.txt
  .env.example
  pillpal/              # project settings and root URL configuration
  core/                 # one app containing all non-administrator features
    models.py           # model registration; all business models have label core
    urls.py             # ordinary Django website routes
    features/           # Python packages, not separate Django apps
      accounts/         # shared user/address models
      deliveries/       # notes; delivery operations use orders/services.py
      disputes/         # order complaints, evidence and reusable review rules
      inventory/        # stock, reorder models and receiving service
      medications/      # medication catalogue
      notifications/    # persisted in-app notifications
      orders/           # orders/items, checkout and fulfillment services, tests
      payments/         # cash collection service; legacy model retained for schema compatibility
      pharmacies/       # profiles and pharmacy staff membership
      prescriptions/    # uploads, verification and refill eligibility
      reminders/        # medication schedules
      reports/          # reusable reporting calculations
      reviews/          # completed-order feedback
      suppliers/        # supplier contacts
    web/                # named function views, shared forms and presentation helpers
    common/             # shared abstract model
    migrations/
    management/commands/
    templatetags/
  administration/       # separate admin portal, invitations and CSV export
frontend/
  templates/            # server-rendered HTML for every role
  static/               # CSS, JavaScript, fonts, icons, images

```

## Run on Windows / VS Code

Open the entire folder, then Terminal > New Terminal. Run commands separately:

```powershell
cd backend
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py runserver
```

Only copy .env.example if you do not already have .env. Use your chosen administrator email and password. Keep the terminal running. Open http://127.0.0.1:8000/ for the website, http://127.0.0.1:8000/administrator/ for the administrator portal or http://127.0.0.1:8000/admin/ for Django administration. The createsuperuser command creates an administrator-role account.

Requirements contain Django>=5.2.8,<5.3 and Pillow>=12,<13. Pillow is an image-handling library needed by Django ImageField; it is not another web framework. Django's transitive dependencies are installed automatically. There is no Node/npm build step. Runserver is for local coursework development.

## Start with records

A new database starts empty. Create pharmacy and medication records as administrator, then invite a pharmacist and assign that pharmacy. Add inventory through the pharmacist or Django admin. Invite a driver. Patients register themselves. Staff password setup links print to the server terminal with the default console email backend; open the link to choose the password. Actual outbound email requires configuring Django's SMTP backend.

Alternatively, generate optional demonstration users and stock:

```powershell
.\.venv\Scripts\python.exe manage.py seed_demo
```

Choose a strong password when prompted. New accounts are demo.admin@example.test, demo.pharmacist@example.test, demo.driver@example.test and demo.patient@example.test. No password is stored in source code or printed. Existing passwords/stock are not overwritten. These records are examples, not real people or medical guidance. See docs/DEMONSTRATION.md for the end-to-end walkthrough.


## Checks

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test core administration
```

75 tests passed with Python 3.14.3, Django 5.2.18 and Pillow 12.3.0 in an isolated environment. The tests use separate databases and temporary upload directories. They cover all role pages, session login, CSRF, forms, ownership, checkout, stock rollback, cancellation, pickup, driver assignment, prescription completion/refills, cash recording, reorder receiving, notifications, media access and password-reset email.

Use .gitignore to exclude .env, .venv, db.sqlite3, uploads, caches and backup files. Keep migrations, .env.example, fonts and their licenses in GitHub. The shared User model and all feature models belong to core; administrator operations belong to administration.

## Manual inventory entry

Pharmacists and administrators open Inventory -> Add Medication Stock. Select an existing catalogue item or enter the details of a new medication, choose the pharmacy and record price, supplier and quantity. The shared add_inventory service checks ownership and updates stock atomically. There are no barcode scanner, camera-capture or live map controls in this release. Saved-coordinate distance estimates and the driver online/offline browsing controls are included.

Order Status shows recorded stages such as pending, processing, ready, out for delivery and delivered. Pharmacy search uses medication names, pharmacy names/addresses, ratings, hours, delivery availability and distance from the patient’s saved address coordinates. These are complete web workflows using ordinary Django GET/POST forms.


## Order disputes

Patients see My Disputes in their sidebar and Report a Problem on each owned order. They can submit a subject, category, description and optional PDF/image evidence. One active dispute is allowed per order. Administrators see Disputes in their own sidebar, with search/status filters and a review page. They can respond, mark a case Under review, resolve/reject it with an explanation, or reopen a closed case for review if there is no other active complaint for that order.

Each submission/review adds a history event. Administrator changes notify the patient; new complaints notify active administrators. Only the owner and administrators can read a complaint or download evidence. Downloads are authenticated attachments, never public media links. Concurrent reviews are version-checked so a stale form cannot overwrite a newer decision.


## Saved distances and driver availability

Address and pharmacy forms accept optional latitude/longitude pairs. Latitude must be between -90 and 90 and longitude between -180 and 180; enter both or leave both blank. Pharmacy distance is a straight-line estimate in miles from the default saved address (or the first saved address when none is default). Distance (Nearest) sorts known estimates first. Missing coordinates produce no distance estimate rather than a fabricated value. This does not collect device GPS data or calculate a road route.

Drivers have an Online/Offline toggle on their dashboard. It is a session browsing preference: offline hides the available-delivery panel, while assigned order records remain accessible. It is not a global location or dispatch-presence feed. The toggle requires a logged-in driver and a CSRF-protected POST.


## Function-based page views

The website uses named Django functions such as login_view, register_view, profile_view, inventory_view and order_status_view. core/web/views.py handles authentication, order/cart operations, protected files and shared dispatch/helpers. core/web/dashboard_views.py contains the named dashboard page views. core/web/password_views.py provides named function entry points that retain Django's built-in password-reset processing, token checks and security. Administration, inventory intake and dispute handlers use descriptive *_view function names too.
