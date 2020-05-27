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
from datetime import datetime, timedelta
import click
import os
import functools
import math
from random import choice
import webbrowser
import humanize
import math

__version__ = "0.1.0"

username = os.environ["BEEMINDER_USERNAME"]
beeminder_auth_token = os.environ["BEEMINDER_TOKEN"]
auth = {"username": username, "auth_token": os.environ["BEEMINDER_TOKEN"]}


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
        return self.datetime.date() >= datetime.now().date()


class Goal:
    """Wraps a Beeminder goal."""

    def __init__(self, **goal):
        """TODO."""
        if "losedate" in goal:
            self._losedate = datetime.utcfromtimestamp(goal["losedate"])
        else:
            self._losedate = None
        self.slug = goal.get("slug")
        self.limsum = goal.get("limsum")
        self.title = goal.get("title")
        self.autodata = goal.get("autodata")
        self.type = goal.get("goal_type")
        self.headsum = goal.get("headsum")
        self.hhmmformat = goal.get("hhmmformat")
        self.integery = goal.get("integery")
        self.safebump = goal.get("safebump")
        self.curval = goal.get("curval")
        if "last_datapoint" in goal:
            self.last_datapoint = Datapoint(**goal["last_datapoint"])
        else:
            self.last_datapoint = None
        self.dictionary = goal
        self.datapoints = []

    @property
    def bump(self):
        delta = self.safebump - self.curval
        if self.hhmmformat:
            return humanize.naturaldelta(timedelta(hours=delta))
        else:
            return int(math.ceil(delta))

    @property
    def losedate(self):
        if "backlog" in self.slug:
            self.ensure_datapoints()
            datapoints = self.datapoints
            today = datetime.now().date()
            i = 0
            dp_today = list(
                filter(
                    lambda dp: dp.datetime.date() == today - timedelta(days=i),
                    datapoints,
                )
            )
            while not dp_today:
                i += 1
                dp_today = list(
                    filter(
                        lambda dp: dp.datetime.date() == today - timedelta(days=i),
                        datapoints,
                    )
                )
            dp_yesterday = list(filter(lambda dp: dp not in dp_today, datapoints))
            delta = dp_today[0].value - dp_yesterday[-1].value
            if delta < 0:
                return self._losedate
            timedel = dp_today[0].datetime - dp_yesterday[-1].datetime
            est_rate = -delta / (timedel.total_seconds() / 24 / 3600)
            actual_time = datetime.now() + timedelta(
                days=self.dictionary["delta"] / est_rate
            )
            beeminder_time = self._losedate
            return min([actual_time, beeminder_time])
        else:
            return self._losedate

    @property
    def formatted_losedate(self):
        return humanize.naturalday(self.losedate)

    @property
    def summary(self):
        return f"{self.slug.upper():25}{self.bump:^15}{self.formatted_losedate:12}{self.last_datapoint.canonical}"

    @property
    def is_do_less(self):
        return self.type == "drinker"  # and a fiend

    @property
    def is_manual(self):
        return self.autodata is None

    def ensure_datapoints(self):
        if not self.datapoints:
            url = f"https://www.beeminder.com/api/v1/users/{username}/goals/{self.slug}.json"
            params = auth.copy()
            params["datapoints"] = "true"
            r = requests.get(url, params=params).json()
            datapoints = [Datapoint(**dp) for dp in r["datapoints"]]
            self.datapoints = sorted(datapoints, key=lambda dp: dp.datetime)

    @property
    def is_updated_today(self):
        if "backlog" in self.slug:
            self.ensure_datapoints()
            datapoints = self.datapoints
            today = datetime.now().date()
            dp_today = list(filter(lambda dp: dp.datetime.date() == today, datapoints))
            if not dp_today:
                return False
            dp_yesterday = list(filter(lambda dp: dp not in dp_today, datapoints))
            delta = dp_today[0].value - dp_yesterday[-1].value
            return delta < 0
        else:
            return self.last_datapoint.is_updated_today

    def __repr__(self, *args, **kwargs):
        return f"{self.__class__.__name__}({self.slug})"

    @property
    def default_description(self):
        return f"Updated from {self} at {datetime.now()}"

    @property
    def color(self):
        now = datetime.now()
        lane = self.dictionary["lane"]
        yaw = self.dictionary["yaw"]
        losedate = self._losedate
        if lane * yaw >= -1:  #  on the road or on the good side of it (blue or green)
            return "blue"
        elif lane * yaw > 1:  # good side of the road (green dot)
            return "green"
        elif lane * yaw == 1:  # right lane (blue dot)
            return "yellow"
        elif lane * yaw == -1:  # wrong lane (orange dot)
            return "orange"
        elif lane * yaw <= -2:  # emergency day or derailed (red dot)
            return "red"
        else:
            raise ValueError("Wrong color, this should not be possible")

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
        if args or kwargs:
            click.echo(
                "This is a remote goal, I can't update it from here.\n"
                "I'm going to ignore this and just call for a remote update."
            )
        url = f"https://www.beeminder.com/api/v1/users/{username}/goals/{self.slug}/refresh_graph.json"
        r = requests.get(url, params=auth)
        click.echo(f"Updated {self.slug}.")


