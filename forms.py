from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField, PasswordField, SelectField, BooleanField, HiddenField
from wtforms.validators import DataRequired, Email, Length, EqualTo, Optional
from flask_wtf.file import FileField, FileAllowed, FileRequired
from flask_babel import gettext as _
from utils.sanitize import sanitize_plain_text, contains_dangerous_input


class BaseSecureForm(FlaskForm):
    website = HiddenField("website")  # honeypot

    def validate(self, extra_validators=None):
        ok = super().validate(extra_validators=extra_validators)
        # Honeypot check
        if (getattr(self, "website", None) and (self.website.data or "").strip()):
            self.errors.setdefault("website", []).append(_("Недопустимые символы"))
            return False
        # Scan textual fields for dangerous patterns
        dangerous = False
        for name, field in self._fields.items():
            try:
                from wtforms.fields import StringField as _SF, TextAreaField as _TA
            except Exception:
                _SF = _TA = ()
            if isinstance(field, (_SF, _TA)):
                raw = field.raw_data[0] if getattr(field, "raw_data", None) else field.data
                if contains_dangerous_input(raw):
                    field.errors.append(_("Недопустимые символы"))
                    dangerous = True
        if dangerous:
            try:
                from flask import current_app, request
                current_app.logger.warning(f"XSS attempt blocked on form {self.__class__.__name__} from IP={getattr(request, 'remote_addr', '?')}")
            except Exception:
                pass
            return False
        return ok

class LoginForm(BaseSecureForm):
    email = StringField("Email or username", validators=[DataRequired(), Length(max=255)], filters=[sanitize_plain_text])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8, max=128)])
    remember = BooleanField("Remember me")
    submit = SubmitField("Sign in")


class RegisterForm(BaseSecureForm):
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)], filters=[sanitize_plain_text])
    username = StringField("Username", validators=[Optional(), Length(max=80)], filters=[sanitize_plain_text])
    password = PasswordField(
        "Password",
        validators=[DataRequired(), Length(min=8, max=128)],
    )
    confirm = PasswordField(
        "Confirm Password",
        validators=[DataRequired(), EqualTo("password", message="Passwords must match")],
    )
    submit = SubmitField("Sign up")


class NewsForm(BaseSecureForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=200)], filters=[sanitize_plain_text])
    body = TextAreaField("Body", validators=[DataRequired()], filters=[sanitize_plain_text])
    image = StringField("Image URL", filters=[sanitize_plain_text])
    submit = SubmitField("Save")


class ScheduleForm(BaseSecureForm):
    day_of_week = SelectField(
        "Day of Week",
        coerce=int,
        choices=[(0, "Mon"), (1, "Tue"), (2, "Wed"), (3, "Thu"), (4, "Fri"), (5, "Sat"), (6, "Sun")],
    )
    time = StringField("Time", validators=[DataRequired()], filters=[sanitize_plain_text])
    activity = StringField("Activity", validators=[DataRequired()], filters=[sanitize_plain_text])
    discipline = SelectField(
        "Discipline",
        validators=[DataRequired()],
        choices=[("boxing", "Boxing"), ("wrestling", "Wrestling"), ("mma", "MMA"), ("sparring", "Sparring")],
    )
    coach = StringField("Coach", filters=[sanitize_plain_text])
    submit = SubmitField("Save")


class SignupForm(BaseSecureForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=120)], filters=[sanitize_plain_text])
    email = StringField("Email", validators=[DataRequired(), Email()], filters=[sanitize_plain_text])
    phone = StringField("Phone", filters=[sanitize_plain_text])
    activity = SelectField(
        "Activity",
        validators=[DataRequired()],
        choices=[("boxing", "Boxing"), ("wrestling", "Wrestling"), ("mma", "MMA"), ("sparring", "Sparring")],
    )
    submit = SubmitField("Sign up")


class PasswordChangeForm(BaseSecureForm):
    old_password = PasswordField("Current Password", validators=[DataRequired(), Length(min=8, max=128)])
    new_password = PasswordField("New Password", validators=[DataRequired(), Length(min=8, max=128)])
    confirm = PasswordField("Confirm New Password", validators=[DataRequired(), EqualTo("new_password", message="Passwords must match")])
    submit = SubmitField("Change password")


class ProfileEditForm(BaseSecureForm):
    full_name = StringField("Full name", validators=[Optional(), Length(max=255)], filters=[sanitize_plain_text])
    username = StringField("Username", validators=[Optional(), Length(max=80)], filters=[sanitize_plain_text])
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


class DocumentUploadForm(BaseSecureForm):
    file = FileField("File", validators=[FileRequired(message="Choose a file"), FileAllowed(["pdf", "jpg", "jpeg", "png"], "PDF or Image only!")])
    note = StringField("Note", validators=[Optional(), Length(max=500)], filters=[sanitize_plain_text])
    submit = SubmitField("Upload")


class UserSearchForm(BaseSecureForm):
    q = StringField("Поиск", validators=[Optional(), Length(max=255)], filters=[sanitize_plain_text])
    submit = SubmitField("Search")
