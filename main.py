import os
from datetime import datetime, timedelta
from time import sleep

import requests
from dateutil.parser import parse
from munch import munchify
# noinspection PyPackageRequirements
from slugify import slugify
from yaml import safe_load


class T2c:
    cache = {}

    def __init__(self):

        if not os.path.exists('config.yaml'):
            raise FileNotFoundError('Missing config.yaml')
        with open('config.yaml') as stream:
            self.config = munchify(safe_load(stream))

    def get_last_tasks(self):
        start_date = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
        res = requests.get(
            url=f"{self.config.timing.url}time-entries?start_date_min={start_date}"
                f"&is_running=false&include_project_data=true&include_child_projects=true",
            headers={
                "Authorization": f"Bearer {self.config.timing.token}"
            }
        )
        if not res.status_code == 200:
            raise ValueError(res.json())

        return munchify(res.json()).data

    def sync_all_tasks(self, date):
        while True:
            print(f"DATA: {date}")
            res = requests.get(
                url=f"{self.config.timing.url}time-entries?"
                    f"is_running=false&include_project_data=true&include_child_projects=true"
                    f"&start_date_min={date.strftime('%Y-%m-%d %H:%M:%S')}"
                    f"&start_date_max={date.strftime('%Y-%m-%d 23:59:59')}",
                headers={
                    "Authorization": f"Bearer {self.config.timing.token}"
                }
            )
            if not res.status_code == 200:
                raise ValueError(res.json())
            tasks = munchify(res.json()).data

            for task in tasks:
                self.upload_task(task)

            if date >= datetime.now():
                break
            date = date + timedelta(days=1)
            sleep(1)

    def upload_task(self, task):
        user_id = self.clokify_get_user()
        workspace_id = self.clokify_get_workspace(task.project.title_chain[0])
        project_id = self.clokify_get_project(workspace_id, task.project.title, task.project.color)
        task_id = self.clokify_get_task(user_id, workspace_id, project_id, task.title if task.title else 'no title')
        res, time_id = self.clokify_time_entry(user_id, workspace_id, project_id, task_id, task)
        if res:
            print(f"Task ADD: {task.title} {task.start_date} {time_id}")
        else:
            print(f"Task SKIP: {task.title} {task.start_date} {time_id}")

    def clokify_get_workspace(self, workspace_name):
        if self.cache.get(f'workspace_{slugify(workspace_name)}'):
            return self.cache[f'workspace_{slugify(workspace_name)}']
        else:
            res = requests.get(
                url=f"{self.config.clockify.url}workspaces",
                headers={"X-Api-Key": self.config.clockify.token}

            )
            workspaces = [x.id for x in munchify(res.json()) if x.name == workspace_name]

            if not workspaces:
                # create workspace
                res = requests.post(
                    url=f"{self.config.clockify.url}workspaces",
                    headers={"X-Api-Key": self.config.clockify.token},
                    json={
                        "name": workspace_name
                    }
                )
                self.cache[f'workspace_{slugify(workspace_name)}'] = munchify(res.json()).id
                return self.cache[f'workspace_{slugify(workspace_name)}']
            else:
                self.cache[f'workspace_{slugify(workspace_name)}'] = workspaces[0]
                return self.cache[f'workspace_{slugify(workspace_name)}']

    def clokify_get_project(self, workspace_id, project_name, color):
        """
        Get or create project
        :param color:
        :type color:
        :param project_name:
        :type project_name:
        :param workspace_id:
        :type workspace_id:
        :return:
        :rtype:
        """
        if self.cache.get(f'prj_{workspace_id}_{slugify(project_name)}'):
            return self.cache[f'prj_{workspace_id}_{slugify(project_name)}']
        else:
            res = requests.get(
                url=f"{self.config.clockify.url}workspaces/{workspace_id}/projects",
                headers={"X-Api-Key": self.config.clockify.token}
            )
            projects = [x.id for x in munchify(res.json()) if x.name == project_name]
            if not projects:
                # create clockify project
                res = requests.post(
                    url=f"{self.config.clockify.url}workspaces/{workspace_id}/projects",
                    headers={"X-Api-Key": self.config.clockify.token},
                    json={
                        "name": project_name,
                        "isPublic": "false",
                        "color": color[0:7],
                        "hourlyRate": {"amount": 6000, "currency": "EURO"},
                        "billable": "true"
                    }
                )
                self.cache[f'prj_{workspace_id}_{slugify(project_name)}'] = munchify(res.json()).id
                return self.cache[f'prj_{workspace_id}_{slugify(project_name)}']
            else:
                self.cache[f'prj_{workspace_id}_{slugify(project_name)}'] = projects[0]
                return self.cache[f'prj_{workspace_id}_{slugify(project_name)}']

    def clokify_get_user(self):
        if self.cache.get('user_id'):
            return self.cache['user_id']
        else:
            res = requests.get(
                url=f"{self.config.clockify.url}user",
                headers={"X-Api-Key": self.config.clockify.token}
            )
            self.cache['user_id'] = munchify(res.json()).id
            return self.cache['user_id']

    def clokify_get_task(self, user_id, workspace_id, project_id, title):
        res = requests.get(
            url=f"{self.config.clockify.url}workspaces/{workspace_id}/projects/{project_id}/tasks",
            headers={"X-Api-Key": self.config.clockify.token}

        )
        tasks = [x.id for x in munchify(res.json()) if x.name == title]
        if not tasks:
            # create task
            # create clockify project
            res = requests.post(
                url=f"{self.config.clockify.url}workspaces/{workspace_id}/projects/{project_id}/tasks",
                headers={"X-Api-Key": self.config.clockify.token},
                json={
                    "name": title,
                    "assigneeIds": [user_id],
                }
            )
            return munchify(res.json()).id
        else:
            return tasks[0]

    def clokify_time_entry(self, user_id, workspace_id, project_id, task_id, task):
        start_time = parse(task.start_date).strftime('%Y-%m-%dT%H:%M:%SZ')
        end_time = parse(task.end_date).strftime('%Y-%m-%dT%H:%M:%SZ')

        res = requests.get(
            url=f"{self.config.clockify.url}"
                f"workspaces/{workspace_id}/user/{user_id}/time-entries"
                f"?project={project_id}&task={task_id}"
                f"&start={start_time}",
            headers={"X-Api-Key": self.config.clockify.token}
        )

        entries = [x.id for x in munchify(res.json()) if
                   x.timeInterval.end == end_time and x.timeInterval.start == start_time]
        if not entries:
            res = requests.post(
                url=f"{self.config.clockify.url}workspaces/{workspace_id}/time-entries",
                headers={"X-Api-Key": self.config.clockify.token},
                json={
                    "start": start_time,
                    "end": end_time,
                    "description": task.notes if task.notes else task.title,
                    "billable": "true",
                    "projectId": project_id,
                    "taskId": task_id
                }
            )
            return True, munchify(res.json()).id
        else:
            return False, entries[0]

    def run(self):
        tasks = self.get_last_tasks()
        if len(tasks) == 0:
            return 'No tasks'

        for task in tasks:
            if not task.is_running:
                self.upload_task(task)
                sleep(1)


if __name__ == '__main__':
    t = T2c()
    t.sync_all_tasks(datetime(2020, 2, 10))
    # t.run(alltasks=True)
