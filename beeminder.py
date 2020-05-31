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
from datetime import datetime, timedelta, timezone
import click
import os
import functools
import math
from random import choice
import webbrowser
import humanize
import math
import dateutil, dateutil.parser
import numpy as np
from dataclasses import dataclass

__version__ = "0.1.0"

username = os.environ["BEEMINDER_USERNAME"]
beeminder_auth_token = os.environ["BEEMINDER_TOKEN"]
auth = {"username": username, "auth_token": os.environ["BEEMINDER_TOKEN"]}

now = datetime.now()


def increment_beeminder(desc, beeminder_goal, value=1):
    data = {"value": value, "auth_token": beeminder_auth_token, "comment": desc}

    response = requests.post(
        f"https://www.beeminder.com/api/v1/users/{username}/goals/{beeminder_goal}/datapoints.json",
        data=data,
    )
    return response


@dataclass
class Datapoint:
    value: float
    comment: int
    timestamp: str
    id: int
    updated_at: str
    requestid: int
    canonical: str
    origin: str
    daystamp: str
    fulltext: str

    @property
    def datetime(self):
        return datetime.fromtimestamp(self.timestamp)

    @property
    def updatedatetime(self):
        return datetime.fromtimestamp(self.updated_at)

    @property
    def is_updated_today(self):
        return self.datetime.date() >= now.date()


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
        self.won = goal.get("won")
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
        return self.last_datapoint.is_updated_today

    def __repr__(self, *args, **kwargs):
        return f"{self.__class__.__name__}({self.slug})"

    @property
    def default_description(self):
        return f"Updated from {self} at {now}"

    @property
    def color(self):
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
            value = 1
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


class TodoistGoal(Goal):
    import todoist

    key = os.environ["TODOIST_KEY"]
    api = todoist.TodoistAPI(key)
    api.sync()
    now = datetime.now(timezone.utc)


class TodoistBacklog(TodoistGoal):
    @staticmethod
    def _filter(task):
        result = not task["checked"]
        if task["due"] is not None:
            return result and not task["due"]["is_recurring"]
        else:
            return result

    def get_dates(self):
        undone_tasks = self.api.items.all(self._filter)
        dates = [dateutil.parser.parse(task["date_added"]) for task in undone_tasks]
        return dates

    def update(self, *args, **kwargs):
        dates = self.get_dates()

        total = -np.sum(np.array(dates) - self.now)
        total_days = total.days + total.seconds / 3600 / 24

        message = f"Incremented {self.slug} to {total_days} automatically from {len(dates)} items at {now}"
        super().update(total_days, message)


class TodoistNumberOfTasksGoal(TodoistGoal):
    # def __init__(self, *args, **kwargs):   # maybe like this?
    #     self._filter = kwargs.pop("filter")
    #     super().__init(*args, **kwargs)

    @staticmethod
    def _filter(task):
        raise NotImplementedError

    def update(self, *args, **kwargs):
        tasks = self.api.items.all(self._filter)
        message = f"{self.slug}: {len(tasks)} tasks at {now}"
        super().update(len(tasks), message)


class TodoistUnprioritized(TodoistNumberOfTasksGoal):
    @staticmethod
    def _filter(task):
        return not task["checked"] and task["priority"] == 1


class TodoistHighPriority(TodoistNumberOfTasksGoal):
    @staticmethod
    def _filter(task):
        return not task["checked"] and task["priority"] == 4


class TodoistInbox(TodoistNumberOfTasksGoal):
    @staticmethod
    def _filter(task):
        return (
            not task["checked"] and task["project_id"] == 1264279437
        )  # TODO configurable


class YoutubeBacklogGoal(Goal):
    def get_dates(self):
        import pafy

        url = "https://www.youtube.com/playlist?list=PLvENAQ9GutPF3r2x5NPBipuqOXn3uUYbF"
        playlist = pafy.get_playlist(url)
        dates = [
            dateutil.parser.parse(item["playlist_meta"]["added"])
            for item in playlist["items"]
        ]
        return dates

    def update(self, *args, **kwargs):
        dates = self.get_dates()
        total = -np.sum(np.array(dates) - now)
        total_days = total.days + total.seconds / 3600 / 24

        message = f"Incremented {self.slug} to {total_days} automatically from {len(dates)} items at {now}"
        super().update(total_days, message)


