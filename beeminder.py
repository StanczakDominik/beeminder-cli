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
import math
from random import choice
import webbrowser

username = os.environ["BEEMINDER_USERNAME"]
beeminder_auth_token = os.environ["BEEMINDER_TOKEN"]


def increment_beeminder(desc, beeminder_goal, value=1):
    data = {"value": value, "auth_token": beeminder_auth_token, "comment": desc}

    response = requests.post(
        f"https://www.beeminder.com/api/v1/users/{username}/goals/{beeminder_goal}/datapoints.json",
        data=data,
    )
    return response


class Datapoint:
    def __init__(self, **datapoint):
        self.value = datapoint["value"]
        self.comment = datapoint["comment"]
        self.timestamp = datapoint["timestamp"]
        self.canonical = datapoint["canonical"]
        self.dictionary = datapoint
        self.datetime = datetime.fromtimestamp(self.timestamp)

    @property
    def is_updated_today(self):
        return self.datetime.date() == datetime.now().date()


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
        self.headsum = goal["headsum"]
        self.last_datapoint = Datapoint(**goal["last_datapoint"])
        self.dictionary = goal

    @property
    def formatted_losedate(self):
        date = datetime.utcfromtimestamp(self.losedate)
        return date.strftime("%Y-%m-%d %H:%M:%S")

    @property
    def summary(self):
        ts = self.formatted_losedate
        return f"{self.slug.upper():25}{self.limsum:27}{self.last_datapoint.canonical}"

    @property
    def is_do_less(self):
        return self.type == "drinker"  # and a fiend

    @property
    def is_manual(self):
        return self.autodata is None

    @property
    def is_updated_today(self):
        return self.last_datapoint.is_updated_today

    def __repr__(self, *args, **kwargs):
        return f"{self.__class__.__name__}({self.slug})"

    @property
    def default_description(self):
        return f"Updated from {self} at {datetime.now()}"

    def update(self, value, description=None):
        if value is None:
            raise ValueError("You need to provide an update value!")
        if description is None:
            description = self.default_description
        click.echo(f"Updating {self} with {value} and description {description}")
        return increment_beeminder(description, self.slug, value)

    def show_web(self):
        goal_url = f"https://www.beeminder.com/{username}/{self.slug}"
        webbrowser.open(goal_url)


class RemoteApiGoal(Goal):
    def update(self, *args, **kwargs):
        click.echo(
            "This is a remote goal, I can't update it from here.\n"
            "I'm going to ignore this and just call for a remote update."
        )
        url = f"https://www.beeminder.com/api/v1/users/{username}/goals/{self.slug}/refresh_graph.json"
        r = requests.get(url, params=auth)


class TogglGoal(RemoteApiGoal):
    @property
    def is_updated_today(self):
        return not (self.last_datapoint.value == 0.0)


auth = {"username": username, "auth_token": os.environ["BEEMINDER_TOKEN"]}
all_goals = []
url = f"https://www.beeminder.com/api/v1/users/{username}/goals.json"
r = requests.get(url, params=auth).json()


def create_goal(**goal):
    if goal["autodata"] is None or goal["autodata"] == "api":
        return Goal(**goal)
    elif goal["autodata"] == "toggl":
        return TogglGoal(**goal)
    elif goal["autodata"] != "api":
        return RemoteApiGoal(**goal)
    else:
        raise ValueError(f"What autodata is {goal['autodata']}?")


for goal in r:
    goal = create_goal(**goal)
    all_goals.append(goal)


@click.group(invoke_without_command=True)
@click.option("-m/-nm", "--manual/--no-manual", default=None)
@click.option("-dl/-ndl", "--do-less/--no-do-less", default=None)
@click.option("-dt/-ndt", "--done-today/--not-done-today", default=None)
@click.option("-n", type=int)
@click.option("-r", "--random", is_flag=True)
@click.pass_context
def beeminder(ctx, manual=None, do_less=None, done_today=None, n=None, random=False):
    """Display timings for beeminder goals."""
    if ctx.invoked_subcommand is None:
        goals = all_goals.copy()
        if manual is not None:
            goals = filter(lambda g: g.is_manual, goals)
        if do_less is not None:
            goals = filter(lambda g: not g.is_do_less, goals)
        if done_today is not None:
            goals = filter(lambda g: g.is_updated_today == done_today, goals)
        goals = sorted(goals, key=lambda g: g.losedate)

        if n is not None:
            n = int(n)
            goals = goals[:n]

        if random:
            click.echo(choice(goals).summary)
            return

        for goal in goals:
            click.echo(goal.summary)
    else:
        pass


def pick_goal(slug):
    return next(filter(lambda g: g.slug == slug, all_goals))


@beeminder.command()
@click.argument("goal")
def show(goal):
    goal = pick_goal(goal)
    click.echo(goal.summary)


@beeminder.command()
@click.option("-d", "--description", default=None)
@click.argument("goal", type=str)
@click.argument("update_value", type=float, required=False)
def update(goal, update_value, description=None):
    goal = pick_goal(goal)
    goal.update(update_value, description)


@beeminder.command()
@click.argument("goal", type=str)
def web(goal):
    goal = pick_goal(goal)
    goal.show_web()


@beeminder.command()
def debug():
    breakpoint()


if __name__ == "__main__":
    beeminder()
