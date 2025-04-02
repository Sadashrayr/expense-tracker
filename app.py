from expense_tracker import ExpenseTracker
import os
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
)
from werkzeug.utils import secure_filename
import matplotlib

matplotlib.use("Agg")  # Use non-interactive backend

app = Flask(__name__)
app.secret_key = "s3cr3t"  # Change this to a random secret key
app.config["UPLOAD_FOLDER"] = "uploads"
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max upload
app.config["ALLOWED_EXTENSIONS"] = {"csv"}

# Create upload folder if it doesn't exist
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_EXTENSIONS"]
    )


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        flash("No file part", "error")
        return redirect(request.url)

    file = request.files["file"]

    if file.filename == "":
        flash("No file selected", "error")
        return redirect(request.url)

    if file and allowed_file(file.filename):
        # Save file temporarily
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)

        # Process the file
        tracker = ExpenseTracker()
        success = tracker.load_data(filepath)

        if not success:
            flash("Error loading data. Please check your CSV format.", "error")
            return redirect(url_for("index"))

        # Add custom categories if provided
        if request.form.get("custom_categories"):
            try:
                custom_categories = {}
                categories_text = request.form.get("custom_categories")
                for line in categories_text.split("\n"):
                    if ":" in line:
                        category, keywords = line.split(":", 1)
                        custom_categories[category.strip()] = [
                            k.strip() for k in keywords.split(",")
                        ]

                if custom_categories:
                    tracker.add_custom_category_rules(custom_categories)
            except Exception as e:
                flash(
                    f"Error processing custom categories: {str(e)}", "warning")

        # Categorize expenses
        tracker.categorize_expenses()

        # Store the required data in session
        session["has_data"] = True
        session["filepath"] = filepath

        # Generate charts and get data
        category_summary = tracker.get_category_summary()
        monthly_summary = tracker.get_monthly_summary()
        unusual_expenses = tracker.identify_unusual_expenses()

        # Convert DataFrames to lists for JSON serialization
        session["category_summary"] = (
            category_summary.to_dict(
                "records") if category_summary is not None else []
        )
        session["monthly_summary"] = (
            monthly_summary.to_dict(
                "records") if monthly_summary is not None else []
        )
        session["unusual_expenses"] = (
            unusual_expenses.to_dict(
                "records") if unusual_expenses is not None else []
        )

        # Generate and save charts
        try:
            # Category chart
            tracker.plot_expenses_by_category()
            # Monthly trend chart
            tracker.plot_monthly_trend()

            session["charts_generated"] = True
        except Exception as e:
            flash(f"Error generating charts: {str(e)}", "warning")
            session["charts_generated"] = False

        # User's budget (simple implementation)
        if request.form.get("budget"):
            try:
                session["budget"] = float(request.form.get("budget"))
            except ValueError:
                flash("Invalid budget value. Using no budget comparison.", "warning")

        return redirect(url_for("dashboard"))

    flash("Invalid file format. Please upload a CSV file.", "error")
    return redirect(url_for("index"))


@app.route("/dashboard")
def dashboard():
    if not session.get("has_data"):
        flash("Please upload your expense data first", "info")
        return redirect(url_for("index"))

    # Load data from session
    category_summary = session.get("category_summary", [])
    monthly_summary = session.get("monthly_summary", [])
    unusual_expenses = session.get("unusual_expenses", [])
    budget = session.get("budget")

    # Calculate total expenses
    total_expenses = sum(item["sum"] for item in category_summary)

    # Calculate budget status
    budget_status = None
    if budget:
        budget_status = {
            "budget": budget,
            "total": total_expenses,
            "remaining": budget - total_expenses,
            "percentage": (total_expenses / budget) * 100 if budget > 0 else 0,
        }

    # Prepare data for monthly trend chart
    months_data = {}
    for item in monthly_summary:
        month_key = f"{item['year']}-{item['month']:02d}"
        if month_key not in months_data:
            months_data[month_key] = 0
        months_data[month_key] += item["amount"]

    monthly_trend = {
        "labels": list(months_data.keys()),
        "values": list(months_data.values()),
    }

    # Prepare data for category chart
    category_data = {}
    for item in category_summary:
        category_data[item["category"]] = item["sum"]

    category_chart = {
        "labels": list(category_data.keys()),
        "values": list(category_data.values()),
    }

    return render_template(
        "dashboard.html",
        category_summary=category_summary,
        total_expenses=total_expenses,
        unusual_expenses=unusual_expenses,
        budget_status=budget_status,
        monthly_trend=monthly_trend,
        category_chart={
            # Access using dictionary keys
            "labels": list(category_chart["labels"]),
            # Access using dictionary keys
            "values": list(category_chart["values"]),
        },
        charts_generated=session.get("charts_generated", False),
    )


@app.route("/reset")
def reset():
    # Clear session data
    session.clear()
    # Remove temporary files
    if "filepath" in session and os.path.exists(session["filepath"]):
        try:
            os.remove(session["filepath"])
        except:
            pass

    flash("Data has been reset. You can upload a new file.", "info")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)
