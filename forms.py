from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (StringField, PasswordField, SubmitField, BooleanField,
                     TextAreaField, FloatField, SelectField, MultipleFileField,
                     IntegerField)
from wtforms.validators import (DataRequired, Length, Email, EqualTo,
                                ValidationError, Optional, NumberRange)
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

class ProjectForm(FlaskForm):
    """
    نموذج إنشاء مشروع جديد (Project)
    المشروع = حاوية لعدَّة وحدات (شقق، فلل، تاون هاوس...) في موقع واحد.
    """
    name = StringField('Project Name', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('Project Description', validators=[DataRequired()])
    developer = StringField('Developer', validators=[Optional(), Length(max=100)])
    location = StringField('Location', validators=[DataRequired()])
    city = StringField('City', validators=[Optional()])
    address = StringField('Address', validators=[Optional()])
    completion_date = StringField('Expected Completion (e.g. Q4 2027)', validators=[Optional()])
    starting_price = FloatField('Starting Price (OMR)', validators=[DataRequired()])
    total_units = IntegerField('Total Units Planned', validators=[Optional(), NumberRange(min=1)])
    investment_omr = FloatField('Total Investment (OMR)', validators=[Optional()])
    latitude = FloatField('Latitude', validators=[Optional()])
    longitude = FloatField('Longitude', validators=[Optional()])
    status = SelectField('Project Status', choices=[
        ('available',          'Available — Now Selling'),
        ('under_construction', 'Under Construction'),
        ('off_plan',           'Off-Plan / Pre-Launch'),
    ], default='under_construction')
    images = MultipleFileField('Project Images', validators=[FileAllowed(['jpg', 'png', 'jpeg'])])
    submit = SubmitField('Create Project')

class UnitForm(FlaskForm):
    """
    نموذج إضافة وحدة (Unit) داخل مشروع موجود.
    عند الإضافة: location و city و agent تَرِث من المشروع تلقائياً.
    """
    title = StringField('Unit Title (e.g. "Type A - 2BR")', validators=[DataRequired()])
    description = TextAreaField('Unit Description', validators=[DataRequired()])
    type = SelectField('Unit Type', choices=[
        ('Villa', 'Villa'),
        ('Apartment', 'Apartment'),
        ('Townhouse', 'Townhouse'),
        ('Penthouse', 'Penthouse'),
        ('Studio', 'Studio'),
    ], validators=[DataRequired()])
    price = FloatField('Price (OMR)', validators=[DataRequired()])
    size = FloatField('Size (sqm)', validators=[DataRequired()])
    bedrooms = IntegerField('Bedrooms', validators=[Optional()])
    bathrooms = IntegerField('Bathrooms', validators=[Optional()])
    floor = IntegerField('Floor', validators=[Optional()])
    quantity = IntegerField('How many units of this type?',
                           validators=[Optional(), NumberRange(min=1, max=200)],
                           default=1)
    images = MultipleFileField('Unit Images', validators=[FileAllowed(['jpg', 'png', 'jpeg'])])
    submit = SubmitField('Add Unit to Project')

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
