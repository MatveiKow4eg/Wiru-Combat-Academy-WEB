from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField, PasswordField, SelectField, BooleanField
from wtforms.validators import DataRequired, Email, Length, EqualTo, Optional


class LoginForm(FlaskForm):
    email = StringField("Email or username", validators=[DataRequired(), Length(max=255)])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=6, max=128)])
    remember = BooleanField("Remember me")
    submit = SubmitField("Sign in")


class RegisterForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    username = StringField("Username", validators=[DataRequired(), Length(max=80)])
    password = PasswordField(
        "Password",
        validators=[DataRequired(), Length(min=6, max=128)],
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
