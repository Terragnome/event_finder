import json

def load_config(path):
	with open(path) as f:
		return json.loads(f.read())