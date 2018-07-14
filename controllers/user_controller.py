import httplib2
import json

from flask import current_app, session
from sqlalchemy import and_, or_

from models.base import db_session
from models.auth import Auth
from models.user import User
from models.user_auth import UserAuth

from utils.config_utils import load_config
from utils.get_from import get_from

class UserController:
	def _logout(self):
		from app import oauth2
		if 'user' in session:
			del session['user']
		session.modified = True
		oauth2.storage.delete()

	def _request_user_info(self, credentials):
		http = httplib2.Http()
		credentials.authorize(http)
		resp, content = http.request('https://www.googleapis.com/plus/v1/people/me')

		if resp.status != 200:
			current_app.logger.error(
				"Error while obtaining user profile: \n%s: %s",
				resp,
				content
			)
			return None

		profile = json.loads(content.decode('utf-8'))

		google_auth_id = profile['id']
		email = profile['emails'][0]['value']
		user = {
			'username': email.split("@")[0],
			'email': email,
			'display_name': profile['displayName'],
			'first_name': get_from(profile, ['name', 'givenName']),
			'last_name': get_from(profile, ['name', 'familyName']),
			'image_url': get_from(profile, ['image', 'url']),
		}

		row_user_auth = db_session.query(UserAuth).filter(
			and_(
				UserAuth.auth_key==Auth.GOOGLE,
				UserAuth.auth_id==google_auth_id
			)
		).first()
		if not row_user_auth:
			row_user = User(**user)
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
			for k,v in user.items():
				setattr(row_user, k, v)
			db_session.merge(row_user)
			db_session.commit()

		session['user'] = row_user.to_json()

	@property
	def current_user_id(self):
		user_id = None
		if 'user' in session:
			user_id = session['user']['user_id']
		return user_id

	@property
	def current_user(self):
		user_id = self.current_user_id
		user = None
		if user_id:
			user = db_session.query(User).filter(User.user_id == user_id).first()
		return user

	def get_user(self, identifier):
		if identifier.__class__ is int:
			user = db_session.query(User).filter(User.user_id==identifier).first()
		else:
			user = db_session.query(User).filter(User.username==identifier).first()
		return user

	def get_users(self):
		return db_session.query(User).all()