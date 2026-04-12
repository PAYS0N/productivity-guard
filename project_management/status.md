# Project Status

Project tasks are managed centrally via the personal assistant CLI:

    /home/payson/Documents/repos/self/personal-assistant/scripts/project_tasks_cli.py

To manipulate status as described by a prompt, use the below commands to add/remove/modify a task. Before modification, ensure you have the correct task first via listing all tasks.

Commands:
- `project_tasks_cli.py list productivity-guard` — list open tasks
- `project_tasks_cli.py add productivity-guard "<name>" [--severity S] [--difficulty D] [--value V]` — add a task
- `project_tasks_cli.py complete productivity-guard <task_id>` — mark done
- `project_tasks_cli.py update productivity-guard <task_id> [--name N] [--severity S] [--difficulty D]  [--value V]` — update
- `project_tasks_cli.py delete productivity-guard <task_id>` — delete

