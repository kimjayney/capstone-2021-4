# project/users/views.py

# IMPORTS
from flask import render_template, Blueprint, request, redirect, url_for, flash, Markup, abort, make_response, jsonify
from sqlalchemy.exc import IntegrityError
from flask_login import login_user, current_user, login_required, logout_user
from itsdangerous import URLSafeTimedSerializer
from threading import Thread
from flask_mail import Message
from datetime import datetime, timedelta

from .forms import RegisterForm, LoginForm, EmailForm, PasswordForm
from project import app, db, mail
from project.models import User, Balance
import project.cloud.views as cloud_env

# CONFIG
users_blueprint = Blueprint('users', __name__, template_folder='templates')

# HELPERS
def send_async_email(msg):
    with app.app_context():  
        try:
            mail.send(msg)
            print(msg)
        except Exception as e:
            print("ERROR")
            print(e)


def send_email(subject, recipients, html_body):
    msg = Message(subject, recipients=recipients)
    msg.html = html_body
    thr = Thread(target=send_async_email, args=[msg])
    thr.start()


def send_confirmation_email(user_email):
    confirm_serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

    confirm_url = url_for(
        'users.confirm_email',
        token=confirm_serializer.dumps(user_email, salt='email-confirmation-salt'),
        _external=True)

    html = render_template(
        'email_confirmation.html',
        confirm_url=confirm_url)
    print("send to {}".format(user_email))
    send_email('Confirm Your Email Address', [user_email], html)


def send_password_reset_email(user_email):
    password_reset_serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

    password_reset_url = url_for(
        'users.reset_with_token',
        token=password_reset_serializer.dumps(user_email, salt='password-reset-salt'),
        _external=True)

    html = render_template(
        'email_password_reset.html',
        password_reset_url=password_reset_url)

    send_email('Password Reset Requested', [user_email], html)


# ROUTES
@users_blueprint.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm(request.form)
    if request.method == 'POST':
        if form.validate_on_submit():
            try:
                new_user = User(form.email.data, form.password.data)
                new_user.authenticated = True
                db.session.add(new_user)
                db.session.commit()
                send_confirmation_email(new_user.email)

                # if request.args("rest") == "true":
                #     auth_token = new_user.encode_auth_token(user.id)
                #     responseObject = {
                #         'status': 'success',
                #         'message': 'Successfully registered.',
                #         'auth_token': auth_token.decode()
                #     }
                #     return make_response(jsonify(responseObject)), 201

                message = Markup(
                    "<strong>Success!</strong> Thanks for registering. Please check your email to confirm your email address.")
                flash(message, 'success')
                return redirect(url_for('home'))
                
            except IntegrityError:
                db.session.rollback()
                message = Markup(
                    "<strong>Error!</strong> Unable to process registration.")
                flash(message, 'danger')
    return render_template('register.html', form=form)

@users_blueprint.route('/token', methods=["POST"])
def token_login():
    post_data = request.get_json()
    print(post_data)
    try:
        # fetch the user data
        user = User.query.filter_by(email=post_data.get('email')).first()
        if user is not None and user.is_correct_password(post_data.get('pass')):
            if user.is_email_confirmed is not True:
                user.authenticated = True
                db.session.add(user)
                db.session.commit()
                login_user(user)
                return redirect(url_for('users.resend_email_confirmation'), )
            if user.is_email_confirmed is True:
                auth_token = user.encode_auth_token(user.id)
                if auth_token:
                    responseObject = {
                        'status': 'success',
                        'message': 'Successfully logged in.',
                        'auth_token': auth_token.decode()
                    }
                    return make_response(jsonify(responseObject)), 200
        else:
            responseObject = {
                'status': 'fail',
                'message': 'account incorrect',
            }
            return make_response(jsonify(responseObject)), 500
    except Exception as e:
        print(e)
        responseObject = {
            'status': 'fail',
            'message': 'Try again'
        }
        return make_response(jsonify(responseObject)), 500
     

