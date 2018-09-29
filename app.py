import functools
import json
import os

from flask import Flask
from flask import redirect, render_template, request
from flask import url_for
from flask_session import Session
from oauth2client.contrib.flask_util import UserOAuth2
import redis

from config.app_config import app_config

from controllers.event_controller import EventController
from controllers.user_controller import UserController
from helpers.jinja_helper import add_url_params, filter_url_params, remove_url_params
from models.base import db_session
from models.block import Block
from models.follow import Follow
from models.tag import Tag

from utils.config_utils import load_config

app = Flask(__name__)
app.config.update(**app_config)
app.config['PROJECT_ID'] = "eventfinder-208801"
app.config['GOOGLE_OAUTH2_CLIENT_SECRETS_FILE'] = 'config/google_auth.json'
app.config['SESSION_TYPE'] = 'redis'
app.config['SESSION_REDIS'] = redis.from_url('redis://redis:6379/')
app.config['TEMPLATES_AUTO_RELOAD'] = True

app.jinja_env.globals.update(add_url_params=add_url_params)
app.jinja_env.globals.update(filter_url_params=filter_url_params)
app.jinja_env.globals.update(remove_url_params=remove_url_params)

sess = Session()
sess.init_app(app)

oauth2_scopes = ["profile", "email"]
oauth2 = UserOAuth2()
oauth2.init_app(
  app,
  scopes = oauth2_scopes,
  prompt = 'select_account',
  authorize_callback=UserController()._request_user_info
)

param_to_kwarg = {
  'p': 'page',
  'q': 'query',
  't': 'tag'
}

TEMPLATE_MAIN = "main.html"
TEMPLATE_BLOCKING = "_blocking.html"
TEMPLATE_FOLLOWERS = "_followers.html"
TEMPLATE_FOLLOWING = "_following.html"
TEMPLATE_EVENT = "_event.html"
TEMPLATE_EVENTS = "_events.html"
TEMPLATE_EVENTS_LIST = "_events_list.html"
TEMPLATE_USER = "_user.html"
TEMPLATE_USERS = "_users.html"

@app.teardown_appcontext
def shutdown_session(exception=None):
    db_session.remove()

def _render_events_list(
  request,
  events,
  vargs,
  scroll=False,
  template=TEMPLATE_EVENTS
):
  if request.is_xhr:
    if scroll:
      template = TEMPLATE_EVENTS_LIST
      if not events: return ''
    return render_template(template, vargs=vargs, **vargs)
  return render_template(TEMPLATE_MAIN, template=template, vargs=vargs, **vargs)

def parse_url_params(fn):
  @functools.wraps(fn)
  def decorated_fn(*args, **kwargs):
    for param,kw in param_to_kwarg.items():
      v = request.args.get(param, default=None, type=str)
      if param in kwargs: del kwargs[param]
      if v not in (None, ''): kwargs[kw] = v

    raw_cities = request.args.get('cities', default=None, type=str)
    if raw_cities:
      cities = set(raw_cities.split(','))
      kwargs['cities'] = cities
    return fn(*args, **kwargs)
  return decorated_fn

def parse_url_for(*args, **kwargs):
  for param,kw in param_to_kwarg.items():
    if kw in kwargs:
      v = kwargs[kw]
      del kwargs[kw]
      kwargs[param] = v

  if 'cities' in kwargs:
    if kwargs['cities']:
      kwargs['cities'] = ','.join(kwargs['cities'])

  return url_for(*args, **kwargs)

