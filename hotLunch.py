import os
import shutil

import csv
from cs50 import SQL
from flask import Flask, current_app, flash, jsonify, redirect, render_template, request, send_file, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from helpers import apology, login_required

# Configure application
application = Flask(__name__)

# Ensure templates are auto-reloaded
application.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@application.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Configure session to use filesystem (instead of signed cookies)
application.config["SESSION_FILE_DIR"] = mkdtemp()
application.config["SESSION_PERMANENT"] = False
application.config["SESSION_TYPE"] = "filesystem"
application.config["UPLOAD_FOLDER"] = 'menu'
Session(application)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///hotLunch.db")

# Set global variables WEEKS, MENU, DATES, and PRICING
WEEKS = 0
MENU = 0
DATES = 0
PRICING = 0

def set_variables():
    with open('menu/menu.txt') as f:
        global WEEKS, MENU, DATES, PRICING
        rows = csv.DictReader(f, delimiter='\t')
        dictionary = {}
        week = 0
        weekMenu = []
        DATES = []
        counter = 0
        for row in rows:
            if row['date']:
                DATES.append(row['date'])
            weekMenu.append(row)
            if (counter == 4):
                dictionary[week] = weekMenu
                weekMenu = list()
                week += 1
                counter = 0
            else:
                counter += 1
        WEEKS = week
        MENU = dictionary
    PRICING = {
        'elementary0': 600,
        'elementary1': 700,
        'middle': 800,
        'high': 1000
    }

# Function to delete all files in directory 'data'
def reset_files():
    folder = 'data'
    for filename in os.listdir(folder):
        file_path = os.path.join(folder, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print('Failed to delete %s. Reason: %s' % (file_path, e))

# Function to check if file uploaded is a text file and is named 'menu'
ALLOWED_EXTENSIONS = {'txt'}
def allowed_file(filename):
    return ('.' in filename and \
        filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS) and \
        filename.rsplit('.', 1)[0].lower() == 'menu'

set_variables()

@application.route("/")
@login_required
def index():

    # Query database for user
    users = db.execute("SELECT * FROM users WHERE id=:id", id=session["user_id"])
    username = users[0]['username']
    school = users[0]['school']

    # If user id is admin's, redirect to admin page
    if session["user_id"] == -1:
        return redirect("/admin")

    # Open logged menu if it exists, else redirect to /menu
    if os.path.isfile("data/"+username+".txt"):
        with open("data/"+username+".txt") as f:

            # Read menu file for user
            rows = csv.DictReader(f, delimiter='\t')
            personalMenu = {}
            week = 0
            weekMenu = []
            counter = 0
            number = 0
            for row in rows:
                if row['menu'] == 'None' or row['menu'] is None:
                    weekMenu.append("/")
                else:
                    chosenMenu = MENU[week][counter][row['menu']]
                    number += 1
                    weekMenu.append(chosenMenu)
                if (counter == 4):
                    personalMenu[week] = weekMenu
                    weekMenu = list()
                    week += 1
                    counter = 0
                else:
                    counter += 1

            # Figure out pricing
            if school in ['KD', 'g1', 'g2']:
                school = 'elementary0'
            elif school in ['g3', 'g4', 'g5']:
                school = 'elementary1'
            price = PRICING[school]
            total = price * number
            switcher = {
                'elementary0': 'KD - Grade 2',
                'elementary1': 'Grade 3 - Grade 5',
                'middle': 'Middle School',
                'high': 'High School'
            }
            school = switcher[school]
        return render_template("index.html", dictionary=personalMenu, weeks=WEEKS, username=username, school=school, total=total, number=number, price=price, dates=DATES)
    else:
        return redirect("/menu")

@application.route("/admin", methods=["GET", "POST"])
@login_required
def admin():

    # If not admin, redirect to index page
    if session["user_id"] != -1:
        return redirect("/")

    # Return html file if not POST
    if request.method == "GET":
        return render_template("admin.html")
    else:
        # Check if the post request has the file part
        if 'file' not in request.files:

            # Check if post request has username (meaning they want to mark someone as paid
            if not request.form.get("username"):
                return apology("Please input a username", 403)
            else:

                # Query database for username
                rows = db.execute("SELECT * FROM users WHERE username = :username",
                                  username=request.form.get("username"))
                if len(rows) != 1:
                    return apology("No username", 403)
                id = rows[0]["id"]

                # Update so user is marked as paid in database
                db.execute("UPDATE users SET paid = 1 WHERE id = :id", id=id)
                flash('Done!')
                return redirect("/admin")
            flash('No file part')
            return redirect("/admin")
        file = request.files['file']

        # If the user does not select a file, the browser submits an empty file without a filename.
        if file.filename == '':
            flash('No selected file')
            return redirect("/admin")

        # Upload file to menu directory
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(application.config['UPLOAD_FOLDER'], filename))
            flash('Uploaded!')
            set_variables()
            reset_files()
            return redirect("/admin")
        else:
            flash('Wrong name')
            return redirect("/admin")

