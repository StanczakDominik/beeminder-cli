#!/usr/bin/env python
"""Utility script for CLI Beeminder usage.

Example usage/API design doc draft:

>>> beeminder
lists existing goals
>>> beeminder --manual
lists only manually updatable goals
>>> beeminder books
updates; asks for values
>>> beeminder books 1
updates; default description
>>> beeminder books 1 "#PlasmaWaves"
updates; asks for nothing
>>> beeminder jrnl
this is an api goal; checks for registered handlers, applies them;
can be called via systemctl assuming secrets are provided...
>>> beeminder todoist
this is an external goal; displays useful information
>>> beeminder todoist edit
"""
import requests
from datetime import datetime
import click
import os
import functools

username = os.environ["BEEMINDER_USERNAME"]
beeminder_auth_token = os.environ["BEEMINDER_TOKEN"]


def increment_beeminder(desc, beeminder_goal, value=1):
    data = {"value": value, "auth_token": beeminder_auth_token, "comment": desc}

    response = requests.post(
        f"https://www.beeminder.com/api/v1/users/{username}/goals/{beeminder_goal}/datapoints.json",
        data=data,
    )
    return response


class Goal:
    """Wraps a Beeminder goal."""

    def __init__(self, **goal):
        """TODO."""
        self.losedate = goal["losedate"]
        self.slug = goal["slug"]
        self.limsum = goal["limsum"]
        self.title = goal["title"]
        self.autodata = goal["autodata"]
        self.type = goal["goal_type"]
        self.dictionary = goal

    @property
    def formatted_losedate(self):
        date = datetime.utcfromtimestamp(self.losedate)
        return date.strftime("%Y-%m-%d %H:%M:%S")

    @property
    def summary(self):
        ts = self.formatted_losedate
        return f"{self.slug.upper():18}{self.limsum:27} derails at {ts:25}{self.title}"

    @property
    def is_do_less(self):
        return self.type == "drinker"  # and a fiend

    @property
    def is_manual(self):
        return self.autodata is None

    def __repr__(self, *args, **kwargs):
        return f"Goal({self.slug})"

    @property
    def default_description(self):
        return f"Updated from {self} at {datetime.now()}"

    def update(self, value, description=None):
        if description is None:
            description = self.default_description
        click.echo(f"Updating {self} with {value} and description {description}")
        return increment_beeminder(description, self.slug, value)


auth = {"username": username, "auth_token": os.environ["BEEMINDER_TOKEN"]}
all_goals = []
url = f"https://www.beeminder.com/api/v1/users/{username}/goals.json"
r = requests.get(url, params=auth).json()

for goal in r:
    goal = Goal(**goal)
    all_goals.append(goal)


@click.group(invoke_without_command=True)
@click.option("-m", "--manual", is_flag=True)
@click.option("-ndl", "--no-do-less", is_flag=True)
@click.pass_context
def beeminder(ctx, manual=False, no_do_less=False):
    """Display timings for beeminder goals."""
    if ctx.invoked_subcommand is None:
        goals = all_goals.copy()
        if manual:
            goals = filter(lambda g: g.is_manual, goals)
        if no_do_less:
            goals = filter(lambda g: not g.is_do_less, goals)
        for goal in sorted(goals, key=lambda g: g.losedate):
            click.echo(goal.summary)
    else:
        pass


@beeminder.command()
@click.argument("goal")
def show(goal):
    goal = next(filter(lambda g: g.slug == goal, all_goals))
    click.echo(goal.summary)


@beeminder.command()
@click.option("-d", "--description", default=None)
@click.argument("goal", type=str)
@click.argument("update_value", type=float)
def update(goal, update_value, description=None):
    goal = next(filter(lambda g: g.slug == goal, all_goals))

    goal.update(update_value, description)


if __name__ == "__main__":
    beeminder()
