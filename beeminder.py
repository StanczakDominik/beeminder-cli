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
updates; asks for description
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

username = os.environ["BEEMINDER_USERNAME"]
auth = {"username": username, "auth_token": os.environ["BEEMINDER_TOKEN"]}
all_goals = []
url = f"https://www.beeminder.com/api/v1/users/{username}/goals.json"
r = requests.get(url, params=auth).json()


class Goal:
    """Wraps a Beeminder goal."""

    def __init__(self, **goal):
        """TODO."""
        self.losedate = goal["losedate"]
        self.slug = goal["slug"]
        self.limsum = goal["limsum"]
        self.title = goal["title"]
        self.autodata = goal["autodata"]
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
    def is_manual(self):
        return self.autodata is None

    def __repr__(self, *args, **kwargs):
        return f"Goal({self.slug})"


for goal in r:
    goal = Goal(**goal)
    all_goals.append(goal)


@click.group(invoke_without_command=True)
@click.option('--manual/--no-manual', default=False)
@click.pass_context
def beeminder(ctx, manual = False):
    """Display timings for beeminder goals."""
    if ctx.invoked_subcommand is None:
        click.echo('I was invoked without subcommand')
        goals = all_goals.copy()
        if manual:
            goals = filter(lambda g: g.is_manual, goals)
        for goal in sorted(goals, key=lambda g: g.losedate):
            click.echo(goal.summary)
    else:
        click.echo('I am about to invoke %s' % ctx.invoked_subcommand)

def create_subcommand(goal):
    def goal_subcommand(test = False):
        click.echo(f"I am {goal}")
        if test:
            click.echo(f"Running on test")
    return goal_subcommand


for goal in all_goals:
    command = create_subcommand(goal)
    # command = click.pass_context(command)
    command = click.option('--test/--no-test', default = False)(command)
    command = beeminder.command(name=goal.slug)(command)

if __name__ == "__main__":
    beeminder()