@users_blueprint.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm(request.form)
    if request.method == 'POST':
        if form.validate_on_submit():
            user = User.query.filter_by(email=form.email.data).first()
            if user is not None and user.is_correct_password(form.password.data):
                if user.is_email_confirmed is not True:
                    user.authenticated = True
                    db.session.add(user)
                    db.session.commit()
                    login_user(user)
                    # responseObject = {
                    #     'status': 'success',
                    #     'message': 'Email is not confirmed',
                    # }
                    # return make_response(jsonify(responseObject)), 200
                    return redirect(url_for('users.resend_email_confirmation'), )

                if user.is_email_confirmed is True:
                    auth_token = user.encode_auth_token(user.id)
                    user.authenticated = True
                    user.last_logged_in = user.current_logged_in
                    user.current_logged_in = datetime.now()
                    db.session.add(user)
                    db.session.commit()
                    login_user(user)
                    # responseObject = {
                    #     'status': 'success',
                    #     'message': 'Successfully logged in.',
                    #     'auth_token': auth_token.decode()
                    # }
                    # return make_response(jsonify(responseObject)), 200
                    message = Markup(
                        "<strong>Welcome back!</strong> You are now successfully logged in.")
                    flash(message, 'success')
                    return redirect(url_for('cloud.all_clouds'))
            else:
                message = Markup(
                    "<strong>Error!</strong> Incorrect login credentials.")
                flash(message, 'danger')
    return render_template('new/login.html', form=form)


@users_blueprint.route('/user_profile', methods=['GET', 'POST'])
@login_required
def user_profile():
    return render_template('user/profile.html')


@users_blueprint.route('/confirm/<token>')
def confirm_email(token):
    try:
        confirm_serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
        email = confirm_serializer.loads(token, salt='email-confirmation-salt', max_age=3600)
    except:
        message = Markup(
            "The confirmation link is invalid or has expired.")
        flash(message, 'danger')
        return redirect(url_for('users.login'))

    user = User.query.filter_by(email=email).first()

    if user.email_confirmed:
        message = Markup(
            "Account already confirmed. Please login.")
        flash(message, 'info')
    else:
        user.email_confirmed = True
        user.email_confirmed_on = datetime.now()
        db.session.add(user)
        
        db.session.flush()  
        db.session.refresh(user)
        
        user_id = user.id
        
        
        new_user_balance = Balance(user_id)
        db.session.add(new_user_balance)
        
        if cloud_env.check_environment(user.id) == False: # cloud env init
            try:
                cloud_env.create_environment(user.id)
                message = Markup(
                    "Thank you for confirming your email address!")
            except:
                message = Markup(
                        "<strong>Error</strong>! 이메일 인증을 다시 시도해 주세요.")
                flash(message, 'danger')
                db.session.rollback()
                return redirect(url_for('home'))
                
        flash(message, 'success') 
    db.session.commit()
    return redirect(url_for('home'))


@users_blueprint.route('/reset', methods=["GET", "POST"])
def reset():
    form = EmailForm()
    if form.validate_on_submit():
        try:
            user = User.query.filter_by(email=form.email.data).first_or_404()
        except:
            message = Markup(
                "Invalid email address!")
            flash(message, 'danger')
            return render_template('password_reset_email.html', form=form)
        if user.email_confirmed:
            send_password_reset_email(user.email)
            message = Markup(
                "Please check your email for a password reset link.")
            flash(message, 'success')
        else:
            message = Markup(
                "Your email address must be confirmed before attempting a password reset.")
            flash(message, 'danger')
        return redirect(url_for('users.login'))

    return render_template('password_reset_email.html', form=form)


@users_blueprint.route('/reset/<token>', methods=["GET", "POST"])
def reset_with_token(token):
    try:
        password_reset_serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
        email = password_reset_serializer.loads(token, salt='password-reset-salt', max_age=3600)
    except:
        message = Markup(
            "The password reset link is invalid or has expired.")
        flash(message, 'danger')
        return redirect(url_for('users.login'))

    form = PasswordForm()

    if form.validate_on_submit():
        try:
            user = User.query.filter_by(email=email).first_or_404()
        except:
            message = Markup(
                "Invalid email address!")
            flash(message, 'danger')
            return redirect(url_for('users.login'))

        user.password = form.password.data
        db.session.add(user)
        db.session.commit()
        message = Markup(
            "Your password has been updated!")
        flash(message, 'success')
        return redirect(url_for('users.login'))

    return render_template('reset_password_with_token.html', form=form, token=token)


@users_blueprint.route('/admin_view_users')
@login_required
def admin_view_users():
    if current_user.role != 'admin':
        abort(403)
    else:
        users = User.query.order_by(User.id).all()
        return render_template('admin_view_users.html', users=users)


