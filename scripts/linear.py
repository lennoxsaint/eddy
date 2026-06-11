#!/usr/bin/env python3
"""Linear board driver for the Eddy build. Reads LINEAR_API_KEY from env.

Commands:
    setup <issues.json>   create project + issues (idempotent-ish: skips if project exists)
    move <EDD-n> <state>  move an issue to a workflow state (e.g. "In Progress", "Done")
    list                  list project issues with states
"""

from __future__ import annotations

import json
import os
import sys

import httpx

API = "https://api.linear.app/graphql"
TEAM_KEY = "EDD"
PROJECT_NAME = "Eddy v1"


def gql(query: str, variables: dict | None = None) -> dict:
    key = os.environ["LINEAR_API_KEY"]
    r = httpx.post(
        API,
        json={"query": query, "variables": variables or {}},
        headers={"Authorization": key, "Content-Type": "application/json"},
        timeout=30,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"{r.status_code}: {r.text[:2000]}")
    data = r.json()
    if "errors" in data:
        raise RuntimeError(json.dumps(data["errors"], indent=2))
    return data["data"]


def team() -> dict:
    d = gql(
        """query { teams { nodes { id key name states { nodes { id name type } } } } }"""
    )
    for t in d["teams"]["nodes"]:
        if t["key"] == TEAM_KEY:
            return t
    raise SystemExit(f"team {TEAM_KEY} not found")


def find_project(team_id: str) -> dict | None:
    d = gql(
        """query($tid: String!) { team(id: $tid) { projects { nodes { id name } } } }""",
        {"tid": team_id},
    )
    for p in d["team"]["projects"]["nodes"]:
        if p["name"] == PROJECT_NAME:
            return p
    return None


def setup(issues_path: str) -> None:
    t = team()
    project = find_project(t["id"])
    if project is None:
        d = gql(
            """mutation($input: ProjectCreateInput!) {
                projectCreate(input: $input) { project { id name } } }""",
            {
                "input": {
                    "name": PROJECT_NAME,
                    "teamIds": [t["id"]],
                    "description": "Local-first agentic video editor. PRD: ~/eddy/docs/PRD.md",
                }
            },
        )
        project = d["projectCreate"]["project"]
        print(f"created project {project['name']} ({project['id']})")
    else:
        print(f"project exists: {project['id']}")

    issues = json.loads(open(issues_path).read())
    for i, issue in enumerate(issues):
        d = gql(
            """mutation($input: IssueCreateInput!) {
                issueCreate(input: $input) { issue { identifier title } } }""",
            {
                "input": {
                    "teamId": t["id"],
                    "projectId": project["id"],
                    "title": issue["title"],
                    "description": issue.get("description", ""),
                    "sortOrder": float(i),
                }
            },
        )
        created = d["issueCreate"]["issue"]
        print(f"{created['identifier']}  {created['title']}")


def state_id(t: dict, name: str) -> str:
    for s in t["states"]["nodes"]:
        if s["name"].lower() == name.lower():
            return s["id"]
    raise SystemExit(f"state '{name}' not found; have: {[s['name'] for s in t['states']['nodes']]}")


def move(identifier: str, state_name: str) -> None:
    t = team()
    num = int(identifier.split("-")[1])
    d = gql(
        """query($tid: String!) { team(id: $tid) { issues(first: 100) { nodes { id identifier number } } } }""",
        {"tid": t["id"]},
    )
    issue = next(
        (n for n in d["team"]["issues"]["nodes"] if n["number"] == num), None
    )
    if issue is None:
        raise SystemExit(f"{identifier} not found")
    gql(
        """mutation($id: String!, $input: IssueUpdateInput!) {
            issueUpdate(id: $id, input: $input) { success } }""",
        {"id": issue["id"], "input": {"stateId": state_id(t, state_name)}},
    )
    print(f"{identifier} -> {state_name}")


def list_issues() -> None:
    t = team()
    d = gql(
        """query($tid: String!) { team(id: $tid) {
            issues(first: 100, orderBy: createdAt) { nodes { identifier title state { name } } } } }""",
        {"tid": t["id"]},
    )
    for n in d["team"]["issues"]["nodes"]:
        print(f"{n['identifier']:8} {n['state']['name']:12} {n['title']}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "setup":
        setup(sys.argv[2])
    elif cmd == "move":
        move(sys.argv[2], sys.argv[3])
    else:
        list_issues()
