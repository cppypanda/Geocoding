import unittest

from app import create_app, db
from app.models import Task, User


class TaskRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(config_overrides={
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite://',
            'WTF_CSRF_ENABLED': False,
            'ZHIPUAI_KEY': None,
            'SECRET_KEY': 'task-route-test-secret',
        })
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.client = self.app.test_client()
        user = User(email='task-owner@example.test', points=0)
        db.session.add(user)
        db.session.commit()
        self.user_id = user.id
        with self.client.session_transaction() as session:
            session['_user_id'] = str(user.id)
            session['_fresh'] = True

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_create_task_returns_success_contract(self):
        response = self.client.post('/tasks/', json={
            'task_name': '中国钢铁工业遗产名录与空间分布',
            'result_data': {'results': [{'address': '测试地址'}]},
        })

        self.assertEqual(response.status_code, 201)
        payload = response.get_json()
        self.assertIs(payload['success'], True)
        self.assertIsInstance(payload['task_id'], int)
        self.assertEqual(Task.query.count(), 1)

    def test_duplicate_task_returns_actionable_error(self):
        body = {'task_name': '重复任务', 'result_data': {'results': []}}
        self.assertEqual(self.client.post('/tasks/', json=body).status_code, 201)

        response = self.client.post('/tasks/', json=body)

        self.assertEqual(response.status_code, 409)
        payload = response.get_json()
        self.assertIs(payload['success'], False)
        self.assertIn('already exists', payload['error'])

    def test_update_task_returns_success_contract(self):
        task = Task(
            user_id=self.user_id,
            task_name='待更新任务',
            result_data='{"results": []}',
        )
        db.session.add(task)
        db.session.commit()

        response = self.client.put(
            f'/tasks/{task.id}',
            json={'result_data': {'results': [{'address': '新地址'}]}},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIs(response.get_json()['success'], True)


if __name__ == '__main__':
    unittest.main()
