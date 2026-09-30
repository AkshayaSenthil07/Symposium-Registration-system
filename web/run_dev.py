"""Development server (auto-reload, http://127.0.0.1:5000). Use `python manage.py run` in production."""
from webapp import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
