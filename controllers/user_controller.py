import httplib2
import json

from flask import current_app, session
from sqlalchemy import and_

from models.base import db_session
from models.auth import Auth
from models.user import User
from models.user_auth import UserAuth

from utils.config_utils import load_config
from utils.get_from import get_from

class UserController:
    def get_current_user_id(self):
        user_id = None
        if 'user' in session:
            user_id = session['user']['user_id']
        return user_id

    def get_current_user(self):
        user_id = klass.get_current_user_id()
        user = None
        if user_id:
            user = db_session.query(User).filter(User.user_id==user_id).first()
        return user

    def _request_user_info(self, credentials):
        """
        Makes an HTTP request to the Google+ API to retrieve the user's basic
        profile information, including full name and photo, and stores it in the
        Flask session.
        """
        http = httplib2.Http()
        credentials.authorize(http)
        resp, content = http.request('https://www.googleapis.com/plus/v1/people/me')

        if resp.status != 200:
            current_app.logger.error(
                "Error while obtaining user profile: \n%s: %s", resp, content)
            return None
        session['profile'] = json.loads(content.decode('utf-8'))

        google_auth_id = session['profile']['id']
        username = session['profile']['displayName']
        email = session['profile']['emails'][0]['value']
        first_name = get_from(session, ['profile', 'name', 'givenName'])
        last_name = get_from(session, ['profile', 'name', 'familyName'])
        image_url = get_from(session, ['profile', 'image', 'url'])

        row_user_auth = db_session.query(UserAuth).filter(
            and_(
                UserAuth.auth_key==Auth.GOOGLE,
                UserAuth.auth_id==google_auth_id
            )
        ).first()
        if not row_user_auth:
            row_user = User(
                first_name = first_name,
                last_name = last_name,
                username = username,
                email = email,
                image_url = image_url
            )
            db_session.add(row_user)
            db_session.commit()

            row_user_auth = UserAuth(
                user_id=row_user.user_id,
                auth_key=Auth.GOOGLE,
                auth_id=google_auth_id
            )
            db_session.add(row_user_auth)
            db_session.commit()
        else:
            row_user = row_user_auth.user
            row_user.first_name = first_name
            row_user.last_name = last_name
            row_user.username = username
            row_user.email = email
            row_user.image_url = image_url
            db_session.merge(row_user)
            db_session.commit()

        session['user'] = {
            'user_id': row_user.user_id,
            'username': row_user.username,
            'email': row_user.email,
            'first_name': row_user.first_name,
            'last_name': row_user.last_name,
            'image_url': row_user.image_url
        }