"""
Example usage:

>>> beeminder
lists existing goals
>>> beeminder --manual
lists only manually updatable goals
>>> beeminder books
updates; asks for values
>>> beeminder books 1
updates; asks for description
>>> beeminder books 1 "#PlasmaWaves"
updates; asks for nothing
>>> beeminder jrnl
this is an api goal; checks for registered handlers, applies them; can be called via systemctl assuming secrets are provided...
>>> beeminder todoist
this is an external goal; displays useful information
"""


#!/usr/bin/env python
import requests
from datetime import datetime
import click
import os

username = os.environ["BEEMINDER_USERNAME"]
auth = {"username":username,"auth_token":os.environ["BEEMINDER_TOKEN"]}

@click.command()
def show_timings():
    """
    Display timings for beeminder goals
    """
    url = f"https://www.beeminder.com/api/v1/users/{username}/goals.json"
    r = requests.get(url, params=auth).json()
    for goal in sorted(r, key = lambda x: x['losedate']):
        url = f"https://www.beeminder.com/api/v1/users/{username}/goals/{goal}.json"
        ts = datetime.utcfromtimestamp(goal['losedate']).strftime('%Y-%m-%d %H:%M:%S')
        print(f"{goal['slug'].upper():18}{goal['limsum']:27} derails at {ts:25}{goal['title']}")

if __name__ == '__main__':
    show_timings()