def paginated(fn):
  @functools.wraps(fn)
  def decorated_fn(*args, **kwargs):
    page = request.args.get('p', default=1, type=int)
    scroll = request.args.get('scroll', default=False, type=bool)
    
    if page <= 1:
        page = 1
        prev_page = None
    else:
        prev_page = page-1
    next_page = page+1

    if 'p' in kwargs: del kwargs['p']
    if 'scroll' in kwargs: del kwargs['scroll']
    if 'prev_page_url' in kwargs: del kwargs['prev_page_url']
    if 'next_page_url' in kwargs: del kwargs['next_page_url']

    kwargs['page'] = prev_page
    prev_page_url = parse_url_for(fn.__name__, *args, **kwargs)
    kwargs['page'] = next_page
    next_page_url = parse_url_for(fn.__name__, *args, **kwargs)

    kwargs['page'] = page
    kwargs['scroll'] = scroll
    kwargs['next_page_url'] = next_page_url
    kwargs['prev_page_url'] = prev_page_url

    return fn(*args, **kwargs)
  return decorated_fn

@app.route("/login")
def login():
  return redirect(request.referrer or '/')

@app.route("/logout")
def logout():
  UserController()._logout()
  return redirect('/')

@app.route("/blocking/", methods=['GET'])
@oauth2.required(scopes=oauth2_scopes)
def blocking():
  current_user = UserController().current_user
  blocking = UserController().get_blocking()

  template = TEMPLATE_BLOCKING

  vargs = {
    'users': blocking,
    'callback': 'blocking'
  }

  for user in blocking:
    user.is_followed = current_user.is_follows_user(user)
    user.is_blocked = current_user.is_blocks_user(user)

  if request.is_xhr:
    return render_template(template, vargs=vargs, **vargs)
  return render_template(TEMPLATE_MAIN, template=template, vargs=vargs, **vargs)

@app.route("/", methods=['GET'])
@app.route("/explore/", methods=['GET'])
@parse_url_params
@paginated
def events(
  query=None, tag=None, cities=None,
  page=1, next_page_url=None, prev_page_url=None,
  scroll=False
):
  events, sections, event_cities = EventController().get_events(
    query=query,
    tag=tag,
    cities=cities,
    page=page
  )

  for section in sections:
    kwargs = {
      'query': query,
      'cities': cities,
      'tag': section['section_name']
    }

    if section['section_name'] == Tag.MOVIES: del kwargs['cities']
    section['section_url'] = parse_url_for('events', **kwargs)

    del kwargs['tag']
    section['section_close_url'] = parse_url_for('events', **kwargs)

  vargs = {
    'events': events,
    'sections': sections,
    'cities': event_cities,
    'page': page,
    'next_page_url': next_page_url,
    'prev_page_url': prev_page_url,
  }

  return _render_events_list(request, events, vargs, scroll=scroll)

@app.route("/event/<int:event_id>/", methods=['GET'])
def event(event_id):
  event = EventController().get_event(event_id=event_id)

  if event:
    template = TEMPLATE_EVENT

    vargs = {
      'event': event
    }

    if request.is_xhr:
      return render_template(template, vargs=vargs, **vargs)
    return render_template(TEMPLATE_MAIN, template=template, vargs=vargs, **vargs)
  return redirect(request.referrer or '/')

@app.route("/event/<int:event_id>/", methods=['POST'])
@oauth2.required(scopes=oauth2_scopes)
def event_update(event_id):
  is_card = request.form.get('card') == 'true'
  go_value = request.form.get('go')

  if go_value in ('-1','2','1','0'):
    interest = str(go_value)
  else:
    interest = None

  callback = request.form.get('cb')
  if callback == "/": callback = 'events'

  event = EventController().update_event(
    event_id=event_id,
    interest=interest
  )

  if event:
    template = TEMPLATE_EVENT

    vargs = {
      'event': event,
      'card': is_card
    }

    if request.is_xhr:
      return render_template(template, vargs=vargs, **vargs)
    if callback:
      return redirect(callback)
    return render_template(TEMPLATE_MAIN, template=template, vargs=vargs, **vargs)
  return redirect(request.referrer or '/')

