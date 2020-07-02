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
this is an external goal; displays useful information >>> beeminder todoist edit """
import requests
from datetime import datetime, timedelta, timezone
import json
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
import itertools
from dataclasses import dataclass
import tqdm
import pathlib
import concurrent.futures
import functools
from pprint import pprint
from tabulate import tabulate
import subprocess

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
        self.runits = goal.get("runits")
        if "last_datapoint" in goal:
            self.last_datapoint = Datapoint(**goal["last_datapoint"])
        else:
            self.last_datapoint = None
        self.dictionary = goal
        self.won = goal.get("won")
        # self.updated_at = datetime.fromtimestamp(goal.get("updated_at"))

    @property
    def losedate(self):
        return datetime.utcfromtimestamp(self.dictionary["losedate"])

    @property
    def is_due_today(self):
        horizon = datetime.now() + timedelta(hours=24)
        return self.losedate <= horizon

    def format_delta(self, delta):
        if self.hhmmformat:
            return humanize.naturaldelta(timedelta(hours=delta))
        else:
            return f"{int(math.ceil(delta))} {self.dictionary['gunits']}"

    @property
    def bumpval(self):
        return self.safebump - self.curval

    @property
    def bump(self):
        return self.format_delta(self.bumpval)

    @property
    def rate(self):
        if self.dictionary["rate"] is None:
            return self.dictionary["mathishard"][2]
        else:
            return self.dictionary["rate"]

    @property
    def rate_timedelta(self):
        rate_dict = dict(y=365, m=30, w=7, d=1, h=1 / 24)
        return timedelta(days=rate_dict[self.runits])

    @functools.cached_property
    def data_rate(self):
        if self.rate == 0:
            return NotImplemented
        self.ensure_datapoints()
        horizon = datetime.now().date() - self.rate_timedelta
        irrelevant_datapoints = sorted(
            filter(lambda dp: dp.datetime.date() <= horizon, self.datapoints),
            key=lambda dp: dp.datetime,
        )
        relevant_datapoints = sorted(
            filter(lambda dp: horizon < dp.datetime.date(), self.datapoints),
            key=lambda dp: dp.datetime,
        )
        if self.type in ["biker", "fatloser", "gainer", "inboxer"]:
            relevant_datapoints = list(relevant_datapoints)
            if relevant_datapoints:
                if irrelevant_datapoints:
                    total_values = (
                        relevant_datapoints[-1].value - irrelevant_datapoints[-1].value
                    )
                else:
                    return NotImplemented
            else:
                total_values = 0
        elif self.type in ["hustler", "drinker"]:
            total_values = sum(dp.value for dp in relevant_datapoints)
        else:
            return NotImplemented
        return total_values / self.rate

    @functools.cached_property
    def format_epsilon_delta(self):
        fraction = self.data_rate
        if fraction is NotImplemented:
            return "?"
        if self.type == "drinker":
            if 1 <= fraction:
                return "!"
            elif 0 < fraction:
                return "ε"
            elif 0 == fraction:
                return "Δ"
            else:
                return "?"
        else:
            if 1 <= fraction:
                return "Δ"
            elif 0 < fraction:
                return "ε"
            elif 0 == fraction:
                return "0"
            else:
                return "!"

    @property
    def losedate(self):
        return self._losedate

    @property
    def formatted_losedate(self):
        return humanize.naturalday(self.losedate)

    @property
    def data_rate_format(self):
        if self.data_rate is NotImplemented:
            return "???"
        else:
            return f"{self.data_rate:.1f}"

    @property
    def remaining_format(self):
        if self.data_rate is NotImplemented:
            return "???"
        if self.data_rate >= 1:
            return "------"
        remaining = (1 - self.data_rate) * self.rate
        remaining_fmt = self.format_delta(remaining)
        if remaining_fmt == self.bump:
            return "--||--"
        return remaining_fmt

    @property
    def summary(self):
        return (
            self.format_epsilon_delta,
            self.data_rate_format,
            self.slug.upper(),
            self.bump,
            self.formatted_losedate,
            self.remaining_format,
            f"{round(self.rate, 1)}/{self.runits}",
            self.last_datapoint.canonical[:40],
        )

    @property
    def summary_header(self):
        return (
            "ε-Δ",
            "frac",
            "name",
            "minimal bump to not derail",
            "lose date",
            "remaining to satisfy rate",
            "rate",
            "last datapoint",
        )

    @property
    def is_do_less(self):
        return self.type == "drinker"  # and a fiend

    @property
    def is_manual(self):
        if self.is_tasker_goal:
            return False
        return self.autodata is None

    def get_full_data(self):
        url = (
            f"https://www.beeminder.com/api/v1/users/{username}/goals/{self.slug}.json"
        )
        params = auth.copy()
        params["datapoints"] = "true"
        r = requests.get(url, params=params).json()
        self.dictionary = r
        return r

    @property
    def datapoints(self):
        datapoints = [Datapoint(**dp) for dp in self.dictionary["datapoints"]]
        return sorted(datapoints, key=lambda dp: dp.datetime)

    def ensure_datapoints(self):
        if "datapoints" not in self.dictionary or not self.dictionary["datapoints"]:
            self.get_full_data()

    @property
    def is_tasker_goal(self):
        return "tasker" in self.slug.lower() or "tasker" in self.title.lower()

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
        return_value = increment_beeminder(description, self.slug, value)
        self.get_full_data()
        return return_value

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
        self.get_full_data()
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

    children = itertools.groupby(api.items.all(), lambda item: item["parent_id"])

    id_task = {task["id"]: task for task in api.items.all()}

    for parent_id, these_children in children:
        if parent_id is not None:
            parent = id_task[parent_id]
            these_children = list(these_children)
            parent["children_ids"] = [child["id"] for child in these_children]


class TodoistBacklog(TodoistGoal):
    @staticmethod
    def _filter(task):
        if task["checked"]:
            return False
        if task["due"] is not None:
            if task["due"]["is_recurring"]:
                return False
        if 2153366150 in task["labels"]:
            return False
        if task["parent_id"] is not None:
            return False
        else:
            return True

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
        return (
            not task["checked"]
            and task["priority"] == 4
            and (not task["children_ids"] if "children_ids" in task else True)
        )


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


class CountGoal(Goal):
    def get_count(self):
        raise NotImplementedError

    def update(self, *args, **kwargs):
        count_items = self.get_count()

        message = f"Incremented {self.slug} to {count_items} items at {now}"
        super().update(count_items, message)


class PubsCountGoal(CountGoal):
    def get_count(self):
        from pubs import repo, config
        from pubs.query import get_paper_filter

        conf_path = config.get_confpath(verify=False)  # will be checked on load
        conf = config.load_conf(path=conf_path)
        rp = repo.Repository(conf)
        all_papers = {}
        for query in ["tag:TODO", "tag:TodoAtWork", "tag:Automated", "tag:InProgress"]:
            papers = list(filter(get_paper_filter([query]), rp.all_papers()))
            for paper in papers:
                all_papers[paper.citekey] = paper
        return len(all_papers)


class BashCountGoal(CountGoal):
    command = NotImplemented

    def get_count(self):
        if self.command is NotImplemented:
            raise ValueError("BashCountGoal subclass must implement `command`")
        proc = subprocess.run(
            self.command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True
        )
        return int(proc.stdout.strip())


class ScreenshotCountGoal(BashCountGoal):
    command = r"ls ~/Pictures/Screenshot_20* | wc -l"


class PapersNoteCountGoal(BashCountGoal):
    command = r"rg  '\- \[ \]' ~/.pubs/notes | cat | wc -l"


class JoplinNoteCountGoal(BashCountGoal):
    command = r"rg  '\- \[ \]' ~/Sync/Joplin | cat | wc -l"


class JrnlLengthGoal(BashCountGoal):
    command = r"jrnl -from 2000 | sed -e 's/| //' | wc -w"


custom_goals = {
    "todoist-backlog": TodoistBacklog,
    "todoist-unprioritized": TodoistUnprioritized,
    "todoist-breakdown": TodoistHighPriority,
    "todoist-inbox": TodoistInbox,
    "youtube-backlog-upgrade": YoutubeBacklogGoal,
    "papers-backlog": PubsCountGoal,
    "joplin-notes": JoplinNoteCountGoal,
    "papers-notes": PapersNoteCountGoal,
    "screenshots-parse": ScreenshotCountGoal,
    "jrnl": JrnlLengthGoal,
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


class CustomEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Goal):
            return obj.dictionary

        return json.JSONEncoder.default(self, obj)


class AllGoals:
    def __init__(self):
        url = f"https://www.beeminder.com/api/v1/users/{username}/goals.json"
        r = requests.get(url, params=auth).json()
        self.goals = [create_goal(**goal) for goal in r]

    def ensure_datapoints(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = {executor.submit(goal.get_full_data): goal for goal in self.goals}
            for future in tqdm.tqdm(
                concurrent.futures.as_completed(futures), total=len(self.goals)
            ):
                futures[future].dictionary = future.result()

    def pick_goal(self, **goal):
        return [g for g in self.goals if g.slug == goal["slug"]][0]

    def filter_goals(
        self,
        manual: bool = None,
        finished: bool = None,
        do_less: bool = None,
        done_today: bool = None,
        over_rate: bool = None,
        n: int = None,
        since: int = None,
        days: int = None,
    ):
        goals = sorted(self.goals, key=lambda g: g.losedate)

        if finished is not None:
            goals = filter(lambda g: g.is_due_today or g.won == finished, goals)
        if manual is not None:
            goals = filter(lambda g: g.is_due_today or g.is_manual == manual, goals)
        if do_less is not None:
            # goals = filter(lambda g: not g.is_do_less == do_less, goals)
            goals = filter(lambda g: g.is_due_today or not g.is_do_less, goals)
        if done_today is not None:
            goals = filter(
                lambda g: g.is_due_today or g.is_updated_today == done_today, goals
            )
        if over_rate is not None:
            goals = filter(
                lambda g: g.is_due_today
                or not (g.format_epsilon_delta == "Δ") == over_rate,
                goals,
            )

        if since is not None:
            horizon = now - timedelta(days=since)
            goals = filter(
                lambda g: g.is_due_today or g.last_datapoint.datetime < horizon, goals
            )
        if days is not None:
            horizon = now + timedelta(days=days)
            goals = filter(lambda g: g.is_due_today or g.losedate <= horizon, goals)
        if n is not None:
            goals = list(goals)[: int(n)]

        return list(goals)


all_goals = AllGoals()


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
@click.option("-o", "--over-rate", default=None, is_flag=True)
@click.option("-d", "--days", type=int)
@click.option("-s", "--since", type=int)
@click.option("-f/-nf", "--finished/--not-finished", default=False)
@click.option("-n", type=int)
@click.option("-r", "--random", is_flag=True)
@click.option("-w", "--watch", is_flag=True)
@click.option("--step", type=int, default=3)
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
    over_rate=None,
    # commands
    random=False,
    watch=False,
    step=3,
):
    """Display timings for beeminder goals."""
    if ctx.invoked_subcommand is None:
        all_goals.ensure_datapoints()
        goals = list(
            all_goals.filter_goals(
                manual=manual,
                do_less=do_less,
                done_today=done_today,
                days=days,
                since=since,
                finished=finished,
                n=n,
                over_rate=over_rate,
            )
        )

        def display(goals):
            alld = (goal.summary for goal in goals)
            contents = [goals[0].summary_header, *alld]
            table = tabulate(contents, headers="firstrow").splitlines()
            lines = [line + "\n" for line in table[:2]] + [
                click.style(line, fg=goal.color) + "\n"
                for line, goal in zip(table[2:], goals)
            ]
            click.echo_via_pager(lines)

        if random:
            goal = choice(goals)
            click.secho(goal.summary, fg=goal.color)

        elif watch:
            display(goals)
            while True:
                if since is not None:
                    since += step
                    click.echo(f"Incrementing since to {since}")
                elif days is not None:
                    days += step
                    click.echo(f"Incrementing days to {days}")
                elif n is not None:
                    n += step

                all_goals.ensure_datapoints()
                goals = all_goals.filter_goals(
                    manual=manual,
                    do_less=do_less,
                    done_today=done_today,
                    days=days,
                    since=since,
                    finished=finished,
                    n=n,
                    over_rate=over_rate,
                )
                display(goals)
                click.confirm("Continue?", default=True, abort=True)
        else:
            all_goals.ensure_datapoints()
            display(goals)
    else:
        pass


@beeminder.command()
@click.argument("goal")
def show(goal):
    goal = all_goals.pick_goal(slug=goal)
    click.secho(goal.summary, fg=goal.color)


@beeminder.command()
@click.argument("goal", type=str)
@click.argument("update_value", required=False)
@click.argument("description", type=str, required=False)
def update(goal, update_value, description=None):
    goal = all_goals.pick_goal(slug=goal)
    goal.update(update_value, description)


@beeminder.command()
@click.argument("goal", type=str)
def web(goal):
    """Display a goal"""
    goal = all_goals.pick_goal(slug=goal)
    goal.show_web()


@beeminder.command()
def fetch_remotes():
    """Force updates of remote autodata goals."""

    def only_remotes(goal):
        return not (goal.autodata is None or goal.autodata == "api")

    goals = filter(only_remotes, all_goals.goals)
    for goal in goals:
        goal.update()


@beeminder.command()
def debug():
    """Open a debugger with goal data pulled."""
    all_goals.ensure_datapoints()
    goals = all_goals.goals
    goal = all_goals.pick_goal(slug="pomodoro")
    breakpoint()


if __name__ == "__main__":
    beeminder()
