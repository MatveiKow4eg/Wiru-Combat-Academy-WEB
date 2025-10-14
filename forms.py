from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField, PasswordField, SelectField, BooleanField
from wtforms.validators import DataRequired, Email, Length, EqualTo, Optional
from flask_wtf.file import FileField, FileAllowed, FileRequired
from flask_babel import gettext as _


class LoginForm(FlaskForm):
    email = StringField("Email or username", validators=[DataRequired(), Length(max=255)])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8, max=128)])
    remember = BooleanField("Remember me")
    submit = SubmitField("Sign in")


class RegisterForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    username = StringField("Username", validators=[Optional(), Length(max=80)])
    password = PasswordField(
        "Password",
        validators=[DataRequired(), Length(min=8, max=128)],
    )
    confirm = PasswordField(
        "Confirm Password",
        validators=[DataRequired(), EqualTo("password", message="Passwords must match")],
    )
    submit = SubmitField("Sign up")


class NewsForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=200)])
    body = TextAreaField("Body", validators=[DataRequired()])
    image = StringField("Image URL")
    submit = SubmitField("Save")


class ScheduleForm(FlaskForm):
    day_of_week = SelectField(
        "Day of Week",
        coerce=int,
        choices=[(0, "Mon"), (1, "Tue"), (2, "Wed"), (3, "Thu"), (4, "Fri"), (5, "Sat"), (6, "Sun")],
    )
    time = StringField("Time", validators=[DataRequired()])
    activity = StringField("Activity", validators=[DataRequired()])
    discipline = SelectField(
        "Discipline",
        validators=[DataRequired()],
        choices=[("boxing", "Boxing"), ("wrestling", "Wrestling"), ("mma", "MMA")],
    )
    coach = StringField("Coach")
    submit = SubmitField("Save")


class SignupForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=120)])
    email = StringField("Email", validators=[DataRequired(), Email()])
    phone = StringField("Phone")
    activity = SelectField(
        "Activity",
        validators=[DataRequired()],
        choices=[("boxing", "Boxing"), ("wrestling", "Wrestling"), ("mma", "MMA")],
    )
    submit = SubmitField("Sign up")


class PasswordChangeForm(FlaskForm):
    old_password = PasswordField("Current Password", validators=[DataRequired(), Length(min=8, max=128)])
    new_password = PasswordField("New Password", validators=[DataRequired(), Length(min=8, max=128)])
    confirm = PasswordField("Confirm New Password", validators=[DataRequired(), EqualTo("new_password", message="Passwords must match")])
    submit = SubmitField("Change password")


class ProfileEditForm(FlaskForm):
    full_name = StringField("Full name", validators=[Optional(), Length(max=255)])
    username = StringField("Username", validators=[Optional(), Length(max=80)])
    level = SelectField(
        "Level",
        validators=[Optional()],
        choices=[
            ("", _("—")),
            ("beginner", _("Beginner")),
            ("intermediate", _("Intermediate")),
            ("advanced", _("Advanced")),
        ],
    )
    group_name = SelectField(
        "Group",
        validators=[Optional()],
        choices=[
            ("", _("—")),
            ("A", "A"),
            ("B", "B"),
            ("C", "C"),
        ],
    )
    avatar = FileField("Avatar", validators=[Optional(), FileAllowed(["jpg", "jpeg", "png"], _("Images only"))])
    submit = SubmitField(_("Save changes"))


class DocumentUploadForm(FlaskForm):
    file = FileField("File", validators=[FileRequired(message="Choose a file"), FileAllowed(["pdf", "jpg", "jpeg", "png"], "PDF or Image only!")])
    note = StringField("Note", validators=[Optional(), Length(max=500)])
    submit = SubmitField("Upload")


class UserSearchForm(FlaskForm):
    q = StringField("Поиск", validators=[Optional(), Length(max=255)])
    submit = SubmitField("Search")