class PubsBacklogGoal(Goal):
    def get_dates(self):
        from pubs import repo, config
        from pubs.query import get_paper_filter

        conf_path = config.get_confpath(verify=False)  # will be checked on load
        conf = config.load_conf(path=conf_path)
        rp = repo.Repository(conf)
        query = ["tag:TODO"]
        papers = list(filter(get_paper_filter(query), rp.all_papers()))
        query2 = ["tag:TodoAtWork"]
        citekeys = [paper.citekey for paper in papers]

        papers2 = list(filter(get_paper_filter(query2), rp.all_papers()))
        for paper in papers2:
            if paper.citekey not in citekeys:
                papers.append(paper)
        rp.close()
        dates = [paper.added for paper in papers]
        return dates

    def update(self, *args, **kwargs):
        dates = self.get_dates()
        total = -np.sum(np.array(dates) - now)
        total_days = total.days + total.seconds / 3600 / 24

        message = f"Incremented {self.slug} to {total_days} automatically from {len(dates)} items at {now}"
        super().update(total_days, message)


custom_goals = {
    "todoist-backlog": TodoistBacklog,
    "todoist-unprioritized": TodoistUnprioritized,
    "todoist-breakdown": TodoistHighPriority,
    "todoist-inbox": TodoistInbox,
    "youtube-backlog-upgrade": YoutubeBacklogGoal,
    "papers-backlog": PubsBacklogGoal,
}


def create_goal(**goal):
    if goal["slug"] in custom_goals:
        return custom_goals[goal["slug"]](**goal)
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


class AliasedGroup(click.Group):
    # as per https://click.palletsprojects.com/en/7.x/advanced/
    def get_command(self, ctx, cmd_name):
        rv = click.Group.get_command(self, ctx, cmd_name)
        if rv is not None:
            return rv
        matches = [x for x in self.list_commands(ctx) if x.startswith(cmd_name)]
        if not matches:
            return None
        elif len(matches) == 1:
            return click.Group.get_command(self, ctx, matches[0])
        ctx.fail("Too many matches: %s" % ", ".join(sorted(matches)))


@click.group(invoke_without_command=True, cls=AliasedGroup)
@click.option("-m/-nm", "--manual/--no-manual", default=None)
@click.option("-dl/-ndl", "--do-less/--no-do-less", default=False)
@click.option("-dt/-ndt", "--done-today/--not-done-today", default=None)
@click.option("-d", "--days", type=int)
@click.option("-s", "--since", type=int)
@click.option("-f/-nf", "--finished/--not-finished", default=False)
@click.option("-n", type=int)
@click.option("-r", "--random", is_flag=True)
@click.option("-w", "--watch", is_flag=True)
@click.pass_context
def beeminder(
    ctx,
    manual=None,
    do_less=None,
    done_today=None,
    days=None,
    since=None,
    finished=False,
    n=None,
    random=False,
    watch=False,
):
    """Display timings for beeminder goals."""
    if ctx.invoked_subcommand is None:

        def filter_goals():
            goals = get_all_goals()
            if finished is not None:
                goals = filter(lambda g: g.won == finished, goals)
            if manual is not None:
                goals = filter(lambda g: g.is_manual, goals)
            if do_less is not None:
                goals = filter(lambda g: not g.is_do_less, goals)
            if done_today is not None:
                goals = filter(lambda g: g.is_updated_today == done_today, goals)
            if since is not None:
                horizon = now - timedelta(days=since)
                goals = filter(lambda g: g.last_datapoint.datetime < horizon, goals)

            goals = sorted(goals, key=lambda g: g.losedate)

            if days is not None:
                horizon = now + timedelta(days=int(days))
                goals = filter(lambda g: g.losedate <= horizon, goals)

            if n is not None:
                goals = goals[: int(n)]
            return goals

        goals = filter_goals()

        def _display():
            for goal in goals:
                yield click.style(goal.summary, fg=goal.color) + "\n"

        if random:
            goal = choice(goals)
            click.secho(goal.summary, fg=goal.color)
        elif watch:
            while True:
                click.echo_via_pager(_display())
                click.confirm("Continue?", abort=True)
                goals = filter_goals()
        else:
            click.echo_via_pager(_display())
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
def fetch_remotes():
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
