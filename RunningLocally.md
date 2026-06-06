# Running Adverse Locally

## Step 1 — Create the `.env` File

Create a file called `.env` in the project root (`adverse/.env`) with the following content:

```env
SECRET_KEY=django-insecure-local-dev-key-change-in-production
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost

# Option A: SQLite (easiest for local preview — no PostgreSQL needed)
DATABASE_URL=sqlite:///db.sqlite3

# Option B: PostgreSQL (if you have it running)
# DATABASE_URL=postgres://youruser:yourpassword@localhost:5432/adverse_db

EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=your@email.com
EMAIL_HOST_PASSWORD=yourpassword

RECAPTCHA_SITE_KEY=dummy
RECAPTCHA_SECRET_KEY=dummy

RATELIMIT_ENABLE=False
```

> Use **Option A (SQLite)** if you just want to preview locally — no database installation needed.

---

## Step 2 — Activate the Virtual Environment

```powershell
cd "c:\Users\USER\Documents\Davis\Advers\adverse"
.venv\Scripts\activate
```

---

## Step 3 — Install Dependencies

```powershell
pip install -r requirements.txt
```

---

## Step 4 — Run Migrations

```powershell
python manage.py migrate
```

---

## Step 5 — Create the Site Entry (required once)

```powershell
python manage.py shell -c "from django.contrib.sites.models import Site; Site.objects.get_or_create(id=1, defaults={'domain': '127.0.0.1:8000', 'name': 'Advers Local'})"
```

This creates the required row in the `django_site` table. Without it the Django admin login page crashes with `Site matching query does not exist`.

---

## Step 6 — Create a Superuser (for the Admin Panel)

```powershell
python manage.py createsuperuser
```

Enter an email and password when prompted. This account will have `is_staff=True` and can access `/admin-panel/`.

---

## Step 7 — Start the Server

```powershell
python manage.py runserver
```

Then open <http://127.0.0.1:8000> in your browser.

---

## Key URLs to Preview

| URL | What you'll see |
| --- | --- |
| `http://127.0.0.1:8000/adverse-auth/register/` | Registration with role selection |
| `http://127.0.0.1:8000/adverse-auth/login/` | Login |
| `http://127.0.0.1:8000/admanager/dashboard/` | Ad Manager dashboard |
| `http://127.0.0.1:8000/advertiser/dashboard/` | Advertiser dashboard |
| `http://127.0.0.1:8000/admin-panel/` | Custom admin panel |
| `http://127.0.0.1:8000/admin/` | Django built-in admin |

---

## Note on Email Verification

Registration requires email verification. Since SMTP won't work with placeholder credentials, manually activate a test user:

1. Go to `http://127.0.0.1:8000/admin/`
2. Log in with your superuser account
3. Navigate to **Security > Custom users**
4. Find your test user and set `is_active = True`
5. Save — the user can now log in
