import os
import re

COMMON_PASSWORDS_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'common_passwords.txt')

def load_common_passwords() -> set:
    if not os.path.exists(COMMON_PASSWORDS_FILE):
        return set()
    with open(COMMON_PASSWORDS_FILE, 'r', encoding='utf-8') as f:
        return {line.strip().lower() for line in f if line.strip()}

COMMON_PASSWORDS = load_common_passwords()

def validate_password(password: str, user=None, email: str = None, full_name: str = None) -> tuple[bool, list[str]]:
    """
    Validates a password against the security policy (Chapter 3 §3.7.3).
    Returns a tuple of (is_valid, list_of_errors).
    """
    errors = []
    
    # Check minimum length
    if len(password) < 12:
        errors.append("Password must be at least 12 characters long. / يجب أن تتكون كلمة المرور من 12 حرفاً على الأقل.")
        
    # Check uppercase
    if not re.search(r'[A-Z]', password):
        errors.append("Password must contain at least one uppercase letter. / يجب أن تحتوي كلمة المرور على حرف كبير واحد على الأقل.")
        
    # Check lowercase
    if not re.search(r'[a-z]', password):
        errors.append("Password must contain at least one lowercase letter. / يجب أن تحتوي كلمة المرور على حرف صغير واحد على الأقل.")
        
    # Check digit
    if not re.search(r'\d', password):
        errors.append("Password must contain at least one digit. / يجب أن تحتوي كلمة المرور على رقم واحد على الأقل.")
        
    # Check special character
    if not re.search(r'[!@#$%^&*(),.?":{}|<>\-_\+=\[\]\\\'/`~]', password):
        errors.append("Password must contain at least one special character. / يجب أن تحتوي كلمة المرور على رمز خاص واحد على الأقل.")
        
    # Extract identifiers from user object if passed instead of raw strings
    if user:
        if not email and hasattr(user, 'email'):
            email = user.email
        if not full_name and hasattr(user, 'full_name'):
            full_name = user.full_name
        if not full_name and hasattr(user, 'username'):
            full_name = user.username

    password_lower = password.lower()

    # Check email local-part
    if email and '@' in email:
        local_part = email.split('@')[0].lower()
        if len(local_part) > 2 and local_part in password_lower:
            errors.append("Password cannot contain the local part of your email. / لا يمكن أن تحتوي كلمة المرور على جزء من بريدك الإلكتروني.")
            
    # Check full name / username
    if full_name:
        for name_part in full_name.lower().split():
            if len(name_part) > 2 and name_part in password_lower:
                errors.append("Password cannot contain your name or username. / لا يمكن أن تحتوي كلمة المرور على اسمك أو اسم المستخدم الخاص بك.")
                break

    # Check common breached passwords
    if password_lower in COMMON_PASSWORDS:
        errors.append("This password is too common and has been found in data breaches. Please choose a unique one. / كلمة المرور هذه شائعة جداً ومخترقة. يرجى اختيار كلمة مرور فريدة.")

    return len(errors) == 0, errors