@users_blueprint.route('/admin_dashboard')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        abort(403)
    else:
        users = User.query.order_by(User.id).all()
        kpi_mau = User.query.filter(User.last_logged_in > (datetime.today() - timedelta(days=30))).count()
        kpi_total_confirmed = User.query.filter_by(email_confirmed=True).count()
        kpi_mau_percentage = (100 / kpi_total_confirmed) * kpi_mau
        return render_template('admin_dashboard.html', users=users, kpi_mau=kpi_mau, kpi_total_confirmed=kpi_total_confirmed, kpi_mau_percentage=kpi_mau_percentage)


@users_blueprint.route('/logout')
@login_required
def logout():
    user = current_user
    user.authenticated = False
    db.session.add(user)
    db.session.commit()
    logout_user()
    message = Markup("<strong>Goodbye!</strong> You are now logged out.")
    flash(message, 'info')

    auth_header = request.headers.get('Authorization')
    # if auth_header:
    #     auth_token = auth_header.split(" ")[1]
    # else:
    #     auth_token = ''
    # if auth_token:
    #     resp = User.decode_auth_token(auth_token)
    #     if not isinstance(resp, str):
    #         # mark the token as blacklisted
    #         blacklist_token = BlacklistToken(token=auth_token)
    #         try:
    #             # insert the token
    #             db.session.add(blacklist_token)
    #             db.session.commit()
    #             responseObject = {
    #                 'status': 'success',
    #                 'message': 'Successfully logged out.'
    #             }
    #             return make_response(jsonify(responseObject)), 200
    #         except Exception as e:
    #             responseObject = {
    #                 'status': 'fail',
    #                 'message': e
    #             }
    #             return make_response(jsonify(responseObject)), 200
    #     else:
    #         responseObject = {
    #             'status': 'fail',
    #             'message': resp
    #         }
    #         return make_response(jsonify(responseObject)), 401
    # else:
    #     responseObject = {
    #         'status': 'fail',
    #         'message': 'Provide a valid auth token.'
    #     }
    #     return make_response(jsonify(responseObject)), 403


    return redirect(url_for('users.login'))


@users_blueprint.route('/password_change', methods=["GET", "POST"])
@login_required
def user_password_change():
    form = PasswordForm()
    if request.method == 'POST':
        if form.validate_on_submit():
            user = current_user
            user.password = form.password.data
            db.session.add(user)
            db.session.commit()
            message = Markup(
                "Password has been updated!")
            flash(message, 'success')
            return redirect(url_for('users.user_profile'))

    return render_template('password_change.html', form=form)


@users_blueprint.route('/resend_confirmation')
@login_required
def resend_email_confirmation():
    try:
        send_confirmation_email(current_user.email)
        message = Markup(
            "Email sent to confirm your email address. Please check your inbox!")
        flash(message, 'success')
        user = current_user
        user.authenticated = False
        db.session.add(user)
        db.session.commit()
        logout_user()
    except IntegrityError:
        message = Markup(
            "Error!  Unable to send email to confirm your email address.")
        flash(message, 'danger')
        user = current_user
        user.authenticated = False
        db.session.add(user)
        db.session.commit()
        logout_user()
    return redirect(url_for('users.login'))


@users_blueprint.route('/email_change', methods=["GET", "POST"])
@login_required
def user_email_change():
    form = EmailForm()
    if request.method == 'POST':
        if form.validate_on_submit():
            try:
                user_check = User.query.filter_by(email=form.email.data).first()
                if user_check is None:
                    user = current_user
                    user.email = form.email.data
                    user.email_confirmed = False
                    user.email_confirmed_on = None
                    user.email_confirmation_sent_on = datetime.now()
                    db.session.add(user)
                    db.session.commit()
                    send_confirmation_email(user.email)
                    message = Markup(
                        "Email changed!  Please confirm your new email address (link sent to new email)")
                    flash(message, 'success')
                    return redirect(url_for('users.user_profile'))
                else:
                    message = Markup(
                        "Sorry, that email already exists!")
                    flash(message, 'danger')
            except IntegrityError:
                message = Markup(
                    "Sorry, that email already exists!")
                flash(message, 'danger')
    return render_template('email_change.html', form=form)
