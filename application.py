import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    stock_symbols = db.execute("SELECT shares, name, symbol FROM stocks WHERE user_id = :user_id", user_id=session["user_id"])
    grand = 0
    
    for stock_symbol in stock_symbols:
        symbol = stock_symbol["symbol"]
        name = stock_symbol["name"]
        shares = stock_symbol["shares"]
        stock = lookup(symbol)
        total = shares * stock["price"]
        grand = grand + total
        db.execute("UPDATE stocks SET price=:price, name=:name,total=:total WHERE user_id=:user_id AND symbol=:symbol", price=usd(stock["price"]), name=stock["name"],total=usd(total), user_id=session["user_id"], symbol=symbol)
    
    updated_cash = db.execute("SELECT cash FROM users WHERE id=:id", id=session["user_id"])
    
    grand += updated_cash[0]["cash"]
    
    updated_stocks = db.execute("SELECT * from stocks WHERE user_id=:user_id", user_id=session["user_id"])                              
    return render_template("index.html", stocks=updated_stocks,                        cash=usd(updated_cash[0]["cash"]), grand=grand)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    users = db.execute("SELECT * FROM users WHERE id = :id", id = session["user_id"])

    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")
        if symbol == "" or shares == "":
            return apology("must enter symbol and number of shares")
        if int(shares)<0:
            return apology("Must enter a positive and no floating point numbers of shares")
        stock = lookup(symbol)
        if not stock:
            return apology("invalid symbol")

        user_current_cash = db.execute("SELECT cash FROM 'users' WHERE id = :user_id", user_id = session["user_id"])

        diff_cash = user_current_cash[0]["cash"] - stock["price"] * int(shares)
        if not diff_cash < 0:
            exists = db.execute("SELECT * FROM 'stocks' WHERE id = :user_id AND symbol = :symbol", user_id = session["user_id"], symbol = stock["symbol"])

            if exists:
                current_shares = exists[0]["Shares"]
                db.execute("UPDATE 'stocks' SET shares = :shares, price = :price WHERE user_id = :user_id AND symbol = :symbol",
                    shares = current_shares + shares, price = stock["price"], user_id = session["user_id"], symbol = stock["symbol"])

            else:
                db.execute("INSERT INTO 'stocks' (user_id, symbol, name,shares, price) VALUES(:user_id, :symbol, :name,:shares, :price)",
                    user_id = session["user_id"], symbol = stock["symbol"], name=stock["name"],shares = shares, price = stock["price"])
                
            db.execute("UPDATE users SET 'cash' = :diff_cash WHERE id = :id", diff_cash = round(diff_cash, 2), id = session["user_id"])
            
            return redirect("/")
        else:
            return apology("you can't afford it!")
    else:
        return render_template("buy.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username")

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password")

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    users = db.execute("SELECT * FROM users WHERE id = :id", id = session["user_id"])
    if request.method == "POST":
        symbol = request.form.get("symbol")
        if symbol == "":
            return apology("must provide ticker")
        stock = lookup(symbol)
        if not stock:
            return apology("invalid symbol")
        else:
            return render_template("quoted.html", name = stock["name"], symbol = stock["symbol"], price = usd(stock["price"]))
    else:
        return render_template("quote.html", user = users[0]["username"])


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method=="POST":
        if not request.form.get("password") == request.form.get("confirmation"):
            return apology("password and password confirmation must match")
        hash = generate_password_hash(request.form.get("password"), method='pbkdf2:sha256', salt_length=8)
        check =  db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))
        if len(check) > 0:
            return apology("Username already exists")
        result = db.execute("INSERT INTO users (username, hash) VALUES(:username, :hash)", username=request.form.get("username"), hash=hash)
        session["user_id"] = result
        return redirect("/")
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        shares = int(request.form.get("shares"))
        if shares < 0:
            return apology("Shares must be positive integer")
        stock=lookup(request.form.get("symbol"))
        user_shares = db.execute("SELECT shares FROM stocks WHERE user_id = :user_id AND symbol=:symbol", user_id=session["user_id"], symbol=stock["symbol"])
        
        if not user_shares or int(user_shares[0]["shares"]) < shares:
            return apology("Not enough shares")
                            
        db.execute("UPDATE users SET cash = cash + :purchase WHERE id = :id", id=session["user_id"], purchase=stock["price"] * float(shares))
                        
        shares_total = user_shares[0]["shares"] - shares
        
        if shares_total == 0:
            db.execute("DELETE FROM stocks WHERE user_id=:user_id, symbol=:symbol", user_id=session["user_id"], symbol=stock["symbol"])
        else:
            db.execute("UPDATE stocks SET shares=:shares WHERE user_id=:user_id AND symbol=:symbol", shares=shares_total, user_id=session["user_id"], symbol=stock["symbol"])
        
        return redirect("/")
    else:
        symbols = db.execute("SELECT symbol FROM stocks WHERE user_id = :user_id", user_id=session["user_id"])
        stock_symbols = []
        for row in symbols:
            stock_symbols.append(row["symbol"])
        return render_template("sell.html", symbols=stock_symbols)

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
