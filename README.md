# Macnova Machinery Fleet Usage App

A Django web application for tracking machinery usage, maintenance, and inspections for Macnova's fleet management.

## Features

- **Machine Management**: Track excavators, loaders, and other machinery with QR code access
- **Usage Reports**: Operators submit detailed reports with:
  - Engine hours (start/end)
  - Fuel levels
  - GPS location
  - Multiple photos (front, back, sides, wheels, cockpit)
  - Inspection checklist
  - **Digital signatures** (operator + administrator)
- **Bilingual Support**: Spanish (default) and English for operator-facing forms
- **Manager Dashboard**: View reports, filter by date/machine/job site, export to CSV
- **Admin Interface**: Full Django admin for managing machines, job sites, and reports

## Tech Stack

- **Backend**: Django 5.2.8
- **Database**: PostgreSQL (production) / SQLite (local development)
- **Storage**: AWS S3 for media files (photos and signatures)
- **Hosting**: Render
- **Static Files**: WhiteNoise
- **Language**: Django i18n (Spanish/English)

## Quick Start

### Prerequisites

- Python 3.13+
- PostgreSQL (for production)
- AWS S3 bucket (for production media storage)

### Local Development Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd App_Macnova
   ```

2. **Create virtual environment**
   ```bash
   python3.13 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   
   Create a `.env` file in the project root:
   ```bash
   DJANGO_SECRET_KEY=your-secret-key-here
   DJANGO_DEBUG=True
   DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
   USE_POSTGRES=False
   USE_S3=False
   ```

5. **Run migrations**
   ```bash
   python manage.py migrate
   ```

6. **Create superuser**
   ```bash
   python manage.py createsuperuser
   ```

7. **Run development server**
   ```bash
   python manage.py runserver
   ```

8. **Access the application**
   - Admin: `http://localhost:8000/admin/`
   - Dashboard: `http://localhost:8000/dashboard/` (requires login)
   - Machine form: `http://localhost:8000/m/<qr-slug>/`

## Project Structure

```
App_Macnova/
├── core/                 # Django project settings
│   ├── settings.py      # Main configuration
│   └── urls.py          # URL routing
├── fleet/               # Main application
│   ├── models.py        # Database models
│   ├── views.py         # View logic
│   ├── admin.py         # Admin configuration
│   ├── storage_backends.py  # S3 storage backend
│   ├── migrations/      # Database migrations
│   └── templates/       # HTML templates
├── locale/              # Translation files (Spanish/English)
├── requirements.txt      # Python dependencies
└── manage.py           # Django management script
```

## Key Models

- **Machine**: Physical machinery with QR code access
- **JobSite**: Construction sites/projects
- **UsageReport**: Usage session with engine hours, fuel, GPS, signatures
- **UsagePhoto**: Photos attached to reports
- **ChecklistItem**: Reusable inspection questions
- **ChecklistEntry**: Answers to checklist items per report

## Production Deployment

### Render Configuration

**Build Command:**
```bash
pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate
```

**Start Command:**
```bash
gunicorn core.wsgi:application --bind 0.0.0.0:8000
```

### Required Environment Variables

**Django:**
- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG=False`
- `DJANGO_ALLOWED_HOSTS=macnova-machinery-app.onrender.com`

**Database:**
- `USE_POSTGRES=True`
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`

**AWS S3:**
- `USE_S3=True`
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_STORAGE_BUCKET_NAME=macnova-machinery-media`
- `AWS_S3_REGION_NAME=us-east-2`

## Features in Detail

### Language Support

- **Default Language**: Spanish
- **Supported Languages**: Spanish (es), English (en)
- **Language Switcher**: Available on usage form (top right dropdown)
- **Translation Scope**: Only operator-facing pages (form and success page)
- **Translation Files**: `locale/es/LC_MESSAGES/` and `locale/en/LC_MESSAGES/`

### Signature Feature

- **Required Signatures**: Both operator and administrator signatures are required
- **Capture Method**: SignaturePad.js library (mobile-friendly touch support)
- **Storage**: Saved as PNG images in `signatures/` folder (S3 in production)
- **Processing**: Base64 data URLs converted to image files server-side

### QR Code System

Each machine has a unique UUID (`qr_slug`) that generates a QR code. Operators scan the QR code to access the usage form:
- URL format: `/m/<uuid>/`
- Example: `https://macnova-machinery-app.onrender.com/m/94a383c0-57a8-4e36-9d19-65a06d34c834/`

## Development Workflow

### Daily Start

1. Activate virtual environment: `source venv/bin/activate`
2. Pull latest changes: `git pull --rebase origin main`
3. Run migrations if needed: `python manage.py migrate`
4. Start server: `python manage.py runserver`

### Making Changes

1. Create a feature branch: `git checkout -b feature/your-feature`
2. Make changes and test locally
3. Commit: `git commit -m "Description of changes"`
4. Push branch: `git push -u origin feature/your-feature`
5. Merge to main after testing

## Admin Access

### Creating Staff Users

1. Log in as superuser
2. Go to **Users** in admin
3. Add user or edit existing user
4. Check **Staff status** to grant admin/dashboard access
5. Optionally check **Superuser status** for full permissions

## File Storage

### Local Development
- Media files stored in `media/` directory
- Photos: `media/usage_photos/`
- Signatures: `media/signatures/`

### Production
- All media files stored in AWS S3 bucket
- Photos: `s3://macnova-machinery-media/usage_photos/`
- Signatures: `s3://macnova-machinery-media/signatures/`
- Public URLs: `https://macnova-machinery-media.s3.us-east-2.amazonaws.com/...`

## Useful Commands

```bash
# Django
python manage.py runserver          # Start dev server
python manage.py migrate            # Apply migrations
python manage.py createsuperuser    # Create admin user
python manage.py shell              # Django shell
python manage.py check              # System checks
python manage.py collectstatic     # Collect static files (production)

# Translations
python manage.py makemessages -l es    # Extract Spanish translations
python manage.py makemessages -l en    # Extract English translations
python manage.py compilemessages       # Compile translation files

# Git
git status                           # Check status
git pull --rebase origin main       # Update from remote
git checkout -b feature/name         # Create feature branch
```

## Troubleshooting

### Signatures not saving locally
- This is expected - signatures are designed to work in production with S3
- Local file storage may have issues, but production S3 storage works correctly

### Language not defaulting to Spanish
- Check that `LANGUAGE_CODE = "es"` in `settings.py`
- Clear browser cache/cookies
- Check that `LocaleMiddleware` is in `MIDDLEWARE`

### Database connection errors
- Local: Ensure `USE_POSTGRES=False` in `.env`
- Production: Verify all database environment variables are set correctly

## License

Proprietary - Macnova Machinery

## Support

For issues or questions, contact the development team.