@app.route("/followers/", methods=['GET'])
@oauth2.required(scopes=oauth2_scopes)
def followers():
  current_user = UserController().current_user
  follower_users = UserController().get_followers()

  template = TEMPLATE_FOLLOWERS

  vargs = {
    'users': follower_users,
    'callback': 'followers'
  }

  for user in follower_users:
    user.is_followed = current_user.is_follows_user(user)
    user.is_blocked = current_user.is_blocks_user(user)

  if request.is_xhr:
    return render_template(template, vargs=vargs, **vargs)
  return render_template(TEMPLATE_MAIN, template=template, vargs=vargs, **vargs)

@app.route("/following/", methods=['GET'])
@oauth2.required(scopes=oauth2_scopes)
def following():
  current_user = UserController().current_user
  recommended_users = UserController().get_following_recommended()
  following_users = UserController().get_following()

  template = TEMPLATE_FOLLOWING

  vargs = {
    'recommended_users': recommended_users,
    'users': following_users,
    'callback': 'following'
  }

  for user in following_users:
    user.is_followed = current_user.is_follows_user(user)
    user.is_blocked = current_user.is_blocks_user(user)

  if request.is_xhr:
    return render_template(template, vargs=vargs, **vargs)
  return render_template(TEMPLATE_MAIN, template=template, vargs=vargs, **vargs)

@app.route("/events", methods=['GET'])
@oauth2.required(scopes=oauth2_scopes)
def home():
  current_user = UserController().current_user
  return user(identifier=current_user.username)

@app.route("/user/<identifier>/", methods=['GET'])
@parse_url_params
@paginated
def user(
  identifier,
  query=None, tag=None, cities=None,
  page=1, next_page_url=None, prev_page_url=None,
  scroll=False
):
  current_user = UserController().current_user
  current_user_id = UserController().current_user_id

  user = UserController().get_user(identifier)

  if user:
    events = []
    sections = []
    cities = []
    if not Block.blocks(user.user_id, current_user_id):
      events, sections, event_cities = EventController().get_events_for_user_by_interested(
        user=user,
        query=query,
        tag=tag,
        cities=cities,
        interested=True,
        page=page
      )
      for section in sections:
        kwargs = {
          'identifier': identifier,
          'query': query,
          'cities': cities,
          'tag': section['section_name']
        }

        if section['section_name'] == Tag.MOVIES: del kwargs['cities']
        section['section_url'] = parse_url_for('user', **kwargs)

        del kwargs['tag']
        section['section_close_url'] = parse_url_for('user', **kwargs)

    vargs = {
      'current_user': current_user,
      'events': events,
      'sections': sections,
      'cities': event_cities,
      'page': page,
      'next_page_url': next_page_url,
      'prev_page_url': prev_page_url
    }

    if user.user_id == current_user_id:
      return _render_events_list(request, events, vargs, scroll=scroll)
    else:
      vargs['user'] = user

      if current_user:
        user.is_followed = current_user.is_follows_user(user)
        user.is_blocked = current_user.is_blocks_user(user)

      return _render_events_list(request, events, vargs, template=TEMPLATE_USER, scroll=scroll)
  return redirect(request.referrer or '/')    

@app.route("/user/<identifier>/", methods=['POST'])
@oauth2.required(scopes=oauth2_scopes)
def user_action(identifier):
  current_user = UserController().current_user
  current_user_id = UserController().current_user_id

  action = request.form.get('action')
  active = request.form.get('active') == 'true'
  callback = request.form.get('cb')

  if action == 'block':
    u = UserController().block_user(identifier, active)
  elif action == 'follow':
    u = UserController().follow_user(identifier, active)

  if u:
    events = []
    if not Block.blocks(u.user_id, current_user_id):
      events = EventController().get_events_for_user_by_interested(
        user=u,
        interested=True
      )

    # TODO: Replace this with something generic but safe
    if 'blocking' in callback:
      return blocking()
    elif 'followers' in callback:
      return followers()
    elif 'following' in callback:
      return following()
    elif 'events' in callback:
      return events()
    elif 'user':
      return user(identifier=identifier)

  return redirect(request.referrer or '/')

if __name__ == '__main__':
  app.run(debug=True, host='0.0.0.0', port=5000)