# HarborWing Air — IT8 Midterm Drill & CRUD Project

| Folder | Project | Read this |
|---|---|---|
| [`database/`](database/README.md) | Part 1 — relational database, Faker seed script, example queries, EER diagram | `database/README.md` |
| [`application/`](application/README.md) | Part 2 — Flask CRUD web app that uses the Part 1 database | `application/README.md` |

New here? Follow **[GUIDE.md](GUIDE.md)** from top to bottom.

Quick start:
```bash
cd database && pip install -r requirements.txt && cp .env.example .env   # edit password
python seed.py                                                           # create + seed
cd ../application && pip install -r requirements.txt && cp .env.example .env
python app.py                                                            # http://127.0.0.1:5000
```

All data is fictional (Faker, fixed seed). No real passenger data or passwords are committed.
