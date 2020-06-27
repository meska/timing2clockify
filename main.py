import os
from datetime import datetime, timedelta
from time import sleep

import requests
from dateutil.parser import parse
from munch import munchify
# noinspection PyPackageRequirements
from slugify import slugify
from telegram import Bot
from yaml import safe_load


class T2c:
    cache = {}

    def __init__(self):
        if not os.path.exists('config.yaml'):
            raise FileNotFoundError('Missing config.yaml')
        with open('config.yaml') as stream:
            self.config = munchify(safe_load(stream))

        if self.config.telegram.token:
            self.bot = Bot(token=self.config.telegram.token)
        else:
            self.bot = False

    def get_last_tasks(self):
        start_date = (datetime.now() - timedelta(days=7)).strftime(
            "%Y-%m-%d %H:%M:%S")
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
            print(f"{datetime.now()} OLD_TASK DATA: {date}")
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
        print(f"{datetime.now()} End sync all tasks")

    def upload_task(self, task):
        user_id = self.clokify_get_user()
        workspace_id = self.clokify_get_workspace(self.config.clockify.workspace_name)
        client_id = self.clokify_get_client(workspace_id, task.project.title_chain[0])
        project_id = self.clokify_get_project(workspace_id, client_id, task.project.title, task.project.color)
        task_id = self.clokify_get_task(user_id, workspace_id, project_id, task.title if task.title else 'no title')
        res, time_id = self.clokify_time_entry(user_id, workspace_id, project_id, task_id, task)
        if res:
            print(f"{datetime.now()} Task ADD: {task.title} {task.start_date} {time_id}")
            if self.bot:
                self.bot.send_message(
                    self.config.telegram.chat_id,
                    f"Clockify ADD: {task.project.title_chain[0]} {task.project.title}\n"
                    f"{task.title} {parse(task.start_date).strftime('%d/%m/%Y %H:%M:%S')}"
                )
        else:
            print(f"{datetime.now()} Task SKIP: {task.title} {task.start_date} {time_id}")

    def clokify_get_client(self, workspace_id, client_name):
        if self.cache.get(f'client_{slugify(client_name)}'):
            return self.cache[f'client_{slugify(client_name)}']
        else:
            res = requests.get(
                url=f"{self.config.clockify.url}workspaces/{workspace_id}/clients",
                headers={"X-Api-Key": self.config.clockify.token}

            )
            clients = [x.id for x in munchify(res.json()) if x.name == client_name]

            if not clients:
                # create client
                res = requests.post(
                    url=f"{self.config.clockify.url}workspaces/{workspace_id}/clients",
                    headers={"X-Api-Key": self.config.clockify.token},
                    json={
                        "name": client_name
                    }
                )
                self.cache[f'client_{slugify(client_name)}'] = munchify(res.json()).id
                return self.cache[f'client_{slugify(client_name)}']
            else:
                self.cache[f'client_{slugify(client_name)}'] = clients[0]
                return self.cache[f'client_{slugify(client_name)}']

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

    def clokify_get_project(self, workspace_id, client_id, project_name, color):
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
                        "clientId": client_id,
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
        print(f"{datetime.now()} Checking Tasks")
        t.bot.send_message(t.config.telegram.chat_id, f"T2c Error! {e}")
        tasks = self.get_last_tasks()
        if len(tasks) == 0:
            print(f"{datetime.now()} No New Tasks")
            return 'No tasks'

        for task in tasks:
            if not task.is_running:
                self.upload_task(task)
                sleep(1)


if __name__ == '__main__':
    print(f"{datetime.now()} Starting ...")
    t = T2c()
    # in avvio sincronizzo indietro di un mese
    mesefa = datetime.now() - timedelta(days=30)
    t.sync_all_tasks(datetime(mesefa.year, mesefa.month, mesefa.day))
    # t.sync_all_tasks(datetime(2019, 12, 10))
    while True:
        try:
            t.run()
        except Exception as e:
            if t.bot:
                t.bot.send_message(t.config.telegram.chat_id, f"T2c Error! {e}")
            print(e)
        sleep(int(t.config.t2c.refresh_time))
