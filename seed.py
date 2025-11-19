from app import app, db, User

with app.app_context():
    db.session.query(User).delete()  # delete all rows
    db.session.commit()

    users = [
        User(username="admin1", password="admin123", role="admin"),
        User(username="stud1", password="stud123", role="student"),
        User(username="parent1", password="parent123", role="parent"),
        User(username="hte1", password="hte123", role="hte"),
    ]

    db.session.add_all(users)
    db.session.commit()
    print("✅ Users reset and inserted!")
