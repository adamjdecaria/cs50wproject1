import os

from flask import Flask, session, flash, jsonify, redirect, render_template, request, abort
from flask_session import Session
from sqlalchemy import create_engine, exc
from sqlalchemy.orm import scoped_session, sessionmaker
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
import urllib.request, json
from urllib.request import urlopen

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

# GoodReads API key must be imported
if not os.getenv("GOODREADS_KEY"):
    raise RuntimeError("Please set GOODREADS_KEY")

# Save GoodReads key for later use
key = os.getenv("GOODREADS_KEY")

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

    if request.method == "POST":

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
                result = db.execute("SELECT DISTINCT * FROM books WHERE LOWER(title) LIKE :title", {"title":("%"+title+"%")}).fetchall()
                print("Search Completed")
                print(result)

            except exc.IntegrityError as e:
                error_message = "Unable to find anything."
                return render_template("error.html", message=error_message)

        elif request.form.get("author"):
            author = request.form.get("author")

            try:
                result = db.execute("SELECT DISTINCT * FROM books WHERE LOWER(author) LIKE :author", {"author":("%"+author+"%")}).fetchall()

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

    # Search DB with ISBN only to pull book page with only selected isbn
    try:
        result = db.execute("SELECT DISTINCT * FROM books WHERE isbn LIKE :isbn", {"isbn":("%"+isbn+"%")}).fetchall()

    except exc.IntegrityError as e:
        flash("Unable to find anything.")
        return render_template("error.html")
    
    # Pull user reviews for selected isbn
    try:
        reviews = db.execute("SELECT * FROM reviews WHERE isbn=:isbn", {"isbn":isbn}).fetchall()
    
    except:
        flash("Unable to find anything.")
        return render_template("error.html")

    # Pull GoodReads data for selected isbn
    try:
        data = urlopen("https://www.goodreads.com/book/review_counts.json?isbns=%s&key=%s" % (isbn, key))
        data = json.loads(data.read())
        book_data = data['books']

    except:
        flash("Something went wrong.")
        return render_template("error.html")
   
    return render_template("book.html", data=result, reviews=reviews, goodreads = book_data)

@app.route("/submitReview", methods=["POST"])
def submitReview():
    """Submit a review for a book and add it to the database"""

    isbn = request.form.get("isbn")
    review = request.form.get("review")
    username = session["username"]
    score = request.form.get("score")

    # Check if this user has already reviewed this book
    try:
        result = db.execute("SELECT * FROM reviews WHERE username=:username AND isbn=:isbn", {"username":username, "isbn":isbn}).fetchall()
    
    except:
        flash("Something went wrong.")
        return render_template("error.html")
    
    if len(result) != 0:
        flash("Thank you - but you have already reviewed this title!")
        return render_template("search.html")

    # Insert new review into DB
    try:
        db.execute("INSERT INTO reviews (isbn, username, review, score) VALUES(:isbn, :username, :review, :score)", 
                        {"isbn": isbn, "username": username, "review": review, "score": score})
        db.commit()
        
    except exc.IntegrityError as e:
        session.clear()
        flash("Oops! Review was not recorded.")
        return render_template("error.html")

    # Pull fresh page with new review
    try:
        result = db.execute("SELECT DISTINCT * FROM books WHERE isbn LIKE :isbn", {"isbn":("%"+isbn+"%")}).fetchall()
            
    except exc.IntegrityError as e:
        session.clear()
        flash("Unable to find anything.")
        return render_template("error.html")
    
    try:
        reviews = db.execute("SELECT * FROM reviews WHERE isbn=:isbn", {"isbn":isbn}).fetchall()
    
    except:
        flash("Unable to find anything.")
        return render_template("error.html")
    
    # Pull GoodReads data for selected isbn
    try:
        data = urlopen("https://www.goodreads.com/book/review_counts.json?isbns=%s&key=%s" % (isbn, key))
        data = json.loads(data.read())
        book_data = data['books']

    except:
        flash("Something went wrong.")
        return render_template("error.html")

    flash("Review submitted!")
    return render_template("book.html", data=result, reviews=reviews, goodreads=book_data)

@app.route("/api/<isbn>", methods=["GET"])
def externalQuery(isbn):
    """Handle an external GET request and return JSON data for isbn passed into route"""

    # Search DB with ISBN only to pull book page with only selected isbn
    try:
        result = db.execute("SELECT DISTINCT * FROM books WHERE isbn LIKE :isbn", {"isbn":("%"+isbn+"%")}).fetchall()

    except exc.IntegrityError as e:
        flash("Unable to find anything.")
        return render_template("error.html")
    
    if not result:
        return abort(404)

    try:
        data = urlopen("https://www.goodreads.com/book/review_counts.json?isbns=%s&key=%s" % (isbn, key))
        data = json.loads(data.read())
        book_data = data['books']

    except:
        flash("Something went wrong.")
        return render_template("error.html")
    
    return jsonify(title=result[0][1], author=result[0][2], year=result[0][3], isbn=isbn, review_count=book_data[0]["reviews_count"], 
                        average_score=book_data[0]["average_rating"])


