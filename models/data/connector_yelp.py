import argparse
import datetime
import json
import os

from sqlalchemy import and_, not_
from yelpapi import YelpAPI


from models.base import db_session
from models.connector_event import ConnectorEvent
from models.event import Event
from models.tag import Tag
from utils.get_from import get_from

class ConnectorYelp(ConnectorEvent):
  TYPE = "Yelp"

  def __init__(self):
    api_key = os.getenv('YELP_API_KEY', None)
    if api_key is None:
      with open("config/secrets/api_keys.json", "r") as f:
        api_key = json.load(f)[self.TYPE]["api_key"]

    self.api = YelpAPI(api_key)

  def extract(self, name):
    events = Event.query.filter(
      ~(Event.primary_type == Tag.TVM)
    )

    if name is not None:
      events = events.filter(Event.name == name)

    events = events.order_by(Event.event_id)

    for row_event in events:
      search_results = None
      b_details = None

      if not search_results:
        kwargs = {
          'name': row_event.name,
          'address1': row_event.address,
          'city': row_event.city,
          'state': row_event.state
        }
        print(" | ".join(["{}: \"{}\"".format(k,v) for k,v in kwargs.items()]))

        try:
          search_results = self.api.business_match_query(
            country = "US",
            **kwargs
          )
        except Exception as e:
          print("business_match_query: {}".format(e))
          print(row_event)

      if not search_results:
        try:
          term = " ".join([row_event.name, row_event.city, row_event.state])
          location = " ".join([row_event.city, row_event.state])

          kwargs = {
            'term': term,
            'location': location
          }
          print(" | ".join(["{}: \"{}\"".format(k,v) for k,v in kwargs.items()]))

          search_results = self.api.search_query(
            limit = 1,
            **kwargs
          )
        except Exception as e:
          print("search_query: {}".format(e))
          print(row_event)

      if search_results:
        for r in search_results['businesses']:
          b_details = self.api.business_query(id = r['id'])
          
          row_event.update_meta(self.TYPE, {**r, **b_details})
          db_session.merge(row_event)
          db_session.commit()
      yield row_event.name, b_details

if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument('--purge', action="store_true")
  parser.add_argument('--name', action="store")
  group = parser.add_mutually_exclusive_group()
  args = vars(parser.parse_args())

  e = ConnectorYelp()
  e.sync(args)

# {
#   "id": "IRD_9JUjR-06zztisuTdAA",
#   "alias": "akikos-restaurant-san-francisco",
#   "name": "Akiko's Restaurant",
#   "image_url": "https://s3-media2.fl.yelpcdn.com/bphoto/XJBfe68tQbZeueKmOgYJIw/o.jpg",
#   "is_claimed": true,
#   "is_closed": false,
#   "url": "https://www.yelp.com/biz/akikos-restaurant-san-francisco?adjust_creative=yX9xMdNvnSHLOH2NSp4ITw&utm_campaign=yelp_api_v3&utm_medium=api_v3_business_lookup&utm_source=yX9xMdNvnSHLOH2NSp4ITw",
#   "phone": "+14153973218",
#   "display_phone": "(415) 397-3218",
#   "review_count": 1902,
#   "categories": [
#       {
#           "alias": "sushi",
#           "title": "Sushi Bars"
#       },
#       {
#           "alias": "japanese",
#           "title": "Japanese"
#       }
#   ],
#   "rating": 4.0,
#   "location": {
#       "address1": "431 Bush St",
#       "address2": "",
#       "address3": "",
#       "city": "San Francisco",
#       "zip_code": "94108",
#       "country": "US",
#       "state": "CA",
#       "display_address": [
#           "431 Bush St",
#           "San Francisco, CA 94108"
#       ],
#       "cross_streets": "Claude Ln & Mark Ln"
#   },
#   "coordinates": {
#       "latitude": 37.790582,
#       "longitude": -122.404653
#   },
#   "photos": [
#       "https://s3-media2.fl.yelpcdn.com/bphoto/XJBfe68tQbZeueKmOgYJIw/o.jpg",
#       "https://s3-media2.fl.yelpcdn.com/bphoto/at0uAHeEZ6r90-Cunqyswg/o.jpg",
#       "https://s3-media4.fl.yelpcdn.com/bphoto/FONu0_Cd-IKmjWV3GBuv8w/o.jpg"
#   ],
#   "price": "$$$",
#   "hours": [
#       {
#           "open": [
#               {
#                   "is_overnight": false,
#                   "start": "1730",
#                   "end": "2030",
#                   "day": 1
#               },
#               {
#                   "is_overnight": false,
#                   "start": "1730",
#                   "end": "2030",
#                   "day": 2
#               },
#               {
#                   "is_overnight": false,
#                   "start": "1730",
#                   "end": "2030",
#                   "day": 4
#               },
#               {
#                   "is_overnight": false,
#                   "start": "1730",
#                   "end": "2030",
#                   "day": 5
#               }
#           ],
#           "hours_type": "REGULAR",
#           "is_open_now": false
#       }
#   ],
#   "transactions": [
#       "delivery"
#   ]
# }