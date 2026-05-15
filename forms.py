from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, PasswordField, SubmitField, BooleanField, TextAreaField, FloatField, SelectField, MultipleFileField
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError
from models import User

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=2, max=20)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    role = SelectField('Role', choices=[('customer', 'Customer'), ('agent', 'Agent')], validators=[DataRequired()])
    submit = SubmitField('Sign Up')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('That username is taken. Please choose a different one.')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('That email is already registered. Please choose a different one.')

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember Me')
    submit = SubmitField('Login')

class PropertyForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired()])
    description = TextAreaField('Description', validators=[DataRequired()])
    price = FloatField('Price (OMR)', validators=[DataRequired()])
    location = StringField('Location', validators=[DataRequired()])
    type = SelectField('Type', choices=[('Villa', 'Villa'), ('Apartment', 'Apartment'), ('Land', 'Land'), ('Commercial', 'Commercial')], validators=[DataRequired()])
    size = FloatField('Size (sqm)', validators=[DataRequired()])
    bedrooms = FloatField('Bedrooms')
    bathrooms = FloatField('Bathrooms')
    city = StringField('City')
    address = StringField('Address')
    latitude = FloatField('Latitude')
    longitude = FloatField('Longitude')
    images = MultipleFileField('Property Images', validators=[FileAllowed(['jpg', 'png', 'jpeg'])])
    submit = SubmitField('Post Property')

class SearchForm(FlaskForm):
    location = StringField('Location')
    type = SelectField('Type', choices=[('', 'Any'), ('Villa', 'Villa'), ('Apartment', 'Apartment'), ('Land', 'Land')], default='')
    min_price = FloatField('Min Price')
    max_price = FloatField('Max Price')
    submit = SubmitField('Search')

class SettingsProfileForm(FlaskForm):
    full_name = StringField('Full Name', validators=[Length(max=100)])
    phone = StringField('Phone Number', validators=[Length(max=20)])
    profile_image = FileField('Profile Image', validators=[FileAllowed(['jpg', 'png', 'jpeg'])])
    submit_profile = SubmitField('Save Profile')

class SettingsSecurityForm(FlaskForm):
    current_password = PasswordField('Current Password', validators=[DataRequired()])
    new_password = PasswordField('New Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('new_password')])
    submit_security = SubmitField('Update Password')

class SettingsPreferencesForm(FlaskForm):
    preferred_language = SelectField('Language', choices=[('en', 'English'), ('ar', 'Arabic')])
    theme_mode = SelectField('Theme', choices=[('light', 'Light Mode'), ('dark', 'Dark Mode')])
    submit_preferences = SubmitField('Save Preferences')
