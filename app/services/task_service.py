import json
from datetime import datetime
from .. import db
from ..models import Task

def create_task(user_id, task_name, result_data):
    """
    Creates a new task for a specific user using SQLAlchemy.
    """
    existing_task = Task.query.filter_by(user_id=user_id, task_name=task_name).first()
    if existing_task:
        raise ValueError(f"Task name '{task_name}' already exists.")

    try:
        result_data_json = json.dumps(result_data, ensure_ascii=False)
        new_task = Task(
            user_id=user_id,
            task_name=task_name,
            result_data=result_data_json,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.session.add(new_task)
        db.session.commit()
        return new_task.id
    except Exception as e:
        db.session.rollback()
        raise e

def get_tasks_by_user(user_id, page=1, per_page=10):
    """
    Retrieves a paginated list of tasks for a specific user.
    """
    pagination = Task.query.filter_by(user_id=user_id)\
                           .order_by(Task.updated_at.desc())\
                           .paginate(page=page, per_page=per_page, error_out=False)
    tasks = pagination.items
    
    # Return a list of dictionaries, which is what the original function did.
    return [
        {'id': task.id, 'task_name': task.task_name, 'updated_at': task.updated_at.isoformat()}
        for task in tasks
    ]

def get_task_by_id(task_id, user_id):
    """
    Gets a single task by its ID, ensuring it belongs to the user.
    """
    task = Task.query.filter_by(id=task_id, user_id=user_id).first()
    if task:
        task_dict = {
            'id': task.id,
            'user_id': task.user_id,
            'task_name': task.task_name,
            'created_at': task.created_at.isoformat(),
            'updated_at': task.updated_at.isoformat(),
            'result_data': json.loads(task.result_data)
        }
        return task_dict
    return None

def update_task(task_id, user_id, new_result_data):
    """
    Updates an existing task's data.
    """
    task = Task.query.filter_by(id=task_id, user_id=user_id).first()
    if task:
        try:
            task.result_data = json.dumps(new_result_data, ensure_ascii=False)
            task.updated_at = datetime.utcnow()
            db.session.commit()
            return 1 # Return 1 to signify success, matching old function
        except Exception as e:
            db.session.rollback()
            raise e
    return 0 # Return 0 if task not found, matching old function

def delete_task(task_id, user_id):
    """
    Deletes a task, ensuring it belongs to the user.
    """
    task = Task.query.filter_by(id=task_id, user_id=user_id).first()
    if task:
        try:
            db.session.delete(task)
            db.session.commit()
            return 1 # Return 1 to signify success
        except Exception as e:
            db.session.rollback()
            raise e
    return 0 # Return 0 if task not found 