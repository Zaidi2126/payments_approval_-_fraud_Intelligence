# deriv_guard

Django + Django REST Framework backend for payment approval and fraud intelligence.

## Requirements

- Python 3.11+

## Setup

1. **Create a virtual environment**

   ```bash
   python -m venv .venv
   source .venv/bin/activate   # On Windows: .venv\Scripts\activate
   ```

2. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment (optional)**

   Create a `.env` file in the project root to override `SECRET_KEY` and `DEBUG`:

   ```
   SECRET_KEY=your-secret-key
   DEBUG=True
   ```

4. **Run database migrations**

   ```bash
   python manage.py migrate
   ```

5. **Run the development server**

   ```bash
   python manage.py runserver
   ```

   The API will be available at `http://127.0.0.1:8000/`.

## API

- **GET /health** — Health check. Returns `{"status": "ok"}`.