class TogglGoal(RemoteApiGoal):
    @property
    def is_updated_today(self):
        return not (self.last_datapoint.value == 0.0)


def create_goal(**goal):
    if goal.get("autodata") is None or goal.get("autodata") == "api":
        return Goal(**goal)
    elif goal["autodata"] == "toggl":
        return TogglGoal(**goal)
    elif goal["autodata"] != "api":
        return RemoteApiGoal(**goal)
    else:
        raise ValueError(f"What autodata is {goal['autodata']}?")


def get_all_goals():
    all_goals = []
    url = f"https://www.beeminder.com/api/v1/users/{username}/goals.json"
    r = requests.get(url, params=auth).json()

    for goal in r:
        goal = create_goal(**goal)
        all_goals.append(goal)
    return all_goals


@click.group(invoke_without_command=True)
@click.option("-m/-nm", "--manual/--no-manual", default=None)
@click.option("-dl/-ndl", "--do-less/--no-do-less", default=False)
@click.option("-dt/-ndt", "--done-today/--not-done-today", default=None)
@click.option("-d", "--days", type=int)
@click.option("-s", "--since", type=int)
@click.option("-n", type=int)
@click.option("-r", "--random", is_flag=True)
@click.pass_context
def beeminder(
    ctx,
    manual=None,
    do_less=None,
    done_today=None,
    days=None,
    since=None,
    n=None,
    random=False,
):
    """Display timings for beeminder goals."""
    if ctx.invoked_subcommand is None:
        goals = get_all_goals()
        if manual is not None:
            goals = filter(lambda g: g.is_manual, goals)
        if do_less is not None:
            goals = filter(lambda g: not g.is_do_less, goals)
        if done_today is not None:
            goals = filter(lambda g: g.is_updated_today == done_today, goals)
        if since is not None:
            horizon = datetime.now() - timedelta(days=since)
            goals = filter(lambda g: g.last_datapoint.datetime < horizon, goals)

        goals = sorted(goals, key=lambda g: g.losedate)

        if days is not None:
            days = int(days)
            horizon = datetime.now() + timedelta(days=days)
            goals = filter(lambda g: g.losedate <= horizon, goals)

        if n is not None:
            n = int(n)
            goals = goals[:n]

        if random:
            goal = choice(goals)
            click.secho(goal.summary, fg=goal.color)
            return

        for goal in goals:
            click.secho(goal.summary, fg=goal.color)
            # TODO use click.echo_via_pager; have a generator handling this
            # https://click.palletsprojects.com/en/7.x/utils/#pager-support
    else:
        pass


@beeminder.command()
@click.argument("goal")
def show(goal):
    goal = create_goal(slug=goal)
    click.secho(goal.summary, fg=goal.color)


@beeminder.command()
@click.argument("goal", type=str)
@click.argument("update_value", required=False)
@click.argument("description", type=str, required=False)
def update(goal, update_value, description=None):
    goal = create_goal(slug=goal)
    goal.update(update_value, description)


@beeminder.command()
@click.argument("goal", type=str)
def web(goal):
    goal = create_goal(slug=goal)
    goal.show_web()


@beeminder.command()
def update_remotes():
    def only_remotes(goal):
        return not (goal.autodata is None or goal.autodata == "api")

    all_goals = get_all_goals()
    goals = filter(only_remotes, all_goals)
    for goal in goals:
        goal.update()


@beeminder.command()
def debug():
    breakpoint()


if __name__ == "__main__":
    beeminder()