@application.route('/download', methods=['GET', 'POST'])
@login_required
def download():

    # If not admin, redirect to index page
    if session["user_id"] != -1:
        return redirect("/")

    # Appending app path to upload folder path within app root folder
    downloads = os.path.join(current_app.root_path, 'downloads')
    rows = db.execute("SELECT * FROM users")
    schools = ['KD', 'g1', 'g2', 'g3', 'g4', 'g5', 'middle', 'high']
    fieldnames = ['name', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday']

    # Create csv files for every grade and every week
    for grade in schools:
        for i in range(10):
            f = open("downloads/orders/"+grade+"_"+str(i)+".csv", "w")
            f.write(','.join(fieldnames)+"\n")
            f.close()

    # For every user that is not admin and is marked as paid, read chosen menu and update corresponding csv
    for row in rows:
        if row["id"] != -1 and row["paid"] == 1:
            user = row['username']
            school = row['school']
            with open("data/" + user + ".txt", 'r') as tsv_file:
                read_tsv = csv.DictReader(tsv_file, delimiter="\t")
                file = []
                for line in read_tsv:
                    file.append(line)
                counter = 0
                all_weeks = []
                week = []
                for i in range(len(file)):
                    if counter < 5:
                        week.append(file[i])
                        counter += 1
                    else:
                        all_weeks.append(week)
                        week = []
                        counter = 1
                        week.append(file[i])
                all_weeks.append(week)
                for i in set(range(10)).intersection(set(range(len(all_weeks)))):
                    with open("downloads/orders/" + school + "_" + str(i) + ".csv", 'a') as csv_file:
                        items = {}
                        for day in all_weeks[i]:
                            items[day['dotw']] = day['menu']
                        write_csv = csv.DictWriter(csv_file, fieldnames=fieldnames)
                        write_csv.writerow({
                            'name': user,
                            'monday': items['Monday'],
                            'tuesday': items['Tuesday'],
                            'wednesday': items['Wednesday'],
                            'thursday': items['Thursday'],
                            'friday': items['Friday']})

    # Zip all orders
    shutil.make_archive('orders', 'zip', downloads)

    # Returning file from appended path
    return send_file('orders.zip', as_attachment=True)

@application.route('/delete')
@login_required
def delete():

    # If not admin, redirect to index
    if session["user_id"] != -1:
        return redirect("/")

    # Delete all rows except admin row
    db.execute("DELETE FROM users WHERE id NOT IN (-1)")
    reset_files()
    flash("Refreshed!")
    return redirect("/")

@application.route("/menu", methods=["GET", "POST"])
@login_required
def menu():
    if request.method == "GET":
        return render_template("menu.html", dictionary=MENU, weeks=WEEKS, dates=DATES)
    else:

        # Create tsv for user when they submit a menu
        username = db.execute("SELECT username FROM users WHERE id=:id", id=session["user_id"])
        username = username[0]['username']
        with open("data/"+username+".txt", 'w') as f:
            f.write("dotw\tmenu\n")
            for i in range(WEEKS):
                for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]:
                    f.write(day+"\t"+request.form.get(str(i)+day)+"\n")
        flash("Submitted!")
        return redirect("/")



@application.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("Please input a username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("Please input a password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("The username and/or password is not correct", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@application.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id,
    session.clear()

    # Redirect user to login form
    return redirect("/")


@application.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")
    else:

        # Check if username
        if request.form.get("username"):

            # Check if password
            if request.form.get("password"):

                # Check if password confirmation
                if request.form.get("confirmation"):

                    # Check if password == password confirmation
                    if request.form.get("confirmation") == request.form.get("password"):

                        # Check if username already exists
                        if not db.execute("SELECT * FROM users WHERE username=:username", username=request.form.get("username")):

                            # Generate hashed password, insert row into table, record session id
                            user_hash = generate_password_hash(request.form.get("password"))
                            userid = db.execute("INSERT INTO users (username, hash, school) VALUES (:username, :hash, :grade)", username=request.form.get("username"), hash=user_hash, grade=request.form.get("grade"))
                            session["user_id"] = userid
                            flash("Registered!")
                            return redirect("/")
                        else:
                            return apology("Username already exists")
                    else:
                        return apology("The passwords do not match")
                else:
                    return apology("Please confirm your password")
            else:
                return apology("Please input a password")
        else:
            return apology("Please input a username")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    application.errorhandler(code)(errorhandler)

if __name__ == "__main__":
    application.run(host="0.0.0.0")
