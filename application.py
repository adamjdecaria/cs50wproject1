import os

from flask import Flask, session, flash, jsonify, redirect, render_template, request
from flask_session import Session
from sqlalchemy import create_engine, exc
from sqlalchemy.orm import scoped_session, sessionmaker
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))

@app.route("/")
def index():
    return render_template("login.html")

# Allow user to register for an account with Book Talk
@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    if request.method == "POST":

        # check for username
        if not request.form.get("username"):
            return render_template("error.html", message="Must provide a username.")

        # check for password
        elif not request.form.get("password"):
            return render_template("error.html", message="Must provide a password.")

        # check for confirmation
        elif not request.form.get("confirmation"):
            return render_template("error.html", message="Must confirm password.")

        # check that password and confirmation match
        elif request.form.get("password") != request.form.get("confirmation"):
            return render_template("error.html", message="Password and Confirmation must be the same.")

        hashed_pwd = generate_password_hash(request.form.get("password"), method='pbkdf2:sha256', salt_length=8)
        
        try:
            db.execute("INSERT INTO users (username, password) VALUES(:username, :hashed_pwd)",
                                {"username": request.form.get("username"), "hashed_pwd": hashed_pwd})
            db.commit()
        
        except exc.IntegrityError as e:
            error_message = "That username is taken.  Please choose another."
            return render_template("error.html", message=error_message)
               
        # Redirect user to blog post page
        flash("Registered!")
        return render_template("login.html")

    else:
        return render_template("register.html") 
    

# Allow the user to login to the personalized Book Talk site
@app.route("/login", methods = ["GET", "POST"])
def login():
    """Log user in to their Book Talk account"""
    
    session.clear()

    if request.method == "POST":
        # check for username
        if not request.form.get("username"):
            return render_template("error.html", message="Please enter your username.")

        # check for password
        elif not request.form.get("password"):
            return render_template("error.html", message="Please enter your password.")
        
        # Query database for username
        result = db.execute("SELECT * FROM users WHERE username = :username",
                          {"username": request.form.get("username")}).fetchall()
        
        # Ensure username exists and password is correct
        if len(result) != 1 or not check_password_hash(result[0]["password"], request.form.get("password")):
            return render_template("error.html", message="Invalid username and/or password")
                
        # Remember which user has logged in
        session["user_id"] = result[0]["id"]

        # remember the username of the user logged in
        session["username"] = result[0]["username"]

        flash("Logged in!")
        return render_template("search.html")

    else:
        return render_template("login.html")
        
@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    flash("Logged out!")
    return redirect("/")

@app.route("/search", methods=["GET", "POST"])
def search():
    """Search for books from Goodreads API using ISBN, title or author"""

    if request.method == "GET":
        return render_template("search.html")

    if request.form.get("isbn"):
        isbn = request.form.get("isbn")

        try:
            result = db.execute("SELECT DISTINCT * FROM books WHERE isbn LIKE :isbn", {"isbn":("%"+isbn+"%")}).fetchall()
            print("Search Completed")
            print(result)

        except exc.IntegrityError as e:
            error_message = "Unable to find anything."
            return render_template("error.html", message=error_message)
       
    elif request.form.get("title"):
        title = request.form.get("title")

        try:
            result = db.execute("SELECT DISTINCT * FROM books WHERE title LIKE :title", {"title":("%"+title+"%")}).fetchall()
            print("Search Completed")
            print(result)

        except exc.IntegrityError as e:
            error_message = "Unable to find anything."
            return render_template("error.html", message=error_message)

    elif request.form.get("author"):
        author = request.form.get("author")

        try:
            result = db.execute("SELECT DISTINCT * FROM books WHERE author LIKE :author", {"author":("%"+author+"%")}).fetchall()
            print("Search Completed")
            print(result)

        except exc.IntegrityError as e:
            error_message = "Unable to find anything."
            return render_template("error.html", message=error_message)
    
    else:
        return("error.html")
   
    return render_template("search_results.html", data=result)

@app.route("/search_by_ISBN", methods=["POST"])
def search_by_ISBN():
    """Search for book selected by user via ISBN"""

    isbn = request.form["choice"]

    try:
        result = db.execute("SELECT DISTINCT * FROM books WHERE isbn LIKE :isbn", {"isbn":("%"+isbn+"%")}).fetchall()
        print("Search Completed")
        print(result)

    except exc.IntegrityError as e:
        flash("Unable to find anything.")
        return render_template("error.html")
    
    try:
        reviews = db.execute("SELECT * FROM reviews WHERE isbn=:isbn", {"isbn":isbn}).fetchall()
    
    except:
        flash("Unable to find anything.")
        return render_template("error.html")
    
    return render_template("book.html", data=result, reviews=reviews)

@app.route("/submitReview", methods=["POST"])
def submitReview():
    """Submit a review for a book and add it ot the database"""

    isbn = request.form.get("isbn")
    review = request.form.get("review")
    username = session["username"]

    try:
        db.execute("INSERT INTO reviews (isbn, username, review) VALUES(:isbn, :username, :review)", 
                        {"isbn": isbn, "username": username, "review": review})
        db.commit()
        
    except exc.IntegrityError as e:
        error_message = "Oops! Review was not recorded."
        session.clear()
        return render_template("error.html", message=error_message)

    try:
        result = db.execute("SELECT DISTINCT * FROM books WHERE isbn LIKE :isbn", {"isbn":("%"+isbn+"%")}).fetchall()
        print("Search Completed")
     
    except exc.IntegrityError as e:
        error_message = "Unable to find anything."
        return render_template("error.html", message=error_message)
    
    try:
        reviews = db.execute("SELECT * FROM reviews WHERE isbn=:isbn", {"isbn":isbn}).fetchall()
    
    except:
        flash("Unable to find anything.")
        return render_template("error.html")

    flash("Review submitted!")
    return render_template("book.html", data=result, reviews=reviews)
